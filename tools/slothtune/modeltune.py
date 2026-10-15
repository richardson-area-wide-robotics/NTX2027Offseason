"""Model-based tuning (decision 75): measure a mechanism on blocks, then compute its gains.

The round-by-round tuner guessed: change one gain, run, look, change again. This measures the
mechanism once and works the gains out from what it measured, the way WPILib's SysId does and the
way the teams that publish their methods (971, 6328) tune:

1. :func:`fit`: SysId's discrete-time least squares over a slow voltage ramp and a quick voltage
   step, each way: ``v[k+1] = a v[k] + b u[k] + c sgn(v[k])`` (``+ d`` for an elevator's gravity,
   ``+ d cos(x) + e sin(x)`` for an arm's), giving kS, kV, kA and kG (and where an arm's gravity
   pulls hardest). :func:`fit_held` is the same from position alone, exact for volts a robot loop
   holds between samples (the robot's ``system_id`` test).
2. :func:`delay`: how far the controller's own speed reading lags the position's: a SPARK's speed
   filter adds tens of milliseconds, and the feedback gains must allow for it.
3. :func:`lqr_pd`: a position loop's kP and kD as SysId computes them: a linear-quadratic regulator
   (Bryson's weights: the position error worth ``r`` volts), discretized at the SPARK's 1 ms loop,
   then compensated for the delay.
4. :func:`simc_pi`: a speed loop's kP and kI by Skogestad's SIMC rule, which writes the delay in
   explicitly (SysId's regulator gives a speed loop almost no gain once the filter's delay is in).
5. :func:`maxmotion`: MAXMotion's cruise speed and acceleration from the model, the battery the
   robot measured under load (decision 77) and the current limit.
6. :func:`predict`: the loop simulated at 1 kHz with the delay, saturation and friction, so a check
   run is judged against what the model expected: more than twice off means measure again.
7. :func:`spark_gains`: everything in the units a SPARK takes: kP, kI, kD per its own position or
   speed unit and the compensation voltage, the feedforward in volts.

Pure Python (the team laptops have no numpy or scipy): the matrices are 2 x 2 or 3 x 3.
"""

from __future__ import annotations

import cmath
import math

from . import analysis as A

SPARK_DT = 0.001          # a SPARK's closed loop runs every millisecond
V_HEADROOM = 0.8          # MAXMotion plans with 80% of the voltage, leaving the rest for feedback


# ---------------------------------------------------------------------------- small matrices


def _mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def _madd(a, b, s=1.0):
    return [[a[i][j] + s * b[i][j] for j in range(len(a[0]))] for i in range(len(a))]


def _mscale(a, s):
    return [[x * s for x in row] for row in a]


def _eye(n):
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _t(a):
    return [list(r) for r in zip(*a)]


def expm(a):
    """The matrix exponential (scaling and squaring with a Taylor series): small, well-scaled matrices."""
    n = len(a)
    norm = max(sum(abs(x) for x in row) for row in a)
    s = max(0, int(math.ceil(math.log2(norm))) + 1) if norm > 0.5 else 0
    x = _mscale(a, 1.0 / (2 ** s))
    out, term = _eye(n), _eye(n)
    for k in range(1, 20):
        term = _mscale(_mm(term, x), 1.0 / k)
        out = _madd(out, term)
    for _ in range(s):
        out = _mm(out, out)
    return out


def discretize(a, b, dt):
    """Zero-order-hold discretization of x' = A x + B u: (Ad, Bd), from one exponential."""
    n, m = len(a), len(b[0])
    big = [[0.0] * (n + m) for _ in range(n + m)]
    for i in range(n):
        for j in range(n):
            big[i][j] = a[i][j] * dt
        for j in range(m):
            big[i][n + j] = b[i][j] * dt
    e = expm(big)
    return [row[:n] for row in e[:n]], [row[n:] for row in e[:n]]


