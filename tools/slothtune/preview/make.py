"""Builds a preview of Sloth Tune and the drive team's Elastic dashboard: one folder of static
files that looks and works like the real thing, for people to look over and comment on without a
robot or this laptop.

The tool's page is its real code (web/), unchanged. Its server is replaced by mock.js, which
answers from a recording of the real server talking to the robot code in the simulator; anything
that would move the robot or save a file says so instead. The dashboard is a copy of Elastic drawn
from the team's layout (elastic/drive-team-layout.json) and the exact text the robot code publishes
at a few moments (elastic-moments.json, from PreviewScenariosTest in common/slothtune).

    # 1. The robot code in the simulator, in another terminal:
    cd Peashooter
    ./gradlew simulateJava -PheadlessSim
    # 2. Record and build (from tools/):
    py -3.12 -m slothtune.preview.make --project Peashooter

It enables the simulated robot and runs one steering test (the Live tab replays it), which saves one
run in runs/ like any other. The result is preview/site/: serve it with any static web server
(py -3.12 -m http.server -d slothtune/preview/site) or publish it. --no-record rebuilds the site
from the last recording, after a change to the page only.

To refresh the dashboard text after the robot code's wording changes:

    cd Peashooter
    SLOTHTUNE_PREVIEW_OUT=../tools/slothtune/preview/elastic-moments.json ./gradlew test --tests frc.lib.slothtune.PreviewScenariosTest
"""

import argparse
import json
import math
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
from html import escape as html_escape
from http.server import ThreadingHTTPServer
from urllib.parse import quote, urlencode

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
                                               headers={"Content-Type": "application/json", "X-SlothTune-Token": self.token}))


def _q(path, **params):
    # As the page builds them (encodeURIComponent): the mock looks answers up by the exact URL.
    return path + "?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())


# Example multimeter readings at each bus's far end, terminator in then out: what the termination
# check says to each is recorded, so the preview answers them.
TERMINATION_EXAMPLES = (("60", "120"), ("120", "120"), ("120", "OL"), ("120", ""))


def _recalc(page, **params):
    return f"https://www.reca.lc/{page}?" + urlencode({k: json.dumps(v) for k, v in params.items()})


# Made-up ReCalc designs for the Systems tab, used only for a mechanism the robot has no settings for
# (the ribbon says so), so the tab shows one set up with its safe test.
SYSTEMS_EXAMPLES = {
    "Shooter": {"link": _recalc("flywheel", motor={"name": "NEO Vortex", "quantity": 2},
                                  ratio={"magnitude": 1, "ratioType": "Reduction"}, shooterDiameter={"s": 4, "u": "in"},
                                  shooterWeight={"s": 2, "u": "lb"}, shooterTargetSpeed={"s": 3950, "u": "rpm"})},
    "Intake pivot": {"link": _recalc("arm", motor={"name": "NEO Vortex", "quantity": 1},
                                       ratio={"magnitude": 45, "ratioType": "Reduction"}, armLength={"s": 12, "u": "in"},
                                       load={"s": 8, "u": "lb"}, minAngle={"s": 0, "u": "deg"}, maxAngle={"s": 120, "u": "deg"})},
}


