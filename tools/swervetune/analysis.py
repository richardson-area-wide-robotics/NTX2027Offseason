"""Turns recorded test data into numbers a person can act on.

Pure Python with no dependencies, so it runs on any laptop and any agent can import it. Every
function takes plain lists and returns plain dicts.

The step-response vocabulary used throughout, for a step of size D from y0 to r:

* **dead time** - from the setpoint change until the output has moved 5% of D. Pure delay:
  measurement filtering, CAN status-frame period, controller loop period. No gain fixes it, and
  it caps how aggressive any gain can be.
* **rise time** - 10% to 90% of D. How fast it gets there.
* **overshoot** - how far past r it went, as a percentage of D.
* **settling time** - from the step until it stays inside the tolerance band for good.
* **steady-state error** - mean error over the last fifth of the hold. Friction shows up here.
* **oscillations** - how many times the error changes sign after first reaching r. Two or more
  is ringing.
* **saturation** - fraction of the move spent at full output. A saturated loop is limited by the
  motor, not by its gains, and raising kP will not make it faster.
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------- basics


def mean(xs):
    xs = [x for x in xs if x is not None and math.isfinite(x)]
    return sum(xs) / len(xs) if xs else float("nan")


def stdev(xs):
    xs = [x for x in xs if x is not None and math.isfinite(x)]
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def median(xs):
    xs = sorted(x for x in xs if x is not None and math.isfinite(x))
    if not xs:
        return float("nan")
    n = len(xs)
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def finite(x):
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


def wrap180(deg):
    return (deg + 180.0) % 360.0 - 180.0


def unwrap_deg(xs):
    out, turns, last = [], 0.0, None
    for x in xs:
        if last is not None and finite(x) and finite(last):
            d = x - last
            if d > 180:
                turns -= 360
            elif d < -180:
                turns += 360
        out.append(x + turns if finite(x) else x)
        if finite(x):
            last = x
    return out


def spread_percent(values):
    """Peak-to-peak spread as a percentage of the mean magnitude."""
    vals = [v for v in values if finite(v)]
    if len(vals) < 2:
        return 0.0
    m = mean([abs(v) for v in vals])
    return 100.0 * (max(vals) - min(vals)) / m if m > 1e-9 else 0.0


# ---------------------------------------------------------------------------- step responses


def segments(t, sp, min_change=1e-6):
    """Splits a run into the stretches where the setpoint is constant.

    Returns ``(start_index, end_index_exclusive, setpoint)`` triples.
    """
    out, start = [], 0
    for i in range(1, len(sp)):
        if abs(sp[i] - sp[i - 1]) > min_change:
            out.append((start, i, sp[start]))
            start = i
    if sp:
        out.append((start, len(sp), sp[start]))
    return out


def smooth(xs, window):
    """Centered moving median. Keeps edges sharp while removing single-count sensor steps."""
    if window <= 1 or len(xs) < window:
        return list(xs)
    h = window // 2
    out = []
    for i in range(len(xs)):
        seg = [x for x in xs[max(0, i - h):i + h + 1] if finite(x)]
        out.append(median(seg) if seg else xs[i])
    return out


def step_metrics(t, sp, y, u=None, tol=None, u_max=None, amps=None, amp_limit=None, window=1):
    """Metrics for one step, given the samples of a single constant-setpoint segment.

    ``t``, ``y`` and ``u`` cover the segment only; ``sp`` is its constant setpoint; the first
    sample of ``y`` is taken as where it started. ``tol`` is the settling band in the units of y;
    by default 2% of the step or what is needed for very small steps.
    """
    n = len(y)
    if n < 4:
        return None
    raw = y
    y = smooth(y, window)
    r = sp
    y0 = y[0]
    d = r - y0
    size = abs(d)
    if size < 1e-9:
        return None
    sign = 1.0 if d > 0 else -1.0
    band = tol if tol is not None else max(0.02 * size, 1e-9)
    t0 = t[0]
    rel = [ti - t0 for ti in t]
    progress = [(yi - y0) * sign / size for yi in y]  # 0 at start, 1 at target

    def first_time(level):
        for i, p in enumerate(progress):
            if p >= level:
                if i == 0:
                    return rel[0]
                # interpolate between samples
                p0, p1 = progress[i - 1], p
                f = (level - p0) / (p1 - p0) if p1 != p0 else 0
                return rel[i - 1] + f * (rel[i] - rel[i - 1])
        return None

    dead = first_time(0.05)
    t10, t90 = first_time(0.10), first_time(0.90)
    rise = (t90 - t10) if (t10 is not None and t90 is not None) else None
    peak = max(progress)
    overshoot = max(0.0, (peak - 1.0) * 100.0)

    err = [(r - yi) * sign for yi in y]  # positive means short of target
    settle = None
    for i in range(n - 1, -1, -1):
        if abs(err[i]) > band:
            settle = rel[i + 1] if i + 1 < n else None
            break
    else:
        settle = 0.0
    tail = err[int(n * 0.8):] or err[-1:]
    ss = mean(tail)
    raw_tail = [(r - yi) * sign for yi in raw[int(n * 0.8):]] or tail
    ss_noise = stdev(raw_tail)

    # Ringing: swings beyond the band that alternate sides once it has first reached the target.
    # Excursions inside the band are noise, not oscillation - a coarse sensor wobbling by one count
    # around the target must not read as a loop that rings.
    reached = next((i for i, p in enumerate(progress) if p >= 1.0), None)
    oscillations = 0
    if reached is not None:
        last_sign = 0
        for e in err[reached:]:
            if abs(e) <= band:
                continue
            s = 1 if e > 0 else -1
            if last_sign and s != last_sign:
                oscillations += 1
            last_sign = s

    # Saturated means the motor is giving all it can: full voltage, or held at its current limit.
    sat = None
    if u is not None and len(u) == n:
        cap = u_max if u_max else max((abs(v) for v in u if finite(v)), default=0.0)
        moving = [i for i, p in enumerate(progress) if p < 0.9]
        if moving and cap > 1e-9:
            def pinned(i):
                at_volts = finite(u[i]) and abs(u[i]) >= 0.95 * cap
                at_amps = (amps is not None and amp_limit and i < len(amps) and finite(amps[i])
                           and abs(amps[i]) >= 0.9 * amp_limit)
                return at_volts or at_amps
            sat = sum(1 for i in moving if pinned(i)) / len(moving)

    return {
        "from": y0, "to": r, "size": d, "duration": rel[-1],
        "dead_time": dead, "rise_time": rise, "overshoot_pct": overshoot,
        "settling_time": settle, "settled": settle is not None,
        "steady_state_error": ss, "steady_state_noise": ss_noise,
        "oscillations": oscillations, "saturation": sat, "band": band,
        "peak_progress": peak,
    }


def analyze_steps(t, sp, y, u=None, tol_abs=None, u_max=None, skip_first=True, amps=None,
                  amp_limit=None, window=1):
    """Every step in a run. Returns a list of step_metrics dicts with an index added."""
    out = []
    for k, (a, b, r) in enumerate(segments(t, sp)):
        if skip_first and k == 0:
            continue  # the settle segment before the first step
        start = max(a - 1, 0)  # include the last sample before the change as the starting point
        seg_t, seg_y = t[start:b], y[start:b]
        seg_u = u[start:b] if u is not None else None
        seg_i = amps[start:b] if amps is not None else None
        size = abs(r - seg_y[0]) if seg_y else 0
        tol = None
        if tol_abs is not None:
            tol = max(tol_abs, 0.02 * size)
        m = step_metrics(seg_t, r, seg_y, seg_u, tol=tol, u_max=u_max, amps=seg_i,
                         amp_limit=amp_limit, window=window)
        if m:
            m["index"] = k
            out.append(m)
    return out


def summarize_steps(steps, small=20.0):
    """Aggregates over a list of step metrics, split into small and large steps."""
    def agg(sel):
        if not sel:
            return {}
        return {
            "count": len(sel),
            "rise_time": mean([s["rise_time"] for s in sel if s["rise_time"] is not None]),
            "dead_time": mean([s["dead_time"] for s in sel if s["dead_time"] is not None]),
            "overshoot_pct": max(s["overshoot_pct"] for s in sel),
            "settling_time": max((s["settling_time"] for s in sel if s["settling_time"] is not None),
                                 default=float("nan")),
            "unsettled": sum(1 for s in sel if not s["settled"]),
            "steady_state_error": mean([abs(s["steady_state_error"]) for s in sel]),
            "steady_state_noise": mean([s["steady_state_noise"] for s in sel]),
            "oscillations": max(s["oscillations"] for s in sel),
            "saturation": mean([s["saturation"] for s in sel if s["saturation"] is not None]),
        }

    smalls = [s for s in steps if abs(s["size"]) <= small]
    larges = [s for s in steps if abs(s["size"]) > small]
    pos = [s for s in steps if s["size"] > 0]
    neg = [s for s in steps if s["size"] < 0]
    return {"all": agg(steps), "small": agg(smalls), "large": agg(larges),
            "positive": agg(pos), "negative": agg(neg)}


def direction_asymmetry(summary):
    """How differently it moves one way versus the other, 0 = identical. Mechanical, not gains."""
    p, n = summary.get("positive", {}), summary.get("negative", {})
    a, b = p.get("rise_time"), n.get("rise_time")
    if not (finite(a) and finite(b)) or max(a, b) <= 0:
        return 0.0
    return abs(a - b) / max(a, b)


# ---------------------------------------------------------------------------- delay


def response_delay(t, sp, y, threshold_frac=0.05):
    """Median dead time over every setpoint change: the pure delay in the loop, in seconds."""
    delays = []
    for k, (a, b, r) in enumerate(segments(t, sp)):
        if k == 0 or b - a < 3:
            continue
        y0 = y[a - 1] if a > 0 else y[a]
        d = r - y0
        if abs(d) < 1e-6:
            continue
        for i in range(a, b):
            if (y[i] - y0) / d >= threshold_frac:
                delays.append(t[i] - t[a])
                break
    return median(delays)


# ---------------------------------------------------------------------------- feedforward


def solve(a, b):
    """Gaussian elimination with partial pivoting; None if singular."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


