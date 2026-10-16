"""The GUI's server: a small local web server between the browser and the robot.

Started by ``py -3.12 tools/slothtune gui``. It listens on 127.0.0.1 only, serves the page in
``web/``, and answers the page's JSON requests by calling the same modules the command line uses.
Nothing here is reachable from another computer, and it needs no internet - it works in a pit.

Two safety details:

* The robot's heartbeat is gated on the **browser**: the page polls ``/api/live`` ten times a
  second, and if it stops (tab closed, laptop asleep) the heartbeat stops and any test on the
  robot ends within half a second.
* The GUI deadman (the page's Hold to run button, held by mouse or touch; never a key, since SPACE
  is the Driver Station's E-STOP) must be refreshed every 100 ms by the page while it is held. A
  dropped refresh releases it.
"""

from __future__ import annotations

import hmac
import json
import math
import mimetypes
import os
import secrets
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlparse

from . import setup as setup_plans
from . import (advisor, akit, battery, camcal, contract as C, controllers, diagnose, explain, fieldsurvey, geometry,
               designcheck, designlinks, logsummary, monitor, motorinv, netcheck, pdhports, plant, ppcheck, predict, progress,
               rehearse, revspecs, robotlog, runs, systems, wiring, yagslcfg)

# A fresh secret each run: only the page this run served can change anything (see Handler).
TOKEN = secrets.token_urlsafe(18)
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


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
        self.netcheck_last = None   # the last network check, for Troubleshoot's evidence
        self.last_poll = 0.0
        self.deadman_until = 0.0
        self.test_thread = None
        self.test_state = {"running": False}
        self.last_run = None
        self.autotune = None        # the auto-tuner, while it runs and after (its result, to save)
        self.sys_autotune = None    # a mechanism's auto-tuner (the Systems tab), the same way
        self.connect_error = ""
        # What the robot keeps reporting: its console (a real roboRIO) and its alerts, counted.
        self.robotlog = robotlog.Tally()
        self.console = None
        self.alerts_at = 0.0

    # ------------------------------------------------------------------ browser presence
    def browser_alive(self):
        alive = time.monotonic() - self.last_poll < 0.5
        if self.link is not None:
            self.link.set_gui_deadman(alive and time.monotonic() < self.deadman_until)
        return alive

    # ------------------------------------------------------------------ project
    def set_project(self, name):
        for d in yagslcfg.find_projects(runs.ROBOTS):
            if os.path.basename(d) == name:
                self.project = yagslcfg.Project(d)
                lim = self.project.phys.get("currentLimit", {})
                self.monitor = monitor.Monitor(float(lim.get("drive", 40)))
                return True
        return False

    def reload_project(self):
        """Re-reads the robot's files (a save may have changed them). The live monitor keeps what it
        has seen: rebuilding it on every card refresh cleared its timers and the drive-ratio check."""
        if self.project:
            keep = self.monitor
            self.set_project(self.project.name)
            if keep is not None:
                keep.limit = float(self.project.phys.get("currentLimit", {}).get("drive", 40))
                self.monitor = keep

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
        lk = L.RobotLink(hosts, client_name="slothtune-gui")
        if not lk.wait_connected(6.0):
            lk.close()
            self.connect_error = ("No robot answered at " + ", ".join(hosts) + ". Is robot code "
                                  "running? Is the laptop on the robot's network?")
            return False
        if not lk.has_harness():
            lk.close()
            self.connect_error = "Connected, but this robot code does not have SlothTune installed."
            return False
        proto = lk.get("int", C.PROTOCOL)
        if proto != C.PROTOCOL_VERSION:
            lk.close()
            self.connect_error = (f"Robot speaks protocol {proto}, this tool {C.PROTOCOL_VERSION}. "
                                  "Deploy the code from this branch.")
            return False
        lk.set_gui_deadman(False)  # this client owns the deadman topic
        lk.start_heartbeat(gate=self.browser_alive)
        self.link, self.target, self.connect_error = lk, target, ""
        name = lk.robot_info().get("name")
        if name and (not self.project or self.project.name != name):
            self.set_project(name)
        return True

    def disconnect(self):
        if self.console:
            self.console.stop()
            self.console = None
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
        if self.autotune and self.autotune.state in ("running", "paused"):
            return False, "The auto-tuner is running: stop it first."

        def work():
            try:
                self.run_test_sync(test, module, args)
            except Exception as e:  # noqa: BLE001 - the GUI must hear about any failure
                traceback.print_exc()
                self.test_state.update(running=False, state="ERROR", message=str(e))

        self.test_state = {"running": True, "test": test, "module": module, "state": "SENDING",
                           "message": "Sending to the robot...", "progress": 0.0, "args": dict(args or {})}
        self.test_thread = threading.Thread(target=work, name="slothtune-test", daemon=True)
        self.test_thread.start()
        return True, "Started."

    def run_test_sync(self, test, module, args):
        """Runs one test to its end, the banner following it, and saves the run like any other:
        ``(result, document, saved run's file name)``; the document is None when it was refused."""
        self.test_state = {"running": True, "test": test, "module": module, "state": "SENDING",
                           "message": "Sending to the robot...", "progress": 0.0, "args": dict(args or {})}
        gains = self.link.gains()
        if test.startswith("system_"):
            # A mechanism's run keeps the mechanism's own gains ("Elevator/kP"): its report's next
            # change, and the auto-tuner, work from them.
            for s in self.link.systems():
                gains.update({f"{s['name']}/{k}": g["value"] for k, g in (s.get("gains") or {}).items()})

        def on_status(st):
            self.test_state.update(state=st["state"], message=st["message"], progress=st["progress"])

        res = self.link.run_test(test, module, args, on_status=on_status)
        doc = res.to_json()
        if not res.accepted:
            self.test_state.update(running=False, state="REFUSED", message=res.message)
            return res, None, None
        lim = self.limits()
        rep = advisor.analyze(doc, gains, current_limit=lim["steer" if test == "steer_step" else "drive"],
                              **advisor.robot_context(self.project))
        path = runs.save(doc, rep, gains)
        self.last_run = os.path.basename(path)
        # A real run of a Guide test ticks (or un-ticks) its step for this robot.
        progress.record_run(self.project.name if self.project else None, doc, rep, self.last_run)
        self.test_state.update(running=False, state=res.outcome, message=res.message, run=self.last_run, progress=1.0)
        return res, doc, self.last_run


S = Session()


# ---------------------------------------------------------------------------- handlers


def api_projects(_):
    names = [os.path.basename(d) for d in yagslcfg.find_projects(runs.ROBOTS)]
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
            "pidf": S.project.pidf, "physical": S.project.phys, "slothtune": S.project.tune,
            "swervedrive": S.project.data["swervedrive.json"]}


def api_connect(body):
    with S.lock:
        ok = S.connect(body.get("target", "robot"), body.get("host"))
    return {"ok": ok, "error": S.connect_error}


def api_netcheck(body=None):
    """The robot and the internet (Claude, over a VPN) at the same time: tools/robot_preflight.ps1."""
    from . import link as L

    from . import station

    team = L.team_from_project(S.project.path) if S.project else None
    robot = None
    if S.link and S.link.is_connected():
        try:
            info = S.link.robot_info()
            robot = {"image": info.get("image"), "wpilib": info.get("wpilib")}
        except Exception:  # noqa: BLE001 - a robot without the newer topics: no versions to compare
            robot = None
    from . import dslog
    try:
        ds_log = dslog.latest_summary()
    except Exception:  # noqa: BLE001 - a log this can't read leaves the rest of the check alone
        ds_log = None
    r = netcheck.run(team or 1745, (body or {}).get("adapter") or None, year=getattr(S.project, "year", None),
                     robot=robot, accepted=station.accepted_images(S.project) if S.project else [], ds_log=ds_log,
                     versions=_version_checks())
    S.netcheck_last = r
    return r


def _version_checks():
    """Each robot's libraries against the newest for its year, and the camera's PhotonVision (from the
    connected robot) against PhotonLib: :mod:`versions`. Examples runs only in the simulator."""
    from . import versions, yagslcfg

    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    projects = [(os.path.basename(p), p, None) for p in yagslcfg.find_projects(repo) if os.path.basename(p) != "Examples"]
    cam = None
    if S.link and S.link.is_connected():
        try:
            cam = S.link.get("str", "/photonvision/version") or None
        except Exception:  # noqa: BLE001 - no camera on this robot
            cam = None
    try:
        return versions.checks(projects, cam)
    except Exception as e:  # noqa: BLE001 - a version check never stops the network check
        return [{"id": "versions-error", "group": versions.GROUP, "level": "info",
                 "title": "Couldn't check the software versions", "why": str(e)[:200]}]


