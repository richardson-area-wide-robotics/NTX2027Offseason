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
from urllib.parse import parse_qsl, unquote, urlparse

from . import (advisor, akit, camcal, contract as C, diagnose, explain, fieldsurvey, geometry, logsummary,
               monitor, pdhports, plant, ppcheck, predict, rehearse, runs, wiring, yagslcfg)

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

    def wiring_map(self):
        if not self.project:
            return None
        if getattr(self, "_wiring", None) is None or self._wiring[0] != self.project.path:
            self._wiring = (self.project.path, wiring.load_map(self.project))
        return self._wiring[1]

    def feed_sample(self, live, m):
        """Collects (PDH volts, controller volts, PDH port current) per mapped controller."""
        hist = self.__dict__.setdefault("_feed", {})
        pdh = live.get("pdh") or {}
        currents, pv = pdh.get("currents") or [], pdh.get("voltage")
        for r in live.get("motors") or []:
            port = (m or {}).get("pdhPorts", {}).get(r.get("name"))
            if port is None or port >= len(currents) or r.get("bus_volts") is None:
                continue
            h = hist.setdefault(r["name"], [])
            h.append((pv, r["bus_volts"], currents[port]))
            del h[:-3000]

    def feed_resistances(self):
        return {n: wiring.feed_resistance(h) for n, h in self.__dict__.get("_feed", {}).items()}

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
                                      current_limit=lim["steer" if test == "steer_step" else "drive"],
                                      **advisor.robot_context(self.project))
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
    S.feed_sample(live, S.wiring_map())
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


def _layout_path():
    return os.path.join(S.project.path, "src", "main", "deploy", "apriltags", "surveyed.json")


def _layout_change(body):
    text = body.get("text") or ""
    d = json.loads(text)
    if not isinstance(d.get("tags"), list) or "field" not in d:
        raise ValueError("not an AprilTag layout")
    path = _layout_path()
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    return path, old, text


def _pathplanner_change(_body):
    """PathPlanner's settings.json made to match the code. The fixes come from a fresh check here,
    never from the browser."""
    S.reload_project()
    path = ppcheck.settings_path(S.project)
    old = open(path, encoding="utf-8").read()
    _, new = ppcheck.fixed_text(S.project, ppcheck.check(S.project)["fixes"])
    return path, old, new


def api_ppcheck(_query=None):
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    S.reload_project()
    r = ppcheck.check(S.project)
    r["ok"] = True
    return r


def _wiring_change(body):
    path = wiring.map_path(S.project)
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    return path, old, wiring.map_text(body["map"])


def api_save_preview(body):
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    if body.get("kind") in ("wiring", "layout", "pathplanner"):
        try:
            path, old, new = CHANGES[body["kind"]](body)
        except (ValueError, KeyError, OSError) as e:
            return {"ok": False, "error": f"Not saved: {e}"}
        rel = os.path.relpath(path, S.project.path).replace(os.sep, "/")
        return {"ok": True, "diff": yagslcfg.diff(old, new, rel) if old != new else "", "files": [rel]}
    changes = S.project.preview(_edits_from(body))
    return {"ok": True, "diff": "".join(yagslcfg.diff(o, n, f) for f, (o, n) in changes.items()),
            "files": list(changes)}