def _fractional_power_2x2(m, p):
    """M^p for a 2 x 2 matrix with distinct eigenvalues, through its eigendecomposition."""
    a, b, c, d = m[0][0], m[0][1], m[1][0], m[1][1]
    tr, det = a + d, a * d - b * c
    disc = cmath.sqrt(tr * tr / 4 - det)
    l1, l2 = tr / 2 + disc, tr / 2 - disc
    if abs(l1 - l2) < 1e-12:
        # Repeated eigenvalue: M = l I + N with N nilpotent, so M^p = l^p I + p l^(p-1) N.
        lp = l1 ** p
        n_ = [[a - l1, b], [c, d - l1]]
        return [[(lp + p * l1 ** (p - 1) * n_[i][j] if i == j else p * l1 ** (p - 1) * n_[i][j]).real
                 for j in range(2)] for i in range(2)]
    # Sylvester's formula.
    f1, f2 = l1 ** p, l2 ** p
    out = [[0.0, 0.0], [0.0, 0.0]]
    for i in range(2):
        for j in range(2):
            mij = m[i][j]
            i_ij = 1.0 if i == j else 0.0
            v = f1 * (mij - l2 * i_ij) / (l1 - l2) + f2 * (mij - l1 * i_ij) / (l2 - l1)
            out[i][j] = v.real
    return out


# ---------------------------------------------------------------------------- identification


