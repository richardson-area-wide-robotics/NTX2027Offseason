package frc.lib.swervetune;

/**
 * Measures the robot's rotational feedforward, {@code volts = kS*sgn(w) + kV*w + kA*alpha}, to get
 * its moment of inertia.
 *
 * <p>PathPlanner plans every turn from the robot's moment of inertia (MOI), and nobody can weigh
 * that. With every module pointed along its tangent and the same voltage on every drive motor,
 * spinning in place is the drive feedforward test turned sideways: each wheel now pushes the
 * robot's rotational inertia instead of its mass. The laptop fits the angular kA from the gyro and
 * compares it with the linear kA from {@code drive_ff}; the ratio is the MOI:
 * {@code MOI = mass x module radius x kA(angular) / kA(linear)}.
 *
 * <p>SysId's shape: a slow voltage ramp each way (kS and kV), then a step each way (kA). The
 * voltages are gentler than {@code drive_ff}'s, because a spinning robot is more alarming than a
 * driving one. Only on the floor: on blocks nothing turns.
 */
final class SpinFeedforwardProcedure implements Procedure {
  private static final int PHASE_ALIGN = 0;
  private static final int PHASE_QS_CCW = 1;
  private static final int PHASE_QS_CW = 2;
  private static final int PHASE_DYN_CCW = 3;
  private static final int PHASE_DYN_CW = 4;
  private static final int PHASE_REST = 5;

  private Timeline timeline;
  private double rampVps;
  private double maxVolts;
  private double stepVolts;
  private final SharedDoubles state = new SharedDoubles(2); // phase, commanded volts

  @Override
  public String name() {
    return "spin_ff";
  }

  @Override
  public boolean spinsWheels() {
    return true;
  }

  @Override
  public boolean movesChassis(TestContext ctx) {
    return ctx.env.chassisCanMove;
  }

  @Override
  public boolean allowedIn(TestEnvironment env) {
    return env == TestEnvironment.FIELD || env == TestEnvironment.SIM;
  }

  private Timeline plan(TestContext ctx) {
    double kv = 12.0 / Math.max(0.5, ctx.io.maxModuleSpeedMps());
    double capVolts = ctx.speedCapMps * kv;
    rampVps = ctx.args.get("ramp_vps", 0.75, 0.2, 2.0);
    maxVolts = Math.min(ctx.args.get("max_v", 4.0, 1.0, 6.0), capVolts);
    stepVolts = Math.min(ctx.args.get("step_v", 3.0, 1.0, 5.0), 0.9 * capVolts);
    double quasiS = Math.max(2.0, maxVolts / rampVps);
    double dynS = ctx.args.get("step_s", 1.0, 0.4, 2.0);
    double restS = ctx.args.get("rest_s", 1.0, 0.5, 3.0);
    return new Timeline()
        .add("align", 0.6, PHASE_ALIGN)
        .add("quasistatic ccw", quasiS, PHASE_QS_CCW)
        .add("rest", restS, PHASE_REST)
        .add("quasistatic cw", quasiS, PHASE_QS_CW)
        .add("rest", restS, PHASE_REST)
        .add("dynamic ccw", dynS, PHASE_DYN_CCW)
        .add("rest", restS, PHASE_REST)
        .add("dynamic cw", dynS, PHASE_DYN_CW)
        .add("rest", restS, PHASE_REST);
  }

  @Override
  public String validate(TestContext ctx) {
    if (ctx.env == TestEnvironment.FIELD) {
      double need = SpinProcedure.maxRadius(ctx.io) + 0.5;
      if (ctx.spaceForwardM < need || ctx.spaceSideM < need) {
        return String.format("Spinning needs %.1f m clear on every side.", need);
      }
    }
    return null;
  }

  @Override
  public double spaceBudgetM(TestContext ctx) {
    return 0.5;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return plan(ctx).totalS() + 3;
  }

  @Override
  public void start(TestContext ctx) {
    timeline = plan(ctx);
    DrivetrainIO io = ctx.io;
    ctx.sampler
        .channel("phase", () -> state.get(0))
        .channel("cmd", () -> state.get(1))
        .angle("heading", io::headingDeg);
    for (int i = 0; i < io.moduleCount(); i++) {
      final int m = i;
      String p = "m" + m + ".";
      double[] xy = io.moduleLocationM(m);
      ctx.meta(p + "x", xy[0]);
      ctx.meta(p + "y", xy[1]);
      ctx.sampler
          .channel(p + "volts", () -> io.driveVolts(m))
          .channel(p + "v", () -> io.driveMps(m))
          .channel(p + "amps", () -> io.driveAmps(m));
    }
    ctx.sampler
        .channel("x", () -> io.pose()[0])
        .channel("y", () -> io.pose()[1])
        .channel("vbus", io::busVolts);
    ctx.meta("ramp_vps", rampVps);
    ctx.meta("max_v", maxVolts);
    ctx.meta("step_v", stepVolts);
    ctx.meta("kv_nominal", 12.0 / Math.max(0.5, io.maxModuleSpeedMps()));
    io.applyFastTelemetry(true);
  }

  /** The direction a module at {@code (x, y)} rolls when the robot turns counter-clockwise. */
  static double tangentDeg(double[] xy) {
    return Math.toDegrees(Math.atan2(xy[0], -xy[1]));
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    int seg = timeline.indexAt(t);
    if (seg >= timeline.size()) {
      return true;
    }
    DrivetrainIO io = ctx.io;
    int phase = (int) timeline.get(seg).value();
    double into = timeline.timeInto(seg, t);
    double volts =
        switch (phase) {
          case PHASE_QS_CCW -> Math.min(rampVps * into, maxVolts);
          case PHASE_QS_CW -> -Math.min(rampVps * into, maxVolts);
          case PHASE_DYN_CCW -> stepVolts;
          case PHASE_DYN_CW -> -stepVolts;
          default -> 0.0;
        };
    state.set(0, phase);
    state.set(1, volts);
    for (int m = 0; m < io.moduleCount(); m++) {
      io.setSteerDeg(m, tangentDeg(io.moduleLocationM(m)));
      io.setDriveVolts(m, phase == PHASE_ALIGN ? 0 : volts);
    }
    return false;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    state.set(1, 0);
    ctx.io.stop();
    // SwerveTune.finish puts the status frames back, and says if it couldn't.
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return timeline == null ? 0 : Math.min(1, t / timeline.totalS());
  }
}
