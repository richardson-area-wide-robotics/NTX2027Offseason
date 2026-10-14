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
