"""Watches live telemetry and raises the problems a mentor would spot by eye.

Fed one snapshot of :meth:`link.RobotLink.live` per robot loop (or as often as the GUI polls).
Each rule needs its condition to hold for a while before it fires, so one noisy sample never
raises a flag, and a flag clears itself once the condition has been gone for a second.

Every flag names a rule, a module (or ``None`` for the chassis), a sentence for a student, and the
troubleshooter symptom that explains it. The rule names are the ``monitor`` evidence the
troubleshooter checks for (see :mod:`diagnose`).

The robot runs most of these rules itself, every loop, matches included, with the same thresholds,
hold times and words (``ModuleWatch.java``); see :data:`ON_ROBOT`. When its snapshot carries the
robot's flags, the laptop shows those for those rules and judges only the rest, so no rule is
reported twice.
"""

from __future__ import annotations

import time

from . import analysis as A
from . import units as U

RULES = {
    "steer_not_reaching": ("pod_wrong_direction",
                           "is more than 10° from where it is told to point"),
    "steer_oscillation": ("pod_oscillates", "is swinging back and forth around its angle"),
    "motor_vs_absolute": ("pod_drifts",
                          "steering motor encoder disagrees with the absolute encoder"),
    "absolute_read_issue": ("pod_oscillates", "absolute encoder is not being read reliably"),
    "drive_backwards": ("wheel_backwards", "wheel is turning opposite to its command"),
    "drive_lagging": ("robot_slow", "wheel is well short of its commanded speed"),
    "stall": ("wheel_slip", "drive motor is at high current with the wheel barely turning"),
    "hot": ("brownout", "motor is over 70 °C"),
    "faults": ("pod_not_moving", "motor controller reports a fault"),
    "low_battery": ("brownout", "battery voltage is sagging below 8 V"),
    "gyro_problem": ("field_relative_wrong", "gyro is not connected, still calibrating, or faulted"),
    "drive_ratio_mismatch": ("gear_ratio", "reports a different distance from the other modules"
                                           " while driving straight: more than worn tread explains, so"
                                           " its gear ratio may differ"),
    "motor_hot": ("motor_hot", "is hot: the motor guard has stepped in"),
    "motor_failing": ("motor_dead", "shows signs of failing: unplugged, an open phase, or a fault"),
    "motor_hotter_than_siblings": ("motor_hot", "runs much hotter than the matching motors on the"
                                                " other modules: binding, a dragging bearing or a"
                                                " failing motor"),
}

# How long each rule's condition must hold before it fires, seconds. The robot's copies use the
# same (tests/test_contract.py reads ModuleWatch.java and compares).
HOLD_S = {
    "steer_not_reaching": 0.5, "steer_oscillation": 0.3, "motor_vs_absolute": 1.0,
    "absolute_read_issue": 0.2, "drive_backwards": 0.3, "drive_lagging": 1.0, "stall": 0.4,
    "hot": 2.0, "faults": 0.0, "low_battery": 0.25, "gyro_problem": 0.5, "drive_ratio_mismatch": 0.0,
    "motor_hot": 0.0, "motor_failing": 0.0, "motor_hotter_than_siblings": 5.0,
}

# The rules the robot judges itself every loop, so they watch matches and need no laptop, and
# publishes (contract.WATCH_*). Their flags come from the robot whenever it sends them.
ON_ROBOT = frozenset(RULES) - {"motor_hot", "motor_failing"}
# These two stay on the laptop: they only put words to the motor guard's stage and flags, which the
# robot already judges every loop, logs and shows on Robot Health (MotorGuard, DashboardAlerts); a
# second robot-side copy would show each twice. Every rule also stays here for robot code from
# before ModuleWatch published its flags, so an older robot is watched as before.
LAPTOP_ONLY = frozenset(RULES) - ON_ROBOT

# The robot's names for its checks in a match log (RealOutputs/SlothTune/Watch/<who>/<name>).
ROBOT_LOG_NAMES = {
    "SteerOff": "steer_not_reaching", "SteerOscillation": "steer_oscillation",
    "SensorsDisagree": "motor_vs_absolute", "AbsoluteReadIssue": "absolute_read_issue",
    "Backwards": "drive_backwards", "DriveLagging": "drive_lagging", "Stall": "stall", "Hot": "hot",
    "Faults": "faults", "DriveRatioMismatch": "drive_ratio_mismatch", "LowBattery": "low_battery",
    "GyroProblem": "gyro_problem", "HotterThanSiblings": "motor_hotter_than_siblings",
}

