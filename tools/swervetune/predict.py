"""'What if I change this gain?' - predicted from a model fitted to a run the robot really made.

Changing a gain on a robot and running it again is the truth, and nothing here replaces it. But a
student learns faster by dragging kP and watching the curve move, and a wild guess that would slam
a module is better tried on a model first. So:

1. **Identify** a small model of the mechanism from one recorded step test: how many volts it
   takes to start moving (kS), to hold a speed (kV), to accelerate (kA), plus the motor's own
   current limit and the controller's speed filter. Units are the loop's: degrees for steering,
   meters per second for drive.
2. **Replay** the run on the model with the gains that were in force, and compare with what the
   robot did. That comparison is the model's honesty: if the replay misses, the prediction will
   too, and the result says so.
3. **Predict** the same setpoints with new gains, using REV's controller semantics (duty-cycle
   output, kD and kI per 1 ms step, ramp, clamp, current limit) - the same as the practice pod.

What the model leaves out: backlash, the wheel's grip changing as it turns on carpet, battery sag,
and anything that makes one step different from the next. Small changes predict well; a gain ten
times bigger predicts the direction, not the number.
"""

from __future__ import annotations

import math

from . import analysis as A
from . import explain
from .plant import Motor, SparkPid

DT = 0.0005  # physics step, s
STEER_COUNTS_PER_MOTOR_REV = 42


def _sgn(x):
    return (x > 0) - (x < 0)


def _deriv(t, y):
    out = [0.0] * len(y)
    for i in range(1, len(y) - 1):
        dt = t[i + 1] - t[i - 1]
        out[i] = (y[i + 1] - y[i - 1]) / dt if dt > 0 else 0.0
    if len(y) > 2:
        out[0], out[-1] = out[1], out[-2]
    return out


def _avg(xs, w):
    if w <= 1:
        return list(xs)
    h = w // 2
    return [A.mean(xs[max(0, i - h):i + h + 1]) for i in range(len(xs))]


# ============================================================================ identification


def identify(t, sp, y, volts, loop, motor_kind, gear, current_limit, units_per_motor_rad,
             vel_window_ms=0):
    """Fits ``V = kS*sgn(w) + kV*w + kA*a`` (w the loop's speed) from a step test.

    ``units_per_motor_rad`` converts motor shaft radians to the loop's units (degrees of module,
    or meters of wheel travel), so the motor's back-EMF and current limit can be put in those
    units. ``vel_window_ms`` is how late the recorded speed is (drive only), so acceleration is
    lined up with the voltage that caused it.
    """
    t, sp, y, volts = A.resample(t, sp, y, volts)
    if loop == "steer":
        y = A.unwrap_deg(y)
    shift = 0
    if vel_window_ms and len(t) > 2:
        dt = t[1] - t[0]
        shift = max(0, int(round(vel_window_ms / 1000.0 / dt)))
    if loop == "steer":
        w = _avg(_deriv(t, y), 3)
    else:
        w = list(y[shift:]) + [y[-1]] * shift  # the recorded speed, moved back to when it happened
    a = _avg(_deriv(t, w), 3)
    fast = 20.0 if loop == "steer" else 0.05
    rows, ys = [], []
    for i in range(2, len(t) - 2):
        if A.finite(volts[i]) and A.finite(w[i]) and A.finite(a[i]) and abs(w[i]) > fast:
            rows.append([_sgn(w[i]), w[i], a[i]])
            ys.append(volts[i])
    motor = Motor(motor_kind)
    k_bemf = 1.0 / (motor.Kv * units_per_motor_rad)  # volts per loop unit per second
    model = {"loop": loop, "motor": motor_kind, "gear": gear, "current_limit": current_limit,
             "R": motor.R, "k_bemf": k_bemf, "ok": False, "samples": len(rows),
             "units_per_motor_rad": units_per_motor_rad}
    if len(rows) < 12:
        model["reason"] = "the run has too little motion to learn from"
        return model
    beta, r2 = A.ols(rows, ys)
    if beta is None:
        model["reason"] = "the fit failed"
        return model
    kS, kV, kA = beta
    if kV <= 0 or kA <= 0:
        model["reason"] = (f"the fit is not physical (kV {kV:.3g}, kA {kA:.3g}): the run may be "
                           "saturated throughout, or slipping")
        return model
    kV = max(kV, k_bemf)  # never less than the motor's own back-EMF
    # Static friction: the largest voltage seen holding still short of the target, judged only
    # where each step has settled - just after a step, a wheel that has not moved yet is late,
    # not stuck.
    tails = set()
    for a0, b0, _ in A.segments(t, sp):
        if b0 - a0 >= 10:  # resampling blurs a step's edge into a one-sample "segment"
            tails.update(range(a0 + int((b0 - a0) * 0.6), b0))
    stuck = [abs(volts[i]) for i in sorted(tails)
             if A.finite(volts[i]) and A.finite(w[i]) and abs(w[i]) < fast * 0.25
             and A.finite(sp[i]) and abs((A.wrap180(sp[i] - y[i]) if loop == "steer" else sp[i] - y[i]))
             > (0.5 if loop == "steer" else 0.02)]
    static = max([max(0.0, kS)] + stuck) * 1.05
    model.update(ok=True, kS=max(0.0, kS), kV=kV, kA=kA, r2=r2, static=static)
    return model


