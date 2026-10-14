package frc.lib.slothtune;

import java.util.Locale;

/**
 * Calibrates a {@link CurrentSensor} with a set number of game pieces, its motor's current
 * recorded throughout; the laptop works out the threshold from it.
 *
 * <p>A roller (an intake): it settles running empty, then for each piece it starts, waits out its
 * spin-up, and a person feeds the piece in when the banner says; then it stops so the piece can be
 * taken out safely. Every start's spin-up spike is in the record, so the threshold is set above it
 * and the time to ignore after a start is measured, not guessed.
 *
 * <p>An arm or an elevator: it sweeps slowly between its limits empty, then again with each piece
 * in turn, a person putting it in and taking it out while it holds at the bottom. The empty sweep
 * is the current it draws at each position with nothing in it; each loaded sweep, how much more a
 * piece adds there.
 *
 * <p>Args: {@code sensor} (index), {@code system} (index: what runs), {@code pieces} (1 to 10),
 * {@code goal} (a roller's speed, in its units), {@code vmax}, {@code amax} (an arm's sweep),
 * {@code settle_s}, {@code feed_s}, {@code clear_s}. Channels: {@code amps}, {@code duty},
 * {@code vel}, {@code pos}, {@code sp}, {@code detected}, {@code phase}: 0 settling, 100 the empty
 * sweep, k while piece k is fed (or swept), -k while it is put in or taken out.
 */
final class PieceSenseProcedure implements Procedure {
  /** A roller's first second after a start is spin-up: nobody feeds yet. */
  static final double SPIN_UP_S = 1.0;

  private CurrentSensor sensor;
  private TunableSystem sys;
  private DriveOwnership owner;
  private int pieces;
  private double settleS;
  private double feedS;
  private double clearS;
  private double goal;
  private double vmax;
  private double amax;
  private double lo;
  private double hi;
  private volatile double phase;
  private volatile double sp = Double.NaN;
  private String say = "";
  // An arm's plan: {phase, from, to, hold seconds} per leg; a leg with hold > 0 holds instead.
  private final java.util.List<double[]> legs = new java.util.ArrayList<>();
  private int leg;
  private double legStart;
  private double total;

  @Override
  public String name() {
    return "system_piece";
  }

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

  static CurrentSensor pickSensor(TestContext ctx) {
    int i = (int) Math.round(ctx.args.get("sensor", -1, -1, 63));
    return i >= 0 && i < ctx.currentSensors.size() ? ctx.currentSensors.get(i) : null;
  }

