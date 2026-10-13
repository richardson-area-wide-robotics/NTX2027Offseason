"""The drive team's controllers: drift, deadband, reach, triggers and buttons, checked in the pit.

The browser reads a controller plugged into this laptop (the Gamepad API, the same XInput device
the Driver Station reads), so this needs no robot. A student follows the Controllers tab's steps;
the samples come here, and each step gets judged:

* **Hands off** - where each stick rests and how much it wanders. A worn stick rests off center
  ("stick drift"). If it rests outside the robot code's deadband, the robot creeps on its own.
* **Circle the sticks** - does each reach full deflection all the way round? A stick that tops out
  at 0.9 never asks for full speed.
* **Flick and let go** - does the spring bring it back to center, every time? A stick that
  settles somewhere different each time needs a bigger deadband than its resting offset suggests.
* **Triggers** - rest at 0, reach 1.
* **Every button** - each press seen once. A worn switch "bounces": one press shows up as two
  or more, which the robot sees as a double-tap.

Samples are rows ``[t_ms, a0, a1, a2, a3, b0 ... b16]`` in the browser's standard layout (axes 0-3
are the sticks; buttons 6 and 7 are the analog triggers; 12-15 the D-pad). Only rows where the
controller reported new data are sent, so the gaps between rows are its real update interval.

An Xbox controller has no gyro, and neither the Driver Station nor the browser reads the gyro in a
PlayStation controller, so "drift" here is stick drift.
"""

from __future__ import annotations

import math
import re

from . import analysis as A

STICKS = {"left": (0, 1), "right": (2, 3)}
AXIS_NAMES = ["Left stick X", "Left stick Y", "Right stick X", "Right stick Y"]
# The browser's standard layout to WPILib's XboxController numbering.
WPILIB_AXIS = {0: 0, 1: 1, 2: 4, 3: 5}
BUTTON_NAMES = ["A", "B", "X", "Y", "Left bumper", "Right bumper", "Left trigger", "Right trigger",
                "Back", "Start", "Left stick press", "Right stick press", "D-pad up", "D-pad down",
                "D-pad left", "D-pad right"]
WPILIB_BUTTON = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 8: 7, 9: 8, 10: 9, 11: 10}
TRIGGERS = {6: ("Left trigger", 2), 7: ("Right trigger", 3)}
DIGITAL = [b for b in range(16) if b not in TRIGGERS]

PRESSED = 0.5
BOUNCE_MS = 30.0          # a press or release shorter than this is a bounce, not a person
FULL_REACH = 0.97         # a stick that reaches this everywhere asks for full speed
MIN_DEADBAND = 0.03


# A WPILib XboxController's numbering, as the robot records it, to the browser's layout above.
_FROM_WPILIB_BUTTON = {w: b for b, w in WPILIB_BUTTON.items()}
_POV_BUTTONS = {12: (315, 0, 45), 13: (135, 180, 225), 14: (225, 270, 315), 15: (45, 90, 135)}


def rows_from_robot(channels):
    """A robot ``controller`` recording (WPILib numbering, a button bitmask, the POV angle) as rows
    in the browser's layout, so the same checks judge both."""
    t = channels.get("t") or []
    a = [channels.get(f"a{i}") or [] for i in range(6)]
    b = channels.get("buttons") or []
    pov = channels.get("pov") or []
    out = []
    for k, tt in enumerate(t):
        ax = [a[i][k] if k < len(a[i]) and A.finite(a[i][k]) else 0.0 for i in range(6)]
        mask = int(b[k]) if k < len(b) and A.finite(b[k]) else 0
        p = int(pov[k]) if k < len(pov) and A.finite(pov[k]) else -1
        buttons = [0.0] * 16
        for w, idx in _FROM_WPILIB_BUTTON.items():
            buttons[idx] = 1.0 if mask & (1 << (w - 1)) else 0.0
        buttons[6], buttons[7] = ax[2], ax[3]
        for idx, angles in _POV_BUTTONS.items():
            buttons[idx] = 1.0 if p in angles else 0.0
        out.append([tt * 1000.0, ax[0], ax[1], ax[4], ax[5], *buttons])
    return out


def _rows(samples):
    return [r for r in samples or [] if isinstance(r, (list, tuple)) and len(r) >= 5]


def update_interval_ms(samples):
    """How often the controller reported new data: the median gap between rows."""
    t = [r[0] for r in _rows(samples)]
    gaps = [b - a for a, b in zip(t, t[1:]) if b > a]
    return A.median(gaps) if gaps else float("nan")


def recommend_deadband(worst):
    """A deadband with a margin over the worst resting or returning offset, in 0.01 steps."""
    return max(MIN_DEADBAND, math.ceil((worst + 0.02) * 100 - 1e-9) / 100)


