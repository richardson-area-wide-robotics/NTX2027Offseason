"""What the controller saw and what it did, rebuilt from a recorded run, for teaching.

A SPARK runs its PID loop a thousand times a second inside the motor controller; the robot only
records what it can read every few milliseconds. From the setpoint, the measurement the loop uses
and the gains in force, this rebuilds each part of the controller's output the way the SPARK
computed it:

* **error** - setpoint minus measurement, what the controller "sees";
* **P term** - ``kP x error``: a spring pulling toward the target, harder the further away;
* **I term** - ``kI x accumulated error``: pushes harder the longer an error persists;
* **D term** - ``kD x change in error``: a damper that brakes the motion as the target nears;
* **feedforward** (drive only) - ``kS + kV x speed``: the voltage physics says the speed needs,
  sent before any error appears;
* **asked** - their sum, as volts; **applied** - what the controller really put out, which is less
  when the battery, the current limit or the ramp rate held it back.

Everything is in volts so the parts add up. REV's units are kept: kP is duty cycle per unit of
error, and kD and kI act per one-millisecond controller step, so a change in error is per
millisecond, not per second. YAGSL turns on the SPARK's voltage compensation at 12 V
(``optimalVoltage``; each run records it as ``comp_volts``), so a duty of 1 means 12 V on any
battery - as long as the battery has 12 V to give. The battery line on the graph is what it had.

Then it finds the moments worth a student's attention - dead time, flat-out saturation, the P
term's strongest push, D braking, overshoot, the error left at the end - and writes a sentence
for each, tied to a lesson in the GUI. These are annotations for graphs, not verdicts: the
advisor judges, this explains.
"""

from __future__ import annotations

from . import analysis as A
from . import units as U

# The units of a run's numbers (the "units" each module reports); the story's words read drive
# speeds in ft/s.
STEER_ERROR_UNITS = "°"
DRIVE_ERROR_UNITS = "m/s"


def _sgn(x):
    return (x > 0) - (x < 0)


def _gain(gains, key, default=0.0):
    v = (gains or {}).get(key)
    return float(v) if v is not None and A.finite(v) else default


def _channel(ch, key, n, default=float("nan")):
    v = ch.get(key)
    return list(v) if v and len(v) == n else [default] * n


def _spans(mask, t, min_len=2):
    """Contiguous runs where mask is true: [(t_start, t_end, i_start, i_end_exclusive)]."""
    out, start = [], None
    for i, m in enumerate(mask + [False]):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if i - start >= min_len:
                out.append((t[start], t[i - 1], start, i))
            start = None
    return out


def _terms(t, sp, meas, vbus, kP, kI, kD, i_zone, wrap):
    """Rebuilds the PID terms in volts at the recorded samples. ``vbus`` is what a duty of 1 means
    in volts at each sample: the compensation voltage when the SPARK compensates."""
    n = len(t)
    err, p, i_t, d = [], [], [], []
    acc, prev_e, prev_t = 0.0, None, None
    for k in range(n):
        e = sp[k] - meas[k] if A.finite(sp[k]) and A.finite(meas[k]) else float("nan")
        if wrap and A.finite(e):
            e = A.wrap180(e)
        err.append(e)
        vb = vbus[k] if A.finite(vbus[k]) else 12.0
        p.append(kP * e * vb if A.finite(e) else float("nan"))
        if A.finite(e) and prev_t is not None:
            dt_ms = max(1e-3, (t[k] - prev_t) * 1000.0)
            if i_zone and abs(e) > i_zone:
                acc = 0.0
            else:
                acc += e * dt_ms  # the SPARK adds the error once per 1 ms step
            d.append(kD * (e - prev_e) / dt_ms * vb if prev_e is not None and A.finite(prev_e) else 0.0)
        else:
            d.append(0.0)
        i_t.append(kI * acc * vb)
        if A.finite(e):
            prev_e, prev_t = e, t[k]
    # Differences of sampled data are noisy; a short median shows what the D term does on average.
    d = A.smooth(d, 5)
    return err, p, i_t, d


def compensation_volts(meta):
    """The voltage the SPARKs compensate to: the run's ``comp_volts``, else YAGSL's default 12 V."""
    v = (meta or {}).get("comp_volts")
    return float(v) if isinstance(v, (int, float)) and A.finite(v) and v > 0 else 12.0


