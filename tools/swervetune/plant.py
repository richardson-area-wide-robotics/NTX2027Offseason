"""A practice swerve module: physics plus a SPARK-style controller, no robot needed.

**This is a model, not your robot.** It exists so a student can learn what kP, kD and a ramp rate
do before touching a robot, so an AI agent can rehearse a tuning strategy offline, and so the
analysis code is tested against a plant whose true parameters are known. Every number a robot
cares about must come from the robot. The GUI and the CLI label every practice result as such.

What is modeled, and how faithfully:

* DC motors from datasheet constants (NEO, NEO 550, Vortex), with back-EMF, current, a smart
  current limit and supply voltage. Good.
* A 1 kHz position or velocity PID in REV's units: output is duty cycle, kP is duty per unit of
  error, and **kD multiplies the change in error per 1 ms controller step**, not per second. Closed
  loop ramp rate and output clamping included. Good.
* Steering: gear backlash, Coulomb and viscous friction, and carpet scrub torque when "on the
  floor". Approximate - real scrub depends on tread, carpet and load.
* Drive: a quarter of the robot's mass on each wheel on the floor, or just the wheel in the air
  on blocks. Velocity is measured the way a SPARK MAX does for a NEO: counts from the 42-count
  hall sensor, differenced over a window of ``meas_period_ms`` and averaged over ``meas_depth``
  readings. That reproduces both the delay and the coarse steps that make a high kP buzz. REV's
  exact filter may differ; the real robot's drive_step measures the true delay.
"""

from __future__ import annotations

import math
import random

MOTORS = {
    # name: (stall torque N*m, stall current A, free current A, free speed rpm)
    "neo": (2.6, 105.0, 1.8, 5676.0),
    "neo550": (0.97, 100.0, 1.4, 11000.0),
    "vortex": (3.6, 211.0, 3.6, 6784.0),
    "krakenx60": (7.09, 366.0, 2.0, 6000.0),
    "falcon500": (4.69, 257.0, 1.5, 6380.0),
}


class Motor:
    def __init__(self, kind, nominal=12.0):
        stall_t, stall_i, free_i, free_rpm = MOTORS[kind]
        self.kind = kind
        self.R = nominal / stall_i
        self.Kt = stall_t / stall_i
        self.free_w = free_rpm * 2 * math.pi / 60
        self.Kv = self.free_w / (nominal - self.R * free_i)  # rad/s per volt
        self.free_i = free_i

    def current(self, volts, w):
        return (volts - w / self.Kv) / self.R

    def limit_volts(self, volts, w, i_limit):
        """Clamps voltage so current stays inside a smart current limit, like a SPARK does."""
        bemf = w / self.Kv
        hi = bemf + i_limit * self.R
        lo = bemf - i_limit * self.R
        return max(lo, min(hi, volts))


class SparkPid:
    """REV-style closed loop: duty-cycle output, per-millisecond D and I, ramp and clamp."""

    def __init__(self, kP=0.0, kI=0.0, kD=0.0, i_zone=0.0, ramp_s=0.0, wrap=None):
        self.kP, self.kI, self.kD, self.i_zone, self.ramp_s = kP, kI, kD, i_zone, ramp_s
        self.wrap = wrap
        self.prev_err = None
        self.i_acc = 0.0
        self.out = 0.0

    def step(self, setpoint, measured, arb_ff_duty=0.0):
        err = setpoint - measured
        if self.wrap:
            err = (err + self.wrap / 2) % self.wrap - self.wrap / 2
        if self.i_zone and abs(err) > self.i_zone:
            self.i_acc = 0.0
        else:
            self.i_acc += err
        d = 0.0 if self.prev_err is None else err - self.prev_err
        self.prev_err = err
        want = self.kP * err + self.kI * self.i_acc + self.kD * d + arb_ff_duty
        want = max(-1.0, min(1.0, want))
        if self.ramp_s > 0:
            max_step = 0.001 / self.ramp_s
            want = max(self.out - max_step, min(self.out + max_step, want))
        self.out = want
        return want


# ---------------------------------------------------------------------------- steering


