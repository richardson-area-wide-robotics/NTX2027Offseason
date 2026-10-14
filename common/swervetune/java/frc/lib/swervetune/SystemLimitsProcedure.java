package frc.lib.swervetune;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * A position mechanism's limits, found by a person: the robot disabled, its motors coasting, they
 * move it by hand all the way one way and all the way the other. The lowest and highest positions
 * it read become its limits for this session (the laptop offers to save them to swervetune.json),
 * and no closed-loop test of it runs without them.
 *
 * <p>Arg {@code system}: the system's index in the robot's list. Ends when asked (the laptop's
 * Done) or after {@code duration_s}. Channels {@code pos}, {@code vel}; meta {@code min}, {@code max}.
 */
final class SystemLimitsProcedure implements Procedure {
  static final double MIN_RANGE_FRACTION = 1e-3;
  private volatile boolean stopRequested;
  private TunableSystem sys;
  private double lo = Double.NaN;
  private double hi = Double.NaN;
  private double durationS;
  private final List<Runnable> restore = new ArrayList<>();

  @Override
  public String name() {
    return "system_limits";
  }

  @Override
  public boolean spinsWheels() {
    return false;
  }

  @Override
  public boolean movesChassis(TestContext ctx) {
    return false;
  }

  @Override
  public boolean needsEnabled() {
    return false;
  }

  @Override
  public boolean allowedIn(TestEnvironment env) {
    return true;
  }

  static TunableSystem pick(TestContext ctx) {
    int i = (int) Math.round(ctx.args.get("system", -1, -1, 63));
    return i >= 0 && i < ctx.systems.size() ? ctx.systems.get(i) : null;
  }

  @Override
  public String validate(TestContext ctx) {
    TunableSystem s = pick(ctx);
    if (s == null) {
      return "No such system: the code registers none at that number.";
    }
    if (!s.kind.positional) {
      return "Only a pivot or an elevator has limits to find; " + s.name + " spins freely.";
    }
    if (ctx.enabled.getAsBoolean()) {
      return "Disable the robot first: someone is going to move " + s.name + " by hand.";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return ctx.args.get("duration_s", 120, 10, 300) + 2;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return 50;
  }

  @Override
  public void start(TestContext ctx) {
    stopRequested = false;
    sys = pick(ctx);
    durationS = ctx.args.get("duration_s", 120, 10, 300);
    lo = Double.NaN;
    hi = Double.NaN;
    restore.clear();
    // Coasting, so a person can move it: each motor goes back to how it was at the end.
    for (MotorGuard.Motor m : ctx.motors) {
      if (sys.motors.contains(m.name)) {
        Boolean was = m.channel.coast();
        if (m.channel.setCoast(true)) {
          boolean back = was == null ? false : was;
          restore.add(() -> m.channel.setCoast(back));
          ctx.note(m.name + " coasting while it is moved by hand");
        } else {
          ctx.note(m.name + " could not be set to coast: it may be stiff to move");
        }
      }
    }
    ctx.sampler.channel("pos", () -> track(sys.position.getAsDouble()))
        .channel("vel", () -> sys.velocity.getAsDouble());
    ctx.note("system: " + sys.name + " (" + sys.kind + ", " + sys.units + ")");
  }

  private double track(double p) {
    if (Double.isFinite(p)) {
      lo = Double.isNaN(lo) ? p : Math.min(lo, p);
      hi = Double.isNaN(hi) ? p : Math.max(hi, p);
    }
    return p;
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    track(sys.position.getAsDouble());
    return stopRequested || t >= durationS;
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    return String.format(Locale.ROOT, "%s now %.3f %s; lowest %.3f, highest %.3f. Move it all the way both ways.",
        sys.name, sys.position.getAsDouble(), sys.units, lo, hi);
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    restore.forEach(Runnable::run);
    if (Double.isFinite(lo) && Double.isFinite(hi)) {
      ctx.meta("min", lo);
      ctx.meta("max", hi);
      // A range of nothing is a mechanism nobody moved, not a limit.
      double scale = Math.max(Math.abs(lo), Math.abs(hi));
      if (!aborted && hi - lo > MIN_RANGE_FRACTION * Math.max(1, scale)) {
        sys.setLimits(lo, hi, "moved by hand");
        ctx.note(String.format(Locale.ROOT, "%s limits for this session: %.4f to %.4f %s", sys.name, lo, hi, sys.units));
      }
    }
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return Math.min(1.0, t / Math.max(1, durationS));
  }

  @Override
  public void requestStop() {
    stopRequested = true;
  }
}
