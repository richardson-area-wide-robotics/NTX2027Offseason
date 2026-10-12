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
}


class Monitor:
    def __init__(self, drive_current_limit=40.0, clock=time.monotonic):
        self.limit = drive_current_limit
        self.clock = clock
        self._since = {}       # (rule, module) -> time the condition started
        self._active = {}      # (rule, module) -> flag dict
        self._last_clear = {}  # (rule, module) -> time the condition stopped
        self._err_hist = {}    # module -> recent (time, steering error) samples

    def _raise(self, rule, module, now, hold, detail, active):
        key = (rule, module)
        if active:
            self._last_clear.pop(key, None)
            start = self._since.setdefault(key, now)
            if now - start >= hold and key not in self._active:
                symptom, text = RULES[rule]
                who = f"Module {module}" if module is not None else "The robot"
                self._active[key] = {"rule": rule, "module": module, "symptom": symptom,
                                     "text": f"{who}: {text}.", "detail": detail, "since": start}
            elif key in self._active:
                self._active[key]["detail"] = detail
        else:
            self._since.pop(key, None)
            if key in self._active:
                stop = self._last_clear.setdefault(key, now)
                if now - stop >= 1.0:
                    self._active.pop(key, None)
                    self._last_clear.pop(key, None)

    def update(self, live, names=None):
        """Feeds one snapshot. Returns the flags currently raised."""
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
            hot = max(x for x in (dtemp[i], stemp[i], 0) if A.finite(x)) > 70
            self._raise("hot", name, now, 2.0, f"{max(dtemp[i], stemp[i]):.0f} °C", hot)
            f = faults[i] if i < len(faults) else ""
            self._raise("faults", name, now, 0.0, f, bool(f))
        bus = live.get("bus")
        self._raise("low_battery", None, now, 0.25, f"{bus:.1f} V" if A.finite(bus) else "",
                    enabled and A.finite(bus) and bus < 8.0)
        return self.flags()

    def flags(self):
        return sorted(self._active.values(), key=lambda f: (f["since"], f["rule"]))