def api_netcheck_save(_body=None):
    """The last network check, saved to send: reports/netcheck-<robot>-<time>.json."""
    from . import link as L

    if not S.netcheck_last or S.netcheck_last.get("error"):
        return {"ok": False, "error": "Check the networks first."}
    team = L.team_from_project(S.project.path) if S.project else None
    path = netcheck.save(S.netcheck_last, S.project.name if S.project else "robot", team)
    # From the repository folder, as docs/NETWORK_CHECK.md gives it.
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return {"ok": True, "path": os.path.relpath(path, repo).replace(os.sep, "/")}


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
    _watch_robot_messages()
    return {"connected": S.link.is_connected(), "live": live, "flags": S.flags,
            "status": S.link.status(), "test": S.test_state, "names": names,
            "locations": S.link.robot_info()["locations"],
            "deadman": S.link.get("bool", C.STATUS_DEADMAN_HELD),
            # A running test's newest rows, for a live graph (the Systems tab's).
            "test_live": S.link.test_live() if S.test_state.get("running") else None,
            "seen_tags": seen_tags(S.link.sightings(), live.get("t")),
            "motor_guard": {k: v for k, v in S.link.motors().items() if k != "motors"}}


SEEN_S = 0.5     # a tag counts as in view while its newest sighting is this fresh


def seen_tags(sightings, now):
    """The tags a camera sees right now. Each camera's newest frame stays published after it loses
    its tags, so a sighting counts only while it is fresh against the robot's clock."""
    out = set()
    for s in sightings:
        t = s.get("t")
        if not (isinstance(now, (int, float)) and math.isfinite(now) and now > 0
                and isinstance(t, (int, float)) and math.isfinite(t) and t > 0) or now - t <= SEEN_S:
            out.add(int(s["tag"]))
    return sorted(out)


def field_view(layout):
    """The field from above for the Live tab, from an AprilTag layout file: its size, and each tag
    where it stands and which way it faces (yaw, degrees counter-clockwise from the red wall's
    direction, +x). Meters, like the file."""
    tags = []
    for t in layout.get("tags") or []:
        tr, q = t["pose"]["translation"], t["pose"]["rotation"]["quaternion"]
        w, x, y, z = (float(q[k]) for k in ("W", "X", "Y", "Z"))
        yaw = math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))
        tags.append({"id": int(t["ID"]), "x": float(tr["x"]), "y": float(tr["y"]), "z": float(tr["z"]),
                     "yaw_deg": round(yaw, 3)})
    field = layout.get("field") or {}
    return {"length": float(field.get("length", 0)), "width": float(field.get("width", 0)), "tags": tags}


def robot_outline(settings):
    """The robot's bumpers as PathPlanner draws them, from its settings.json (robotLength along x,
    robotWidth along y, bumperOffsetX/Y; meters), or None without them."""
    try:
        length, width = float(settings["robotLength"]), float(settings["robotWidth"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (0.2 < length < 2.5 and 0.2 < width < 2.5):
        return None
    return {"length": length, "width": width, "offset": [float(settings.get("bumperOffsetX") or 0.0),
                                                          float(settings.get("bumperOffsetY") or 0.0)]}


def official_field_view(project):
    """The official layout the robot loads without a survey: slothtune.json's ``vision.field``
    variant (welded unless it says andymark), as :func:`field_view` draws it; None without one."""
    tune = (project.data.get("slothtune.json") or {}) if project else {}
    variant = str((tune.get("vision") or {}).get("field") or "welded").lower()
    variant = variant if variant in ("welded", "andymark") else "welded"
    try:
        with open(os.path.join(fieldsurvey.FIELDS, f"2026-rebuilt-{variant}.json"), encoding="utf-8") as fh:
            return dict(field_view(json.load(fh)), variant=variant)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def api_field(_query=None):
    """The field the Live tab draws the robot on: this field's surveyed tags (New field's layout),
    else the official layout the robot loads without one (``surveyed: False, official: True``: the
    real field's tags may sit a little off it); and the robot's bumpers from PathPlanner."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    robot = None
    try:
        with open(ppcheck.settings_path(S.project), encoding="utf-8") as fh:
            robot = robot_outline(json.load(fh))
    except (OSError, ValueError):
        pass
    path = _layout_path()
    if not os.path.exists(path):
        off = official_field_view(S.project)
        return {"ok": True, "surveyed": False, "robot": robot, **({"official": True, **off} if off else {})}
    try:
        with open(path, encoding="utf-8") as fh:
            view = field_view(json.load(fh))
    except (OSError, ValueError, KeyError, TypeError) as e:
        return {"ok": True, "surveyed": False, "robot": robot, "error": f"Can't read {os.path.basename(path)}: {e}"}
    return {"ok": True, "surveyed": True, "file": os.path.relpath(path, S.project.path).replace(os.sep, "/"),
            "saved": os.path.getmtime(path), "robot": robot, **view}


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
    if mode == "FIELD" and not body.get("bumpers"):
        return {"ok": False, "error": "Put the bumpers on before the robot goes on the floor."}
    S.link.set_environment(mode, body.get("apriltags"), body.get("space_forward"),
                           body.get("space_side"), body.get("speed_cap"))
    time.sleep(0.25)
    return {"ok": True, "environment": S.link.environment()}


def api_test(body):
    ok, msg = S.start_test(body.get("test"), body.get("module", "ALL"), body.get("args") or {})
    return {"ok": ok, "message": msg}


def api_gyro_command(body):
    """The gyro's own commands (a Canandgyro's): calibrate with the robot disabled, blink its light so
    a person can find it, or clear its sticky faults."""
    action = (body or {}).get("action")
    if action not in ("calibrate", "identify", "identify_stop", "clear_faults"):
        return {"ok": False, "error": "Unknown gyro action."}
    if not (S.link and S.link.is_connected()):
        return {"ok": False, "error": "Connect to the robot first."}
    ok, msg = S.link.gyro_command(action, (body or {}).get("seconds"))
    return {"ok": ok, "message": msg, "error": None if ok else msg}


def api_abort(_):
    if S.autotune:
        S.autotune.stop("Stopped by ABORT.")
    if S.link:
        S.link.abort()
    return {"ok": True}


# ---------------------------------------------------------------------------- the auto-tuner


def api_autotune_start(body):
    """Starts the auto-tuner on every pod's steering or drive gains: on the robot (a person holds the
    deadman for every round) or on the practice pods."""
    from . import autotune

    body = body or {}
    loop = body.get("loop")
    if loop not in autotune.TESTS:
        return {"ok": False, "error": "Pick steering or drive."}
    if S.autotune and S.autotune.state in ("running", "paused"):
        return {"ok": False, "error": "The auto-tuner is already running."}
    if S.sys_autotune and S.sys_autotune.state in ("running", "paused"):
        return {"ok": False, "error": "A mechanism's auto-tune is running: stop it first."}
    if body.get("target") == "practice":
        gains = dict(body.get("gains") or {})
        runner = autotune.PracticeRunner(gains, surface="floor" if body.get("surface") == "floor" else "blocks")
    else:
        if not (S.link and S.link.is_connected()):
            return {"ok": False, "error": "Connect to the robot first."}
        if S.test_state.get("running"):
            return {"ok": False, "error": "A test is running: let it finish first."}
        # Where the robot is (blocks or floor) is the robot's own check: an unset place refuses every test.
        runner = autotune.RobotRunner(S)
        if not runner.modules():
            return {"ok": False, "error": "The robot didn't say what its pods are called."}
    S.autotune = autotune.AutoTune(runner, loop, max_rounds=int(body.get("rounds") or autotune.MAX_ROUNDS))
    S.autotune.target = "practice" if body.get("target") == "practice" else "robot"
    S.autotune.start()
    return {"ok": True, **S.autotune.to_json()}


def id_args(name, args=None):
    """The measuring run's arguments for a registered mechanism: its number, its top test speed (the
    step test's), and a guess at the volts that hold it from its physics (an arm's at its angle now)."""
    reg = next((s for s in (S.link.systems() if S.link and S.link.is_connected() else []) if s["name"] == name), None)
    if not reg:
        return None
    out = {"system": reg["index"]}
    vmax = (args or {}).get("vmax") or reg.get("max_velocity")
    if isinstance(vmax, (int, float)) and vmax == vmax and vmax > 0:
        out["vmax"] = vmax
    entry = systems.settings(S.project).get(name)
    p = systems.plan(entry, reg) if entry else {}
    ff = p.get("feedforward") if p.get("ok") else None
    if not out.get("vmax") and p.get("ok") and p.get("vmax"):
        out["vmax"] = p["vmax"]
    # An elevator's gravity is the same everywhere; an arm's depends on where level is, which isn't known
    # until it is measured (its zero may be straight up): an arm's seesaw starts from 0 V.
    if ff and ff.get("kG") and reg.get("kind") == "ELEVATOR":
        out["hold"] = round(max(-6.0, min(6.0, ff["kG"])), 3)
    return out


def api_sys_autotune_start(body):
    """Starts the auto-tuner on one mechanism (the Systems tab), while a person holds the deadman.
    ``mode`` "model" (decision 75) measures it once (system_id, on blocks) and works every gain out
    from its model, then checks with the step test; otherwise its step test with the tab's arguments,
    a round at a time. ``practice`` runs a made-up elevator or flywheel instead, for trying it out."""
    from . import autotune

    body = body or {}
    name, args = str(body.get("system") or ""), body.get("args") or {}
    if not name or not isinstance(args, dict):
        return {"ok": False, "error": "Pick the mechanism to tune."}
    for t in (S.autotune, S.sys_autotune):
        if t and t.state in ("running", "paused"):
            return {"ok": False, "error": "An auto-tune is already running: stop it first."}
    rounds = int(body.get("rounds") or autotune.MAX_ROUNDS)
    model = body.get("mode") == "model"
    if body.get("practice"):
        kind = "FLYWHEEL" if str(body.get("kind") or "").upper() in ("FLYWHEEL", "ROLLER") else "ELEVATOR"
        runner = autotune.PracticeSystemRunner(name, kind, {k: float(v) for k, v in (body.get("gains") or {}).items()} or None,
                                               spark=model, control=body.get("control") or None)
    else:
        if not (S.link and S.link.is_connected()):
            return {"ok": False, "error": "Connect to the robot first."}
        if S.test_state.get("running"):
            return {"ok": False, "error": "A test is running: let it finish first."}
        if not any(s["name"] == name for s in S.link.systems()):
            return {"ok": False, "error": f"The robot has no mechanism called {name}."}
        ida = dict(id_args(name, args) or {}, **(body.get("id_args") or {}))
        if model and not ida.get("vmax"):
            return {"ok": False, "error": f"Give {name} a top speed for its measuring run (its physics or maxVelocity)."}
        runner = autotune.RobotSystemRunner(S, name, args, id_args=ida)
        if not runner.gains():
            return {"ok": False, "error": f"{name} registers no gains for the tuner to change."}
    S.sys_autotune = (autotune.ModelTune(runner, name, max_checks=int(body.get("checks") or autotune.ModelTune.MAX_CHECKS))
                      if model else autotune.SystemTune(runner, name, max_rounds=rounds))
    S.sys_autotune.target = "practice" if body.get("practice") else "robot"
    S.sys_autotune.start()
    return {"ok": True, **S.sys_autotune.to_json()}


def api_sys_autotune(_):
    t = S.sys_autotune
    return {"ok": True, "state": "none"} if not t else {"ok": True, "target": getattr(t, "target", "robot"), **t.to_json()}


def api_sys_autotune_continue(_):
    if not S.sys_autotune or S.sys_autotune.state != "paused":
        return {"ok": False, "error": "The auto-tuner isn't paused."}
    S.sys_autotune.resume()
    return {"ok": True}


def api_sys_autotune_stop(_):
    if S.sys_autotune:
        S.sys_autotune.stop("Stopped.")
    return {"ok": True}


def api_autotune(_):
    if not S.autotune:
        return {"ok": True, "state": "none"}
    return {"ok": True, "target": getattr(S.autotune, "target", "robot"), **S.autotune.to_json()}


def api_autotune_continue(_):
    if not S.autotune or S.autotune.state != "paused":
        return {"ok": False, "error": "The auto-tuner isn't paused."}
    S.autotune.resume()
    return {"ok": True}


def api_autotune_stop(_):
    if S.autotune:
        S.autotune.stop("Stopped.")
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
    status, gains = S.link.set_gains(values, reason=str(body.get("reason") or "from the GUI")[:200])
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
        only = body.get("module")
        return [(f"modules/{n}.json", ("absoluteEncoderOffset",), r["new"]) for n, r in res.items()
                if not only or n == only]
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


def api_motor_inventory(_query=None):
    """Every controller the code creates: as coded, as the robot reports, and the drive motors as
    the latest real drive_ff measured them."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    S.reload_project()
    live = S.link.motors()["motors"] if S.link and S.link.is_connected() else []
    measured, run = _measured_motor()
    out = motorinv.table(S.project, live, measured)
    out.update(ok=True, connected=bool(live), measured_run=run)
    return out


