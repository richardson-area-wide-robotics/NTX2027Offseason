"""A mechanism's design (a ReCalc or AMBcalc link) checked against the robot.

A design is a plan; the robot is the truth. For each design the team attaches to a mechanism (the
motors it drives), this says where the two disagree, cheapest evidence first:

* **the code and its files** - the motors really fitted and how many, the team's current policy,
  velocity setpoints the motor can never reach, and for the drivetrain the YAGSL gearing, wheel
  and mass;
* **the robot's sensors** - from a match log: how fast each motor turns per volt (which tells a
  NEO from a Vortex, whatever the files say), its top speed, and how long it sat at its current
  limit (a design's speeds assume it doesn't).

It also says which configuration numbers the design can fill in, and only those a design should
decide: a drivetrain's gearing when it is one REV sells, the robot's mass until it is weighed, and
the motor type of a mechanism motor nobody has named yet. The drive current limit is never one of
them: the slip test measures that.

Designs live in ``swervetune.json`` under ``"designs"``: ``{"Shooter": {"url": ..., "motors":
["Shooter leader", "Shooter follower"]}}``. Only the link is kept, so a better reader of the link
improves every saved design.
"""

from __future__ import annotations

import os
import re

from . import contract as C
from . import designlinks as D
from . import motorinv, revspecs

# revspecs keys to the motor guard's MotorKind, for the team's current policy.
_POLICY_KIND = {"neo": "NEO_V1_1", "neo2": "NEO_2_0", "vortex": "VORTEX", "neo550": "NEO_550"}
# A setpoint above this share of free speed can't be held on a real battery under load.
REACHABLE = 0.9
# rpm per volt that tells the motors apart (REV: NEO 473, Vortex 565, NEO 550 917).
_KV = {k: m["kv_rpm_per_v"] for k, m in revspecs.MOTORS.items()}


def _f(level, title, why, **extra):
    d = {"level": level, "title": title, "why": why}
    d.update(extra)
    return d


def _family(label):
    return motorinv._family(label)


def policy_amps(key):
    k = _POLICY_KIND.get(key)
    return C.MOTOR_KINDS[k][1] if k in C.MOTOR_KINDS else None


def saved(project):
    """The designs saved for this robot: ``{mechanism: {"url", "motors"}}``."""
    return {k: v for k, v in ((project.data.get("swervetune.json") or {}).get("designs") or {}).items() if v}


def mechanism_file(project, motor_names):
    """The Java file that registers these motors with the motor guard (their subsystem), or None."""
    for name, src in (project.java or {}).items():
        if any(f'"{m}"' in src and ".watch(" in src for m in motor_names):
            return name, src
    return None, None


def velocity_setpoints(src):
    """Velocity setpoints written as numbers in a subsystem: ``setSetpoint(3950, ControlType.kVelocity)``."""
    out = []
    for m in re.finditer(r"(?:setSetpoint|setReference)\(\s*(-?[\d.]+)\s*,\s*(?:\w+\.)*ControlType\.kVelocity", src or ""):
        out.append(abs(float(m.group(1))))
    return sorted(set(out))