def ols(rows, ys):
    """Least squares with R squared. rows: list of regressor lists."""
    k = len(rows[0])
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(k)] for i in range(k)]
    aty = [sum(r[i] * y for r, y in zip(rows, ys)) for i in range(k)]
    beta = solve(ata, aty)
    if beta is None:
        return None, 0.0
    pred = [sum(b * x for b, x in zip(beta, r)) for r in rows]
    my = mean(ys)
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - p) ** 2 for y, p in zip(ys, pred))
    r2 = 1 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    return beta, max(0.0, min(1.0, r2))


def resample(t, *series, dt=None):
    """Resamples onto a uniform grid by linear interpolation. Returns (t_uniform, *series)."""
    if len(t) < 3:
        return (t,) + series
    if dt is None:
        dt = median([t[i + 1] - t[i] for i in range(len(t) - 1)])
    grid = []
    x = t[0]
    while x <= t[-1] + 1e-12:
        grid.append(x)
        x += dt
    outs = []
    for s in series:
        out, j = [], 0
        for g in grid:
            while j < len(t) - 2 and t[j + 1] < g:
                j += 1
            t0, t1 = t[j], t[j + 1]
            f = (g - t0) / (t1 - t0) if t1 > t0 else 0
            out.append(s[j] + f * (s[j + 1] - s[j]))
        outs.append(out)
    return (grid,) + tuple(outs)


