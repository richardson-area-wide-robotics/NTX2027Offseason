"""Does PathPlanner describe the same robot as the code?

PathPlanner keeps its own copy of the robot: ``deploy/pathplanner/settings.json``, which the
PathPlanner app writes and the robot loads at boot (``RobotConfig.fromGUISettings()``). Nothing
keeps it in step with the YAGSL files, the code's constants or what the tools measured, and when
they drift apart nothing fails: paths are planned for a different robot, and the robot falls behind
or overshoots. This checks, in four parts:

1. **The robot model**: every setting PathPlanner plans with, against where the truth lives - the
   YAGSL files (gearing, wheel size, module positions, current limit, grip), the code
   (``MAX_SPEED``), and the measured mass and moment of inertia in ``slothtune.json``.
2. **The limits in the paths**: the default and per-path speed, acceleration and turn limits,
   against what this robot can physically do. A limit above that is a promise the robot can't keep.
3. **Named commands**: every one an auto or event marker uses must be registered in the code;
   PathPlanner skips an unregistered one with only a console warning.
4. **Names**: every path an auto uses, and every auto or path the code loads by name, must exist.

The robot model can be written to match (``fixes``); paths are the students' designs, so their
limits are only reported.
"""

from __future__ import annotations

import glob
import json
import math
import os
import re

from . import units as U
from . import yagslcfg as Y

G = 9.81
# PathPlannerLib 2026's driveMotorType names (from RobotConfig.fromGUISettings), by YAGSL motor kind.
PP_MOTOR = {"neo": ("NEO",), "vortex": ("vortex",), "krakenx60": ("krakenX60", "krakenX60FOC"),
            "falcon500": ("falcon500", "falcon500FOC")}
CORNERS = {"fl": ("front", "left"), "fr": ("front", "right"), "bl": ("back", "left"), "br": ("back", "right")}
SLACK = 1.02   # a limit this close to the robot's capability is fine


def _pp_dir(project):
    return os.path.join(project.path, "src", "main", "deploy", "pathplanner")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def settings_path(project):
    return os.path.join(_pp_dir(project), "settings.json")


def _corner(name):
    n = name.lower()
    fb = "f" if "front" in n else "b" if "back" in n else None
    lr = "l" if "left" in n else "r" if "right" in n else None
    return fb + lr if fb and lr else None


def capabilities(project):
    """What this robot can do, for judging path limits."""
    kind = project.drive_kind()
    vmax, src, _ = project.create_swerve_max_speed()
    v = vmax or project.max_module_speed()
    mass, _ = project.mass()
    lim = float(project.phys.get("currentLimit", {}).get("drive", 40))
    mu = float(project.phys.get("wheelGripCoefficientOfFriction", 1.19))
    force = 4 * Y.wheel_force(kind, project.drive_gear(), project.wheel_d_in(), lim) if kind else float("inf")
    a = min(mu * G, force / mass)
    r = max(math.hypot(project.module(n)["location"]["front"], project.module(n)["location"]["left"]) * 0.0254
            for n in project.module_names())
    # Turning: the wheels' force at radius r against the robot's moment of inertia. a / r would treat
    # the whole mass as sitting at the wheels, and understate it about 1.5x for a real robot.
    moi, _ = project.moi()
    alpha = mass * a * r / moi if moi and moi > 0 else a / r
    return {"max_speed": v, "max_speed_source": f"{src.replace(os.sep, '/')} MAX_SPEED" if vmax else "the drive's free speed",
            "max_accel": a, "accel_limited_by": "grip" if mu * G <= force / mass else f"the {lim:.0f} A current limit",
            "max_ang_vel_deg": math.degrees(v / r), "max_ang_accel_deg": math.degrees(alpha), "radius_m": r}


def _row(rows, key, pp_value, want, source, tol=None, fix=True, note=""):
    if want is None:
        status = "unknown"
    elif pp_value is None:
        status = "missing"
    elif isinstance(want, tuple):
        status = "ok" if pp_value in want else "differs"
    elif isinstance(want, (int, float)) and not isinstance(want, bool):
        status = "ok" if abs(float(pp_value) - float(want)) <= (tol or 0) else "differs"
    else:
        status = "ok" if pp_value == want else "differs"
    value = want[0] if isinstance(want, tuple) else want
    rows.append({"key": key, "pathplanner": pp_value, "code": value, "source": source, "status": status,
                 "fix": fix and status in ("differs", "missing") and value is not None, "note": note})


