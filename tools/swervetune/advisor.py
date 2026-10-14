"""Reads a test result and says what to do next.

Every report has the same shape, so the GUI, the command line and an AI agent all consume it the
same way::

    {
      "test": "steer_step", "env": "FIELD", "practice": False,
      "summary": "one line a person can read",
      "score": 0-100,          # share of the targets met
      "cost": float,           # lower is better; what an agent should minimize
      "targets": [{"name", "value", "target", "met"}],
      "modules": {name: {...metrics...}},
      "findings": [ {level, title, why, action?} ],   # most important first
      "next": the first finding with an action, or None
    }

An ``action`` is one of:

* ``{"type": "gains", "values": {"Steer/kP": 0.015, ...}}`` - try these live; Save keeps them.
* ``{"type": "run", "test": "drive_ff", "env": "FIELD", "args": {...}}`` - run this test next.
* ``{"type": "config", "file": ..., "path": [...], "value": ...}`` - a JSON edit (needs redeploy).
* ``{"type": "troubleshoot", "symptom": "..."}`` - open that troubleshooting guide.

The rules come from control theory applied to these specific mechanisms, and the reasons are
written for a student who has done the basic training: what is happening physically, and why the
suggested change helps. Each recommendation moves one thing at a time and never more than doubles
or halves a gain, because two changes at once cannot be told apart in the next run.
"""

from __future__ import annotations

import math

from . import analysis as A
from . import battery
from . import explain
from . import revspecs
from . import ratios as R

# What "tight" means, per loop. Steering numbers are for a MAXSwerve-class module (NEO 550 at
# 46.42:1): about 1400 deg/s free speed at the module, so a 90 degree move cannot take much under
# 70 ms; the targets leave room for current limiting and carpet scrub.
STEER_TARGETS = {
    "large_rise_s": 0.12,      # 10-90% of a 45-90 degree step
    "overshoot_pct": 5.0,
    "settle_s": 0.30,          # into +/-max(2%, 1 degree)
    "small_sse_deg": 0.75,     # what friction leaves behind on a small correction
    "noise_deg": 0.25,         # jitter once settled
}
# With a measured feedforward, a steady speed error bigger than this means the feedforward
# doesn't fit (measured on blocks or other carpet, another motor), not that kP is low.
FF_MISFIT_FRAC = 0.08
DRIVE_TARGETS = {
    # Includes up to one 20 ms robot loop before the setpoint even reaches the controller.
    "dead_time_s": 0.05,
    "jitter_mps": 0.04,        # speed noise while holding a constant command
    "overshoot_pct": 10.0,
    "sse_frac": 0.03,          # steady-state speed error as a fraction of the setpoint
    "module_spread_pct": 5.0,
}

STEER_CURRENT_LIMIT_DEFAULT = 20.0
DRIVE_CURRENT_LIMIT_DEFAULT = 40.0


def finding(level, title, why, action=None, **extra):
    f = {"level": level, "title": title, "why": why}
    if action:
        f["action"] = action
    f.update(extra)
    return f


def gains_action(**values):
    return {"type": "gains", "values": {k.replace("__", "/"): round(v, 6) for k, v in values.items()}}


def _module_names(result, count):
    names = (result.get("robot") or {}).get("modules") or []
    return [names[i] if i < len(names) else f"m{i}" for i in range(count)]


def pod_doc(doc, pod):
    """One pod's view of a run: only its channels (the time and whole-robot channels kept), and the
    gains that pod ran with in place of the shared ones, so the report and its advice are that
    pod's. ``pod`` is a module name or index; an unknown one returns the run unchanged."""
    names = list((doc.get("robot") or {}).get("modules") or [])
    i = names.index(pod) if pod in names else (int(pod) if str(pod).isdigit() else -1)
    if i < 0:
        return doc
    out = dict(doc)
    pre = f"m{i}."
    out["channels"] = {k: v for k, v in (doc.get("channels") or {}).items()
                       if not (k.startswith("m") and "." in k and k[1:k.index(".")].isdigit()) or k.startswith(pre)}
    g = dict(doc.get("gains") or {})
    name = names[i] if i < len(names) else str(i)
    for loop in ("Steer", "Drive"):
        for k in ("kP", "kI", "kD", "IZone"):
            v = g.get(f"Pod/{name}/{loop}/{k}")
            if v is not None:
                g[f"{loop}/{k}"] = v
    out["gains"] = g
    out["pod"] = name
    return out


def _modules_in(channels, suffix):
    out = []
    for key in channels:
        if key.startswith("m") and key.endswith("." + suffix):
            try:
                out.append(int(key[1:key.index(".")]))
            except ValueError:
                pass
    return sorted(set(out))


def _clamp_ratio(new, old, lo=0.5, hi=2.0):
    """Never more than doubles or halves in one step. Zero can become anything sensible."""
    if old <= 0:
        return new
    return max(old * lo, min(old * hi, new))


def _ff_misfit(gains, kind, result, wheel_d_in, kP):
    """Whether a steady speed error means the feedforward in force is for another robot, motor or
    surface (measure it again) rather than something kP should fix.

    A measured kV more than 10% from what this motor and gearing need on a free wheel is the
    signature of a feedforward measured elsewhere. Close to it, the feedforward is right and the
    error is drag it can't model (carpet nap, a rubbing bumper): kP is the tool, and asking to
    re-measure would only return the same numbers forever.
    """
    kvs = [v for k, v in gains.items() if k.startswith("FF/") and k.endswith("/kV") and A.finite(v) and v > 0]
    gear = (result.get("meta") or {}).get("drive_gear_ratio") or 5.5
    nominal = _nominal_kv(kind, gear, wheel_d_in or 3.0)
    if kvs and A.finite(nominal):
        return abs(A.median(kvs) / nominal - 1) > 0.10
    return A.finite(kP) and kP >= 0.04


def _worse(cur, value):
    """The worse of a running worst and a new value, where "never" (NaN: the step never got there)
    is worst of all. ``max(0.0, nan)`` is 0.0 in Python, which once graded a step that never
    finished as "0 ms, met"."""
    if value is None:
        return cur
    return float("inf") if not A.finite(value) else max(cur, value)


def _grade(name, value, target, lower_is_better=True):
    met = A.finite(value) and (value <= target if lower_is_better else value >= target)
    return {"name": name, "value": value, "target": target, "met": bool(met), "lower_is_better": lower_is_better}


def _finish(report):
    targets = report.get("targets", [])
    report["score"] = round(100.0 * sum(t["met"] for t in targets) / len(targets)) if targets else None
    report["next"] = next((f for f in report["findings"] if f.get("action")), None)
    return report


def _practice_note(result, report):
    if result.get("practice"):
        note = finding(
            "info", "Practice pod, not the robot",
            "These numbers come from a physics model of a MAXSwerve module. Use it to learn what "
            "each gain does. Keep only gains measured on the robot.")
        note["kind"] = "practice"  # the GUI already says this in a banner, so it can skip this one
        report["findings"].insert(0, note)


# ============================================================================ steering


