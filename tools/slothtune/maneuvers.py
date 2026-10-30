"""The accuracy maneuvers: the robot library's ManeuverCatalog.java, for the laptop.

The robot runs a maneuver leg by leg and sends back its legs, the planned end and where its
odometry ended (``maneuver`` in contract.TESTS). The laptop needs the list for two things: a picker
(the Calibrate tab's Accuracy section, ``run maneuver --arg id=...``) and the report's words about
what each family of maneuver isolates. The order and the names must match the Java list; the GUI
asks by ``id`` (a number from the name, computed the same way on both sides), so a robot whose list
differs refuses instead of running the wrong one. tests/test_maneuvers.py checks the two against
each other.

Units are the robot's: meters and degrees. The 2026 requirement: 10 ft of travel to within 1 in.
"""

from __future__ import annotations

import math

FT = 0.3048
TEN_FT = 10 * FT
FIVE_FT = 5 * FT
# 1 in of error for every 10 ft driven.
BUDGET_PER_M = 1 / 120
# The heading error that, held over the next 10 ft, would by itself use up that 1 in: atan(1/120).
HEADING_BUDGET_DEG = 0.5

PERMUTATION, SAME_PATH, DIFFERENT_PATH = 0, 1, 2
FAMILIES = {
    PERMUTATION: {
        "key": "permutation", "label": "Drive, turn, drive",
        "isolates": "One combination of distance, turn and direction at a time: a turn accurate one way "
                    "and not the other, or a reverse leg with more backlash, shows only against its mirror."},
    SAME_PATH: {
        "key": "same_path", "label": "Out and back, same path",
        "isolates": "Heading error, backlash and hysteresis. Wheel size cancels on the way back, so a small "
                    "closure does NOT mean the wheels are right (the Straight line test measures them)."},
    DIFFERENT_PATH: {
        "key": "different_path", "label": "Out and back, different path",
        "isolates": "Wheel size and heading together: the legs don't mirror each other, so their errors add "
                    "up instead of cancelling. The closest thing to an autonomous path."},
}


def drive(m):
    return ("drive", float(m))


def turn(deg):
    return ("turn", float(deg))


def _m(name, description, family, legs):
    return {"name": name, "description": description, "family": family, "legs": list(legs)}


def retrace(legs):
    """Legs that come back along ``legs`` exactly: reversed, every value negated."""
    return [(k, -v) for k, v in reversed(legs)]


def _permutations():
    out = []
    for d, dn, dw in ((TEN_FT, "10ft", "10 ft"), (FIVE_FT, "5ft", "5 ft")):
        for t in (90, 270):
            for sign, sn, sw in ((1, "L", "left"), (-1, "R", "right")):
                for last, ln, lw in ((TEN_FT, "fwd10ft", "10 ft forward"), (-TEN_FT, "rev10ft", "10 ft in reverse")):
                    out.append(_m(f"P_{dn}_{sn}{t}_{ln}", f"Drive {dw}, turn {t} deg {sw}, then {lw}",
                                  PERMUTATION, [drive(d), turn(t * sign), drive(last)]))
    return out


def _same_path():
    shape = [drive(TEN_FT), turn(90), drive(FIVE_FT)]
    return [
        _m("OB_same_straight10ft", "Out 10 ft forward, back 10 ft in reverse along the same line", SAME_PATH,
           [drive(TEN_FT), drive(-TEN_FT)]),
        _m("OB_same_straight5ft", "Out 5 ft forward, back 5 ft in reverse along the same line", SAME_PATH,
           [drive(FIVE_FT), drive(-FIVE_FT)]),
        _m("OB_same_turnaround10ft", "Out 10 ft, turn 180 deg, drive 10 ft forward, turn 180 deg back", SAME_PATH,
           [drive(TEN_FT), turn(180), drive(TEN_FT), turn(180)]),
        _m("OB_same_L_retrace", "L-shape out (10 ft, left 90 deg, 5 ft), then the identical L retraced back to the start",
           SAME_PATH, shape + retrace(shape)),
    ]