def _measured_motor():
    """The drive motor as this robot's latest real drive_ff measured it: (identity, run file)."""
    robot = S.project.name.lower()
    for r in runs.list_runs(300):
        if (r["test"] == "drive_ff" and not r["practice"] and r["env"] in ("FIELD", "BLOCKS")
                and (r.get("robot") or "").lower() == robot):
            doc = runs.load(r["file"])
            rep = advisor.analyze(doc, doc.get("gains"), **advisor.robot_context(S.project))
            return rep.get("motor"), r["file"]
    return None, None


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


def _design_change(body):
    """The robot's design file, as the page edited, drafted or imported it."""
    from . import design as D
    d = body.get("design")
    if not isinstance(d, dict) or not isinstance(d.get("motors"), list):
        raise ValueError("not a design file (it needs a motors list)")
    path = D.path(S.project)
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    return path, old, D.text(d)


def _report_change(body):
    """The bring-up report: written here from the evidence, never from the browser's text."""
    from . import bringup
    ctx = _setup_ctx()
    signed = {k: str(v)[:60] for k, v in (body.get("signed") or {}).items() if k in ("programming", "mechanical", "electrical")}
    path, text = bringup.report(S.project, ctx, signed)
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    return path, old, text


def _bad_save(e):
    return {"ok": False, "error": f"Not saved: {e}"}


def api_save_preview(body):
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    if body.get("kind") in CHANGES:
        try:
            path, old, new = CHANGES[body["kind"]](body)
        except (ValueError, KeyError, OSError) as e:
            return {"ok": False, "error": f"Not saved: {e}"}
        rel = os.path.relpath(path, S.project.path).replace(os.sep, "/")
        return {"ok": True, "diff": yagslcfg.diff(old, new, rel) if old != new else "", "files": [rel]}
    try:
        changes = S.project.preview(_edits_from(body))
    except ValueError as e:
        return _bad_save(e)
    return {"ok": True, "diff": "".join(yagslcfg.diff(o, n, f) for f, (o, n) in changes.items()),
            "files": list(changes)}


def api_save_apply(body):
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    if body.get("kind") in CHANGES:
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
        if body["kind"] == "bringup_report":
            progress.update(S.project.name, {"bu_signoff": {"result": "pass", "when": setup_plans.stamp(),
                                                            "detail": "Report: " + os.path.relpath(path, S.project.path).replace(os.sep, "/")}})
        return {"ok": True, "diff": yagslcfg.diff(old, new, os.path.basename(path))}
    try:
        text = S.project.apply(_edits_from(body))
    except ValueError as e:
        return _bad_save(e)
    return {"ok": True, "diff": text}


CHANGES = {"wiring": lambda b: _wiring_change(b), "layout": lambda b: _layout_change(b),
           "pathplanner": lambda b: _pathplanner_change(b), "design": lambda b: _design_change(b),
           "bringup_report": lambda b: _report_change(b)}


def api_bringup(_query=None):
    """The design file and what it says against itself and the code; the robot's motor order (for
    the motor test's masks); and bring-up's marks."""
    from . import design as D
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    path = D.path(S.project)
    rel = os.path.relpath(path, S.project.path).replace(os.sep, "/")
    try:
        d = D.load(S.project)
    except (OSError, ValueError) as e:
        return {"ok": True, "exists": True, "path": rel, "design": None, "error": f"The design file doesn't read: {e}"}
    order = []
    if S.link and S.link.is_connected():
        try:
            order = [m.get("name") for m in (S.link.motors().get("motors") or [])]
        except Exception:  # noqa: BLE001 - a robot without the motor guard
            order = []
    prog = progress.load(S.project.name)
    marks = {k: v for k, v in prog.items() if k.startswith("bu_")}
    out = {"ok": True, "exists": d is not None, "path": rel, "design": d, "order": order, "marks": marks,
           "colors": D.BUS_COLORS}
    if d is not None:
        out["check"] = D.check(d)
        out["compare"] = D.compare(S.project, d)
    return out


def api_bringup_draft(body):
    """A design file drafted from the code, or imported from a spreadsheet (``text``); not saved."""
    from . import design as D
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    b = body or {}
    ctl = b.get("controller") if b.get("controller") in D.CONTROLLERS else "roborio2"
    if b.get("text"):
        d = D.from_csv(str(b["text"]), robot=S.project.name, controller=ctl)
    else:
        d = D.from_code(S.project)
        d["controller"] = ctl
    return {"ok": True, "design": d, "check": D.check(d)}


def api_runs(_):
    return {"runs": runs.list_runs(100)}


def api_run(name, query=None):
    doc = runs.load(name)
    # One pod's view (Tune drive train, Each pod): its channels and its own gains only.
    if (query or {}).get("pod"):
        doc = advisor.pod_doc(doc, query["pod"])
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