  @Override
  public String validate(TestContext ctx) {
    CurrentSensor s = pickSensor(ctx);
    if (s == null) {
      return "No such current sensor: the code registers none at that number.";
    }
    if (s.motor == null) {
      return s.name + " reads a motor the motor guard doesn't watch (" + s.motorName + "): watch it first.";
    }
    TunableSystem y = SystemLimitsProcedure.pick(ctx);
    if (y == null || y.goal == null) {
      return "Pick the mechanism that runs it, registered with a goal (Systems tab).";
    }
    if (y.kind.positional) {
      if (!y.hasLimits()) {
        return "Set the limits of " + y.name + " first (Systems tab, Limits).";
      }
      double v = SystemStepProcedure.cap(ctx.args.get("vmax", 0, 0, 1e6), y.maxVelocity);
      double a = SystemStepProcedure.cap(ctx.args.get("amax", 0, 0, 1e7), y.maxAccel);
      if (!(v > 0) || !(a > 0)) {
        return "Give the sweep a speed and acceleration: the Systems tab works them out.";
      }
    } else if (!(Math.abs(ctx.args.get("goal", 0, -1e9, 1e9)) > 0)) {
      return "Give the roller the speed it takes pieces in at.";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    int n = (int) Math.round(ctx.args.get("pieces", 3, 1, 10));
    return ctx.args.get("settle_s", 2, 1, 10) + n * (ctx.args.get("feed_s", 4, 2, 15) + ctx.args.get("clear_s", 3, 2, 15))
        + n * 30 + 40;
  }

  @Override
  public void start(TestContext ctx) {
    sensor = pickSensor(ctx);
    sys = SystemLimitsProcedure.pick(ctx);
    pieces = (int) Math.round(ctx.args.get("pieces", 3, 1, 10));
    settleS = ctx.args.get("settle_s", 2, 1, 10);
    feedS = ctx.args.get("feed_s", 4, 2, 15);
    clearS = ctx.args.get("clear_s", 3, 2, 15);
    goal = ctx.args.get("goal", 0, -1e9, 1e9);
    if (sys.subsystem != null) {
      owner = new DriveOwnership.CommandsV2(sys.subsystem);
      owner.acquire();
    }
    if (sys.kind.positional) {
      vmax = SystemStepProcedure.cap(ctx.args.get("vmax", 0, 0, 1e6), sys.maxVelocity);
      amax = SystemStepProcedure.cap(ctx.args.get("amax", 0, 0, 1e7), sys.maxAccel);
      double range = sys.max - sys.min;
      lo = sys.min + SystemStepProcedure.MARGIN * range;
      hi = sys.max - SystemStepProcedure.MARGIN * range;
      double here = sys.position.getAsDouble();
      legs.clear();
      legs.add(new double[] {0, Double.isFinite(here) ? here : lo, lo, 0});
      legs.add(new double[] {0, lo, lo, settleS});
      legs.add(new double[] {100, lo, hi, 0});
      legs.add(new double[] {100, hi, lo, 0});
      for (int k = 1; k <= pieces; k++) {
        legs.add(new double[] {-k, lo, lo, feedS});
        legs.add(new double[] {k, lo, hi, 0});
        legs.add(new double[] {k, hi, lo, 0});
        legs.add(new double[] {-k, lo, lo, clearS});
      }
      leg = 0;
      legStart = 0;
      sp = legs.get(0)[1];
      ctx.meta("vmax", vmax);
      ctx.meta("amax", amax);
      ctx.meta("min", sys.min);
      ctx.meta("max", sys.max);
    } else {
      total = settleS + pieces * (feedS + clearS);
    }
    ctx.sampler.channel("amps", () -> sensor.motor.amps())
        .channel("duty", () -> sensor.motor.duty)
        .channel("vel", () -> sys.velocity.getAsDouble())
        .channel("pos", () -> sys.position.getAsDouble())
        .channel("sp", () -> sp)
        .channel("detected", () -> sensor.detected() ? 1 : 0)
        .channel("phase", () -> phase);
    ctx.note("sensor: " + sensor.name + " (" + sensor.motorName + ", " + sensor.mode.key() + ")");
    ctx.note("system: " + sys.name + " (" + sys.kind + ", " + sys.units + ")");
    ctx.meta("pieces", pieces);
    ctx.meta("settle_s", settleS);
    ctx.meta("feed_s", feedS);
    ctx.meta("clear_s", clearS);
    ctx.meta("goal", goal);
    ctx.meta("spin_up_s", SPIN_UP_S);
    ctx.meta("threshold_a", sensor.thresholdA);
    ctx.meta("hold_s", sensor.holdS);
    ctx.meta("ignore_s", sensor.ignoreS);
    ctx.meta("positional", sys.kind.positional ? 1 : 0);
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    return sys.kind.positional ? sweep(t) : roll(t);
  }

  private boolean roll(double t) {
    if (t >= total) {
      return true;
    }
    if (t < settleS) {
      phase = 0;
      say = "Running empty: don't feed anything yet.";
      run(true);
      return false;
    }
    double c = (t - settleS) % (feedS + clearS);
    int k = 1 + (int) ((t - settleS) / (feedS + clearS));
    if (c < feedS) {
      phase = k;
      boolean spinning = c >= SPIN_UP_S;
      say = spinning ? String.format(Locale.ROOT, "Feed piece %d of %d now, the way the game does.", k, pieces)
          : String.format(Locale.ROOT, "Starting up: piece %d of %d next, wait...", k, pieces);
      run(true);
    } else {
      phase = -k;
      say = String.format(Locale.ROOT, "Stopped: take piece %d out.", k);
      run(false);
    }
    return false;
  }

  private void run(boolean on) {
    sp = on ? goal : 0;
    if (on) {
      sys.goal.accept(goal);
    } else if (sys.stop != null) {
      sys.stop.run();
    } else {
      sys.goal.accept(0);
    }
  }

  private boolean sweep(double t) {
    double[] l = legs.get(leg);
    phase = l[0];
    double el = t - legStart;
    boolean done;
    if (l[3] > 0) {
      sp = l[2];
      sys.goal.accept(sp);
      done = el >= l[3];
      int k = (int) Math.abs(l[0]);
      boolean loading = leg + 1 < legs.size() && legs.get(leg + 1)[0] == k;
      say = l[0] == 0 ? "Holding empty." : loading
          ? String.format(Locale.ROOT, "Put piece %d of %d in now.", k, pieces)
          : String.format(Locale.ROOT, "Take piece %d out now.", k);
    } else {
      double[] s = SystemStepProcedure.profile(l[1], l[2], vmax, amax, el);
      sp = s[0];
      sys.goal.accept(sp);
      done = s[2] == 1;
      say = l[0] == 100 ? "Sweeping empty." : l[0] == 0 ? "Moving to the start." : String.format(Locale.ROOT, "Sweeping with piece %d.", (int) l[0]);
    }
    if (done) {
      leg++;
      legStart = t;
      return leg >= legs.size();
    }
    return false;
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    return say;
  }

  @Override
  public String abortReason(TestContext ctx) {
    if (sys.kind.positional) {
      double p = sys.position.getAsDouble(), range = sys.max - sys.min;
      if (Double.isFinite(p) && (p < sys.min - SystemStepProcedure.OVERRUN * range || p > sys.max + SystemStepProcedure.OVERRUN * range)) {
        return String.format(Locale.ROOT, "%s went past its limits (%.3f %s): stopped.", sys.name, sys.shown(p),
            sys.shownUnits());
      }
    }
    return null;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    try {
      if (sys.stop != null) {
        sys.stop.run();
      } else if (sys.kind.positional) {
        sys.goal.accept(sys.position.getAsDouble());
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
    if (sys.kind.positional) {
      return legs.isEmpty() ? 0 : Math.min(1.0, (double) leg / legs.size());
    }
    return total > 0 ? Math.min(1.0, t / total) : 0;
  }
}