def fit(t, pos, vel, volts, kind="ELEVATOR", angle_rad_per_unit=None, min_speed=None):
    """kS, kV, kA (and kG) from a run's applied volts and its measured motion, SysId's way.

    ``vel`` is the speed from the position's own differences (a filtered controller reading would
    inflate kA). ``kind`` is ELEVATOR (constant gravity), PIVOT (gravity times cos of the angle, with
    ``angle_rad_per_unit`` turning its position into radians), or FLYWHEEL/ROLLER (none). Samples
    slower than ``min_speed`` (default 2% of the fastest) are left out, as SysId leaves out the
    standstill. Returns ``{"ok", "kS", "kV", "kA", "kG", "offset_rad", "r2", "samples", "why"}``.
    """
    n = min(len(t), len(vel), len(volts))
    if n < 40:
        return {"ok": False, "why": "too few samples"}
    top = max((abs(v) for v in vel[:n] if v == v), default=0.0)
    if top <= 0:
        return {"ok": False, "why": "it never moved"}
    floor = min_speed if min_speed is not None else 0.02 * top
    arm = kind == "PIVOT" and angle_rad_per_unit
    rows, ys, dts = [], [], []
    for k in range(n - 1):
        v0, v1, u = vel[k], vel[k + 1], volts[k]
        dt = t[k + 1] - t[k]
        if not (v0 == v0 and v1 == v1 and u == u) or dt <= 0 or abs(v0) < floor or abs(v1) < floor:
            continue
        row = [v0, u, math.copysign(1.0, v0)]
        if kind == "ELEVATOR":
            row.append(1.0)
        elif arm:
            x = pos[k] * angle_rad_per_unit
            row += [math.cos(x), math.sin(x)]
        rows.append(row)
        ys.append(v1)
        dts.append(dt)
    if len(rows) < 30:
        return {"ok": False, "why": f"only {len(rows)} moving samples"}
    beta, r2 = A.ols(rows, ys)
    if not beta:
        return {"ok": False, "why": "the fit is singular: the run had no variety"}
    T = sorted(dts)[len(dts) // 2]
    alpha, b = beta[0], beta[1]
    if not (0 < alpha < 1) or abs(b) < 1e-12:
        return {"ok": False, "why": f"not a physical fit (alpha {alpha:.4f}): a sign, an inversion, or something pushed it", "r2": r2}
    kV = (1 - alpha) / b
    kA = -kV * T / math.log(alpha)
    kS = -beta[2] / b
    out = {"ok": True, "kS": kS, "kV": kV, "kA": kA, "kG": 0.0, "offset_rad": 0.0, "r2": r2,
           "samples": len(rows), "dt": T}
    if kind == "ELEVATOR":
        out["kG"] = -beta[3] / b
    elif arm:
        d, e = beta[3], beta[4]
        out["kG"] = math.hypot(d, e) / abs(b)
        out["offset_rad"] = math.atan2(e, -d) if b > 0 else math.atan2(-e, d)
    if kV <= 0 or kA <= 0:
        out.update(ok=False, why="kV or kA came out at or below zero: not a physical fit")
    elif r2 < 0.9:
        out.update(ok=False, why=f"the fit explains only {r2:.0%} of the motion (needs 90%): measure again")
    return out


def fit_held(t, pos, volts, kind="ELEVATOR", angle_rad_per_unit=None, min_speed=None, max_shift=3):
    """:func:`fit` from position alone, for volts held between samples.

    A robot loop sets the volts and holds them until the next loop. Over each interval the speed is
    then exactly ``(x[k+1] - x[k]) / T``, and the next interval's speed is a fixed mix of this one,
    the volts held over it and the volts held over the one before:
    ``v[k+1] = a v[k] + b0 u[k] + b1 u[k-1] + c sgn(v[k]) (+ gravity)``, with ``b0 + b1 = (1 - a) / kV``.
    A central difference would fold the next interval's volts into this sample's speed and inflate
    kA; a backward one without ``u[k-1]`` would leave half of each change unexplained.

    The volts may reach the motor a sample or more after they were recorded (CAN, status frames):
    shifts of 0 to ``max_shift`` samples are tried and the best fit kept (``shift`` in the result).

    A recorder sampling faster than the position arrives (a status frame every 10 ms, a simulation
    every 20 ms) repeats readings: only the samples where the position changed are kept, each
    interval's volts the average of what was asked over it, and an interval much longer than the
    rest (it sat still) breaks the chain.
    """
    n0 = min(len(t), len(pos), len(volts))
    keep = [k for k in range(n0) if k == 0 or pos[k] != pos[k - 1]]
    t = [t[k] for k in keep]
    pos = [pos[k] for k in keep]

    def held(shift):
        # The volts over each kept interval, recorded ``shift`` samples before they acted.
        out = []
        for j, k in enumerate(keep):
            end = keep[j + 1] if j + 1 < len(keep) else k + 1
            us = [volts[i - shift] for i in range(k, end) if i - shift >= 0 and volts[i - shift] == volts[i - shift]]
            out.append(sum(us) / len(us) if us else float("nan"))
        return out
    n = len(t)
    if n < 40:
        return {"ok": False, "why": "too few samples"}
    gaps = sorted(t[k] - t[k - 1] for k in range(1, n))
    longest = 2.5 * gaps[len(gaps) // 2]
    sp = [float("nan")] * n
    for k in range(1, n):
        dt = t[k] - t[k - 1]
        if 0 < dt <= longest and pos[k] == pos[k] and pos[k - 1] == pos[k - 1]:
            sp[k] = (pos[k] - pos[k - 1]) / dt
    top = max((abs(v) for v in sp if v == v), default=0.0)
    if top <= 0:
        return {"ok": False, "why": "it never moved"}
    floor = min_speed if min_speed is not None else 0.02 * top
    arm = kind == "PIVOT" and angle_rad_per_unit
    best = None
    for shift in range(0, max_shift + 1):
        u = held(shift)
        rows, ys, dts = [], [], []
        for k in range(1, n - 1):
            v0, v1 = sp[k], sp[k + 1]
            u0, um = u[k], u[k - 1]
            dt = t[k + 1] - t[k]
            if not (v0 == v0 and v1 == v1 and u0 == u0 and um == um) or dt <= 0 \
                    or abs(v0) < floor or abs(v1) < floor:
                continue
            row = [v0, u0, um, math.copysign(1.0, v0)]
            if kind == "ELEVATOR":
                row.append(1.0)
            elif arm:
                x = pos[k] * angle_rad_per_unit
                row += [math.cos(x), math.sin(x)]
            rows.append(row)
            ys.append(v1)
            dts.append(dt)
        if len(rows) < 30:
            continue
        beta, r2 = A.ols(rows, ys)
        if beta and (best is None or r2 > best[1]):
            best = (beta, r2, shift, len(rows), sorted(dts)[len(dts) // 2])
    if best is None:
        return {"ok": False, "why": "too few moving samples, or the fit is singular: the run had no variety"}
    beta, r2, shift, used, T = best
    alpha, b = beta[0], beta[1] + beta[2]
    if not (0 < alpha < 1) or abs(b) < 1e-12:
        return {"ok": False, "why": f"not a physical fit (alpha {alpha:.4f}): a sign, an inversion, or something pushed it",
                "r2": r2}
    kV = (1 - alpha) / b
    out = {"ok": True, "kS": -beta[3] / b, "kV": kV, "kA": -kV * T / math.log(alpha), "kG": 0.0, "offset_rad": 0.0,
           "r2": r2, "samples": used, "dt": T, "shift": shift}
    if kind == "ELEVATOR":
        out["kG"] = -beta[4] / b
    elif arm:
        d, e = beta[4], beta[5]
        out["kG"] = math.hypot(d, e) / abs(b)
        out["offset_rad"] = math.atan2(e, -d) if b > 0 else math.atan2(-e, d)
    if kV <= 0 or out["kA"] <= 0:
        out.update(ok=False, why="kV or kA came out at or below zero: not a physical fit")
    elif r2 < 0.9:
        out.update(ok=False, why=f"the fit explains only {r2:.0%} of the motion (needs 90%): measure again")
    return out


def delay(t, pos, ctrl_vel, max_s=0.15):
    """How far the controller's own speed reading lags the speed worked out from position, seconds:
    the lag that best lines the two up (0 to ``max_s``)."""
    n = min(len(t), len(pos), len(ctrl_vel))
    if n < 20:
        return None
    dv = [float("nan")] * n
    for k in range(1, n - 1):
        dt = t[k + 1] - t[k - 1]
        if dt > 0:
            dv[k] = (pos[k + 1] - pos[k - 1]) / dt
    dt = sorted(t[k + 1] - t[k] for k in range(n - 1))[(n - 1) // 2]
    if dt <= 0:
        return None
    best, best_err = 0.0, float("inf")
    for lag in range(0, int(max_s / dt) + 1):
        err, used = 0.0, 0
        for k in range(1 + lag, n - 1):
            a, b = ctrl_vel[k], dv[k - lag]
            if a == a and b == b:
                err += (a - b) ** 2
                used += 1
        if used > 10 and err / used < best_err:
            best, best_err = lag * dt, err / used
    return best


def velocity_from_position(t, pos):
    """The speed from the position's differences (central): unfiltered, so kA isn't inflated."""
    n = len(pos)
    out = [float("nan")] * n
    for k in range(1, n - 1):
        dt = t[k + 1] - t[k - 1]
        if dt > 0:
            out[k] = (pos[k + 1] - pos[k - 1]) / dt
    if n > 1:
        out[0], out[-1] = out[1], out[-2]
    return out


# ---------------------------------------------------------------------------- feedback


def lqr_pd(kV, kA, qp, qv, r=7.0, dt=SPARK_DT, delay_s=0.0):
    """A position loop's Kp (volts per unit) and Kd (volts per unit/s), as WPILib SysId computes
    them: x = [position, velocity], A = [[0, 1], [0, -kV/kA]], B = [[0], [1/kA]], Bryson's weights
    Q = diag(1/qp^2, 1/qv^2), R = 1/r^2, discretized at ``dt``, the discrete Riccati equation solved,
    then K compensated for ``delay_s`` as WPILib's LinearQuadraticRegulator does."""
    a = [[0.0, 1.0], [0.0, -kV / kA]]
    b = [[0.0], [1.0 / kA]]
    ad, bd = discretize(a, b, dt)
    q = [[1.0 / qp ** 2, 0.0], [0.0, 1.0 / qv ** 2]]
    rr = 1.0 / r ** 2
    p = q
    for _ in range(200000):
        bt_p = _mm(_t(bd), p)
        s = rr + _mm(bt_p, bd)[0][0]
        k = _mscale(_mm(bt_p, ad), 1.0 / s)
        nxt = _madd(_madd(_mm(_mm(_t(ad), p), ad), _mm(_t(_mm(bt_p, ad)), k), -1.0), q)
        if max(abs(nxt[i][j] - p[i][j]) for i in range(2) for j in range(2)) <= 1e-12 * max(1.0, abs(p[0][0])):
            p = nxt
            break
        p = nxt
    bt_p = _mm(_t(bd), p)
    k = _mscale(_mm(bt_p, ad), 1.0 / (rr + _mm(bt_p, bd)[0][0]))
    if delay_s > 0:
        closed = _madd(ad, _mm(bd, k), -1.0)
        steps = delay_s / dt
        if abs(steps - round(steps)) < 1e-6:
            # A whole number of controller steps (the usual case): a plain matrix power, always real.
            power = _eye(2)
            for _ in range(int(round(steps))):
                power = _mm(power, closed)
        else:
            power = _fractional_power_2x2(closed, steps)
        k = _mm(k, power)
    return k[0][0], k[0][1]


def simc_pi(kV, kA, delay_s, tau_c=None):
    """A speed loop's Kp (volts per unit/s) and Ki (volts per unit), Skogestad's SIMC for a first
    order plant with delay: gain 1/kV, time constant kA/kV, delay theta; tau_c defaults to theta
    (his 'tight but robust' choice: gain margin about 3, phase margin about 60 degrees)."""
    theta = max(delay_s, 0.0005)
    tc = theta if tau_c is None else tau_c
    tau = kA / kV
    kp = kA / (tc + theta)
    ti = min(tau, 4 * (tc + theta))
    return kp, kp / ti if ti > 0 else 0.0


# ---------------------------------------------------------------------------- MAXMotion


STALL_OHMS = {"NEO": 12 / 105, "NEO V1.1": 12 / 105, "NEO 2.0": 12 / 150, "NEO Vortex": 12 / 211,
              "Vortex": 12 / 211, "NEO 550": 12 / 100}


def maxmotion(model, volts, current_limit_a=None, motor="NEO", motors=1, move=None):
    """MAXMotion's limits from the model: ``{"cruise", "accel", "why"}`` in the mechanism's units.

    ``volts`` is what the battery holds under load (decision 77: measured on the robot, never an
    assumed 12 V); 80% of it is planned with, the rest left for feedback. The cruise speed is 80% of
    the fastest that leaves; the acceleration the least of what the voltage gives at cruise and what
    the current limit gives (each motor's resistance from its stall current), less 20%. ``move`` (a
    typical move, in units) caps the cruise speed at what a triangle profile reaches over it."""
    kS, kV, kA, kG = model["kS"], model["kV"], model["kA"], abs(model.get("kG") or 0.0)
    v_ff = V_HEADROOM * volts
    v_top = max(0.0, (v_ff - kS - kG) / kV)
    cruise = 0.8 * v_top
    a_v = max(0.0, (v_ff - kS - kG - kV * cruise) / kA)
    why = [f"{V_HEADROOM:.0%} of {volts:.1f} V measured under load"]
    a_i = None
    if current_limit_a:
        ohms = STALL_OHMS.get(motor, 12 / 105) / max(1, motors)
        a_i = max(0.0, (current_limit_a * ohms - kS - kG) / kA)
        why.append(f"{current_limit_a:.0f} A limit")
    accel = 0.8 * min(a_v, a_i) if a_i is not None else 0.8 * a_v
    if move and accel > 0:
        tri = math.sqrt(abs(move) * accel)      # the peak speed a triangle profile reaches over the move
        if cruise > tri:
            cruise, _ = tri, why.append("capped by the move's length")
    return {"cruise": cruise, "accel": accel, "v_top": v_top, "why": "; ".join(why)}


# ---------------------------------------------------------------------------- prediction


def _profile(x0, x1, vmax, amax, dt):
    """A trapezoid move: [(position, speed, acceleration)] each ``dt``."""
    d, s = abs(x1 - x0), 1 if x1 >= x0 else -1
    if amax <= 0 or vmax <= 0:
        return [(x1, 0.0, 0.0)]
    ta = vmax / amax
    if amax * ta * ta > d:
        ta = math.sqrt(d / amax)
        vmax = amax * ta
    tc = (d - amax * ta * ta) / vmax if vmax else 0.0
    out, t, total = [], 0.0, 2 * ta + tc
    while t < total:
        if t < ta:
            p, v, a = 0.5 * amax * t * t, amax * t, amax
        elif t < ta + tc:
            p, v, a = 0.5 * amax * ta * ta + vmax * (t - ta), vmax, 0.0
        else:
            r = total - t
            p, v, a = d - 0.5 * amax * r * r, amax * r, -amax
        out.append((x0 + s * p, s * v, s * a))
        t += dt
    out.append((x1, 0.0, 0.0))
    return out


def predict(model, gains, kind, move, cruise, accel, volts=12.0, delay_s=0.0, hold_s=1.0, dt=SPARK_DT,
            angle_rad_per_unit=None, start=0.0):
    """The loop simulated: the model, a 1 ms controller seeing the mechanism ``delay_s`` late,
    output limited to ``volts``. Positional: a profiled move of ``move`` units then a hold; speed: a
    ramp to ``move`` units/s then a hold. ``gains``: Kp, Kd (positional) or Kp, Ki (speed), and the
    feedforward kS, kV, kA, kG in volts. Returns overshoot (% of the move), error at the end (%),
    settling time (s, to 2% positional, 3% speed) and the peak volts."""
    kS, kV, kA, kG = model["kS"], model["kV"], model["kA"], model.get("kG") or 0.0
    positional = kind in ("ELEVATOR", "PIVOT")
    lag = max(0, int(round(delay_s / dt)))
    x, v = start, 0.0
    seen = [(x, v)] * (lag + 1)
    integ, peak_u = 0.0, 0.0
    if positional:
        ref = _profile(start, start + move, cruise, accel, dt)
    else:
        ramp = int(abs(move) / max(accel, 1e-9) / dt) + 1
        ref = [(0.0, move * min(1.0, k / ramp), (move / ramp / dt) if k < ramp else 0.0) for k in range(ramp + 1)]
    ref += [ref[-1][:1] + (ref[-1][1] if not positional else 0.0, 0.0)] * int(hold_s / dt)
    trace = []
    for rp, rv, ra in ref:
        xs, vs = seen[0]
        grav = kG * math.cos((x - (model.get("offset_rad") or 0.0) / (angle_rad_per_unit or 1)) * (angle_rad_per_unit or 0)) \
            if kind == "PIVOT" and angle_rad_per_unit else (kG if kind == "ELEVATOR" else 0.0)
        ff = kS * (1 if rv > 0 else -1 if rv < 0 else 0) + kV * rv + kA * ra + grav
        if positional:
            u = ff + gains.get("kP", 0) * (rp - xs) + gains.get("kD", 0) * (rv - vs)
        else:
            e = rv - vs
            integ += e * dt
            u = ff + gains.get("kP", 0) * e + gains.get("kI", 0) * integ
        u = max(-volts, min(volts, u))
        peak_u = max(peak_u, abs(u))
        fric = kS * (1 if v > 1e-9 else -1 if v < -1e-9 else 0)
        acc = (u - fric - kV * v - grav) / kA
        if abs(v) < 1e-9 and abs(u - grav) <= kS:
            acc = 0.0
        v += acc * dt
        x += v * dt
        seen = seen[1:] + [(x, v)]
        trace.append(x if positional else v)
    goal = (start + move) if positional else move
    step = abs(move) or 1.0
    arrive = len(ref) - int(hold_s / dt) - 1
    hold = trace[arrive:]
    tail = hold[-max(1, len(hold) // 4):]
    final = sum(tail) / len(tail)
    sign = 1 if move >= 0 else -1
    over = max(0.0, max((y - final) * sign for y in hold)) / step * 100
    err = (final - goal) / step * 100
    band = (0.02 if positional else 0.03) * step
    settle = next((j * dt for j in range(len(hold)) if all(abs(y - goal) <= band for y in hold[j:])), None)
    return {"overshoot_pct": over, "error_pct": err, "settle_s": settle, "peak_volts": peak_u}


# ---------------------------------------------------------------------------- the whole computation


POSITION_DELAY_S = 0.002   # a SPARK's onboard position loop: the encoder read and one loop, about 2 ms


def compute(model, kind, volts, delay_s, move, current_limit_a=None, motor="NEO", motors=1, aggressiveness=1.0,
            angle_rad_per_unit=None, position_delay_s=POSITION_DELAY_S):
    """Gains and limits for an identified mechanism, in its own units and volts: positional loops by
    LQR (the position error worth 7 V is 2% of the move, divided by ``aggressiveness``), speed loops
    by SIMC (tau_c = the delay, divided by ``aggressiveness``). ``aggressiveness`` is the one setting
    the check runs trim, within half and double.

    ``delay_s`` is the speed reading's measured delay: it is what a speed loop sees. A position loop
    on the SPARK reads its encoder every millisecond, so it sees only ``position_delay_s``; the
    speed filter's delay never reaches it (its D term uses the position's own differences)."""
    positional = kind in ("ELEVATOR", "PIVOT")
    mm = maxmotion(model, volts, current_limit_a, motor, motors, move if positional else None)
    gains = {"kS": model["kS"], "kV": model["kV"], "kA": model["kA"]}
    if kind == "ELEVATOR":
        gains["kG"] = model["kG"]
    elif kind == "PIVOT":
        gains["kCos"] = model["kG"]
    if positional:
        qp = max(1e-9, 0.02 * abs(move)) / aggressiveness
        qv = max(1e-9, 0.25 * (mm["cruise"] or 1.0))
        kp, kd = lqr_pd(model["kV"], model["kA"], qp, qv, r=7.0, delay_s=round(position_delay_s / SPARK_DT) * SPARK_DT)
        gains.update(kP=kp, kD=kd, kI=0.0)
    else:
        theta = max(delay_s, 0.0005)
        kp, ki = simc_pi(model["kV"], model["kA"], theta, tau_c=theta / aggressiveness)
        gains.update(kP=kp, kI=ki, kD=0.0)
    pred = predict(model, gains, kind, move, mm["cruise"] or abs(move), mm["accel"] or abs(move), volts=volts,
                   delay_s=position_delay_s if positional else delay_s, angle_rad_per_unit=angle_rad_per_unit)
    return {"gains": gains, "maxmotion": mm, "predicted": pred, "aggressiveness": aggressiveness}


def spark_gains(gains, mm, volts_comp, ratio_p=1.0, ratio_v=1.0, positional=True):
    """The gains in a SPARK's units, with voltage compensation at ``volts_comp``: kP, kI, kD in duty
    per its own position (or speed) unit, kD per unit change per millisecond and kI per unit
    accumulated each millisecond (REV's units); kS, kG, kCos in volts; kV, kA in volts per its speed
    unit. ``ratio_p`` / ``ratio_v``: the SPARK's position / speed units per the mechanism's (read
    from the identification run, so whatever conversion factors the code set are honored). MAXMotion's
    cruise and acceleration come back in the SPARK's speed units (and per second)."""
    rv = ratio_p if positional else ratio_v
    out = {"kP": gains["kP"] / (volts_comp * rv),
           "kI": gains.get("kI", 0.0) * SPARK_DT / (volts_comp * rv),
           "kD": gains.get("kD", 0.0) / (volts_comp * SPARK_DT * rv),
           "kS": gains["kS"], "kV": gains["kV"] / ratio_v, "kA": gains["kA"] / ratio_v}
    for k in ("kG", "kCos"):
        if k in gains:
            out[k] = gains[k]
    if mm:
        out["mmCruise"] = mm["cruise"] * ratio_v
        out["mmAccel"] = mm["accel"] * ratio_v
    return out


def compensation_volts(loaded_min_volts):
    """The voltage to compensate to (decision 77): what the battery held at the hardest pull of the
    identification, less a margin, rounded down to a half volt; never above 12 or below 9."""
    if not loaded_min_volts or loaded_min_volts != loaded_min_volts:
        return 11.0
    return max(9.0, min(12.0, math.floor((loaded_min_volts - 0.3) * 2) / 2))
