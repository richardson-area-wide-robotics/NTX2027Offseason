"""Game pieces by a motor's own current: what the Systems tab's two runs say.

* :func:`calibration_report` (``system_piece``): a roller run empty, then fed a set number of pieces
  one at a time; or an arm or elevator swept empty, then once with each piece. It finds how much
  the current rises when a piece is in against everything the empty motor does (its spin-up spike
  above all), and sets the threshold halfway between, how long the current must stay past it, and
  how long to ignore after a start. For an arm, the current it draws empty at each position too.
* :func:`hold_report` (``system_hold``): the hold current stepped down while a person pulled the
  piece, like the slip test; where it slipped, the hold current with a margin, and how fast the
  motor warmed holding there.

Each ends with the change to slothtune.json it suggests, for the usual preview before it's saved.
"""

from __future__ import annotations

import math
import statistics

# The current must clear the empty motor by this much to be told apart reliably.
MIN_MARGIN_A = 1.5
# A match is 2:30; a hold may last most of it.
MATCH_S = 150.0


def _f(level, title, why):
    return {"level": level, "title": title, "why": why}


def _num(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


def _windows(phase, t, value):
    """The (start, end) index spans where ``phase`` equals ``value``."""
    out, start = [], None
    for i, p in enumerate(phase):
        if p == value and start is None:
            start = i
        elif p != value and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(phase)))
    return out


def _sustained(amps, i0, i1, n):
    """The highest current held for ``n`` samples in a row (the lowest of each run of ``n``)."""
    best = -math.inf
    for i in range(i0, max(i0, i1 - n + 1)):
        w = [a for a in amps[i:i + n] if _num(a)]
        if len(w) == n:
            best = max(best, min(w))
    return best


