"""The Systems tab's model: the robot's mechanisms grouped by subsystem, each tunable one's physics,
limits and safe test, and what a test of it showed.

* **Groups**: the code's subsystems (each class extending SubsystemBase, with the motors it gives
  the motor guard) and the design file's ``subsystem`` field, merged by name.
* **Tunable mechanisms**: what the robot code registers (``TunableSystem``), with its live state.
* **Settings**, in swervetune.json's ``"systems"``, one entry per mechanism: ``min``, ``max`` (its
  limits, found by moving it by hand), ``maxVelocity``, ``maxAccel`` (the team's caps: the robot
  enforces these four), ``link`` (its ReCalc or AMBcalc link) or ``physics`` (the same numbers typed in from
  the AMB spreadsheet), and ``unitsPerRadian`` (its units per radian of the mechanism, or for a
  flywheel per rad/s) when the units don't say.
"""

from __future__ import annotations

import math
import os
import re

from . import advisor, mechanics, wiring

TWO_PI = 2 * math.pi


# ---------------------------------------------------------------------------- groups


def code_subsystems(project):
    """``{class name: [motor names]}`` for each class extending SubsystemBase, from the motors it
    hands the motor guard (the swerve modules' motors count as the drive train)."""
    out = {}
    stems = {}
    for rel, src in (getattr(project, "java", None) or {}).items():
        m = re.search(r"class\s+(\w+)\s+extends\s+SubsystemBase", src)
        if m:
            stems[os.path.basename(rel)] = m.group(1)
            out.setdefault(m.group(1), [])
    for d in wiring.discover(project):
        src = d.get("source") or ""
        if src.startswith("swerve/"):
            out.setdefault("Drive train", []).append(d["name"])
        elif src in stems:
            out[stems[src]].append(d["name"])
    # The drive subsystem's motors come from YAGSL's files, not its class: one group.
    for cls in [c for c, ms in out.items() if not ms and re.search(r"drive|swerve", c, re.I)]:
        if "Drive train" in out:
            del out[cls]
    return out


def in_code(project):
    """``{name: kind}`` for each mechanism the robot code registers, read from its source
    (``tune.system("Shooter", TunableSystem.Kind.FLYWHEEL)``): what it will register once it runs."""
    out = {}
    for src in (getattr(project, "java", None) or {}).values():
        for m in re.finditer(r'\.system\(\s*"([^"]+)"\s*,\s*(?:TunableSystem\.)?Kind\.(\w+)', src):
            out[m.group(1)] = m.group(2)
    return out


def groups(project, design=None, registered=()):
    """Each group: its name, where it was found (code, design), its motors and sensors, and the
    registered mechanisms in it (by a shared motor, or by name).

    A design subsystem joins the code's subsystem of the same name, or the one that holds all its
    motors: a design file drafted from the code calls the swerve motors "Drive" and a Feeder's
    motors by their own names, and those are the code's Drive train and Feeder. The design's name
    is kept in the group's ``aka``."""
    g = {}

    def grp(name):
        return g.setdefault(name, {"name": name, "from": [], "aka": [], "motors": [], "sensors": [], "systems": []})

    code = code_subsystems(project)
    for name, motors in code.items():
        e = grp(name)
        e["from"].append("code")
        e["motors"] += [m for m in motors if m not in e["motors"]]
    by_lower = {n.lower(): n for n in code}
    owner = {m: n for n, ms in code.items() for m in ms}
    design_motors = {}
    for d in (design or {}).get("motors") or []:
        if d.get("subsystem") and d.get("name"):
            design_motors.setdefault(d["subsystem"], []).append(d["name"])

    def home(sub):
        if sub.lower() in by_lower:
            return by_lower[sub.lower()]
        owners = {owner.get(m) for m in design_motors.get(sub) or []}
        return owners.pop() if len(owners) == 1 and None not in owners else sub

    for kind in ("motors", "sensors"):
        for d in (design or {}).get(kind) or []:
            if d.get("subsystem") and d.get("name"):
                name = home(d["subsystem"])
                e = grp(name)
                if "design" not in e["from"]:
                    e["from"].append("design")
                if d["subsystem"] != name and d["subsystem"] not in e["aka"]:
                    e["aka"].append(d["subsystem"])
                if d["name"] not in e[kind]:
                    e[kind].append(d["name"])
    def squash(x):
        return re.sub(r"[^a-z0-9]", "", x.lower())

    for s in registered:
        # By a shared motor, else the subsystem its name starts with, the longest: "Shooter pivot" is
        # ShooterPivot's, not Shooter's.
        named = [e for e in g.values() if squash(s["name"]).startswith(squash(e["name"]))]
        home = next((e for e in g.values() if set(s.get("motors") or []) & set(e["motors"])), None) \
            or max(named, key=lambda e: len(squash(e["name"])), default=None) \
            or grp(s["name"])
        home["systems"].append(s["name"])
    return sorted(g.values(), key=lambda e: (e["name"] != "Drive train", e["name"]))