def steer_report(result, gains=None, current_limit=STEER_CURRENT_LIMIT_DEFAULT):
    ch = result["channels"]
    env = result.get("env", "")
    gains = gains or result.get("gains") or {}
    t = ch.get("t", [])
    vbus = A.mean(ch.get("vbus", [12.0])) or 12.0
    # The most a motor can be given: the battery, but never more than the 12 V the SPARKs are
    # compensated to. On a fresh 12.8 V battery a motor pinned at 12 V is flat out.
    u_cap = min(vbus, explain.compensation_volts(result.get("meta") or {}))
    mods = _modules_in(ch, "sp")
    names = _module_names(result, max(mods) + 1 if mods else 0)
    report = {"test": "steer_step", "env": env, "practice": bool(result.get("practice")),
              "modules": {}, "findings": [], "targets": []}

    worst = {"rise": 0.0, "os": 0.0, "settle": 0.0, "sse": 0.0, "osc": 0, "noise": 0.0,
             "sat": 0.0, "unsettled": 0, "asym": 0.0, "steps": 0, "disagree": 0.0}
    for i in mods:
        sp, y = ch[f"m{i}.sp"], ch[f"m{i}.steer"]
        volts = ch.get(f"m{i}.volts")
        amps = ch.get(f"m{i}.amps")
        steps = A.analyze_steps(t, sp, y, volts, tol_abs=1.0, u_max=u_cap, amps=amps,
                                amp_limit=current_limit)
        summ = A.summarize_steps(steps)
        name = names[i]
        moved = max((abs(s["peak_progress"]) for s in steps), default=0.0)
        runaway = any(s["peak_progress"] < -0.5 for s in steps)
        motor = ch.get(f"m{i}.motor")
        disagree = 0.0
        if motor and env != "SIM":  # simulated encoders are not two physical sensors
            # Only where the module has settled: mid-move the two sensors legitimately differ
            # (different update rates, backlash taking up), which says nothing about drift.
            settled = []
            for a0, b0, _ in A.segments(t, sp):
                tail = range(a0 + int(0.7 * (b0 - a0)), b0)
                settled += [abs(A.wrap180(y[k] - motor[k])) for k in tail
                            if A.finite(y[k]) and A.finite(motor[k])]
            disagree = A.median(settled) if settled else 0.0
        report["modules"][name] = {
            "steps": steps, "summary": summ, "asymmetry": A.direction_asymmetry(summ),
            "moved": moved, "runaway": runaway, "motor_vs_absolute_deg": disagree,
        }
        if runaway:
            report["findings"].append(finding(
                "error", f"{name}: steering runs away from its setpoint",
                "The module turned the opposite way to the command and kept going. That is positive "
                "feedback: the steering motor and the sensor it is controlled by disagree about which "
                "way is positive. No gain fixes it.",
                {"type": "troubleshoot", "symptom": "pod_wrong_direction"}))
        if moved < 0.2 and not runaway:
            report["findings"].append(finding(
                "error", f"{name}: steering barely moved",
                "The setpoint changed but the angle did not follow. Usually a CAN ID, an unplugged "
                "encoder, a breaker, or kP so small the motor cannot overcome friction.",
                {"type": "troubleshoot", "symptom": "pod_not_moving"}))
        L, S = summ.get("large", {}), summ.get("small", {})
        worst["rise"] = _worse(worst["rise"], L.get("rise_time"))
        worst["os"] = max(worst["os"], summ["all"].get("overshoot_pct", 0) or 0)
        worst["settle"] = _worse(worst["settle"], L.get("settling_time"))
        worst["sse"] = _worse(worst["sse"], S.get("steady_state_error"))
        worst["osc"] = max(worst["osc"], summ["all"].get("oscillations", 0) or 0)
        worst["noise"] = max(worst["noise"], summ["all"].get("steady_state_noise", 0) or 0)
        worst["sat"] = max(worst["sat"], L.get("saturation", 0) or 0)
        worst["unsettled"] += summ["all"].get("unsettled", 0) or 0
        worst["steps"] += summ["all"].get("count", 0) or 0
        worst["asym"] = max(worst["asym"], report["modules"][name]["asymmetry"])
        worst["disagree"] = max(worst["disagree"], disagree)

    def nz(x):
        return x if A.finite(x) else float("inf")

    report["targets"] = [
        _grade("large-step rise time, 45-90° (s)", nz(worst["rise"]), STEER_TARGETS["large_rise_s"]),
        _grade("overshoot (%)", worst["os"], STEER_TARGETS["overshoot_pct"]),
        _grade("settling time (s)", nz(worst["settle"]), STEER_TARGETS["settle_s"]),
        _grade("small-step error (deg)", nz(worst["sse"]), STEER_TARGETS["small_sse_deg"]),
        _grade("jitter when settled (deg)", worst["noise"], STEER_TARGETS["noise_deg"]),
    ]
    unsettled_frac = worst["unsettled"] / max(1, worst["steps"])
    report["cost"] = round(
        min(nz(worst["rise"]), 1.0) / STEER_TARGETS["large_rise_s"]
        + worst["os"] / 10.0
        + min(nz(worst["sse"]), 10.0) / STEER_TARGETS["small_sse_deg"]
        + min(nz(worst["settle"]), 1.0) / STEER_TARGETS["settle_s"]
        + 2.0 * max(0, worst["osc"] - 1)
        + 3.0 * unsettled_frac, 3)
    report["worst"] = worst

    if worst["steps"] == 0:
        if not report["findings"]:
            return no_data_report(dict(result, message="No step could be analyzed: the setpoint "
                                       "never changed or the angle never moved."))
        report["targets"], report["cost"] = [], None  # nothing measured, so nothing is met
    if any(f["level"] == "error" for f in report["findings"]):
        report["summary"] = "Steering has a fault to fix before any tuning."
        _practice_note(result, report)
        return _finish(report)

    kP = gains.get("Steer/kP", float("nan"))
    kI = gains.get("Steer/kI", 0.0) or 0.0
    kD = gains.get("Steer/kD", 0.0) or 0.0
    ramp = gains.get("Steer/RampS", 0.0) or 0.0
    have_gains = A.finite(kP)
    F = report["findings"]

    if env == "SIM":
        F.append(finding(
            "info", "Simulation: gains have no effect here",
            "YAGSL drives simulated modules with its own controller, so this run proves the test "
            "and the tools work. Tune on blocks first, then on the floor."))
    if env == "BLOCKS":
        F.append(finding(
            "info", "On blocks: confirm on the floor before keeping these",
            "Carpet scrub loads the steering several times harder than air. Gains that look perfect "
            "on blocks usually leave the wheel short of its target on the floor. Finish this step "
            "with the robot on the floor (it does not drive, the wheels only turn in place)."))

    floor = env in ("FIELD", "") or result.get("practice_surface") == "floor"
    sse_limit = STEER_TARGETS["small_sse_deg"] if floor else 0.5

    if have_gains and ramp > 0.02 and (worst["os"] > 5 or worst["osc"] >= 1
                                       or nz(worst["rise"]) > STEER_TARGETS["large_rise_s"]):
        F.append(finding(
            "warn", f"Steering ramp rate is {ramp:.2f} s: take it to 0",
            "YAGSL applies the ramp rate to the closed loop too, so every steering correction is "
            "slew-limited. That is pure added lag in a position loop: it slows the response and, "
            "with any real kP, makes it overshoot. The current limit already protects the NEO 550. "
            "Change only this, then run the same test again.",
            gains_action(Steer__RampS=0.0)))
    elif worst["osc"] >= 2 or worst["os"] > 15:
        if have_gains and kD < 3 * kP:
            new_kd = min(2.0, max(kP * 5, kD * 2 if kD > 0 else kP * 5))
            F.append(finding(
                "warn", f"Rings or overshoots {worst['os']:.0f}%: add damping",
                "The module swings past its target and back. kD pushes back in proportion to how "
                "fast the error is closing, which brakes the module as it arrives. On a SPARK, kD is "
                f"per 1 ms step, so kD = kP x 5 means 'look 5 ms ahead'. Try kD {new_kd:.4g}.",
                gains_action(Steer__kD=new_kd)))
        elif have_gains:
            F.append(finding(
                "warn", "Still ringing with damping: lower kP",
                "kD is already several times kP and it still rings, so the loop is simply too "
                "aggressive for the delay in it. Back kP off by 30%.",
                gains_action(Steer__kP=_clamp_ratio(kP * 0.7, kP))))
    elif worst["os"] > STEER_TARGETS["overshoot_pct"] and have_gains:
        new_kd = max(kD, kP * 3) if kD < kP * 3 else kD * 1.5
        F.append(finding(
            "warn", f"Overshoots {worst['os']:.0f}%",
            "A little past and back. More kD will catch it at the end of the move without slowing "
            "the start much.", gains_action(Steer__kD=min(2.0, new_kd))))
    elif nz(worst["sse"]) > sse_limit or unsettled_frac > 0.25:
        if have_gains:
            if worst["os"] < 3:
                new_kp = _clamp_ratio(kP * 1.5, kP)
                lateral = math.tan(math.radians(min(nz(worst["sse"]), 20))) * 100
                F.append(finding(
                    "warn", f"Small corrections stop {worst['sse']:.1f}° short",
                    "Friction (carpet scrub, mostly) holds the wheel until the error is big enough "
                    "for kP to push through it. Every degree of steering error is about "
                    f"{math.tan(math.radians(1)) * 100:.1f} cm of sideways drift per meter driven, "
                    f"so this one is about {lateral:.1f} cm per meter. Raise kP 50%.",
                    gains_action(Steer__kP=new_kp)))
            elif kI == 0:
                F.append(finding(
                    "warn", "Friction leaves an error and kP cannot go higher without overshoot",
                    "Add a small integral term, limited to the last few degrees by IZone so it cannot "
                    "wind up during big moves. kI = kP / 100 per ms with a 3 degree IZone is a safe "
                    "start.", gains_action(Steer__kI=min(0.01, kP / 100), Steer__IZone=3.0)))
    elif nz(worst["rise"]) > STEER_TARGETS["large_rise_s"]:
        if worst["sat"] >= 0.5:
            F.append(finding(
                "info", f"Big moves take {worst['rise'] * 1000:.0f} ms, but the motor is already "
                "giving everything",
                f"The steering motor sat at its {current_limit:.0f} A limit or full voltage for "
                f"{worst['sat'] * 100:.0f}% of the move, so a higher kP cannot make it faster. "
                "The team keeps a NEO 550 at 20 A because it has the least heat capacity of any "
                "motor on the robot, so this is as fast as the hardware allows. What still helps: "
                "less steering friction (worn tread scrubbing, a tight bearing), and later a motion "
                "profile that plans each move instead of slamming into it."))
        elif have_gains:
            F.append(finding(
                "warn", f"Big moves are slow ({worst['rise'] * 1000:.0f} ms) with no overshoot",
                "There is room to be more aggressive: no overshoot and the motor is not working "
                "flat out. Raise kP 40%.", gains_action(Steer__kP=_clamp_ratio(kP * 1.4, kP))))

    F.extend(steer_ratio_findings(result))
    if worst["asym"] > 0.3:
        F.append(finding(
            "warn", f"Turns {worst['asym'] * 100:.0f}% faster one way than the other",
            "Gains are symmetric, so a direction-dependent response is mechanical: a rubbing belt or "
            "gear, a tight bearing, or a wire dragging. Fix the mechanism, not the gains.",
            {"type": "troubleshoot", "symptom": "pod_slow"}))
    if worst["noise"] > STEER_TARGETS["noise_deg"]:
        F.append(finding(
            "warn", f"Jitters {worst['noise']:.2f}° once settled",
            "A settled module should sit still. Jitter comes from too much kD amplifying encoder "
            "noise, from backlash with high kP, or from a loose encoder magnet.",
            gains_action(Steer__kD=kD * 0.5) if have_gains and kD > 0 else
            {"type": "troubleshoot", "symptom": "pod_jitter"}))
    if worst["disagree"] > 1.5:
        F.append(finding(
            "info", f"Motor encoder and absolute encoder differ by {worst['disagree']:.1f}°",
            "Steering is controlled by one sensor and measured by the other. A gap this size is "
            "gear backlash or the motor encoder drifting since boot; it shows up as a module that "
            "is 'aligned' by one sensor and not the other. Turning on encoder auto-sync, or steering "
            "on the absolute encoder, removes it.", {"type": "troubleshoot", "symptom": "pod_drifts"}))

    met = sum(t["met"] for t in report["targets"])
    if not any(f["level"] in ("warn", "error") for f in F):
        all_met = met == len(report["targets"])
        if not all_met:
            report["limited"] = True  # nothing left to tune: the Guide counts it done
        F.append(finding(
            "ok", "Steering meets every target" if all_met else "Steering is as good as its limits allow",
            "Save these gains so they survive a restart. Then run it once more on the floor if this "
            "was on blocks.", {"type": "save", "what": "steer_pid"}))
    rise = f"{worst['rise'] * 1000:.0f} ms" if A.finite(worst["rise"]) else "never finished"
    sse = f"{worst['sse']:.2f}°" if A.finite(worst["sse"]) else "never settled"
    report["summary"] = (f"Steering: {met}/{len(report['targets'])} targets met; large-step rise "
                         f"{rise}, overshoot {worst['os']:.0f}%, small-step error {sse}.")
    _practice_note(result, report)
    return _finish(report)


# ============================================================================ drive velocity


# The config check's line for an aggressive drive loop (yagslcfg: drive_p_hot).
HOT_DRIVE_P = 2.0
HOT_DRIVE_D = 0.05


def _nominal_kv(kind, gear, wheel_d_in):
    """12 V over the module's free speed: the kV a free wheel on this motor and gearing needs."""
    m = revspecs.MOTORS.get(kind)
    if not (m and gear and wheel_d_in):
        return float("nan")
    return 12.0 / (m["free_rpm"] / 60.0 / gear * math.pi * wheel_d_in * 0.0254)