class SteeringModule:
    """A MAXSwerve-like steering axis: NEO 550, 46.42:1, through-bore on the output."""

    def __init__(self, surface="blocks", gear=46.42, backlash_deg=0.8, current_limit=20.0,
                 seed=1):
        self.motor = Motor("neo550")
        self.gear = gear
        self.surface = surface
        self.backlash = backlash_deg
        self.current_limit = current_limit
        out_inertia = 0.004  # kg m^2 about the steering axis
        self.J = 1.0e-6 + out_inertia / gear ** 2
        # Friction at the output, N*m: carpet scrub is the big one.
        self.coulomb_out = 1.2 if surface == "floor" else 0.04
        self.viscous_out = 0.02 if surface == "floor" else 0.005
        self.motor_deg = 0.0  # motor angle expressed in output degrees
        self.out_deg = 0.0
        self.w = 0.0  # motor rad/s
        self.rng = random.Random(seed)

    def physics(self, volts, dt):
        volts = self.motor.limit_volts(volts, self.w, self.current_limit)
        i = self.motor.current(volts, self.w)
        torque = self.motor.Kt * i
        out_w = self.w / self.gear  # rad/s at output
        engaged = abs(self.motor_deg - self.out_deg) >= self.backlash / 2 - 1e-9
        load = 0.0
        if engaged:
            fric = self.coulomb_out * (1 if out_w > 0 else -1 if out_w < 0 else 0)
            load = (fric + self.viscous_out * out_w) / self.gear
            if abs(out_w) < 1e-4 and abs(torque) < self.coulomb_out / self.gear:
                torque = 0.0  # stiction holds it
                self.w = 0.0
        self.w += (torque - load) / self.J * dt
        self.motor_deg += math.degrees(self.w / self.gear) * dt
        gap = self.motor_deg - self.out_deg
        half = self.backlash / 2
        if gap > half:
            self.out_deg = self.motor_deg - half
        elif gap < -half:
            self.out_deg = self.motor_deg + half
        return volts, abs(i)

    def absolute_reading(self):
        return round(self.out_deg / (360 / 1024)) * (360 / 1024)  # 10-bit duty-cycle encoder

    def motor_reading(self):
        counts_per_out_deg = 42 * self.gear / 360
        return round(self.motor_deg * counts_per_out_deg) / counts_per_out_deg


def steer_step(targets, hold_s=0.6, settle_s=0.5, kP=0.01, kI=0.0, kD=0.0, i_zone=0.0,
               ramp_s=0.0, feedback="motor", surface="blocks", rate_hz=200, bus=12.0, seed=1):
    """Same shape of result as the robot's steer_step: one module, as ``m0``."""
    mod = SteeringModule(surface=surface, seed=seed)
    pid = SparkPid(kP, kI, kD, i_zone, ramp_s, wrap=360.0)
    dt = 0.0002
    t = 0.0
    total = settle_s + hold_s * len(targets)
    out = {k: [] for k in ("t", "m0.sp", "m0.steer", "m0.motor", "m0.volts", "m0.amps", "vbus")}
    next_sample = 0.0
    next_ctrl = 0.0
    duty = 0.0
    volts_applied, amps = 0.0, 0.0
    while t <= total:
        seg = 0 if t < settle_s else 1 + int((t - settle_s) / hold_s)
        sp = 0.0 if seg == 0 else targets[min(seg - 1, len(targets) - 1)]
        if t >= next_ctrl:
            meas = mod.absolute_reading() if feedback == "absolute" else mod.motor_reading()
            duty = pid.step(sp, meas)
            next_ctrl += 0.001
        volts_applied, amps = mod.physics(duty * bus, dt)
        if t >= next_sample:
            out["t"].append(t)
            out["m0.sp"].append(sp)
            out["m0.steer"].append(mod.absolute_reading())
            out["m0.motor"].append(mod.motor_reading())
            out["m0.volts"].append(volts_applied)
            out["m0.amps"].append(amps)
            out["vbus"].append(bus)
            next_sample += 1.0 / rate_hz
        t += dt
    return out


# ---------------------------------------------------------------------------- drive


