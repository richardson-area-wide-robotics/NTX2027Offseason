package frc.lib.slothtune;

import java.util.Locale;

/**
 * Homing a position mechanism that reads a relative encoder: the robot disabled, a person holds it
 * still at one of its ends and says which. Its encoder started wherever it was when the robot was
 * turned on, so its saved limits (slothtune.json) may sit somewhere else; the difference between
 * where it reads now and where that end was saved moves the limits into this boot's readings. The
 * encoder and the team's own code are left alone. Until a mechanism is homed (or its limits are
 * moved by hand this boot, or it declares an absolute sensor), no test moves it.
 *
 * <p>Args {@code system}: the system's index in the robot's list; {@code end}: 0 at its lower
 * limit, 1 at its upper. Reads for {@link #HOLD_S}; stops if the robot is enabled meanwhile or the
 * mechanism moves. Channel {@code pos}; meta {@code shift}, {@code min}, {@code max}.
 */
final class SystemHomeProcedure implements Procedure {
  /** How long it is read, held still. */
  static final double HOLD_S = 0.5;
  /** Moving more than this share of its range while held still is someone still moving it. */
  static final double STILL_FRACTION = 0.01;
  private TunableSystem sys;
  private boolean atMax;
  private double sum;
  private int count;
  private double lo = Double.NaN;
  private double hi = Double.NaN;
  private boolean lost;

  @Override
  public String name() {
    return "system_home";
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

  @Override
  public String validate(TestContext ctx) {
    TunableSystem s = SystemLimitsProcedure.pick(ctx);
    if (s == null) {
      return "No such system: the code registers none at that number.";
    }
    if (!s.kind.positional) {
      return "Only a pivot or an elevator is homed; " + s.name + " spins freely.";
    }
    if (!s.hasLimits()) {
      return s.name + " has no saved limits to home to: set its limits by hand instead (Systems tab, Limits).";
    }
    if (ctx.enabled.getAsBoolean()) {
      return "Disable the robot first: someone is holding " + s.name + " at its end by hand.";
    }
    if (!Double.isFinite(s.position.getAsDouble())) {
      return s.name + " has no position reading: check its sensor and its cable first.";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return HOLD_S + 3;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return 50;
  }

  @Override
  public void start(TestContext ctx) {
    sys = SystemLimitsProcedure.pick(ctx);
    atMax = ctx.args.get("end", 0, 0, 1) >= 0.5;
    sum = 0;
    count = 0;
    lo = Double.NaN;
    hi = Double.NaN;
    lost = false;
    ctx.sampler.channel("pos", () -> sys.position.getAsDouble());
    ctx.note("system: " + sys.name + " (" + sys.kind + ", " + sys.units + "), held at its " + endName());
  }

  private String endName() {
    return atMax ? "upper end" : "lower end";
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    double p = sys.position.getAsDouble();
    if (!Double.isFinite(p)) {
      lost = true;
      return false;
    }
    sum += p;
    count++;
    lo = Double.isNaN(lo) ? p : Math.min(lo, p);
    hi = Double.isNaN(hi) ? p : Math.max(hi, p);
    return t >= HOLD_S;
  }

  @Override
  public String abortReason(TestContext ctx) {
    if (ctx.enabled.getAsBoolean()) {
      return "The robot was enabled while " + sys.name + " was held by hand: stopped, and it isn't homed. Disable "
          + "the robot and home it again.";
    }
    if (lost) {
      return sys.name + "'s position reading stopped: it isn't homed. Check its sensor and its cable.";
    }
    if (Double.isFinite(lo) && hi - lo > STILL_FRACTION * (sys.max - sys.min)) {
      return String.format(Locale.ROOT, "%s moved %.3f %s while it was read: hold it still at its %s and home it "
          + "again.", sys.name, sys.shown(hi - lo), sys.shownUnits(), endName());
    }
    return null;
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    return String.format(Locale.ROOT, "%s reads %.3f %s: hold it still at its %s.", sys.name,
        sys.shown(sys.position.getAsDouble()), sys.shownUnits(), endName());
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    if (aborted || count == 0) {
      return;
    }
    double reading = sum / count;
    double range = sys.max - sys.min;
    double before = sys.homeShift;
    sys.home(atMax, reading);
    double shift = sys.homeShift - before;
    ctx.meta("shift", shift);
    ctx.meta("min", sys.min);
    ctx.meta("max", sys.max);
    ctx.note(String.format(Locale.ROOT, "%s homed at its %s: its limits moved %.4f %s, now %.4f to %.4f %s for this "
        + "boot", sys.name, endName(), sys.shown(shift), sys.shownUnits(), sys.shown(sys.min), sys.shown(sys.max),
        sys.shownUnits()));
    if (Math.abs(shift) > range) {
      ctx.note(String.format(Locale.ROOT, "That is more than its whole range (%.4f %s): if it wasn't really at its "
          + "%s, set its limits by hand instead.", sys.shown(range), sys.shownUnits(), endName()));
    }
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return Math.min(1.0, t / HOLD_S);
  }

  @Override
  public void requestStop() {}
}
