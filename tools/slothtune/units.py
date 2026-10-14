"""The team's units, for everything a person reads: speed in ft/s, lengths in inches, mass in
pounds, torque in foot-pounds, angles in degrees.

The robot, WPILib, YAGSL and every saved file keep their own units (meters, kilograms, radians,
newton-meters), and so does every number in a run, a report's data or the robot link: only the
words a person reads convert, here, at the last step (web/units.js is the page's twin of this).
A gain stays in the code's units, because the number on screen must be the number in the file.

Speed is written "ft/s", never "fps": the camera's frames per second are on the same pages.
"""

from __future__ import annotations

import math

IN_PER_M = 1 / 0.0254
FT_PER_M = 1 / 0.3048
LB_PER_KG = 1 / 0.45359237
FTLB_PER_NM = 1 / 1.3558179483
DEG_PER_RAD = 180 / math.pi
LB_IN2_PER_KG_M2 = LB_PER_KG * IN_PER_M ** 2


# ---------------------------------------------------------------------------- numbers

def fps(mps):
    """m/s to ft/s."""
    return mps * FT_PER_M


def inches(m):
    return m * IN_PER_M


def lb(kg):
    return kg * LB_PER_KG


def ftlb(nm):
    return nm * FTLB_PER_NM


def deg(rad):
    return rad * DEG_PER_RAD


# Back to the robot's units, for a number a person typed.

def mps_from_fps(v):
    return v / FT_PER_M


def m_from_in(v):
    return v / IN_PER_M


def kg_from_lb(v):
    return v / LB_PER_KG


def nm_from_ftlb(v):
    return v / FTLB_PER_NM


def rad_from_deg(v):
    return v / DEG_PER_RAD


# ---------------------------------------------------------------------------- words

def _n(v, nd, sign=False):
    if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
        return "?"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def speed(mps, nd=2, sign=False):
    """``1.50 m/s`` as ``4.92 ft/s``."""
    return f"{_n(None if mps is None else fps(mps), nd, sign)} ft/s"


def accel(mps2, nd=1, sign=False):
    return f"{_n(None if mps2 is None else fps(mps2), nd, sign)} ft/s²"


def length(m, nd=1, sign=False):
    """``0.05 m`` as ``2.0 in``."""
    return f"{_n(None if m is None else inches(m), nd, sign)} in"


def mass(kg, nd=0):
    return f"{_n(None if kg is None else lb(kg), nd)} lb"


def torque(nm, nd=1, sign=False):
    return f"{_n(None if nm is None else ftlb(nm), nd, sign)} ft·lb"


def inertia(kg_m2, nd=0):
    """A moment of inertia, kg·m² as lb·in²."""
    return f"{_n(None if kg_m2 is None else kg_m2 * LB_IN2_PER_KG_M2, nd)} lb·in²"


def angle(rad, nd=1, sign=False):
    return f"{_n(None if rad is None else deg(rad), nd, sign)}°"


def angvel(radps, nd=0, sign=False):
    return f"{_n(None if radps is None else deg(radps), nd, sign)}°/s"


def angaccel(radps2, nd=0, sign=False):
    return f"{_n(None if radps2 is None else deg(radps2), nd, sign)}°/s²"


# ---------------------------------------------------------------------------- a mechanism's own units

# A mechanism names its units in free text (TunableSystem.units): those in meters, radians or
# kilograms show in the team's; anything else (RPM, motor rotations, degrees) as it is.
_SYSTEM = {
    "m": ("in", IN_PER_M), "meter": ("in", IN_PER_M), "meters": ("in", IN_PER_M), "metres": ("in", IN_PER_M),
    "m/s": ("ft/s", FT_PER_M), "meters per second": ("ft/s", FT_PER_M), "mps": ("ft/s", FT_PER_M),
    "rad": ("deg", DEG_PER_RAD), "radian": ("deg", DEG_PER_RAD), "radians": ("deg", DEG_PER_RAD),
    "rad/s": ("deg/s", DEG_PER_RAD), "radians per second": ("deg/s", DEG_PER_RAD),
    "cm": ("in", IN_PER_M / 100), "centimeters": ("in", IN_PER_M / 100),
    "mm": ("in", IN_PER_M / 1000), "millimeters": ("in", IN_PER_M / 1000),
    "kg": ("lb", LB_PER_KG), "kilograms": ("lb", LB_PER_KG),
    "n·m": ("ft·lb", FTLB_PER_NM), "nm": ("ft·lb", FTLB_PER_NM), "n*m": ("ft·lb", FTLB_PER_NM),
    "newton meters": ("ft·lb", FTLB_PER_NM),
}


def system_unit(units):
    """``(label, factor)`` to show a mechanism's numbers in: ``value * factor`` in ``label``. A
    rate ("per second") of a converted unit converts by the same factor."""
    key = (units or "").strip().lower()
    return _SYSTEM.get(key, (units or "", 1.0))