def _different_path():
    f, t = FIVE_FT, TEN_FT
    return [
        _m("OB_diff_square5ft", "5 ft square, four left turns: the closure is the accumulated turn error",
           DIFFERENT_PATH, [drive(f), turn(90)] * 4),
        _m("OB_diff_square5ft_right", "5 ft square clockwise, four right turns: compare with the left-hand square",
           DIFFERENT_PATH, [drive(f), turn(-90)] * 4),
        _m("OB_diff_rectangle", "Rectangle with left turns: 10 ft out, 5 ft across, 10 ft back, 5 ft across",
           DIFFERENT_PATH, [drive(t), turn(90), drive(f), turn(90)] * 2),
        # Named "mixed turns" in 2026; its legs are the rectangle's mirror (kept, so old logs compare).
        _m("OB_diff_mixed_turns", "Rectangle with right turns: 10 ft out, 5 ft across, 10 ft back, 5 ft across",
           DIFFERENT_PATH, [drive(t), turn(-90), drive(f), turn(-90)] * 2),
        _m("OB_diff_triangle", "Equilateral triangle with 5 ft sides and 120 deg left turns",
           DIFFERENT_PATH, [drive(f), turn(120)] * 3),
    ]


CATALOG = _permutations() + _same_path() + _different_path()

# What to run next to compare against: the same maneuver turning the other way.
_MIRRORS = {"OB_diff_square5ft": "OB_diff_square5ft_right", "OB_diff_rectangle": "OB_diff_mixed_turns",
            "OB_same_straight10ft": "OB_same_turnaround10ft"}
_MIRRORS.update({v: k for k, v in list(_MIRRORS.items())})


def ident(name):
    """ManeuverCatalog.id: a number for a name, the same on the robot. Below 2**31."""
    h = 0
    for c in name:
        h = (h * 131 + ord(c)) % 1_000_000_007
    return h


def wrap_deg(deg):
    """-180 to 180."""
    return math.remainder(deg, 360)


def expected_pose(legs, start=(0.0, 0.0, 0.0)):
    """Where ``legs`` should finish from ``start`` (x m, y m, heading deg): a drive moves along the
    current heading, a turn rotates in place. Heading -180 to 180."""
    x, y, h = start
    for kind, v in legs:
        if kind == "turn":
            h += v
        else:
            x += v * math.cos(math.radians(h))
            y += v * math.sin(math.radians(h))
    return x, y, wrap_deg(h)


def extent(legs):
    """How far the robot's center goes from the start, meters: ``{ahead, behind, side, radius}``."""
    x = y = h = 0.0
    e = {"ahead": 0.0, "behind": 0.0, "side": 0.0, "radius": 0.0}
    for kind, v in legs:
        if kind == "turn":
            h += v
            continue
        x += v * math.cos(math.radians(h))
        y += v * math.sin(math.radians(h))
        e["ahead"] = max(e["ahead"], x)
        e["behind"] = max(e["behind"], -x)
        e["side"] = max(e["side"], abs(y))
        e["radius"] = max(e["radius"], math.hypot(x, y))
    return e


def travel(legs):
    return sum(abs(v) for k, v in legs if k == "drive")


def by_name(name):
    return next((m for m in CATALOG if m["name"] == name), None)


def mirror(name):
    """The maneuver to compare a run with: the same shape turning the other way, or None."""
    if name in _MIRRORS:
        return _MIRRORS[name]
    if name.startswith("P_"):
        swapped = name.replace("_L", "_#").replace("_R", "_L").replace("_#", "_R")
        return swapped if by_name(swapped) else None
    return None


def listing():
    """Every maneuver for the picker, in catalog order, with what it needs."""
    out = []
    for i, m in enumerate(CATALOG):
        e = extent(m["legs"])
        out.append({"index": i, "id": ident(m["name"]), "name": m["name"], "description": m["description"],
                    "family": FAMILIES[m["family"]]["key"], "family_label": FAMILIES[m["family"]]["label"],
                    "returns": m["family"] != PERMUTATION, "travel_m": travel(m["legs"]),
                    "budget_m": travel(m["legs"]) * BUDGET_PER_M, "ahead_m": e["ahead"], "side_m": e["side"],
                    "turns": sum(1 for k, _ in m["legs"] if k == "turn"), "mirror": mirror(m["name"])})
    return out