def _design_inventory():
    live = S.link.motors()["motors"] if S.link and S.link.is_connected() else []
    return motorinv.table(S.project, live)


def _design_out(url, mechanism, motors, inv, stats):
    try:
        out = designcheck.evaluate(url, S.project, motors, inv, stats)
    except ValueError as e:
        return {"mechanism": mechanism, "url": url, "motors": motors or [], "error": str(e)}
    out.update(mechanism=mechanism, url=url, motors=motors or [])
    return out


def api_designs(query=None):
    """The designs saved for this robot, each checked; ``log`` adds a match log's measurements."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    S.reload_project()
    log = (query or {}).get("log") or ""
    stats = designcheck.from_log(log) if log else {}
    inv = _design_inventory()
    designs = [_design_out(v.get("url", ""), name, v.get("motors") or [], inv, stats)
               for name, v in designcheck.saved(S.project).items() if v and v.get("url")]
    return {"ok": True, "designs": designs, "log": log, "log_motors": sorted(stats),
            "motors": [{"name": r["name"], "motor": r.get("motor") or ""} for r in inv["rows"]
                       if r.get("key") not in ("drive", "steer")]}


def api_design_read(body):
    """A pasted link: what it says, the motors it is probably for, and its checks."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    b = body or {}
    url, mech = str(b.get("url") or "").strip(), str(b.get("mechanism") or "").strip()
    try:
        d = designlinks.parse(url)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    inv = _design_inventory()
    motors = b.get("motors")
    mech = mech or designcheck.default_name(d)
    if motors is None and d["kind"] not in ("drivetrain", "gearing"):
        motors = designcheck.suggest_motors(d, inv, mech)
    out = _design_out(url, mech, motors, inv, designcheck.from_log(b.get("log")) if b.get("log") else {})
    out["ok"] = "error" not in out
    return out


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
    b = rep.get("battery") or {}
    if b.get("id") and b.get("fit"):
        mtime = os.path.getmtime(path)
        runs.battery_ledger_add(f"{os.path.basename(path)}:{int(mtime)}", time.strftime("%Y%m%d-%H%M%S",
                                time.localtime(mtime)), b["id"], b["fit"], "match log " + os.path.basename(path))
    return rep


_BATTERY_RUNS = {}


def _battery_entries():
    """Every battery measurement: saved runs that knew their battery, then match logs."""
    out = []
    for r in runs.list_runs(400):
        if r["practice"]:
            continue
        key = r["file"]
        if key not in _BATTERY_RUNS:
            try:
                doc = runs.load(key)
            except (OSError, ValueError):
                continue
            b = (doc.get("report") or {}).get("battery") or {}
            _BATTERY_RUNS[key] = (doc.get("saved"), doc.get("battery") or b.get("id"), b.get("fit"),
                                  f"{doc.get('test')} run")
        out.append(_BATTERY_RUNS[key])
    for e in runs.battery_ledger().values():
        out.append((e.get("when"), e.get("id"), e.get("fit"), e.get("source")))
    return out


def _battery_rows(live):
    """Every battery on the list (and any measured since it left), with its latest grade."""
    options = live.get("battery_options") or []
    if not options and S.project:
        options = [str(b) for b in (S.project.data.get("slothtune.json") or {}).get("batteries") or []]
    options = options or [str(i) for i in range(1, 13)]
    hist = battery.history(_battery_entries())
    if battery.BORROWED not in options:
        options = list(options) + [battery.BORROWED]
    rows = []
    for bid in list(options) + [b for b in hist if b not in options]:
        h = hist.get(bid) or []
        last = h[-1] if h else {}
        rows.append({"id": bid, "listed": bid in options, "status": last.get("status"), "mohm": last.get("mohm"),
                     "v_rest": last.get("v_rest"), "when": last.get("when"), "source": last.get("source"),
                     "n": len(h), "trend": [x["mohm"] for x in h[-12:]]})
    return rows, hist


def _grades_stale(rows):
    grades = battery.grades_for_robot(rows)
    saved = (S.project.data.get("slothtune.json") or {}).get("batteryGrades") if S.project else None
    return grades, bool(S.project) and bool(grades) and grades != (saved or {})


def api_battery(_query=None):
    """Which battery is in, the choices, and every battery's measured sag over time."""
    live = S.link.live() if S.link and S.link.is_connected() else {}
    rows, hist = _battery_rows(live)
    current = live.get("battery_id") or ""
    grades, stale = _grades_stale(rows)
    return {"ok": True, "connected": bool(live), "id": current,
            # What the robot shows on Elastic comes from slothtune.json: offer to send newer grades.
            "robot_grades": grades, "robot_grades_stale": stale,
            "rest_v": live.get("battery_rest"), "batteries": rows, "robot_path": battery.robot_path_suspect(hist),
            "next": battery.suggest_next(rows, current),
            "good_max_mohm": battery.GOOD_MAX_OHM * 1000, "practice_max_mohm": battery.PRACTICE_MAX_OHM * 1000,
            "datasheet": battery.ES17_12}


# ---------------------------------------------------------------- where to start, what next

def _setup_ctx():
    if S.project:
        S.reload_project()
    try:
        stale = _grades_stale(_battery_rows({})[0])[1]
    except Exception:  # noqa: BLE001 - no battery data is not a reason to fail the plan
        stale = False
    try:
        measured = _measured_motor()[0] if S.project else None
    except Exception:  # noqa: BLE001 - a run that won't analyze leaves the inventory as coded
        measured = None
    return setup_plans.gather(S.project, link=S.link, battery_grades_stale=stale, measured=measured)


def api_setup(query=None):
    """A tool's checklist: ``?tab=calibrate`` (config, motors, wiring, controllers), or every tool."""
    tab = (query or {}).get("tab") or ""
    ctx = _setup_ctx()
    if tab:
        if tab not in setup_plans.TOOLS:
            return {"ok": False, "error": f"No checklist for {tab}."}
        return dict(setup_plans.with_order(tab, ctx), ok=True, tab=tab)
    plans = {t: fn(ctx) for t, fn in setup_plans.TOOLS.items()}
    return {"ok": True, "tools": {t: setup_plans.with_order(t, ctx, plans) for t in plans}}


def _parts():
    return (progress.load(S.project.name) if S.project else {}).get("parts") or {}


def _save_parts(parts):
    progress.update(S.project.name, {"parts": parts})


