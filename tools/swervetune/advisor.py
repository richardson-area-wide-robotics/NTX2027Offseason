"""Reads a test result and says what to do next.

Every report has the same shape, so the GUI, the command line and an AI agent all consume it the
same way::

    {
      "test": "steer_step", "env": "FIELD", "practice": False,
      "summary": "one line a person can read",
      "score": 0-100,          # share of the targets met
      "cost": float,           # lower is better; what an agent should minimise
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


def _grade(name, value, target, lower_is_better=True):
    met = A.finite(value) and (value <= target if lower_is_better else value >= target)
    return {"name": name, "value": value, "target": target, "met": bool(met)}


def _finish(report):
    targets = report.get("targets", [])
    report["score"] = round(100.0 * sum(t["met"] for t in targets) / len(targets)) if targets else None
    report["next"] = next((f for f in report["findings"] if f.get("action")), None)
    return report


def _practice_note(result, report):
    if result.get("practice"):
        report["findings"].insert(0, finding(
            "info", "Practice pod, not the robot",
            "These numbers come from a physics model of a MAXSwerve module. Use it to learn what "
            "each gain does. Keep only gains measured on the robot."))


# ============================================================================ steering


def steer_report(result, gains=None, current_limit=STEER_CURRENT_LIMIT_DEFAULT):
    ch = result["channels"]
    env = result.get("env", "")
    gains = gains or result.get("gains") or {}
    t = ch.get("t", [])
    vbus = A.mean(ch.get("vbus", [12.0])) or 12.0
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
        steps = A.analyze_steps(t, sp, y, volts, tol_abs=1.0, u_max=vbus, amps=amps,
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
        worst["rise"] = max(worst["rise"], L.get("rise_time", 0) or 0)
        worst["os"] = max(worst["os"], summ["all"].get("overshoot_pct", 0) or 0)
        worst["settle"] = max(worst["settle"], L.get("settling_time", 0) or 0)
        worst["sse"] = max(worst["sse"], S.get("steady_state_error", 0) or 0)
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
            return no_data_report(dict(result, message="No step could be analysed: the setpoint "
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
                    f"{math.tan(math.radians(1)) * 100:.1f} cm of sideways drift per metre driven, "
                    f"so this one is about {lateral:.1f} cm per metre. Raise kP 50%.",
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
                f"{worst['sat'] * 100:.0f}% of the move. A higher kP cannot make it faster. The "
                "lever is the steering current limit: a NEO 550 handles 25-30 A in short bursts. "
                "Change currentLimit.angle in physicalproperties.json, redeploy, and watch the "
                "steering motor temperature in the Live view.",
                {"type": "config", "file": "modules/physicalproperties.json",
                 "path": ["currentLimit", "angle"], "value": 25}))
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
        F.append(finding(
            "ok", "Steering meets every target",
            "Save these gains so they survive a restart. Then run it once more on the floor if this "
            "was on blocks.", {"type": "save", "what": "steer_pid"}))
    report["summary"] = (f"Steering: {met}/{len(report['targets'])} targets met; large-step rise "
                         f"{worst['rise'] * 1000:.0f} ms, overshoot {worst['os']:.0f}%, small-step "
                         f"error {worst['sse']:.2f}°.")
    _practice_note(result, report)
    return _finish(report)


# ============================================================================ drive velocity


def drive_report(result, gains=None, current_limit=DRIVE_CURRENT_LIMIT_DEFAULT):
    ch = result["channels"]
    env = result.get("env", "")
    gains = gains or result.get("gains") or {}
    t, sp = ch.get("t", []), ch.get("sp", [])
    vbus = A.mean(ch.get("vbus", [12.0])) or 12.0
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
        steps = A.analyze_steps(t, sp, v, ch.get(f"m{i}.volts"), tol_abs=0.05, u_max=vbus,
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
            return no_data_report(dict(result, message="No speed step could be analysed: the "
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
        elif period == 0 or period > 16:
            F.append(finding(
                "warn", f"Speed is measured {dead_t * 1000:.0f} ms late",
                "Before the controller can correct an error it has to see it. A NEO's built-in "
                "velocity on a SPARK MAX is averaged over a window that YAGSL does not shorten (it "
                "sets a different, quadrature, filter). Delay caps how hard the velocity loop can "
                "push before it oscillates. Try a 16 ms x 2 window and run this again: less delay, "
                "a little more noise.", gains_action(Drive__VelPeriodMs=16, Drive__VelDepth=2)))
        else:
            F.append(finding(
                "info", f"{dead_t * 1000:.0f} ms of delay remains",
                "With the ramp and the sensor window already short, what is left is the 20 ms robot "
                "loop and CAN. That is normal; tune the gains around it."))
    if jitter > DRIVE_TARGETS["jitter_mps"] and have and (kP > 0.15 or kD > 0):
        F.append(finding(
            "warn", f"Speed buzzes ±{jitter:.2f} m/s while holding a constant command",
            "A NEO's built-in sensor counts 42 steps a turn, so the measured speed moves in coarse "
            "jumps. A large kP turns every jump into a voltage kick, and kD on a velocity loop "
            "multiplies them again - you hear it as a buzz and see it as heat. Set kD to 0 and "
            "halve kP; a measured feedforward does the real work.",
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


def feedforward_report(result, gains=None, history=None):
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
    nominal = meta.get("kv_nominal")
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
                                 "Look for wheel slip or a bump during the run, then repeat it.",
                                 {"type": "run", "test": "drive_ff", "env": "FIELD", "args": {}}))
            if f.get("kA", 0) < 0:
                F.append(finding("error", f"{n}: negative kA is not physical",
                                 "Something else pushed on the robot during the run - a collision, "
                                 "a slipping wheel. Repeat it on clear carpet."))
        if kv_spread > 8 and len(kvs) > 1:
            weakest = max(good, key=lambda n: good[n]["kV"])
            F.append(finding(
                "warn", f"kV differs {kv_spread:.0f}% between modules; {weakest} is the weak corner",
                "Up to about 8% is normal motor-to-motor variation and a per-module feedforward "
                "absorbs it. More means that corner is mechanically different: check its gears, "
                "tread and bearings before trusting its numbers."))
        if nominal and kvs:
            ratio = A.mean(kvs) / nominal
            if ratio > 1.15 or ratio < 0.85:
                F.append(finding(
                    "warn", f"Measured kV is {ratio * 100:.0f}% of what the motor physics predicts",
                    "kV is measured against the speed the motor's own encoder reports, so a wrong "
                    "gear ratio or wheel size cancels out of it - it cannot be the cause. What moves "
                    "kV is the motor: the config names one motor (NEO, Vortex, NEO 550) and another is "
                    "fitted. A NEO configured where a Vortex is fitted reads about 84%. Heavy drag "
                    "(a binding module, a dragging bumper) raises it instead.",
                    {"type": "troubleshoot", "symptom": "robot_slow"}))
        if len(good) == len(mods) and r2_min >= 0.95 and kv_spread <= 15:
            values = {}
            for n, f in good.items():
                values[f"FF/{n}/kS"] = max(0.0, f["kS"])
                values[f"FF/{n}/kV"] = f["kV"]
                values[f"FF/{n}/kA"] = max(0.0, f.get("kA", 0.0))
            F.append(finding(
                "ok", "Per-module feedforward measured",
                "Apply these live, then rerun drive_step: the speed error should collapse and the "
                "drive kP can come down to a gentle correction. Save writes them to swervetune.json.",
                {"type": "gains", "values": {k: round(v, 4) for k, v in values.items()}}))
    if history:
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
        report["summary"] = "No spin segments to analyse."
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
            "module JSON files are smaller than the real ones. Measure axle centre to axle centre."))
    elif g_ratio / max(w_ratio, 1e-6) > 1.05:
        F.append(finding(
            "warn", f"Robot turned {g_ratio / w_ratio * 100:.0f}% as fast as its wheels imply",
            "Turning faster than the wheels allow means the module locations in the config are "
            "larger than the real ones - often the frame size was entered instead of the distance "
            "between wheel centres. Measure axle centre to axle centre."))
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
    end = next((k for k in range(started, len(cmd)) if abs(cmd[k]) < 1e-6 and k > started + 5),
               len(cmd) - 1)
    end = min(len(t) - 1, end + int(0.5 / max(1e-3, (t[1] - t[0]) if len(t) > 1 else 0.01)))
    h0 = math.radians(heading[0])
    dx, dy = x[end] - x[0], y[end] - y[0]
    fwd = dx * math.cos(h0) + dy * math.sin(h0)
    lat = -dx * math.sin(h0) + dy * math.cos(h0)
    dh = heading[end] - heading[0]
    dist = meta.get("distance_m", fwd)
    report["measured"] = {"odometry_forward_m": fwd, "odometry_lateral_m": lat,
                          "heading_change_deg": dh, "commanded_m": dist}
    report["targets"] = [_grade("heading change (deg)", abs(dh), 1.0)]
    if measured_forward_m is not None:
        report["measured"]["tape_forward_m"] = measured_forward_m
        scale = measured_forward_m / fwd if fwd else float("nan")
        report["measured"]["wheel_scale"] = scale
        report["targets"].append(_grade("odometry vs tape (|1 - ratio|)", abs(1 - scale), 0.01))
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
                "warn", f"Odometry says {fwd:.3f} m, the tape says {measured_forward_m:.3f} m",
                f"Wheels are effectively {scale:.4f} times their configured size - tread wears and "
                "compresses. Multiply the wheel diameter in physicalproperties.json by this, and the "
                "PathPlanner wheel radius with it.",
                {"type": "config", "file": "modules/physicalproperties.json",
                 "path": ["conversionFactors", "drive", "diameter"], "value": f"x{scale:.4f}"}))
    if measured_lateral_m is not None:
        report["measured"]["tape_lateral_m"] = measured_lateral_m
        report["targets"].append(_grade("sideways drift per metre (m)",
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
    if len(t) > 10 and t[-1] > t[0]:
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
                         _grade("motor vs absolute (deg)", worst_gap, 2.0),
                         _grade("gyro drift (deg/min)", abs(drift), 0.5)]
    if not F:
        F.append(finding("ok", "Sensors healthy", "Quiet encoders, encoders agree, gyro steady."))
    report["summary"] = (f"Health: noise {worst_noise:.2f}°, motor/absolute gap {worst_gap:.1f}°, "
                         f"gyro drift {drift:.2f}°/min.")
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
    """One hand-motion step: ``kind`` is ``wheel`` (drive encoder) or ``steer`` (both steering sensors)."""
    ch = result["channels"]
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
        text = R.describe(f) if cfg else (f"{f['module']} reports {abs(1 - f['travel_ratio']) * 100:.1f}% "
                                          "different travel from the other modules over the same floor.")
        out.append(finding(
            "warn", f"{f['module']}: drive gear ratio looks different from the other modules",
            text + " On the floor every wheel covers the same ground, so a different reported distance "
            "means a different reduction - the motor encoder cannot see the gearbox. Count that "
            "module's pinion teeth.", {"type": "troubleshoot", "symptom": "gear_ratio"},
            ratio=f))
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
    report["targets"] = [_grade("wheels that slipped", len(found), n, lower_is_better=False)]
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
    report["targets"].append(_grade("slip spread between corners (%)", spread, 25.0))
    listing = ", ".join(f"{n2} {a:.1f} A" for n2, a in sorted(found.items(), key=lambda kv: kv[1]))
    F.append(finding(
        "ok", f"Drive current limit: {rec} A",
        f"Breakaway currents: {listing}. The weakest corner, {weakest}, sets the limit: 90% of "
        f"{low:.1f} A leaves room for a different carpet at an event and for tread that wears. Just "
        "below slip is the hardest the carpet lets the robot accelerate; above it the wheel only "
        "spins, wasting battery and making odometry count distance the robot never travelled. "
        "Change PathPlanner's drive current limit to match (Settings, Robot Config); the linter "
        "checks they agree. Then redeploy and measure the feedforward again.",
        {"type": "config", "file": "modules/physicalproperties.json", "path": ["currentLimit", "drive"],
         "value": rec}))
    if before and before > low:
        F.append(finding(
            "warn", f"The limit in use, {before:.0f} A, is above where {weakest} slips",
            "Hard acceleration spins that wheel today. The robot loses push it could have had, the "
            "tread wears, and the odometry drifts."))
    if spread > 25:
        F.append(finding(
            "warn", f"Corners slip at very different currents ({low:.0f} to {high:.0f} A)",
            "The robot's weight is not shared evenly: the corner that slips first carries the least. "
            "A battery or a heavy mechanism far from the center does this. The lightest corner sets "
            "the limit for all four, so evening out the weight raises it."))
    never = [names[i] for i in mods if not report["modules"][names[i]]["slipped"]]
    if never:
        F.append(finding("info", f"{', '.join(never)} never slipped up to {ceiling:.0f} A",
                         "Those corners carry more weight. The limit still has to protect the "
                         "lightest one."))
    report["summary"] = f"Slip test: weakest corner {weakest} at {low:.1f} A; recommended limit {rec} A"
    _practice_note(result, report)
    return _finish(report)


def no_data_report(result):
    """A run that recorded nothing gets no score. An empty run must never read as a pass."""
    why = result.get("message") or "The run recorded no samples."
    return {"test": result.get("test"), "env": result.get("env", ""), "summary": "No usable data: " + why,
            "findings": [finding("error", "Nothing was measured", why
                                 + " Fix whatever stopped it (the message says), then run it again.")],
            "targets": [], "score": None, "cost": None, "next": None, "modules": {}}


def analyze(result, gains=None, **kw):
    """Picks the report for a test result (a dict from TestResult.to_json or a practice run)."""
    test = result.get("test")
    if len((result.get("channels") or {}).get("t", [])) < 5:
        return no_data_report(result)
    if test == "steer_step":
        return steer_report(result, gains, **{k: v for k, v in kw.items() if k == "current_limit"})
    if test == "drive_step":
        return drive_report(result, gains, **{k: v for k, v in kw.items() if k == "current_limit"})
    if test == "drive_ff":
        history = kw.get("history")
        if history is None and not result.get("practice"):
            from . import runs
            history = runs.ff_history((result.get("robot") or {}).get("name"),
                                      result.get("env") == "BLOCKS", before=result.get("saved"),
                                      exclude=result.get("_file"))
        return feedforward_report(result, gains, history)
    if test == "spin":
        return spin_report(result)
    if test == "straight":
        return straight_report(result, kw.get("measured_forward_m"), kw.get("measured_lateral_m"))
    if test == "capture":
        return health_report(result)
    if test == "slip":
        return slip_report(result)
    return {"test": test, "summary": "No analysis for this test.", "findings": [], "targets": [],
            "next": None, "score": None}