def calibration_report(doc):
    ch, meta = doc.get("channels") or {}, doc.get("meta") or {}
    t, amps, phase = ch.get("t") or [], ch.get("amps") or [], ch.get("phase") or []
    name = next((n.split(": ", 1)[1].split(" (")[0] for n in doc.get("notes") or [] if n.startswith("sensor: ")), "the sensor")
    if len(t) < 20 or len(amps) != len(t):
        return {"summary": "Too little recorded to calibrate it.", "score": None, "findings": [
            _f("error", "Nothing to work out", "The run stopped before the pieces. Run it again, the deadman held throughout.")]}
    if not any(_num(a) for a in amps):
        return {"summary": f"{name}: no current readings.", "score": None, "findings": [
            _f("error", "The motor controller reported no current",
               "Its current is what this reads, and none came through: in the simulator there is none to read. "
               "On the robot, check the motor is watched under that name and on the CAN bus.")]}
    if meta.get("positional"):
        return _arm_report(doc, name, t, amps, phase, ch)
    dt = (t[-1] - t[0]) / max(1, len(t) - 1)
    spin = float(meta.get("spin_up_s") or 1.0)
    pieces = int(meta.get("pieces") or 0)

    # Empty: settling (after its own spin-up) and each feed window's spin-up second, before a piece.
    empty, spikes, settle_times = [], [], []
    starts = [s for s, _ in _windows(phase, t, 0)] + [s for k in range(1, pieces + 1) for s, _ in _windows(phase, t, k)]
    for s in starts:
        e = s
        while e < len(t) and t[e] - t[s] < spin:
            e += 1
        vals = [a for a in amps[s:e] if _num(a)]
        if vals:
            spikes.append(max(vals))
    for s, e in _windows(phase, t, 0):
        ss = s
        while ss < e and t[ss] - t[s] < spin:
            ss += 1
        empty += [a for a in amps[ss:e] if _num(a)]
    if not empty:
        return {"summary": "No empty running recorded.", "score": None, "findings": [
            _f("error", "It never ran empty", "The run stopped too early. Run it again.")]}
    empty_hi = sorted(empty)[int(0.98 * (len(empty) - 1))]
    empty_level = statistics.median(empty)

    # How long each start's spike takes to come back down: the time to ignore after a start.
    for s in starts:
        e = s
        while e < len(t) and t[e] - t[s] < spin:
            e += 1
        k = s
        while k < e and _num(amps[k]) and amps[k] > empty_hi:
            k += 1
        settle_times.append(t[min(k, len(t) - 1)] - t[s])

    # Each piece: its window after the spin-up, the current it held for a few samples.
    hold_n = max(2, int(round(0.04 / max(dt, 1e-3))))
    found = []
    for k in range(1, pieces + 1):
        win = _windows(phase, t, k)
        if not win:
            found.append({"piece": k, "peak_a": None})
            continue
        s, e = win[0]
        while s < e and t[s] - t[win[0][0]] < spin:
            s += 1
        peak = _sustained(amps, s, e, hold_n)
        found.append({"piece": k, "peak_a": round(peak, 1) if _num(peak) else None})
    seen = [p for p in found if p["peak_a"] is not None and p["peak_a"] > empty_hi + 0.5]
    missed = [p["piece"] for p in found if p not in seen]
    F = []
    if missed:
        F.append(_f("warn", f"Piece{'s' if len(missed) > 1 else ''} {', '.join(map(str, missed))}: no rise in the current",
                    "Fed too late (after the roller stopped), not pushed in far enough to load the roller, or this "
                    "mechanism's current doesn't change with a piece. Run it again, feeding each one when the banner says."))
    if not seen:
        return {"summary": f"{name}: no piece raised the current above the empty roller's.", "score": 0, "findings": F,
                "empty_a": round(empty_hi, 1), "pieces": found}
    low = min(p["peak_a"] for p in seen)
    margin = (low - empty_hi) / 2
    threshold = round(empty_hi + margin, 1)
    # How long it must stay past the threshold: half the shortest piece's time above it.
    above = []
    for p in seen:
        s, e = _windows(phase, t, p["piece"])[0]
        run = best = 0.0
        for i in range(s, e):
            run = run + dt if _num(amps[i]) and amps[i] > threshold else 0.0
            best = max(best, run)
        above.append(best)
    hold_s = round(min(0.25, max(0.02, min(above) / 2)), 2)
    ignore_s = round(min(1.0, max(0.1, max(settle_times or [0.25]) + 0.1)), 2)
    spike = max(spikes) if spikes else None
    F.insert(0, _f("ok" if margin >= MIN_MARGIN_A else "warn",
                   f"A piece raises it to {low:.1f} A or more; running empty it stays under {empty_hi:.1f} A",
                   f"The threshold sits halfway, at {threshold} A: {margin:.1f} A clear of each side."
                   + ("" if margin >= MIN_MARGIN_A else " That's close: a worn roller or a low battery could cross it. "
                      "Check the piece really loads the roller, or use a beam break.")))
    if spike is not None and spike > threshold:
        F.append(_f("info", f"Its spin-up spike reaches {spike:.1f} A, above the threshold",
                    f"So it ignores the first {ignore_s} s after each start (the spike lasted up to "
                    f"{max(settle_times):.2f} s here)."))
    edits = {"mode": "rise", "thresholdA": threshold, "holdS": hold_s, "ignoreS": ignore_s}
    return {"summary": f"{name}: threshold {threshold} A, held {hold_s} s, ignoring {ignore_s} s after a start",
            "score": 100 if margin >= MIN_MARGIN_A and not missed else 60, "findings": F,
            "empty_a": round(empty_hi, 1), "empty_level_a": round(empty_level, 1), "spike_a": spike, "pieces": found,
            "suggest": {"sensor": name, "values": edits}}


def _arm_report(doc, name, t, amps, phase, ch):
    """An arm or elevator: the empty current at each position, and how much a piece adds there."""
    pos = ch.get("pos") or []
    meta = doc.get("meta") or {}
    lo, hi = meta.get("min"), meta.get("max")
    if not (_num(lo) and _num(hi) and hi > lo) or len(pos) != len(t):
        return {"summary": "No positions recorded.", "score": None, "findings": [
            _f("error", "It needs its limits and position", "Set its limits on the Systems tab and run it again.")]}
    bins = 8
    edges = [lo + (hi - lo) * i / bins for i in range(bins + 1)]

    def by_bin(sel):
        out = [[] for _ in range(bins)]
        for i, p in enumerate(phase):
            if sel(p) and _num(pos[i]) and _num(amps[i]) and lo <= pos[i] <= hi:
                b = min(bins - 1, int((pos[i] - lo) / (hi - lo) * bins))
                out[b].append(amps[i])
        return [statistics.median(v) if len(v) >= 3 else None for v in out]

    empty = by_bin(lambda p: p == 100)
    pieces = int(meta.get("pieces") or 0)
    loaded = [by_bin(lambda p, k=k: p == k) for k in range(1, pieces + 1)]
    deltas = [[(l[b] - empty[b]) if l[b] is not None and empty[b] is not None else None for b in range(bins)] for l in loaded]
    flat = [d for row in deltas for d in row if d is not None]
    centers = [(edges[b] + edges[b + 1]) / 2 for b in range(bins)]
    if not flat:
        return {"summary": f"{name}: nothing to compare.", "score": 0, "findings": [
            _f("error", "No loaded sweep recorded", "Run it again, putting each piece in when the banner says.")]}
    good = sorted(flat)[int(0.25 * (len(flat) - 1))]
    threshold = round(max(0.3, good / 2), 2)
    weak = [round(centers[b], 2) for b in range(bins)
            if any(row[b] is not None and row[b] < 1.5 * threshold for row in deltas)]
    baseline = [[round(centers[b], 3), round(empty[b], 2)] for b in range(bins) if empty[b] is not None]
    F = [_f("ok" if good >= 2 * MIN_MARGIN_A / 2 and not weak else "warn",
            f"A piece adds about {statistics.median(flat):.1f} A over the empty arm",
            f"The threshold is {threshold} A over the empty current at each position (saved with it)."
            + (f" Near {', '.join(map(str, weak))} the difference is small (gravity pulls less there): it may "
               "not tell a piece apart at those positions." if weak else ""))]
    return {"summary": f"{name}: {threshold} A over the empty current at each position", "score": 100 if not weak else 70,
            "findings": F, "baseline": baseline, "deltas": deltas,
            "suggest": {"sensor": name, "values": {"mode": "aboveBaseline", "thresholdA": threshold, "holdS": 0.1,
                                                   "ignoreS": 0.25, "baseline": baseline}}}