def robot_model(project, pp):
    """Every robot setting PathPlanner plans with, against its source of truth."""
    rows = []
    kind = project.drive_kind()
    inv = (project.tune.get("motors") or {}) if project.data.get("slothtune.json") else {}
    _row(rows, "holonomicMode", pp.get("holonomicMode"), True, "swerve")
    _row(rows, "driveMotorType", pp.get("driveMotorType"), PP_MOTOR.get(kind),
         f"YAGSL drive motor ({kind}" + (f", {inv['drive']} in slothtune.json" if inv.get("drive") else "") + ")")
    _row(rows, "driveGearing", pp.get("driveGearing"), round(project.drive_gear(), 4),
         "modules/physicalproperties.json", 0.005)
    _row(rows, "driveWheelRadius", pp.get("driveWheelRadius"), round(project.wheel_d_in() * 0.0254 / 2, 5),
         "modules/physicalproperties.json (wheel diameter)", 0.0005)
    vmax, src, arg = project.create_swerve_max_speed()
    _row(rows, "maxDriveSpeed", pp.get("maxDriveSpeed"),
         round(vmax, 3) if vmax else round(project.max_module_speed(), 3),
         f"{src.replace(os.sep, '/')} ({arg})" if vmax else "the drive's free speed", 0.05)
    lim = project.phys.get("currentLimit", {}).get("drive")
    _row(rows, "driveCurrentLimit", pp.get("driveCurrentLimit"), float(lim) if lim is not None else None,
         "modules/physicalproperties.json", 0.5)
    cof = project.phys.get("wheelGripCoefficientOfFriction")
    _row(rows, "wheelCOF", pp.get("wheelCOF"), float(cof) if cof is not None else None,
         "modules/physicalproperties.json", 0.02)
    by_corner = {}
    for n in project.module_names():
        c = _corner(n)
        if c:
            by_corner[c] = (n, project.module(n)["location"])
    for c in CORNERS:
        n, loc = by_corner.get(c, (c, None))
        _row(rows, f"{c}ModuleX", pp.get(f"{c}ModuleX"), round(loc["front"] * 0.0254, 4) if loc else None,
             f"modules/{n}.json location.front", 0.005)
        _row(rows, f"{c}ModuleY", pp.get(f"{c}ModuleY"), round(loc["left"] * 0.0254, 4) if loc else None,
             f"modules/{n}.json location.left", 0.005)
    mass = project.tune.get("robotMassKg") if project.data.get("slothtune.json") else None
    _row(rows, "robotMass", pp.get("robotMass"), float(mass) if mass else None,
         "slothtune.json robotMassKg (weighed)" if mass else "not weighed yet: Calibrate tab", 0.25,
         note="" if mass or abs(float(pp.get("robotMass", 0)) - Y.PP_DEFAULT_MASS) > 0.5
         else "PathPlanner's default: weigh the robot")
    moi = project.tune.get("robotMoiKgM2") if project.data.get("slothtune.json") else None
    est, _ = project.moi()
    _row(rows, "robotMOI", pp.get("robotMOI"), float(moi) if moi else None,
         "slothtune.json robotMoiKgM2 (measured)" if moi else f"not measured yet (estimate {est:.2f}): Calibrate tab",
         0.05, note="" if moi or abs(float(pp.get("robotMOI", 0)) - Y.PP_DEFAULT_MOI) > 0.001
         else "PathPlanner's default: measure it")
    return rows


def _walk(cmd, named, paths):
    t, d = (cmd or {}).get("type"), (cmd or {}).get("data") or {}
    if t == "named" and d.get("name"):
        named.append(d["name"])
    if t == "path" and d.get("pathName"):
        paths.append(d["pathName"])
    for c in d.get("commands") or []:
        _walk(c, named, paths)