# ---------------------------------------------------------------------------- settings and physics


def settings(project):
    return ((project.data.get("swervetune.json") or {}).get("systems") or {}) if project else {}


def physics(entry, kind=None):
    """The mechanism's physics from its ReCalc or AMBcalc link, or typed-in numbers; None without
    either. ``kind`` is how the code registered it, which an AMBcalc mechanism link needs."""
    entry = entry or {}
    if entry.get("link"):
        return mechanics.from_link(entry["link"], kind)
    p = entry.get("physics")
    if isinstance(p, dict) and p.get("motor") in mechanics.MOTORS and p.get("ratio"):
        return dict(p)
    return None


def scale(entry, units, mech):
    """How many of the system's units are one radian of the mechanism (for a flywheel, one rad/s;
    for an elevator, one meter). The entry's own, else from its units and gear ratio; None unknown."""
    if (entry or {}).get("unitsPerRadian"):
        return float(entry["unitsPerRadian"])
    u, g = (units or "").lower(), (mech or {}).get("ratio")
    if (mech or {}).get("kind") == "elevator":
        # One meter of travel: the drum turns 1 / (pi d) times, the motor g times that.
        d = mech.get("spool_diameter_m")
        if "rot" in u and d:
            return (g if "motor" in u and g else 1.0) / (math.pi * d)
        return {"m": 1.0, "meter": 1.0, "meters": 1.0, "cm": 100.0, "mm": 1000.0,
                "in": 1 / 0.0254, "inch": 1 / 0.0254, "inches": 1 / 0.0254}.get(u)
    if "motor" in u and "rot" in u and g:
        return g / TWO_PI
    if "rpm" in u:
        # A motor's encoder in RPM is through the gearbox; "wheel RPM" is the mechanism's own.
        return (1 if "wheel" in u or "mechanism" in u else (g or 1)) * 60 / TWO_PI
    if "deg" in u:
        return 180 / math.pi
    if u.startswith("rad"):
        return 1.0
    if "rot" in u:
        return 1 / TWO_PI
    if u in ("m", "meter", "meters"):
        return 1.0
    return None


def plan(entry, registered):
    """The safe test for a registered mechanism: ``{"ok", "vmax", "amax", "a", "b", "why"}``, or
    ``{"ok": False, "missing": [...]}`` saying what it still needs."""
    entry = entry or {}
    missing = []
    try:
        mech = physics(entry, registered.get("kind"))
    except ValueError as e:
        return {"ok": False, "missing": [f"its calculator link doesn't read: {e}"]}
    if not mech:
        missing.append("its physics: a ReCalc or AMBcalc link, or the numbers from the AMB spreadsheet")
    positional = registered.get("kind") in ("PIVOT", "ELEVATOR")
    lo, hi = registered.get("min"), registered.get("max")
    has_limits = all(isinstance(x, (int, float)) and math.isfinite(x) for x in (lo, hi)) and hi > lo
    if positional and not has_limits:
        missing.append("its limits: move it by hand to both ends")
    k = scale(entry, registered.get("units"), mech)
    if mech and k is None:
        missing.append(f"how many {registered.get('units') or 'units'} are one radian of it")
    if missing:
        return {"ok": False, "missing": missing}
    team = entry.get("maxVelocity") or registered.get("max_velocity")
    p = mechanics.test_plan(mech, (lo, hi) if positional else None, k,
                            team if isinstance(team, (int, float)) and math.isfinite(team) else None)
    p.update(ok=True, scale=k, feedforward=mechanics.feedforward(mech), kind=mech["kind"])
    return p