def drive_report(result, gains=None, current_limit=DRIVE_CURRENT_LIMIT_DEFAULT, drive_kind=None,
                 wheel_d_in=None):
    ch = result["channels"]
    # A practice run says which motor the pod modeled; a robot run uses the robot's drive motor.
    kind = ((result.get("meta") or {}).get("pod_motor") or "neo") if result.get("practice") else (drive_kind or "neo")
    sensor_period, _, sensor_counts, sensor_words = revspecs.drive_speed_sensor(kind)
    env = result.get("env", "")
    gains = gains or result.get("gains") or {}
    t, sp = ch.get("t", []), ch.get("sp", [])
    vbus = A.mean(ch.get("vbus", [12.0])) or 12.0
    u_cap = min(vbus, explain.compensation_volts(result.get("meta") or {}))
    mods = _modules_in(ch, "v")
    names = _module_names(result, max(mods) + 1 if mods else 0)
    report = {"test": "drive_step", "env": env, "practice": bool(result.get("practice")),
              "modules": {}, "findings": [], "targets": []}
    F = report["findings"]
    dead, os_, osc, sse_frac, steady = [], 0.0, 0, 0.0, {}
    low_err, high_err, jitter = [], [], 0.0
    for i in mods:
        v = ch[f"m{i}.v"]
        name = names[i]
        steps = A.analyze_steps(t, sp, v, ch.get(f"m{i}.volts"), tol_abs=0.05, u_max=u_cap,
                                amps=ch.get(f"m{i}.amps"), amp_limit=current_limit, window=5)
        summ = A.summarize_steps(steps, small=0.6)
        d = A.response_delay(t, sp, v)
        backwards = sum(1 for a, b in zip(sp, v) if abs(a) > 0.2 and a * b < 0) > 0.3 * sum(
            1 for a in sp if abs(a) > 0.2)
        speeds = {}
        for a, b, r in A.segments(t, sp)[1:]:
            if abs(r) < 0.1:
                continue
            tail = v[a + int(0.6 * (b - a)):b]
            if tail:
                jitter = max(jitter, A.stdev(tail))
                speeds[round(r, 3)] = A.mean(tail)
                err = abs(A.mean(tail) - r) / abs(r)
                (low_err if abs(r) < 0.6 else high_err).append(err)
        report["modules"][name] = {"steps": steps, "summary": summ, "dead_time": d,
                                   "backwards": backwards, "steady_speeds": speeds}
        if backwards:
            F.append(finding(
                "error", f"{name}: wheel turns the opposite way to its command",
                "The drive motor and its own encoder agree, but the wheel goes the wrong way for "
                "the angle the module is pointing. Either this drive motor's inversion is wrong, or "
                "the module's absolute offset is 180° out and the other modules are right. Check "
                "the offset first: a mixed set of drive inversions is how that mistake hides.",
                {"type": "troubleshoot", "symptom": "wheel_backwards"}))
        if A.finite(d):
            dead.append(d)
        os_ = max(os_, summ["all"].get("overshoot_pct", 0) or 0)
        osc = max(osc, summ["all"].get("oscillations", 0) or 0)
        for r, mv in speeds.items():
            steady.setdefault(r, []).append(mv)
    errs = low_err + high_err
    sse_frac = max(errs) if errs else float("nan")
    spread = max((A.spread_percent(vs) for vs in steady.values() if len(vs) > 1), default=0.0)
    dead_t = A.median(dead)

    report["targets"] = [
        _grade("response delay (s)", dead_t, DRIVE_TARGETS["dead_time_s"]),
        _grade("overshoot (%)", os_, DRIVE_TARGETS["overshoot_pct"]),
        _grade("steady speed error (fraction)", sse_frac, DRIVE_TARGETS["sse_frac"]),
        _grade("module-to-module spread (%)", spread, DRIVE_TARGETS["module_spread_pct"]),
        _grade("speed jitter at constant command (m/s)", jitter, DRIVE_TARGETS["jitter_mps"]),
    ]
    report["cost"] = round(
        (dead_t if A.finite(dead_t) else 0.2) / DRIVE_TARGETS["dead_time_s"]
        + os_ / 10.0 + (sse_frac if A.finite(sse_frac) else 1.0) / DRIVE_TARGETS["sse_frac"]
        + spread / DRIVE_TARGETS["module_spread_pct"] + 2.0 * max(0, osc - 1)
        + jitter / DRIVE_TARGETS["jitter_mps"], 3)
    report["worst"] = {"dead_time": dead_t, "overshoot": os_, "oscillations": osc,
                       "sse_frac": sse_frac, "spread": spread, "jitter": jitter,
                       "low_speed_error": max(low_err) if low_err else float("nan"),
                       "high_speed_error": max(high_err) if high_err else float("nan")}
    if not dead and not steady:
        if not F:
            return no_data_report(dict(result, message="No speed step could be analyzed: the "
                                       "wheels never moved."))
        report["targets"], report["cost"] = [], None
    if any(f["level"] == "error" for f in F):
        report["summary"] = "A wheel is driving backwards; fix that before tuning."
        _practice_note(result, report)
        return _finish(report)

    kP = gains.get("Drive/kP", float("nan"))
    kD = gains.get("Drive/kD", 0.0) or 0.0
    ramp = gains.get("Drive/RampS", 0.0) or 0.0
    period = gains.get("Drive/VelPeriodMs", 0) or 0
    have = A.finite(kP)
    ff_measured = any((gains.get(k, 0) or 0) > 0 for k in gains if k.endswith("/kS"))
    ka_measured = any((gains.get(k, 0) or 0) > 0 for k in gains if k.endswith("/kA"))

    if env == "BLOCKS":
        F.append(finding(
            "info", "On blocks: direction, friction and delay only",
            "With the wheels in the air the motor turns about a fiftieth of the inertia it sees "
            "carrying the robot, so every gain looks far stronger here than on carpet. Use this "
            "run to confirm direction and delay; tune the velocity loop on the floor."))
    if env == "SIM":
        F.append(finding("info", "Simulation: gains have no effect here",
                         "This proves the test runs. Tune on the floor."))

    if A.finite(dead_t) and dead_t > DRIVE_TARGETS["dead_time_s"]:
        # Attribute the delay before prescribing for it: ramp first, then the sensor filter.
        if ramp > 0.05 and have:
            F.append(finding(
                "warn", f"{dead_t * 1000:.0f} ms before the wheel responds: the ramp rate is part of it",
                f"A {ramp:.2f} s ramp lets the output climb only {12 / ramp:.0f} V per second, so the "
                "first volts of every correction arrive late. The current limit is what protects the "
                "wheels and gearbox; 0.05 s is plenty of ramp.", gains_action(Drive__RampS=0.05)))
        elif (period or sensor_period) > 16:
            F.append(finding(
                "warn", f"Speed is measured {dead_t * 1000:.0f} ms late",
                f"Before the controller can correct an error it has to see it. The speed comes from "
                f"{sensor_words}, and YAGSL doesn't shorten that window for a NEO (it sets a different, "
                "quadrature, filter). Delay caps how hard the velocity loop can push before it "
                "oscillates. Try a 16 ms x 2 window and run this again: less delay, a little more noise.",
                gains_action(Drive__VelPeriodMs=16, Drive__VelDepth=2)))
        else:
            F.append(finding(
                "info", f"{dead_t * 1000:.0f} ms of delay remains",
                "With the ramp and the sensor window already short, what is left is the 20 ms robot "
                "loop and CAN. That is normal; tune the gains around it."))
    if jitter > DRIVE_TARGETS["jitter_mps"] and have and (kP > 0.15 or kD > 0):
        F.append(finding(
            "warn", f"Speed buzzes ±{jitter:.2f} m/s while holding a constant command",
            ("A NEO's built-in sensor counts 42 steps a turn, so the measured speed moves in coarse "
             "jumps. A large kP turns every jump into a voltage kick, and kD on a velocity loop "
             "multiplies them again - you hear it as a buzz and see it as heat. Set kD to 0 and "
             "halve kP; a measured feedforward does the real work.") if sensor_counts < 100 else
            (f"The Vortex's encoder counts {sensor_counts} steps a turn, so this isn't a coarse sensor: a "
             "large kP turns every bump in the carpet and every flicker of the short speed window into "
             "a voltage kick, and kD on a velocity loop multiplies them again - you hear it as a buzz and "
             "see it as heat. Set kD to 0 and halve kP; a measured feedforward does the real work."),
            gains_action(Drive__kP=_clamp_ratio(kP * 0.5, kP), Drive__kD=0.0)))
    elif (osc >= 2 or os_ > 20) and not (ka_measured and A.finite(kP) and kP <= 0.06):
        if have:
            F.append(finding(
                "warn", f"Speed overshoots {os_:.0f}% and rings",
                "The velocity loop is too aggressive for its measurement delay. kD on a velocity "
                "loop mostly amplifies encoder noise; set it to 0 and lower kP 40%.",
                gains_action(Drive__kP=_clamp_ratio(kP * 0.6, kP), Drive__kD=0.0)))
    elif A.finite(sse_frac) and sse_frac > DRIVE_TARGETS["sse_frac"]:
        lo = report["worst"]["low_speed_error"]
        hi = report["worst"]["high_speed_error"]
        if not ff_measured:
            F.append(finding(
                "warn", f"Holds speed {sse_frac * 100:.0f}% off target: measure the feedforward first",
                "YAGSL's default feedforward is kV from the datasheet with no kS and no kA, so the "
                "PID is doing work the feedforward should do. Measure kS, kV and kA per module "
                "(drive_ff, on the floor), then come back here."
                + (" The error is worst at low speed, which is the missing kS." if
                   A.finite(lo) and A.finite(hi) and lo > 1.5 * hi else ""),
                {"type": "run", "test": "drive_ff", "env": "FIELD", "args": {}}))
        elif sse_frac > FF_MISFIT_FRAC and _ff_misfit(gains, kind, result, wheel_d_in, kP):
            F.append(finding(
                "warn", f"Holds speed {sse_frac * 100:.0f}% off target: the feedforward doesn't fit this robot",
                "A measured feedforward on its own gets within a few percent; kP only cleans up the rest. "
                "Off by this much, it was measured somewhere else (on blocks, on other carpet), with "
                "another motor, or the robot has changed since. Raising kP to cover it makes the loop "
                "ring before it fixes the error. Measure drive_ff again, on this floor.",
                {"type": "run", "test": "drive_ff", "env": "FIELD", "args": {}}))
        elif have:
            new_kp = 0.04 if kP < 0.01 else _clamp_ratio(kP * 1.5, kP)
            F.append(finding(
                "warn", f"Holds speed {sse_frac * 100:.0f}% off target",
                "With a measured feedforward this is what kP is for. REV's own MAXSwerve example "
                f"uses about 0.04 duty per m/s. Try kP {new_kp:.3g}.",
                gains_action(Drive__kP=new_kp)))
    elif os_ > DRIVE_TARGETS["overshoot_pct"] and have:
        if ka_measured and kP <= 0.06:
            F.append(finding(
                "info", f"Overshoots {os_:.0f}% on an instant step: that is the feedforward kick",
                "With kA in the feedforward, an instant step asks for kA x (change in speed) / 20 ms "
                "for one loop - a big voltage kick - so a step test overshoots even with a gentle "
                "kP. PathPlanner paths are smooth and never ask for that. If drivers feel a lurch "
                "when slamming the stick, add a slew-rate limiter to the stick inputs rather than "
                "detuning the loop."))
        else:
            F.append(finding(
                "warn", f"Overshoots {os_:.0f}% on a step",
                "Some overshoot on a hard step is expected, but this much shows up as a lurch. "
                "Lower kP 25%.", gains_action(Drive__kP=_clamp_ratio(kP * 0.75, kP))))
    F.extend(drive_ratio_findings(result))
    if spread > DRIVE_TARGETS["module_spread_pct"]:
        F.append(finding(
            "warn", f"Modules disagree by {spread:.0f}% at the same command",
            "One corner runs slower than the others for the same request, which pulls the robot "
            "off a straight line. A per-module feedforward fixes small differences; a big one is "
            "mechanical (a dragging brake, worn tread, a different gear).",
            {"type": "run", "test": "drive_ff", "env": "FIELD", "args": {}}))
    if ramp > 0.1 and have:
        F.append(finding(
            "info", f"Drive ramp rate {ramp:.2f} s slows every correction",
            "The ramp limits how fast the motor's output can change, including the velocity loop's "
            "own corrections, so it reads as lag to PathPlanner. The current limit is what protects "
            "the wheels from slipping. 0.05 s keeps the gearbox happy without the lag.",
            gains_action(Drive__RampS=0.05)))
    # The pod has no sensor noise, module flex or gear lash, so a gain far past the feedforward's
    # own slope can pass every target here and still buzz on a robot. The same line as the config
    # check (yagslcfg drive_p_hot): kP over twice the feedforward's slope, or kD over 0.05.
    kvs = [v for k, v in gains.items() if k.startswith("FF/") and k.endswith("/kV") and A.finite(v) and v > 0]
    kv = A.median(kvs) if kvs else _nominal_kv(kind, (result.get("meta") or {}).get("drive_gear_ratio") or 5.5,
                                                wheel_d_in or 3.0)
    slope = kv / 12.0 if A.finite(kv) and kv > 0 else float("nan")
    if have and A.finite(slope) and (kP > HOT_DRIVE_P * slope or kD > HOT_DRIVE_D):
        halve = {}
        if kP > HOT_DRIVE_P * slope:
            halve["Drive/kP"] = kP / 2
        if kD > HOT_DRIVE_D:
            halve["Drive/kD"] = kD / 2
        F.append(finding(
            "warn", f"Drive kP {kP:g}{f', kD {kD:g}' if kD else ''} is too aggressive for a robot",
            f"kP is {kP / slope:.1f}× the feedforward's own slope ({slope:.3f} output per m/s). On a robot, "
            "every bump in the carpet, flex in the module and lash in the gears shows up in the speed "
            "reading, and a gain this large turns each one into a voltage kick: the drive buzzes, runs hot "
            "and overshoots. The practice pod has none of that, so it can pass here and still fail on the "
            "robot. Halve it, run, and repeat until it is under "
            f"{HOT_DRIVE_P:g}× ({HOT_DRIVE_P * slope:.2f}){'; kD stays under ' + format(HOT_DRIVE_D, 'g') if kD > HOT_DRIVE_D else ''}.",
            {"type": "gains", "values": halve}))
    met = sum(t["met"] for t in report["targets"])
    if not any(f["level"] in ("warn", "error") for f in F):
        F.append(finding("ok", "Drive velocity meets every target",
                         "Save these gains.", {"type": "save", "what": "drive_pid"}))
    if have and kP > 0.3 and not ff_measured:
        F.append(finding(
            "info", f"kP {kP:.2f} is doing the feedforward's job",
            "This meets the targets, but only because a large kP is making up for a feedforward "
            "that was never measured. Large kP amplifies sensor noise and battery sag. Measuring the "
            "feedforward lets kP drop to a gentle correction (around 0.04), which holds up better "
            "over a match."))
    report["summary"] = (f"Drive: {met}/{len(report['targets'])} targets met; delay "
                         f"{dead_t * 1000 if A.finite(dead_t) else float('nan'):.0f} ms, overshoot "
                         f"{os_:.0f}%, speed error {sse_frac * 100 if A.finite(sse_frac) else float('nan'):.1f}%.")
    _practice_note(result, report)
    return _finish(report)