class DriveModule:
    """A NEO on 5.50:1 to a 3 inch wheel, carrying a quarter of the robot or nothing."""

    COUNTS_PER_REV = 42

    def __init__(self, surface="floor", robot_mass_kg=55.0, gear=5.5, wheel_d_in=3.0,
                 current_limit=40.0, kS_volts=0.15, meas_period_ms=32, meas_depth=8, mu=1.1,
                 seed=1):
        self.motor = Motor("neo")
        self.gear = gear
        self.r = wheel_d_in * 0.0254 / 2
        self.surface = surface
        self.current_limit = current_limit
        self.kS_torque = kS_volts / self.motor.R * self.motor.Kt  # friction as a motor torque
        rotor = 3.0e-5
        if surface == "floor":
            self.J = rotor + (robot_mass_kg / 4) * self.r ** 2 / gear ** 2
            self.traction_force = mu * robot_mass_kg * 9.81 / 4
        else:
            self.J = rotor + 1.1e-4 / gear ** 2
            self.traction_force = float("inf")
        self.w = 0.0
        self.motor_rev = 0.0
        self.meas = 0.0
        self.meas_period_ms = max(1, int(meas_period_ms))
        self.meas_depth = max(1, int(meas_depth))
        self._counts = []
        self._raw = []
        self.slipping = False
        self.rng = random.Random(seed)

    def measure_tick(self):
        """Once per millisecond: what the SPARK's velocity reading is now, in m/s."""
        self._counts.append(math.floor(self.motor_rev * self.COUNTS_PER_REV))
        if len(self._counts) > self.meas_period_ms + 1:
            self._counts.pop(0)
        span = len(self._counts) - 1
        if span <= 0:
            return self.meas
        counts_per_s = (self._counts[-1] - self._counts[0]) / (span / 1000.0)
        rev_per_s = counts_per_s / self.COUNTS_PER_REV
        self._raw.append(rev_per_s / self.gear * 2 * math.pi * self.r)
        if len(self._raw) > self.meas_depth:
            self._raw.pop(0)
        self.meas = sum(self._raw) / len(self._raw)
        return self.meas

    def speed(self):
        return self.w / self.gear * self.r

    def physics(self, volts, dt):
        volts = self.motor.limit_volts(volts, self.w, self.current_limit)
        i = self.motor.current(volts, self.w)
        torque = self.motor.Kt * i
        if abs(self.w) < 1e-3 and abs(torque) < self.kS_torque:
            self.w = 0.0
            torque = 0.0
            fric = 0.0
        else:
            fric = self.kS_torque * (1 if self.w > 0 else -1)
        # Traction: the wheel cannot push the robot harder than the carpet allows.
        wheel_force = (torque - fric) * self.gear / self.r
        self.slipping = abs(wheel_force) > self.traction_force
        if self.slipping:
            # The carpet only passes on so much force; the robot accelerates at that, no faster.
            net = math.copysign(self.traction_force * self.r / self.gear, wheel_force)
            self.w += net / self.J * dt
        else:
            self.w += (torque - fric) / self.J * dt
        self.motor_rev += self.w / (2 * math.pi) * dt
        return volts, abs(i)


def _ff_volts(v_sp, v_prev_sp, ff):
    kS, kV, kA = ff
    s = (v_sp > 0) - (v_sp < 0)
    return kS * s + kV * v_sp + kA * (v_sp - v_prev_sp) / 0.02


def drive_step(speeds, hold_s=0.8, align_s=0.6, kP=0.002, kI=0.0, kD=0.0, ramp_s=0.0,
               ff=(0.0, 2.915, 0.0), surface="floor", meas_period_ms=32, meas_depth=8,
               rate_hz=100, bus=12.0, modules=4, seed=1):
    """Same shape of result as the robot's drive_step, with module-to-module variation."""
    rng = random.Random(seed)
    mods = [DriveModule(surface=surface, meas_period_ms=meas_period_ms, meas_depth=meas_depth,
                        kS_volts=0.15 * (1 + 0.15 * (rng.random() - 0.5)), seed=seed + i)
            for i in range(modules)]
    pids = [SparkPid(kP, kI, kD, 0.0, ramp_s) for _ in mods]
    dt = 0.0002
    total = align_s + hold_s * len(speeds)
    keys = ["t", "sp"] + [f"m{i}.{k}" for i in range(modules) for k in ("v", "spm", "volts", "amps", "steer")]
    out = {k: [] for k in keys + ["heading", "x", "y", "vbus"]}
    t, next_sample, next_ctrl, next_loop = 0.0, 0.0, 0.0, 0.0
    v_sp, v_prev, ff_v = 0.0, 0.0, 0.0
    duties = [0.0] * modules
    applied = [(0.0, 0.0)] * modules
    x = 0.0
    while t <= total:
        if t >= next_loop:  # the 50 Hz robot loop recomputes the setpoint and feedforward
            seg = 0 if t < align_s else 1 + int((t - align_s) / hold_s)
            v_prev = v_sp
            v_sp = 0.0 if seg == 0 else speeds[min(seg - 1, len(speeds) - 1)]
            ff_v = _ff_volts(v_sp, v_prev, ff)
            next_loop += 0.02
        if t >= next_ctrl:
            for i, (m, p) in enumerate(zip(mods, pids)):
                duties[i] = p.step(v_sp, m.measure_tick(), ff_v / bus)
            next_ctrl += 0.001
        for i, m in enumerate(mods):
            applied[i] = m.physics(duties[i] * bus, dt)
        if surface == "floor":
            x += sum(m.speed() for m in mods) / modules * dt
        if t >= next_sample:
            out["t"].append(t)
            out["sp"].append(v_sp)
            for i, m in enumerate(mods):
                out[f"m{i}.v"].append(m.meas)
                out[f"m{i}.spm"].append(v_sp)
                out[f"m{i}.volts"].append(applied[i][0])
                out[f"m{i}.amps"].append(applied[i][1])
                out[f"m{i}.steer"].append(0.0)
            out["heading"].append(0.0)
            out["x"].append(x)
            out["y"].append(0.0)
            out["vbus"].append(bus)
            next_sample += 1.0 / rate_hz
        t += dt
    return out