# ---------------------------------------------------------------------------- what a test showed


def _legs(t, goal):
    """(start index, goal) each time the goal changes."""
    out = []
    for i, g in enumerate(goal):
        if g == g and (not out or g != out[-1][1]):
            out.append((i, g))
    return out


def step_report(doc, all_settings=None):
    """A system_step run: per move, how closely it followed the moving goal, how far it overshot,
    how long it took to settle and what it settled at, and the volts it held with against what the
    physics say; with advice on the gains."""
    ch = doc.get("channels") or {}
    t, pos, vel, sp, goal = (ch.get(k) or [] for k in ("t", "pos", "vel", "sp", "goal"))
    notes = doc.get("notes") or []
    m = next((re.match(r"system: (.+) \((\w+), (.*)\)$", n) for n in notes if n.startswith("system: ")), None)
    name, kind, units = (m.group(1), m.group(2), m.group(3)) if m else ("the mechanism", "PIVOT", "")
    entry = (all_settings or {}).get(name)
    positional = kind in ("PIVOT", "ELEVATOR")
    meas = pos if positional else vel
    volts = [v for k, v in sorted(ch.items()) if re.fullmatch(r"volts\d+", k)]
    sim = doc.get("env") == "SIM"
    # A simulated mechanism with physics (the Examples robot) moves; one without never does.
    seen = [x for x in meas if x == x]
    modeled = bool(seen) and max(seen) - min(seen) > 1e-6
    F, moves = [], []
    legs = _legs(t, goal)
    for n, (i0, g) in enumerate(legs):
        i1 = legs[n + 1][0] if n + 1 < len(legs) else len(t)
        start = meas[i0] if i0 < len(meas) else float("nan")
        step = g - (legs[n - 1][1] if n else start)
        if not step or step != step:
            continue
        # The goal reaches its target when sp does; after that, the hold.
        arrive = next((i for i in range(i0, i1) if i < len(sp) and abs(sp[i] - g) < 1e-9), i1 - 1)
        track = max((abs(meas[i] - sp[i]) for i in range(i0, arrive) if i < len(meas) and meas[i] == meas[i]), default=0.0)
        hold = [meas[i] for i in range(arrive, i1) if i < len(meas) and meas[i] == meas[i]]
        if not hold:
            continue
        past = max(((x - g) * math.copysign(1, step) for x in hold), default=0.0)
        overshoot = max(0.0, past) / abs(step) * 100
        tail = hold[-max(1, len(hold) // 4):]
        final = sum(tail) / len(tail)
        err = (final - g) / abs(step) * 100 if positional else (final - g) / abs(g) * 100 if g else 0.0
        band = 0.02 * abs(step) if positional else 0.03 * abs(g or step)
        settle = next((t[arrive + j] - t[arrive] for j in range(len(hold))
                       if all(abs(x - g) <= band for x in hold[j:])), None)
        hv = [sum(v[i] for v in volts if i < len(v)) / max(1, len(volts)) for i in range(arrive, i1)]
        hv = [x for x in hv if x == x]
        moves.append({"goal": g, "step": step, "track_error": track, "overshoot_pct": overshoot, "error_pct": err,
                      "settle_s": settle, "hold_volts": sum(hv[-len(tail):]) / len(tail) if hv else None})
    if not moves:
        return {"test": "system_step", "env": doc.get("env", ""), "summary": "Nothing to judge: no move was recorded.",
                "findings": [], "targets": [], "score": None, "next": None, "modules": {}, "moves": []}
    worst_os = max(mv["overshoot_pct"] for mv in moves)
    worst_err = max(abs(mv["error_pct"]) for mv in moves)
    slow = [mv for mv in moves if mv["settle_s"] is None]
    gains = (doc.get("gains") or {})
    plan_ = plan(entry, {"kind": kind, "units": units, "min": (doc.get("meta") or {}).get("min"),
                         "max": (doc.get("meta") or {}).get("max")}) if entry else {"ok": False}
    ff = plan_.get("feedforward") if plan_.get("ok") else None
    k = plan_.get("scale") if plan_.get("ok") else None
    actions = []
    if modeled or not sim:
        if worst_os > 15:
            F.append(advisor.finding("warn", f"{name} overshoots {worst_os:.0f}%",
                                     "It passes the goal and comes back: less kP, or some kD to brake it."))
        if worst_err > (2 if positional else 3):
            missed = [mv for mv in moves if abs(mv["error_pct"]) > (2 if positional else 3)]
            word = "short of" if all(mv["error_pct"] * math.copysign(1, mv["step"]) < 0 for mv in missed) else "off"
            why = f"It settles {worst_err:.1f}% {word} the goal: "
            if not positional and ff and k:
                kv = ff["kV"] / k
                why += (f"the physics say a kV of {kv:.4g} volts per {units} holds it at speed "
                        "(the SPARK's own feedforward), so kP only has to correct what is left.")
                actions.append({"type": "system_gains", "values": {f"{name}/kV": round(kv, 8)},
                                "label": f"Try kV {kv:.4g} (from the physics)"})
            else:
                why += ("more kP pulls it the rest of the way; a mechanism that sags under gravity wants "
                        "kG (or kCos for an arm) so kP isn't holding it up.")
            F.append(advisor.finding("warn", f"{name} settles {worst_err:.1f}% {word} its goals", why))
        if slow:
            F.append(advisor.finding("warn", f"{name} never settled within {'2' if positional else '3'}% on "
                                     f"{len(slow)} of {len(moves)} moves",
                                     "It is still moving (ringing) or still short when the next move starts: watch the graph."))
        if ff and volts and not positional:
            held = [mv for mv in moves if mv["hold_volts"] is not None and mv["goal"]]
            if held and k:
                mv = held[-1]
                want = ff["kV"] * mv["goal"] / k
                F.append(advisor.finding("info", f"Holding {mv['goal']:.0f} {units} took {mv['hold_volts']:.2f} V; "
                                         f"the physics say {want:.2f} V",
                                         "Far apart means the physical data (ratio, inertia, motor) or the units are off, "
                                         "or friction the model leaves out."))
    score = None if sim else max(0, round(100 - 2 * worst_os - 5 * worst_err - 10 * len(slow)))
    judged = f"{len(moves)} moves: overshoot up to {worst_os:.0f}%, settled within {worst_err:.1f}% of the goal."
    summary = (judged if not sim else
               f"Simulator, practice only (it never counts for the real robot). {judged}" if modeled else
               "Simulator: the mechanism's physics aren't modeled, so only the sequence was checked.")
    return {"test": "system_step", "env": doc.get("env", ""), "summary": summary, "findings": F, "targets": [],
            "score": score, "next": None, "modules": {}, "moves": moves, "actions": actions,
            "system": {"name": name, "kind": kind, "units": units}}


def limits_report(doc):
    """A system_limits run: the range a person moved it through."""
    meta = doc.get("meta") or {}
    notes = doc.get("notes") or []
    m = next((re.match(r"system: (.+) \((\w+), (.*)\)$", n) for n in notes if n.startswith("system: ")), None)
    name, units = (m.group(1), m.group(3)) if m else ("the mechanism", "")
    lo, hi = meta.get("min"), meta.get("max")
    F = []
    if lo is None or hi is None:
        summary = "Nothing was recorded."
    elif hi - lo <= 1e-3 * max(1, abs(lo), abs(hi)):
        summary = "It didn't move: nobody moved it, or its position isn't being read."
        F.append(advisor.finding("error", f"{name} didn't move", "Move it by hand all the way both ways while the "
                                 "readout runs. If it moved and the numbers didn't, the code reads the wrong encoder."))
    else:
        summary = f"{name}: {lo:.4g} to {hi:.4g} {units}."
        F.append(advisor.finding("ok", f"Limits {lo:.4g} to {hi:.4g} {units}",
                                 "Held for this session; save them so the robot keeps them after a restart."))
    return {"test": "system_limits", "env": doc.get("env", ""), "summary": summary, "findings": F, "targets": [],
            "score": None, "next": None, "modules": {}, "limits": {"min": lo, "max": hi, "units": units, "name": name}}
