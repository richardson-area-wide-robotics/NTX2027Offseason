"""The laptop's connection to the robot, over NetworkTables 4.

Everything that touches ``pyntcore`` lives in this file. Two reasons:

* pyntcore's method names change in 2027 (``getDefault`` becomes ``get_default`` and so on), so
  every call goes through :func:`_call`, which tries both spellings.
* the GUI, the command line and an AI agent all use this one class, so they all talk to the robot
  the same way.

The robot never trusts this end: it bounds every gain, enforces every safety rule, and needs a
boot id echoed on every command (see SwerveTuneTopics.BOOT_ID). This class just makes those
rules easy to follow.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field

from . import contract as C

try:  # pyntcore is only needed when talking to a robot; analysis and lint work without it.
    import ntcore  # type: ignore
except ImportError:  # pragma: no cover - exercised on machines without pyntcore
    ntcore = None


NT_PORT = 5810
INSTALL_HINT = "pyntcore is not installed. Run:  py -3.12 -m pip install pyntcore"


def _call(obj, camel, *args):
    """Calls ``obj.camelName(*args)`` or, on 2027 pyntcore, ``obj.camel_name(*args)``."""
    fn = getattr(obj, camel, None)
    if fn is None:
        snake = "".join("_" + c.lower() if c.isupper() else c for c in camel).lstrip("_")
        fn = getattr(obj, snake)
    return fn(*args)


def team_from_project(project_dir):
    """Team number from ``.wpilib/wpilib_preferences.json``, or None."""
    try:
        with open(os.path.join(project_dir, ".wpilib", "wpilib_preferences.json"), encoding="utf-8") as fh:
            return int(json.load(fh).get("teamNumber"))
    except (OSError, ValueError, TypeError):
        return None


def candidate_hosts(team=None, host=None, sim=False):
    """Addresses to try, best first.

    A literal address beats mDNS: with a robot NIC and a VPN both up, mDNS answers from whichever
    interface replies first. Covers the roboRIO (2026) and SystemCore (2027): SystemCore keeps
    10.TE.AM.2 but its hostname is always ``robot`` and it adds its own USB and Wi-Fi addresses.
    """
    if host:
        return [host]
    if sim:
        return ["127.0.0.1"]
    hosts = []
    if team:
        te, am = divmod(int(team), 100)
        hosts += [f"10.{te}.{am}.2", f"roborio-{team}-frc.local"]
    hosts += ["172.22.11.2", "robot.local", "172.26.0.1", "172.27.0.1", "172.30.0.1"]
    return hosts


@dataclass
class TestResult:
    """What came back from one test run."""

    test: str
    module: str
    args: dict
    accepted: bool
    message: str
    outcome: str = ""
    seq: int = 0
    channels: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    robot: dict = field(default_factory=dict)
    env: str = ""
    started: float = field(default_factory=time.time)
    battery: str = ""

    @property
    def ok(self):
        return self.accepted and self.outcome == "DONE"

    def to_json(self):
        return {
            "test": self.test, "module": self.module, "args": self.args,
            "accepted": self.accepted, "message": self.message, "outcome": self.outcome,
            "seq": self.seq, "meta": self.meta, "notes": self.notes, "robot": self.robot,
            "env": self.env, "started": self.started, "channels": self.channels,
            "battery": self.battery,
        }

    @staticmethod
    def from_json(d):
        return TestResult(
            test=d["test"], module=d.get("module", "ALL"), args=d.get("args", {}),
            accepted=d.get("accepted", True), message=d.get("message", ""),
            outcome=d.get("outcome", ""), seq=d.get("seq", 0), channels=d.get("channels", {}),
            meta=d.get("meta", {}), notes=d.get("notes", []), robot=d.get("robot", {}),
            env=d.get("env", ""), started=d.get("started", 0.0), battery=d.get("battery", ""))


class RobotLink:
    """One connection to one robot (or the simulator)."""

    def __init__(self, hosts, client_name="swervetune"):
        if ntcore is None:
            raise RuntimeError(INSTALL_HINT)
        self.hosts = list(hosts)
        self.inst = _call(ntcore.NetworkTableInstance, "create")
        _call(self.inst, "startClient4", client_name)
        _call(self.inst, "setServer", [(h, NT_PORT) for h in self.hosts])
        # A new NT4 subscriber reads its default until the server's first value arrives. Subscribing
        # to the whole /SwerveTune tree up front keeps every value cached here, so the first read of
        # any topic is the robot's value, not a stale default.
        self._everything = ntcore.MultiSubscriber(
            self.inst, [C.ROOT + "/", C.AK + "/PowerDistribution/", C.AK + "/SystemStats/", "/SmartDashboard/"])
        self._pubs = {}
        self._subs = {}
        self._hb_value = 0.0
        self._hb_stop = threading.Event()
        self._hb_thread = None
        self._deadman = False
        self._gui_deadman = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ plumbing
    def _topic(self, kind, name):
        getter = {"double": "getDoubleTopic", "int": "getIntegerTopic", "bool": "getBooleanTopic",
                  "str": "getStringTopic", "double[]": "getDoubleArrayTopic",
                  "str[]": "getStringArrayTopic"}[kind]
        return _call(self.inst, getter, name)

    def _pub(self, kind, name):
        key = (kind, name)
        if key not in self._pubs:
            self._pubs[key] = _call(self._topic(kind, name), "publish")
        return self._pubs[key]

    def _sub(self, kind, name, default):
        key = (kind, name)
        if key not in self._subs:
            self._subs[key] = _call(self._topic(kind, name), "subscribe", default)
        return self._subs[key]

    def get(self, kind, name, default=None):
        defaults = {"double": float("nan"), "int": 0, "bool": False, "str": "", "double[]": [],
                    "str[]": []}
        d = defaults[kind] if default is None else default
        return _call(self._sub(kind, name, d), "get")

    def put(self, kind, name, value):
        with self._lock:
            _call(self._pub(kind, name), "set", value)

    def flush(self):
        _call(self.inst, "flush")

    def close(self):
        self.stop_heartbeat()
        try:
            _call(self.inst, "stopClient")
        except Exception:  # noqa: BLE001 - closing must never raise
            pass

    # ------------------------------------------------------------------ connection
    def is_connected(self):
        return bool(_call(self.inst, "isConnected"))

    def wait_connected(self, timeout=6.0):
        end = time.time() + timeout
        while time.time() < end:
            if self.is_connected() and self.get("int", C.BOOT_ID) != 0:
                return True
            time.sleep(0.05)
        return self.is_connected()

    def connected_to(self):
        try:
            conns = _call(self.inst, "getConnections")
            return conns[0].remote_ip if conns else ""
        except Exception:  # noqa: BLE001
            return ""

    def has_harness(self):
        return self.get("int", C.PROTOCOL) != 0

    def robot_info(self):
        names = list(self.get("str[]", C.MODULE_NAMES))
        locs = list(self.get("double[]", C.MODULE_LOCATIONS))
        return {
            "protocol": self.get("int", C.PROTOCOL),
            "boot_id": self.get("int", C.BOOT_ID),
            "name": self.get("str", C.ROBOT_NAME),
            "modules": names,
            "locations": [locs[2 * i:2 * i + 2] for i in range(len(locs) // 2)],
            "max_module_speed": self.get("double", C.MAX_MODULE_SPEED),
            "steer_feedback": self.get("str", C.STEER_FEEDBACK),
            "startup_report": list(self.get("str[]", C.STARTUP_REPORT)),
            "address": self.connected_to(),
        }

    # ------------------------------------------------------------------ heartbeat and deadman
    def start_heartbeat(self, gate=None):
        """Tells the robot a laptop is watching. Motion tests stop within half a second of this ending.

        ``gate``, if given, is asked before every beat. The GUI passes "has the browser checked in
        within the last half second", so closing the browser tab stops a running test even though
        this process keeps running.
        """
        self._gate = gate
        if self._hb_thread and self._hb_thread.is_alive():
            return
        self._hb_started = time.time()

        def beat():
            while not self._hb_stop.wait(0.05):
                alive = self._gate() if self._gate else True
                if alive:
                    self._hb_value += 1
                    self.put("double", C.CLIENT_HEARTBEAT, self._hb_value)
                # Only the GUI publishes the deadman: a command-line client publishing "not held"
                # on the same topic made the robot read the GUI's Hold to run as released.
                if self._gui_deadman:
                    self.put("bool", C.CLIENT_DEADMAN, self._deadman and alive)
                self.flush()

        self._hb_stop.clear()
        self._hb_thread = threading.Thread(target=beat, name="swervetune-heartbeat", daemon=True)
        self._hb_thread.start()

    def wait_heartbeat_established(self, seconds=0.3):
        """The robot refuses motion tests until it has seen a heartbeat; give it time to see one."""
        started = getattr(self, "_hb_started", None)
        if started is not None:
            time.sleep(max(0.0, started + seconds - time.time()))

    def stop_heartbeat(self):
        self._hb_stop.set()
        self._deadman = False

    def set_gui_deadman(self, held):
        """Only the GUI calls this, while its Hold to run button is held."""
        self._gui_deadman = True
        self._deadman = bool(held)

    # ------------------------------------------------------------------ environment
    def put_retained(self, kind, name, value):
        """Publishes a value the robot must keep after this program exits. NT4 drops a topic when its
        last publisher goes away, so a one-shot command line (``env --mode BLOCKS``) would set the
        environment and lose it the moment it closed; a retained topic keeps its last value until
        the robot restarts."""
        with self._lock:
            _call(self._pub(kind, name), "set", value)
            # After publishing: the server ignores the property on a topic nobody has published.
            _call(self._topic(kind, name), "setRetained", True)

    def set_environment(self, mode=None, apriltags=None, space_forward=None, space_side=None,
                        speed_cap=None):
        if mode is not None:
            if mode.upper() not in C.ENVIRONMENTS:
                raise ValueError(f"environment must be one of {', '.join(C.ENVIRONMENTS)}")
            self.put_retained("str", C.ENV_MODE, mode.upper())
        if apriltags is not None:
            self.put_retained("bool", C.ENV_APRILTAGS, bool(apriltags))
        if space_forward is not None:
            self.put_retained("double", C.ENV_SPACE_FORWARD, float(space_forward))
        if space_side is not None:
            self.put_retained("double", C.ENV_SPACE_SIDE, float(space_side))
        if speed_cap is not None:
            self.put_retained("double", C.ENV_SPEED_CAP, float(speed_cap))
        self.flush()

    def environment(self):
        return {
            "active": self.get("str", C.ENV_ACTIVE) or "UNSET",
            "requested": self.get("str", C.ENV_MODE) or "UNSET",
            "apriltags": self.get("bool", C.ENV_APRILTAGS),
            "vision_available": self.get("bool", C.ENV_VISION_AVAILABLE),
            "vision_in_use": self.get("bool", C.ENV_VISION_IN_USE),
            "space_forward": self.get("double", C.ENV_SPACE_FORWARD, 0.0),
            "space_side": self.get("double", C.ENV_SPACE_SIDE, 0.0),
            "speed_cap": self.get("double", C.ENV_SPEED_CAP, 1.0),
        }

    # ------------------------------------------------------------------ live telemetry
    def live(self):
        out = {k: list(self.get("double[]", t)) for k, t in C.LIVE_MODULE_ARRAYS.items()}
        out.update({
            "faults": list(self.get("str[]", C.LIVE_FAULTS)),
            "gyro": list(self.get("str[]", C.LIVE_GYRO)),
            "heading": self.get("double", C.LIVE_HEADING_DEG),
            "accel": list(self.get("double[]", C.LIVE_ACCEL)),
            "pose": list(self.get("double[]", C.LIVE_POSE)),
            "vision_pose": list(self.get("double[]", C.LIVE_VISION_POSE)),
            "vision_counts": list(self.get("double[]", C.LIVE_VISION_COUNTS)),
            "vision_last_reject": self.get("str", C.LIVE_VISION_LAST_REJECT),
            "bus": self.get("double", C.LIVE_BUS_VOLTS),
            "mode": self.get("str", C.LIVE_ROBOT_MODE) or "UNKNOWN",
            "fms": self.get("bool", C.LIVE_FMS_ATTACHED),
            "t": self.get("double", C.LIVE_TIMESTAMP),
            "motors": self.motors()["motors"],
            "can": list(self.get("double[]", C.WIRING_CAN)),
            "pdh": {"currents": list(self.get("double[]", C.AK_PDH_CURRENTS)),
                    "voltage": self.get("double", C.AK_PDH_VOLTAGE)},
            "battery": self.get("double", C.AK_BATTERY),
            "battery_id": self.get("str", C.BATTERY_ID),
            "battery_rest": self.get("double", C.BATTERY_REST_VOLTS),
            "battery_options": list(self.get("str[]", C.BATTERY_OPTIONS)),
        })
        return out

    def alerts(self):
        """The robot's WPILib Alerts showing now, every group: ``[(level, text), ...]``. A group is a
        table under /SmartDashboard whose ".type" is "Alerts", with string arrays of errors and
        warnings (infos are left out)."""
        out = []
        try:
            topics = _call(self.inst, "getTopics", "/SmartDashboard/")
        except Exception:  # noqa: BLE001 - no topics yet
            return out
        for t in topics:
            name = _call(t, "getName")
            for suffix, level in (("/errors", "error"), ("/warnings", "warning")):
                if name.endswith(suffix) and self.get("str", name[: -len(suffix)] + "/.type") == "Alerts":
                    out.extend((level, str(x)) for x in self.get("str[]", name))
        return out

    def set_battery(self, battery_id, timeout=5.0):
        """Picks which battery is in, as the dashboard's drop-down does, and waits for the robot to
        take it. The robot clears a pick that arrives in the first seconds after a client connects
        (it may be a dashboard putting back the battery from before a swap), so a pick made right
        after connecting is sent again once that window has passed. True if the robot took it."""
        bid = str(battery_id)
        start = time.time()
        resent = False
        self.put("str", C.BATTERY_SELECTED, bid)
        self.flush()
        while time.time() - start < timeout:
            if self.get("str", C.BATTERY_ID) == bid:
                return True
            if not resent and time.time() - start > 3.3:
                # Our last value is still this id; go through "" so the robot sees a change.
                self.put("str", C.BATTERY_SELECTED, "")
                self.flush()
                time.sleep(0.05)
                self.put("str", C.BATTERY_SELECTED, bid)
                self.flush()
                resent = True
            time.sleep(0.05)
        return False

    def sightings(self):
        """The tags in each camera's newest frame, as dicts (see ``camcal``)."""
        flat = list(self.get("double[]", C.LIVE_VISION_SIGHTINGS))
        cams = list(self.get("str[]", C.LIVE_VISION_SIGHTING_CAMERAS))
        out = []
        for i in range(len(flat) // 10):
            v = flat[10 * i:10 * i + 10]
            out.append({"camera": cams[i] if i < len(cams) else "", "tag": int(v[0]), "x": v[1], "y": v[2],
                        "z": v[3], "qw": v[4], "qx": v[5], "qy": v[6], "qz": v[7], "ambiguity": v[8],
                        "t": v[9]})
        return out

    def status(self):
        return {
            "seq": self.get("int", C.STATUS_SEQ),
            "test": self.get("str", C.STATUS_TEST),
            "state": self.get("str", C.STATUS_STATE) or "IDLE",
            "message": self.get("str", C.STATUS_MESSAGE),
            "progress": self.get("double", C.STATUS_PROGRESS, 0.0),
            "deadman_held": self.get("bool", C.STATUS_DEADMAN_HELD),
        }

    # ------------------------------------------------------------------ tests
    def _send(self, test, module="ALL", args=None):
        args = dict(args or {})
        keys = [str(k) for k in args]
        values = [float(args[k]) for k in args]
        seq = int(time.time() * 1000) % (2 ** 52)
        self.put("str[]", C.CMD_ARG_KEYS, keys)
        self.put("double[]", C.CMD_ARG_VALUES, values)
        self.put("str", C.CMD_TEST, test)
        self.put("str", C.CMD_MODULE, module or "ALL")
        self.put("int", C.CMD_BOOT_ID, self.get("int", C.BOOT_ID))
        self.flush()
        time.sleep(0.05)  # let the arguments land before the sequence number that triggers them
        self.put("int", C.CMD_SEQ, seq)
        self.flush()
        return seq

    def _wait_ack(self, seq, timeout=3.0):
        end = time.time() + timeout
        while time.time() < end:
            if self.get("int", C.ACK_SEQ) == seq:
                return self.get("bool", C.ACK_ACCEPTED), self.get("str", C.ACK_MESSAGE)
            time.sleep(0.02)
        return False, "No answer from the robot. Is robot code running with SwerveTune installed?"

    def run_test(self, test, module="ALL", args=None, timeout=None, on_status=None):
        """Runs one test and blocks until its data is back.

        ``on_status`` is called with each status dict while waiting, which is how the GUI shows
        "hold the deadman" and progress, and how the CLI prints them.
        """
        self.start_heartbeat()
        self.wait_heartbeat_established()
        env = self.environment()["active"]
        seq = self._send(test, module, args)
        accepted, msg = self._wait_ack(seq)
        result = TestResult(test=test, module=module or "ALL", args=dict(args or {}),
                            accepted=accepted, message=msg, seq=seq, robot=self.robot_info(),
                            env=env, battery=self.get("str", C.BATTERY_ID))
        if not accepted:
            return result
        deadline = time.time() + (timeout or 180)
        last = None
        while time.time() < deadline:
            st = self.status()
            if st["seq"] == seq:
                if on_status and st != last:
                    on_status(st)
                last = st
                if st["state"] in ("DONE", "ABORTED"):
                    result.message = st["message"]
                    result.outcome = st["state"]
                    break
            time.sleep(0.05)
        else:
            self.abort()
            result.outcome = "ABORTED"
            result.message = "Timed out waiting for the robot; abort sent."
            return result
        # Results follow the status; wait for the data to land.
        end = time.time() + 5
        while time.time() < end and self.get("int", C.RESULT_SEQ) != seq:
            time.sleep(0.05)
        if self.get("int", C.RESULT_SEQ) != seq:
            result.notes.append("The robot ended before any data was recorded.")
            return result
        time.sleep(0.15)
        names = list(self.get("str[]", C.RESULT_CHANNELS))
        result.channels = {n: list(self.get("double[]", C.RESULT_DATA + n)) for n in names}
        keys = list(self.get("str[]", C.RESULT_META_KEYS))
        vals = list(self.get("double[]", C.RESULT_META_VALUES))
        result.meta = dict(zip(keys, vals))
        result.notes = list(self.get("str[]", C.RESULT_NOTES))
        result.outcome = self.get("str", C.RESULT_OUTCOME) or result.outcome
        lengths = {len(v) for v in result.channels.values()}
        if len(lengths) > 1:
            result.notes.append("Channels arrived with different lengths; trimmed to the shortest.")
            n = min(lengths)
            result.channels = {k: v[:n] for k, v in result.channels.items()}
        return result

    def abort(self):
        self.put("int", C.CLIENT_ABORT_SEQ, int(time.time() * 1000) % (2 ** 52))
        self.flush()

    def stop(self):
        seq = self._send("stop")
        return self._wait_ack(seq)

    # ------------------------------------------------------------------ gains
    def gains(self):
        """Every gain the robot is actually running, from its echo."""
        out = {}
        for key in list(C.GAIN_SPECS) + self._ff_keys() + self._pod_keys():
            out[key] = self.get("double", C.GAINS_APPLIED + key)
        return out

    def _pod_keys(self):
        return [C.pod_key(m, loop, k) for m in self.get("str[]", C.MODULE_NAMES) for loop in C.POD_LOOPS for k in C.PID_KEYS]

    def _ff_keys(self):
        return [f"FF/{m}/{k}" for m in self.get("str[]", C.MODULE_NAMES) for k in C.FF_SPECS]

    def set_gains(self, values, timeout=3.0, reason=""):
        """Applies several gains together. Returns (status text, gains now running). ``reason`` (a
        short sentence) goes into the robot's match log with the change."""
        self.put("str", C.GAINS_REASON, str(reason or "")[:200])
        for key, value in values.items():
            self.put("double", C.GAINS + key, float(value))
        self.put("int", C.GAINS_BOOT_ID, self.get("int", C.BOOT_ID))
        self.flush()
        time.sleep(0.05)
        seq = int(time.time() * 1000) % (2 ** 52)
        self.put("int", C.GAINS_APPLY_SEQ, seq)
        self.flush()
        end = time.time() + timeout
        while time.time() < end:
            if self.get("int", C.GAINS_APPLIED_SEQ) == seq:
                time.sleep(0.1)
                return self.get("str", C.GAINS_APPLY_STATUS), self.gains()
            time.sleep(0.02)
        return "No answer from the robot about the gain change.", self.gains()

    # ------------------------------------------------------------------ systems
    def systems(self):
        """Every mechanism the robot code registered (TunableSystem), with its live state, limits
        and gains: ``[{"index", "name", "kind", "units", "motors", "position", "velocity", "goal",
        "min", "max", "max_velocity", "max_accel", "limits_from", "gains": {name: {value, min, max}}}]``."""
        names = list(self.get("str[]", C.SYSTEMS_NAMES))
        col = lambda t: list(self.get("str[]", t))
        num = lambda t: list(self.get("double[]", t))
        kinds, units, motors, frm = col(C.SYSTEMS_KINDS), col(C.SYSTEMS_UNITS), col(C.SYSTEMS_MOTORS), col(C.SYSTEMS_LIMITS_FROM)
        pos, vel, goal, lim = num(C.SYSTEMS_POSITION), num(C.SYSTEMS_VELOCITY), num(C.SYSTEMS_GOAL), num(C.SYSTEMS_LIMITS)
        at = lambda xs, i, d=None: xs[i] if i < len(xs) else d
        gains = {}
        for entry in col(C.SYSTEMS_GAIN_NAMES):
            key, _, rng = entry.partition("|")
            lo, _, hi = rng.partition("|")
            sysname, _, g = key.partition("/")
            gains.setdefault(sysname, {})[g] = {"value": self.get("double", C.SYSTEMS_GAINS_APPLIED + key),
                                                "min": float(lo or "nan"), "max": float(hi or "nan")}
        out = []
        for i, n in enumerate(names):
            out.append({"index": i, "name": n, "kind": at(kinds, i, ""), "units": at(units, i, ""),
                        "motors": [m for m in (at(motors, i, "") or "").split(",") if m],
                        "position": at(pos, i), "velocity": at(vel, i), "goal": at(goal, i),
                        "min": at(lim, 4 * i), "max": at(lim, 4 * i + 1), "max_velocity": at(lim, 4 * i + 2),
                        "max_accel": at(lim, 4 * i + 3), "limits_from": at(frm, i, ""), "gains": gains.get(n, {})})
        return out

    def set_system_gains(self, values, timeout=3.0):
        """Applies systems' gains together, ``{"Shooter/kV": 0.002}``. Returns the robot's sentence."""
        for key, value in values.items():
            self.put("double", C.SYSTEMS_GAINS + key, float(value))
        self.put("int", C.SYSTEMS_APPLY_BOOT_ID, self.get("int", C.BOOT_ID))
        self.flush()
        time.sleep(0.05)
        seq = int(time.time() * 1000) % (2 ** 52)
        self.put("int", C.SYSTEMS_APPLY_SEQ, seq)
        self.flush()
        end = time.time() + timeout
        while time.time() < end:
            if self.get("int", C.SYSTEMS_APPLIED_SEQ) == seq:
                time.sleep(0.1)
                return self.get("str", C.SYSTEMS_APPLY_STATUS)
            time.sleep(0.02)
        return "No answer from the robot about the gain change."

    # ------------------------------------------------------------------ motor guard
    def motors(self):
        """Every watched motor as a dict, with the guard's startup report and recent events."""
        cols = {k: list(self.get("str[]", t)) for k, t in C.MOTOR_STRINGS.items()}
        cols.update({k: list(self.get("double[]", t)) for k, t in C.MOTOR_NUMBERS.items()})
        rows = [{k: (v[i] if i < len(v) else None) for k, v in cols.items()}
                for i in range(len(cols["name"]))]
        return {
            "guard_on": bool(self.get("bool", C.MOTORS_GUARD_ON, True)),
            "motors": rows,
            "report": list(self.get("str[]", C.MOTORS_REPORT)),
            "events": list(self.get("str[]", C.MOTORS_EVENTS)),
        }

    def override_motors(self, name="ALL", seconds=C.MAX_OVERRIDE_S, timeout=3.0):
        """Holds heat shutoffs at half current for a while (0 cancels). Returns the robot's answer."""
        self.put("str", C.MOTORS_OVERRIDE_NAME, name)
        self.put("double", C.MOTORS_OVERRIDE_SECONDS, float(seconds))
        self.put("int", C.MOTORS_OVERRIDE_BOOT_ID, self.get("int", C.BOOT_ID))
        self.flush()
        time.sleep(0.05)
        seq = int(time.time() * 1000) % (2 ** 52)
        self.put("int", C.MOTORS_OVERRIDE_SEQ, seq)
        self.flush()
        end = time.time() + timeout
        while time.time() < end:
            if self.get("int", C.MOTORS_OVERRIDE_ACK_SEQ) == seq:
                return self.get("str", C.MOTORS_OVERRIDE_ACK_MESSAGE)
            time.sleep(0.02)
        return "No answer from the robot about the override."

    # ------------------------------------------------------------------ simulation
    def sim_enable(self, on):
        self.put("bool", C.SIM_REQUEST_ENABLE, bool(on))
        self.flush()