# ---------------------------------------------------------------------------- mechanisms
def check_mechanism(d, project, rows, stats=None):
    """Findings for a mechanism design against the motors it is attached to.

    ``rows`` are those motors' motor-inventory rows (:func:`motorinv.table`), ``stats`` per-motor
    numbers from a match log (:func:`logsummary.motor_stats`).
    """
    F = []
    m = d.get("motor") or {}
    key = m.get("key")
    if not rows:
        return [_f("info", "No motors attached", "Pick the motors this design is for, so it can be checked.")]
    if m and m.get("count") and m["count"] != len(rows):
        F.append(_f("warn", f"The design has {m['count']} motor{'s' if m['count'] != 1 else ''}; {len(rows)} are attached",
                    "Every number it predicts scales with the motor count. Attach the right motors, or change the "
                    "count in the calculator."))
    fitted = sorted({r.get("motor") or "" for r in rows})
    if m and not key:
        F.append(_f("warn", f"The design is for a {m['label']}, which isn't a REV motor",
                    f"This robot's motors are {', '.join(f or 'not named' for f in fitted)}. The design's speeds and "
                    "currents are for a different motor; pick the fitted one in the calculator."))
    elif key:
        wrong = [r["name"] for r in rows if r.get("motor") and _family(r["motor"]) and _family(r["motor"]) != _family(m["label"])]
        if wrong:
            F.append(_f("error", f"The design is for a {m['label']}; {', '.join(wrong)} {'is' if len(wrong) == 1 else 'are'} "
                        f"{rows[[r['name'] for r in rows].index(wrong[0])]['motor']}",
                        "Its speeds and currents are for another motor. Fix whichever is wrong: the calculator, or "
                        "the motor named in the code (watch(..., MotorKind.X)) or the motor inventory."))
        pol = policy_amps(key)
        lim = d.get("current_limit_a")
        if pol and lim and lim > pol + 0.5:
            F.append(_f("warn", f"The design assumes {lim:g} A; the team limits a {m['label']} to {pol} A",
                        "The motor guard holds it to the policy, so the design's speeds and accelerations are "
                        f"optimistic. Set the calculator's current limit to {pol} A and check again.", learn="current_limit"))
        spec = revspecs.MOTORS[key]
        _, src = mechanism_file(project, [r["name"] for r in rows])
        if src and "velocityConversionFactor" not in src:
            too_fast = [s for s in velocity_setpoints(src) if s > REACHABLE * spec["free_rpm"]]
            if too_fast:
                F.append(_f("error", f"The code asks for {', '.join(f'{s:g}' for s in too_fast)} rpm; a {m['label']} "
                            f"turns at most {spec['free_rpm']} rpm",
                            f"That is its free speed at 12 V, with nothing to turn. Under load on a real battery it "
                            f"won't hold even {REACHABLE * spec['free_rpm']:.0f} rpm, so the loop runs flat out and "
                            "never gets there. Ask for less: with no velocity conversion factor the setpoint is the motor's own "
                            "speed, so no gearing changes it.", learn="saturation"))
        if d.get("target_rpm") and d.get("ratio"):
            motor_rpm = d["target_rpm"] * d["ratio"]
            if motor_rpm > REACHABLE * spec["free_rpm"]:
                F.append(_f("warn", f"The design's {d['target_rpm']:g} rpm at the wheel needs {motor_rpm:.0f} rpm at the motor",
                            f"More than {REACHABLE * 100:.0f}% of a {m['label']}'s {spec['free_rpm']} rpm free speed: "
                            "it will spin up slowly and sag with every shot.", learn="saturation"))
    p = D.predicts(d)
    if p.get("hold_margin") is not None and p["hold_margin"] < 1.3:
        F.append(_f("error" if p["hold_margin"] < 1 else "warn",
                    f"At {d.get('current_limit_a') or 'its stall'} A the motors give {p['hold_margin']:.2g}× what holding "
                    "the arm out level takes",
                    "Below 1 it can't hold the load level at all; below about 1.3 it has nothing left to lift with. "
                    "Gear it down, shorten the arm or lighten the load.", learn="current_limit"))
    F.extend(_from_log(d, rows, stats))
    if not F:
        F.append(_f("ok", "The design matches the robot", "Motor, count and current limit agree with the code."))
    return F


def _from_log(d, rows, stats):
    F = []
    m = d.get("motor") or {}
    for r in rows:
        s = (stats or {}).get(r["name"])
        if not s:
            continue
        kv = s.get("rpm_per_volt")
        if kv:
            near = min(_KV, key=lambda k: abs(_KV[k] - kv))
            if abs(_KV[near] - kv) / _KV[near] < 0.12 and m.get("key") and _family(revspecs.MOTORS[near]["label"]) != _family(m["label"]):
                F.append(_f("error", f"{r['name']} turns like a {revspecs.MOTORS[near]['label']} ({kv:.0f} rpm per volt)",
                            f"The design says {m['label']}. A match log measures the motor itself, whatever the files "
                            "say: fix the design or the motor inventory.", learn="motor_inventory"))
        at = s.get("at_limit_frac")
        if at is not None and at > 0.2:
            F.append(_f("warn", f"{r['name']} sat at its current limit {at * 100:.0f}% of the time it was driven",
                        "The design's speeds assume the motor isn't held back; this one often is. Expect it slower "
                        "than the calculator says, and hotter.", learn="current_limit"))
    return F