def fit_feedforward(t, volts, v, min_speed=0.05):
    """Fits ``V = kS*sgn(v) + kV*v + kA*a`` the way SysId does.

    SysId does not differentiate velocity. It fits the discrete-time model

        v[k+1] = alpha*v[k] + beta*V[k] + gamma*sgn(v[k])

    and converts alpha, beta, gamma back to kS, kV, kA. Differentiating a noisy velocity to get
    acceleration attenuates kA (the 2026 code's known defect); this does not. A direct fit is
    returned alongside as a cross-check - when the two disagree on kS or kV, look at the data.
    """
    tu, Vu, vu = resample(t, volts, v)
    dt = tu[1] - tu[0] if len(tu) > 1 else 0.01
    rows, ys = [], []
    for k in range(len(tu) - 1):
        if abs(vu[k]) < min_speed or abs(vu[k + 1]) < min_speed:
            continue
        rows.append([vu[k], Vu[k], math.copysign(1.0, vu[k])])
        ys.append(vu[k + 1])
    result = {"samples": len(rows), "dt": dt}
    if len(rows) < 30:
        result.update(ok=False, reason=f"only {len(rows)} usable samples; the wheels barely moved")
        return result
    beta, r2 = ols(rows, ys)
    if beta is None:
        result.update(ok=False, reason="singular fit: no acceleration in the data to separate kA")
        return result
    alpha, b, g = beta
    if not (0 < alpha < 1) or abs(b) < 1e-12:
        result.update(ok=False, reason=f"unphysical fit (alpha={alpha:.4f}); usually a sign or "
                      "inversion problem, or the wheels slipped")
        return result
    A = math.log(alpha) / dt
    B = b * A / (alpha - 1)
    Cc = g * A / (alpha - 1)
    kA = 1.0 / B
    kV = -A / B
    kS = -Cc / B
    result.update(kS=kS, kV=kV, kA=kA, r2=r2)
    if kV <= 0:
        result.update(ok=False, reason="kV came out negative: voltage and speed disagree in sign. "
                      "That is a wiring or inversion fault, not a fit problem; more data will not fix it")
        return result
    if kA < 0:
        result.update(ok=False, reason="kA came out negative, which is not physical: something else "
                      "pushed the robot during the run (a collision, wheel slip). Run it again on clear carpet")
        return result
    result["ok"] = True

    # direct fit with central-difference acceleration, as a cross-check
    rows2, ys2 = [], []
    for k in range(1, len(tu) - 1):
        if abs(vu[k]) < min_speed:
            continue
        a = (vu[k + 1] - vu[k - 1]) / (2 * dt)
        rows2.append([math.copysign(1.0, vu[k]), vu[k], a])
        ys2.append(Vu[k])
    if len(rows2) >= 30:
        beta2, r22 = ols(rows2, ys2)
        if beta2:
            result["direct"] = {"kS": beta2[0], "kV": beta2[1], "kA": beta2[2], "r2": r22}
    return result