def explain_module(result, gains, m, loop, current_limit=None):
    """One module of a steer_step or drive_step run. Returns None if the channels are missing."""
    ch = result.get("channels") or {}
    t = ch.get("t") or []
    n = len(t)
    meta = result.get("meta") or {}
    if n < 10:
        return None
    vbus = _channel(ch, "vbus", n, 12.0)
    per_duty = [compensation_volts(meta)] * n  # what a duty of 1 means, in volts
    # The most the motor can be given at each moment: the battery, but no more than the 12 V the
    # SPARK is compensated to, so "flat out" shows on a fresh battery too.
    cap = [min(v, per_duty[0]) if A.finite(v) else per_duty[0] for v in vbus]
    volts = _channel(ch, f"m{m}.volts", n)
    amps = _channel(ch, f"m{m}.amps", n)
    names = (result.get("robot") or {}).get("modules") or []
    name = names[m] if m < len(names) else f"m{m}"
    if loop == "steer":
        if f"m{m}.sp" not in ch or f"m{m}.steer" not in ch:
            return None
        sp = _channel(ch, f"m{m}.sp", n)
        absolute = meta.get("steer_feedback_absolute") == 1
        meas = _channel(ch, f"m{m}.steer" if absolute else f"m{m}.motor", n)
        if not any(A.finite(x) for x in meas):
            meas = _channel(ch, f"m{m}.steer", n)
        shown = _channel(ch, f"m{m}.steer", n)
        kP, kI, kD = (_gain(gains, "Steer/" + k) for k in ("kP", "kI", "kD"))
        i_zone = _gain(gains, "Steer/IZone")
        ramp = _gain(gains, "Steer/RampS")
        limit = current_limit or 20.0
        err, p, i_t, d = _terms(t, sp, meas, per_duty, kP, kI, kD, i_zone, wrap=True)
        ff = [0.0] * n
        units = STEER_ERROR_UNITS
        sensor = "the absolute encoder" if absolute else "the steering motor's own encoder"
    else:
        if f"m{m}.v" not in ch:
            return None
        sp = _channel(ch, f"m{m}.spm", n) if f"m{m}.spm" in ch else _channel(ch, "sp", n)
        meas = _channel(ch, f"m{m}.v", n)
        shown = meas
        kP, kI, kD = (_gain(gains, "Drive/" + k) for k in ("kP", "kI", "kD"))
        i_zone = _gain(gains, "Drive/IZone")
        ramp = _gain(gains, "Drive/RampS")
        limit = current_limit or 40.0
        err, p, i_t, d = _terms(t, sp, meas, per_duty, kP, kI, kD, i_zone, wrap=False)
        kS = _gain(gains, f"FF/{name}/kS")
        kV = _gain(gains, f"FF/{name}/kV", 0.0)
        ff = [kS * _sgn(s) + kV * s if A.finite(s) else float("nan") for s in sp]
        units = DRIVE_ERROR_UNITS
        sensor = "the drive motor's encoder, after its speed filter"

    asked, limit_line = [], []
    for k in range(n):
        vb = vbus[k] if A.finite(vbus[k]) else 12.0
        total = sum(x for x in (p[k], i_t[k], d[k], ff[k]) if A.finite(x))
        asked.append(total)
        limit_line.append(vb)

    out = {
        "module": name, "index": m, "loop": loop, "units": units, "sensor": sensor,
        "gains": {"kP": kP, "kI": kI, "kD": kD, "iZone": i_zone, "ramp": ramp},
        "t": t, "sp": sp, "measured": shown, "seen": meas, "error": err, "p": p, "i": i_t, "d": d, "ff": ff,
        "asked": asked, "applied": volts, "battery": limit_line,
        "response": [], "controller": [], "story": [],
    }
    _moments(out, t, sp, shown, err, p, d, ff, asked, volts, amps, cap, limit, loop, units)
    return out


def _note(out, plot, kind, learn, text, **where):
    step = out.get("_step")
    item = {"type": kind, "learn": learn, "text": text, "step": step}
    item.update(where)
    out[plot].append(item)
    if "t" in where or "x0" in where:
        out["story"].append({"t": where.get("t", where.get("x0")), "learn": learn, "text": text,
                             "step": step, "size": out.get("_size")})


