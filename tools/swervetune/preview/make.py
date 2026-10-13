"""Builds a preview of Swerve Tools and the drive team's Elastic dashboard: one folder of static
files that looks and works like the real thing, for people to look over and comment on without a
robot or this laptop.

The tool's page is its real code (web/), unchanged. Its server is replaced by mock.js, which
answers from a recording of the real server talking to the robot code in the simulator; anything
that would move the robot or save a file says so instead. The dashboard is a copy of Elastic drawn
from the team's layout (elastic/drive-team-layout.json) and the exact text the robot code publishes
at a few moments (elastic-moments.json, from PreviewScenariosTest in common/swervetune).

    # 1. The robot code in the simulator, in another terminal:
    cd Peashooter
    ./gradlew simulateJava -PheadlessSim
    # 2. Record and build (from tools/):
    py -3.12 -m swervetune.preview.make --project Peashooter

It enables the simulated robot and runs one steering test (the Live tab replays it), which saves one
run in runs/ like any other. The result is preview/site/: serve it with any static web server
(py -3.12 -m http.server -d swervetune/preview/site) or publish it. --no-record rebuilds the site
from the last recording, after a change to the page only.

To refresh the dashboard text after the robot code's wording changes:

    cd Peashooter
    SWERVETUNE_PREVIEW_OUT=../tools/swervetune/preview/elastic-moments.json ./gradlew test --tests frc.lib.swervetune.PreviewScenariosTest
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
WEB = os.path.join(PKG, "web")
LAYOUT = os.path.join(PKG, "elastic", "drive-team-layout.json")
MOMENTS = os.path.join(HERE, "elastic-moments.json")
REC = os.path.join(HERE, "rec")
SITE = os.path.join(HERE, "site")
MAX_RUNS = 60


# ---------------------------------------------------------------------------- recording


class _Client:
    """The page's side of the conversation: the same requests, with this run's token."""

    def __init__(self, base, token):
        self.base, self.token = base, token

    def _go(self, req):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except ValueError:
                return {"ok": False, "error": f"HTTP {e.code}"}

    def get(self, path):
        return self._go(urllib.request.Request(self.base + path))

    def post(self, path, body):
        return self._go(urllib.request.Request(self.base + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                               headers={"Content-Type": "application/json", "X-SwerveTune-Token": self.token}))


def _q(path, **params):
    # As the page builds them (encodeURIComponent): the mock looks answers up by the exact URL.
    return path + "?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())


def record(project_name, *, seconds=14.0, say=print):
    """Talks to the simulator through the tool's own server, as the page would, and keeps every answer."""
    from .. import diagnose, progress, server, setup as SP

    # A scratch progress file: the recording never touches this laptop's real checklists.
    scratch = tempfile.mkdtemp(prefix="swervetune-preview-")
    progress.PATH = os.path.join(scratch, "guide_progress.json")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    c = _Client(f"http://127.0.0.1:{httpd.server_address[1]}", server.TOKEN)
    rec = {"get": {}, "post": [], "live": [], "state": [], "started": {},
           "recorded": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    def post(path, body):
        r = c.post(path, body)
        rec["post"].append({"path": path, "body": body, "resp": r})
        return r

    try:
        r = post("/api/project", {"name": project_name})
        if r.get("ok") is False:
            raise SystemExit(f"No robot project {project_name!r}: {r.get('error')}")
        r = post("/api/connect", {"target": "sim", "host": ""})
        if not r.get("ok"):
            raise SystemExit("Could not connect to the simulator. Start the robot code first:\n"
                             f"    cd {project_name}\n    ./gradlew simulateJava -PheadlessSim\n({r.get('error')})")
        time.sleep(2)
        post("/api/battery/pick", {"id": "7"})
        # Wheels moving for the Live tab: one steering test on the simulated robot.
        post("/api/sim", {"on": True})
        time.sleep(1.5)
        r = post("/api/test", {"test": "steer_step", "module": "all", "args": {}})
        say(f"steering test: {r.get('message') or r.get('error')}")
        end = time.time() + seconds
        while time.time() < end:
            rec["live"].append(c.get("/api/live"))
            time.sleep(0.1)
        end = time.time() + 90
        while time.time() < end and (c.get("/api/state").get("test") or {}).get("running"):
            time.sleep(0.5)
        post("/api/sim", {"on": False})
        time.sleep(1.5)
        rec["state"] = [c.get("/api/state")]

        # Every GET the server has, with the parameters the page sends.
        names = server.S.project.module_names() if server.S.project else ["frontleft"]
        which = {"module": names[0], "motor": names[0] + " drive", "camera": "front", "gyro": ""}
        for path in sorted(server.GET):
            # The live pair is recorded above; a match log's summary needs a log file to read.
            if path in ("/api/live", "/api/state", "/api/logsummary"):
                continue
            if path == "/api/setup":
                for tab in SP.TOOLS:
                    key = _q(path, tab=tab)
                    rec["get"][key] = c.get(key)
            elif path == "/api/parts/plan":
                for kind in SP.PARTS:
                    key = _q(path, kind=kind, which=which.get(kind, ""))
                    rec["get"][key] = c.get(key)
            else:
                rec["get"][path] = c.get(path)
        for s in diagnose.SYMPTOMS:
            key = "/api/diagnose/" + quote(s["id"], safe="")
            rec["get"][key] = c.get(key)
        # A part's checklist once started, for Redo one part.
        for kind in SP.PARTS:
            sel = {"kind": kind, "which": which.get(kind, "")}
            c.post("/api/parts/start", sel)
            rec["started"][f"{kind}:{sel['which']}"] = c.get(_q("/api/parts/plan", **sel))
            c.post("/api/parts/stop", sel)
        # The saved runs the Runs tab lists, newest first, so a row opens.
        os.makedirs(os.path.join(REC, "runs"), exist_ok=True)
        for f in os.listdir(os.path.join(REC, "runs")):
            os.remove(os.path.join(REC, "runs", f))
        listed = [x.get("file") for x in (rec["get"].get("/api/runs") or {}).get("runs") or [] if x.get("file")]
        for f in listed[:MAX_RUNS]:
            with open(os.path.join(REC, "runs", f), "w", encoding="utf-8") as fh:
                json.dump(c.get("/api/runs/" + quote(f, safe="")), fh, separators=(",", ":"))
        c.post("/api/disconnect", {})
    finally:
        httpd.shutdown()
        shutil.rmtree(scratch, ignore_errors=True)
    with open(os.path.join(REC, "rec.json"), "w", encoding="utf-8") as fh:
        json.dump(rec, fh, separators=(",", ":"))
    say(f"recorded {len(rec['get'])} answers, {len(rec['live'])} live samples, {len(listed[:MAX_RUNS])} runs")
    return rec


# ---------------------------------------------------------------------------- the site


def theme_css(css):
    """The tool follows the laptop's light or dark setting; a published page also follows the
    viewer's own switch (data-theme on the root). Raises if the stylesheet's shape has changed."""
    m = re.search(r"@media \(prefers-color-scheme: dark\) \{\n  :root \{\n(.*?)\n  \}\n\}\n", css, re.S)
    if not m:
        raise ValueError("style.css: no dark :root block")
    dark = m.group(1)
    css = css.replace(m.group(0), '@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {\n' + dark
                      + '\n  }\n}\n:root[data-theme="dark"] {\n' + dark + "\n}\n")
    # Every other dark-only rule: guarded the same way, and repeated for the switch.
    out = []
    for block in re.findall(r"@media \(prefers-color-scheme: dark\) \{\n((?:  [^\n]*\n|\n)*?)\}\n", css):
        if ":root:not" in block:
            continue
        rules = re.findall(r"^  ([^{\n/][^{\n]*)\{([^}]*)\}", block, re.M)
        if not rules:
            continue
        guarded = "".join(f'  :root:not([data-theme="light"]) {sel.strip()} {{{body}}}\n' for sel, body in rules)
        switched = "".join(f':root[data-theme="dark"] {sel.strip()} {{{body}}}\n' for sel, body in rules)
        out.append((block, guarded, switched))
    for block, guarded, switched in out:
        css = css.replace("@media (prefers-color-scheme: dark) {\n" + block + "}\n",
                          "@media (prefers-color-scheme: dark) {\n" + guarded + "}\n" + switched)
    # A sticky bar under the phone's status bar, not behind it.
    return css.replace(".top { position: sticky; top: 0;", ".top { position: sticky; top: env(safe-area-inset-top, 0px);")


def _when(iso):
    """'Oct 13 at 1:49 PM CDT (18:49 UTC)': local first, UTC beside it to match a log line."""
    utc = datetime.fromisoformat(iso)
    local = utc.astimezone()
    name = local.tzname() or ""
    abbr = "".join(w[0] for w in name.split()) if " " in name else name
    return f"{local:%b} {local.day} at {local:%I:%M %p}".replace(" 0", " ") + f" {abbr} ({utc:%H:%M} UTC)"


def build(rec_dir=REC, site=SITE, web=WEB):
    """Assembles the site from the tool's page, the recording and the dashboard. Returns its files."""
    with open(os.path.join(rec_dir, "rec.json"), encoding="utf-8") as fh:
        rec = json.load(fh)
    shutil.rmtree(site, ignore_errors=True)
    os.makedirs(os.path.join(site, "img"))
    os.makedirs(os.path.join(site, "rec", "runs"))
    with open(os.path.join(web, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    scripts = re.findall(r'<script src="([^"]+)"></script>', html)
    for f in scripts:
        shutil.copy(os.path.join(web, f), os.path.join(site, f))
    shutil.copy(os.path.join(web, "img", "frc-control-system-layout-rev.svg"), os.path.join(site, "img"))
    for f in ("mock.js", "preview.js", "preview.css"):
        shutil.copy(os.path.join(HERE, f), os.path.join(site, f))
    with open(os.path.join(web, "style.css"), encoding="utf-8") as fh:
        css = theme_css(fh.read())
    with open(os.path.join(site, "style.css"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(css)

    # The page: the tool's own body, the mock ahead of its scripts, the ribbon and dashboard ahead of it.
    body = html[html.index("<body>") + len("<body>"):html.index("</body>")].strip()
    first, last = scripts[0], scripts[-1]
    body = body.replace(f'<script src="{first}"></script>', f'<script src="mock.js"></script>\n<script src="{first}"></script>', 1)
    body = body.replace(f'<script src="{last}"></script>', f'<script src="{last}"></script>\n<script src="preview.js"></script>', 1)
    project = next((p["body"].get("name") for p in rec["post"] if p["path"] == "/api/project"), "the robot")
    ribbon = f"""<div class="pv-ribbon">
  <span class="pv-tag">Preview</span>
  <span class="pv-note">Recorded from the real tool, connected to {project}'s robot code in the simulator, {_when(rec["recorded"])}.
    The robot replays the steering test it ran. Buttons that would move the robot or save a file say so instead.</span>
  <span class="pv-seg" role="group" aria-label="Show">
    <button data-pv="tools" aria-pressed="true">Swerve Tools (laptop)</button>
    <button data-pv="elastic" aria-pressed="false">Elastic (Driver Station)</button>
  </span>
</div>
<section id="pv-elastic" aria-label="Elastic dashboard"></section>
"""
    with open(os.path.join(site, "index.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'<title>Swerve Tools Preview</title>\n<link rel="stylesheet" href="style.css">\n'
                 f'<link rel="stylesheet" href="preview.css">\n{ribbon}{body}\n')

    # The steering test's motion and a moment either side, not the idle time after it.
    live = [x for x in rec["live"] if x.get("connected") and x.get("live")]
    moving = [i for i in range(1, len(live)) if live[i]["live"]["steer"] != live[i - 1]["live"]["steer"]]
    if moving:
        live = live[max(0, moving[0] - 10):moving[-1] + 15]
    rec["live"] = [x for x in live if x["live"].get("mode") != "DISABLED"] or live
    with open(os.path.join(site, "rec", "rec.json"), "w", encoding="utf-8") as fh:
        json.dump(rec, fh, separators=(",", ":"))
    runs = os.path.join(rec_dir, "runs")
    for f in sorted(os.listdir(runs)) if os.path.isdir(runs) else []:
        shutil.copy(os.path.join(runs, f), os.path.join(site, "rec", "runs", f))
    with open(LAYOUT, encoding="utf-8") as fh:
        layout = json.load(fh)
    with open(MOMENTS, encoding="utf-8") as fh:
        moments = json.load(fh)
    with open(os.path.join(site, "rec", "elastic.json"), "w", encoding="utf-8") as fh:
        json.dump({"layout": layout, "moments": moments}, fh)
    return sorted(os.path.relpath(os.path.join(d, f), site).replace(os.sep, "/") for d, _, fs in os.walk(site) for f in fs)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="swervetune.preview.make", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default="Peashooter", help="robot project folder (default Peashooter)")
    ap.add_argument("--no-record", action="store_true", help="rebuild the site from the last recording")
    ap.add_argument("--seconds", type=float, default=14.0, help="how long to record the live view")
    a = ap.parse_args(argv)
    if not a.no_record:
        record(a.project, seconds=a.seconds)
    elif not os.path.exists(os.path.join(REC, "rec.json")):
        sys.exit("No recording yet: run without --no-record, with the simulator running.")
    files = build()
    size = sum(os.path.getsize(os.path.join(SITE, f)) for f in files)
    print(f"{len(files)} files, {size / 1e6:.1f} MB in {SITE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
