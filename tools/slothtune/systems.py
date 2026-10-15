"""The Systems tab's model: the robot's mechanisms grouped by subsystem, each tunable one's physics,
limits and safe test, and what a test of it showed.

* **Groups**: the code's subsystems (each class extending SubsystemBase, with the motors it gives
  the motor guard) and the design file's ``subsystem`` field, merged by name.
* **Tunable mechanisms**: what the robot code registers (``TunableSystem``), with its live state.
* **Settings**, in slothtune.json's ``"systems"``, one entry per mechanism: ``min``, ``max`` (its
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
from . import units as U

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
    return ((project.data.get("slothtune.json") or {}).get("systems") or {}) if project else {}


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
                            team if isinstance(team, (int, float)) and math.isfinite(team) else None,
                            units=registered.get("units") or "")
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


# What a mechanism's step test must show to be done tuning (the auto-tuner's targets).
OVERSHOOT_OK = 15.0          # percent of the move
RING_OS = 5.0                # still ringing at the next move with this much overshoot: too much kP
ERROR_OK = {True: 2.0, False: 3.0}   # settled within, percent (positional, velocity)
LAG_OK = 10.0                # following the moving goal within this percent of the move
SLOWER, FASTER = 0.7, 1.5    # kP steps; never more than doubled or halved in one round


def _gain(gains, name, k):
    v = gains.get(f"{name}/{k}")
    return v if isinstance(v, (int, float)) and math.isfinite(v) else None


ANGLE_TO_RAD = {"deg": math.pi / 180, "degree": math.pi / 180, "degrees": math.pi / 180,
                "rad": 1.0, "radian": 1.0, "radians": 1.0}


def run_feedforward(ch, kind, units=""):
    """``{"kS", "kV", "kA", "kG", "r2"}`` fitted from a step test's own volts and speeds (the direct
    fit SysId cross-checks with): ``V = kG + kS*sgn(v) + kV*v + kA*a``, with kG for an elevator, or
    times cos(angle) for a pivot read in degrees or radians. For a mechanism with no physics
    entered; None without enough unsaturated motion or a good fit."""
    from . import analysis as A
    t, vel = ch.get("t") or [], ch.get("vel") or []
    pos = ch.get("pos") or []
    volts = [v for key, v in sorted(ch.items()) if re.fullmatch(r"volts\d+", key)]
    if not volts or len(t) < 40:
        return None
    n = min(len(t), len(vel), *(len(v) for v in volts))
    u = [sum(v[i] for v in volts) / len(volts) for i in range(n)]
    ang = ANGLE_TO_RAD.get((units or "").strip().lower()) if kind == "PIVOT" else None
    grav = kind == "ELEVATOR" or ang is not None
    top = max((abs(x) for x in vel[:n] if x == x), default=0.0)
    if top <= 0:
        return None
    rows, ys = [], []
    for i in range(1, n - 1):
        V, v, dt = u[i], vel[i], t[i + 1] - t[i - 1]
        if not (V == V and v == v) or abs(V) > 11.0 or dt <= 0 or abs(v) < 0.03 * top:
            continue
        a = (vel[i + 1] - vel[i - 1]) / dt
        if a != a:
            continue
        row = [math.copysign(1.0, v), v, a]
        if kind == "ELEVATOR":
            row = [1.0] + row
        elif ang is not None and i < len(pos) and pos[i] == pos[i]:
            row = [math.cos(pos[i] * ang)] + row
        elif ang is not None:
            continue
        rows.append(row)
        ys.append(V)
    if len(rows) < 30:
        return None
    beta, r2 = A.ols(rows, ys)
    if not beta or r2 < 0.8:
        return None
    kG, (kS, kV, kA) = (beta[0], beta[1:]) if grav else (0.0, beta)
    if kV <= 0:
        return None
    return {"kS": kS, "kV": kV, "kA": max(0.0, kA), "kG": kG, "r2": r2}


def tune_options(name, positional, moves, gains, ff=None, k=None, kind="", fit=None):
    """Every change worth trying for a mechanism after its step test, the likeliest first: each
    ``{"title", "why", "action"}`` with a ``gains`` action (its own ``Name/k`` gains only) or a
    ``person`` one (a gain it doesn't have, a kP of 0); ``save`` alone when it meets every target.

    A pivot or elevator: gravity first (kG from the physics, when it has none), then overshoot or
    ringing (kP x0.7), lag behind the moving goal (kV from the physics, then kP x1.5), settling
    short (kP x1.5). A flywheel or roller: kV from the physics, overshoot (kP x0.7), then a steady
    miss (kV scaled by goal over what it reached, kept within half and double; then kP x1.5).
    Without physics entered, kG and kV come from this run's own volts and speeds."""
    if not moves:
        return []
    worst_os = max(mv["overshoot_pct"] for mv in moves)
    worst_err = max(abs(mv["error_pct"]) for mv in moves)
    worst_lag = max(mv.get("track_pct") or 0.0 for mv in moves)
    unsettled = [mv for mv in moves if mv["settle_s"] is None]
    kP, kV, kG = (_gain(gains, name, x) for x in ("kP", "kV", "kG"))
    has = lambda x: f"{name}/{x}" in gains   # noqa: E731
    phys_kv = ff["kV"] / k if ff and ff.get("kV") and k else None
    phys_kg = ff.get("kG") if ff else None
    src_kv = src_kg = "from the physics"
    if phys_kv is None and fit:
        phys_kv, src_kv = fit["kV"], "from this run"
    if phys_kg is None and fit and fit.get("kG"):
        phys_kg, src_kg = fit["kG"], "from this run"
    out = []

    def change(key, value, title, why):
        out.append({"title": title, "why": why, "action": {"type": "gains", "values": {f"{name}/{key}": round(value, 8)}}})

    def kp(factor, title, why):
        if not has("kP"):
            out.append({"title": f"{title}: it has no kP to change", "why": why, "action": {"type": "person"}})
        elif not kP:
            out.append({"title": f"{title}, but its kP is 0", "why": "Give kP a starting value by hand; the tuner scales what is there.",
                        "action": {"type": "person"}})
        else:
            change("kP", kP * factor, f"{title}: kP {kP:.4g} to {kP * factor:.4g}", why)

    if positional:
        if worst_err > ERROR_OK[True] and kind in ("ELEVATOR", "PIVOT") and has("kG") and not kG and phys_kg and phys_kg > 0.02:
            change("kG", phys_kg, f"Add kG {phys_kg:.3g} V ({src_kg})",
                   "Gravity pulls it short of every goal: kG holds it up so kP only has to move it.")
        if worst_os > OVERSHOOT_OK:
            kp(SLOWER, f"Overshoots {worst_os:.0f}%", "It passes the goal and comes back: less kP.")
        elif unsettled and worst_os > RING_OS:
            kp(SLOWER, "Still ringing at the next move", "It swings past and back without settling: less kP.")
        if worst_lag > LAG_OK:
            if has("kV") and not kV and phys_kv:
                change("kV", phys_kv, f"Add kV {phys_kv:.4g} ({src_kv})",
                       "It falls behind the moving goal: kV gives the volts for the speed, so kP only corrects.")
            if worst_os <= OVERSHOOT_OK:
                kp(FASTER, f"Lags {worst_lag:.0f}% behind the moving goal", "It can't keep up with the goal as it moves: more kP.")
        elif (worst_err > ERROR_OK[True] or unsettled) and worst_os <= RING_OS:
            kp(FASTER, f"Settles {worst_err:.1f}% off its goals", "It stops short: more kP pulls it the rest of the way.")
    else:
        if has("kV") and not kV and phys_kv:
            change("kV", phys_kv, f"Add kV {phys_kv:.4g} ({src_kv})", "kV gives the volts for each speed, so kP only corrects what is left.")
        if worst_os > OVERSHOOT_OK:
            kp(SLOWER, f"Overshoots {worst_os:.0f}%", "It passes its speed and comes back: less kP.")
        if worst_err > ERROR_OK[False]:
            ratios = sorted(mv["goal"] / mv["final"] for mv in moves if mv.get("final") and mv["goal"] and mv["goal"] * mv["final"] > 0)
            if kV and ratios:
                r = min(2.0, max(0.5, ratios[len(ratios) // 2]))
                change("kV", kV * r, f"Settles {worst_err:.1f}% off its speed: kV {kV:.4g} to {kV * r:.4g}",
                       "It holds the wrong speed: kV scaled by how far off it settled.")
            if worst_os <= OVERSHOOT_OK:
                kp(FASTER, f"Settles {worst_err:.1f}% off its speed", "It holds the wrong speed: more kP.")
        elif unsettled and worst_os <= OVERSHOOT_OK:
            kp(SLOWER, "Never settles at its speed", "It hunts around its speed: less kP.")
    if not out:
        out.append({"title": "Meets every target", "why": "Save its gains to slothtune.json.", "action": {"type": "save"}})
    return out


def tune_next(name, positional, moves, gains, ff=None, k=None, kind="", fit=None):
    """The first of :func:`tune_options`: the one change to try next, or None without moves."""
    opts = tune_options(name, positional, moves, gains, ff, k, kind, fit)
    return opts[0] if opts else None


def change_key(values, gains):
    """What a change does, to remember one that made things worse: ``(gain, "set"/"up"/"down")``."""
    (k, v), = values.items()
    now = gains.get(k)
    return k, "set" if not now else "up" if v > now else "down"


def step_cost(moves, positional):
    """One number to rank a mechanism's runs by: overshoot, the miss, lag and moves never settled
    (lower is better). The auto-tuner ends on the round with the lowest."""
    if not moves:
        return None
    return round(2 * max(mv["overshoot_pct"] for mv in moves) + 5 * max(abs(mv["error_pct"]) for mv in moves)
                 + (max(mv.get("track_pct") or 0.0 for mv in moves) if positional else 0.0)
                 + 10 * sum(mv["settle_s"] is None for mv in moves), 3)


def step_report(doc, all_settings=None, gains=None):
    """A system_step run: per move, how closely it followed the moving goal, how far it overshot,
    how long it took to settle and what it settled at, and the volts it held with against what the
    physics say; with advice on the gains, and (from the gains it ran with) the one change to try
    next."""
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
    sizes = [abs(g - legs[n - 1][1]) for n, (_, g) in enumerate(legs) if n]
    biggest = max(sizes, default=0.0)
    for n, (i0, g) in enumerate(legs):
        # A pivot's or elevator's first leg only takes it from wherever it was to the first goal:
        # its size is chance (none at all when the last test left it there), so it isn't judged.
        if positional and n == 0 and len(legs) > 1:
            continue
        i1 = legs[n + 1][0] if n + 1 < len(legs) else len(t)
        start = meas[i0] if i0 < len(meas) else float("nan")
        step = g - (legs[n - 1][1] if n else start)
        # A tiny step makes every percentage of it huge: judged only against the moves that matter.
        if not step or step != step or (biggest and abs(step) < 0.05 * biggest):
            continue
        # The goal reaches its target when sp does; after that, the hold.
        arrive = next((i for i in range(i0, i1) if i < len(sp) and abs(sp[i] - g) < 1e-9), i1 - 1)
        track = max((abs(meas[i] - sp[i]) for i in range(i0, arrive) if i < len(meas) and meas[i] == meas[i]), default=0.0)
        hold = [meas[i] for i in range(arrive, i1) if i < len(meas) and meas[i] == meas[i]]
        if not hold:
            continue
        tail = hold[-max(1, len(hold) // 4):]
        final = sum(tail) / len(tail)
        # Overshoot is the swing past where it settled: settling off the goal is the error's.
        past = max(((x - final) * math.copysign(1, step) for x in hold), default=0.0)
        overshoot = max(0.0, past) / abs(step) * 100
        err = (final - g) / abs(step) * 100 if positional else (final - g) / abs(g) * 100 if g else 0.0
        band = 0.02 * abs(step) if positional else 0.03 * abs(g or step)
        settle = next((t[arrive + j] - t[arrive] for j in range(len(hold))
                       if all(abs(x - g) <= band for x in hold[j:])), None)
        hv = [sum(v[i] for v in volts if i < len(v)) / max(1, len(volts)) for i in range(arrive, i1)]
        hv = [x for x in hv if x == x]
        moves.append({"goal": g, "step": step, "track_error": track, "track_pct": track / abs(step) * 100,
                      "overshoot_pct": overshoot, "error_pct": err, "final": final,
                      "settle_s": settle, "hold_volts": sum(hv[-len(tail):]) / len(tail) if hv else None})
    if not moves:
        return {"test": "system_step", "env": doc.get("env", ""), "summary": "Nothing to judge: no move was recorded.",
                "findings": [], "targets": [], "score": None, "next": None, "modules": {}, "moves": []}
    worst_os = max(mv["overshoot_pct"] for mv in moves)
    worst_err = max(abs(mv["error_pct"]) for mv in moves)
    slow = [mv for mv in moves if mv["settle_s"] is None]
    gains = gains or doc.get("gains") or {}
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
                said, f_said = U.system_unit(units)   # its speed, in the team's units
                F.append(advisor.finding("info", f"Holding {mv['goal'] * f_said:.0f} {said} took {mv['hold_volts']:.2f} V; "
                                         f"the physics say {want:.2f} V",
                                         "Far apart means the physical data (ratio, inertia, motor) or the units are off, "
                                         "or friction the model leaves out."))
    score = None if sim else max(0, round(100 - 2 * worst_os - 5 * worst_err - 10 * len(slow)))
    judged = f"{len(moves)} moves: overshoot up to {worst_os:.0f}%, settled within {worst_err:.1f}% of the goal."
    summary = (judged if not sim else
               f"Simulator, practice only (it never counts for the real robot). {judged}" if modeled else
               "Simulator: the mechanism's physics aren't modeled, so only the sequence was checked.")
    judged_ok = modeled or not sim
    options = tune_options(name, positional, moves, gains, ff, k, kind, run_feedforward(ch, kind, units)) if judged_ok else []
    nxt = options[0] if options else None
    return {"test": "system_step", "env": doc.get("env", ""), "summary": summary, "findings": F, "targets": [],
            "score": score, "cost": step_cost(moves, positional) if judged_ok else None, "next": nxt, "options": options,
            "modules": {}, "moves": moves, "actions": actions,
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
        said, f_said = U.system_unit(units)   # the words in the team's units; "limits" keeps the code's
        summary = f"{name}: {lo * f_said:.4g} to {hi * f_said:.4g} {said}."
        F.append(advisor.finding("ok", f"Limits {lo * f_said:.4g} to {hi * f_said:.4g} {said}",
                                 "Held for this session; save them so the robot keeps them after a restart."))
    return {"test": "system_limits", "env": doc.get("env", ""), "summary": summary, "findings": F, "targets": [],
            "score": None, "next": None, "modules": {}, "limits": {"min": lo, "max": hi, "units": units, "name": name}}


# ---------------------------------------------------------------------------- model-based tuning


# The gains each SPARK closed-loop mode uses (REV applies kV and kA only in some of them). A
# position loop the code profiles on the roboRIO (plain Position) gets no speed feedforward.
MODE_GAINS = {
    "Position": ("kP", "kD", "kG", "kCos"),
    "MAXMotionPosition": ("kP", "kD", "kS", "kV", "kA", "kG", "kCos", "mmCruise", "mmAccel"),
    "Velocity": ("kP", "kI", "kS", "kV"),
    "MAXMotionVelocity": ("kP", "kI", "kS", "kV", "kA", "mmAccel"),
}
MOTOR_LABEL = {"NEO Vortex": "NEO Vortex", "NEO 2.0": "NEO 2.0", "NEO V1.1": "NEO V1.1", "NEO 550": "NEO 550"}


def _system_note(doc):
    m = next((re.match(r"system: (.+) \((\w+), (.*)\)$", n) for n in doc.get("notes") or [] if n.startswith("system: ")), None)
    return (m.group(1), m.group(2), m.group(3)) if m else ("the mechanism", "PIVOT", "")


def _finite(xs):
    return [x for x in xs if isinstance(x, (int, float)) and x == x]


def _slope(xs, ys):
    """Least-squares slope of ys against xs over the pairs both have; None without spread."""
    pairs = [(x, y) for x, y in zip(xs, ys) if isinstance(x, (int, float)) and isinstance(y, (int, float))
             and x == x and y == y]
    if len(pairs) < 10:
        return None
    mx = sum(p[0] for p in pairs) / len(pairs)
    my = sum(p[1] for p in pairs) / len(pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    return sum((p[0] - mx) * (p[1] - my) for p in pairs) / sxx if sxx > 1e-12 else None


def id_report(doc, entry=None, registered=None, motor=None, aggressiveness=1.0):
    """A system_id run (model-based tuning, decision 75): the mechanism's physics fitted from what it
    did (:func:`modeltune.fit_held`), its speed reading's delay and a filter to try (decision 78), the
    battery it held under load (decision 77), and the SPARK settings worked out from them for the
    mode its code runs the SPARK in (:func:`model_gains`).

    ``entry`` is its slothtune.json settings (physics, to compare with); ``registered`` the robot's
    view of it (its gains and their ranges, its control mode); ``motor`` its leading motor:
    ``{"motor", "limit_a", "count", "controller", "settings"}``. The fit is in the SPARK's own units
    (its closed loop's sensor, conversion factors and all), so the gains need no conversion but REV's.
    """
    from . import modeltune as M

    ch = doc.get("channels") or {}
    meta = doc.get("meta") or {}
    name, kind, units = _system_note(doc)
    registered = registered or {}
    motor = motor or {}
    positional = kind in ("PIVOT", "ELEVATOR")
    sim = doc.get("env") == "SIM"
    base = {"test": "system_id", "env": doc.get("env", ""), "targets": [], "score": None, "cost": None,
            "next": None, "options": [], "system": {"name": name, "kind": kind, "units": units}}
    t = ch.get("t") or []
    if sim and ch.get("loop"):
        t = [l * 0.02 for l in ch["loop"]]   # the simulator's physics: a 20 ms step each loop
    n = len(t)
    if n < 40:
        return dict(base, summary="Too short to fit: it stopped before it had moved much.", findings=[])
    pos = (ch.get("pos") or [float("nan")] * n)[:n]
    vel = (ch.get("vel") or [float("nan")] * n)[:n]
    spos, svel = (ch.get("spos") or [])[:n], (ch.get("svel") or [])[:n]
    cmd = (ch.get("cmd") or [])[:n]
    applied = (ch.get("volts0") or [])[:n]
    use_applied = len(_finite(applied)) >= 0.9 * n and len(applied) == n
    volts = applied if use_applied else cmd
    spark_units = len(_finite(spos)) >= 0.9 * n and (max(_finite(spos)) - min(_finite(spos))) > 0
    x = spos if spark_units else pos
    F = []

    # The units: the SPARK's position per the code's, and its speed reading per its position a second.
    delay = M.delay(t, spos, svel) if spark_units and len(_finite(svel)) >= 0.9 * n else None
    ratio_v = M.speed_ratio(t, spos, svel, delay or 0.0) if delay is not None else None
    if positional:
        per = _slope(spos, pos) if spark_units else 1.0      # code units per SPARK unit
    else:
        per = M.speed_ratio(t, spos, vel, delay or 0.0) if spark_units else 1.0   # code speed per SPARK unit/s
    mech = None
    try:
        mech = physics(entry, kind)
    except ValueError:
        mech = None
    k_units = scale(entry, units, mech)
    arpu = ANGLE_TO_RAD.get((units or "").strip().lower()) or (1.0 / k_units if k_units else None)
    angle = None
    if kind == "PIVOT":
        if arpu and len(_finite(pos)) >= 0.9 * n:
            angle = [p * arpu if p == p else float("nan") for p in pos]
        else:
            F.append(advisor.finding("warn", f"Say how many {units or 'units'} are one radian of {name}",
                                     "An arm's gravity follows the cosine of its angle: without the angle the fit "
                                     "can't separate gravity from friction. Set unitsPerRadian in its settings."))
    fit = M.fit_held(t, x, volts, kind, angle=angle)
    if not fit.get("ok"):
        return dict(base, summary=f"The fit didn't take: {fit.get('why')}.", findings=F, fit=fit)
    ok = lambda v: v is not None and v == v   # noqa: E731
    sp_units = "its SPARK's units" if spark_units else (units or "its units")

    # The model, shown in the code's units (what a person reads); the gains use the SPARK's.
    shown = {"kS": fit["kS"], "kG": fit["kG"]}
    if ok(per) and per:
        shown["kV"] = fit["kV"] / per
        shown["kA"] = fit["kA"] / per
    model = {k: fit[k] for k in ("kS", "kV", "kA", "kG", "offset_rad", "r2", "samples", "dt", "shift")}
    model["units"] = sp_units

    # The battery it held under its hardest pull (decision 77).
    batt = _finite(ch.get("batt") or [])
    low = min(batt) if batt else None
    vcomp = M.compensation_volts(low) if low and not sim else 12.0 if sim else M.compensation_volts(None)

    # The filter (decision 78): only a speed loop reads it.
    filt = M.filter_suggestion(delay, motor.get("controller") or "SPARK MAX",
                               int(registered.get("gains", {}).get("velMs", {}).get("value") or 0) or None,
                               int(registered.get("gains", {}).get("velDepth", {}).get("value") or 0) or None,
                               speed_loop=not positional)

    # The move the gains are judged on: its planned test, else half its window (or 60% of its top speed).
    plan_ = plan(entry, dict(registered, kind=kind, units=units, min=meta.get("min"), max=meta.get("max"))) if entry else {}
    if positional:
        move_code = abs(plan_["b"] - plan_["a"]) if plan_.get("ok") else 0.5 * abs((meta.get("hi") or 1) - (meta.get("lo") or 0))
    else:
        move_code = plan_.get("b") if plan_.get("ok") and plan_.get("b") else 0.6 * (meta.get("vmax") or 0)
    move = move_code / per if ok(per) and per else move_code
    control = registered.get("control") or ""
    basis = {"name": name, "kind": kind, "model": {k: fit[k] for k in ("kS", "kV", "kA", "kG", "offset_rad")},
             "volts": vcomp, "delay_s": delay or 0.0, "move": move, "current_limit_a": motor.get("limit_a"),
             "motor": MOTOR_LABEL.get(motor.get("motor") or "", "NEO"), "motors": motor.get("count") or 1,
             "ratio_v": ratio_v if ok(ratio_v) and ratio_v else 1.0, "angle_rad_per_unit": (arpu * per) if (arpu and ok(per)) else None,
             "control": control, "spark_units": spark_units,
             # A real SPARK's loop runs every millisecond; REVLib's simulated one once a robot loop.
             "period": 0.02 if sim else M.SPARK_DT,
             # REVLib's simulated SPARK applies kD far harder than a real one (it wrecked the Examples
             # elevator at kD 0.5): the simulator's gains use kP alone.
             "use_kd": not sim,
             "ranges": {k: (g.get("min"), g.get("max")) for k, g in (registered.get("gains") or {}).items()}}
    computed = model_gains(basis, aggressiveness)

    # What a person should know.
    level = "info" if fit["r2"] >= 0.98 else "warn"
    F.append(advisor.finding(level, f"The model explains {fit['r2']:.1%} of how {name} moved",
                             f"Fitted from {fit['samples']} moving samples with the "
                             f"{'volts the SPARK applied' if use_applied else 'volts asked'}."
                             + (" Below 98%: something it doesn't model (a cable, a spring, slack) is in there."
                                if level == "warn" else "")))
    if fit["kS"] < 0:
        F.append(advisor.finding("info", "Friction came out just below zero",
                                 f"kS {fit['kS']:.3f} V: there is next to no friction to fit (a simulator's mechanism "
                                 "has none); kS is left at zero."))
    if kind == "PIVOT" and angle is not None:
        off = math.degrees(fit["offset_rad"])
        if abs(off) > 3:
            F.append(advisor.finding("warn", f"{name} is level at {off:.1f} degrees, not 0",
                                     "REV's kCos assumes the position reads 0 when the arm is level. Either zero the "
                                     f"encoder so level reads 0, or the gravity it holds is off by cos({off:.0f} degrees)."))
    if mech and positional is not None:
        ff = mechanics.feedforward(mech)
        k_rad = k_units  # code units per radian (per meter for an elevator)
        if ff and ff.get("kV") and k_rad and ok(shown.get("kV")):
            want = ff["kV"] / k_rad
            if want and abs(shown["kV"] / want - 1) > 0.3:
                F.append(advisor.finding("warn", f"kV is {shown['kV'] / want:.1f} times what its physics say",
                                         "Its gear ratio, drum or wheel in the settings, or its units, may be off; or it "
                                         "drags more than the physics know (a bearing, a belt too tight)."))
    if low is not None:
        F.append(advisor.finding("info", f"The battery held {low:.2f} V at the hardest pull",
                                 f"Voltage compensation at {vcomp:.1f} V keeps the gains the same as it drains "
                                 "(decision 77): the motor gets the volts asked whatever the battery holds above that."))
    sensor = ((motor.get("settings") or {}).get("sensor") or "PrimaryEncoder")
    if not positional and sensor not in ("PrimaryEncoder", ""):
        filt = dict(filt, suggest=None)
        filt["why"] = ((filt.get("why") or "") + f" Its loop reads its {sensor}: that encoder's own filter is set in "
                       "its code (velMs and velDepth are the built-in encoder's).").strip()
    if filt.get("why"):
        F.append(advisor.finding("warn" if filt.get("suggest") else "info",
                                 f"Its speed reading is {filt['delay_ms']:.0f} ms late" if filt.get("delay_ms") is not None
                                 else "Its speed reading's delay is unknown", filt["why"]))
    if computed.get("note"):
        F.append(advisor.finding("info", computed["note_title"], computed["note"]))
    if sim and positional:
        F.append(advisor.finding("info", "No kD in the simulator",
                                 "REVLib's simulated SPARK runs its loop once a robot loop and applies kD far harder than "
                                 "a real SPARK (any kD wrecked the Examples elevator), so the simulator's gains use kP "
                                 "alone. On the robot the same model gives kP and kD."))
    pred = computed["predicted"]
    settle = pred.get("settle_s")
    summary = (f"{name}: kS {fit['kS']:.3f} V, kV {shown.get('kV', fit['kV']):.4g}, kA {shown.get('kA', fit['kA']):.4g}"
               + (f", kG {fit['kG']:.3f} V" if kind in ("ELEVATOR", "PIVOT") else "")
               + f" (fit {fit['r2']:.1%}). With the gains worked out from it, the model expects "
               + f"{pred['overshoot_pct']:.0f}% overshoot"
               + (", on target as the move ends." if settle is not None and settle < 0.01 else
                  f", settled {settle:.2f} s after the move." if settle is not None else ", never settling: check it."))
    if computed.get("clamped"):
        F.append(advisor.finding("warn", f"{', '.join(computed['clamped'])} held at the robot's allowed range",
                                 "The model wants more than the code allows for "
                                 + ("it" if len(computed["clamped"]) == 1 else "them")
                                 + ": the check run shows what that costs."))
    if sim:
        summary = "Simulator, practice only. " + summary
    nxt = None
    if computed["apply"]:
        nxt = {"level": "warn", "title": f"Apply the gains worked out from {name}'s model",
               "why": "Every gain at once, from one measured model: a check run of the step test follows.",
               "action": {"type": "gains", "values": computed["apply"], "model": True}}
    options = [nxt] if nxt else []
    if filt.get("suggest") and "velMs" in (registered.get("gains") or {}):
        options.append({"level": "info", "title": f"Try the speed filter at {filt['suggest']['ms']} ms, depth {filt['suggest']['depth']}",
                        "why": filt["why"],
                        "action": {"type": "gains", "values": {f"{name}/velMs": filt["suggest"]["ms"],
                                                               f"{name}/velDepth": filt["suggest"]["depth"]}}})
    current = {k: g.get("value") for k, g in (registered.get("gains") or {}).items()}
    return dict(base, summary=summary, findings=F, next=nxt, options=options, fit=fit, model=model, shown=shown, current=current,
                delay_s=delay, filter=filt, ratio_v=ratio_v, per=per, battery_low=low, volts_comp=vcomp,
                computed=computed, basis=basis, applied_volts=use_applied)


def model_gains(basis, aggressiveness=1.0):
    """The SPARK settings for a fitted model (:func:`id_report`'s ``basis``): LQR position gains or
    SIMC speed gains (:func:`modeltune.compute`), REV's units, voltage compensation, and only the ones
    the mode the code runs its SPARK in uses, inside the ranges the robot allows. ``apply`` is
    ``{"Name/k": value}``; ``all`` every computed value; ``predicted`` the model's own step test."""
    from . import modeltune as M

    kind, name = basis["kind"], basis["name"]
    positional = kind in ("PIVOT", "ELEVATOR")
    model = dict(basis["model"])
    model["kS"] = max(0.0, model["kS"])
    control = basis.get("control") or ""
    mode = control if control in MODE_GAINS else ("Position" if positional else "Velocity")
    c = M.compute(model, kind, basis["volts"], basis["delay_s"], basis["move"], basis.get("current_limit_a"),
                  basis.get("motor") or "NEO", basis.get("motors") or 1, aggressiveness,
                  basis.get("angle_rad_per_unit"), control=mode, period=basis.get("period") or M.SPARK_DT,
                  use_kd=basis.get("use_kd", True))
    spark = M.spark_gains(c["gains"], c["maxmotion"], basis["volts"], 1.0, basis.get("ratio_v") or 1.0, positional,
                          period=basis.get("period") or M.SPARK_DT)
    spark["vComp"] = basis["volts"]
    note_title = note = ""
    if control not in MODE_GAINS:
        guess = "Position" if positional else "Velocity"
        if control in ("DutyCycle", "Voltage"):
            note_title = f"{name}'s code has only run its SPARK open loop ({control}) so far"
            note = ("If its code runs a closed loop when it's used (a shooter at speed), run that once and measure "
                    "again: nothing is applied until then. If it is always open loop, the SPARK's gains do nothing; "
                    f"its own feedforward would want, in volts: kS {c['gains']['kS']:.3f}, kV {c['gains']['kV']:.4g}, "
                    f"kA {c['gains']['kA']:.4g}.")
            keep = ()
        else:
            note_title = f"Not seen how {name}'s code runs its SPARK yet"
            note = (f"Gains for {guess} mode: run its code once (a move) and measure again to be sure. "
                    "REV applies kV and kA only in MAXMotion and velocity modes.")
            keep = MODE_GAINS[guess]
    else:
        keep = MODE_GAINS[control]
        if control == "Position":
            note_title = f"{name}'s code profiles on the roboRIO in plain Position mode"
            note = ("REV doesn't apply kV or kA there, so kP carries it along the profile. MAXMotion would add the "
                    f"speed feedforward and a 1 kHz profile: cruise {spark.get('mmCruise', 0):.4g}, acceleration "
                    f"{spark.get('mmAccel', 0):.4g} in its SPARK's units.")
    keep = set(keep)
    if keep:
        keep.add("vComp")   # never for open loop: it would change what the code's duty cycle means
    if kind == "PIVOT":
        keep.discard("kG")
    elif kind == "ELEVATOR":
        keep.discard("kCos")
    ranges = basis.get("ranges") or {}
    apply, clamped = {}, []
    for k, v in spark.items():
        if k not in keep or k not in ranges:
            continue
        lo, hi = ranges[k]
        w = v
        if lo is not None and lo == lo and w < lo:
            w = lo
        if hi is not None and hi == hi and w > hi:
            w = hi
        if w != v:
            clamped.append(k)
        apply[f"{name}/{k}"] = round(w, 10)
    return {"apply": apply, "all": spark, "model_gains": c["gains"], "maxmotion": c["maxmotion"],
            "predicted": c["predicted"], "aggressiveness": aggressiveness, "clamped": clamped,
            "note": note, "note_title": note_title}


def system_motor(motors, registered):
    """A mechanism's leading motor for :func:`id_report`, from the motor guard's list
    (:meth:`link.motors`): its kind, current limit, controller and settings, and how many of the
    mechanism's motors drive."""
    names = set((registered or {}).get("motors") or [])
    mine = [m for m in motors or [] if m.get("name") in names]
    leads = [m for m in mine if not (m.get("settings") or {}).get("follows")]
    lead = (leads or mine or [{}])[0]
    return {"motor": lead.get("kind") or "", "limit_a": lead.get("base_limit") or lead.get("limit"),
            "count": max(1, len(mine)), "controller": lead.get("controller") or lead.get("code_controller") or "",
            "settings": lead.get("settings") or {}}