def record(project_name, *, seconds=14.0, say=print, note="", marks=None):
    """Talks to the simulator through the tool's own server, as the page would, and keeps every answer."""
    from .. import diagnose, progress, server, setup as SP, systems as SY

    # A scratch progress file: the recording never touches this laptop's real checklists.
    scratch = tempfile.mkdtemp(prefix="slothtune-preview-")
    # The Systems examples, in memory only: the robot's slothtune.json is never written.
    real_settings, used = SY.settings, []

    def example_settings(project):
        own = real_settings(project)
        out = {k: dict(v) for k, v in SYSTEMS_EXAMPLES.items() if k not in own}
        used[:] = sorted(out)
        return dict(out, **own)

    SY.settings = example_settings
    progress.PATH = os.path.join(scratch, "guide_progress.json")
    if marks:
        # Example checklist results for the preview (its ribbon says so), never this laptop's own.
        progress.update(project_name, marks)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    c = _Client(f"http://127.0.0.1:{httpd.server_address[1]}", server.TOKEN)
    rec = {"get": {}, "post": [], "live": [], "state": [], "started": {},
           "recorded": datetime.now(timezone.utc).isoformat(timespec="seconds"), "note": note}

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
        # What the robot reports before a battery is picked (its "Which battery is in?" alert), so
        # Troubleshoot's counts show a message that came and went.
        for _ in range(3):
            c.get("/api/live")
            time.sleep(0.6)
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
        # Each part's choices to record: one of most, every mechanism the code registers.
        picks = {kind: [which.get(kind, "")] for kind in SP.PARTS}
        if "system" in picks and server.S.project:
            picks["system"] = sorted(SY.in_code(server.S.project)) or [""]
        for path in sorted(server.GET):
            # The live pair is recorded above; a match log's summary needs a log file to read.
            if path in ("/api/live", "/api/state", "/api/logsummary"):
                continue
            if path == "/api/setup":
                for tab in SP.TOOLS:
                    key = _q(path, tab=tab)
                    rec["get"][key] = c.get(key)
            elif path == "/api/parts/plan":
                for kind, choices in picks.items():
                    for w in choices:
                        key = _q(path, kind=kind, which=w)
                        rec["get"][key] = c.get(key)
            else:
                rec["get"][path] = c.get(path)
        for bus in (rec["get"].get("/api/wiring") or {}).get("map", {}).get("buses") or []:
            for a, b in TERMINATION_EXAMPLES:
                post("/api/wiring/termination", {"ohms": a, "without": b, "bus": bus.get("name")})
        for s in diagnose.SYMPTOMS:
            key = "/api/diagnose/" + quote(s["id"], safe="")
            rec["get"][key] = c.get(key)
        # Each example mechanism's physics, asked as the page asks, so its Read it answers.
        mechs = [s for s in (rec["get"].get("/api/systems") or {}).get("systems") or [] if s.get("name") in used]
        for s in mechs:
            post("/api/systems/physics", {"name": s["name"], "kind": s.get("kind"), "units": s.get("units"),
                                          "settings": s.get("settings") or {}})
        if mechs:
            ex = " and ".join(s["name"] for s in mechs)
            rec["note"] = ((note + " ") if note else "") + (
                f"Systems shows made-up ReCalc designs for the {ex}, since {project_name} has none saved yet.")
        # A part's checklist once started, for Redo one part.
        for kind, choices in picks.items():
            for w in choices:
                sel = {"kind": kind, "which": w}
                c.post("/api/parts/start", sel)
                rec["started"][f"{kind}:{w}"] = c.get(_q("/api/parts/plan", **sel))
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
        SY.settings = real_settings
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


HUB_2026 = (4.63, 4.03)       # the blue hub's center, meters: the example drive aims at it


def field_example(rec):
    """The Live tab's field view needs a camera and a surveyed field, and the simulator has
    neither. When the recording has no survey, the preview stands the official 2026 layout in for
    one (the ribbon says so); ``drive_example`` then moves the robot. Returns the layout, or None."""
    got = rec["get"].get("/api/field") or {}
    if not got.get("ok") or got.get("surveyed"):
        return None
    from .. import fieldsurvey, server
    with open(os.path.join(fieldsurvey.FIELDS, "2026-rebuilt-welded.json"), encoding="utf-8") as fh:
        view = server.field_view(json.load(fh))
    rec["get"]["/api/field"] = dict(got, surveyed=True, file="the official 2026 layout (an example)", **view)
    for st in rec["state"]:
        if isinstance(st.get("environment"), dict):
            st["environment"].update(vision_available=True, vision_in_use=True)
    rec["note"] = ((rec.get("note") or "") + " Live's On the field is an example too: the official 2026 tag "
                   "layout stands in for this field's survey, and the robot drives a made-up loop aiming at "
                   "the blue hub, since the simulator has no camera.").strip()
    return view


def tags_in_view(tags, x, y, heading_deg, fov_deg=70.0, range_m=5.0):
    """The tags a forward camera at the robot's center would see: in range, inside its field of
    view, and facing it."""
    out = []
    for t in tags:
        dx, dy = t["x"] - x, t["y"] - y
        d = math.hypot(dx, dy)
        off = (math.degrees(math.atan2(dy, dx)) - heading_deg + 540) % 360 - 180
        faces = math.cos(math.radians(t["yaw_deg"])) * -dx + math.sin(math.radians(t["yaw_deg"])) * -dy
        if 0.3 < d <= range_m and abs(off) <= fov_deg / 2 and faces > 0.2 * d:
            out.append(t["id"])
    return sorted(out)


def drive_example(frames, view, center=(2.5, 4.03), radius=(0.9, 1.5)):
    """One loop beside the blue hub over the replayed frames, always aiming at the hub; the
    cameras' own pose wanders a little off odometry's, as a real one does."""
    n = max(1, len(frames))
    for i, f in enumerate(frames):
        th = 2 * math.pi * i / n
        x, y = center[0] + radius[0] * math.cos(th), center[1] + radius[1] * math.sin(th)
        hd = math.degrees(math.atan2(HUB_2026[1] - y, HUB_2026[0] - x))
        live = f["live"]
        live["pose"], live["heading"] = [x, y, hd], hd
        live["vision_pose"] = [x + 0.05 * math.sin(3 * th), y - 0.04 * math.cos(2 * th), hd + 1.5 * math.sin(th)]
        f["seen_tags"] = tags_in_view(view["tags"], x, y, hd)


