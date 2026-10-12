"""Where each swerve module really is, and how big each wheel really is.

Odometry multiplies every wheel turn by the configured wheel size, and every turn of the robot by
the configured module positions. Both are measured by hand once and then wear: tread compresses,
a frame gets rebuilt. Three tools, each for what it can actually measure:

* **A tape measure, for module positions.** Wheelbase (front axle to back axle) and track width
  (left wheel center to right wheel center) become YAGSL's ``location`` numbers. Driving cannot
  measure one module's position: the drive velocity loop makes every wheel report the speed it was
  asked for, so a misplaced module scrubs instead of showing up in the numbers.
* **A push in coast, for wheel sizes.** With the robot disabled and the motors coasting, push it in
  a straight line along a measured tape distance. Every wheel rolls freely over the same ground, so
  each wheel's encoder distance against the tape is that wheel's real size. A worn tread reads long.
* **A spin, as a check.** Turning on the spot, the gyro's turn rate against the wheels' speed says
  whether the module positions and wheel sizes agree with each other, as a whole.
"""

from __future__ import annotations

import math

from . import analysis as A

IN = 0.0254
WHEEL_SPREAD_WARN = 0.010     # one wheel this much off the others: worn or different tread
DIAMETER_EDIT = 0.004         # the average this far from the configured size is worth a change
LOCATION_EDIT_IN = 0.25       # tape this far from the config is worth a change
MISALIGNED_DEG = 8.0
CURVED_DEG = 3.0
MIN_PUSH_M = 1.5
SPIN_AGREE = 0.03


def _f(level, title, why, **extra):
    d = {"level": level, "title": title, "why": why}
    d.update(extra)
    return d


def _quadrant(name, value, word_pos, word_neg):
    n = name.lower()
    if word_pos in n:
        return 1.0
    if word_neg in n:
        return -1.0
    return 1.0 if value >= 0 else -1.0


def tape_locations(project, wheelbase_in, track_in):
    """Module locations from a tape measure: ``{"rows", "edits", "findings"}``.

    Each module keeps its quadrant (taken from its name - front/back, left/right - or else from the
    sign already configured) and gets half the wheelbase forward or back and half the track left or
    right. Inches, as YAGSL's module files use.
    """
    wb, tw = float(wheelbase_in), float(track_in)
    F = []
    if not (6 <= wb <= 40 and 6 <= tw <= 40):
        return {"rows": [], "edits": [], "findings": [_f(
            "error", "Those measurements don't look like a robot",
            "Measure in inches, from the center of a front wheel's axle to the center of the back "
            "wheel's axle (wheelbase), and from the center of a left wheel to the center of the right "
            "one (track width). A typical frame gives 18 to 30 inches.")]}
    rows, edits = [], []
    for n in project.module_names():
        loc = project.module(n).get("location") or {}
        f, l = float(loc.get("front", 0)), float(loc.get("left", 0))
        nf = round(_quadrant(n, f, "front", "back") * wb / 2, 3)
        nl = round(_quadrant(n, l, "left", "right") * tw / 2, 3)
        moved = math.hypot(nf - f, nl - l)
        rows.append({"name": n, "front": f, "left": l, "new_front": nf, "new_left": nl, "moved_in": moved,
                     "change": moved >= LOCATION_EDIT_IN})
        if moved >= LOCATION_EDIT_IN:
            edits += [(f"modules/{n}.json", ("location", "front"), nf),
                      (f"modules/{n}.json", ("location", "left"), nl)]
    if edits:
        worst = max(rows, key=lambda r: r["moved_in"])
        F.append(_f("warn", f"The module files are up to {worst['moved_in']:.2f} in from the tape",
                    "Odometry turns every rotation of the robot into module speeds using these "
                    "positions. Wrong ones make the wheels fight each other while turning (scrub), and "
                    "the robot's turns come out too big or too small."))
    else:
        F.append(_f("ok", "The module files match the tape", f"Every module within {LOCATION_EDIT_IN} in."))
    if abs(wb - tw) < 0.01 and all(abs(r["front"]) == abs(r["left"]) for r in rows):
        F.append(_f("info", "A square frame", "Fine if it really is square: measure both ways."))
    return {"rows": rows, "edits": edits, "findings": F, "wheelbase_in": wb, "track_in": tw}


def _module_count(ch):
    return len({k.split(".")[0] for k in ch if k.startswith("m") and k.endswith(".pos")})