# ---------------------------------------------------------------------------- the code's deadband
def code_deadbands(project):
    """``[{"value", "file", "line"}]``: every ``MathUtil.applyDeadband(x, 0.1)`` in the robot code."""
    out = []
    for name, src in (project.java or {}).items():
        for m in re.finditer(r"applyDeadband\([^;]*?,\s*([0-9.]+)\s*\)", src):
            out.append({"value": float(m.group(1)), "file": name.replace("\\", "/").split("/")[-1],
                        "line": src.count("\n", 0, m.start()) + 1})
    return out


# ---------------------------------------------------------------------------- steps
def rest(samples):
    """Hands off: where each stick axis sits and how much it wanders."""
    rows = _rows(samples)
    out = {"axes": [], "findings": []}
    if len(rows) < 10:
        out["findings"].append({"level": "warn", "title": "Too little data", "why": "Hold still for the whole count."})
        return out
    for a in range(4):
        v = [r[1 + a] for r in rows]
        mean = sum(v) / len(v)
        sd = math.sqrt(sum((x - mean) ** 2 for x in v) / len(v))
        out["axes"].append({"axis": a, "name": AXIS_NAMES[a], "wpilib_axis": WPILIB_AXIS[a], "offset": mean,
                            "noise": sd, "max_abs": max(abs(x) for x in v)})
    worst = max(x["max_abs"] for x in out["axes"])
    out["worst"] = worst
    out["recommended_deadband"] = recommend_deadband(worst)
    pressed = [BUTTON_NAMES[b] for b in range(16) if len(rows[0]) > 5 + b
               and sum(1 for r in rows if r[5 + b] >= PRESSED) > len(rows) / 2]
    out["stuck"] = pressed
    if pressed:
        out["findings"].append({"level": "error", "title": f"Pressed with nobody touching it: {', '.join(pressed)}",
                                "why": "A stuck button or trigger: the robot sees it held. Clean or replace the controller."})
    return out


def sticks(samples):
    """Circle each stick round its edge: how far it reaches in every direction."""
    rows = _rows(samples)
    out = {"sticks": {}, "findings": []}
    for name, (ax, ay) in STICKS.items():
        sectors = [0.0] * 16
        for r in rows:
            x, y = r[1 + ax], r[1 + ay]
            rad = math.hypot(x, y)
            if rad < 0.3:
                continue
            s = int(((math.atan2(-y, x) + 2 * math.pi) % (2 * math.pi)) / (2 * math.pi) * 16) % 16
            sectors[s] = max(sectors[s], min(rad, 1.5))
        covered = sum(1 for s in sectors if s > 0.5)
        reach = min(sectors) if covered == 16 else float("nan")
        out["sticks"][name] = {"sectors": sectors, "covered": covered, "reach": reach,
                               "x_range": _range(rows, ax), "y_range": _range(rows, ay)}
        label = name.capitalize() + " stick"
        if covered < 16:
            out["findings"].append({"level": "warn", "title": f"{label}: not circled all the way round",
                                    "why": "Roll it slowly round the edge, pressing outward, two or three times."})
        elif reach < FULL_REACH:
            worst = min(range(16), key=lambda i: sectors[i])
            out["findings"].append({
                "level": "warn", "title": f"{label} only reaches {reach:.2f} toward {_direction(worst)}",
                "why": "Full speed needs 1.0. Worn sticks stop short: the robot never asks for full speed that "
                       "way. Swap the controller, or scale the stick in the code."})
        else:
            out["findings"].append({"level": "info", "title": f"{label} reaches full deflection all round",
                                    "why": f"At least {reach:.2f} in every direction."})
    return out


def returns(samples):
    """Flick each stick and let go: where the spring leaves it each time."""
    rows = _rows(samples)
    out = {"sticks": {}, "findings": []}
    for name, (ax, ay) in STICKS.items():
        settles, moving, quiet_since = [], False, None
        for k, r in enumerate(rows):
            rad = math.hypot(r[1 + ax], r[1 + ay])
            if rad > 0.6:
                moving, quiet_since = True, None
            elif moving and rad < 0.3:
                quiet_since = quiet_since if quiet_since is not None else r[0]
                if r[0] - quiet_since >= 300:
                    # Settled: average the next 100 ms.
                    win = [q for q in rows[k:] if q[0] - r[0] <= 100]
                    settles.append((sum(q[1 + ax] for q in win) / len(win), sum(q[1 + ay] for q in win) / len(win)))
                    moving, quiet_since = False, None
        worst = max((math.hypot(x, y) for x, y in settles), default=float("nan"))
        out["sticks"][name] = {"settles": settles, "worst": worst}
        label = name.capitalize() + " stick"
        if len(settles) < 3:
            out["findings"].append({"level": "warn", "title": f"{label}: fewer than 3 flicks seen",
                                    "why": "Push it all the way, let go, wait a moment; five times."})
        elif worst > 0.06:
            out["findings"].append({"level": "warn", "title": f"{label} comes back up to {worst:.2f} off center",
                                    "why": "The spring doesn't center it reliably: the deadband has to cover the worst "
                                           "return, not just where it rested."})
    finite = [s["worst"] for s in out["sticks"].values() if A.finite(s["worst"])]
    out["worst"] = max(finite) if finite else float("nan")
    return out


