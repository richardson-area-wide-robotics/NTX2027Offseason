"""The battery: what it is rated for, how far it sags, and which one was in.

FRC robots run on a 12 V sealed lead-acid battery; this team's is the MK ES17-12 (REV sells it).
"12 V" is the label, not what the robot sees. Charged and rested it reads about 12.7 to 13 V. Under
load it sags, because the battery and everything between it and the motors (its leads, the Anderson
connector, the main breaker, the PDH) has resistance: ``V = V_rest - R x I``. R is what this module
measures, in milliohms, from any stretch of data with both the voltage and the current: a wheel
test (the PDH's voltage and total current, recorded since the robot knows it), or a whole match
log, which spans 0 to 200 A and more and so measures it best.

Why it matters: every motor gets what is left after the sag. YAGSL compensates the SPARKs to 12 V,
so a command means the same volts on any battery until the battery can't supply them: then full
stick is slower than the code asks, and below about 6.8 V the roboRIO browns out and cuts the
motors. A worn battery (or a loose main connection) shows up as a bigger R long before it fails.

From the datasheet (MK Battery ES17-12, 2018, https://revrobotics.com/content/docs/ES17-12_User_Guide.pdf):
12 V nominal; 18 Ah at the 20-hour rate (0.9 A) but 9.6 Ah at 18 A and 6.3 Ah at 54 A; internal
resistance about 12 mOhm, measured at 1 kHz; 270 A at most for 5 s; 5.86 kg. The datasheet gives no
resting-voltage table; the charge levels below are the usual figures for this kind of battery.
"""

from __future__ import annotations

import math

from . import analysis as A
from . import units as U

ES17_12 = {
    "name": "MK ES17-12", "nominal_v": 12.0, "ah_20h": 18.0, "ah_1c": 9.6, "ah_3c": 6.3,
    "r_ohm": 0.012, "max_5s_a": 270.0, "mass_kg": 5.86,
    "source": "https://revrobotics.com/content/docs/ES17-12_User_Guide.pdf",
}
# roboRIO 1 browns out at 6.8 V (fixed); a roboRIO 2 at 6.75 V unless the code changes it.
BROWNOUT_V = 6.8
# Battery plus leads, connector and breaker, as the robot measures it. The datasheet's 12 mOhm is
# the battery alone at 1 kHz (what a battery tester reads), so a healthy one reads a few more here.
GOOD_MAX_OHM = 0.020
PRACTICE_MAX_OHM = 0.028
# Resting voltage (an hour off the charger, nothing drawing): the usual AGM figures.
REST_FULL_V = 12.7
REST_LOW_V = 12.3
MIN_SPREAD_A = 15.0
MIN_SAMPLES = 20


def pairs_from_run(doc):
    """``([(amps, volts)], source)`` from a test run, or ``([], None)``.

    Best is the PDH's own voltage and total current (``pdh_v``, ``ibatt``). Without them, the
    battery current is estimated from the motors in the run: each draws ``volts x amps / battery
    volts`` from the battery. Steering and everything else draw a near-steady few amps, which land
    in V_rest rather than R.
    """
    ch = doc.get("channels") or {}
    if ch.get("pdh_v") and ch.get("ibatt"):
        out = [(i, v) for i, v in zip(ch["ibatt"], ch["pdh_v"]) if A.finite(i) and A.finite(v) and v > 1]
        return out, "the PDH's voltage and total current"
    vb = ch.get("vbus") or []
    mods = sorted({int(k[1:k.index(".")]) for k in ch if k.startswith("m") and k.endswith(".amps") and "." in k
                   and k[1:k.index(".")].isdigit()})
    if not vb or not mods:
        return [], None
    out = []
    for k, v in enumerate(vb):
        if not A.finite(v) or v <= 1:
            continue
        tot = 0.0
        for m in mods:
            volts = (ch.get(f"m{m}.volts") or [])[k] if k < len(ch.get(f"m{m}.volts") or []) else float("nan")
            amps = (ch.get(f"m{m}.amps") or [])[k] if k < len(ch.get(f"m{m}.amps") or []) else float("nan")
            if A.finite(volts) and A.finite(amps):
                tot += abs(volts * amps) / v
        out.append((tot, v))
    return out, "the roboRIO's voltage, with the current estimated from the drive motors"


def pairs_from_log(series):
    """``[(amps, volts)]`` from an AdvantageKit match log: the PDH's total current and voltage."""
    amps = series.get("/PowerDistribution/TotalCurrent") or []
    volts = dict(series.get("/PowerDistribution/Voltage") or [])
    return [(a, volts[t]) for t, a in amps if t in volts and A.finite(a) and A.finite(volts[t]) and volts[t] > 1]


