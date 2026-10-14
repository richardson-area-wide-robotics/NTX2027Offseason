"""A mechanism's physics, and the safe test that follows from it.

The physical data comes from the design team's calculator: a ReCalc (reca.lc) or AMBcalc
(ambcalc.com) share link, read by :mod:`designlinks`, or the same numbers typed in from the AMB
Design Spreadsheet. From it,
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

import math

from . import units as U

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

# Other names the calculators give these motors (AMBcalc's "NEO 1.1", "Kraken X60 FOC").
_ALIASES = {"neo1.1": "NEO", "neov1.1": "NEO", "neo11": "NEO", "vortex": "NEO Vortex", "neovortex": "NEO Vortex",
            "kraken": "Kraken X60", "krakenx60foc": "Kraken X60 (FOC)", "falcon500foc": "Falcon 500 (FOC)",
            "krakenx44foc": "Kraken X44 (FOC)", "pulsar": "Thrifty Pulsar", "775": "775pro"}


def _key(name):
    return "".join(c for c in str(name or "").lower() if c.isalnum() or c == ".")


def motor_name(name):
    """A calculator's motor name to this table's, or None for a motor it doesn't have."""
    k = _key(name)
    return next((m for m in MOTORS if _key(m) == k), None) or _ALIASES.get(k)


# A registered system's kind to the physics it needs: a roller is a wheel, like a flywheel.
_FOR_KIND = {"PIVOT": "pivot", "ELEVATOR": "elevator", "FLYWHEEL": "flywheel", "ROLLER": "flywheel"}


def from_link(url, kind=None):
    """A ReCalc or AMBcalc share link's mechanism, read by :mod:`designlinks`: ``{"kind", "motor",
    "count", "ratio", ...}`` in SI, with ``"source"`` the link and ``"notes"`` on anything assumed.

    ``kind`` is how the code registered it (PIVOT, ELEVATOR, FLYWHEEL, ROLLER). AMBcalc's mechanism
    page is a motor turning a radius against a load, which is an arm or an elevator's spool
    depending on that; a calculator page of the wrong kind is refused. Raises ValueError for a link
    this can't read."""
    from . import designlinks
    d = designlinks.parse(url)
    want = _FOR_KIND.get(str(kind or "").upper())
    named = (d.get("motor") or {}).get("name")
    motor = motor_name(named)
    if d["kind"] in ("motor", "gearing", "drivetrain"):
        raise ValueError(f"that is {d['source']}'s {d['calculator']} page; link the mechanism's own page")
    if not motor:
        raise ValueError(f"motor {named!r} isn't in the motor table here")
    if not d.get("ratio"):
        raise ValueError(" ".join(["the link has no gear ratio."] + list(d.get("notes") or [])))
    out = {"motor": motor, "count": int((d.get("motor") or {}).get("count") or 1), "ratio": float(d["ratio"]),
           "efficiency": d.get("efficiency") or 1.0, "source": str(url).strip(), "calculator": d["source"],
           "notes": list(d.get("notes") or [])}
    mass, k = d.get("mass_kg"), d["kind"]
    if k == "arm":
        lo, hi = d.get("angles_deg") or (None, None)
        out.update(kind="pivot", arm_length_m=d.get("arm_length_m"), load_kg=mass,
                   min_angle_rad=math.radians(lo) if lo is not None else None,
                   max_angle_rad=math.radians(hi) if hi is not None else None)
    elif k in ("elevator", "linear"):
        out.update(kind="elevator", load_kg=mass, spool_diameter_m=d.get("spool_diameter_m"), travel_m=d.get("travel_m"))
    elif k == "flywheel":
        rpm = d.get("target_rpm")
        out.update(kind="flywheel", moi_kgm2=d.get("moi_kgm2"), target_rad_s=rpm * 2 * math.pi / 60 if rpm else None)
    elif k == "roller":
        out.update(kind="flywheel", moi_kgm2=None, target_rad_s=None)
    elif k == "mechanism":
        # AMBcalc: a radius and a load force; the startup page adds the mass it spins up.
        if not want:
            raise ValueError("AMBcalc's mechanism page fits an arm, an elevator or a wheel: register the system first")
        r, f = d.get("radius_m"), d.get("load_n")
        load = mass if mass else (f / G_ACCEL if f else None)
        for field in d.get("assumed") or []:
            out["notes"].append({"radius_m": "AMBcalc's default 1 in radius", "load_n": "AMBcalc's default 50 lbf load",
                                 "mass_kg": "AMBcalc's default 10 lb mass"}.get(field, field) + " (the link doesn't set it).")
        if want == "pivot":
            out.update(kind="pivot", arm_length_m=r, load_kg=load)
        elif want == "elevator":
            out.update(kind="elevator", load_kg=load, spool_diameter_m=2 * r if r else None)
        else:
            out.update(kind="flywheel", moi_kgm2=mass * r ** 2 / 2 if mass and r else None, target_rad_s=None)
    else:
        raise ValueError(f"{d['source']}'s {d['calculator']} page is not a mechanism")
    if want and out["kind"] != want:
        an = lambda w: ("an " if w[:1] in "aeiou" else "a ") + w  # noqa: E731
        raise ValueError(f"that is {an(out['kind'])} design, but the code registers this as {an(str(kind).lower())}")
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