def _limits(where, c, cap, F):
    # (key, capability, PathPlanner's unit, the team's unit and factor, what it is): PathPlanner keeps
    # and shows speeds in m/s, so the words give its number too, to find it there.
    checks = [("maxVelocity", "max_speed", "m/s", "ft/s", U.FT_PER_M, "speed"),
              ("maxAcceleration", "max_accel", "m/s²", "ft/s²", U.FT_PER_M, "acceleration"),
              ("maxAngularVelocity", "max_ang_vel_deg", "deg/s", "deg/s", 1.0, "turn rate"),
              ("maxAngularAcceleration", "max_ang_accel_deg", "deg/s²", "deg/s²", 1.0, "turn acceleration")]
    for key, capkey, unit, team, k, what in checks:
        v = c.get(key)
        if v is not None and v > cap[capkey] * SLACK:
            F.append({"level": "warn", "kind": "limits",
                      "title": f"{where}: {what} limit {v * k:.3g} {team} is more than the robot can do ({cap[capkey] * k:.3g} {team})",
                      "why": ("" if k == 1.0 else f"PathPlanner has it as {v:g} {unit}. ")
                             + "PathPlanner will plan for it and the robot will fall behind the path. "
                             + ("Top speed comes from " + cap["max_speed_source"] + "." if capkey == "max_speed" else
                                "Acceleration is limited by " + cap["accel_limited_by"] + "." if "accel" in capkey else
                                "Turning is the top speed over the module radius.")})
    if c.get("unlimited"):
        F.append({"level": "info", "kind": "limits", "title": f"{where}: constraints set to unlimited",
                  "why": "The robot will be asked for whatever the path needs. Fine for testing, not for a match."})


