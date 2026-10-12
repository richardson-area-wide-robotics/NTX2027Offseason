"""Watches live telemetry and raises the problems a mentor would spot by eye.

Fed one snapshot of :meth:`link.RobotLink.live` per robot loop (or as often as the GUI polls).
Each rule needs its condition to hold for a while before it fires, so one noisy sample never
raises a flag, and a flag clears itself once the condition has been gone for a second.

Every flag names a rule, a module (or ``None`` for the chassis), a sentence for a student, and the
troubleshooter symptom that explains it. The rule names are the ``monitor`` evidence the
troubleshooter checks for (see :mod:`diagnose`).
"""

from __future__ import annotations

import time

from . import analysis as A

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
                                           " while driving straight - its gear ratio may differ"),
    "motor_hot": ("motor_hot", "is hot: the motor guard has stepped in"),
    "motor_failing": ("motor_dead", "shows signs of failing: unplugged, an open phase, or a fault"),
    "motor_hotter_than_siblings": ("motor_hot", "runs much hotter than the matching motors on the"
                                                " other modules: binding, a dragging bearing or a"
                                                " failing motor"),
}

# One swerve motor this much hotter than the median of its siblings, C, is not the duty cycle.
SIBLING_HOT_C = 15.0

# Passive drive-ratio check: how much straight-line driving to collect before judging, metres.
RATIO_MIN_TRAVEL_M = 3.0


class Monitor:
    def __init__(self, drive_current_limit=40.0, clock=time.monotonic):
        self.limit = drive_current_limit
        self.clock = clock
        self._since = {}       # (rule, module) -> time the condition started
        self._active = {}      # (rule, module) -> flag dict
        self._last_clear = {}  # (rule, module) -> time the condition stopped
        self._err_hist = {}    # module -> recent (time, steering error) samples
        self._ratio_last = None  # (positions, heading) at the previous straight-driving sample
        self._ratio_travel = {}  # module -> metres reported while driving straight on the floor

    def _raise(self, rule, module, now, hold, detail, active):
        key = (rule, module)
        if active:
            self._last_clear.pop(key, None)
            start = self._since.setdefault(key, now)
            if now - start >= hold and key not in self._active:
                symptom, text = RULES[rule]
                who = f"Module {module}" if module is not None else "The robot"
                sentence = f"{module} motor {text}." if rule.startswith("motor_") else f"{who}: {text}."
                self._active[key] = {"rule": rule, "module": module, "symptom": symptom,
                                     "text": sentence, "detail": detail, "since": start}
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
        only there does the chassis make every wheel cover the same ground.
        """
        now = self.clock()
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
            self._raise("steer_not_reaching", name, now, 0.5, f"{err:+.1f}°",
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
            self._raise("steer_oscillation", name, now, 0.3, f"{crossings} swings/s",
                        enabled and crossings >= 4)

            gap = abs(A.wrap180(steer[i] - motor[i])) if A.finite(motor[i]) and A.finite(steer[i]) else 0
            still = not A.finite(v[i]) or abs(v[i]) < 0.05
            self._raise("motor_vs_absolute", name, now, 1.0, f"{gap:.1f}°", still and gap > 3.0)
            self._raise("absolute_read_issue", name, now, 0.2, "", bool(issue[i] == 1))
            backwards = (enabled and moving_cmd and A.finite(v[i]) and v[i] * v_sp[i] < 0
                         and abs(v[i]) > 0.1)
            self._raise("drive_backwards", name, now, 0.3, f"{v[i]:+.2f} vs {v_sp[i]:+.2f} m/s",
                        backwards)
            lag = (enabled and A.finite(v[i]) and A.finite(v_sp[i]) and abs(v_sp[i]) > 0.5
                   and not backwards and abs(v[i] - v_sp[i]) / abs(v_sp[i]) > 0.3)
            self._raise("drive_lagging", name, now, 1.0,
                        f"{v[i]:.2f} of {v_sp[i]:.2f} m/s" if A.finite(v[i]) else "", lag)
            stall = (enabled and A.finite(amps[i]) and amps[i] > 0.85 * self.limit
                     and A.finite(v[i]) and abs(v[i]) < 0.15)
            self._raise("stall", name, now, 0.4, f"{amps[i]:.0f} A", stall)
            # With the motor guard running, its kind-aware rules below replace this one.
            hot = not guarded and max(x for x in (dtemp[i], stemp[i], 0) if A.finite(x)) > 70
            self._raise("hot", name, now, 2.0, f"{max(dtemp[i], stemp[i]):.0f} °C", hot)
            f = faults[i] if i < len(faults) else ""
            self._raise("faults", name, now, 0.0, f, bool(f))
        self._passive_ratio(live, names, n, enabled and env == "FIELD", now)
        self._motor_rules(motors, now)
        gyro = live.get("gyro") or []
        bad_gyro = len(gyro) >= 4 and (gyro[1] != "connected" or gyro[2] != "ready" or bool(gyro[3]))
        detail = ", ".join(x for x in gyro[:4] if x) if gyro else ""
        self._raise("gyro_problem", None, now, 0.5, detail, bad_gyro)
        bus = live.get("bus")
        self._raise("low_battery", None, now, 0.25, f"{bus:.1f} V" if A.finite(bus) else "",
                    enabled and A.finite(bus) and bus < 8.0)
        return self.flags()

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
            odd = {f["module"]: f for f in R.module_ratio_findings(travel, 1.0)}
            for name in travel:
                f = odd.get(name)
                self._raise("drive_ratio_mismatch", name, now, 0.0,
                            f"{(f['travel_ratio'] - 1) * 100:+.1f}% over {travel[name]:.1f} m" if f else "",
                            f is not None)

    def _motor_rules(self, motors, now):
        for m in motors:
            name = m.get("name") or "?"
            stage = m.get("stage") or "OK"
            detail = f"{stage}: {m.get('cause') or ''}".rstrip(": ")
            self._raise("motor_hot", name, now, 0.0, detail, stage != "OK")
            self._raise("motor_failing", name, now, 0.0, m.get("flags") or "", bool(m.get("flags")))
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
                self._raise("motor_hotter_than_siblings", m["name"], now, 5.0,
                            f"{m['temp']:.0f} °C vs {mid:.0f} °C", gap > SIBLING_HOT_C)

    def flags(self):
        return sorted(self._active.values(), key=lambda f: (f["since"], f["rule"]))
