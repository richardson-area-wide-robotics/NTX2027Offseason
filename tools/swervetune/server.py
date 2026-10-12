"""The GUI's server: a small local web server between the browser and the robot.

Started by ``py -3.12 tools/swervetune gui``. It listens on 127.0.0.1 only, serves the page in
``web/``, and answers the page's JSON requests by calling the same modules the command line uses.
Nothing here is reachable from another computer, and it needs no internet - it works in a pit.

Two safety details:

* The robot's heartbeat is gated on the **browser**: the page polls ``/api/live`` ten times a
  second, and if it stops (tab closed, laptop asleep) the heartbeat stops and any test on the
  robot ends within half a second.
* The GUI deadman (hold the space bar) must be refreshed every 100 ms by the page while the key is
  held. A dropped refresh releases it.
"""

from __future__ import annotations

import json
import math
import mimetypes
import os
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from . import (advisor, akit, contract as C, diagnose, explain, monitor, plant, predict, rehearse,
               runs, yagslcfg)

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PROGRESS = os.path.join(runs.RUNS, "setup_progress.json")


def clean(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return o


class Session:
    """Everything the GUI is connected to. One per server."""

    def __init__(self):
        self.lock = threading.RLock()
        self.link = None
        self.target = None
        self.project = None
        self.monitor = monitor.Monitor()
        self.flags = []
        self.last_poll = 0.0
        self.deadman_until = 0.0
        self.test_thread = None
        self.test_state = {"running": False}
        self.last_run = None
        self.connect_error = ""

    # ------------------------------------------------------------------ browser presence
    def browser_alive(self):
        alive = time.monotonic() - self.last_poll < 0.5
        if self.link is not None:
            self.link.set_gui_deadman(alive and time.monotonic() < self.deadman_until)
        return alive

    # ------------------------------------------------------------------ project
    def set_project(self, name):
        for d in yagslcfg.find_projects(runs.REPO):
            if os.path.basename(d) == name:
                self.project = yagslcfg.Project(d)
                lim = self.project.phys.get("currentLimit", {})
                self.monitor = monitor.Monitor(float(lim.get("drive", 40)))
                return True
        return False

    def reload_project(self):
        if self.project:
            self.set_project(self.project.name)

    # ------------------------------------------------------------------ robot
    def connect(self, target, host=None):
        from . import link as L

        self.disconnect()
        if L.ntcore is None:
            self.connect_error = L.INSTALL_HINT
            return False
        team = L.team_from_project(self.project.path) if self.project else None
        hosts = L.candidate_hosts(team=team, host=host if target == "host" else None,
                                  sim=target == "sim")
        lk = L.RobotLink(hosts, client_name="swervetune-gui")
        if not lk.wait_connected(6.0):
            lk.close()
            self.connect_error = ("No robot answered at " + ", ".join(hosts) + ". Is robot code "
                                  "running? Is the laptop on the robot's network?")
            return False
        if not lk.has_harness():
            lk.close()
            self.connect_error = "Connected, but this robot code does not have SwerveTune installed."
            return False
        proto = lk.get("int", C.PROTOCOL)
        if proto != C.PROTOCOL_VERSION:
            lk.close()
            self.connect_error = (f"Robot speaks protocol {proto}, this tool {C.PROTOCOL_VERSION}. "
                                  "Deploy the code from this branch.")
            return False
        lk.start_heartbeat(gate=self.browser_alive)
        self.link, self.target, self.connect_error = lk, target, ""
        name = lk.robot_info().get("name")
        if name and (not self.project or self.project.name != name):
            self.set_project(name)
        return True

    def disconnect(self):
        if self.link:
            try:
                self.link.close()
            finally:
                self.link = None
                self.target = None

    def limits(self):
        if not self.project:
            return {"steer": 20.0, "drive": 40.0}
        lim = self.project.phys.get("currentLimit", {})
        return {"steer": float(lim.get("angle", 20)), "drive": float(lim.get("drive", 40))}

    # ------------------------------------------------------------------ tests
    def start_test(self, test, module, args):
        if self.test_state.get("running"):
            return False, "A test is already running."
        if not self.link:
            return False, "Not connected to a robot."
        self.test_state = {"running": True, "test": test, "module": module, "state": "SENDING",
                           "message": "Sending to the robot...", "progress": 0.0}

        def work():
            try:
                gains = self.link.gains()

                def on_status(st):
                    self.test_state.update(state=st["state"], message=st["message"],
                                           progress=st["progress"])

                res = self.link.run_test(test, module, args, on_status=on_status)
                doc = res.to_json()
                if not res.accepted:
                    self.test_state.update(running=False, state="REFUSED", message=res.message)
                    return
                lim = self.limits()
                rep = advisor.analyze(doc, gains,
                                      current_limit=lim["steer" if test == "steer_step" else "drive"])
                path = runs.save(doc, rep, gains)
                self.last_run = os.path.basename(path)
                self.test_state.update(running=False, state=res.outcome, message=res.message,
                                       run=self.last_run, progress=1.0)
            except Exception as e:  # noqa: BLE001 - the GUI must hear about any failure
                traceback.print_exc()
                self.test_state.update(running=False, state="ERROR", message=str(e))

        self.test_thread = threading.Thread(target=work, name="swervetune-test", daemon=True)
        self.test_thread.start()
        return True, "Started."


S = Session()


# ---------------------------------------------------------------------------- handlers


def api_projects(_):
    names = [os.path.basename(d) for d in yagslcfg.find_projects(runs.REPO)]
    return {"projects": names, "current": S.project.name if S.project else None}


def api_set_project(body):
    if not S.set_project(body.get("name", "")):
        return {"ok": False, "error": "No such project."}
    return {"ok": True, "current": S.project.name}


def api_lint(_):
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    S.reload_project()
    return {"ok": True, "project": S.project.name, "summary": yagslcfg.summary(S.project),
            "findings": yagslcfg.lint(S.project),
            "modules": {n: S.project.module(n) for n in S.project.module_names()},
            "pidf": S.project.pidf, "physical": S.project.phys, "swervetune": S.project.tune,
            "swervedrive": S.project.data["swervedrive.json"]}


def api_connect(body):
    with S.lock:
        ok = S.connect(body.get("target", "robot"), body.get("host"))
    return {"ok": ok, "error": S.connect_error}


def api_disconnect(_):
    S.disconnect()
    return {"ok": True}


def api_state(_):
    S.last_poll = time.monotonic()
    st = {"connected": S.link is not None and S.link.is_connected(), "target": S.target,
          "project": S.project.name if S.project else None, "test": S.test_state,
          "last_run": S.last_run, "connect_error": S.connect_error}
    st.update(motor_kinds=C.MOTOR_KINDS, max_override_s=C.MAX_OVERRIDE_S)
    if S.link:
        st.update(robot=S.link.robot_info(), environment=S.link.environment(),
                  status=S.link.status(), gains=S.link.gains())
    return st


def api_live(_):
    S.last_poll = time.monotonic()
    if not S.link:
        return {"connected": False}
    live = S.link.live()
    names = S.link.robot_info()["modules"]
    S.flags = S.monitor.update(live, names, S.link.environment().get("active"))
    return {"connected": S.link.is_connected(), "live": live, "flags": S.flags,
            "status": S.link.status(), "test": S.test_state, "names": names,
            "locations": S.link.robot_info()["locations"],
            "deadman": S.link.get("bool", C.STATUS_DEADMAN_HELD),
            "motor_guard": {k: v for k, v in S.link.motors().items() if k != "motors"}}


def api_motor_override(body):
    if not S.link:
        return {"ok": False, "error": "Not connected."}
    seconds = max(0.0, min(float(body.get("seconds", C.MAX_OVERRIDE_S)), C.MAX_OVERRIDE_S))
    return {"ok": True, "message": S.link.override_motors(str(body.get("name") or "ALL"), seconds)}


def api_env(body):
    if not S.link:
        return {"ok": False, "error": "Not connected."}
    mode = body.get("mode")
    if mode == "FIELD" and not (body.get("space_forward") and body.get("space_side")):
        return {"ok": False, "error": "Measure the clear floor ahead and to each side first."}
    S.link.set_environment(mode, body.get("apriltags"), body.get("space_forward"),
                           body.get("space_side"), body.get("speed_cap"))
    time.sleep(0.25)
    return {"ok": True, "environment": S.link.environment()}


def api_test(body):
    ok, msg = S.start_test(body.get("test"), body.get("module", "ALL"), body.get("args") or {})
    return {"ok": ok, "message": msg}


def api_abort(_):
    if S.link:
        S.link.abort()
    return {"ok": True}


def api_stop(_):
    if S.link:
        S.link.stop()
    return {"ok": True}


def api_deadman(body):
    S.deadman_until = time.monotonic() + 0.3 if body.get("held") else 0.0
    S.browser_alive()
    return {"ok": True}


def api_gains(body):
    if not S.link:
        return {"ok": False, "error": "Not connected."}
    values = {k: float(v) for k, v in (body.get("values") or {}).items()}
    status, gains = S.link.set_gains(values)
    return {"ok": "REFUSED" not in status, "status": status, "gains": gains}


def _edits_from(body):
    kind = body.get("kind")
    if kind == "gains":
        live = S.link.gains() if S.link else {}
        prefixes = body.get("keys")
        g = {k: v for k, v in live.items() if isinstance(v, float) and math.isfinite(v)
             and (not prefixes or any(k.startswith(p) for p in prefixes))}
        return yagslcfg.edits_for_gains(S.project, g)
    if kind == "offsets":
        doc = runs.load(body["file"])
        res = advisor.offsets_from_capture(doc, S.project.offsets())
        return [(f"modules/{n}.json", ("absoluteEncoderOffset",), r["new"]) for n, r in res.items()]
    if kind == "edit":
        return [(body["file"], tuple(body["path"]), body["value"])]
    if kind == "edits":
        return [(e["file"], tuple(e["path"]), e["value"]) for e in body["edits"]]
    raise ValueError("unknown save kind")


def api_save_preview(body):
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    changes = S.project.preview(_edits_from(body))
    return {"ok": True, "diff": "".join(yagslcfg.diff(o, n, f) for f, (o, n) in changes.items()),
            "files": list(changes)}


def api_save_apply(body):
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    text = S.project.apply(_edits_from(body))
    return {"ok": True, "diff": text}


def api_runs(_):
    return {"runs": runs.list_runs(100)}


def api_run(name):
    doc = runs.load(name)
    # Re-analyse on every open: the advisor may be newer than the run, and the channels are kept.
    lim = S.limits()
    doc["report"] = advisor.analyze(doc, doc.get("gains"),
                                    current_limit=lim["steer" if doc.get("test") == "steer_step" else "drive"])
    doc["explain"] = explain.explain(doc, doc.get("gains"), lim)
    return doc


def api_export(body):
    doc = runs.load(body["file"])
    path = os.path.join(runs.RUNS, os.path.splitext(doc["_file"])[0] + ".wpilog")
    names = akit.export_run(doc, path)
    return {"ok": True, "path": path, "entries": len(names), "sysid": doc.get("test") == "drive_ff"}


def api_predict(body):
    """'What if': the same run, predicted with changed gains. Gains not given keep their value."""
    doc = runs.load(body["file"])
    now = {k: float(v) for k, v in (doc.get("gains") or {}).items() if isinstance(v, (int, float))}
    new = dict(now)
    new.update({k: float(v) for k, v in (body.get("gains") or {}).items()})
    lim = S.limits() if not doc.get("practice") else {"steer": 20.0, "drive": 40.0}
    loop = "steer" if doc.get("test") == "steer_step" else "drive"
    return predict.predict(doc, now, new, int(body.get("module", 0)), current_limit=lim.get(loop))


def api_analyze(body):
    doc = runs.load(body["file"])
    return advisor.analyze(doc, doc.get("gains"), measured_forward_m=body.get("tape_forward"),
                           measured_lateral_m=body.get("tape_lateral"))


def api_offsets(body):
    doc = runs.load(body["file"])
    return advisor.offsets_from_capture(doc, S.project.offsets() if S.project else {})


def api_handcheck(body):
    doc = runs.load(body["file"])
    return advisor.hand_check(doc, body.get("kind", "wheel"), int(body.get("sign", 1)))


def api_symptoms(_):
    return {"symptoms": [{"id": s["id"], "title": s["title"], "looks_like": s["looks_like"]}
                         for s in diagnose.SYMPTOMS]}


def api_diagnose(sid):
    lint = yagslcfg.lint(S.project) if S.project else []
    return diagnose.evaluate(sid, lint, S.flags)


def api_practice(body):
    loop = body.get("loop", "steer")
    surface = body.get("surface", "floor")
    g = {k: float(v) for k, v in (body.get("gains") or {}).items()}
    if loop == "steer":
        ch = plant.steer_step(rehearse.STEER_PATTERN, kP=g.get("Steer/kP", 0.01),
                              kI=g.get("Steer/kI", 0), kD=g.get("Steer/kD", 0),
                              i_zone=g.get("Steer/IZone", 0), ramp_s=g.get("Steer/RampS", 0),
                              surface=surface)
        doc = {"test": "steer_step", "module": "FL"}
    elif loop == "drive":
        m = rehearse.MODULES[0]
        ch = plant.drive_step(rehearse.DRIVE_PATTERN, kP=g.get("Drive/kP", 0.002),
                              kI=g.get("Drive/kI", 0), kD=g.get("Drive/kD", 0),
                              ramp_s=g.get("Drive/RampS", 0), surface=surface,
                              meas_period_ms=int(g.get("Drive/VelPeriodMs") or 32),
                              meas_depth=int(g.get("Drive/VelDepth") or 8),
                              ff=(g.get(f"FF/{m}/kS", 0), g.get(f"FF/{m}/kV", 2.915),
                                  g.get(f"FF/{m}/kA", 0)))
        doc = {"test": "drive_step", "module": "ALL"}
    elif loop == "slip":
        ch, meta = plant.wall_push(mu_static=float(body.get("mu", 1.1)),
                                   limit_before_a=g.get("Limit/Drive", 40.0))
        doc = {"test": "slip", "module": "ALL", "meta": meta}
    else:
        ch = plant.drive_ff(surface=surface, quasi_s=6, max_v=6,
                            meas_period_ms=int(g.get("Drive/VelPeriodMs") or 16),
                            meas_depth=int(g.get("Drive/VelDepth") or 2))
        doc = {"test": "drive_ff", "module": "ALL", "meta": {"kv_nominal": 2.915}}
    doc.update(channels=ch, practice=True, env="FIELD" if surface == "floor" else "BLOCKS",
               robot={"name": "practice pod", "modules": rehearse.MODULES}, outcome="DONE")
    rep = advisor.analyze(doc, g)
    path = runs.save(doc, rep, g, practice=True)
    doc["report"] = rep
    doc["explain"] = explain.explain(doc, g, {"steer": 20.0, "drive": 40.0})
    doc["_file"] = os.path.basename(path)
    doc["gains"] = g
    return doc


def api_progress_get(_):
    try:
        with open(PROGRESS, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def api_progress_put(body):
    os.makedirs(runs.RUNS, exist_ok=True)
    data = api_progress_get(None)
    data.update(body or {})
    with open(PROGRESS, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    return data


def api_sim(body):
    if not S.link:
        return {"ok": False, "error": "Not connected."}
    S.link.sim_enable(bool(body.get("on")))
    return {"ok": True}


GET = {"/api/projects": api_projects, "/api/lint": api_lint, "/api/state": api_state,
       "/api/live": api_live, "/api/runs": api_runs, "/api/symptoms": api_symptoms,
       "/api/progress": api_progress_get}
POST = {"/api/project": api_set_project, "/api/connect": api_connect,
        "/api/disconnect": api_disconnect, "/api/env": api_env, "/api/test": api_test,
        "/api/abort": api_abort, "/api/stop": api_stop, "/api/deadman": api_deadman,
        "/api/gains": api_gains, "/api/save/preview": api_save_preview,
        "/api/save/apply": api_save_apply, "/api/analyze": api_analyze,
        "/api/offsets": api_offsets, "/api/handcheck": api_handcheck,
        "/api/practice": api_practice, "/api/progress": api_progress_put, "/api/sim": api_sim,
        "/api/motors/override": api_motor_override, "/api/predict": api_predict,
        "/api/export": api_export}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):  # keep the console readable
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(clean(body)).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _guard_origin(self):
        # Only this page may drive the robot: refuse requests from any other site's page.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        return origin is None or origin.endswith("//" + host)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in GET:
                return self._send(200, GET[path](None))
            if path.startswith("/api/runs/"):
                return self._send(200, api_run(unquote(path[len("/api/runs/"):])))
            if path.startswith("/api/diagnose/"):
                return self._send(200, api_diagnose(unquote(path[len("/api/diagnose/"):])))
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            full = os.path.normpath(os.path.join(WEB, rel))
            if not full.startswith(WEB) or not os.path.isfile(full):
                return self._send(404, {"error": "not found"})
            with open(full, "rb") as fh:
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                return self._send(200, fh.read(), ctype)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"ok": False, "error": str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._guard_origin():
            return self._send(403, {"ok": False, "error": "cross-origin request refused"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if path not in POST:
                return self._send(404, {"ok": False, "error": "no such action"})
            return self._send(200, POST[path](body))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"ok": False, "error": str(e)})


def main(args):
    if getattr(args, "project", None):
        S.set_project(os.path.basename(args.project))
    else:
        projects = yagslcfg.find_projects(runs.REPO)
        if projects:
            S.set_project(os.path.basename(projects[0]))
    port = getattr(args, "port", 5806)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Swerve tools running at {url}  (Ctrl+C to stop)")
    if not getattr(args, "no_browser", False):
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        S.disconnect()
        srv.server_close()
    return 0