def drive_ff(ramp_vps=1.0, max_v=6.0, step_v=4.0, quasi_s=None, dyn_s=1.0, rest_s=1.0,
             surface="floor", meas_period_ms=16, meas_depth=2, rate_hz=100, bus=12.0, modules=4,
             seed=1):
    """Same shape as the robot's drive_ff: open-loop voltage ramps and steps."""
    rng = random.Random(seed)
    mods = [DriveModule(surface=surface, meas_period_ms=meas_period_ms, meas_depth=meas_depth,
                        kS_volts=0.15 * (1 + 0.15 * (rng.random() - 0.5)), seed=seed + i)
            for i in range(modules)]
    quasi_s = quasi_s or max_v / ramp_vps
    plan = [(0, 0.6), (1, quasi_s), (5, rest_s), (2, quasi_s), (5, rest_s), (3, dyn_s), (5, rest_s),
            (4, dyn_s), (5, rest_s)]
    dt = 0.0002
    keys = ["t", "phase", "cmd"] + [f"m{i}.{k}" for i in range(modules) for k in ("volts", "v", "pos", "amps")]
    out = {k: [] for k in keys + ["heading", "x", "y", "vbus"]}
    t, next_sample, next_tick = 0.0, 0.0, 0.0
    pos = [0.0] * modules
    for phase, dur in plan:
        start = t
        while t < start + dur:
            into = t - start
            cmd = {1: min(ramp_vps * into, max_v), 2: -min(ramp_vps * into, max_v),
                   3: step_v, 4: -step_v}.get(phase, 0.0)
            app = [m.physics(cmd, dt) for m in mods]
            if t >= next_tick:
                for m in mods:
                    m.measure_tick()
                next_tick += 0.001
            for i, m in enumerate(mods):
                pos[i] += m.speed() * dt
            if t >= next_sample:
                out["t"].append(t)
                out["phase"].append(phase)
                out["cmd"].append(cmd)
                for i, m in enumerate(mods):
                    out[f"m{i}.volts"].append(app[i][0])
                    out[f"m{i}.v"].append(m.meas)
                    out[f"m{i}.pos"].append(pos[i])
                    out[f"m{i}.amps"].append(app[i][1])
                out["heading"].append(0.0)
                out["x"].append(mean_pos(pos))
                out["y"].append(0.0)
                out["vbus"].append(bus)
                next_sample += 1.0 / rate_hz
            t += dt
    return out


def mean_pos(p):
    return sum(p) / len(p)


def true_drive_feedforward(surface="floor", robot_mass_kg=55.0, kS_volts=0.15):
    """What kS, kV and kA really are for the model, to check a fit against."""
    m = DriveModule(surface=surface, robot_mass_kg=robot_mass_kg, kS_volts=kS_volts)
    kV = m.gear / m.r / m.motor.Kv  # back-EMF volts per (m/s)
    # torque per volt at stall-free current: Kt / R; force per volt = Kt/R * G / r
    force_per_volt = m.motor.Kt / m.motor.R * m.gear / m.r
    mass_equiv = m.J * (m.gear / m.r) ** 2
    kA = mass_equiv / force_per_volt
    return {"kS": kS_volts, "kV": kV, "kA": kA}


# ---------------------------------------------------------------------------- wall push


def wall_loads(robot_mass_kg=55.0, front_share=0.46, seed=1):
    """Normal force on each wheel, newtons: front pair, then back pair, a little uneven."""
    rng = random.Random(seed)
    g = 9.81
    shares = [front_share / 2, front_share / 2, (1 - front_share) / 2, (1 - front_share) / 2]
    return [robot_mass_kg * g * s * (1 + 0.04 * (rng.random() - 0.5)) for s in shares]