# Numbers per check in contract.WATCH_VALUES: active, episodes, since (robot s), two readings.
STRIDE = 5

# One swerve motor this much hotter than the median of its siblings, C, is not the duty cycle.
SIBLING_HOT_C = 15.0

# Passive drive-ratio check: how much straight-line driving to collect before judging, meters.
RATIO_MIN_TRAVEL_M = 3.0
# Worn MAXSwerve tread is up to 1/8 in, about 4% of a 3 in wheel; one pinion tooth is about 8%.
# Between them is a wheel to measure, not a gearbox to open.
RATIO_FLAG = 0.05

NAN = float("nan")


def detail(rule, a=NAN, b=NAN):
    """A flag's one or two readings in words: the same wording whether the laptop judged it or the
    robot did. ``faults`` and ``gyro_problem`` are words already and come from the snapshot."""
    if rule == "steer_not_reaching":
        return f"{a:+.1f}°"
    if rule == "steer_oscillation":
        return f"{a:.0f} swings/s"
    if rule == "motor_vs_absolute":
        return f"{a:.1f}°"
    if rule == "drive_backwards":
        return f"{U.fps(a):+.2f} vs {U.fps(b):+.2f} ft/s"
    if rule == "drive_lagging":
        return f"{U.fps(a):.2f} of {U.fps(b):.2f} ft/s" if A.finite(a) else ""
    if rule == "stall":
        return f"{a:.0f} A"
    if rule == "hot":
        return f"{a:.0f} °C"
    if rule == "low_battery":
        return f"{a:.1f} V" if A.finite(a) else ""
    if rule == "drive_ratio_mismatch":
        return f"{(a - 1) * 100:+.1f}% over {U.inches(b):.0f} in"
    if rule == "motor_hotter_than_siblings":
        return f"{a:.0f} °C vs {b:.0f} °C"
    return ""


def sentence(rule, module):
    """The flag's sentence for a student: a module's, a motor's, or the whole robot's."""
    text = RULES[rule][1]
    if rule.startswith("motor_"):
        return f"{module} motor {text}."
    who = f"Module {module}" if module is not None else "The robot"
    return f"{who}: {text}."


def robot_checks(rules, who, values):
    """The robot's checks from its three topics: ``[{"rule", "who", "active", "count", "since", "a",
    "b"}]``, who "" for the whole robot and since in robot seconds. Read while the robot republishes
    its list, the numbers may not line up with the names: every check is then listed as quiet, so the
    laptop still leaves those rules to the robot and nothing shows twice."""
    n = len(rules)
    ok = len(who) == n and len(values) == n * STRIDE
    out = []
    for i, rule in enumerate(rules):
        v = values[i * STRIDE:(i + 1) * STRIDE] if ok else [0, 0, NAN, NAN, NAN]
        out.append({"rule": rule, "who": who[i] if ok else "", "active": v[0] == 1,
                    "count": int(v[1]) if A.finite(v[1]) else 0, "since": v[2], "a": v[3], "b": v[4]})
    return out