# ============================================================================ simulation


def simulate(model, t_out, sp_out, gains, vbus=12.0, feedforward=None, vel_period_ms=32,
             vel_depth=8, absolute=False, delay_s=0.0, comp_v=None):
    """Runs the setpoints through the model under a REV-style controller.

    Returns the loop's measurement at each ``t_out`` (seconds), seen ``delay_s`` late the way the
    robot's recording sees it. ``comp_v`` is the voltage the SPARK compensates to (YAGSL: 12 V): a
    duty of 1 means that many volts, capped at the battery's ``vbus``. None means no compensation.
    """
    per_duty = comp_v or vbus
    loop = model["loop"]
    pre = "Steer/" if loop == "steer" else "Drive/"
    pid = SparkPid(gains.get(pre + "kP", 0.0), gains.get(pre + "kI", 0.0), gains.get(pre + "kD", 0.0),
                   gains.get(pre + "IZone", 0.0), gains.get(pre + "RampS", 0.0),
                   wrap=360.0 if loop == "steer" else None)
    kS, kV, kA, static = model["kS"], model["kV"], model["kA"], model["static"]
    k_bemf, R, ilim = model["k_bemf"], model["R"], model["current_limit"] or 1e9
    ff = feedforward or (0.0, 0.0)
    pos = sp_out[0] if loop == "steer" and A.finite(sp_out[0]) else 0.0
    if loop == "steer":
        pos = 0.0
    w = 0.0
    # Sensors the controller sees.
    if loop == "steer":
        counts_per_unit = (STEER_COUNTS_PER_MOTOR_REV / (2 * math.pi)) / model["units_per_motor_rad"]
        if absolute:
            counts_per_unit = 1024 / 360.0
    vel_hist, raw_hist = [], []
    period = max(1, int(vel_period_ms or 32))
    depth = max(1, int(vel_depth or 8))
    meas_v = 0.0

    end = t_out[-1] + delay_s + DT
    t, next_ctrl, duty = t_out[0], t_out[0], 0.0
    j = 0
    sp_now = sp_out[0]
    trace_t, trace_y = [], []
    pos_hist = []
    while t <= end:
        while j + 1 < len(t_out) and t_out[j + 1] <= t:
            j += 1
        sp_now = sp_out[j] if A.finite(sp_out[j]) else sp_now
        if t >= next_ctrl:
            if loop == "steer":
                meas = round(pos * counts_per_unit) / counts_per_unit
                duty = pid.step(sp_now, meas)
            else:
                pos_hist.append(pos)
                if len(pos_hist) > period + 1:
                    pos_hist.pop(0)
                span = len(pos_hist) - 1
                if span > 0:
                    raw_hist.append((pos_hist[-1] - pos_hist[0]) / (span / 1000.0))
                    if len(raw_hist) > depth:
                        raw_hist.pop(0)
                    meas_v = sum(raw_hist) / len(raw_hist)
                arb = (ff[0] * _sgn(sp_now) + ff[1] * sp_now) / per_duty
                duty = pid.step(sp_now, meas_v, arb)
            next_ctrl += 0.001
        v = max(-vbus, min(vbus, duty * per_duty))  # compensated, but never more than the battery has
        bemf = k_bemf * w
        v = max(bemf - R * ilim, min(bemf + R * ilim, v))
        if abs(w) < 1e-9:
            if abs(v) <= static:
                acc = 0.0
            else:
                acc = (v - kS * _sgn(v)) / kA
        else:
            acc = (v - kS * _sgn(w) - kV * w) / kA
        w_new = w + acc * DT
        if w != 0 and w_new * w < 0 and abs(v) <= static:
            w_new = 0.0  # friction stops it rather than reversing it
        w = w_new
        pos += w * DT
        trace_t.append(t)
        trace_y.append(pos if loop == "steer" else (meas_v if loop == "drive" else pos))
        t += DT
    # Sample the trace delay_s late at the output times.
    out, k = [], 0
    for tt in t_out:
        target = tt - delay_s
        while k + 1 < len(trace_t) and trace_t[k + 1] <= target:
            k += 1
        out.append(trace_y[k] if trace_t[k] <= target or k == 0 else trace_y[k])
    return out


# ============================================================================ the public call


def _rms(a, b, wrap=False):
    d = [(A.wrap180(x - y) if wrap else x - y) for x, y in zip(a, b) if A.finite(x) and A.finite(y)]
    return math.sqrt(sum(v * v for v in d) / len(d)) if d else float("nan")


def _summary(t, sp, y, loop):
    steps = A.analyze_steps(t, sp, y, tol_abs=1.0 if loop == "steer" else 0.05)
    if not steps:
        return {}
    def med(key):
        vals = [s[key] for s in steps if s.get(key) is not None and A.finite(s[key])]
        return A.median(vals) if vals else None
    return {"rise_time": med("rise_time"), "overshoot_pct": med("overshoot_pct"),
            "settling_time": med("settling_time"), "steady_state_error": med("steady_state_error"),
            "settled": all(s["settled"] for s in steps), "oscillations": max(s["oscillations"] for s in steps)}


