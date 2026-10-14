package frc.lib.swervetune;

import java.util.Locale;

/**
 * Tunes a {@link HoldCurrent} the way the slip test tunes the drive current: the least current that
 * keeps a game piece in against a steady pull, and a margin over it.
 *
 * <p>With a piece in, it holds at {@code start_a} while the piece seats, then lowers the limit by
 * {@code step_a} every {@code step_s} while a person pulls the piece out steadily, the same way
 * each time (a hand, or a spring scale at a set pull). When the roller turns more than
 * {@code slip_rot} motor rotations in a step, the piece is slipping: that step's current is the
 * slip current. It then holds at {@code margin} times that (never above {@code start_a}) for
 * {@code heat_s} with the pull let go, recording how fast the motor warms there.
 *
 * <p>Args: {@code hold} (index), {@code start_a}, {@code step_a}, {@code step_s}, {@code min_a},
 * {@code slip_rot}, {@code margin}, {@code heat_s}, {@code duty} (default the hold's own). Channels:
 * {@code amps}, {@code limit}, {@code rot}, {@code temp}, {@code duty}, {@code phase} (0 seating,
 * 1 stepping down, 2 the heat check). Meta: {@code slip_a} (NaN if it never slipped),
 * {@code hold_a}.
 */
final class HoldProcedure implements Procedure {
  static final double SEAT_S = 4.0;
  /** The first moment of each step is the limit settling, not the piece moving. */
  static final double STEP_GRACE_S = 0.5;

  private HoldCurrent hold;
  private DriveOwnership owner;
  private double startA;
  private double stepA;
  private double stepS;
  private double minA;
  private double slipRot;
  private double margin;
  private double heatS;
  private double duty;
  private volatile double limit;
  private volatile double phase;
  private double stepStart;
  private double rotAtStep = Double.NaN;
  private double slipA = Double.NaN;
  private double holdA = Double.NaN;
  private double heatStart = Double.NaN;
  private String say = "";

  @Override
  public String name() {
    return "system_hold";
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

  static HoldCurrent pickHold(TestContext ctx) {
    int i = (int) Math.round(ctx.args.get("hold", -1, -1, 63));
    return i >= 0 && i < ctx.holds.size() ? ctx.holds.get(i) : null;
  }

  @Override
  public String validate(TestContext ctx) {
    HoldCurrent h = pickHold(ctx);
    if (h == null) {
      return "No such hold: the code registers none at that number.";
    }
    if (h.motor == null) {
      return "The hold's motor (" + h.motorName + ") isn't watched by the motor guard: watch it first.";
    }
    double s = ctx.args.get("start_a", h.motor.baseLimitA(), 1, 80);
    if (s <= ctx.args.get("min_a", 2, 1, 40)) {
      return "Start above the lowest current.";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    double s = ctx.args.get("start_a", 30, 1, 80), m = ctx.args.get("min_a", 2, 1, 40);
    double step = ctx.args.get("step_a", 2, 0.5, 10), steps = Math.ceil((s - m) / step) + 1;
    return SEAT_S + steps * ctx.args.get("step_s", 2.5, 1, 10) + ctx.args.get("heat_s", 10, 3, 60) + 10;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return 50;
  }

  @Override
  public void start(TestContext ctx) {
    hold = pickHold(ctx);
    startA = ctx.args.get("start_a", hold.motor.baseLimitA(), 1, 80);
    stepA = ctx.args.get("step_a", 2, 0.5, 10);
    stepS = ctx.args.get("step_s", 2.5, 1, 10);
    minA = ctx.args.get("min_a", 2, 1, 40);
    slipRot = ctx.args.get("slip_rot", 0.25, 0.02, 10);
    margin = ctx.args.get("margin", 1.5, 1.0, 3.0);
    heatS = ctx.args.get("heat_s", 10, 3, 60);
    duty = ctx.args.get("duty", hold.duty, -1, 1);
    if (hold.subsystem != null) {
      owner = new DriveOwnership.CommandsV2(hold.subsystem);
      owner.acquire();
    }
    limit = startA;
    phase = 0;
    ctx.sampler.channel("amps", () -> hold.motor.amps())
        .channel("limit", () -> limit)
        .channel("rot", () -> hold.motor.channel.motorRotations())
        .channel("temp", () -> hold.motor.tempC())
        .channel("duty", () -> hold.motor.duty)
        .channel("phase", () -> phase);
    ctx.note("hold: " + hold.motorName);
    ctx.meta("start_a", startA);
    ctx.meta("step_a", stepA);
    ctx.meta("step_s", stepS);
    ctx.meta("min_a", minA);
    ctx.meta("slip_rot", slipRot);
    ctx.meta("margin", margin);
    ctx.meta("heat_s", heatS);
    ctx.meta("duty", duty);
    ctx.meta("current_a", hold.currentA);
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    if (t < SEAT_S) {
      phase = 0;
      say = String.format(Locale.ROOT, "Holding at %.0f A: let the piece seat. Don't pull yet.", limit);
      hold.run(limit, duty);
      stepStart = SEAT_S;
      return false;
    }
    if (phase <= 1 && Double.isNaN(holdA)) {
      phase = 1;
      double rot = hold.motor.channel.motorRotations();
      if (t - stepStart >= STEP_GRACE_S && Double.isNaN(rotAtStep)) {
        rotAtStep = rot;
      }
      boolean slipped = Double.isFinite(rotAtStep) && Double.isFinite(rot) && Math.abs(rot - rotAtStep) > slipRot;
      if (slipped) {
        slipA = limit;
        holdA = Math.min(startA, Math.ceil(slipA * margin));
      } else if (t - stepStart >= stepS) {
        double next = limit - stepA;
        if (next < minA) {
          holdA = Math.min(startA, Math.ceil(minA * margin));   // it held at every current tried
        } else {
          limit = next;
          stepStart = t;
          rotAtStep = Double.NaN;
        }
      }
      if (Double.isNaN(holdA)) {
        say = String.format(Locale.ROOT, "Pull the piece out steadily, the same way each time: holding at %.0f A.", limit);
        hold.run(limit, duty);
        return false;
      }
      ctx.meta("slip_a", slipA);
      ctx.meta("hold_a", holdA);
      limit = holdA;
      heatStart = t;
    }
    phase = 2;
    say = String.format(Locale.ROOT, "Let go: holding at %.0f A for %.0f s to see how warm the motor gets.", holdA, heatS);
    hold.run(holdA, duty);
    return t - heatStart >= heatS;
  }

  @Override
  public String liveMessage(TestContext ctx, double t) {
    return say;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    try {
      hold.off();
    } finally {
      if (owner != null) {
        owner.release();
      }
    }
  }

  @Override
  public double progress(TestContext ctx, double t) {
    if (phase == 2 && Double.isFinite(heatStart)) {
      return Math.min(1.0, 0.7 + 0.3 * (t - heatStart) / heatS);
    }
    double span = Math.max(1, startA - minA);
    return phase == 0 ? 0.05 : Math.min(0.7, 0.1 + 0.6 * (startA - limit) / span);
  }
}