def fit_static(volts, v, min_speed=0.05):
    """kS and kV only, from steady samples. Used on blocks, where kA means nothing."""
    rows, ys = [], []
    for V, s in zip(volts, v):
        if abs(s) >= min_speed and finite(V):
            rows.append([math.copysign(1.0, s), s])
            ys.append(V)
    if len(rows) < 20:
        return {"ok": False, "samples": len(rows), "reason": "the wheels barely moved"}
    beta, r2 = ols(rows, ys)
    if beta is None:
        return {"ok": False, "samples": len(rows), "reason": "singular fit"}
    return {"ok": True, "kS": beta[0], "kV": beta[1], "r2": r2, "samples": len(rows)}


# ---------------------------------------------------------------------------- hand motion


def hand_motion(series, expected_sign=1, min_travel=None):
    """Verdict for one thing turned by hand in one direction.

    AGREES / INVERTED / NO_MOTION / AMBIGUOUS, as in the 2026 runbook: rocking it back and forth
    is reported as AMBIGUOUS rather than resolved in whichever direction it happened to end.
    """
    xs = [x for x in series if finite(x)]
    if len(xs) < 2:
        return {"verdict": "NO_DATA", "net": 0.0, "path": 0.0}
    net = xs[-1] - xs[0]
    path = sum(abs(xs[i + 1] - xs[i]) for i in range(len(xs) - 1))
    need = min_travel if min_travel is not None else 0.0
    if path < need:
        verdict = "NO_MOTION"
    elif abs(net) < 0.5 * path:
        verdict = "AMBIGUOUS"
    elif net * expected_sign > 0:
        verdict = "AGREES"
    else:
        verdict = "INVERTED"
    return {"verdict": verdict, "net": net, "path": path}


def ratio(a, b):
    """Slope of a against b by least squares through their changes: motor degrees per module degree."""
    da = [a[i] - a[0] for i in range(len(a))]
    db = [b[i] - b[0] for i in range(len(b))]
    num = sum(x * y for x, y in zip(da, db))
    den = sum(y * y for y in db)
    return num / den if den > 1e-9 else float("nan")
