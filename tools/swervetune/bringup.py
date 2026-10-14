"""Robot bring-up: a freshly built robot, handed over by the mechanical and electrical teams, brought
up against its design file (design.py) one motor at a time.

``motor_test_report`` reads a ``motor_test`` run (MotorTestProcedure on the robot): which motors were
run, held at zero or only watched, and for each whether it turned, how far, at what current, and on
which PDH channel. Against the design file it says whether every motor on a shared shaft turned the
way its configuration expects (a partner turning the other way would fight it when both run), at the
speed its gear ratio predicts. A motor's own encoder always agrees with its configured direction,
so which way the mechanism really moved is the one thing a person must look at: the report asks.
"""

from __future__ import annotations

import re

from . import advisor

MOVED_ROT = 0.05      # motor rotations: less than this is "didn't turn"
RATIO_TOL = 0.30      # a shaft partner's turns within 30% of what the gear ratios predict
PDH_RISE_A = 1.0      # a PDH channel rising more than this during the pulse fed the motor


def _windows(doc):
    ch = doc.get("channels") or {}
    meta = doc.get("meta") or {}
    t = ch.get("t") or []
    quiet = float(meta.get("quiet_s", 0.3))
    pulse = float(meta.get("pulse_s", 0.6))
    before = [i for i, x in enumerate(t) if x < quiet]
    during = [i for i, x in enumerate(t) if quiet <= x < quiet + pulse]
    return ch, before, during


def _mean(xs):
    xs = [x for x in xs if x == x]
    return sum(xs) / len(xs) if xs else float("nan")


def roles(doc):
    """``{index: (name, role)}`` from the run's notes; role is run, held or watched."""
    out = {}
    for note in doc.get("notes") or []:
        m = re.match(r"motor (\d+): (.+) \((run|held at zero|watched)\)$", note)
        if m:
            out[int(m.group(1))] = (m.group(2), {"run": "run", "held at zero": "held", "watched": "watched"}[m.group(3)])
    return out


def _shaft_sign(dm):
    """+1, or -1 for a follower set to turn opposite its leader: how its own encoder reads when its
    shaft turns the designed positive way."""
    f = (dm or {}).get("follows") or {}
    return -1 if f.get("inverted") else 1


