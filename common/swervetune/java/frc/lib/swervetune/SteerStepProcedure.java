package frc.lib.swervetune;

/**
 * Step response of the steering position loop, one or more modules at once.
 *
 * <p>Each selected module is held where it starts, then commanded through a sequence of angles
 * relative to that start. The sampler records setpoint, absolute angle, motor-encoder angle,
 * applied voltage and current at 200 Hz, which is what the laptop needs to measure rise time,
 * overshoot, settling, steady-state error and ringing for each step separately.
 *
 * <p>Steps go both ways and come in several sizes on purpose. A loop that looks perfect on a
 * 10 degree step can saturate on a 90 degree one, and friction makes small steps behave
 * differently from large ones; the analysis compares them. Direction-dependent results point at
 * mechanical problems (a tight bearing, a rubbing belt), not at gains.
 *
 * <p>Drive motors are held at zero volts throughout, so on the floor the robot stays put and
 * only the wheels turn in place. That makes this safe to run on {@link TestEnvironment#FIELD}
 * with the deadman held, and it is <b>where the final numbers should come from</b>: carpet scrub
 * loads the steering far more than air does, and gains tuned on blocks are usually too soft on
 * the floor.
 *
 * <p>Commands bypass YAGSL's optimisation and anti-jitter on purpose — this measures the loop
 * itself, not the logic in front of it.
 */
final class SteerStepProcedure implements Procedure {
  /** Small, medium and large steps, both directions, each returning to the start. */
  static final double[] STANDARD = {10, 0, -10, 0, 45, 0, -45, 0, 90, 0, -90, 0};
  /** For friction and steady-state error: steps too small to saturate anything. */
  static final double[] SMALL = {2, 0, -2, 0, 5, 0, -5, 0};
  /** For saturation: what a module flip actually asks for. Stops short of 180 so the way round is not a coin toss. */
  static final double[] LARGE = {90, 0, -90, 0, 170, 0, -170, 0};

  private double[] targets;
  private double holdS;
  private double settleS;
  private double[] startDeg;
  private SharedDoubles setpointDeg;
  private Timeline timeline;

  @Override
  public String name() {
    return "steer_step";
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
    return env.allowsActuation;
  }

  @Override
  public String validate(TestContext ctx) {
    double[] t = pickTargets(ctx.args);
    if (t.length > 24) {
      return "At most 24 steps per run.";
    }
    for (double v : t) {
      if (Math.abs(v) > 175) {
        return "Steps must stay within +/-175 degrees of the start so the direction is not ambiguous.";
      }
    }
    if (ctx.modules.length == 0) {
      return "Pick at least one module.";
    }
    return null;
  }

  private static double[] pickTargets(TestArgs args) {
    double[] custom = args.list("s");
    if (custom != null) {
      return custom;
    }
    return switch ((int) args.get("pattern", 0)) {
      case 1 -> SMALL;
      case 2 -> LARGE;
      default -> STANDARD;
    };
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return ctx.args.get("settle_s", 0.5, 0.2, 2) + pickTargets(ctx.args).length
        * ctx.args.get("hold_s", 0.6, 0.2, 3) + 3;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return ctx.args.get("rate_hz", 200, 50, 250);
  }

  @Override
  public void start(TestContext ctx) {
    targets = pickTargets(ctx.args);
    holdS = ctx.args.get("hold_s", 0.6, 0.2, 3);
    settleS = ctx.args.get("settle_s", 0.5, 0.2, 2);
    DrivetrainIO io = ctx.io;
    int n = io.moduleCount();
    startDeg = new double[n];
    setpointDeg = new SharedDoubles(n);
    for (int m = 0; m < n; m++) {
      startDeg[m] = io.steerDeg(m);
      setpointDeg.set(m, startDeg[m]);
    }
    timeline = new Timeline().add("settle", settleS, 0);
    for (double target : targets) {
      timeline.add("step", holdS, target);
    }

    for (int m : ctx.modules) {
      String p = "m" + m + ".";
      ctx.sampler
          .channel(p + "sp", () -> setpointDeg.get(m))
          .angle(p + "steer", () -> io.steerDeg(m))
          .angle(p + "motor", () -> io.steerMotorDeg(m))
          .channel(p + "volts", () -> io.steerVolts(m))
          .channel(p + "amps", () -> io.steerAmps(m));
      ctx.meta(p + "start_deg", startDeg[m]);
    }
    ctx.sampler.channel("vbus", io::busVolts);
    ctx.meta("hold_s", holdS);
    ctx.meta("settle_s", settleS);
    for (int i = 0; i < targets.length; i++) {
      ctx.meta("target" + i, targets[i]);
    }

    DrivetrainIO.ApplyResult fast = io.applyFastTelemetry(true);
    if (!fast.ok()) {
      ctx.note("Could not speed up status frames (" + fast.message() + "); samples repeat every"
          + " 20 ms, so fast transients will look stepped.");
    }
    ctx.meta("fast_telemetry", fast.ok() ? 1 : 0);
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    int seg = timeline.indexAt(t);
    if (seg >= timeline.size()) {
      return true;
    }
    double target = timeline.get(seg).value();
    DrivetrainIO io = ctx.io;
    for (int m = 0; m < io.moduleCount(); m++) {
      double sp = ctx.isSelected(m) ? startDeg[m] + target : startDeg[m];
      setpointDeg.set(m, sp);
      io.setSteerDeg(m, sp);
      io.setDriveVolts(m, 0);
    }
    return false;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    for (int m = 0; m < ctx.io.moduleCount(); m++) {
      ctx.io.setDriveVolts(m, 0);
    }
    ctx.io.applyFastTelemetry(false);
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return timeline == null ? 0 : Math.min(1, t / timeline.totalS());
  }
}