def true_slip_currents(robot_mass_kg=55.0, mu_static=1.1, front_share=0.46, gear=5.5,
                       wheel_d_in=3.0, seed=1):
    """The current at which each modeled wheel breaks loose, to check an analysis against."""
    motor = Motor("neo")
    r = wheel_d_in * 0.0254 / 2
    return [mu_static * n * r / (gear * motor.Kt) + motor.free_i
            for n in wall_loads(robot_mass_kg, front_share, seed)]


def wall_push(robot_mass_kg=55.0, mu_static=1.1, mu_kinetic=0.85, front_share=0.46, gear=5.5,
              wheel_d_in=3.0, ceiling_a=60.0, ramp_vps=1.0, slip_mps=0.15, limit_before_a=40.0,
              rate_hz=200, bus=12.0, seed=1):
    """Same shape as the robot's slip test: four modules, a bumper against a wall.

    Returns ``(channels, meta)``. Each wheel is stalled until its push beats static friction, then
    spins against kinetic friction; it is cut, as on the robot, once its speed stays above
    ``slip_mps`` for two 20 ms loops.
    """
    motor = Motor("neo")
    r = wheel_d_in * 0.0254 / 2
    loads = wall_loads(robot_mass_kg, front_share, seed)
    J = 3.0e-5 + 1.1e-4 / gear ** 2
    fric = motor.Kt * motor.free_i  # internal friction torque at the motor
    n = len(loads)
    w = [0.0] * n
    slipping = [False] * n
    cut = [False] * n
    fast = [0] * n
    hist = [[] for _ in range(n)]
    pos = [0.0] * n
    meas = [0.0] * n
    align, dt = 0.8, 0.0005
    total = align + 12.0 / ramp_vps + 1
    keys = ["t", "phase", "cmd"] + [f"m{i}.{k}" for i in range(n) for k in ("volts", "amps", "v", "pos")]
    out = {k: [] for k in keys + ["heading", "x", "y", "ax", "ay", "vbus"]}
    t, next_sample, next_loop, next_ms = 0.0, 0.0, 0.0, 0.0
    applied, amps = [0.0] * n, [0.0] * n
    peak = [0.0] * n
    slip_a = [float("nan")] * n
    done_at = None
    while t <= total and (done_at is None or t < done_at + 0.3):
        cmd = 0.0 if t < align else min(12.0, ramp_vps * (t - align))
        for i in range(n):
            v_cmd = 0.0 if cut[i] else cmd
            vlt = motor.limit_volts(v_cmd, w[i], ceiling_a)
            cur = motor.current(vlt, w[i])
            torque = motor.Kt * cur
            if not slipping[i]:
                if (torque - fric) * gear / r >= mu_static * loads[i]:
                    slipping[i] = True
                else:
                    w[i] = 0.0
            if slipping[i]:
                load = mu_kinetic * loads[i] * r / gear + fric
                w[i] += (torque - load) / J * dt
                if w[i] < 0:
                    w[i] = 0.0
            pos[i] += w[i] / gear * r * dt
            applied[i], amps[i] = vlt, abs(cur)
        if t >= next_ms:  # the SPARK's speed reading: the last 16 ms of travel
            for i in range(n):
                hist[i].append(pos[i])
                if len(hist[i]) > 17:
                    hist[i].pop(0)
                meas[i] = (hist[i][-1] - hist[i][0]) / ((len(hist[i]) - 1) / 1000.0) if len(hist[i]) > 1 else 0.0
            next_ms += 0.001
        if t >= next_loop:  # the 50 Hz robot loop, as SlipProcedure does it
            for i in range(n):
                if cut[i]:
                    continue
                peak[i] = max(peak[i], amps[i])
                fast[i] = fast[i] + 1 if abs(meas[i]) > slip_mps else 0
                if fast[i] >= 2:
                    cut[i] = True
                    slip_a[i] = peak[i]
            if done_at is None and all(cut):
                done_at = t
            next_loop += 0.02
        if t >= next_sample:
            out["t"].append(t)
            out["phase"].append(0 if t < align else 1)
            out["cmd"].append(cmd)
            for i in range(n):
                out[f"m{i}.volts"].append(applied[i])
                out[f"m{i}.amps"].append(amps[i])
                out[f"m{i}.v"].append(meas[i])
                out[f"m{i}.pos"].append(pos[i])
            for k in ("heading", "x", "y", "ax", "ay"):
                out[k].append(0.0)
            out["vbus"].append(bus)
            next_sample += 1.0 / rate_hz
        t += dt
    meta = {"ceiling_a": ceiling_a, "policy_a": ceiling_a, "limit_before_a": limit_before_a,
            "ramp_vps": ramp_vps, "slip_mps": slip_mps, "direction": 1, "wall_lost": 0,
            "min_plausible_slip_a": 8.0}
    for i in range(n):
        meta[f"slip_a_m{i}"] = slip_a[i]
        meta[f"peak_a_m{i}"] = peak[i]
    return out, meta


