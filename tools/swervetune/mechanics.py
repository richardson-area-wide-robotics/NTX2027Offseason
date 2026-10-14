"""A mechanism's physics, and the safe test that follows from it.

The physical data comes from the design team's calculator: a ReCalc share link (reca.lc, whose URL
carries every input as JSON) or the same numbers typed in from the AMB Design Spreadsheet. From it,
the way ReCalc does it (both build WPILib's ``Models``: ``SingleJointedArmFromPhysicalConstants``
and ``FlywheelFromPhysicalConstants``; see ReCalc's wpilib/patches/wpilibc/wasm/feedforward_gains.h):

* ``kV = G / Kv`` volts per rad/s of the mechanism, ``kA = R J / (G Kt eta)``, and for an arm
  ``kG = R g L m / (G Kt eta)``, where R, Kv and Kt are the motors' (n of them, WPILib's DCMotor);
* the mechanism's free speed, ``motor free speed / G``.

The motor numbers are ReCalc's own table (app/lib/models/Motor.ts), so a ReCalc link gives the same
gains here as on reca.lc.

The test plan keeps well inside that: a top speed a fraction of the free speed (and never above
the team's own maximum), an acceleration a fraction of what the motors could do at full voltage
against gravity, and goals inside the limits a person found by moving the mechanism by hand.
"""

from __future__ import annotations

import json
import math
from urllib.parse import parse_qs, urlparse

G_ACCEL = 9.80665
VOLTS = 12.0

# ReCalc's motor table (app/lib/models/Motor.ts): stall torque N*m, stall current A, free current A,
# free speed rpm, per motor.
MOTORS = {
    "Kraken X60": (7.157, 374.383, 2.83, 6065),
    "Kraken X60 (FOC)": (9.362, 476.098, 3.496, 5784),
    "NEO Vortex": (5.957, 391.091, 5.434, 6825),
    "NEO 2.0": (4.201, 216.269, 1.782, 5906),
    "NEO": (4.201, 216.269, 1.782, 5906),
    "Kraken X44": (4.113, 279.099, 3.156, 7757),
    "Kraken X44 (FOC)": (5.011, 329.188, 3.231, 7367),
    "Falcon 500": (4.69, 257, 1.5, 6380),
    "Falcon 500 (FOC)": (5.84, 304, 1.5, 6080),
    "Minion": (3.173, 211.607, 2.206, 7703),
    "Thrifty Pulsar": (3.1, 189, 2.7, 7500),
    "NEO 550": (1.08, 111, 1.1, 11710),
    "775pro": (0.71, 134, 0.7, 18730),
}

# Units a ReCalc measurement may carry, to SI.
_UNITS = {
    "lb": 0.45359237, "lbs": 0.45359237, "kg": 1.0, "g": 0.001,
    "in": 0.0254, "ft": 0.3048, "m": 1.0, "mm": 0.001, "cm": 0.01,
    "deg": math.pi / 180, "rad": 1.0,
    "A": 1.0, "V": 1.0, "Ohm": 1.0, "ms": 0.001, "s": 1.0,
    "rpm": 2 * math.pi / 60, "rad/s": 1.0, "deg/s": math.pi / 180,
    "in2*lbs": 0.45359237 * 0.0254 ** 2, "lbs*in2": 0.45359237 * 0.0254 ** 2, "lb*in^2": 0.45359237 * 0.0254 ** 2,
    "kg*m^2": 1.0, "kg*m2": 1.0,
}


def _si(m):
    """``{"s": 24, "u": "in"}`` -> 0.6096; None if not a measurement this knows."""
    if not isinstance(m, dict) or not isinstance(m.get("s"), (int, float)):
        return None
    f = _UNITS.get(str(m.get("u", "")))
    return None if f is None else m["s"] * f


def _ratio(r):
    """``{"magnitude": 100, "ratioType": "Reduction"}`` -> motor turns per mechanism turn."""
    if not isinstance(r, dict) or not r.get("magnitude"):
        return None
    mag = float(r["magnitude"])
    return mag if r.get("ratioType", "Reduction") == "Reduction" else 1.0 / mag


def from_recalc(url):
    """A ReCalc share link's mechanism: ``{"kind", "motor", "count", "ratio", ...}`` in SI, with
    ``"source"`` the link. Raises ValueError for a link this can't read."""
    u = urlparse(url.strip())
    page = u.path.strip("/").split("/")[-1].lower()
    if "reca.lc" not in u.netloc and page not in ("arm", "flywheel", "linear"):
        raise ValueError("not a ReCalc link (reca.lc/arm, /flywheel or /linear)")
    q = {k: v[-1] for k, v in parse_qs(u.query).items()}

    def j(k):
        try:
            return json.loads(q[k]) if k in q else None
        except ValueError:
            return None

    motor = j("motor") or {}
    out = {"motor": motor.get("name"), "count": int(motor.get("quantity") or 1), "ratio": _ratio(j("ratio")),
           "efficiency": float(q.get("efficiency", 100)) / 100 if q.get("efficiency") else 1.0, "source": url.strip()}
    if out["motor"] not in MOTORS:
        raise ValueError(f"motor {out['motor']!r} is not in ReCalc's table here")
    if page == "arm":
        out.update(kind="pivot", arm_length_m=_si(j("armLength")), load_kg=_si(j("load")),
                   min_angle_rad=_si(j("minAngle")), max_angle_rad=_si(j("maxAngle")))
    elif page == "flywheel":
        d, w = _si(j("shooterDiameter")), _si(j("shooterWeight"))
        moi = _si(j("customShooterMoi")) if j("useCustomShooterMoi") else (w * (d / 2) ** 2 / 2 if d and w else None)
        if j("flywheelEnabled"):
            fd, fw = _si(j("flywheelDiameter")), _si(j("flywheelWeight"))
            extra = _si(j("customFlywheelMoi")) if j("useCustomFlywheelMoi") else (fw * (fd / 2) ** 2 / 2 if fd and fw else 0)
            moi = (moi or 0) + (extra or 0)
        out.update(kind="flywheel", moi_kgm2=moi, target_rad_s=_si(j("shooterTargetSpeed")))
    elif page == "linear":
        out.update(kind="elevator", load_kg=_si(j("load")), spool_diameter_m=_si(j("spoolDiameter")),
                   travel_m=_si(j("travelDistance")))
    else:
        raise ValueError(f"ReCalc's {page or 'home'} page is not a mechanism")
    if not out["ratio"]:
        raise ValueError("the link has no gear ratio")
    return out