def build(rec_dir=REC, site=SITE, web=WEB):
    """Assembles the site from the tool's page, the recording and the dashboard. Returns its files."""
    with open(os.path.join(rec_dir, "rec.json"), encoding="utf-8") as fh:
        rec = json.load(fh)
    example_field = field_example(rec)
    shutil.rmtree(site, ignore_errors=True)
    os.makedirs(os.path.join(site, "img"))
    os.makedirs(os.path.join(site, "rec", "runs"))
    with open(os.path.join(web, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    scripts = re.findall(r'<script src="([^"]+)"></script>', html)
    for f in scripts:
        shutil.copy(os.path.join(web, f), os.path.join(site, f))
    shutil.copytree(os.path.join(web, "img"), os.path.join(site, "img"), dirs_exist_ok=True)
    # The artifact host refuses an SVG with a DOCTYPE; a few of the part drawings carry SVG 1.1's,
    # which the browser ignores anyway. The site's copies go without it (the tool's stay unchanged).
    for d, _, fs in os.walk(os.path.join(site, "img")):
        for f in fs:
            if f.endswith(".svg"):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    svg = fh.read()
                bare = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg, flags=re.I)
                if bare != svg:
                    with open(os.path.join(d, f), "w", encoding="utf-8", newline="") as fh:
                        fh.write(bare)
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
    # One line, so the tool below it keeps its full height: the long story is behind "About".
    ribbon = f"""<div class="pv-ribbon">
  <span class="pv-tag">Preview</span>
  <span class="pv-note">Recorded from the real tool in {project}'s simulator, {_when(rec["recorded"])}. Buttons that would move the robot or save a file say so instead.</span>
  <details class="pv-about"><summary>About this preview</summary>
    <div class="pv-about-body">Recorded from the real tool, connected to {project}'s robot code in the simulator, {_when(rec["recorded"])}.
    The robot replays the steering test it ran. Buttons that would move the robot or save a file say so instead.{(" " + html_escape(rec["note"])) if rec.get("note") else ""}</div></details>
  <span class="pv-seg" role="group" aria-label="Show">
    <button data-pv="tools" aria-pressed="true">Sloth Tune (laptop)</button>
    <button data-pv="elastic" aria-pressed="false">Elastic (Driver Station)</button>
  </span>
</div>
<section id="pv-elastic" aria-label="Elastic dashboard"></section>
"""
    with open(os.path.join(site, "index.html"), "w", encoding="utf-8", newline="\n") as fh:
        # The charset first: a server that sends none (python -m http.server) otherwise reads the
        # scripts as cp1252, and their "·" and "Ω" come out as two letters each.
        fh.write(f'<meta charset="utf-8">\n<title>Sloth Tune Preview</title>\n<link rel="stylesheet" href="style.css">\n'
                 f'<link rel="stylesheet" href="preview.css">\n{ribbon}{body}\n')

    # The steering test's motion and a moment either side, not the idle time after it.
    live = [x for x in rec["live"] if x.get("connected") and x.get("live")]
    moving = [i for i in range(1, len(live)) if live[i]["live"]["steer"] != live[i - 1]["live"]["steer"]]
    if moving:
        live = live[max(0, moving[0] - 10):moving[-1] + 15]
    rec["live"] = [x for x in live if x["live"].get("mode") != "DISABLED"] or live
    if example_field:
        drive_example(rec["live"], example_field)
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
    ap = argparse.ArgumentParser(prog="slothtune.preview.make", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default="Peashooter", help="robot project folder (default Peashooter)")
    ap.add_argument("--no-record", action="store_true", help="rebuild the site from the last recording")
    ap.add_argument("--seconds", type=float, default=14.0, help="how long to record the live view")
    ap.add_argument("--note", default="", help="a sentence for the ribbon, e.g. what in it is an example")
    ap.add_argument("--marks", help="a JSON file of example checklist marks to record with")
    a = ap.parse_args(argv)
    if not a.no_record:
        marks = None
        if a.marks:
            with open(a.marks, encoding="utf-8") as fh:
                marks = json.load(fh)
        record(a.project, seconds=a.seconds, note=a.note, marks=marks)
    elif not os.path.exists(os.path.join(REC, "rec.json")):
        sys.exit("No recording yet: run without --no-record, with the simulator running.")
    files = build()
    size = sum(os.path.getsize(os.path.join(SITE, f)) for f in files)
    print(f"{len(files)} files, {size / 1e6:.1f} MB in {SITE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