def fit(pairs):
    """``V = V_rest - R x I`` by least squares, twice: the second time without samples more than
    three robust deviations off the first line (a reading taken mid-change). None if the current
    never moved enough to tell."""
    pts = [(i, v) for i, v in pairs if A.finite(i) and A.finite(v)]
    if len(pts) < MIN_SAMPLES:
        return None
    lo, hi = min(i for i, _ in pts), max(i for i, _ in pts)
    if hi - lo < MIN_SPREAD_A:
        return None

    def line(p):
        n = len(p)
        mi = sum(i for i, _ in p) / n
        mv = sum(v for _, v in p) / n
        sxx = sum((i - mi) ** 2 for i, _ in p)
        if sxx <= 0:
            return None
        slope = sum((i - mi) * (v - mv) for i, v in p) / sxx
        return mv - slope * mi, -slope

    first = line(pts)
    if not first:
        return None
    res = [v - (first[0] - first[1] * i) for i, v in pts]
    mad = A.median([abs(r) for r in res]) or 1e-6
    kept = [p for p, r in zip(pts, res) if abs(r) <= 3 * 1.4826 * mad] or pts
    v0, r = line(kept) or first
    if not (0.001 < r < 0.25):
        return None
    rms = math.sqrt(sum((v - (v0 - r * i)) ** 2 for i, v in kept) / len(kept))
    return {"r_ohm": r, "v_rest": v0, "n": len(kept), "i_max": hi, "v_min": min(v for _, v in pts),
            "spread_a": hi - lo, "rms_v": rms}


def grade(r_ohm):
    """``(status, words)`` for a measured battery-path resistance."""
    mohm = r_ohm * 1000
    if r_ohm <= GOOD_MAX_OHM:
        return "good", f"{mohm:.0f} mΩ: a healthy battery and connections."
    if r_ohm <= PRACTICE_MAX_OHM:
        return "practice", (f"{mohm:.0f} mΩ: sags more than a fresh one. Fine for practice; keep it out of "
                            "matches if better ones are charged.")
    return "retire", (f"{mohm:.0f} mΩ: sags hard. Check the Anderson connector and the main breaker's "
                      "bolts first; if they are tight, the battery is worn out.")


def charge_words(v_rest):
    if not A.finite(v_rest):
        return ""
    if v_rest >= REST_FULL_V:
        return f"{v_rest:.2f} V at rest: charged."
    if v_rest >= REST_LOW_V:
        return f"{v_rest:.2f} V at rest: partly charged."
    return f"{v_rest:.2f} V at rest: charge it before use."


def volts_at(f, amps):
    return f["v_rest"] - f["r_ohm"] * amps


def brownout_amps(f, v_brownout=BROWNOUT_V):
    """The total current at which this battery would sag to a brownout."""
    return (f["v_rest"] - v_brownout) / f["r_ohm"]


def full_stick_volts(kv, ks, max_speed):
    """The motor voltage full stick needs: kS + kV x MAX_SPEED (SPARK losses aside)."""
    if not (A.finite(kv) and A.finite(max_speed)):
        return float("nan")
    return (ks if A.finite(ks) else 0.0) + kv * max_speed


def rest_from_run(doc):
    """The battery voltage before anything moved: the first 0.3 s of the run."""
    ch = doc.get("channels") or {}
    t = ch.get("t") or []
    v = ch.get("pdh_v") or ch.get("vbus") or []
    early = [x for tt, x in zip(t, v) if tt <= 0.3 and A.finite(x) and x > 1]
    return A.median(early) if early else float("nan")


def report(doc, kv=None, ks=None, max_speed=None, pairs=None, source=None):
    """``{"battery": {...}, "findings": [...]}`` for a run or a match."""
    if pairs is None:
        pairs, source = pairs_from_run(doc)
    f = fit(pairs) if pairs else None
    rest = rest_from_run(doc) if doc else float("nan")
    out = {"id": doc.get("battery") if doc else None, "source": source, "fit": f, "rest_v": rest,
           "datasheet": ES17_12}
    F = []
    who = f"Battery {out['id']}" if out["id"] else "The battery"
    if f:
        status, words = grade(f["r_ohm"])
        out.update(status=status, brownout_a=brownout_amps(f), volts_at_150a=volts_at(f, 150))
        level = {"good": "info", "practice": "warn", "retire": "error"}[status]
        F.append({"level": level, "title": f"{who} sags {f['r_ohm'] * 1000:.0f} mV for every amp drawn ({f['r_ohm'] * 1000:.0f} mΩ)",
                  "why": (f"{words} Measured from {source}, {f['spread_a']:.0f} A of range. The datasheet's "
                          f"12 mΩ is the battery alone; the robot also measures its leads, connector and "
                          f"breaker. At 150 A this one would read {volts_at(f, 150):.1f} V; it would brown "
                          f"out the roboRIO near {brownout_amps(f):.0f} A."),
                  "learn": "battery"})
    elif pairs:
        out["status"] = None
    need = full_stick_volts(kv, ks, max_speed) if kv else float("nan")
    if A.finite(need):
        out["full_stick_v"] = need
        if f:
            amps = (f["v_rest"] - need) / f["r_ohm"]
            out["full_stick_until_a"] = amps
            F.append({"level": "info", "title": f"Full stick ({U.speed(max_speed, 1)}) needs {need:.1f} V at the motors",
                      "why": (f"{who} holds that up to about {amps:.0f} A in total. Draw more (four drive motors "
                              "accelerating, a shooter spinning up) and full stick is slower than the code asks "
                              "until the current falls.") if amps > 0 else
                             (f"{who} can't hold {need:.1f} V even at rest: full stick will be slow. Charge it "
                              "or lower MAX_SPEED."),
                      "learn": "battery"})
    if A.finite(rest) and rest < REST_LOW_V:
        F.append({"level": "warn", "title": f"{who} started at {rest:.2f} V", "why": charge_words(rest),
                  "learn": "battery"})
    return {"battery": out, "findings": F}