def hold_report(doc, motor_limits=None):
    """The hold current from the step-down: where the piece slipped, the hold with its margin, and
    the motor's warming there. ``motor_limits`` is {"warn_c": ...} for its kind, if known."""
    ch, meta = doc.get("channels") or {}, doc.get("meta") or {}
    t, temp, phase = ch.get("t") or [], ch.get("temp") or [], ch.get("phase") or []
    motor = next((n.split(": ", 1)[1] for n in doc.get("notes") or [] if n.startswith("hold: ")), "the motor")
    slip, hold = meta.get("slip_a"), meta.get("hold_a")
    if not _num(hold):
        return {"summary": "The run stopped before it found the hold current.", "score": None, "findings": [
            _f("error", "No hold current found", "Run it again with a piece in, pulling it steadily as the banner says.")]}
    F = []
    start = meta.get("start_a")
    if _num(slip) and _num(start) and slip >= start - 1e-6:
        F.append(_f("warn", f"It slipped even at the start, {slip:.0f} A",
                    "More current won't hold it: the rollers don't grip the piece (compression, worn or slick rollers). "
                    "Fix the grip, then tune again."))
    elif _num(slip):
        F.append(_f("ok", f"The piece slipped at {slip:.0f} A; it holds at {hold:.0f} A",
                    f"{hold / slip:.2f} times the slip current: margin for a harder knock than the pull."))
    else:
        F.append(_f("ok", f"It held at every current tried, down to {meta.get('min_a')} A; it holds at {hold:.0f} A",
                    "The lowest tried, with the margin. A firmer pull would find the real slip current."))
    # Warming while it held: its rate, and where a whole match at that rate would leave it.
    idx = [i for i, p in enumerate(phase) if p == 2 and _num(temp[i] if i < len(temp) else None)]
    rate = None
    if len(idx) >= 2 and t[idx[-1]] > t[idx[0]]:
        rate = (temp[idx[-1]] - temp[idx[0]]) / (t[idx[-1]] - t[idx[0]])
        end = temp[idx[-1]] + rate * MATCH_S
        warn = (motor_limits or {}).get("warn_c", meta.get("warn_c"))
        hot = _num(warn) and end >= warn
        F.append(_f("warn" if hot else "ok", f"It warmed {rate * 60:.1f} °C a minute holding at {hold:.0f} A",
                    (f"A whole match of holding would take it to about {end:.0f} °C, past its {warn:.0f} °C warning: hold "
                     "for less of the match, or lower the hold." if hot else
                     f"A whole match of holding would take it to about {end:.0f} °C.")))
    return {"summary": f"{motor}: hold at {hold:.0f} A", "score": 100 if not any(f["level"] == "warn" for f in F) else 60,
            "findings": F, "slip_a": slip if _num(slip) else None, "hold_a": hold,
            "warming_c_per_min": round(rate * 60, 2) if rate is not None else None,
            "suggest": {"hold": motor, "values": {"currentA": hold, "duty": meta.get("duty")}}}


def edits(suggest):
    """slothtune.json edits for a report's suggestion (a sensor's calibration, or a hold)."""
    if not suggest:
        return []
    if "sensor" in suggest:
        return [("slothtune.json", ("currentSensors", suggest["sensor"], k), v) for k, v in suggest["values"].items()]
    return [("slothtune.json", ("holds", suggest["hold"], k), v) for k, v in suggest["values"].items() if v is not None]