def predict(result, gains_now, gains_new, module=0, current_limit=None, motor_kind=None,
            wheel_d_in=3.0):
    """Model, replay and prediction for one module of a steer_step or drive_step run."""
    loop = {"steer_step": "steer", "drive_step": "drive"}.get(result.get("test"))
    if not loop:
        return {"ok": False, "reason": "predictions are for steering and drive step tests"}
    ch = result.get("channels") or {}
    meta = result.get("meta") or {}
    t = ch.get("t") or []
    m = module
    names = (result.get("robot") or {}).get("modules") or []
    name = names[m] if m < len(names) else f"m{m}"
    vbus_s = [v for v in ch.get("vbus") or [] if A.finite(v)]
    vbus = A.median(vbus_s) if vbus_s else 12.0
    comp = explain.compensation_volts(meta)
    volts = ch.get(f"m{m}.volts")
    if loop == "steer":
        absolute = meta.get("steer_feedback_absolute") == 1
        sp, y = ch.get(f"m{m}.sp"), ch.get(f"m{m}.steer")
        gear = meta.get("steer_gear_ratio") or 46.42
        kind = motor_kind or "neo550"
        units = math.degrees(1.0) / gear  # module degrees per motor radian
        limit = current_limit or 20.0
        window = 0
        ff = None
        period = depth = 0
    else:
        absolute = False
        sp = ch.get(f"m{m}.spm") or ch.get("sp")
        y = ch.get(f"m{m}.v")
        gear = meta.get("drive_gear_ratio") or 5.5
        kind = motor_kind or "neo"
        units = wheel_d_in * 0.0254 / 2 / gear  # wheel meters per motor radian
        limit = current_limit or 40.0
        period = int(gains_now.get("Drive/VelPeriodMs") or 32)
        depth = int(gains_now.get("Drive/VelDepth") or 8)
        window = period / 2 + depth / 2
        ff = (gains_now.get(f"FF/{name}/kS", 0.0), gains_now.get(f"FF/{name}/kV", 0.0))
    if not (t and sp and y and volts):
        return {"ok": False, "reason": "this run does not have the channels a prediction needs"}

    model = identify(t, sp, y, volts, loop, kind, gear, limit, units, window)
    if not model["ok"]:
        return {"ok": False, "reason": "Could not learn a model from this run: " + model["reason"],
                "model": model}

    ff_new = ff
    if loop == "drive":
        ff_new = (gains_new.get(f"FF/{name}/kS", ff[0]), gains_new.get(f"FF/{name}/kV", ff[1]))
        period_new = int(gains_new.get("Drive/VelPeriodMs") or period)
        depth_new = int(gains_new.get("Drive/VelDepth") or depth)
    else:
        period_new, depth_new = period, depth

    # The recording sees the mechanism late (status frames, the speed filter); find how late by
    # lining the replay up with what was recorded.
    best = None
    for delay_ms in range(0, 65, 5):
        rep = simulate(model, t, sp, gains_now, vbus, ff, period, depth, absolute, delay_ms / 1000.0,
                       comp_v=comp)
        err = _rms(rep, y, wrap=loop == "steer")
        if best is None or err < best[0]:
            best = (err, delay_ms, rep)
    rms, delay_ms, replay = best
    predicted = simulate(model, t, sp, gains_new, vbus, ff_new, period_new, depth_new, absolute,
                         delay_ms / 1000.0, comp_v=comp)

    sizes = [abs(A.wrap180(b2 - a2) if loop == "steer" else b2 - a2)
             for (_, _, a2), (_, _, b2) in zip(A.segments(t, sp), A.segments(t, sp)[1:])]
    scale = A.mean(sizes) if sizes else 1.0
    rel = rms / scale if scale else float("nan")
    quality = "good" if rel < 0.06 else "fair" if rel < 0.15 else "rough"
    return {
        "ok": True, "loop": loop, "module": name, "units": "°" if loop == "steer" else "m/s",
        "model": {k: model[k] for k in ("kS", "kV", "kA", "static", "r2", "motor", "gear",
                                         "current_limit", "samples")},
        "delay_ms": delay_ms, "rms": rms, "relative_error": rel, "quality": quality,
        "t": t, "sp": sp, "measured": y, "replay": replay, "predicted": predicted,
        "summary": {"measured": _summary(t, sp, y, loop), "replay": _summary(t, sp, replay, loop),
                    "predicted": _summary(t, sp, predicted, loop)},
        "note": {"good": "The model replays this run closely; small gain changes should predict well.",
                 "fair": "The model replays this run roughly; trust the direction of a change more "
                         "than the exact numbers.",
                 "rough": "The model does not replay this run well (slip, backlash or a bump?). "
                          "Treat the prediction as a sketch and let the robot decide."}[quality],
    }