def test_plan(mech, limits, units_per_mech_unit, team_max_velocity=None, units=""):
    """The safe test: ``{"vmax", "amax", "a", "b", "why"}`` in the system's own units; ``why``'s
    words in the team's (``units`` names the system's, as TunableSystem does).

    ``units_per_mech_unit``: how many of its units are one radian of the mechanism (one meter of an
    elevator; for a flywheel read in RPM, RPM per rad/s). ``limits``: (min, max) found by hand, for a
    pivot or elevator. A pivot or elevator moves at a quarter of its free speed, accelerating at a
    quarter of what full voltage gives less what holding it against gravity takes; a flywheel goes
    up to its target speed. Never above the team's maximum."""
    ff = feedforward(mech)
    k = units_per_mech_unit
    free = ff["free_speed"] * k
    why = []
    said, f_said = U.system_unit(units)

    def num(x, rate=""):
        """A value in the mechanism's (shown) units; ``rate`` "/s" or "/s²" for a speed or acceleration."""
        unit = f" {said}{rate}" if said else {"/s": " per s", "/s²": " per s²"}.get(rate, "")
        return f"{x * f_said:.4g}{unit}"
    if ff["kA"]:
        full = (VOLTS - abs(ff["kG"] or 0)) / ff["kA"] * k
    else:
        full = None
    if mech["kind"] == "flywheel":
        target = (mech.get("target_rad_s") or 0) * k
        vmax = min(target, 0.9 * free) if target else FLYWHEEL_FRACTION * free
        why.append(f"top speed {num(vmax)}: " + ("its target speed" if target else f"{FLYWHEEL_FRACTION:.0%} of its free speed, {num(free)}"))
        amax = ACCEL_FRACTION * full if full else vmax / 1.0
        why.append(f"spin-up {num(amax, '/s')}: " + (f"a quarter of what full voltage gives" if full else "no inertia in the data, so a full second to top speed"))
    else:
        vmax = SPEED_FRACTION * free
        why.append(f"top speed {num(vmax, '/s')}: a quarter of its free speed, {num(free, '/s')}")
        amax = ACCEL_FRACTION * full if full else vmax / 0.5
        why.append(f"acceleration {num(amax, '/s²')}: " + ("a quarter of what full voltage gives, less holding it up" if full
                                                            else "no inertia in the data, so half a second to top speed"))
    if team_max_velocity and 0 < team_max_velocity < vmax:
        vmax = team_max_velocity
        why.append(f"capped at the team's maximum, {num(team_max_velocity, '' if mech['kind'] == 'flywheel' else '/s')}")
    if mech["kind"] == "flywheel":
        return {"vmax": vmax, "amax": amax, "a": 0.5 * vmax, "b": vmax, "why": why}
    lo, hi = limits
    rng = hi - lo
    return {"vmax": vmax, "amax": amax, "a": lo + 0.3 * rng, "b": lo + 0.7 * rng, "why": why}
