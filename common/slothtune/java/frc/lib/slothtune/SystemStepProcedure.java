package frc.lib.slothtune;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * A mechanism's closed loop, tested through the team's own code: goals set one after another, and
 * what the mechanism did recorded. Never a jump: every goal is reached along a path limited to a
 * maximum speed and acceleration (the laptop works them out from the mechanism's physics, e.g.
 * its ReCalc numbers, and slothtune.json's limits cap them), so the team's loop follows a
 * moving goal at a safe pace.
 *
 * <p>A pivot or elevator: from where it is to goal {@code a}, then {@code a} to {@code b} and back,
 * {@code moves} times, holding {@code hold_s} at each. It refuses without limits, keeps every goal
 * inside them with a margin, and stops at once if the mechanism leaves them or goes faster than
 * the test allows. A flywheel: up to speed {@code a}, then {@code b}, then back down, holding at each.
 *
 * <p>Args: {@code system} (index), {@code a}, {@code b}, {@code vmax}, {@code amax}, {@code hold_s},
 * {@code moves}. Channels: {@code pos}, {@code vel}, {@code sp} (the moving goal), {@code sp_vel},
 * {@code goal} (where it is headed), and {@code amps0..}, {@code volts0..} for its motors.
 */
final class SystemStepProcedure implements Procedure {
  /** Goals stay this far inside the limits, as a fraction of the range. */
  static final double MARGIN = 0.05;
  /** Past the limits by this much of the range, it stops. */
  static final double OVERRUN = 0.03;
  /** Faster than this times the allowed speed, it stops. */
  static final double SPEED_STOP = 1.5;

  private TunableSystem sys;
  private final List<double[]> legs = new ArrayList<>();
  private double vmax;
  private double amax;
  private double holdS;
  private volatile double sp = Double.NaN;
  private volatile double spVel;
  private volatile double target = Double.NaN;
  private int leg;
  private double legStart;
  private double holdStart;
  private double legFrom;
  private boolean held;
  private DriveOwnership owner;

  @Override
  public String name() {
    return "system_step";
  }

  /** It commands motors: the deadman, enable and heartbeat rules apply. */
  @Override
  public boolean spinsWheels() {
    return true;
  }

  @Override
  public boolean movesChassis(TestContext ctx) {
    return false;
  }

  @Override
  public boolean allowedIn(TestEnvironment env) {
    return env == TestEnvironment.BLOCKS || env == TestEnvironment.FIELD || env == TestEnvironment.SIM;
  }

  /** The allowed speed: the laptop's, never above slothtune.json's. */
  static double cap(double asked, double configured) {
    if (!Double.isFinite(configured) || configured <= 0) {
      return asked;
    }
    return Math.min(asked, configured);
  }

  @Override
  public String validate(TestContext ctx) {
    TunableSystem s = SystemLimitsProcedure.pick(ctx);
    if (s == null) {
      return "No such system: the code registers none at that number.";
    }
    if (s.goal == null) {
      return "The code doesn't give " + s.name + " a goal to set: add .goal(...) where it registers it.";
    }
    double v = cap(ctx.args.get("vmax", 0, 0, 1e6), s.maxVelocity);
    double a = cap(ctx.args.get("amax", 0, 0, 1e7), s.maxAccel);
    if (!(v > 0) || !(a > 0)) {
      return "Give the test a maximum speed and acceleration: the Systems tab works them out from the mechanism's physics.";
    }
    if (s.kind.positional && !s.hasLimits()) {
      return "Set the limits of " + s.name + " first: move it by hand to both ends (Systems tab, Limits).";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return 60;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return 100;
  }

  @Override
  public double expectedTopSpeedMps(TestContext ctx) {
    return 0;  // the wheels never turn; the drivetrain's overspeed stop has nothing to watch
  }

  @Override
  public void start(TestContext ctx) {
    sys = SystemLimitsProcedure.pick(ctx);
    vmax = cap(ctx.args.get("vmax", 0, 0, 1e6), sys.maxVelocity);
    amax = cap(ctx.args.get("amax", 0, 0, 1e7), sys.maxAccel);
    holdS = ctx.args.get("hold_s", 1.0, 0.2, 5);
    int moves = (int) Math.round(ctx.args.get("moves", 2, 1, 6));
    double a = ctx.args.get("a", 0, -1e9, 1e9);
    double b = ctx.args.get("b", 0, -1e9, 1e9);
    legs.clear();
    double now = sys.kind.positional ? sys.position.getAsDouble() : sys.velocity.getAsDouble();
    if (sys.kind.positional) {
      double range = sys.max - sys.min, lo = sys.min + MARGIN * range, hi = sys.max - MARGIN * range;
      a = Math.max(lo, Math.min(hi, a));
      b = Math.max(lo, Math.min(hi, b));
      legs.add(new double[] {a});
      for (int i = 0; i < moves; i++) {
        legs.add(new double[] {i % 2 == 0 ? b : a});
      }
    } else {
      // A flywheel's speeds never above the allowed top speed; up, up again, back down.
      legs.add(new double[] {Math.max(-vmax, Math.min(vmax, a))});
      legs.add(new double[] {Math.max(-vmax, Math.min(vmax, b))});
      legs.add(new double[] {0});
    }
    leg = 0;
    legStart = 0;
    legFrom = Double.isFinite(now) ? now : 0;
    target = legs.get(0)[0];
    sp = legFrom;
    spVel = 0;
    held = false;
    if (sys.subsystem != null) {
      owner = new DriveOwnership.CommandsV2(sys.subsystem);
      owner.acquire();
    }
    ctx.sampler.channel("pos", () -> sys.position.getAsDouble())
        .channel("vel", () -> sys.velocity.getAsDouble())
        .channel("sp", () -> sp)
        .channel("sp_vel", () -> spVel)
        .channel("goal", () -> target);
    int i = 0;
    for (MotorGuard.Motor m : ctx.motors) {
      if (sys.motors.contains(m.name)) {
        ctx.sampler.channel("amps" + i, m::amps).channel("volts" + i, m::appliedVolts);
        ctx.note("motor " + i + ": " + m.name);
        i++;
      }
    }
    ctx.note("system: " + sys.name + " (" + sys.kind + ", " + sys.units + ")");
    ctx.meta("vmax", vmax);
    ctx.meta("amax", amax);
    ctx.meta("hold_s", holdS);
    if (sys.kind.positional) {
      ctx.meta("min", sys.min);
      ctx.meta("max", sys.max);
    }
  }

  /**
   * Where a trapezoid-shaped move from {@code from} to {@code to} is after {@code t} seconds, never
   * faster than {@code vmax} nor speeding up faster than {@code amax}: {position, velocity, done}.
   */
  static double[] profile(double from, double to, double vmax, double amax, double t) {
    double d = Math.abs(to - from), dir = Math.signum(to - from);
    if (d == 0) {
      return new double[] {to, 0, 1};
    }
    double ta = vmax / amax;
    double peak = vmax;
    double tc;
    if (amax * ta * ta >= d) {  // never reaches top speed: a triangle
      ta = Math.sqrt(d / amax);
      peak = amax * ta;
      tc = 0;
    } else {
      tc = (d - amax * ta * ta) / vmax;
    }
    double total = 2 * ta + tc;
    if (t >= total) {
      return new double[] {to, 0, 1};
    }
    double p;
    double v;
    if (t < ta) {
      p = 0.5 * amax * t * t;
      v = amax * t;
    } else if (t < ta + tc) {
      p = 0.5 * amax * ta * ta + peak * (t - ta);
      v = peak;
    } else {
      double r = total - t;
      p = d - 0.5 * amax * r * r;
      v = amax * r;
    }
    return new double[] {from + dir * p, dir * v, 0};
  }

  /** A flywheel's speed goal, ramped at {@code rate} per second: {speed, rate, done}. */
  static double[] ramp(double from, double to, double rate, double t) {
    double d = to - from, step = rate * t;
    if (Math.abs(d) <= step) {
      return new double[] {to, 0, 1};
    }
    return new double[] {from + Math.signum(d) * step, Math.signum(d) * rate, 0};
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    if (!held) {
      // On the way: the goal moves along the limited path.
      double[] s = sys.kind.positional ? profile(legFrom, target, vmax, amax, t - legStart)
          : ramp(legFrom, target, amax, t - legStart);
      sp = s[0];
      spVel = s[1];
      sys.goal.accept(sp);
      if (s[2] == 1) {
        held = true;
        holdStart = t;
      }
      return false;
    }
    // There: hold, then the next goal.
    sp = target;
    spVel = 0;
    sys.goal.accept(sp);
    if (t - holdStart >= holdS) {
      leg++;
      if (leg >= legs.size()) {
        return true;
      }
      legFrom = target;
      target = legs.get(leg)[0];
      legStart = t;
      held = false;
    }
    return false;
  }

  @Override
  public String abortReason(TestContext ctx) {
    double v = sys.velocity.getAsDouble();
    if (sys.kind.positional) {
      double p = sys.position.getAsDouble(), range = sys.max - sys.min;
      if (Double.isFinite(p) && (p < sys.min - OVERRUN * range || p > sys.max + OVERRUN * range)) {
        return String.format(Locale.ROOT, "%s went past its limits (%.3f, limits %.3f to %.3f %s): stopped.",
            sys.name, p, sys.min, sys.max, sys.units);
      }
      if (Double.isFinite(v) && Math.abs(v) > SPEED_STOP * vmax) {
        return String.format(Locale.ROOT, "%s moved at %.3f %s/s, faster than the test allows (%.3f): stopped.",
            sys.name, Math.abs(v), sys.units, vmax);
      }
    } else {
      double top = Math.max(Math.abs(legs.get(0)[0]), Math.abs(legs.get(1)[0]));
      if (Double.isFinite(v) && Math.abs(v) > 1.25 * top + 0.05 * vmax) {
        return String.format(Locale.ROOT, "%s reached %.0f %s, above the test's top speed: stopped.", sys.name, Math.abs(v), sys.units);
      }
    }
    return null;
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    double now = sys.kind.positional ? sys.position.getAsDouble() : sys.velocity.getAsDouble();
    return String.format(Locale.ROOT, "%s: heading for %.3f, goal now %.3f, at %.3f %s.", sys.name, target, sp, now, sys.units);
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    try {
      if (sys.stop != null) {
        sys.stop.run();
      } else if (sys.kind.positional) {
        sys.goal.accept(sys.position.getAsDouble());  // hold where it is
      } else {
        sys.goal.accept(0);
      }
    } finally {
      if (owner != null) {
        owner.release();
      }
    }
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return legs.isEmpty() ? 0 : Math.min(1.0, (double) leg / legs.size());
  }
}