BORROWED = "Borrowed"
# A robot whose own power path is high makes every battery measure high.
PATH_RECENT_DAYS = 14


def robot_path_suspect(hist, today=None):
    """``{"title", "why"}`` when nearly every battery measured lately grades practice or retire: the
    likelier cause is the robot's own power path (main breaker bolts, the Anderson connector, the PDH
    lugs), which every measurement includes, not every battery at once. None otherwise."""
    import time
    stamp = today or time.strftime("%Y%m%d")
    recent = []
    for bid, h in hist.items():
        if bid == BORROWED or not h:
            continue
        last = h[-1]
        try:
            age = (time.mktime(time.strptime(stamp[:8], "%Y%m%d")) -
                   time.mktime(time.strptime(str(last["when"])[:8], "%Y%m%d"))) / 86400
        except (ValueError, TypeError):
            continue
        if age <= PATH_RECENT_DAYS and last.get("status"):
            recent.append(last["status"])
    if len(recent) >= 3 and sum(1 for s in recent if s != "good") >= 0.75 * len(recent):
        return {"title": f"{sum(1 for s in recent if s != 'good')} of {len(recent)} batteries measured lately are tired",
                "why": "Every sag measurement includes the robot's own power path, so a loose main breaker "
                       "bolt, a worn Anderson connector or a PDH lug makes every battery look tired at once. "
                       "Tighten and check those before retiring batteries."}
    return None


RESTED_MIN = 60  # a battery measured on the robot more recently than this is probably still flat


def _minutes_since(when, now):
    import time
    for fmt, n in (("%Y%m%d-%H%M%S", 15), ("%Y%m%d", 8)):
        try:
            return (now - time.mktime(time.strptime(str(when)[:n], fmt))) / 60
        except (ValueError, TypeError):
            continue
    return None


def _ago(minutes):
    if minutes < 90:
        return f"{minutes:.0f} min ago"
    if minutes < 36 * 60:
        return f"{minutes / 60:.0f} h ago"
    return f"{minutes / 1440:.0f} days ago"


def suggest_next(rows, current=None, now=None):
    """Which battery to put in next: ``{"id", "why"}``, or None.

    Never the one in now, a borrowed one, or one graded retire. Good before practice before not yet
    measured; among those, the one on the robot longest ago, the likeliest to be charged and cool.
    One measured on the robot in the last hour is a last resort: it is probably still flat. "On the
    robot" means in a test or a match log; a battery used without either leaves no record.
    """
    import time
    now = time.time() if now is None else now
    rank = {"good": 0, "practice": 1, None: 2}
    cands = []
    for b in rows:
        if not b.get("listed") or b["id"] in (current, BORROWED) or b.get("status") == "retire":
            continue
        mins = _minutes_since(b.get("when"), now) if b.get("when") else None
        fresh = mins is not None and mins < RESTED_MIN
        # Not yet measured: no record of when it was last on the robot, so as rested as any.
        cands.append((fresh, rank.get(b.get("status"), 2), -(mins if mins is not None else 1e9), b, mins))
    if not cands:
        return None
    fresh, _, _, b, mins = min(cands, key=lambda c: c[:3])
    graded = f"graded {b['status']} ({b['mohm']:g} mΩ)" if b.get("status") else "not measured yet"
    seen = f"last on the robot {_ago(mins)}" if mins is not None else "no record of its last use"
    why = f"{graded}, {seen}"
    if fresh:
        why += ". Every other battery is retired or was on the robot in the last hour: check this one's charge"
    else:
        why += ": the likeliest to be charged and cool"
    return {"id": b["id"], "why": why + "."}


def grades_for_robot(rows):
    """``{id: grade}`` for the robot's Battery check line and its next-battery choice: each listed
    battery's latest grade. Borrowed is many batteries under one name, so it is never graded."""
    return {b["id"]: b["status"] for b in rows
            if b.get("listed") and b.get("status") and b["id"] != BORROWED}


def history(entries):
    """Per battery id, its measurements oldest first. ``entries`` are ``(when, id, fit, source)``."""
    out = {}
    for when, bid, f, source in sorted(entries, key=lambda e: e[0] or ""):
        if not bid or not f:
            continue
        # "Borrowed" is many batteries under one name: its measurements are kept but never graded.
        status, _ = grade(f["r_ohm"]) if bid != BORROWED else (None, "")
        out.setdefault(bid, []).append({"when": when, "mohm": round(f["r_ohm"] * 1000, 1),
                                        "v_rest": round(f["v_rest"], 2), "status": status, "source": source})
    return out