def dc_motor(name, count=1):
    """WPILib's DCMotor for ``count`` of ``name``: (R ohms, Kv rad/s per V, Kt N*m per A, free rad/s)."""
    stall_t, stall_a, free_a, free_rpm = MOTORS[name]
    stall_t, stall_a, free_a = stall_t * count, stall_a * count, free_a * count
    free = free_rpm * 2 * math.pi / 60
    r = VOLTS / stall_a
    return r, free / (VOLTS - r * free_a), stall_t / stall_a, free


def feedforward(mech):
    """``{"kV", "kA", "kG", "free_speed"}`` for the mechanism, per radian of it (per meter for an
    elevator), as ReCalc computes them; None where the data is missing."""
    r, kv, kt, free = dc_motor(mech["motor"], mech.get("count", 1))
    g, eta = mech["ratio"], mech.get("efficiency") or 1.0
    out = {"kV": g / kv, "kA": None, "kG": None, "free_speed": free / g}
    if mech["kind"] == "pivot" and mech.get("arm_length_m") and mech.get("load_kg"):
        j = mech["load_kg"] * mech["arm_length_m"] ** 2
        out["kA"] = r * j / (g * kt * eta)
        out["kG"] = r * G_ACCEL * mech["arm_length_m"] * mech["load_kg"] / (g * kt * eta)
    elif mech["kind"] == "flywheel" and mech.get("moi_kgm2"):
        out["kA"] = r * mech["moi_kgm2"] / (g * kt * eta)
        out["kG"] = 0.0
    elif mech["kind"] == "elevator" and mech.get("load_kg") and mech.get("spool_diameter_m"):
        rad = mech["spool_diameter_m"] / 2
        out["kV"] = g / (kv * rad)
        out["kA"] = r * mech["load_kg"] * rad / (g * kt * eta)
        out["kG"] = out["kA"] * G_ACCEL
        out["free_speed"] = free / g * rad
    return out


# How far inside the physics a first test of a pivot or elevator stays: it can hit a hard stop.
SPEED_FRACTION = 0.25
ACCEL_FRACTION = 0.25
# A flywheel spinning at its shooting speed is just working; without a target, 60% of its free speed.
FLYWHEEL_FRACTION = 0.6


def test_plan(mech, limits, units_per_mech_unit, team_max_velocity=None):
    """The safe test: ``{"vmax", "amax", "a", "b", "why"}`` in the system's own units.

    ``units_per_mech_unit``: how many of its units are one radian of the mechanism (one meter of an
    elevator; for a flywheel read in RPM, RPM per rad/s). ``limits``: (min, max) found by hand, for a
    pivot or elevator. A pivot or elevator moves at a quarter of its free speed, accelerating at a
    quarter of what full voltage gives less what holding it against gravity takes; a flywheel goes
    up to its target speed. Never above the team's maximum."""
    ff = feedforward(mech)
    k = units_per_mech_unit
    free = ff["free_speed"] * k
    why = []
    if ff["kA"]:
        full = (VOLTS - abs(ff["kG"] or 0)) / ff["kA"] * k
    else:
        full = None
    if mech["kind"] == "flywheel":
        target = (mech.get("target_rad_s") or 0) * k
        vmax = min(target, 0.9 * free) if target else FLYWHEEL_FRACTION * free
        why.append(f"top speed {vmax:.4g}: " + ("its target speed" if target else f"{FLYWHEEL_FRACTION:.0%} of its free speed, {free:.4g}"))
        amax = ACCEL_FRACTION * full if full else vmax / 1.0
        why.append(f"spin-up {amax:.4g} per s: " + (f"a quarter of what full voltage gives" if full else "no inertia in the data, so a full second to top speed"))
    else:
        vmax = SPEED_FRACTION * free
        why.append(f"top speed {vmax:.4g} per s: a quarter of its free speed, {free:.4g}")
        amax = ACCEL_FRACTION * full if full else vmax / 0.5
        why.append(f"acceleration {amax:.4g} per s^2: " + ("a quarter of what full voltage gives, less holding it up" if full
                                                            else "no inertia in the data, so half a second to top speed"))
    if team_max_velocity and 0 < team_max_velocity < vmax:
        vmax = team_max_velocity
        why.append(f"capped at the team's maximum, {team_max_velocity:.4g}")
    if mech["kind"] == "flywheel":
        return {"vmax": vmax, "amax": amax, "a": 0.5 * vmax, "b": vmax, "why": why}
    lo, hi = limits
    rng = hi - lo
    return {"vmax": vmax, "amax": amax, "a": lo + 0.3 * rng, "b": lo + 0.7 * rng, "why": why}