def pdh_pulses(names, ports, volts=4.0, quiet_s=0.6, pulse_s=0.8, rate_hz=50, noise_a=0.06,
               background=None, seed=3):
    """A ``pdh_map`` run on blocks: ``(channels, notes, meta)``.

    ``names`` are the pulsed motors in order (drive, steer, drive, steer...), ``ports`` their true
    PDH ports (None for a motor fed from somewhere else). Battery-side current: a start-up spike
    that settles to a steady draw, about duty x motor current. ``background`` is ``{port: amps}``
    drawn all the time (a radio, a compressor). The PDH snapshot lags the command by one sample, as
    on the robot. Readings are rounded to the PDH's 1/16 A steps.
    """
    rng = random.Random(seed)
    dt = 1.0 / rate_hz
    t_total = len(names) * (quiet_s + pulse_s)
    ch = {"t": [], "slot": [], "on": []}
    for p in range(24):
        ch[f"pdh{p}"] = []
    prev = [0.0] * 24
    t = 0.0
    while t < t_total:
        k = int(t / (quiet_s + pulse_s))
        into = t - k * (quiet_s + pulse_s) - quiet_s
        on = into >= 0
        now = [0.05 + (background or {}).get(p, 0.0) for p in range(24)]
        if on and ports[k] is not None:
            steer = names[k].endswith("steer")
            steady = (0.35 if steer else 0.6) * volts / 4.0 * (1 + 0.2 * rng.random())
            spike = (2.0 if steer else 4.0) * volts / 4.0 * math.exp(-into / 0.08)
            now[ports[k]] += steady + spike
        ch["t"].append(round(t, 6))
        ch["slot"].append(float(k))
        ch["on"].append(1.0 if on else 0.0)
        for p in range(24):
            ch[f"pdh{p}"].append(round(max(0.0, prev[p] + rng.gauss(0, noise_a)) * 16) / 16)
        prev = now
        t += dt
    notes = [f"pulse {k}: {n}" for k, n in enumerate(names)]
    meta = {"pulse_volts": volts, "quiet_s": quiet_s, "pulse_s": pulse_s, "pdh_channels": 24.0}
    return ch, notes, meta


def coast_push(tape_m=3.0, real_in=(4.0, 4.0, 4.0, 4.0), configured_in=4.0, angles_deg=(0, 0, 0, 0),
               curve_deg=0.0, push_s=4.0, rate_hz=50, seed=4):
    """A capture run of the robot pushed straight in coast: channels like the robot records.

    Every wheel rolls over the same ground; its encoder counts that distance (times the cosine of
    its angle) scaled by configured/real diameter, so worn tread reads long.
    """
    rng = random.Random(seed)
    dt = 1.0 / rate_hz
    n = len(real_in)
    ch = {"t": [], "heading": []}
    for i in range(n):
        ch[f"m{i}.pos"], ch[f"m{i}.steer"], ch[f"m{i}.v"] = [], [], []
    t, total = 0.0, push_s + 1.0
    while t <= total:
        u = min(1.0, max(0.0, (t - 0.5) / push_s))
        s = tape_m * (3 * u * u - 2 * u ** 3)           # a smooth start and stop
        v = tape_m * 6 * u * (1 - u) / push_s if 0 < u < 1 else 0.0
        ch["t"].append(round(t, 6))
        ch["heading"].append(curve_deg * u + rng.gauss(0, 0.05))
        for i in range(n):
            k = configured_in / real_in[i] * math.cos(math.radians(angles_deg[i]))
            ch[f"m{i}.pos"].append(s * k + rng.gauss(0, 0.0005))
            ch[f"m{i}.steer"].append(angles_deg[i] + rng.gauss(0, 0.3))
            ch[f"m{i}.v"].append(v * k)
        t += dt
    return ch