# ============================================================================ feedforward


def motor_trend_findings(fits, history):
    """Compares this run's per-module kV and kS with earlier runs of the same robot.

    Each module is judged relative to the others in the same run, so a cold morning, a fresh
    battery or a firmware change that moves every module together cannot raise a false alarm; one
    motor drifting away from its siblings can. A motor's magnets weaken when it is cooked: it then
    spins faster per volt, so its kV (volts per m/s) falls. Growing drag - a dry bearing, debris,
    a pinion working loose - shows as kS climbing instead.
    """
    F = []
    now = {n: f for n, f in fits.items() if f.get("ok")}
    if len(now) < 3:
        return F

    def shares(mods, key):
        vals = {n: f[key] for n, f in mods.items() if f.get("ok") and A.finite(f.get(key))}
        med = A.median(list(vals.values()))
        return {n: v / med for n, v in vals.items()} if A.finite(med) and med > 0 else {}

    earlier_kv = [shares(h["modules"], "kV") for h in history]
    earlier_ks = [shares(h["modules"], "kS") for h in history]
    since = next((h.get("saved") for h in history), None)
    kv_now, ks_now = shares(now, "kV"), shares(now, "kS")
    ks_med_now = A.median([f["kS"] for f in now.values()])
    for n in now:
        past = [e[n] for e in earlier_kv if n in e]
        if len(past) >= 2 and n in kv_now:
            change = kv_now[n] / A.median(past) - 1
            if change < -0.05:
                F.append(finding(
                    "warn", f"{n}: kV down {-change * 100:.0f}% against the other modules since "
                            f"{_day(since)}",
                    "That motor now spins faster per volt than it used to, compared with its "
                    "siblings: the signature of magnets weakened by overheating (or a different "
                    "motor fitted since). A weakened motor makes less torque per amp and runs "
                    "hotter for the same work. Check the Motors panel's heat history for it, and "
                    "plan to replace it before it fails in a match.",
                    {"type": "troubleshoot", "symptom": "motor_dead"}))
        past_s = [e[n] for e in earlier_ks if n in e]
        if len(past_s) >= 2 and n in ks_now and A.finite(ks_med_now):
            base = A.median(past_s)
            grew = ks_now[n] / base if base > 0 else float("inf")
            if grew > 1.5 and (ks_now[n] - base) * ks_med_now > 0.05:
                F.append(finding(
                    "warn", f"{n}: needs {(grew - 1) * 100:.0f}% more voltage to start turning than "
                            f"it used to, against the other modules",
                    "Friction in that module is growing: a dry or failing bearing, debris in the "
                    "gears, a rubbing wheel or a pinion working loose. Spin it by hand with the "
                    "others for comparison.",
                    {"type": "troubleshoot", "symptom": "motor_hot"}))
    return F


def _day(stamp):
    s = str(stamp or "")
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 and s[:8].isdigit() else "earlier runs"


def feedforward_report(result, gains=None, history=None, ctx=None):
    ch = result["channels"]
    env = result.get("env", "")
    meta = result.get("meta", {})
    t = ch.get("t", [])
    phase = ch.get("phase", [])
    mods = _modules_in(ch, "volts")
    names = _module_names(result, max(mods) + 1 if mods else 0)
    blocks = env == "BLOCKS" or meta.get("env_blocks") == 1
    report = {"test": "drive_ff", "env": env, "practice": bool(result.get("practice")),
              "modules": {}, "findings": [], "targets": []}
    F = report["findings"]
    fits = {}
    for i in mods:
        V, v = ch[f"m{i}.volts"], ch[f"m{i}.v"]
        if blocks:
            q = [k for k, p in enumerate(phase) if p in (1, 2)] if phase else range(len(t))
            fit = A.fit_static([V[k] for k in q], [v[k] for k in q])
        else:
            fit = A.fit_feedforward(t, V, v)
        fits[names[i]] = fit
        report["modules"][names[i]] = fit
        if not fit.get("ok"):
            F.append(finding("error", f"{names[i]}: no usable fit",
                             fit.get("reason", "the fit failed"),
                             {"type": "troubleshoot", "symptom": "wheel_backwards"}
                             if "sign" in fit.get("reason", "") else None))
    good = {n: f for n, f in fits.items() if f.get("ok")}
    kvs = [f["kV"] for f in good.values()]
    kss = [f["kS"] for f in good.values()]
    kv_spread = A.spread_percent(kvs)
    r2_min = min((f.get("r2", 0) for f in good.values()), default=0)
    report["targets"] = [
        _grade("modules fitted", len(good), len(mods), lower_is_better=False),
        _grade("worst R²", r2_min, 0.95, lower_is_better=False),
        _grade("kV spread (%)", kv_spread, 8.0),
    ]
    report["cost"] = round((len(mods) - len(good)) * 5 + max(0, 0.98 - r2_min) * 50 + kv_spread / 8, 3)

    if blocks:
        F.append(finding(
            "info", "On blocks: friction per module, not a feedforward to keep",
            "In the air there is no robot to accelerate, so kA means nothing and kV is the free "
            "wheel's. What this run is good for is comparing kS between modules: a corner that "
            "needs noticeably more voltage to start turning is binding."))
        med = A.median(kss)
        for n, f in good.items():
            if A.finite(med) and med > 0 and f["kS"] > 1.6 * med and f["kS"] - med > 0.08:
                F.append(finding(
                    "warn", f"{n} needs {f['kS']:.2f} V to start turning, the others {med:.2f} V",
                    "That module is binding: a rubbing wheel, a tight bearing, debris in the "
                    "gears or a misaligned pinion. Spin it by hand and compare with the others.",
                    {"type": "troubleshoot", "symptom": "robot_slow"}))
    else:
        phase = ch.get("phase") or []
        powered = [p in (1, 2, 3, 4) for p in phase] if phase else None
        F.extend(drive_ratio_findings(result, mask=powered))
        for n, f in good.items():
            if f.get("r2", 1) < 0.95:
                F.append(finding("warn", f"{n}: weak fit (R² {f['r2']:.3f})",
                                 "R² says how well the straight line through the run's points fits them: 1.00 "
                                 "is perfect, under 0.95 something else pushed on the wheel. Look for wheel "
                                 "slip or a bump during the run, then repeat it.",
                                 {"type": "run", "test": "drive_ff", "env": "FIELD", "args": {}}))
            if f.get("kA", 0) < 0:
                F.append(finding("error", f"{n}: negative kA is not physical",
                                 "Something else pushed on the robot during the run - a collision, "
                                 "a slipping wheel. Repeat it on clear carpet."))
        if kv_spread > 8 and len(kvs) > 1:
            odd = max(good, key=lambda n: abs(good[n]["kV"] / A.median(kvs) - 1))
            # Up to 15% the per-module feedforward below still applies, so this is a note to follow
            # up, not the next step: as the next step it sent people to blocks, where no gains come out,
            # and the floor feedforward never came up.
            mild = kv_spread <= 15
            F.append(finding(
                "info" if mild else "warn", f"kV differs {kv_spread:.0f}% between modules; {odd} is the odd one out",
                "Up to about 8% is normal motor-to-motor variation and a per-module feedforward "
                "absorbs it. On carpet the chassis drives every wheel at the robot's speed, so a worn "
                "or smaller wheel, a slipping wheel and a different pinion all show up here the same "
                "way a weak motor would. Check that corner's wheel size first (Calibrate tab, Wheel "
                "sizes); to judge the motor itself, run the feedforward on blocks, where each wheel "
                "spins free.", None if mild else {"type": "run", "test": "drive_ff", "env": "BLOCKS", "args": {}}))
        top = (ctx or {}).get("max_speed")
        reached = max((abs(x) for i in mods for x in ch.get(f"m{i}.v", []) if A.finite(x)), default=0.0)
        if not blocks and top and reached < 0.4 * top:
            F.append(finding(
                "info", f"kV was measured over 0 to {reached:.1f} m/s; full speed is about {top:.1f}",
                "The ramp stops at the speed cap, so kV is a straight line stretched far past what was "
                "measured. It is usually close, but for a kV that holds at full speed, set a higher speed "
                "cap (2.5 m/s or more) with the space to match, and run this again.", learn="kV"))
        ident_findings, ident = motor_identity_findings(kvs, ctx or {})
        F.extend(ident_findings)
        if ident:
            report["motor"] = ident
        if len(good) == len(mods) and r2_min >= 0.95 and kv_spread <= 15:
            values = {}
            for n, f in good.items():
                values[f"FF/{n}/kS"] = max(0.0, f["kS"])
                values[f"FF/{n}/kV"] = f["kV"]
                values[f"FF/{n}/kA"] = max(0.0, f.get("kA", 0.0))
            F.append(finding(
                "ok", "Per-module feedforward measured",
                "Apply these live, then run drive_step on the floor (not this test again): the speed "
                "error should collapse and the drive kP can come down to a gentle correction. Saving "
                "the drive gains writes them to swervetune.json.",
                {"type": "gains", "values": {k: round(v, 4) for k, v in values.items()},
                 "then": {"test": "drive_step", "env": "FIELD"}}))
    # A motor's health is judged on blocks only: on carpet the chassis couples the wheels, so a
    # module drifting from its siblings could be its wheel, its grip or its gearing.
    if history and blocks:
        F.extend(motor_trend_findings(fits, history))
    met = sum(t["met"] for t in report["targets"])
    report["summary"] = (f"Feedforward: {len(good)}/{len(mods)} modules fitted, kV spread "
                         f"{kv_spread:.0f}%" + (" (blocks: friction only)" if blocks else ""))
    _practice_note(result, report)
    return _finish(report)


# ============================================================================ spin


