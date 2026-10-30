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
 * the test allows, or if its position can't be read (lost, or frozen while its SPARK's own encoder
 * moves, as identification checks), since then its limits can't be kept. A flywheel: up to speed
 * {@code a}, then {@code b}, then back down, holding at each. Either stops if it pushes hard without
 * moving: jammed.
 *
 * <p>Args: {@code system} (index), {@code a}, {@code b}, {@code vmax}, {@code amax}, {@code hold_s},
 * {@code moves}, {@code stop_amps}. Channels: {@code pos}, {@code vel}, {@code sp} (the moving goal),
 * {@code sp_vel}, {@code goal} (where it is headed), and {@code amps0..}, {@code volts0..} for its motors.
 */
final class SystemStepProcedure implements Procedure {
  /** Goals stay this far inside the limits, as a fraction of the range. */
  static final double MARGIN = 0.05;
  /** Past the limits by this much of the range, it stops. */
  static final double OVERRUN = 0.03;
  /** Faster than this times the allowed speed, it stops. */
  static final double SPEED_STOP = 1.5;
  /** Pushing hard: a motor over {@code stop_amps}, or over this fraction of its own current limit if less. */
  static final double JAM_LIMIT_FRACTION = 0.85;
  /** A pivot or elevator pushing hard that moves less than this of its range, its goal farther: jammed. */
  static final double JAM_TRAVEL = 0.01;

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
  /** Its motors the motor guard watches; the first that leads is the SPARK the frozen check reads. */
  private final List<MotorGuard.Motor> mine = new ArrayList<>();
  private MotorGuard.MotorChannel spark;
  private final SystemIdProcedure.FrozenReading frozen = new SystemIdProcedure.FrozenReading();
  private double stopAmps;
  /** When it began pushing hard without moving, and where it was then (a flywheel: its speed). */
  private double jamSince = Double.NaN;
  private double jamFrom = Double.NaN;
  private String cut;

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
    String notReady = s.notReady();  // limits, then homed this boot
    if (notReady != null) {
      return notReady;
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
    stopAmps = ctx.args.get("stop_amps", 40, 10, 80);
    cut = null;
    jamSince = Double.NaN;
    frozen.reset();
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
    mine.clear();
    spark = null;
    for (MotorGuard.Motor m : ctx.motors) {
      if (sys.motors.contains(m.name)) {
        mine.add(m);
        if (spark == null && !m.channel.follower()) {
          spark = m.channel;
        }
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
    watch(t);
    if (cut != null) {
      return false;  // stopping: the goal stays where it was until the test ends
    }
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

  /**
   * The checks that need the time, each loop: a position reading frozen while its SPARK's own encoder
   * moves (identification's {@link SystemIdProcedure.FrozenReading}), and a jam: a motor pushing hard
   * for {@link SystemIdProcedure#STALL_S} while a pivot or elevator moves under {@link #JAM_TRAVEL} of
   * its range with its goal farther than that, or a flywheel stays under 2% of the allowed speed.
   */
  private void watch(double t) {
    if (cut != null) {
      return;
    }
    double x;
    boolean still;
    boolean away;
    if (sys.kind.positional) {
      x = sys.position.getAsDouble();
      if (!Double.isFinite(x)) {
        return;  // abortReason stops it
      }
      double range = sys.max - sys.min;
      cut = frozen.check(sys, range, t, x, spark == null ? Double.NaN : spark.feedbackPosition());
      still = Double.isNaN(jamSince) || Math.abs(x - jamFrom) <= JAM_TRAVEL * range;
      away = Math.abs(sp - x) > JAM_TRAVEL * range;
    } else {
      x = sys.velocity.getAsDouble();
      still = Math.abs(x) < 0.02 * vmax;  // false for NaN: without a speed it can't tell
      away = true;
    }
    double amps = 0;
    boolean hard = false;
    for (MotorGuard.Motor m : mine) {
      double a = m.channel.amps();
      if (Double.isFinite(a)) {
        int limit = m.baseLimitA();
        amps = Math.max(amps, a);
        hard |= a > (limit > 0 ? Math.min(stopAmps, JAM_LIMIT_FRACTION * limit) : stopAmps);
      }
    }
    if (!(hard && still && away)) {
      jamSince = Double.NaN;
    } else if (Double.isNaN(jamSince)) {
      jamSince = t;
      jamFrom = x;
    } else if (cut == null && t - jamSince >= SystemIdProcedure.STALL_S) {
      cut = String.format(Locale.ROOT, "%s didn't move with its motors at %.0f A: jammed, or something holds it. "
          + "Stopped.", sys.name, amps);
    }
  }

  @Override
  public String abortReason(TestContext ctx) {
    if (cut != null) {
      return cut;
    }
    double v = sys.velocity.getAsDouble();
    if (sys.kind.positional) {
      double p = sys.position.getAsDouble(), range = sys.max - sys.min;
      if (!Double.isFinite(p)) {
        return "It can't read " + sys.name + "'s position (its sensor, or that sensor's CAN messages, dropped out), "
            + "so it can't keep it inside its limits: stopped.";
      }
      if (p < sys.min - OVERRUN * range || p > sys.max + OVERRUN * range) {
        return String.format(Locale.ROOT, "%s went past its limits (%.3f, limits %.3f to %.3f %s): stopped.",
            sys.name, sys.shown(p), sys.shown(sys.min), sys.shown(sys.max), sys.shownUnits());
      }
      if (Double.isFinite(v) && Math.abs(v) > SPEED_STOP * vmax) {
        return String.format(Locale.ROOT, "%s moved at %.3f %s/s, faster than the test allows (%.3f): stopped.",
            sys.name, sys.shown(Math.abs(v)), sys.shownUnits(), sys.shown(vmax));
      }
    } else {
      double top = Math.max(Math.abs(legs.get(0)[0]), Math.abs(legs.get(1)[0]));
      if (Double.isFinite(v) && Math.abs(v) > 1.25 * top + 0.05 * vmax) {
        return String.format(Locale.ROOT, "%s reached %.0f %s, above the test's top speed: stopped.", sys.name,
            sys.shown(Math.abs(v)), sys.shownUnits());
      }
    }
    return null;
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    double now = sys.kind.positional ? sys.position.getAsDouble() : sys.velocity.getAsDouble();
    return String.format(Locale.ROOT, "%s: heading for %.3f, goal now %.3f, at %.3f %s.", sys.name, sys.shown(target),
        sys.shown(sp), sys.shown(now), sys.shownUnits());
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    try {
      stopSystem(ctx, sys);
    } finally {
      if (owner != null) {
        owner.release();
      }
    }
  }

  /**
   * Stops a mechanism the team's way: its {@code stop}, else its goal held where it is (a flywheel's
   * at 0). If that throws, its motors are set to zero output directly ({@link #zeroOutput}), so a
   * broken stop never leaves them running; what happened is noted, and the exception thrown on for the
   * harness to report too.
   */
  static void stopSystem(TestContext ctx, TunableSystem sys) {
    try {
      if (sys.stop != null) {
        sys.stop.run();
      } else if (sys.kind.positional) {
        sys.goal.accept(sys.position.getAsDouble());  // hold where it is
      } else {
        sys.goal.accept(0);
      }
    } catch (RuntimeException e) {
      List<MotorGuard.Motor> ms = new ArrayList<>();
      for (MotorGuard.Motor m : ctx.motors) {
        if (sys.motors.contains(m.name)) {
          ms.add(m);
        }
      }
      ctx.note(sys.name + "'s own stop raised " + e + ": " + zeroOutput(ms));
      throw e;
    }
  }

  /**
   * Zero output on each of {@code motors} that leads, outside the team's code, as bring-up runs a
   * motor (a follower follows its leader to zero; commanding it would take it out of follow mode).
   * Says what it did, for a note.
   */
  static String zeroOutput(List<MotorGuard.Motor> motors) {
    List<String> zeroed = new ArrayList<>();
    List<String> refused = new ArrayList<>();
    for (MotorGuard.Motor m : motors) {
      if (m.channel.follower()) {
        continue;
      }
      boolean ok;
      try {
        ok = m.channel.testDuty(0);
      } catch (RuntimeException e) {
        ok = false;
      }
      (ok ? zeroed : refused).add(m.name);
    }
    if (zeroed.isEmpty()) {
      return "the test couldn't set any of its motors to zero output: disable the robot.";
    }
    String did = String.join(", ", zeroed) + (zeroed.size() == 1 ? " was" : " were") + " set to zero output instead";
    return refused.isEmpty() ? did + "." : did + ", but " + String.join(", ", refused) + " couldn't be: disable the robot.";
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return legs.isEmpty() ? 0 : Math.min(1.0, (double) leg / legs.size());
  }
}