def triggers(samples):
    """Squeeze both triggers fully a few times."""
    rows = _rows(samples)
    out = {"triggers": {}, "findings": []}
    for b, (name, wpi) in TRIGGERS.items():
        v = [r[5 + b] for r in rows if len(r) > 5 + b]
        if not v:
            continue
        lo, hi = min(v), max(v)
        out["triggers"][name] = {"min": lo, "max": hi, "wpilib_axis": wpi}
        if hi < FULL_REACH:
            out["findings"].append({"level": "warn", "title": f"{name} only reaches {hi:.2f}",
                                    "why": "Squeeze it all the way. If it still stops short, anything the code ties "
                                           "to a full squeeze will never happen."})
        if lo > 0.05:
            out["findings"].append({"level": "warn", "title": f"{name} never goes back below {lo:.2f}",
                                    "why": "It doesn't release fully: the robot sees it partly squeezed."})
    return out


def buttons(samples):
    """Press every button a few times: each press should be seen exactly once."""
    rows = _rows(samples)
    out = {"buttons": {}, "findings": []}
    bounced = []
    for b in DIGITAL:
        if not rows or len(rows[0]) <= 5 + b:
            continue
        state = rows[0][5 + b] >= PRESSED
        changes = [(rows[0][0], state)]
        for r in rows[1:]:
            s = r[5 + b] >= PRESSED
            if s != state:
                changes.append((r[0], s))
                state = s
        presses = sum(1 for _, s in changes[1:] if s)
        # A press or a release that lasted less than BOUNCE_MS is the switch bouncing, not a person.
        short = sum(1 for (t0, _), (t1, _) in zip(changes[1:], changes[2:]) if t1 - t0 < BOUNCE_MS)
        out["buttons"][BUTTON_NAMES[b]] = {"presses": presses, "bounces": short, "wpilib": WPILIB_BUTTON.get(b)}
        if short:
            bounced.append(f"{BUTTON_NAMES[b]} ({short}x)")
    missing = [n for n, x in out["buttons"].items() if x["presses"] == 0]
    if bounced:
        out["findings"].append({"level": "error", "title": f"Bouncing: {', '.join(bounced)}",
                                "why": f"A single press showed up as more than one (gaps under {BOUNCE_MS:.0f} ms). "
                                       "The robot sees a double-tap: a toggle flips twice. Replace the controller."})
    if missing:
        out["findings"].append({"level": "warn", "title": f"Never pressed: {', '.join(missing)}",
                                "why": "Press each of them a few times, or it may be dead."})
    return out


def report(steps, code_db=None):
    """The whole check: a recommended deadband against the code's, and every step's findings."""
    F = []
    worst_rest = (steps.get("rest") or {}).get("worst")
    worst_return = (steps.get("returns") or {}).get("worst")
    worst = max([w for w in (worst_rest, worst_return) if A.finite(w)], default=float("nan"))
    rec = recommend_deadband(worst) if A.finite(worst) else None
    code = [d["value"] for d in code_db or []]
    if rec is not None and code:
        cur = min(code)
        where = ", ".join(sorted({d["file"] for d in code_db}))
        if worst >= cur:
            F.append({"level": "error",
                      "title": f"This controller drifts {worst:.2f}, past the code's {cur:g} deadband",
                      "why": f"The robot will creep with nobody touching the sticks. Use another controller, or "
                             f"raise the deadband in {where} to {rec:.2f}.", "learn": "deadband"})
        elif rec > cur:
            F.append({"level": "warn", "title": f"Drift {worst:.2f} is close to the code's {cur:g} deadband",
                      "why": f"No creep today, but there is little margin; {rec:.2f} would be safe. Worn sticks get "
                             "worse.", "learn": "deadband"})
        else:
            F.append({"level": "info", "title": f"Drift {worst:.2f}: well inside the code's {cur:g} deadband",
                      "why": f"{rec:.2f} would be enough for this controller; a smaller deadband means finer "
                             "control near center.", "learn": "deadband"})
    for name in ("rest", "sticks", "returns", "triggers", "buttons"):
        F.extend((steps.get(name) or {}).get("findings") or [])
    level = "error" if any(f["level"] == "error" for f in F) else "warn" if any(f["level"] == "warn" for f in F) else "ok"
    return {"recommended_deadband": rec, "worst_offset": worst, "code_deadbands": code_db or [],
            "verdict": level, "findings": F}


def _range(rows, axis):
    v = [r[1 + axis] for r in rows]
    return (min(v), max(v)) if v else (float("nan"), float("nan"))


def _direction(sector):
    names = ["right", "up-right", "up", "up-left", "left", "down-left", "down", "down-right"]
    return names[round((sector + 0.5) / 2) % 8]  # the 22.5° sector's center, to the nearest 45°