def api_parts(_query=None):
    """What can be redone on its own, the choices for each, and the ones already started."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    tune = S.project.data.get("slothtune.json") or {}
    picks = {"module": S.project.module_names(),
             "motor": [d["name"] for d in wiring.discover(S.project) if d["kind"] == "controller"],
             "camera": [str(c) for c in (tune.get("vision") or {}).get("cameras") or []] or ["front"],
             # The mechanisms the robot registers, else the ones its code registers.
             "system": [s["name"] for s in (S.link.systems() if S.link and S.link.is_connected() else [])]
             or sorted(systems.in_code(S.project))}
    kinds = [{"kind": k, "title": v["title"], "when": v["when"], "choices": picks.get(v["pick"]) if v["pick"] else None}
             for k, v in setup_plans.PARTS.items()]
    active = []
    ctx = None
    for key, p in sorted(_parts().items(), key=lambda kv: kv[1].get("started", ""), reverse=True):
        kind, _, which = key.partition(":")
        if kind not in setup_plans.PARTS:
            continue
        ctx = ctx or _setup_ctx()
        plan = setup_plans.part_plan(kind, which, ctx, p.get("started", ""))
        active.append({"kind": kind, "which": which, "started": p.get("started"), "done": plan["done"], "of": plan["of"],
                       "title": plan["title"]})
    return {"ok": True, "kinds": kinds, "active": active}


def api_part_plan(query=None):
    q = query or {}
    kind, which = q.get("kind") or "", q.get("which") or ""
    if kind not in setup_plans.PARTS:
        return {"ok": False, "error": "Which part?"}
    p = _parts().get(setup_plans.part_key(kind, which))
    if not p:
        # Not started: the checklist as it would be, with nothing counted (a start far in the future).
        plan = setup_plans.part_plan(kind, which, _setup_ctx(), "99999999-999999")
        return dict(plan, ok=True, kind=kind, which=which, started=None, preview=True)
    plan = setup_plans.part_plan(kind, which, _setup_ctx(), p["started"])
    return dict(plan, ok=True, kind=kind, which=which, started=p["started"], marks=p.get("marks") or {})


def api_part_start(body):
    b = body or {}
    kind, which = b.get("kind") or "", str(b.get("which") or "")
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    if kind not in setup_plans.PARTS:
        return {"ok": False, "error": "Which part?"}
    if setup_plans.PARTS[kind]["pick"] and not which:
        return {"ok": False, "error": f"Which {setup_plans.PARTS[kind]['pick']}?"}
    # Starting again starts over: only what is done from now on counts.
    key = setup_plans.part_key(kind, which)
    progress.change(S.project.name, lambda p: p.setdefault("parts", {}).__setitem__(
        key, {"started": setup_plans.stamp(), "marks": {}}))
    return api_part_plan({"kind": kind, "which": which})


def _watch_robot_messages():
    """Counts what the robot reports while the page is open: its alerts twice a second, and its
    console, read in the background from a real roboRIO (the simulator has none to read)."""
    now = time.monotonic()
    if not (S.link and S.link.is_connected()) or now - S.alerts_at < 0.5:
        return
    S.alerts_at = now
    try:
        S.robotlog.alerts(S.link.alerts())
    except Exception:  # noqa: BLE001 - the counts are a convenience; never break the live view
        pass
    if _in_sim():
        return
    host = S.link.connected_to()
    if host and (S.console is None or S.console.host != host):
        if S.console:
            S.console.stop()
        S.console = robotlog.ConsoleWatch(host, S.robotlog)


def api_robotlog(_query=None):
    """Each distinct error and warning the robot has reported since the counts were cleared, with
    how often and how recently."""
    connected = bool(S.link and S.link.is_connected())
    console = ("the simulator has no console to read" if connected and _in_sim()
               else S.console.state if S.console else "not connected")
    return {"ok": True, "connected": connected, "console": console,
            "since_s": round(time.time() - S.robotlog.since), "recent_s": robotlog.RECENT_S,
            "messages": S.robotlog.summary()}


def api_systems(_query=None):
    """The Systems tab: the robot's subsystems and their motors and sensors, and each mechanism the
    code registers with its live state, its settings, its physics and its safe test."""
    if not S.project:
        return {"ok": False, "error": "Pick a robot project first."}
    connected = bool(S.link and S.link.is_connected())
    reg = S.link.systems() if connected else []
    cfg = systems.settings(S.project)
    out = []
    for r in reg:
        entry = cfg.get(r["name"]) or {}
        try:
            phys, err = systems.physics(entry, r.get("kind")), None
        except ValueError as e:
            phys, err = None, str(e)
        from . import mechanics
        out.append(dict(r, settings=entry, physics=phys, physics_error=err, plan=systems.plan(entry, r),
                        feedforward=mechanics.feedforward(phys) if phys else None,
                        scale=systems.scale(entry, r.get("units"), phys)))
    # Game pieces by current: each sensor and hold with the mechanism it belongs to (by name, or
    # by its motor).
    pieces = S.link.pieces() if connected else []
    holds = S.link.holds() if connected else []
    for p in pieces:
        if not p["system"]:
            p["system"] = next((r["name"] for r in reg if p["motor"] in r.get("motors", [])), "")
    for h in holds:
        h["system"] = next((r["name"] for r in reg if h["motor"] in r.get("motors", [])), "")
    return {"ok": True, "connected": connected, "groups": systems.groups(S.project, wiring._design(S.project), reg),
            "systems": out, "motors": mechanics_motors(), "pieces": pieces, "holds": holds}


def mechanics_motors():
    from . import mechanics
    return sorted(mechanics.MOTORS)


def api_systems_physics(body):
    """A mechanism's physics and safe test from a ReCalc or AMBcalc link or typed numbers, before saving."""
    b = body or {}
    entry = {k: v for k, v in (b.get("settings") or {}).items() if v not in (None, "")}
    registered = next((r for r in (S.link.systems() if S.link and S.link.is_connected() else [])
                       if r["name"] == b.get("name")), {"name": b.get("name"), "kind": b.get("kind", ""),
                                                         "units": b.get("units", "")})
    try:
        phys = systems.physics(entry, registered.get("kind"))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    from . import mechanics
    return {"ok": True, "physics": phys, "feedforward": mechanics.feedforward(phys) if phys else None,
            "plan": systems.plan(entry, registered), "scale": systems.scale(entry, registered.get("units"), phys)}


def api_motors_clear_sticky(_body):
    """Clears every sticky fault on the robot (the Wiring tab's button)."""
    if not (S.link and S.link.is_connected()):
        return {"ok": False, "error": "Connect to the robot first."}
    msg = S.link.clear_sticky()
    return {"ok": not msg.startswith(("No answer", "Ignored")), "message": msg}


def api_systems_gains(body):
    if not (S.link and S.link.is_connected()):
        return {"ok": False, "error": "Connect to the robot first."}
    values = {k: float(v) for k, v in ((body or {}).get("values") or {}).items()}
    status = S.link.set_system_gains(values)
    return {"ok": "REFUSED" not in status and "No answer" not in status, "status": status}


def api_robotlog_clear(_body):
    S.robotlog.clear()
    return {"ok": True}


def _in_sim():
    """Whether the connected robot is the simulator: its results never count for a real part."""
    try:
        return bool(S.link and S.link.is_connected() and S.link.environment().get("active") == "SIM")
    except Exception:  # noqa: BLE001 - no answer: not the simulator as far as we know
        return False


def api_part_mark(body):
    b = body or {}
    key = setup_plans.part_key(b.get("kind") or "", str(b.get("which") or ""))
    if key not in _parts():
        return {"ok": False, "error": "Start that part first."}
    if _in_sim():
        return {"ok": False, "error": "The simulator's results never count for a real part: nothing was recorded."}
    mark = {"result": "pass" if b.get("result") == "pass" else "fail", "when": setup_plans.stamp(),
            "detail": str(b.get("detail") or "")[:300]}
    progress.change(S.project.name, lambda p: p.setdefault("parts", {}).setdefault(key, {})
                    .setdefault("marks", {}).__setitem__(str(b.get("step")), mark))
    return api_part_plan({"kind": b.get("kind"), "which": b.get("which")})


def api_part_stop(body):
    b = body or {}
    key = setup_plans.part_key(b.get("kind") or "", str(b.get("which") or ""))
    progress.change(S.project.name if S.project else None, lambda p: p.setdefault("parts", {}).pop(key, None))
    return {"ok": True}


def api_mark(body):
    """A tool's result for its checklist: ``{"key": "cal_positions", "result": "pass", "detail"}``."""
    b = body or {}
    key = str(b.get("key") or "")
    if not S.project or not key.startswith(("cal_", "wire_", "bu_")):
        return {"ok": False, "error": "Nothing to mark."}
    if _in_sim():
        return {"ok": False, "error": "The simulator's results never count: nothing was recorded."}
    progress.update(S.project.name, {key: {"result": "pass" if b.get("result") == "pass" else "fail",
                                           "when": setup_plans.stamp(), "detail": str(b.get("detail") or "")[:300]}})
    return {"ok": True}


def api_battery_pick(body):
    bid = str((body or {}).get("id") or "").strip()
    if not bid:
        return {"ok": False, "error": "Which battery?"}
    if not (S.link and S.link.is_connected()):
        return {"ok": False, "error": "Connect to the robot first."}
    if not S.link.set_battery(bid):
        return {"ok": False, "error": "The robot did not take it. Try again, or pick it on the dashboard."}
    return {"ok": True, "id": bid}


_CONTROLLER_STEPS = {"rest": controllers.rest, "sticks": controllers.sticks, "returns": controllers.returns,
                     "triggers": controllers.triggers, "buttons": controllers.buttons}


def api_controllers_code(_query=None):
    """The deadbands the robot code applies to the sticks."""
    if not S.project:
        return {"ok": True, "deadbands": []}
    S.reload_project()
    return {"ok": True, "project": S.project.name, "deadbands": controllers.code_deadbands(S.project),
            "sticks": controllers.stick_deadbands(S.project),
            # Which Driver Station port drives and which holds the test deadman (slothtune.json).
            "operator": (S.project.data.get("slothtune.json") or {}).get("operator") or {}}


def api_controllers_step(body):
    fn = _CONTROLLER_STEPS.get((body or {}).get("step"))
    if not fn:
        return {"ok": False, "error": "Which step?"}
    samples = body.get("samples") or []
    out = fn(samples)
    out.update(ok=True, interval_ms=controllers.update_interval_ms(samples), n=len(samples))
    return out


def api_controllers_robot(body):
    """One step of the joystick check through the robot: what the robot code receives from a
    Driver Station port, recorded by the robot (disabled), judged like the laptop's own."""
    b = body or {}
    fn = _CONTROLLER_STEPS.get(b.get("step"))
    if not fn:
        return {"ok": False, "error": "Which step?"}
    if not (S.link and S.link.is_connected()):
        return {"ok": False, "error": "Connect to the robot first."}
    secs = max(1.0, min(90.0, float(b.get("secs") or 5)))
    res = S.link.run_test("controller", "ALL", {"port": int(b.get("port", 0)), "duration_s": secs},
                          timeout=secs + 15)
    if not res.accepted:
        return {"ok": False, "error": res.message}
    samples = controllers.rows_from_robot(res.channels)
    out = fn(samples)
    out.update(ok=True, interval_ms=controllers.update_interval_ms(samples), n=len(samples), source="robot",
               name=next((n.split(": ", 1)[1] for n in res.notes if n.startswith("Controller on port")), ""))
    return out