def spin_report(result):
    ch, meta, env = result["channels"], result.get("meta", {}), result.get("env", "")
    t, cmd = ch.get("t", []), ch.get("cmd_omega", [])
    heading = A.unwrap_deg(ch.get("heading", []))
    mods = _modules_in(ch, "v")
    names = _module_names(result, max(mods) + 1 if mods else 0)
    report = {"test": "spin", "env": env, "modules": {}, "findings": [], "targets": []}
    F = report["findings"]
    gyro, wheel, want = [], [], []
    for a, b, w in A.segments(t, cmd)[1:]:
        if abs(w) < 0.05 or b - a < 20:
            continue
        a2 = a + int(0.35 * (b - a))
        dt = t[b - 1] - t[a2]
        if dt <= 0:
            continue
        g = math.radians(heading[b - 1] - heading[a2]) / dt
        wheel_rates = []
        for i in mods:
            r = math.hypot(meta.get(f"m{i}.x", 0.3), meta.get(f"m{i}.y", 0.3))
            wheel_rates.append(A.mean([abs(x) for x in ch[f"m{i}.v"][a2:b]]) / r)
        gyro.append(g)
        wheel.append(math.copysign(A.mean(wheel_rates), w))
        want.append(w)
    if not want:
        report["summary"] = "No spin segments to analyze."
        return _finish(report)
    g_ratio = A.mean([g / w for g, w in zip(gyro, want)])
    w_ratio = A.mean([x / w for x, w in zip(wheel, want)])
    report["measured"] = {"gyro_over_command": g_ratio, "wheels_over_command": w_ratio,
                          "gyro_over_wheels": g_ratio / w_ratio if w_ratio else float("nan")}
    if env == "BLOCKS":
        report["targets"] = [_grade("gyro rotation on blocks (ratio)", abs(g_ratio), 0.05)]
        report["summary"] = f"On blocks: wheels at {w_ratio * 100:.0f}% of command, gyro still."
        if w_ratio < 0.8:
            F.append(finding("warn", "Wheels did not reach the commanded spin speed",
                             "Check drive gains and that every module turned to its tangent.",
                             {"type": "troubleshoot", "symptom": "robot_slow"}))
        return _finish(report)
    report["targets"] = [
        _grade("gyro agrees with command (|1 - ratio|)", abs(1 - g_ratio), 0.08),
        _grade("wheels agree with command (|1 - ratio|)", abs(1 - w_ratio), 0.08),
    ]
    report["cost"] = round(abs(1 - g_ratio) * 10 + abs(1 - w_ratio) * 10, 3)
    if g_ratio < 0:
        F.append(finding(
            "error", "The gyro says the robot turned the other way",
            "Commanded counter-clockwise, gyro read clockwise. With an inverted gyro, field-relative "
            "driving rotates the wrong way as the robot turns and every heading controller fights "
            "itself. Flip invertedIMU in swervedrive.json.",
            {"type": "config", "file": "swervedrive.json", "path": ["invertedIMU"], "value": "toggle"}))
    elif g_ratio / max(w_ratio, 1e-6) < 0.9:
        F.append(finding(
            "warn", f"Robot turned {g_ratio / w_ratio * 100:.0f}% as fast as its wheels imply",
            "Either the wheels are slipping (try a lower spin rate), or the module locations in the "
            "module JSON files are smaller than the real ones. Measure axle center to axle center."))
    elif g_ratio / max(w_ratio, 1e-6) > 1.05:
        F.append(finding(
            "warn", f"Robot turned {g_ratio / w_ratio * 100:.0f}% as fast as its wheels imply",
            "Turning faster than the wheels allow means the module locations in the config are "
            "larger than the real ones - often the frame size was entered instead of the distance "
            "between wheel centers. Measure axle center to axle center."))
    radius = [math.hypot(meta.get(f"m{i}.x", 0.3), meta.get(f"m{i}.y", 0.3)) for i in range(max(mods) + 1)]
    spinning = [abs(c) > 0.05 for c in cmd]
    F.extend(drive_ratio_findings(result, mask=spinning, radius=radius))
    if w_ratio < 0.92 and g_ratio > 0:
        F.append(finding("warn", "Wheels fall short of the commanded spin",
                         "The drive velocity loop is not keeping up; tune drive first.",
                         {"type": "run", "test": "drive_step", "env": "FIELD", "args": {}}))
    if not F:
        F.append(finding("ok", "Spin is consistent",
                         "Gyro, wheels and command agree: module locations and gyro are right."))
    report["summary"] = (f"Spin: gyro {g_ratio * 100:.0f}% of command, wheels {w_ratio * 100:.0f}%.")
    return _finish(report)


# ============================================================================ straight line


def straight_report(result, measured_forward_m=None, measured_lateral_m=None):
    ch, meta = result["channels"], result.get("meta", {})
    t, cmd = ch.get("t", []), ch.get("cmd_vx", [])
    heading = A.unwrap_deg(ch.get("heading", []))
    x, y = ch.get("x", []), ch.get("y", [])
    report = {"test": "straight", "env": result.get("env", ""), "findings": [], "targets": []}
    F = report["findings"]
    if not t:
        report["summary"] = "No data."
        return _finish(report)
    # End of the outbound leg: last sample before the commanded speed first returns to zero.
    started = next((k for k, v in enumerate(cmd) if abs(v) > 1e-3), 0)
    stop = next((k for k in range(started, len(cmd)) if abs(cmd[k]) < 1e-6 and k > started + 5),
                len(cmd) - 1)
    end = min(len(t) - 1, stop + int(0.5 / max(1e-3, (t[1] - t[0]) if len(t) > 1 else 0.01)))
    h0 = math.radians(heading[0])
    dx, dy = x[end] - x[0], y[end] - y[0]
    fwd = dx * math.cos(h0) + dy * math.sin(h0)
    lat = -dx * math.sin(h0) + dy * math.cos(h0)
    dh = heading[end] - heading[0]
    dist = meta.get("distance_m", fwd)
    report["measured"] = {"odometry_forward_m": fwd, "odometry_lateral_m": lat,
                          "heading_change_deg": dh, "commanded_m": dist}
    report["targets"] = [_grade("heading change (deg)", abs(dh), 1.0)]
    # AprilTags, when a camera saw them standing still at the start and at the far end: the ground
    # truth without a tape. The distance between the two poses (field frame, so its length).
    vx, vy = ch.get("vx_vision") or [], ch.get("vy_vision") or []

    def seen(k0, k1):
        pts = [(vx[k], vy[k]) for k in range(max(0, k0), min(k1, len(vx), len(vy))) if A.finite(vx[k]) and A.finite(vy[k])]
        return (A.mean([p[0] for p in pts]), A.mean([p[1] for p in pts])) if len(pts) >= 3 else None
    v0, v1 = seen(0, started), seen(stop, end + 1)
    truth = "the tape"
    if measured_forward_m is None and v0 and v1:
        measured_forward_m = math.hypot(v1[0] - v0[0], v1[1] - v0[1])
        report["measured"]["vision_forward_m"] = measured_forward_m
        truth = "AprilTags"
    if measured_forward_m is not None and fwd and not (0.9 <= measured_forward_m / fwd <= 1.1):
        # Wheels wear a few percent; 10% off is a measuring mistake (measured after the robot came
        # back, the wrong mark, feet for meters), never a wheel size to write into the files.
        F.append(finding(
            "error", f"{truth.capitalize()} say{'s' if truth == 'the tape' else ''} {measured_forward_m:.3f} m but the robot went out {fwd:.3f} m",
            "That is too far apart to be the wheels. Measure from the start mark to the robot's center "
            "where it stopped at the far end, in meters, and enter it again.",
            {"type": "troubleshoot", "symptom": "auto_inaccurate"}))
        report["measured"]["tape_forward_m"] = measured_forward_m
        measured_forward_m = None
    if measured_forward_m is not None:
        report["measured"]["tape_forward_m"] = measured_forward_m
        scale = measured_forward_m / fwd if fwd else float("nan")
        report["measured"]["wheel_scale"] = scale
        report["targets"].append(_grade(f"odometry vs {truth} (|1 - ratio|)", abs(1 - scale), 0.01))
        cfg = meta.get("drive_gear_ratio")
        if A.finite(scale) and abs(1 - scale) > 0.04 and cfg:
            # Odometry reads distance x configured/real; the tape is the truth.
            real = cfg / scale
            c = R.candidates(real, R.family(meta.get("steer_gear_ratio")))
            if c:
                F.append(finding(
                    "warn", f"Every module is off by {abs(1 - scale) * 100:.0f}%: more than tread wear",
                    f"Worn or compressed tread changes the effective wheel size by 1-3%. "
                    f"{abs(1 - scale) * 100:.0f}% matches a different gear ratio on every module: "
                    f"{c[0]['name']} ({c[0]['ratio']:.2f}:1) instead of the configured {cfg}:1. Count "
                    "a pinion before changing the wheel size.",
                    {"type": "troubleshoot", "symptom": "gear_ratio"}))
        if A.finite(scale) and abs(1 - scale) > 0.01:
            F.append(finding(
                "warn", f"Odometry says {fwd:.3f} m, {truth} say{'s' if truth == 'the tape' else ''} {measured_forward_m:.3f} m",
                f"Wheels are effectively {scale:.4f} times their configured size - tread wears and "
                "compresses. Multiply the wheel diameter in physicalproperties.json by this, and the "
                "PathPlanner wheel radius with it.",
                {"type": "config", "file": "modules/physicalproperties.json",
                 "path": ["conversionFactors", "drive", "diameter"], "value": f"x{scale:.4f}"}))
    if measured_lateral_m is not None:
        report["measured"]["tape_lateral_m"] = measured_lateral_m
        report["targets"].append(_grade("sideways drift per meter (m)",
                                        abs(measured_lateral_m) / max(dist, 0.1), 0.01))
    if abs(dh) > 1.0:
        F.append(finding(
            "warn", f"Heading changed {dh:.1f}° over {dist:.1f} m with no correction",
            "A robot drifting in heading on a straight command has a corner that is weaker or "
            "pointed differently from the others. Check the offsets with a straight-edge, compare "
            "modules in drive_ff, and only then turn on heading correction - it hides the cause.",
            {"type": "troubleshoot", "symptom": "wont_drive_straight"}))
    if not F:
        F.append(finding("ok", "Straight and true", "Heading held without correction."))
    report["cost"] = round(abs(dh) + (abs(1 - report["measured"].get("wheel_scale", 1)) * 100), 3)
    report["summary"] = f"Straight: {fwd:.2f} m by odometry, heading {dh:+.1f}°, lateral {lat:+.3f} m."
    return _finish(report)


# ============================================================================ capture: health