class Monitor:
    def __init__(self, drive_current_limit=40.0, clock=time.monotonic):
        self.limit = drive_current_limit
        self.clock = clock
        self._since = {}       # (rule, module) -> time the condition started
        self._active = {}      # (rule, module) -> flag dict
        self._last_clear = {}  # (rule, module) -> time the condition stopped
        self._err_hist = {}    # module -> recent (time, steering error) samples
        self._ratio_last = None  # (positions, heading) at the previous straight-driving sample
        self._ratio_travel = {}  # module -> meters reported while driving straight on the floor
        self._robot_rules = frozenset()  # rules the robot judges and sends: not judged here
        self._robot_flags = []  # the robot's active flags, as this monitor words them
        self._robot_words = {}  # (rule, who) -> the last fault or gyro words seen while it held

    def _raise(self, rule, module, now, detail, active):
        if rule in self._robot_rules:
            return
        key = (rule, module)
        if active:
            self._last_clear.pop(key, None)
            start = self._since.setdefault(key, now)
            if now - start >= HOLD_S[rule] and key not in self._active:
                symptom = RULES[rule][0]
                self._active[key] = {"rule": rule, "module": module, "symptom": symptom,
                                     "text": sentence(rule, module), "detail": detail, "since": start}
            elif key in self._active:
                self._active[key]["detail"] = detail
        else:
            self._since.pop(key, None)
            if key in self._active:
                stop = self._last_clear.setdefault(key, now)
                if now - stop >= 1.0:
                    self._active.pop(key, None)
                    self._last_clear.pop(key, None)

    def update(self, live, names=None, env=None):
        """Feeds one snapshot. Returns the flags currently raised.

        ``env`` is the robot's environment; the drive-ratio check only runs on the FIELD, because
        only there does the chassis make every wheel cover the same ground. ``live["watch"]`` is the
        robot's own checks (:func:`robot_checks`): the rules it sends are shown from it.
        """
        now = self.clock()
        robot = [w for w in live.get("watch") or [] if w.get("rule") in RULES]
        self._robot_rules = frozenset(w["rule"] for w in robot)
        for state in (self._since, self._active, self._last_clear):
            for key in [k for k in state if k[0] in self._robot_rules]:
                state.pop(key)
        enabled = live.get("mode") not in ("DISABLED", "ESTOP", "UNKNOWN", None)
        steer = live.get("steer") or []
        n = len(steer)
        names = names or [f"m{i}" for i in range(n)]

        def arr(key):
            v = live.get(key) or []
            return v if len(v) == n else [float("nan")] * n

        sp, motor = arr("steer_sp"), arr("steer_motor")
        v, v_sp = arr("v"), arr("v_sp")
        amps, issue = arr("drive_amps"), arr("abs_issue")
        dtemp, stemp = arr("drive_temp"), arr("steer_temp")
        faults = live.get("faults") or [""] * n
        motors = live.get("motors") or []
        guarded = bool(motors)
        for i in range(n):
            name = names[i] if i < len(names) else f"m{i}"
            moving_cmd = A.finite(v_sp[i]) and abs(v_sp[i]) > 0.1
            err = A.wrap180(sp[i] - steer[i]) if A.finite(sp[i]) and A.finite(steer[i]) else float("nan")
            self._raise("steer_not_reaching", name, now, detail("steer_not_reaching", err),
                        enabled and moving_cmd and A.finite(err) and abs(err) > 10)

            hist = self._err_hist.setdefault(name, [])
            if enabled and A.finite(err):
                hist.append((now, err))
            while hist and now - hist[0][0] > 1.0:
                hist.pop(0)
            crossings, last = 0, 0
            for _, e in hist:
                if abs(e) < 1.0:
                    continue
                s = 1 if e > 0 else -1
                if last and s != last:
                    crossings += 1
                last = s
            self._raise("steer_oscillation", name, now, detail("steer_oscillation", crossings),
                        enabled and crossings >= 4)

            gap = abs(A.wrap180(steer[i] - motor[i])) if A.finite(motor[i]) and A.finite(steer[i]) else 0
            still = not A.finite(v[i]) or abs(v[i]) < 0.05
            self._raise("motor_vs_absolute", name, now, detail("motor_vs_absolute", gap), still and gap > 3.0)
            self._raise("absolute_read_issue", name, now, "", bool(issue[i] == 1))
            backwards = (enabled and moving_cmd and A.finite(v[i]) and v[i] * v_sp[i] < 0
                         and abs(v[i]) > 0.1)
            self._raise("drive_backwards", name, now, detail("drive_backwards", v[i], v_sp[i]), backwards)
            lag = (enabled and A.finite(v[i]) and A.finite(v_sp[i]) and abs(v_sp[i]) > 0.5
                   and not backwards and abs(v[i] - v_sp[i]) / abs(v_sp[i]) > 0.3)
            self._raise("drive_lagging", name, now, detail("drive_lagging", v[i], v_sp[i]), lag)
            stall = (enabled and A.finite(amps[i]) and amps[i] > 0.85 * self.limit
                     and A.finite(v[i]) and abs(v[i]) < 0.15)
            self._raise("stall", name, now, detail("stall", amps[i]), stall)
            # With the motor guard running, its kind-aware rules below replace this one.
            hottest = max(x for x in (dtemp[i], stemp[i], 0) if A.finite(x))
            self._raise("hot", name, now, detail("hot", hottest), not guarded and hottest > 70)
            f = faults[i] if i < len(faults) else ""
            self._raise("faults", name, now, f, bool(f))
        self._passive_ratio(live, names, n, enabled and env == "FIELD", now)
        self._motor_rules(motors, now)
        gyro = live.get("gyro") or []
        bad_gyro = len(gyro) >= 4 and (gyro[1] != "connected" or gyro[2] != "ready" or bool(gyro[3]))
        gyro_words = ", ".join(x for x in gyro[:4] if x) if gyro else ""
        self._raise("gyro_problem", None, now, gyro_words, bad_gyro)
        bus = live.get("bus")
        self._raise("low_battery", None, now, detail("low_battery", bus),
                    enabled and A.finite(bus) and bus < 8.0)
        self._robot_flags = self._from_robot(robot, live, names, now)
        return self.flags()

    def _from_robot(self, robot, live, names, now):
        """The robot's active flags, worded as this monitor words its own. Its clock is not this
        one: each flag's start is placed by how long ago it was on the robot's clock."""
        t = live.get("t")
        faults, gyro = live.get("faults") or [], live.get("gyro") or []
        out = []
        for w in robot:
            rule, who = w["rule"], w["who"] or None
            key = (rule, who)
            if rule == "faults":
                i = names.index(who) if who in names else -1
                words = faults[i] if 0 <= i < len(faults) else ""
            elif rule == "gyro_problem":
                bad = len(gyro) >= 4 and (gyro[1] != "connected" or gyro[2] != "ready" or bool(gyro[3]))
                words = ", ".join(x for x in gyro[:4] if x) if bad else ""
            else:
                words = None
            if words:
                self._robot_words[key] = words
            if not w["active"]:
                self._robot_words.pop(key, None)
                continue
            text = detail(rule, w["a"], w["b"]) if words is None else self._robot_words.get(key, "")
            since = now - max(0.0, t - w["since"]) if A.finite(t) and A.finite(w["since"]) else now
            out.append({"rule": rule, "module": who, "symptom": RULES[rule][0], "text": sentence(rule, who),
                        "detail": text, "since": since, "count": w["count"], "source": "robot"})
        return out

    def _passive_ratio(self, live, names, n, on_field, now):
        pos, steer, v = live.get("pos") or [], live.get("steer") or [], live.get("v") or []
        heading = live.get("heading")
        straight = (on_field and n >= 3 and len(pos) == n and len(v) == n and A.finite(heading)
                    and all(A.finite(x) for x in pos + steer + v)
                    and max(abs(A.wrap180(a - steer[0])) for a in steer) < 3.0
                    and min(abs(x) for x in v) > 0.3)
        if straight and self._ratio_last is not None:
            last_pos, last_heading = self._ratio_last
            if abs(A.wrap180(heading - last_heading)) < 0.5:
                for i in range(n):
                    name = names[i] if i < len(names) else f"m{i}"
                    self._ratio_travel[name] = self._ratio_travel.get(name, 0.0) + abs(pos[i] - last_pos[i])
        self._ratio_last = (list(pos), heading) if straight else None
        travel = self._ratio_travel
        if len(travel) >= 3 and min(travel.values()) >= RATIO_MIN_TRAVEL_M:
            from . import ratios as R
            odd = {f["module"]: f for f in R.module_ratio_findings(travel, 1.0, threshold=RATIO_FLAG)}
            for name in travel:
                f = odd.get(name)
                self._raise("drive_ratio_mismatch", name, now,
                            detail("drive_ratio_mismatch", f["travel_ratio"], travel[name]) if f else "",
                            f is not None)

    def _motor_rules(self, motors, now):
        for m in motors:
            name = m.get("name") or "?"
            stage = m.get("stage") or "OK"
            words = f"{stage}: {m.get('cause') or ''}".rstrip(": ")
            self._raise("motor_hot", name, now, words, stage != "OK")
            self._raise("motor_failing", name, now, m.get("flags") or "", bool(m.get("flags")))
        # Swerve motors come in matched sets doing nearly the same work; one running far hotter
        # than the rest is mechanical drag or a dying motor, whatever the absolute number.
        for suffix in (" drive", " steer"):
            group = [m for m in motors if (m.get("name") or "").endswith(suffix)
                     and A.finite(m.get("temp")) and 0 < m["temp"] < 150]
            temps = sorted(m["temp"] for m in group)
            for m in group:
                others = list(temps)
                others.remove(m["temp"])
                if len(others) < 2:
                    continue
                mid = others[len(others) // 2] if len(others) % 2 else \
                    (others[len(others) // 2 - 1] + others[len(others) // 2]) / 2
                gap = m["temp"] - mid
                self._raise("motor_hotter_than_siblings", m["name"], now,
                            detail("motor_hotter_than_siblings", m["temp"], mid), gap > SIBLING_HOT_C)

    def flags(self):
        """Every flag raised now, the laptop's own and the robot's, oldest first."""
        return sorted(list(self._active.values()) + self._robot_flags, key=lambda f: (f["since"], f["rule"]))