def api_controllers_report(body):
    db = controllers.code_deadbands(S.project) if S.project else []
    read = controllers.axes_read(S.project) if S.project else None
    out = controllers.report((body or {}).get("steps") or {}, db, read or None)
    out["ok"] = True
    return out


def api_controllers_save(body):
    b = body or {}
    label = str(b.get("label") or "").strip()
    if not label:
        return {"ok": False, "error": "Name the joystick first (Driver, Operator, Spare 1...)."}
    rep = b.get("report") or {}
    entry = {"when": time.strftime("%Y%m%d-%H%M%S"), "label": label, "device": str(b.get("device") or "")[:120],
             "worst_offset": rep.get("worst_offset"), "recommended_deadband": rep.get("recommended_deadband"),
             "verdict": rep.get("verdict"), "problems": [f["title"] for f in rep.get("findings") or []
                                                         if f.get("level") in ("warn", "error")]}
    runs.controller_log_add(entry)
    return {"ok": True, "entry": entry}


def api_controllers_history(_query=None):
    return {"ok": True, "history": runs.controller_log()[-200:]}


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
    from . import design as D
    prog = progress.load(S.project.name) or {}
    design = wiring._design(S.project)
    return {"ok": True, "map": m, "devices": wiring.devices_by_name(S.project, m),
            "lengths": [wiring.bus_length(b) for b in m["buses"]], "snapshot": snap,
            # Each bus's cable color (CAN-H; CAN-L is green on all), and the colors CTRE's cable comes in.
            "bus_colors": wiring.bus_colors(m, design), "palette": D.BUS_COLORS,
            "bus_labels": wiring.bus_labels(m, design),
            # The robot controller the design names (roborio, roborio2, systemcore): which one is drawn.
            "controller": (design or {}).get("controller") or "",
            # From the design file, for a device's hover card: its subsystem and breaker.
            "design_devices": {x.get("name"): {"subsystem": x.get("subsystem") or "",
                                               "breaker": (x.get("pdh") or {}).get("breaker"),
                                               "positive": x.get("positive") or ""}
                               for x in (design or {}).get("motors") or [] if x.get("name")},
            # Each bus's termination check, as last recorded (robot off, a multimeter).
            "termination": {b.get("name"): prog.get("wire_ohms:" + str(b.get("name")))
                            or (prog.get("wire_ohms") if len(m["buses"]) == 1 else None) for b in m["buses"]},
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
            return {"ok": False, "error": "Type how far the robot moved, in inches."}
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
    mine = [r for r in spins if (r.get("robot") or "").lower() == robot]
    use = mine or spins
    if not use:
        out = geometry.spin_check({})
        out.update(ok=True, run=None)
        return out
    doc = runs.load(use[0]["file"])
    out = geometry.spin_check(advisor.spin_report(doc).get("measured"), ratio)
    # Another robot's spin is shown, never counted for this one.
    out.update(ok=True, run=use[0]["file"], saved=use[0].get("saved"), robot_match=bool(mine))
    return out


def _camera_mounts():
    return dict((S.project.data.get("slothtune.json") or {}).get("cameras") or {}) if S.project else {}


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


def api_survey_start(body=None):
    """Starts recording every camera's tags until stopped (``keep``: added to what was recorded before,
    as the new-field sweep does at each spot)."""
    if not S.link or not S.link.is_connected():
        return {"ok": False, "error": "Connect to the robot first (or try Practice)."}
    if SURVEY["running"]:
        return {"ok": True}
    if (body or {}).get("keep"):
        SURVEY.update(running=True)
    else:
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

    SURVEY["thread"] = threading.Thread(target=work, name="slothtune-survey", daemon=True)
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


# ---------------------------------------------------------------------------- the camera itself
# The laptop talks to the camera's PhotonVision directly (photon.py): its version, a guided lens
# calibration, and tuning it to a venue's lights. The robot code can't: PhotonLib only switches
# pipelines.
CAMERA = {"photon": None, "lighting": None}
NEWFIELD = {"sweeps": [], "samples": [], "running": False, "message": ""}


def _camera(body=None, connect=False):
    """The connected camera, (re)connecting to ``body["host"]`` ("10.17.45.11", or "host:port")."""
    from . import photon

    host = ((body or {}).get("host") or "").strip()
    p = CAMERA["photon"]
    if host:
        h, _, port = host.partition(":")
        port = int(port) if port.isdigit() else photon.PORT
        if connect or not (p and p.alive and p.host == h and p.port == port):
            if p:
                p.close()
            p = CAMERA["photon"] = photon.Photon(h, port, timeout=4.0).connect()
    if not (p and p.alive):
        raise ConnectionError("Connect to the camera first.")
    return p


def _camera_info(p):
    from . import photon, versions

    out = {"ok": True, "host": p.host, "port": p.port, **p.hardware(), "cameras": []}
    for c in p.cameras:
        cur = c.get("currentPipelineSettings") or {}
        out["cameras"].append({
            "unique": c.get("uniqueName"), "nickname": c.get("nickname"), "connected": c.get("isConnected"),
            "modes": photon.Photon.modes(c), "pipeline": c.get("currentPipelineIndex"),
            "mode": cur.get("cameraVideoModeIndex"),
            "settings": {k: cur.get(k) for k in ("cameraAutoExposure", "cameraExposureRaw", "cameraGain", "cameraBrightness")},
            "calibrations": [photon.summarize_calibration(x) for x in c.get("calibrations") or []],
            "stream": f"http://{p.host}:{c.get('inputStreamPort') or 1181}/stream.mjpg"})
    # The camera's PhotonVision must be the robot code's PhotonLib version (PhotonLib refuses a mismatch).
    lib = None
    if S.project:
        lib = next((d["version"] for d in versions.local(S.project.path) if d["name"].lower() == "photonlib"), None)
    cam = p.version()
    out["photonlib"] = lib
    out["match"] = bool(lib and cam and versions.vkey(cam)[:3] == versions.vkey(lib)[:3])
    return out


def api_camera_connect(body):
    try:
        return _camera_info(_camera(body, connect=True))
    except (OSError, ConnectionError) as e:
        return {"ok": False, "error": f"No PhotonVision at {(body or {}).get('host')}: {e}. Is the camera on, on the "
                                      "robot's network, and is that its address (its page is on port 5800)?"}


def api_camera_cal_start(body):
    try:
        p = _camera(body)
        p.start_calibration(body["camera"], int(body.get("mode", 1)), float(body.get("square_in") or 1.0),
                            float(body.get("marker_in") or 0.75))
        return {"ok": True}
    except (OSError, ConnectionError, KeyError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def api_camera_cal_snap(body):
    try:
        return {"ok": True, **_camera(body).snapshot(body["camera"])}
    except (OSError, ConnectionError, KeyError) as e:
        return {"ok": False, "error": str(e)}


def api_camera_cal_finish(body):
    """Has PhotonVision solve the calibration, then reads it back: mean error and field of view."""
    from . import photon

    try:
        p = _camera(body)
        ok, msg = p.finish_calibration(body["camera"])
        if not ok:
            return {"ok": False, "error": f"PhotonVision couldn't solve it ({msg}): take more snapshots, the board "
                                          "flat and tilted, all over the picture."}
        # Its new calibration comes with fresh settings: connect again to read them.
        p = _camera({"host": f"{p.host}:{p.port}"}, connect=True)
        cam = p.camera(body["camera"]) or {}
        w, h = body.get("width"), body.get("height")
        cals = [photon.summarize_calibration(x) for x in cam.get("calibrations") or []]
        mine = next((c for c in cals if (c["width"], c["height"]) == (w, h)), cals[-1] if cals else None)
        return {"ok": True, "message": msg, "calibration": mine}
    except (OSError, ConnectionError, KeyError) as e:
        return {"ok": False, "error": str(e)}


def api_camera_cal_cancel(body):
    try:
        _camera(body).finish_calibration(body["camera"], timeout=30)
    except (OSError, ConnectionError, KeyError):
        pass
    return {"ok": True}


def api_camera_lighting(body):
    """Starts tuning the camera's exposure and gain to the light it sees now (newfield.Lighting)."""
    from . import newfield, photon

    try:
        p = _camera(body)
    except (OSError, ConnectionError) as e:
        return {"ok": False, "error": str(e)}
    cam = p.camera(body.get("camera"))
    if not cam:
        return {"ok": False, "error": "Pick the camera."}
    cur = cam.get("currentPipelineSettings") or {}
    mode = next((m for m in photon.Photon.modes(cam) if m["index"] == cur.get("cameraVideoModeIndex")), None)
    cal = next((photon.summarize_calibration(c) for c in cam.get("calibrations") or []
                if mode and ((c.get("resolution") or {}).get("width"), (c.get("resolution") or {}).get("height"))
                == (mode["width"], mode["height"])), None)
    if not cal or not cal.get("fx"):
        return {"ok": False, "error": "Calibrate the lens at the resolution the pipeline uses first (6. Camera lens): "
                                      "the exposure is worked out from it."}
    if CAMERA["lighting"] and CAMERA["lighting"].state == "running":
        return {"ok": False, "error": "It's already tuning."}
    CAMERA["lighting"] = newfield.Lighting(p, cam["uniqueName"], cal["fx"])
    CAMERA["lighting"].start()
    return {"ok": True, **CAMERA["lighting"].to_json()}


def api_camera_lighting_state(_query=None):
    job = CAMERA["lighting"]
    return {"ok": True, **job.to_json()} if job else {"ok": True, "state": "none"}


def api_camera_lighting_stop(_):
    if CAMERA["lighting"]:
        CAMERA["lighting"].stop()
    return {"ok": True}


def api_camera_lighting_restore(_):
    if CAMERA["lighting"]:
        CAMERA["lighting"].restore()
        CAMERA["lighting"].message = "The camera is back on the settings it had before."
    return {"ok": True}


def api_newfield_sweep(_body=None):
    """The robot spins slowly in place, a full turn each way, while the survey records every tag and
    the vision poses are kept for the mount check. A person holds the deadman, as for any test."""
    from . import newfield

    if not (S.link and S.link.is_connected()):
        return {"ok": False, "error": "Connect to the robot first."}
    if S.test_state.get("running") or NEWFIELD["running"]:
        return {"ok": False, "error": "A test is running."}
    NEWFIELD.update(running=True, message="Spinning slowly: hold the deadman. A full turn each way.")
    api_survey_start({"keep": True})

    def work():
        samples, stop = [], threading.Event()

        def poses():
            last = None
            while not stop.is_set():
                try:
                    L = S.link.live()
                    v = tuple(L.get("vision_pose") or ())
                    if len(v) >= 3 and v != last:
                        samples.append((list(L.get("pose") or []), list(v)))
                        last = v
                except Exception:  # noqa: BLE001 - a dropped sample is fine
                    pass
                time.sleep(0.05)

        th = threading.Thread(target=poses, daemon=True)
        th.start()
        try:
            res, _doc, run = S.run_test_sync("spin", "ALL", dict(newfield.SWEEP))
            outcome = res.outcome if res.accepted else "REFUSED"
            msg = res.message
        except Exception as e:  # noqa: BLE001
            outcome, msg, run = "ERROR", str(e), None
        stop.set()
        th.join(1.0)
        SURVEY["running"] = False
        NEWFIELD["samples"] += samples
        NEWFIELD["sweeps"].append({"outcome": outcome, "message": msg, "run": run, "poses": len(samples),
                                   "when": time.strftime("%H:%M")})
        NEWFIELD.update(running=False, message=("Swept. Move the robot to another spot and sweep again (two or three "
                                                "spots), then work out where the tags are." if outcome == "DONE"
                                                else f"The sweep ended {outcome.lower()}: {msg}"))

    threading.Thread(target=work, name="slothtune-sweep", daemon=True).start()
    return {"ok": True}


def api_newfield(_query=None):
    from . import newfield

    from . import link as L

    survey = api_survey_state()
    team = L.team_from_project(S.project.path) if S.project else None
    return {"ok": True, "running": NEWFIELD["running"], "message": NEWFIELD["message"], "sweeps": NEWFIELD["sweeps"],
            # The team's convention for the camera's address (docs/VISION_LUMA_PHOTONVISION.md).
            "default_host": f"10.{team // 100}.{team % 100}.11" if team else "",
            "survey": {k: survey[k] for k in ("sightings", "views", "tags")},
            "mount": newfield.mount_check(NEWFIELD["samples"]) if NEWFIELD["sweeps"] else None,
            "lighting": api_camera_lighting_state()}


def api_newfield_reset(_):
    NEWFIELD.update(sweeps=[], samples=[], message="")
    SURVEY.update(sightings=[], keys=set())
    return {"ok": True}


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
    devices = [n for n in chain if n not in ("roboRIO", "PDH")]
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
    """A bus's termination from one or two multimeter readings at its far end (with its terminator
    in, then out); "OL" is open."""
    b = body or {}
    bus = None
    if S.project and b.get("bus"):
        bus = next((x for x in S.wiring_map().get("buses") or [] if x.get("name") == b.get("bus")), None)
    return wiring.termination_pair(wiring.parse_ohms(b.get("ohms")), wiring.parse_ohms(b.get("without")), bus)


def api_export(body):
    doc = runs.load(body["file"])
    path = os.path.join(runs.RUNS, os.path.splitext(doc["_file"])[0] + ".wpilog")
    names = akit.export_run(doc, path)
    return {"ok": True, "path": path, "entries": len(names), "sysid": doc.get("test") == "drive_ff"}


def api_predict(body):
    """'What if': the same run, predicted with changed gains. Gains not given keep their value."""
    doc = runs.load(body["file"])
    if body.get("pod"):
        doc = advisor.pod_doc(doc, body["pod"])  # from that pod's own gains
    now = {k: float(v) for k, v in (doc.get("gains") or {}).items() if isinstance(v, (int, float))}
    new = dict(now)
    new.update({k: float(v) for k, v in (body.get("gains") or {}).items()})
    lim = S.limits() if not doc.get("practice") else {"steer": 20.0, "drive": 40.0}
    loop = "steer" if doc.get("test") == "steer_step" else "drive"
    if loop == "steer":
        kind = None
    elif doc.get("practice"):
        kind = (doc.get("meta") or {}).get("pod_motor")  # the pod drives with the robot's motor (a Vortex)
    else:
        kind = S.project.drive_kind() if S.project else None
    return predict.predict(doc, now, new, int(body.get("module", 0)), current_limit=lim.get(loop),
                           motor_kind=kind)


def api_analyze(body):
    doc = runs.load(body["file"])
    rep = advisor.analyze(doc, doc.get("gains"), measured_forward_m=body.get("tape_forward"),
                          measured_lateral_m=body.get("tape_lateral"))
    if body.get("tape_forward") is not None and S.project:
        # The tape is what the straight-line step is graded on: it ticks (or un-ticks) the step.
        progress.record_run(S.project.name, doc, rep, doc.get("_file"))
    return rep


def api_offsets(body):
    doc = runs.load(body["file"])
    return advisor.offsets_from_capture(doc, S.project.offsets() if S.project else {})


def api_handcheck(body):
    doc = runs.load(body["file"])
    out = advisor.hand_check(doc, body.get("kind", "wheel"), int(body.get("sign", 1)))
    g = (out.get("gyro") or {}).get("heading") if body.get("kind") == "gyro" else None
    if g and g["verdict"] == "INVERTED" and S.project:
        # The one setting that flips it: offered as a change to review, never written here.
        now = bool((S.project.data.get("swervedrive.json") or {}).get("invertedIMU"))
        out["gyro"]["fix"] = {"file": "swervedrive.json", "path": ["invertedIMU"], "value": not now}
    return out


def api_symptoms(_):
    """Every problem Troubleshoot knows, with the groups it shows under (kind of problem, and device
    or system), and those groups' names in order."""
    return {"symptoms": [{"id": s["id"], "title": s["title"], "looks_like": s["looks_like"],
                          **diagnose.groups(s["id"])} for s in diagnose.SYMPTOMS],
            "groups": {"issues": [list(g) for g in diagnose.ISSUES], "devices": [list(g) for g in diagnose.DEVICES]}}


def api_diagnose(sid):
    lint = yagslcfg.lint(S.project) if S.project else []
    return diagnose.evaluate(sid, lint, S.flags, S.netcheck_last)


def api_practice(body):
    loop = body.get("loop", "steer")
    surface = body.get("surface", "floor")
    g = {k: float(v) for k, v in (body.get("gains") or {}).items()}
    # The pod drives with the robot's own drive motor (a Vortex on both robots), so practice
    # teaches that motor's speeds and sensor.
    kind = S.project.drive_kind() if S.project else None
    motor = kind if kind in plant.MOTORS and kind != "neo550" else "neo"
    pod = {"pod_motor": motor}
    lim = S.limits()  # the robot's own current limits, so practice saturates where the robot would
    if loop == "steer":
        ch = plant.steer_step(rehearse.STEER_PATTERN, kP=g.get("Steer/kP", 0.01),
                              kI=g.get("Steer/kI", 0), kD=g.get("Steer/kD", 0),
                              i_zone=g.get("Steer/IZone", 0), ramp_s=g.get("Steer/RampS", 0),
                              surface=surface, current_limit=lim["steer"])
        doc = {"test": "steer_step", "module": "FL"}
    elif loop == "drive":
        m = rehearse.MODULES[0]
        ch = plant.drive_step(rehearse.DRIVE_PATTERN, kP=g.get("Drive/kP", 0.002),
                              kI=g.get("Drive/kI", 0), kD=g.get("Drive/kD", 0),
                              ramp_s=g.get("Drive/RampS", 0), surface=surface, motor=motor,
                              current_limit=lim["drive"],
                              meas_period_ms=int(g.get("Drive/VelPeriodMs") or 0) or None,
                              meas_depth=int(g.get("Drive/VelDepth") or 0) or None,
                              ff=(g.get(f"FF/{m}/kS", 0), g.get(f"FF/{m}/kV", plant.nominal_kv(motor)),
                                  g.get(f"FF/{m}/kA", 0)))
        doc = {"test": "drive_step", "module": "ALL", "meta": pod}
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
                                   limit_before_a=g.get("Limit/Drive", 40.0), motor=motor)
        doc = {"test": "slip", "module": "ALL", "meta": dict(meta, **pod)}
    else:
        ch = plant.drive_ff(surface=surface, quasi_s=6, max_v=6, motor=motor,
                            meas_period_ms=int(g.get("Drive/VelPeriodMs") or 16),
                            meas_depth=int(g.get("Drive/VelDepth") or 2))
        doc = {"test": "drive_ff", "module": "ALL", "meta": {"kv_nominal": plant.nominal_kv(motor), **pod}}
    doc.update(channels=ch, practice=True, env="FIELD" if surface == "floor" else "BLOCKS",
               robot={"name": f"practice pod ({revspecs.MOTORS[motor]['label']} drive)", "modules": rehearse.MODULES},
               outcome="DONE")
    # The pod is a MAXSwerve on 5.50:1 and 3 inch wheels, so the report can judge its motor too.
    rep = advisor.analyze(doc, g, drive_gear=5.5, wheel_d_in=3.0, drive_kind=motor)
    path = runs.save(doc, rep, g, practice=True)
    doc["report"] = rep
    doc["explain"] = explain.explain(doc, g, {"steer": 20.0, "drive": 40.0})
    doc["_file"] = os.path.basename(path)
    doc["gains"] = g
    return doc


def api_progress_get(_):
    return progress.load(S.project.name if S.project else None)


def api_progress_put(body):
    return progress.update(S.project.name if S.project else None, body)


def api_sim(body):
    if not S.link:
        return {"ok": False, "error": "Not connected."}
    S.link.sim_enable(bool(body.get("on")))
    return {"ok": True}


GET = {"/api/projects": api_projects, "/api/lint": api_lint, "/api/state": api_state, "/api/autotune": api_autotune,
       "/api/systems/autotune": api_sys_autotune,
       "/api/camera/lighting": api_camera_lighting_state, "/api/newfield": api_newfield, "/api/field": api_field,
       "/api/live": api_live, "/api/runs": api_runs, "/api/symptoms": api_symptoms,
       "/api/progress": api_progress_get, "/api/wiring": api_wiring, "/api/logs": api_logs,
       "/api/robotlog": api_robotlog, "/api/systems": api_systems,
       "/api/designs": api_designs,
       "/api/logsummary": api_logsummary, "/api/wiring/pdhfind": api_wiring_pdhfind,
       "/api/wiring/wiggle": api_wiring_wiggle, "/api/geometry/spin": api_geometry_spin,
       "/api/survey/state": api_survey_state, "/api/ppcheck": api_ppcheck,
       "/api/motors/inventory": api_motor_inventory, "/api/battery": api_battery,
       "/api/controllers/code": api_controllers_code, "/api/controllers/history": api_controllers_history,
       "/api/setup": api_setup, "/api/parts": api_parts, "/api/parts/plan": api_part_plan,
       "/api/bringup": api_bringup}
POST = {"/api/project": api_set_project, "/api/connect": api_connect, "/api/netcheck": api_netcheck, "/api/netcheck/save": api_netcheck_save,
        "/api/disconnect": api_disconnect, "/api/env": api_env, "/api/test": api_test,
        "/api/abort": api_abort, "/api/stop": api_stop, "/api/deadman": api_deadman,
        "/api/autotune/start": api_autotune_start, "/api/autotune/continue": api_autotune_continue,
        "/api/motors/clear-sticky": api_motors_clear_sticky,
        "/api/systems/autotune/start": api_sys_autotune_start, "/api/systems/autotune/continue": api_sys_autotune_continue,
        "/api/systems/autotune/stop": api_sys_autotune_stop,
        "/api/autotune/stop": api_autotune_stop, "/api/gyro/command": api_gyro_command,
        "/api/camera/connect": api_camera_connect, "/api/camera/cal/start": api_camera_cal_start,
        "/api/camera/cal/snap": api_camera_cal_snap, "/api/camera/cal/finish": api_camera_cal_finish,
        "/api/camera/cal/cancel": api_camera_cal_cancel, "/api/camera/lighting": api_camera_lighting,
        "/api/camera/lighting/stop": api_camera_lighting_stop, "/api/camera/lighting/restore": api_camera_lighting_restore,
        "/api/newfield/sweep": api_newfield_sweep, "/api/newfield/reset": api_newfield_reset,
        "/api/gains": api_gains, "/api/save/preview": api_save_preview,
        "/api/save/apply": api_save_apply, "/api/analyze": api_analyze,
        "/api/offsets": api_offsets, "/api/handcheck": api_handcheck,
        "/api/practice": api_practice, "/api/progress": api_progress_put,
        "/api/designs/read": api_design_read, "/api/sim": api_sim,
        "/api/motors/override": api_motor_override, "/api/predict": api_predict,
        "/api/export": api_export, "/api/wiring/termination": api_wiring_termination,
        "/api/robotlog/clear": api_robotlog_clear, "/api/systems/physics": api_systems_physics,
        "/api/systems/gains": api_systems_gains,
        "/api/geometry/tape": api_geometry_tape, "/api/geometry/wheels": api_geometry_wheels,
        "/api/camcal/sample": api_camcal_sample, "/api/camcal/solve": api_camcal_solve,
        "/api/survey/start": api_survey_start, "/api/survey/stop": api_survey_stop,
        "/api/survey/solve": api_survey_solve, "/api/gyro": api_gyro, "/api/battery/pick": api_battery_pick,
        "/api/controllers/step": api_controllers_step, "/api/controllers/report": api_controllers_report,
        "/api/controllers/robot": api_controllers_robot,
        "/api/controllers/save": api_controllers_save, "/api/mark": api_mark,
        "/api/parts/start": api_part_start, "/api/parts/mark": api_part_mark, "/api/parts/stop": api_part_stop,
        "/api/bringup/draft": api_bringup_draft}


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

    def _host_ok(self):
        # Only this laptop's own address: a page from another site that points its own name at
        # 127.0.0.1 (DNS rebinding) arrives with that name as its Host.
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _guard_origin(self):
        # Only this page may drive the robot: refuse requests from any other site's page, and any
        # request without this run's token (another program, or a page from before a restart).
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if not self._host_ok() or not (origin is None or origin.endswith("//" + host)):
            return False
        return hmac.compare_digest(self.headers.get("X-SlothTune-Token", ""), TOKEN)

    def do_GET(self):
        path = urlparse(self.path).path
        if not self._host_ok():
            return self._send(403, {"ok": False, "error": "wrong host"})
        try:
            if path in GET:
                return self._send(200, GET[path](dict(parse_qsl(urlparse(self.path).query))))
            if path.startswith("/api/runs/"):
                return self._send(200, api_run(unquote(path[len("/api/runs/"):]),
                                               dict(parse_qsl(urlparse(self.path).query))))
            if path.startswith("/api/diagnose/"):
                return self._send(200, api_diagnose(unquote(path[len("/api/diagnose/"):])))
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            full = os.path.normpath(os.path.join(WEB, rel))
            if not full.startswith(WEB) or not os.path.isfile(full):
                return self._send(404, {"error": "not found"})
            with open(full, "rb") as fh:
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                data = fh.read()
            if rel == "index.html":
                # The page carries this run's token; every change it asks for sends it back.
                data = data.replace(b"</head>", f'<meta name="slothtune-token" content="{TOKEN}">\n</head>'.encode(), 1)
            return self._send(200, data, ctype)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"ok": False, "error": str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        # Read the body before anything else, even a refusal: a socket closed with its request still
        # unread is reset on Windows, and the client can lose the answer (the suite's intermittent
        # ConnectionAbortedError in the token test).
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        raw = self.rfile.read(n) if n > 0 else b""
        if not self._guard_origin():
            return self._send(403, {"ok": False, "error": "Refused: this page is out of date or isn't the tool's own. "
                                    "Reload it (the tool may have restarted)."})
        try:
            body = json.loads(raw or b"{}")
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
        projects = yagslcfg.find_projects(runs.ROBOTS)
        if projects:
            S.set_project(os.path.basename(projects[0]))
    port = getattr(args, "port", 5806)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Sloth Tune running at {url}  (Ctrl+C to stop)")
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