def api_save_apply(body):
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    if body.get("kind") in ("wiring", "layout", "pathplanner"):
        try:
            path, old, new = CHANGES[body["kind"]](body)
        except (ValueError, KeyError, OSError) as e:
            return {"ok": False, "error": f"Not saved: {e}"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        S._wiring = None
        if body["kind"] == "pathplanner":
            S.reload_project()
        return {"ok": True, "diff": yagslcfg.diff(old, new, os.path.basename(path))}
    text = S.project.apply(_edits_from(body))
    return {"ok": True, "diff": text}


CHANGES = {"wiring": lambda b: _wiring_change(b), "layout": lambda b: _layout_change(b),
           "pathplanner": lambda b: _pathplanner_change(b)}


def api_runs(_):
    return {"runs": runs.list_runs(100)}


def api_run(name):
    doc = runs.load(name)
    # Re-analyze on every open: the advisor may be newer than the run, and the channels are kept.
    lim = S.limits()
    doc["report"] = advisor.analyze(doc, doc.get("gains"),
                                    current_limit=lim["steer" if doc.get("test") == "steer_step" else "drive"],
                                    **advisor.robot_context(S.project))
    doc["explain"] = explain.explain(doc, doc.get("gains"), lim)
    return doc


DEMOS = {
    "tail": "A CAN cable pulled out partway along the chain",
    "single": "One controller with no power",
    "resets": "A loose power lead: one controller keeps rebooting",
    "busoff": "No terminator at the far end",
}


def _demo_snapshot(m, kind):
    chain = [n for n in m["buses"][0]["chain"] if n not in ("roboRIO", "PDH")]
    rows = [{"name": n, "present": 1, "dropouts": 0, "resets": 0, "brownouts": 0} for n in chain]
    can = [0.35, 0, 0, 0, 0]
    k = max(1, len(rows) // 2)
    if kind == "tail":
        for r in rows[k:]:
            r["present"], r["dropouts"] = 0, 1
        can = [0.2, 0, 3, 96, 0]
    elif kind == "single" and rows:
        rows[k]["present"], rows[k]["dropouts"] = 0, 1
    elif kind == "resets" and rows:
        rows[k]["resets"], rows[k]["brownouts"], rows[k]["dropouts"] = 3, 2, 3
    elif kind == "busoff":
        can = [0.1, 4, 25, 128, 255]
    return {"motors": rows, "can": can}


_LOG_CACHE = {}


def _log_series(path):
    if not path.lower().endswith(".wpilog") or not os.path.isfile(path):
        raise ValueError("not a .wpilog file: " + path)
    key = (path, os.path.getmtime(path))
    if key not in _LOG_CACHE:
        _LOG_CACHE.clear()
        _LOG_CACHE[key] = logsummary.read(path)
    return _LOG_CACHE[key]


def api_logs(query=None):
    """The .wpilog files in a folder, newest first."""
    folder = os.path.expanduser((query or {}).get("folder") or "")
    if not folder or not os.path.isdir(folder):
        return {"ok": False, "error": "Not a folder: " + folder}
    files = []
    for name in os.listdir(folder):
        if name.lower().endswith(".wpilog"):
            full = os.path.join(folder, name)
            files.append({"name": name, "path": full, "size": os.path.getsize(full),
                          "mtime": os.path.getmtime(full)})
    files.sort(key=lambda f: -f["mtime"])
    return {"ok": True, "folder": folder, "files": files[:200]}


def api_logsummary(query=None):
    path = (query or {}).get("file") or ""
    rep = logsummary.summarize(_log_series(path), S.wiring_map())
    rep["ok"] = True
    rep["file"] = path
    return rep


def api_wiring(query=None):
    """The map, every device, the bus lengths and the live diagnosis (or a practice fault, or a
    moment from a match log)."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    m = S.wiring_map()
    q = query or {}
    demo = q.get("demo")
    if q.get("log"):
        snap = logsummary.snapshot_at(_log_series(q["log"]), float(q.get("t", 0)))
        demo = None
    elif demo in DEMOS:
        snap = _demo_snapshot(m, demo)
    elif S.link and S.link.is_connected():
        live = S.link.live()
        snap = {"motors": live.get("motors"), "can": live.get("can"), "pdh": live.get("pdh"),
                "feed_r": S.feed_resistances()}
    else:
        snap = {}
    return {"ok": True, "map": m, "devices": wiring.devices_by_name(S.project, m),
            "lengths": [wiring.bus_length(b) for b in m["buses"]], "snapshot": snap,
            "findings": wiring.diagnose(m, snap), "demos": DEMOS, "demo": demo if demo in DEMOS else None,
            "path": os.path.relpath(wiring.map_path(S.project), S.project.path)}


def _edit_dicts(edits):
    return [{"file": f, "path": list(p), "value": v} for f, p, v in edits]


def api_geometry_tape(body):
    """Module locations from a tape-measured wheelbase and track width."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    try:
        r = geometry.tape_locations(S.project, float(body.get("wheelbase_in")), float(body.get("track_in")))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Type both measurements, in inches."}
    r["edits"] = _edit_dicts(r["edits"])
    r["ok"] = True
    return r


PRACTICE_WHEELS = (0.982, 1.0, 0.998, 1.003)


def api_geometry_wheels(body):
    """Each wheel's real size from a push in coast (a capture run), or practice data."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    cfg = S.project.wheel_d_in()
    names = S.project.module_names()
    if body.get("practice"):
        k = PRACTICE_WHEELS[:len(names)] + (1.0,) * max(0, len(names) - len(PRACTICE_WHEELS))
        angles = [0.0] * len(names)
        if len(angles) > 1:
            angles[1] = 4.0   # one wheel not quite straight, to show the correction
        doc = {"channels": plant.coast_push(tape_m=3.0, real_in=tuple(cfg * x for x in k),
                                            configured_in=cfg, angles_deg=tuple(angles))}
        tape = 3.0
    else:
        try:
            tape = float(body.get("tape_m"))
        except (TypeError, ValueError):
            return {"ok": False, "error": "Type how far the robot moved, in meters."}
        doc = runs.load(body["file"])
        names = (doc.get("robot") or {}).get("modules") or names
    r = geometry.wheel_sizes(doc, tape, cfg, names)
    r["edits"] = _edit_dicts(r.get("edits", []))
    r["ok"] = True
    r["practice"] = bool(body.get("practice"))
    return r


def api_gyro(body):
    """Drift and tilt from a still capture, or scale from full turns (or practice data)."""
    kind = body.get("kind", "still")
    if body.get("practice"):
        ch = plant.gyro_capture(kind, seconds=60 if kind == "still" else 40, drift_dpm=0.3, scale=0.985,
                                tilt=(1.2, -0.8))
        doc = {"channels": ch}
    else:
        doc = runs.load(body["file"])
    try:
        turns = int(body.get("turns", 5))
    except (TypeError, ValueError):
        return {"ok": False, "error": "How many full turns?"}
    r = geometry.gyro_still(doc) if kind == "still" else geometry.gyro_turns(doc, turns)
    r.update(ok=True, practice=bool(body.get("practice")), kind=kind)
    return r


def api_geometry_spin(query=None):
    """The newest floor spin, judged against the module positions and (optionally) wheel sizes."""
    ratio = float((query or {}).get("configured_over_real") or 1.0)
    robot = S.project.name.lower() if S.project else ""
    spins = [r for r in runs.list_runs(300) if r["test"] == "spin" and r["env"] == "FIELD"
             and not r["practice"] and r["outcome"] == "DONE"]
    mine = [r for r in spins if (r.get("robot") or "").lower() == robot] or spins
    if not mine:
        out = geometry.spin_check({})
        out.update(ok=True, run=None)
        return out
    doc = runs.load(mine[0]["file"])
    out = geometry.spin_check(advisor.spin_report(doc).get("measured"), ratio)
    out.update(ok=True, run=mine[0]["file"], saved=mine[0].get("saved"))
    return out


def _camera_mounts():
    return dict((S.project.data.get("swervetune.json") or {}).get("cameras") or {}) if S.project else {}


def api_camcal_sample(body):
    """About two seconds of one camera's sightings of one tag, for one spot."""
    if not S.link or not S.link.is_connected():
        return {"ok": False, "error": "Connect to the robot first (or try Practice)."}
    cam, tag = body.get("camera", ""), int(body.get("tag_id", -1))
    seconds = min(5.0, max(0.5, float(body.get("seconds", 2.0))))
    got, seen_cams, seen_tags, stamps = [], set(), set(), set()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for s in S.link.sightings():
            seen_cams.add(s["camera"])
            seen_tags.add(s["tag"])
            key = (s["camera"], s["tag"], s["t"])
            if s["camera"] == cam and s["tag"] == tag and key not in stamps:
                stamps.add(key)
                got.append(s)
        time.sleep(0.04)
    out = {"ok": True, "samples": got, "count": len(got), "cameras_seen": sorted(seen_cams),
           "tags_seen": sorted(seen_tags)}
    if not got:
        out["hint"] = (f"Camera {cam!r} reported no tag {tag}. Seen: cameras {sorted(seen_cams) or 'none'}, "
                       f"tags {sorted(seen_tags) or 'none'}. Check the name matches PhotonVision's page, the "
                       "pipeline is in AprilTag 3D mode, and robot code passes sightings (PhotonVisionSource).")
    return out


SURVEY = {"running": False, "sightings": [], "keys": set(), "thread": None}


def api_survey_start(_):
    """Starts recording every camera's tags until stopped."""
    if not S.link or not S.link.is_connected():
        return {"ok": False, "error": "Connect to the robot first (or try Practice)."}
    if SURVEY["running"]:
        return {"ok": True}
    SURVEY.update(running=True, sightings=[], keys=set())

    def work():
        while SURVEY["running"]:
            try:
                for s in S.link.sightings():
                    key = (s["camera"], s["tag"], s["t"])
                    if key not in SURVEY["keys"]:
                        SURVEY["keys"].add(key)
                        SURVEY["sightings"].append(s)
            except Exception:  # noqa: BLE001 - a dropped connection just pauses the recording
                pass
            time.sleep(0.02)

    SURVEY["thread"] = threading.Thread(target=work, name="swervetune-survey", daemon=True)
    SURVEY["thread"].start()
    return {"ok": True}


def api_survey_stop(_):
    SURVEY["running"] = False
    return api_survey_state()


def api_survey_state(_query=None):
    s = SURVEY["sightings"]
    frames = {}
    for x in s:
        frames.setdefault((x["camera"], x["t"]), set()).add(x["tag"])
    return {"ok": True, "running": SURVEY["running"], "sightings": len(s),
            "views": sum(1 for v in frames.values() if len(v) >= 2), "tags": sorted({x["tag"] for x in s})}


PRACTICE_SURVEY = {5: (0.04, 0.0, 0.0, 0, 0, 0), 26: (0.0, 0.0, 0.0, 0, 0, 3.0),
                   21: (0.0, -0.025, 0.01, 0, 0, 0), 9: (0.45, 0.0, 0.0, 0, 0, 0)}


def api_survey_solve(body):
    """Works out where every recorded tag really is (or a practice field's)."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    variant = body.get("variant") or None
    if body.get("practice"):
        sightings = plant.field_frames(moved=PRACTICE_SURVEY)
    else:
        sightings = list(SURVEY["sightings"])
    r = fieldsurvey.survey(sightings, variant)
    r["practice"] = bool(body.get("practice"))
    if r["practice"]:
        r["truth"] = {str(k): v for k, v in PRACTICE_SURVEY.items()}
    if r.get("variant"):
        lay = fieldsurvey.official(r["variant"])
        r["official"] = {str(i): {"x": t[1][0], "y": t[1][1], "yaw": camcal.mat_to_euler(t[0])[2]}
                         for i, t in lay["tags"].items()}
        r["field"] = lay["field"]
    r.pop("poses", None)
    if S.project:
        r["path"] = os.path.relpath(_layout_path(), S.project.path).replace(os.sep, "/")
    return r


PRACTICE_MOUNT = (0.28, -0.12, 0.52, 0.0, -18.0, 8.0)
PRACTICE_SPOTS = [{"side": "front", "distance_m": 2.0, "lateral_m": 0.0, "height_m": 0.6, "tag_id": 7},
                  {"side": "front", "distance_m": 1.5, "lateral_m": 0.5, "height_m": 0.6, "tag_id": 7},
                  {"side": "front", "distance_m": 2.6, "lateral_m": -0.4, "height_m": 0.6, "tag_id": 7}]


def api_camcal_solve(body):
    """The camera mount from every spot taken (or from practice spots)."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    cam = body.get("camera") or "front"
    if body.get("practice"):
        placements = plant.camera_sightings(PRACTICE_MOUNT, PRACTICE_SPOTS)
    else:
        placements = body.get("placements") or []
    r = camcal.solve(cam, placements, _camera_mounts().get(cam))
    r["ok"] = True
    r["practice"] = bool(body.get("practice"))
    if r["practice"]:
        r["placements"] = [{k: v for k, v in p.items() if k != "samples"} | {"count": len(p["samples"])}
                           for p in placements]
        r["true_mount"] = dict(zip(("x", "y", "z", "roll", "pitch", "yaw"), PRACTICE_MOUNT))
        r["edit"] = None
    if r.get("edit"):
        f, p, v = r["edit"]
        r["edits"] = [{"file": f, "path": list(p), "value": v}]
    r["current"] = _camera_mounts().get(cam)
    return r


PRACTICE_PORTS = (0, 1, 2, 3, 16, 17, 18, 19)


def _pdh_plot(ch, rep):
    """What the Wiring tab graphs: the channels that rose, and when each motor was pulsed."""
    ports = sorted({r["port"] if r["port"] is not None else r.get("port_guess") for r in rep["rows"]} - {None})
    t, slot, on = ch.get("t") or [], ch.get("slot") or [], ch.get("on") or []
    spans, i, n = [], 0, min(len(t), len(slot), len(on))
    while i < n:
        if not on[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and on[j + 1] and slot[j + 1] == slot[i]:
            j += 1
        k = int(slot[i])
        row = rep["rows"][k] if k < len(rep["rows"]) else {}
        spans.append({"x0": t[i], "x1": t[j], "name": row.get("name", f"pulse {k}"),
                      "port": row.get("port"), "rise_a": row.get("rise_a")})
        i = j + 1
    return {"t": t, "channels": {str(p): ch.get(f"pdh{p}") or [] for p in ports}, "pulses": spans}


def api_wiring_wiggle(query=None):
    """Practice for the wiggle test: a made-up robot's live snapshot, with one loose CAN plug and
    one loose power lead that act up only while their step is being wiggled."""
    import random

    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    m = S.wiring_map()
    chain = m["buses"][0]["chain"]
    devices = chain[1:-1]
    q = query or {}
    st = S.__dict__.get("_wiggle")
    if q.get("reset") or not st or st["chain"] != chain:
        k = min(4, len(chain) - 2)
        st = S._wiggle = {"chain": chain, "bad_seg": [chain[k], chain[k + 1]],
                          "bad_power": devices[len(devices) // 3] if devices else None,
                          "rows": {n: {"name": n, "present": 1, "dropouts": 0, "resets": 0, "brownouts": 0}
                                   for n in devices},
                          "can": [0.35, 0, 0, 0, 0, 0], "rng": random.Random(7)}
    rng, step = st["rng"], q.get("step", "")
    if step == "can:" + "|".join(st["bad_seg"]):
        st["can"][5] += rng.randint(2, 20)
        if rng.random() < 0.25:
            for n in chain[chain.index(st["bad_seg"][1]):-1]:
                st["rows"][n]["dropouts"] += 1
    elif st["bad_power"] and step == "power:" + st["bad_power"]:
        r = st["rows"][st["bad_power"]]
        if rng.random() < 0.3:
            r["resets"] += 1
        elif rng.random() < 0.3:
            r["brownouts"] += 1
    return {"ok": True, "practice": True,
            "snapshot": {"motors": [dict(r) for r in st["rows"].values()], "can": list(st["can"])}}


def api_wiring_pdhfind(query=None):
    """PDH ports found from a pdh_map run, a practice log, or (read-only) practice data."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    q = query or {}
    m = S.wiring_map()
    if q.get("practice"):
        names = [f"{n} {part}" for n in S.project.module_names() for part in ("drive", "steer")]
        ports = list(PRACTICE_PORTS[:len(names)]) + [None] * max(0, len(names) - len(PRACTICE_PORTS))
        if len(ports) > 3:
            ports[3] = None   # one motor fed from somewhere else, to show what that looks like
        ch, notes, meta = plant.pdh_pulses(names, ports, background={20: 2.5})
        rep = pdhports.from_pulses({"channels": ch, "notes": notes, "meta": meta}, m)
        rep["practice"] = True
        rep["plot"] = _pdh_plot(ch, rep)
    elif q.get("run"):
        doc = runs.load(q["run"])
        rep = pdhports.from_pulses(doc, m)
        rep["plot"] = _pdh_plot(doc.get("channels") or {}, rep)
    elif q.get("log"):
        rep = pdhports.from_log(_log_series(q["log"]), m)
    else:
        return {"ok": False, "error": "Say where to look: a run, a log, or practice."}
    rep["ok"] = True
    rep["mapped"] = m.get("pdhPorts") or {}
    return rep


def api_wiring_termination(body):
    try:
        ohms = float(body.get("ohms"))
    except (TypeError, ValueError):
        ohms = None
    return wiring.termination_verdict(ohms)


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
    elif loop == "spin_ff":
        ch, meta = plant.spin_ff(moi=6.0, mass=55.0)
        doc = {"test": "spin_ff", "module": "ALL", "meta": meta, "channels": ch, "practice": True,
               "env": "FIELD", "robot": {"name": "practice pod", "modules": rehearse.MODULES}, "outcome": "DONE"}
        hist = [{"modules": {m: {"ok": True, "kA": 0.45, "kV": 2.9} for m in rehearse.MODULES}}]
        rep = advisor.analyze(doc, g, history=hist, mass_kg=55.0, mass_source="practice", moi_estimate=6.6)
        doc.update(report=rep, gains=g)
        return doc
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
       "/api/progress": api_progress_get, "/api/wiring": api_wiring, "/api/logs": api_logs,
       "/api/logsummary": api_logsummary, "/api/wiring/pdhfind": api_wiring_pdhfind,
       "/api/wiring/wiggle": api_wiring_wiggle, "/api/geometry/spin": api_geometry_spin,
       "/api/survey/state": api_survey_state, "/api/ppcheck": api_ppcheck}
POST = {"/api/project": api_set_project, "/api/connect": api_connect,
        "/api/disconnect": api_disconnect, "/api/env": api_env, "/api/test": api_test,
        "/api/abort": api_abort, "/api/stop": api_stop, "/api/deadman": api_deadman,
        "/api/gains": api_gains, "/api/save/preview": api_save_preview,
        "/api/save/apply": api_save_apply, "/api/analyze": api_analyze,
        "/api/offsets": api_offsets, "/api/handcheck": api_handcheck,
        "/api/practice": api_practice, "/api/progress": api_progress_put, "/api/sim": api_sim,
        "/api/motors/override": api_motor_override, "/api/predict": api_predict,
        "/api/export": api_export, "/api/wiring/termination": api_wiring_termination,
        "/api/geometry/tape": api_geometry_tape, "/api/geometry/wheels": api_geometry_wheels,
        "/api/camcal/sample": api_camcal_sample, "/api/camcal/solve": api_camcal_solve,
        "/api/survey/start": api_survey_start, "/api/survey/stop": api_survey_stop,
        "/api/survey/solve": api_survey_solve, "/api/gyro": api_gyro}


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
                return self._send(200, GET[path](dict(parse_qsl(urlparse(self.path).query))))
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