def motor_test_report(doc, design=None):
    ch, before, during = _windows(doc)
    R = roles(doc)
    sim = doc.get("env") == "SIM"
    by_name = {m.get("name"): m for m in ((design or {}).get("motors") or [])}
    F, rows = [], []
    end = len(ch.get("t") or []) - 1
    for i, (name, role) in sorted(R.items()):
        rot = ch.get(f"m{i}.rot") or []
        amps = ch.get(f"m{i}.amps") or []
        if not rot or not before:
            continue
        start = rot[before[-1]]
        d = (rot[end] if end < len(rot) else rot[-1]) - start
        peak = max((abs(a) for a in (amps[j] for j in during) if a == a), default=0.0)
        rows.append({"name": name, "role": role, "turns": d, "peak_a": peak, "moved": abs(d) >= MOVED_ROT})
    run = [r for r in rows if r["role"] == "run"]
    stopped = (doc.get("outcome") == "ABORTED") and "pushing against each other" in (doc.get("message") or "")
    if stopped:
        F.append(advisor.finding("error", "Stopped: a motor pulled hard without turning",
                                 (doc.get("message") or "") + " Run each motor on that shaft alone first: the one that "
                                 "turns its partner backwards has the wrong inversion."))
    for r in run:
        if not r["moved"] and not sim and not stopped:
            F.append(advisor.finding("error", f"{r['name']} didn't turn",
                                     f"It peaked at {r['peak_a']:.1f} A. No current: no power or no signal (its PDH port and "
                                     "breaker, its CAN plug). Current but no motion: jammed, its brake partner holding the "
                                     "shaft, or it isn't the motor you are looking at."))
    # Shaft partners: each turns the way its own configuration expects, at the speed the ratios give.
    for p in rows:
        if p["role"] == "run" or not run:
            continue
        lead = run[0]
        dl, dp = by_name.get(lead["name"]), by_name.get(p["name"])
        if not dl or not dp or not dl.get("shaft") or dl.get("shaft") != dp.get("shaft"):
            continue
        if not lead["moved"]:
            continue
        rl, rp = dl.get("gearRatio") or 1.0, dp.get("gearRatio") or 1.0
        want = lead["turns"] * (_shaft_sign(dp) / _shaft_sign(dl)) * (rp / rl)
        if not p["moved"]:
            F.append(advisor.finding("error", f"{p['name']} didn't turn with {lead['name']}",
                                     f"They share shaft {dl['shaft']!r}, so {p['name']} should have turned about "
                                     f"{abs(want):.2f} rotations. A belt or gear not engaged, its brake holding, or not the "
                                     "same shaft after all."))
        elif (p["turns"] > 0) != (want > 0):
            F.append(advisor.finding("error", f"{p['name']} turns against {lead['name']}",
                                     f"Turning their shared shaft, {p['name']}'s encoder read {p['turns']:+.2f} rotations where "
                                     f"its configuration expects {want:+.2f}. Run together they would push against each other: "
                                     "fix its inversion (or, for a follower, its follow inversion) in the code and the design."))
        elif abs(p["turns"] - want) > RATIO_TOL * abs(want):
            F.append(advisor.finding("warn", f"{p['name']} turned {abs(p['turns']):.2f} rotations; the ratios say {abs(want):.2f}",
                                     "Check both gear ratios in the design file, and for a slipping belt."))
    # Which PDH channel fed each motor that ran.
    ports = sorted(int(k[3:]) for k in ch if re.fullmatch(r"pdh\d+", k))
    if ports and before and during and len(run) == 1:
        rises = sorted(((_mean([ch[f"pdh{p}"][j] for j in during[len(during) // 3:]]) - _mean([ch[f"pdh{p}"][j] for j in before]), p)
                        for p in ports), reverse=True)
        rise, port = rises[0]
        want = ((by_name.get(run[0]["name"]) or {}).get("pdh") or {}).get("port")
        if rise >= PDH_RISE_A:
            run[0]["pdh_port"] = port
            if want is not None and want != port:
                F.append(advisor.finding("error", f"{run[0]['name']} is fed from PDH port {port}; the design says {want}",
                                         "Its power lead is in another port than designed: move it, or fix the design and the "
                                         "breaker that protects it."))
    # The one thing only a person can see.
    ask = []
    for r in run:
        pos = (by_name.get(r["name"]) or {}).get("positive") or ""
        sign = (doc.get("meta") or {}).get("duty", 0.08)
        ask.append({"motor": r["name"], "question": f"Did {r['name']} turn so that {pos}?" if pos and sign > 0 else
                    f"Which way did {r['name']} turn? Write its positive direction in the design file."})
    summary = ("Stopped: a motor pulled hard without turning." if stopped else
               "Simulator: only the sequence was checked." if sim else
               "; ".join(f"{r['name']} {r['turns']:+.2f} rot, {r['peak_a']:.0f} A" for r in rows) or "Nothing recorded.")
    bad = any(f["level"] == "error" for f in F)
    return {"test": "motor_test", "env": doc.get("env", ""), "summary": summary, "findings": F, "targets": [],
            "score": None if sim else (0 if bad else 100), "next": None, "modules": {}, "motors": rows, "ask": ask}


# ---------------------------------------------------------------------------- the sign-off report


def _local_and_utc(t=None):
    """'10/13/2026 2:31 PM CDT (19:31 UTC)': this laptop's time first, UTC beside it."""
    import time
    lt, ut = time.localtime(t), time.gmtime(t)
    name = time.strftime("%Z", lt)
    abbr = "".join(w[0] for w in name.split()) if " " in name else name
    clock = time.strftime("%I:%M %p", lt).lstrip("0")
    return f"{lt.tm_mon}/{lt.tm_mday}/{lt.tm_year} {clock} {abbr} ({time.strftime('%H:%M', ut)} UTC)"


def _stamp_text(s):
    """A progress stamp ``20261013-143100`` (laptop time) in the same form."""
    import time
    try:
        return _local_and_utc(time.mktime(time.strptime(str(s), "%Y%m%d-%H%M%S")))
    except ValueError:
        return str(s or "")


def report(project, ctx, signed=None):
    """The bring-up report for this robot: ``(path, markdown)``. Written from the evidence (the
    checklist, the design file, the marks), dated, in the robot's ``bringup`` folder."""
    import os
    import time
    from . import design as D, setup as SP
    d = ctx.get("design") or {}
    prog = ctx.get("prog") or {}
    plan = SP.bringup(ctx)
    signed = signed or {}
    path = os.path.join(project.path, "bringup", time.strftime("%Y-%m-%d") + ".md")
    L = [f"# Bring-up: {project.name}", "",
         f"Written {_local_and_utc()} by the swerve tools from what was checked.", ""]
    who = [f"{k}: {v}" for k, v in signed.items() if v]
    L += [("Signed off by " + "; ".join(who) + ".") if who else "Not signed by anyone yet.", ""]
    L += ["## The checklist", "", "| Job | Status | Detail |", "|---|---|---|"]
    for j in plan["jobs"]:
        L.append(f"| {j['title']} | {j['status']} | {(j.get('detail') or '').replace('|', '/')} |")
    L += ["", "## The design file", ""]
    if d:
        buses = ", ".join(f"{b.get('name')} ({b.get('color')}/green)" for b in d.get("canBuses") or [])
        L += [f"`{os.path.relpath(D.path(project), project.path).replace(os.sep, '/')}`: controller {d.get('controller')}, "
              f"CAN {buses}, {len(d.get('motors') or [])} motors, {len(d.get('sensors') or [])} sensors.", ""]
        left = [f for f in (ctx.get("design_check") or []) + (ctx.get("design_compare") or [])]
        L += ["Where the design and the code still disagree:", ""]
        L += [f"- **{f['level']}**: {f['title']}" for f in left] or ["- Nothing."]
    else:
        L += ["No design file."]
    L += ["", "## Each mechanism motor", "", "| Motor | Result | When | Detail |", "|---|---|---|---|"]
    for m in SP.mechanism_motors(d):
        mk = prog.get("bu_motor:" + m["name"]) or {}
        L.append(f"| {m['name']} | {mk.get('result', 'not checked')} | {_stamp_text(mk.get('when')) if mk else ''} | "
                 f"{(mk.get('detail') or '').replace('|', '/')} |")
    sh = SP.shafts(d)
    if sh:
        L += ["", "## Shared shafts", "", "| Shaft | Motors | Result | Detail |", "|---|---|---|---|"]
        for k, ms in sh.items():
            mk = prog.get("bu_shaft:" + k) or {}
            L.append(f"| {k} | {', '.join(m['name'] for m in ms)} | {mk.get('result', 'not checked')} | "
                     f"{(mk.get('detail') or '').replace('|', '/')} |")
    for key, title in (("bu_handover", "Hand-over check, robot off"), ("bu_sensors", "Sensors")):
        mk = prog.get(key)
        if mk:
            L += ["", f"## {title}", "", f"{mk.get('result')} ({_stamp_text(mk.get('when'))}): {mk.get('detail', '')}"]
    return path, "\n".join(L) + "\n"