def health_report(result):
    ch = result["channels"]
    t = ch.get("t", [])
    mods = _modules_in(ch, "steer")
    names = _module_names(result, max(mods) + 1 if mods else 0)
    report = {"test": "capture", "env": result.get("env", ""), "modules": {}, "findings": [],
              "targets": []}
    F = report["findings"]
    worst_noise, worst_gap = 0.0, 0.0
    for i in mods:
        steer = ch[f"m{i}.steer"]
        motor = ch.get(f"m{i}.motor", [])
        noise = A.stdev(steer)
        gap = A.median([abs(A.wrap180(a - b)) for a, b in zip(steer, motor)]) if motor else 0.0
        moved = max(steer) - min(steer) if steer else 0.0
        report["modules"][names[i]] = {"noise_deg": noise, "motor_vs_absolute_deg": gap,
                                       "range_deg": moved, "mean_deg": A.mean(steer)}
        if moved < 5:
            worst_noise = max(worst_noise, noise)
            worst_gap = max(worst_gap, gap)
            if noise > 0.3:
                F.append(finding(
                    "warn", f"{names[i]}: absolute encoder noisy at rest ({noise:.2f}°)",
                    "A still module should read within a few hundredths of a degree. Check the "
                    "encoder's magnet and that the cable is seated.",
                    {"type": "troubleshoot", "symptom": "pod_jitter"}))
            if gap > 2.0:
                F.append(finding(
                    "warn", f"{names[i]}: motor encoder {gap:.1f}° away from the absolute encoder",
                    "The steering loop is closed on the motor encoder, which was set from the "
                    "absolute encoder at boot. A gap this size means it slipped or the boot read was "
                    "bad - the module will point wrong by this much until the robot restarts.",
                    {"type": "troubleshoot", "symptom": "pod_drifts"}))
    heading = A.unwrap_deg(ch.get("heading", []))
    drift = 0.0
    # Over a few seconds the gyro's noise is as big as its drift: a 3-second capture failed good
    # gyros 10-40% of the time. Drift is judged from 20 seconds or more (Calibrate's "Record a
    # minute still").
    long_enough = len(t) > 10 and t[-1] - t[0] >= GYRO_DRIFT_MIN_S
    if long_enough:
        drift = (heading[-1] - heading[0]) / (t[-1] - t[0]) * 60
        if abs(drift) > 0.5:
            F.append(finding(
                "warn", f"Gyro drifts {drift:.1f}°/min sitting still",
                "Field-relative driving inherits this. Keep the robot still for the first few "
                "seconds after power-on while the gyro calibrates."))
    bus = A.mean(ch.get("vbus", []))
    if A.finite(bus) and bus < 12.2:
        F.append(finding("info", f"Battery at rest {bus:.1f} V",
                         "Below about 12.3 V at rest a battery is tired; tuning numbers move with it."))
    report["targets"] = [_grade("encoder noise at rest (deg)", worst_noise, 0.3),
                         _grade("motor vs absolute (deg)", worst_gap, 2.0)]
    if long_enough:
        report["targets"].append(_grade("gyro drift (deg/min)", abs(drift), 0.5))
    elif len(t) > 10:
        F.append(finding("info", "Gyro drift not judged from a short capture",
                         f"A capture under {GYRO_DRIFT_MIN_S:.0f} s can't tell drift from noise. The Calibrate "
                         "tab's Gyro panel records a minute standing still for that."))
    if not F:
        F.append(finding("ok", "Sensors healthy", "Quiet encoders, encoders agree"
                         + (", gyro steady." if long_enough else ".")))
    # Only what was measured: a short capture says nothing about the gyro.
    report["summary"] = (f"Health: noise {worst_noise:.2f}°, motor/absolute gap {worst_gap:.1f}°, "
                         + (f"gyro drift {drift:.2f}°/min." if long_enough
                            else f"gyro drift not judged (under {GYRO_DRIFT_MIN_S:.0f} s)."))
    return _finish(report)


# ============================================================================ offsets and hand checks


def offsets_from_capture(result, current_offsets):
    """New absoluteEncoderOffset per module, from a capture with every wheel set straight ahead.

    Works whichever sensor steers: YAGSL's reported angle is the physical angle relative to the
    configured zero in both modes, so new = old + what it reads when straight.
    """
    ch = result["channels"]
    mods = _modules_in(ch, "steer")
    names = _module_names(result, max(mods) + 1 if mods else 0)
    out = {}
    for i in mods:
        s = ch[f"m{i}.steer"]
        reading = A.wrap180(A.median(s))
        spread = max(s) - min(s) if s else 0
        old = current_offsets.get(names[i], 0.0)
        out[names[i]] = {"reading_deg": reading, "old": old,
                         "new": round((old + reading) % 360, 2), "steady": spread < 1.0}
    return out


def hand_check(result, kind, expected_sign=1):
    """One hand-motion step: ``kind`` is ``wheel`` (drive encoder), ``steer`` (both steering sensors)
    or ``gyro`` (the whole robot turned counter-clockwise by hand: the heading must go up)."""
    ch = result["channels"]
    if kind == "gyro":
        # WPILib and YAGSL: counter-clockwise positive, seen from above. A quarter turn is plenty.
        return {"gyro": {"heading": A.hand_motion(A.unwrap_deg(ch.get("heading") or []), expected_sign, min_travel=20)}}
    mods = _modules_in(ch, "steer")
    names = _module_names(result, max(mods) + 1 if mods else 0)
    out = {}
    for i in mods:
        if kind == "wheel":
            v = A.hand_motion(ch[f"m{i}.pos"], expected_sign, min_travel=0.05)
            out[names[i]] = {"drive": v}
        else:
            absolute = A.hand_motion(A.unwrap_deg(ch[f"m{i}.steer"]), expected_sign, min_travel=20)
            motor = A.hand_motion(A.unwrap_deg(ch[f"m{i}.motor"]), expected_sign, min_travel=20)
            r = A.ratio(A.unwrap_deg(ch[f"m{i}.motor"]), A.unwrap_deg(ch[f"m{i}.steer"]))
            out[names[i]] = {"absolute": absolute, "motor": motor, "motor_per_module_deg": r}
    return out


# ============================================================================ gear ratios


def _travel(ch, t, mods, names, mask=None, radius=None):
    """Distance each module reported, from positions if recorded, else integrated speed."""
    out = {}
    for i in mods:
        pos = ch.get(f"m{i}.pos")
        v = ch.get(f"m{i}.v")
        d = 0.0
        for k in range(1, len(t)):
            if mask is not None and not mask[k]:
                continue
            if pos:
                step = pos[k] - pos[k - 1]
            elif v:
                step = v[k] * (t[k] - t[k - 1])
            else:
                continue
            if A.finite(step):
                d += abs(step)
        out[names[i]] = d / radius[i] if radius else d
    return out


def drive_ratio_findings(result, mask=None, radius=None):
    """On the floor only: a module whose reported travel differs from the rest has another ratio."""
    if result.get("env") not in ("FIELD",):
        return []
    ch, meta = result["channels"], result.get("meta", {})
    t = ch.get("t", [])
    mods = _modules_in(ch, "v") or _modules_in(ch, "pos")
    names = _module_names(result, max(mods) + 1 if mods else 0)
    cfg = meta.get("drive_gear_ratio")
    fam = R.family(meta.get("steer_gear_ratio"))
    travel = _travel(ch, t, mods, names, mask, radius)
    if min(travel.values() or [0]) < (0.5 if not radius else 1.0):
        return []  # not enough travel to judge
    out = []
    for f in R.module_ratio_findings(travel, cfg or 1.0, fam):
        if cfg and f["candidates"]:
            # A ratio REV sells fits: one pinion tooth different.
            out.append(finding(
                "warn", f"{f['module']}: drive gear ratio looks different from the other modules",
                R.describe(f) + " On the floor every wheel covers the same ground, so a different reported "
                "distance means a different reduction - the motor encoder cannot see the gearbox. Count "
                "that module's pinion teeth.", {"type": "troubleshoot", "symptom": "gear_ratio"},
                ratio=f))
        else:
            # No sold ratio fits: a worn or different wheel (MAXSwerve tread wears up to about 4%
            # smaller), or one that slipped. Not a reason to open the gearbox.
            more = "less" if f["travel_ratio"] < 1 else "more"
            out.append(finding(
                "info", f"{f['module']} reports {abs(1 - f['travel_ratio']) * 100:.1f}% {more} travel than the others",
                "On the floor every wheel covers the same ground. No gear ratio REV sells explains this, so "
                "it is that wheel: worn or different tread, or it slipped. Check its size (Calibrate tab, "
                "Wheel sizes) and its tread.", ratio=f))
    return out


def steer_ratio_findings(result):
    """Motor encoder against the absolute encoder: their ratio is real over configured reduction."""
    ch, meta = result["channels"], result.get("meta", {})
    if result.get("env") == "SIM" or meta.get("steer_feedback_absolute") == 1:
        return []  # one physical sensor, or none: nothing to compare
    cfg = meta.get("steer_gear_ratio")
    mods = _modules_in(ch, "motor")
    names = _module_names(result, max(mods) + 1 if mods else 0)
    out = []
    for i in mods:
        motor = A.unwrap_deg(ch[f"m{i}.motor"])
        absolute = A.unwrap_deg(ch.get(f"m{i}.steer", []))
        if not absolute or (max(absolute) - min(absolute)) < 30:
            continue
        r = A.ratio(motor, absolute)
        if A.finite(r) and abs(r - 1) > 0.03:
            real = (cfg or 0) * r
            known = [f"{n} ({v:.2f}:1)" for n, v in R.STEER if cfg and abs(v - real) / real < 0.03]
            out.append(finding(
                "warn", f"{names[i]}: steering motor moves {r:.3f}x as far as the module",
                (f"The configured steering ratio is {cfg}:1 but this module behaves like {real:.2f}:1."
                 if cfg else "The steering ratio in the config does not match this module.")
                + (f" That matches {known[0]}." if known else "")
                + " With a wrong steering ratio the motor encoder drifts away from the real angle on "
                "every move. If r is near -1 instead, the steering motor inversion is wrong.",
                {"type": "troubleshoot", "symptom": "gear_ratio"}, ratio=r))
    return out


# ============================================================================ dispatch


# ============================================================================ slip


SLIP_MARGIN = 0.90  # the limit sits this far below the weakest corner's breakaway current


def _abbr(name):
    """frontleft -> FL, back_right -> BR; anything else unchanged."""
    n = name.lower()
    fb = "F" if "front" in n else "B" if "back" in n or "rear" in n else ""
    lr = "L" if "left" in n else "R" if "right" in n else ""
    return fb + lr if fb and lr else name