def wheel_sizes(capture, tape_m, configured_in, names=None):
    """Each wheel's real diameter from a straight push in coast: ``{"rows", "average_in", ...}``.

    ``capture`` is a capture run (channels ``m<i>.pos`` meters, ``m<i>.steer`` degrees,
    ``heading`` degrees); ``tape_m`` how far the robot really went; ``configured_in`` the wheel
    diameter odometry uses now.
    """
    ch = capture.get("channels") or {}
    n = _module_count(ch)
    names = list(names or [])[:n] + [f"module {i}" for i in range(len(names or []), n)]
    F, rows = [], []
    tape = float(tape_m)
    if n == 0 or tape <= 0:
        return {"rows": [], "findings": [_f("error", "Nothing to measure",
                                            "Record the push first, and type how far the robot went.")]}
    heading = A.unwrap_deg(ch.get("heading") or [])
    curved = abs(heading[-1] - heading[0]) if len(heading) > 1 else 0.0
    for i in range(n):
        pos = ch.get(f"m{i}.pos") or []
        steer = ch.get(f"m{i}.steer") or []
        if len(pos) < 2:
            continue
        d = pos[-1] - pos[0]
        # The wheel's axis while it was rolling, against straight ahead. Averaged as an axis (double
        # the angle, average the unit vectors, halve it), so 179 and -179 average to 180, not 0, and
        # a wheel pointing backwards counts as straight: it just rolls backwards.
        moving = [k for k in range(1, len(pos)) if abs(pos[k] - pos[k - 1]) > 1e-4 and k < len(steer)]
        sx = sum(math.cos(math.radians(2 * steer[k])) for k in moving)
        sy = sum(math.sin(math.radians(2 * steer[k])) for k in moving)
        off = abs(math.degrees(math.atan2(sy, sx)) / 2) if moving else 0.0
        rolled = abs(d)
        real = configured_in * tape * math.cos(math.radians(off)) / rolled if rolled > 0.05 else float("nan")
        rows.append({"name": names[i], "encoder_m": d, "angle_deg": off, "diameter_in": real})
    good = [r["diameter_in"] for r in rows if A.finite(r["diameter_in"])]
    if not good:
        return {"rows": rows, "findings": [_f("error", "No wheel turned",
                                              "Coast mode must be on while pushing: run the push "
                                              "recording, then push.")]}
    avg = A.mean(good)
    for r in rows:
        r["vs_average"] = r["diameter_in"] / avg - 1 if A.finite(r["diameter_in"]) else float("nan")
    if tape < MIN_PUSH_M:
        F.append(_f("warn", f"A short push ({tape:.2f} m)",
                    f"Measuring a 1% difference needs a push of at least {MIN_PUSH_M} m: a 2 cm "
                    "tape error over 1 m is already 2%."))
    if curved > CURVED_DEG:
        F.append(_f("warn", f"The push curved by {curved:.1f} degrees",
                    "The wheels on the outside of a curve roll further than those inside it. Push "
                    "straight along the tape and repeat."))
    for r in rows:
        if r["angle_deg"] > MISALIGNED_DEG:
            F.append(_f("warn", f"{r['name']} pointed {r['angle_deg']:.0f} degrees off straight",
                        "Point every wheel straight ahead before pushing; a wheel at an angle rolls "
                        "less than the robot moves (corrected for here, but less accurately).",
                        where={"devices": [r["name"] + " drive"]}))
        if r["encoder_m"] < -0.05:
            F.append(_f("info", f"{r['name']}'s distance counted backwards",
                        "Fine if the robot was pushed backwards. If not, that drive motor's inversion "
                        "is wrong - the hand check would show it too."))
    worst = max(rows, key=lambda r: abs(r["vs_average"]) if A.finite(r["vs_average"]) else 0)
    if A.finite(worst["vs_average"]) and abs(worst["vs_average"]) > WHEEL_SPREAD_WARN:
        F.append(_f("warn", f"{worst['name']}'s wheel is {abs(worst['vs_average']) * 100:.1f}% "
                            f"{'smaller' if worst['vs_average'] < 0 else 'bigger'} than the average",
                    "Worn or compressed tread, or a different wheel. The code uses one wheel size for "
                    "every module, so the best fix is new tread on that module; until then that wheel "
                    "drags while driving straight.", where={"devices": [worst["name"] + " drive"]}))
    edits = []
    change = avg / configured_in - 1
    if abs(change) > DIAMETER_EDIT:
        edits.append(("modules/physicalproperties.json", ("conversionFactors", "drive", "diameter"),
                      round(avg, 4)))
        F.append(_f("warn", f"The wheels are {abs(change) * 100:.1f}% {'smaller' if change < 0 else 'bigger'} "
                            f"than configured ({avg:.3f} in, not {configured_in:g} in)",
                    "Odometry turns wheel rotations into distance with this number, so every distance "
                    "the robot thinks it drove is off by the same amount. Update the wheel diameter "
                    "(and PathPlanner's wheel radius with it)."))
    elif len(F) == 0:
        F.append(_f("ok", "Wheel sizes match the configuration",
                    f"Average {avg:.3f} in against {configured_in:g} in configured."))
    return {"rows": rows, "average_in": avg, "configured_in": configured_in, "tape_m": tape,
            "curved_deg": curved, "edits": edits, "findings": F}


def spin_check(spin_report_measured, configured_over_real=1.0):
    """Do the module positions and wheel sizes agree, judged from a floor spin's report?

    ``gyro_over_wheels`` is how fast the robot turned against how fast its wheels say it turned.
    With true positions and wheel sizes it is 1. Above 1 the modules sit closer to the center than
    configured (or the wheels are bigger); below 1, the other way - or the wheels slipped.
    ``configured_over_real`` is the configured wheel diameter over the real one from a push (above 1
    for worn tread, which reads long).
    """
    gw = (spin_report_measured or {}).get("gyro_over_wheels")
    if gw is None or not A.finite(gw) or gw <= 0:
        return {"findings": [_f("info", "No spin on the floor to check against",
                                "Run the spin test on the floor (Tune tab) after updating the positions.")]}
    # Wheels read v = w_true * r_true * s with s = configured/real diameter, and are judged against
    # r_cfg: gyro/wheels = r_cfg / (r_true * s).
    radius_ratio = 1 / (gw * configured_over_real)
    F = []
    if abs(radius_ratio - 1) <= SPIN_AGREE:
        F.append(_f("ok", "The spin agrees with the module positions",
                    f"The robot turned within {abs(radius_ratio - 1) * 100:.1f}% of what its wheels and "
                    "module positions predict."))
    else:
        F.append(_f("warn", f"The robot turns as if its modules were {radius_ratio:.3f}x as far from the "
                            "center as configured",
                    "Measure wheelbase and track width again (axle center to axle center, not the frame), "
                    "and check the wheel sizes with a push. If both are right, the wheels slipped: spin "
                    "slower and repeat."))
    return {"gyro_over_wheels": gw, "radius_ratio": radius_ratio, "findings": F}