def _moments(out, t, sp, y, err, p, d, ff, asked, applied, amps, vbus, limit, loop, units):
    segs = A.segments(t, sp)
    for k, (a, b, r) in enumerate(segs):
        if k == 0 or b - a < 6:
            continue
        start = max(a - 1, 0)
        y0 = y[start]
        if not (A.finite(y0) and A.finite(r)):
            continue
        size = (A.wrap180(r - y0) if loop == "steer" else r - y0)
        if abs(size) < 1e-6:
            continue
        sign = 1 if size > 0 else -1
        seg_t, seg_y = t[start:b], y[start:b]
        tol = 1.0 if loop == "steer" else 0.05
        mt = A.step_metrics(seg_t, r, seg_y, applied[start:b], tol=max(tol, 0.02 * abs(size)),
                            u_max=None, amps=amps[start:b], amp_limit=limit)
        if not mt:
            continue
        t0 = t[a]
        # The words: a speed in ft/s, an angle as it is.
        say, k_say = (" ft/s", U.FT_PER_M) if units == DRIVE_ERROR_UNITS else (units, 1.0)
        step_name = f"step {k} ({'+' if size > 0 else ''}{size * k_say:.3g}{say})"
        out["_step"], out["_size"] = k, abs(size)

        if mt["dead_time"] and mt["dead_time"] > 0.004:
            _note(out, "response", "vspan", "dead_time",
                  f"{step_name}: for {mt['dead_time'] * 1000:.0f} ms nothing moves. The new setpoint "
                  "has to reach the controller, current has to build, and friction has to give. No "
                  "gain removes dead time; it limits how aggressive any gain can safely be.",
                  x0=t0, x1=t0 + mt["dead_time"])

        # Rise: where it crosses 10% and 90% of the way.
        def cross(frac):
            for i in range(a, b):
                if A.finite(y[i]) and ((A.wrap180(y[i] - y0) if loop == "steer" else y[i] - y0) * sign
                                       >= frac * abs(size)):
                    return i
            return None
        i10, i90 = cross(0.1), cross(0.9)
        if i10 is not None and i90 is not None and i90 > i10:
            _note(out, "response", "rise", "rise_time",
                  f"{step_name}: 10% to 90% of the way in {(t[i90] - t[i10]) * 1000:.0f} ms. Rise time "
                  "is mostly kP (the spring) and how hard the motor can push.",
                  x0=t[i10], x1=t[i90], y0=y[i10], y1=y[i90])

        # Flat out: everything the battery has, or held at the current limit.
        flat = [A.finite(applied[i]) and A.finite(vbus[i]) and abs(applied[i]) >= 0.95 * vbus[i]
                for i in range(a, b)]
        held = [A.finite(amps[i]) and limit > 0 and abs(amps[i]) >= 0.9 * limit for i in range(a, b)]
        for x0, x1, _, _ in _spans(flat, t[a:b]):
            _note(out, "controller", "vspan", "saturation",
                  f"{step_name}: flat out from {x0:.2f} to {x1:.2f} s - the controller asks for more "
                  "than the battery has. Here the gains do not matter: a bigger kP cannot push harder. "
                  "WPILib: a saturated mechanism behaves as if its gains were smaller.",
                  x0=x0, x1=x1)
        # Held back by the ramp: asking for much more than it gets, with battery and current to spare.
        ramp = out["gains"].get("ramp", 0.0)
        slewed = [ramp > 0 and A.finite(asked[i]) and A.finite(applied[i]) and not flat[i - a] and not held[i - a]
                  and abs(asked[i]) - abs(applied[i]) > 1.0 and _sgn(asked[i]) == _sgn(applied[i] or asked[i])
                  for i in range(a, b)]
        for x0, x1, _, _ in _spans(slewed, t[a:b], min_len=3):
            _note(out, "controller", "vspan", "ramp_rate",
                  f"{step_name}: from {x0:.2f} to {x1:.2f} s the controller asks for far more than it gets, "
                  f"with battery and current to spare: the {ramp:.2f} s ramp rate only lets the output climb "
                  "so fast. That is pure added delay inside the loop.", x0=x0, x1=x1)
        for x0, x1, _, _ in _spans(held, t[a:b]):
            _note(out, "controller", "vspan", "current_limit",
                  f"{step_name}: held at the {limit:.0f} A current limit from {x0:.2f} to {x1:.2f} s. "
                  "The limit protects the motor and the wheels' grip; it also caps how fast this can go.",
                  x0=x0, x1=x1)

        # The P term's strongest push.
        idx = [i for i in range(a, b) if A.finite(p[i])]
        if idx:
            ip = max(idx, key=lambda i: abs(p[i]))
            if abs(p[ip]) > 0.05:
                vb = vbus[ip] if A.finite(vbus[ip]) else 12.0
                clipped = (f" That is more than the {vb:.1f} V it can give, so the controller can only "
                           "give all it has." if abs(p[ip]) > vb else "")
                # kP is per m/s on drive, so the product quotes the error in the gain's unit.
                times = "kP x error" if k_say == 1.0 else f"kP x {abs(err[ip]):.3g} m/s (kP is per m/s)"
                _note(out, "controller", "point", "kP",
                      f"{step_name}: the biggest error, {abs(err[ip]) * k_say:.3g}{say}, so P pushes hardest: "
                      f"{times} = {p[ip]:+.2f} V.{clipped} P is a spring: the further from the "
                      "target, the harder it pulls.", t=t[ip], y=p[ip], series="p")

        # D braking: D opposing P while the error closes.
        for i in range(a, b):
            if (A.finite(p[i]) and A.finite(d[i]) and abs(p[i]) > 0.1 and _sgn(d[i]) == -_sgn(p[i])
                    and abs(d[i]) >= 0.25 * abs(p[i])):
                _note(out, "controller", "point", "kD",
                      f"{step_name}: D is braking ({d[i]:+.2f} V against P's {p[i]:+.2f} V). The error "
                      "is shrinking fast, so D pushes back to stop it overshooting - a damper.",
                      t=t[i], y=d[i], series="d")
                break

        # Overshoot.
        if mt["overshoot_pct"] > 2:
            prog = [((A.wrap180(y[i] - y0) if loop == "steer" else y[i] - y0) * sign / abs(size), i)
                    for i in range(a, b) if A.finite(y[i])]
            _, ipk = max(prog)
            _note(out, "response", "point", "overshoot",
                  f"{step_name}: overshoots by {mt['overshoot_pct']:.0f}% - it carried past the "
                  "target. More damping (kD) or a softer spring (kP) settles it; on a steering axis "
                  "overshoot sends the robot sideways for a moment.", t=t[ipk], y=y[ipk])

        if mt["oscillations"] >= 2:
            _note(out, "response", "vspan", "oscillation",
                  f"{step_name}: swings back and forth {mt['oscillations']} times. Too much spring "
                  "(kP) for this much damping (kD) and this much delay.", x0=t0, x1=t[b - 1])

        # Settling band and what is left over.
        band = mt["band"]
        _note(out, "response", "band", "settling_time",
              f"{step_name}: the settling band is ±{band * k_say:.3g}{say}. "
              + (f"It stays inside after {mt['settling_time'] * 1000:.0f} ms." if mt["settled"]
                 else "It never settles inside it."),
              x0=t0, x1=t[b - 1], y0=r - band, y1=r + band)
        sse = mt["steady_state_error"]
        if abs(sse) > band:
            tail = [i for i in range(a + int((b - a) * 0.8), b) if A.finite(p[i])]
            p_end = A.mean([p[i] for i in tail]) if tail else float("nan")
            ff_end = A.mean([ff[i] for i in tail if A.finite(ff[i])]) if tail else 0.0
            if loop == "steer":
                why = (f"There P makes only {abs(p_end):.2f} V, not enough to beat the carpet's grip on "
                       "the wheel, so it stops short. A little more kP, or a tiny kI with an IZone "
                       "of a few degrees, closes it - WPILib warns that I can wind up, so keep it small.")
            else:
                why = (f"There P adds {p_end:+.2f} V to the feedforward's {ff_end:+.2f} V. A speed that "
                       "stays short means the feedforward is low: measure it (drive_ff) rather than "
                       "raising kP.")
            _note(out, "response", "bracket", "steady_state_error",
                  f"{step_name}: {abs(sse) * k_say:.3g}{say} left at the end. " + why,
                  t=t[b - 1], y0=r, y1=r - sse * sign)

        if loop == "drive":
            hold = [i for i in range(a + int((b - a) * 0.5), b)
                    if A.finite(ff[i]) and A.finite(applied[i]) and abs(applied[i]) > 0.2]
            if hold:
                share = A.mean([ff[i] / applied[i] for i in hold])
                if A.finite(share):
                    _note(out, "controller", "vspan", "feedforward",
                          f"{step_name}: holding speed, the feedforward supplies about {share * 100:.0f}% "
                          "of the voltage. Near 100% is the goal: feedforward does the work, feedback "
                          "only corrects what it got wrong.", x0=t[hold[0]], x1=t[hold[-1]])
    out.pop("_step", None)
    out.pop("_size", None)
    out["story"].sort(key=lambda s: s["t"])


def explain(result, gains=None, current_limits=None):
    """Every module of a steer_step or drive_step run, or None for other tests.

    ``current_limits`` is ``{"drive": amps, "steer": amps}`` from the project, if known.
    """
    test = result.get("test")
    loop = {"steer_step": "steer", "drive_step": "drive"}.get(test)
    if not loop:
        return None
    gains = gains or result.get("gains") or {}
    ch = result.get("channels") or {}
    suffix = "sp" if loop == "steer" else "v"
    mods = sorted({int(k[1:k.index(".")]) for k in ch if k.startswith("m") and k.endswith("." + suffix)
                   and k[1:k.index(".")].isdigit()})
    limit = (current_limits or {}).get(loop)
    out = [e for e in (explain_module(result, gains, m, loop, limit) for m in mods) if e]
    return {"test": test, "loop": loop, "modules": out}