def slip_report(result):
    """The wall push: each wheel's breakaway current, and the drive current limit to use."""
    ch = result["channels"]
    meta = result.get("meta", {})
    env = result.get("env", "")
    t = ch.get("t", [])
    mods = _modules_in(ch, "amps")
    names = _module_names(result, max(mods) + 1 if mods else 0)
    thr = meta.get("slip_mps", 0.15)
    ceiling = meta.get("ceiling_a")
    policy = meta.get("policy_a") or ceiling
    before = meta.get("limit_before_a")
    report = {"test": "slip", "env": env, "practice": bool(result.get("practice")), "modules": {},
              "findings": [], "targets": [], "annotations": []}
    F = report["findings"]
    if meta.get("wall_lost") == 1:
        F.append(finding(
            "error", "The robot drove instead of pushing: it was not against a wall",
            "A wheel turned at a current far too low to be slipping, so the chassis was free to move. "
            "Put the front bumper flat against something solid - the field wall, or a wall in the "
            "shop - with every wheel pointing into it, and run again.",
            {"type": "run", "test": "slip", "env": "FIELD"}))
        report["summary"] = "Slip test: not against a wall, nothing measured"
        return _finish(report)
    if env == "SIM":
        F.append(finding("info", "Simulation has no carpet",
                         "This proves the test runs; the numbers mean nothing. Run it on the robot."))

    found = {}
    for i in mods:
        amps = [abs(a) if A.finite(a) else float("nan") for a in ch[f"m{i}.amps"]]
        v = ch.get(f"m{i}.v") or [0.0] * len(amps)
        k = next((j for j in range(len(v) - 1)
                  if A.finite(v[j]) and A.finite(v[j + 1]) and abs(v[j]) > thr and abs(v[j + 1]) > thr), None)
        upto = [a for a in amps[:(k + 1 if k is not None else len(amps))] if A.finite(a)]
        peak = max(upto) if upto else float("nan")
        m = {"slipped": k is not None, "peak_a": peak,
             "slip_a": peak if k is not None else None, "slip_t": t[k] if k is not None else None}
        report["modules"][names[i]] = m
        if k is not None:
            found[names[i]] = peak
            report["annotations"].append({
                "type": "point", "t": t[k], "y": peak, "learn": "traction", "label": f"{_abbr(names[i])} {peak:.0f} A",
                "text": f"{names[i]} breaks loose at {peak:.1f} A: past this its push is more than the carpet "
                        "holds, so the wheel spins instead of pushing harder."})
    if ceiling:
        report["annotations"].append({"type": "band", "x0": t[0] if t else 0, "x1": t[-1] if t else 1,
                                      "y0": 0.95 * ceiling, "y1": ceiling, "learn": "current_limit",
                                      "text": f"The ceiling for this run, {ceiling:.0f} A: never above the team's policy."})

    n = len(mods)
    # The test's job is a drive limit: from the weakest breakaway, or the policy itself when the carpet
    # grips past the ceiling. Either is a pass; how many wheels slipped is information (a grippy
    # carpet slipping none used to score 0, and the Guide step could never tick).
    report["targets"] = [_grade("a drive limit found", 1, 1, lower_is_better=False)]
    report["wheels_slipped"] = len(found)
    if not found:
        rec = int(min(x for x in (policy, ceiling) if x))
        report["recommended_a"] = rec
        F.append(finding(
            "ok", f"No wheel slipped up to {ceiling:.0f} A",
            "This carpet grips better than the ceiling allows, so traction is not what limits "
            f"acceleration here - the team's {policy:.0f} A policy is. "
            + ("" if not before or before >= rec else f"The robot ran at {before:.0f} A; {rec} A is allowed. ")
            + "Keep the policy limit.",
            {"type": "config", "file": "modules/physicalproperties.json", "path": ["currentLimit", "drive"],
             "value": rec} if before and abs(before - rec) >= 1 else None))
        report["summary"] = f"Slip test: no slip up to {ceiling:.0f} A"
        return _finish(report)

    weakest = min(found, key=found.get)
    low, high = found[weakest], max(found.values())
    spread = (high - low) / low * 100 if low > 0 else 0.0
    rec = int(SLIP_MARGIN * low)
    if policy:
        rec = min(rec, int(policy))
    report["recommended_a"] = rec
    # Front against rear is the test itself (the wall tips weight onto the rear wheels); the robot's
    # balance shows only left against right on the same axle.
    axles = []
    for a, b in (("frontleft", "frontright"), ("backleft", "backright")):
        if a in found and b in found:
            axles.append((a, b, abs(found[a] - found[b]) / min(found[a], found[b]) * 100))
    lr = max((x[2] for x in axles), default=0.0)
    report["targets"].append(_grade("left/right difference on an axle (%)", lr, 20.0))
    listing = ", ".join(f"{n2} {a:.1f} A" for n2, a in sorted(found.items(), key=lambda kv: kv[1]))
    F.append(finding(
        "ok", f"Drive current limit: {rec} A",
        f"Breakaway currents: {listing}. The weakest corner, {weakest}, sets the limit: 90% of "
        f"{low:.1f} A leaves room for a different carpet at an event and for tread that wears. Just "
        "below slip is the hardest the carpet lets the robot accelerate; above it the wheel only "
        "spins, wasting battery and making odometry count distance the robot never traveled. "
        "Change PathPlanner's drive current limit to match (Settings, Robot Config); the linter "
        "checks they agree. Then redeploy and measure the feedforward again.",
        {"type": "config", "file": "modules/physicalproperties.json", "path": ["currentLimit", "drive"],
         "value": rec}))
    if before and before > low:
        F.append(finding(
            "warn", f"The limit in use, {before:.0f} A, is above where {weakest} slips",
            "Hard acceleration spins that wheel today. The robot loses push it could have had, the "
            "tread wears, and the odometry drifts."))
    fronts = [found[n2] for n2 in ("frontleft", "frontright") if n2 in found]
    rears = [found[n2] for n2 in ("backleft", "backright") if n2 in found]
    if fronts and (not rears or A.mean(rears) > 1.1 * A.mean(fronts)):
        F.append(finding(
            "info", "The front wheels slipped first, as a wall push makes them",
            "The wheels push at the floor and the wall pushes back at bumper height, which tips weight "
            "off the front wheels onto the rear ones: the fronts break loose at a lower current, the "
            "rears at a higher one" + ("" if rears else ", above this run's ceiling") + ". That is the test, "
            "not the robot's balance. Accelerating hard tips weight the same way, so the front pair's "
            "number is the right one for the limit.", learn="traction"))
    if lr > 20:
        a, b, _ = max(axles, key=lambda x: x[2])
        F.append(finding(
            "warn", f"{a} and {b} slip at different currents ({found[a]:.0f} and {found[b]:.0f} A)",
            "Two wheels on the same axle feel the wall's tipping alike, so a difference between them is "
            "the robot's weight sitting to one side (a battery or a heavy mechanism off center), or one "
            "wheel's tread. The lighter side sets the limit for all four; evening it out raises it."))
    never = [names[i] for i in mods if not report["modules"][names[i]]["slipped"]]
    if never:
        F.append(finding("info", f"{', '.join(never)} never slipped up to {ceiling:.0f} A",
                         "Those corners carry more weight. The limit still has to protect the "
                         "lightest one."))
    report["summary"] = f"Slip test: weakest corner {weakest} at {low:.1f} A; recommended limit {rec} A"
    _practice_note(result, report)
    return _finish(report)


def pdh_map_report(result):
    """The PDH-port pulse test: what was found. The Wiring tab compares it with the map and saves."""
    from . import pdhports

    r = pdhports.from_pulses(result)
    n, found = len(r["rows"]), len(r["proposed"])
    bad = any(f["level"] == "error" for f in r["findings"])
    return {"test": "pdh_map", "env": result.get("env", ""),
            "summary": (f"Found the PDH port of {found} of {n} swerve motors: "
                        + ", ".join(f"{k} on {v}" for k, v in r["proposed"].items())
                        + ". Open the Wiring tab to compare them with the map and save them.") if found
            else "No PDH port found for any motor.",
            "findings": [finding(f["level"], f["title"], f["why"]) for f in r["findings"]],
            "targets": [], "score": 100 if n and found == n and not bad else None, "cost": None,
            "next": None, "modules": {}, "pdh": r}


MOI_PLAUSIBLE = (1.5, 15.0)    # kg m^2: an FRC robot with bumpers and battery
SCRUB_TOLERANCE = 0.15


def robot_context(project):
    """What only the laptop knows about the robot, for the reports that need it (spin_ff, and
    drive_ff's motor check)."""
    if project is None:
        return {}
    mass, source = project.mass()
    moi, _ = project.moi()
    inv = ((project.data.get("swervetune.json") or {}).get("motors") or {}).get("drive")
    try:
        vmax = project.create_swerve_max_speed()[0] or project.max_module_speed()
    except (OSError, ValueError, KeyError, TypeError):
        vmax = None
    return {"mass_kg": mass, "mass_source": source, "moi_estimate": moi, "drive_gear": project.drive_gear(),
            "wheel_d_in": project.wheel_d_in(), "drive_kind": project.drive_kind(), "drive_inventory": inv,
            "max_speed": vmax, "inverted_imu": bool((project.data.get("swervedrive.json") or {}).get("invertedIMU", False)),
            "design": _design(project)}


def _design(project):
    """The robot's design file, for bring-up's motor test; None without one."""
    from . import design
    try:
        return design.load(project)
    except (OSError, ValueError):
        return None


# Free speed at 12 V, rpm (REV's spec tables). A NEO V1.1 and a NEO 2.0 spin alike, so this can't
# tell them apart.
MOTOR_FREE_RPM = {k: revspecs.MOTORS[k]["free_rpm"] for k in ("neo", "vortex", "neo550")}
MOTOR_LABEL = {"neo": "NEO", "vortex": "NEO Vortex", "neo550": "NEO 550"}
# A measured kV includes friction and a loaded wheel, so motors read a little under the datasheet.
MEASURED_SHARE = 0.94


def motor_from_kv(kv, gear, wheel_d_in):
    """Which motor a drive feedforward's kV (volts per m/s) belongs to.

    The speed in kV came from the motor's own encoder through the configured gear ratio and wheel
    size, so undoing those with the same numbers gives the motor's own rpm per volt, whatever the
    real gearing is. Returns ``(rpm_per_volt, best_kind, {kind: share_of_datasheet})``.
    """
    rpm_per_v = 60.0 * gear / (kv * math.pi * wheel_d_in * 0.0254)
    shares = {k: rpm_per_v / (rpm / 12.0) for k, rpm in MOTOR_FREE_RPM.items()}
    best = min(shares, key=lambda k: abs(math.log(shares[k] / MEASURED_SHARE)))
    return rpm_per_v, best, shares


def motor_identity_findings(kvs, ctx):
    """The drive motors as measured, against the configuration."""
    gear, wheel, kind = ctx.get("drive_gear"), ctx.get("wheel_d_in"), ctx.get("drive_kind")
    if not (kvs and gear and wheel):
        return [], None
    rpm_per_v, best, shares = motor_from_kv(A.median(kvs), gear, wheel)
    ident = {"rpm_per_volt": rpm_per_v, "kind": best, "label": MOTOR_LABEL[best]}
    fit = abs(math.log(shares[best] / MEASURED_SHARE))
    if fit > 0.12:
        return [finding("warn", f"The drive motors spin at {rpm_per_v:.0f} rpm per volt, like no REV motor",
                        "A NEO is about 473, a Vortex 565, a NEO 550 917. Heavy drag (a binding module, a "
                        "dragging bumper) lowers it; check the modules spin freely by hand.")], ident
    if kind in MOTOR_FREE_RPM and kind != best:
        return [finding("error", f"The config says {MOTOR_LABEL[kind]}, but the drive motors spin like "
                                 f"{MOTOR_LABEL[best]}s ({rpm_per_v:.0f} rpm per volt)",
                        f"A NEO is about 473 rpm per volt, a Vortex 565, a NEO 550 917. Set the YAGSL drive "
                        f"type (modules/*.json) and swervetune.json's motor inventory to {MOTOR_LABEL[best]}, "
                        "and check the controller type matches (the Motors tab shows what each controller "
                        "says it is).", {"type": "troubleshoot", "symptom": "gear_ratio"})], ident
    return [finding("info", f"The drive motors spin like {MOTOR_LABEL[best]}s, as configured "
                            f"({rpm_per_v:.0f} rpm per volt)",
                    "Measured from the feedforward: the motor's own speed per volt, whatever the gearing.")], ident