def check(project):
    """Every finding, the robot-model rows, and the fixes: ``{"rows", "findings", "fixes", ...}``."""
    base = _pp_dir(project)
    pp = project.pathplanner
    autos = sorted(glob.glob(os.path.join(base, "autos", "*.auto")))
    paths = {os.path.splitext(os.path.basename(f))[0]: f for f in glob.glob(os.path.join(base, "paths", "*.path"))}
    code = "\n".join(project.java.values())
    uses_pp = "pathplanner" in code.lower()
    F = []
    if pp is None:
        return {"used": uses_pp or bool(autos), "rows": [], "fixes": [], "findings": [] if not (uses_pp or autos) else [
            {"level": "error", "kind": "model", "title": "The code uses PathPlanner but there is no settings.json",
             "why": "RobotConfig.fromGUISettings() reads deploy/pathplanner/settings.json; open the project "
                    "in the PathPlanner app and set the robot config."}]}
    rows = robot_model(project, pp)
    differs = [r for r in rows if r["status"] in ("differs", "missing")]
    if differs:
        F.append({"level": "error" if len(differs) >= 3 else "warn", "kind": "model",
                  "title": f"PathPlanner's robot model disagrees with the code ({len(differs)} settings)",
                  "why": "PathPlanner plans every auto from its own copy of the robot: "
                         + "; ".join(f"{r['key']} {r['pathplanner']} vs {r['code']}" for r in differs)
                         + ". Make PathPlanner match (Config tab), then reopen the PathPlanner app so it "
                           "doesn't write its old values back."})
    for r in rows:
        if r["note"]:
            F.append({"level": "warn", "kind": "model", "title": f"{r['key']} {r['pathplanner']}: {r['note']}",
                      "why": "PathPlanner uses mass for how hard the robot can accelerate and the moment of "
                             "inertia for how hard it can start and stop turning. Calibrate tab: Mass and "
                             "moment of inertia."})
    if "RobotConfig.fromGUISettings" not in code and "new RobotConfig(" in code:
        F.append({"level": "info", "kind": "model", "title": "The robot config is built in code, not read from PathPlanner",
                  "why": "Then the app's settings.json only affects path previews; compare the code's own "
                         "RobotConfig with the YAGSL files by hand."})

    cap = capabilities(project)
    _limits("Default limits (new paths)", {"maxVelocity": pp.get("defaultMaxVel"),
                                           "maxAcceleration": pp.get("defaultMaxAccel"),
                                           "maxAngularVelocity": pp.get("defaultMaxAngVel"),
                                           "maxAngularAcceleration": pp.get("defaultMaxAngAccel")}, cap, F)
    named_used = {}
    for name, f in sorted(paths.items()):
        try:
            d = _read(f)
        except (OSError, ValueError):
            F.append({"level": "error", "kind": "names", "title": f"Path '{name}' can't be read", "why": f})
            continue
        if not d.get("useDefaultConstraints", True):
            _limits(f"Path '{name}'", d.get("globalConstraints") or {}, cap, F)
        for z in d.get("constraintZones") or []:
            _limits(f"Path '{name}', zone '{z.get('name', '')}'", z.get("constraints") or {}, cap, F)
        for mk in d.get("eventMarkers") or []:
            n, p = [], []
            _walk(mk.get("command"), n, p)
            for x in n:
                named_used.setdefault(x, set()).add(f"path '{name}'")
    for f in autos:
        name = os.path.splitext(os.path.basename(f))[0]
        try:
            d = _read(f)
        except (OSError, ValueError):
            F.append({"level": "error", "kind": "names", "title": f"Auto '{name}' can't be read", "why": f})
            continue
        n, p = [], []
        _walk(d.get("command"), n, p)
        for x in n:
            named_used.setdefault(x, set()).add(f"auto '{name}'")
        for x in sorted(set(p) - set(paths)):
            F.append({"level": "error", "kind": "names", "title": f"Auto '{name}' uses path '{x}', which doesn't exist",
                      "why": "The auto fails to load. Renamed or deleted in the PathPlanner app?"})
    registered = set(re.findall(r'NamedCommands\.registerCommand\(\s*"([^"]+)"', code))
    # Names the team keeps unregistered on purpose ("Shoot B", decision 16) stay listed, as warnings,
    # so CI's PathPlanner check isn't red on every run and then ignored.
    known = set(((project.data.get("slothtune.json") or {}).get("pathplanner") or {}).get("knownUnregistered") or [])
    for x in sorted(set(named_used) - registered):
        # Never suggest renaming it: only the auto's author knows which command it means (the team
        # keeps "Shoot B" by name for exactly that reason).
        F.append({"level": "warn" if x in known else "error", "kind": "names",
                  "title": f"Named command '{x}' is used by {', '.join(sorted(named_used[x]))} but the code never registers it"
                           + (" (kept on purpose: slothtune.json knownUnregistered)" if x in known else ""),
                  "why": "PathPlanner skips it with only a console warning, so that step of the auto silently "
                         + ("does nothing. The team keeps it that way on purpose (pathplanner.knownUnregistered "
                            "in slothtune.json); take it off that list once the command is registered."
                            if x in known else
                            "does nothing. Ask whoever wrote the auto which command it means, then register it in "
                            "the robot code with NamedCommands.registerCommand. This doesn't affect swerve tuning.")})
    for x in sorted(registered - set(named_used)):
        F.append({"level": "info", "kind": "names", "title": f"Named command '{x}' is registered but no auto uses it",
                  "why": "Harmless; listed so a typo on either side is easy to spot."})
    auto_names = {os.path.splitext(os.path.basename(f))[0] for f in autos}
    for pat, kind, have in ((r'(?:buildAuto|PathPlannerAuto)\(\s*"([^"]+)"', "auto", auto_names),
                            (r'PathPlannerPath\.fromPathFile\(\s*"([^"]+)"', "path", set(paths))):
        for x in sorted(set(re.findall(pat, code)) - have):
            F.append({"level": "error", "kind": "names", "title": f"The code loads {kind} '{x}', which doesn't exist",
                      "why": f"Check the spelling against the PathPlanner app's {kind} list; names are case- and "
                             "space-sensitive."})
    order = {"error": 0, "warn": 1, "info": 2}
    F.sort(key=lambda f: order[f["level"]])
    return {"used": True, "rows": rows, "findings": F, "capabilities": cap,
            "fixes": [(r["key"], r["code"]) for r in rows if r["fix"]],
            "named": {"used": {k: sorted(v) for k, v in named_used.items()}, "registered": sorted(registered)}}


def fixed_text(project, fixes):
    """settings.json with the fixes written in, everything else byte for byte."""
    path = settings_path(project)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for key, value in fixes:
        text = Y.json_set(text, (key,), value)
    return path, text