# ---------------------------------------------------------------------------- the drivetrain
def check_drivetrain(d, project, summary=None):
    """Findings for a drivetrain design against the YAGSL files, and the edits it can fill in."""
    F, edits = [], []
    m = d.get("motor") or {}
    dk = project.drive_kind()
    if m.get("key") and dk and m["key"] != dk and _family(m["label"]) != _family(revspecs.MOTORS.get(dk, {}).get("label", "")):
        F.append(_f("error", f"The design is for {m['label']} drive motors; YAGSL drives {revspecs.MOTORS[dk]['label']}s",
                    "Every speed in the design is for another motor. Fix the calculator, or the YAGSL module type if "
                    "the robot really changed."))
    elif m and not m.get("key"):
        F.append(_f("warn", f"The design is for {m['label']} drive motors, which aren't REV's",
                    "Both robots drive MAXSwerve modules with REV motors; pick the fitted motor in the calculator."))
    if m.get("count") and m["count"] != 4:
        F.append(_f("warn", f"The design drives with {m['count']} motors", "A swerve robot has four drive motors."))
    ratio, have = d.get("ratio"), project.drive_gear()
    sold = {r: n for n, r, _, _ in revspecs.MAXSWERVE["drive_ratios"]}
    if ratio:
        match = next((r for r in sold if abs(r - ratio) / r < 0.01), None)
        if match is None:
            F.append(_f("warn", f"{ratio:.3g}:1 isn't a MAXSwerve ratio",
                        "REV sells " + ", ".join(f"{n} {r}" for r, n in sold.items()) + ". This design is for "
                        "another module, so its gearing can't be copied."))
        elif abs(match - have) > 0.005:
            F.append(_f("warn", f"The design gears the drive {match}:1 ({sold[match]}); YAGSL has {have:g}:1",
                        "One of them is wrong: count the pinion's teeth (12T Low, 13T Medium, 14T High). The tool can "
                        "write the design's ratio if that's what's fitted."))
            edits.append({"file": "modules/physicalproperties.json", "path": ["conversionFactors", "drive", "gearRatio"],
                          "value": match, "label": f"Drive gear ratio {have:g} → {match}"})
    wheel = d.get("wheel_diameter_m")
    if wheel:
        win, cfg = wheel / 0.0254, project.wheel_d_in()
        if abs(win - cfg) / cfg > 0.05:
            F.append(_f("warn", f"The design's wheel is {win:.3g} in; YAGSL has {cfg:g} in",
                        "MAXSwerve wheels are 3 in. A design for another wheel predicts the wrong speed. (A few percent "
                        "is tread wear: measure it on the Calibrate tab instead.)", learn="wheel_size"))
    lim, cfg_lim = d.get("current_limit_a"), (project.phys.get("currentLimit") or {}).get("drive")
    if lim and cfg_lim and abs(lim - float(cfg_lim)) > 0.5:
        F.append(_f("info", f"The design limits each drive motor to {lim:g} A; the files have {cfg_lim} A",
                    "The tool doesn't copy this one: the slip test measures where your wheels break loose on your "
                    "carpet, and the limit belongs just below that.", learn="slip_current"))
    mass, src = project.mass()
    if d.get("mass_kg"):
        if "assumed" in src:
            edits.append({"file": "swervetune.json", "path": ["robotMassKg"], "value": round(d["mass_kg"], 1),
                          "label": f"Robot mass {mass:g} kg (assumed) → {d['mass_kg']:.1f} kg (the design's, until it is weighed)"})
            F.append(_f("info", f"The design weighs {d['mass_kg']:.1f} kg; the robot hasn't been weighed",
                        "The tool can use the design's mass until someone weighs the robot (Calibrate tab)."))
        elif abs(d["mass_kg"] - mass) / mass > 0.1:
            F.append(_f("info", f"The design weighs {d['mass_kg']:.1f} kg; the robot weighs {mass:g} kg ({src})",
                        "The design predicts more acceleration than the robot has, or less. Update the calculator."))
    cof, pp = d.get("cof"), (project.pathplanner or {}).get("wheelCOF")
    if cof and pp and abs(cof - float(pp)) > 0.05:
        F.append(_f("info", f"The design's wheel grip is {cof:g}; PathPlanner's is {pp}",
                    "Grip sets how hard an auto can accelerate. The slip test measures the real number on carpet.",
                    learn="traction"))
    if not F:
        F.append(_f("ok", "The design matches the drivetrain's files", "Motor, gearing, wheel and mass agree."))
    return F, edits


# ---------------------------------------------------------------------------- the whole check
def evaluate(url, project, motor_names=None, inventory=None, stats=None):
    """One design: what the link says, its findings, and the configuration it can fill in."""
    d = D.parse(url)
    out = {"design": d, "describe": D.describe(d), "edits": []}
    if d["kind"] == "drivetrain":
        out["findings"], out["edits"] = check_drivetrain(d, project)
        return out
    if d["kind"] == "gearing":
        out["findings"] = [_f("info", "A gearing link", "It carries only a ratio: attach it to a mechanism's design "
                              "in its calculator to check the rest.")]
        return out
    inv = inventory or motorinv.table(project)
    rows = [r for r in inv["rows"] if r["name"] in (motor_names or [])]
    out["findings"] = check_mechanism(d, project, rows, stats)
    m = d.get("motor") or {}
    if m.get("key"):
        for r in rows:
            if r.get("motor_source") in ("not said anywhere", "assumed from the SPARK Flex"):
                out["edits"].append({"file": "swervetune.json", "path": ["motors", r["name"]], "value": m["label"],
                                     "label": f"{r['name']}: {r.get('motor') or 'not named'} → {m['label']} (from the design)"})
    return out


# What each calculator's mechanism is usually called on a robot.
DEFAULT_NAME = {"flywheel": "Shooter", "arm": "Arm", "elevator": "Elevator", "linear": "Elevator",
                "roller": "Intake", "drivetrain": "Drivetrain"}


def default_name(d):
    return d.get("title") or DEFAULT_NAME.get(d["kind"], "")


def suggest_motors(d, inventory, mechanism=""):
    """The motors a design is probably for: those whose name starts with the mechanism's name.
    None otherwise: a guess by motor type alone would check the design against the wrong
    mechanism and call it a match."""
    rows = [r for r in inventory["rows"] if r.get("key") not in ("drive", "steer")]
    mech = mechanism.strip().lower()
    return [r["name"] for r in rows if mech and r["name"].lower().startswith(mech)]


def from_log(path):
    """Per-motor numbers from a match log, for the sensor checks (empty when it can't be read)."""
    from . import logsummary
    if not path or not os.path.exists(path):
        return {}
    try:
        return logsummary.motor_stats(logsummary.read(path))
    except Exception:  # noqa: BLE001 - a damaged log only means fewer checks
        return {}