def spin_ff_report(result, history=None, mass_kg=None, mass_source="", moi_estimate=None):
    """The spin_ff run: the robot's angular feedforward, and from it the moment of inertia.

    Each module rolls along its tangent, so the drive feedforward applies with the wheel speed
    r*w: V = kS sgn(w) + (kV r) w + kA_ang alpha, and kA_ang = kA_lin MOI / (mass r). With the
    linear kA from drive_ff and the mass, MOI = mass r kA_ang / kA_lin.
    """
    ch, meta, env = result["channels"], result.get("meta", {}), result.get("env", "")
    report = {"test": "spin_ff", "env": env, "practice": bool(result.get("practice")), "modules": {},
              "findings": [], "targets": []}
    F = report["findings"]
    if env == "BLOCKS":
        report["summary"] = "On blocks nothing turns: run it on the floor."
        F.append(finding("error", "spin_ff needs the robot on the floor",
                         "The moment of inertia is the robot resisting being turned; on blocks there is no "
                         "robot to turn.", {"type": "run", "test": "spin_ff", "env": "FIELD"}))
        return _finish(report)
    t = ch.get("t", [])
    heading = [math.radians(h) for h in A.unwrap_deg(ch.get("heading", []))]
    mods = _modules_in(ch, "volts")
    n = len(t)
    w = [0.0] * n
    for k in range(1, n - 1):
        w[k] = (heading[k + 1] - heading[k - 1]) / max(1e-6, t[k + 1] - t[k - 1])
    volts = [A.mean([ch[f"m{i}.volts"][k] for i in mods]) for k in range(n)]
    fit = A.fit_feedforward(t, volts, w, min_speed=0.05)
    radii = [math.hypot(meta.get(f"m{i}.x", 0), meta.get(f"m{i}.y", 0)) for i in mods]
    good_r = [x for x in radii if x > 0]
    r = A.mean(good_r) if good_r else float("nan")
    report["measured"] = {"angular": fit, "radius_m": r}
    if not fit.get("ok"):
        report["summary"] = "No usable angular fit."
        F.append(finding("error", "The spin couldn't be fitted", fit.get("reason", "the fit failed")
                         + ". Check every module pointed along its tangent during the run, and the gyro "
                           "reads the turn (the spin test checks both)."))
        return _finish(report)
    kA_ang, kV_ang = fit["kA"], fit["kV"]
    lin = []
    for entry in reversed(history or []):
        lin = [m for m in (entry.get("modules") or {}).values() if m.get("ok") and m.get("kA", 0) > 0]
        if lin:
            break
    report["targets"] = [_grade("angular fit R²", fit.get("r2", 0), 0.95, lower_is_better=False)]
    if not lin:
        report["summary"] = f"Angular kA {kA_ang:.3f} V/(rad/s²); the MOI needs the linear one from drive_ff."
        F.append(finding("warn", "Measure the drive feedforward on the floor first",
                         "The moment of inertia comes from comparing how hard the robot is to turn with how "
                         "hard it is to push, so it needs drive_ff's linear kA from the floor.",
                         {"type": "run", "test": "drive_ff", "env": "FIELD"}))
        return _finish(report)
    kA_lin = A.median([m["kA"] for m in lin])
    kV_lin = A.median([m["kV"] for m in lin])
    scrub = (kV_ang / r) / kV_lin if r > 0 and kV_lin > 0 else float("nan")
    report["measured"].update(kA_lin=kA_lin, kV_lin=kV_lin, turn_vs_straight_kv=scrub)
    if A.finite(scrub) and abs(scrub - 1) > SCRUB_TOLERANCE:
        more = "more" if scrub > 1 else "less"
        F.append(finding("warn", f"Turning took {abs(scrub - 1) * 100:.0f}% {more} voltage per wheel speed "
                                 "than driving straight",
                         "Rolling along their tangents, the wheels should need the same voltage per m/s as "
                         "driving straight. More means they scrub: modules not quite on their tangents, or "
                         "module positions in the config that don't match the robot (measure them in the "
                         "Calibrate tab). The MOI is still a fair estimate, but check that first.",
                         {"type": "troubleshoot", "symptom": "skew_when_rotating"}))
    if mass_kg is None:
        report["summary"] = f"Angular kA {kA_ang:.3f}; the MOI needs the robot's mass."
        F.append(finding("warn", "Weigh the robot to get its moment of inertia",
                         "Put robotMassKg (with bumpers and battery) in swervetune.json, then re-open this run."))
        return _finish(report)
    moi = mass_kg * r * kA_ang / kA_lin
    report["measured"]["moi_kg_m2"] = moi
    plausible = MOI_PLAUSIBLE[0] <= moi <= MOI_PLAUSIBLE[1]
    report["targets"].append(_grade("MOI plausible (1 = yes)", 1.0 if plausible else 0.0, 1.0,
                                    lower_is_better=False))
    est = f" (the estimate was {moi_estimate:.2f})" if moi_estimate else ""
    assumed = "assumed" in (mass_source or "")
    report["summary"] = f"Moment of inertia {moi:.2f} kg·m²{est}, from {mass_kg:.0f} kg."
    if not plausible:
        F.append(finding("error", f"{moi:.2f} kg·m² is not a plausible moment of inertia",
                         f"FRC robots come out between {MOI_PLAUSIBLE[0]} and {MOI_PLAUSIBLE[1]}. Check the "
                         "linear kA came from a floor drive_ff run on this robot, and the mass."))
        return _finish(report)
    if assumed:
        # The moment of inertia scales with the mass it was worked out from: a guessed mass gives a
        # guessed MOI, and saving it would put a guess into every auto PathPlanner plans.
        F.append(finding("warn", f"Moment of inertia: {moi:.2f} kg·m²{est}, from an assumed {mass_kg:.0f} kg",
                         "It scales with the mass, and nobody has weighed the robot yet. Weigh it with "
                         "bumpers and battery (Calibrate tab), save the mass, then re-open this run to "
                         "save the moment of inertia."))
        return _finish(report)
    F.append(finding("warn",
                     f"Moment of inertia: {moi:.2f} kg·m²{est}",
                     "PathPlanner uses it for how hard the robot can start and stop turning. Save it to "
                     "swervetune.json, then copy it into PathPlanner (Settings, Robot Config, MOI).",
                     {"type": "config", "file": "swervetune.json", "path": ["robotMoiKgM2"],
                      "value": round(moi, 2)}))
    return _finish(report)


GYRO_DRIFT_MIN_S = 30.0  # one threshold everywhere: the health capture and Calibrate's minute


def no_data_report(result):
    """A run that recorded nothing gets no score. An empty run must never read as a pass."""
    why = result.get("message") or "The run recorded no samples."
    return {"test": result.get("test"), "env": result.get("env", ""), "summary": "No usable data: " + why,
            "findings": [finding("error", "Nothing was measured", why
                                 + " Fix whatever stopped it (the message says), then run it again.")],
            "targets": [], "score": None, "cost": None, "next": None, "modules": {}}


WHEEL_TESTS = ("drive_step", "drive_ff", "straight", "slip", "spin", "spin_ff", "pdh_map")


MAX_STEP = 2.0
# A drive save keeps the measured feedforward too: it was applied live, and a reboot would lose it.
_SAVE_KEYS = {"steer_pid": ["Steer"], "drive_pid": ["Drive", "FF"]}


def _concrete(rep, gains, kw):
    """Makes every action something the command line can carry out as written:

    * a gain change is held to at most double or half the gain now (a gain at 0 may be set to its
      first value), and says so when it was held;
    * a file change carries the real value, not "toggle" or "x1.0123", when the robot's files are
      known;
    * a save names the gain groups ``save gains --keys`` takes.
    """
    gains = gains or {}
    for f in rep.get("findings") or []:
        a = f.get("action")
        if not a:
            continue
        if a.get("type") == "gains":
            held = []
            for k, v in list((a.get("values") or {}).items()):
                g = gains.get(k)
                if isinstance(g, (int, float)) and A.finite(g) and g > 0 and A.finite(v):
                    c = min(max(float(v), g / MAX_STEP), g * MAX_STEP)
                    if abs(c - v) > 1e-12:
                        a["values"][k] = float(f"{c:.6g}")
                        held.append(k.split("/")[-1])
            if held:
                a["clamped"] = True
                f["why"] = f["why"].rstrip() + (f" ({', '.join(held)} held to {MAX_STEP:g}× this run: one step of at "
                                                "most double or half. Run again and the advice continues.)")
        elif a.get("type") == "config":
            v = a.get("value")
            if v == "toggle" and kw.get("inverted_imu") is not None:
                a["value"] = not kw["inverted_imu"]
            elif isinstance(v, str) and v.startswith("x") and kw.get("wheel_d_in"):
                try:
                    a["value"] = round(kw["wheel_d_in"] * float(v[1:]), 4)
                except ValueError:
                    pass
            if a["value"] == "toggle" or (isinstance(a["value"], str) and a["value"].startswith("x")):
                # Without the robot's files the real value can't be worked out, and "x1.0163"
                # written as-is would be a string where YAGSL needs a number.
                f.pop("action", None)
                f["why"] = f["why"].rstrip() + " (Name the robot, --project, to get the exact value to write.)"
        elif a.get("type") == "save" and "keys" not in a:
            a["keys"] = _SAVE_KEYS.get(a.get("what"), [])
    return rep


def analyze(result, gains=None, **kw):
    """Picks the report for a test result (a dict from TestResult.to_json or a practice run), and
    adds what the run says about the battery to any test that spun the wheels."""
    rep = _concrete(_analyze_test(result, gains, **kw), gains, kw)
    outcome = result.get("outcome")
    if outcome and outcome != "DONE" and isinstance(rep.get("findings"), list):
        rep = _stopped(result, rep)
    if result.get("test") in WHEEL_TESTS and isinstance(rep.get("findings"), list) \
            and len((result.get("channels") or {}).get("t", [])) >= 5:
        kv = ks = None
        if result.get("test") == "drive_ff" and rep.get("env") != "BLOCKS":
            good = [f for f in (rep.get("modules") or {}).values() if f.get("ok")]
            if good:
                kv, ks = A.median([f["kV"] for f in good]), A.median([f["kS"] for f in good])
        b = battery.report(result, kv, ks, kw.get("max_speed"))
        rep["battery"] = b["battery"]
        rep["findings"].extend(b["findings"])
    return rep


def _stopped(result, rep):
    """A run that was stopped part-way: no score, no gains to change, and the next step is to find
    out why it stopped. What it did measure stays, for reading only."""
    why = result.get("message") or "it was stopped before the end"
    for f in rep["findings"]:
        f.pop("action", None)
    stop = finding("error", f"Stopped before it finished: {why}",
                   "Its numbers cover only part of the test, so they can't be scored or used to change "
                   "gains. Find out why it stopped (the reason above), fix that, and run it again.",
                   {"type": "stop", "reason": why})
    rep["findings"].insert(0, stop)
    rep["targets"] = []
    rep["score"] = None
    rep["cost"] = None
    rep["next"] = stop
    rep["summary"] = "Stopped: " + why
    return rep


def _analyze_test(result, gains=None, **kw):
    test = result.get("test")
    if len((result.get("channels") or {}).get("t", [])) < 5:
        return no_data_report(result)
    if test == "steer_step":
        return steer_report(result, gains, **{k: v for k, v in kw.items() if k == "current_limit"})
    if test == "drive_step":
        return drive_report(result, gains, **{k: v for k, v in kw.items()
                                              if k in ("current_limit", "drive_kind", "wheel_d_in")})
    if test == "drive_ff":
        history = kw.get("history")
        if history is None and not result.get("practice"):
            from . import runs
            history = runs.ff_history((result.get("robot") or {}).get("name"),
                                      result.get("env") == "BLOCKS", before=result.get("saved"),
                                      exclude=result.get("_file"), env=result.get("env") or None)
        return feedforward_report(result, gains, history, ctx=kw)
    if test == "spin":
        return spin_report(result)
    if test == "straight":
        return straight_report(result, kw.get("measured_forward_m"), kw.get("measured_lateral_m"))
    if test == "capture":
        return health_report(result)
    if test == "slip":
        return slip_report(result)
    if test == "pdh_map":
        return pdh_map_report(result)
    if test == "motor_test":
        from . import bringup
        return bringup.motor_test_report(result, kw.get("design"))
    if test == "sensors":
        from . import bringup
        return bringup.sensors_report(result, kw.get("design"))
    if test == "spin_ff":
        history = kw.get("history")
        if history is None and not result.get("practice"):
            from . import runs
            history = runs.ff_history((result.get("robot") or {}).get("name"), False,
                                      before=result.get("saved"), exclude=result.get("_file"),
                                      env=result.get("env") or None)
        return spin_ff_report(result, history, kw.get("mass_kg"), kw.get("mass_source", ""),
                              kw.get("moi_estimate"))
    return {"test": test, "summary": "No analysis for this test.", "findings": [], "targets": [],
            "next": None, "score": None}
