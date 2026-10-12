package frc.lib.swervetune;

/**
 * Measures each module's drive feedforward, {@code volts = kS*sgn(v) + kV*v + kA*a}.
 *
 * <p>This is the single biggest step toward a tight drivetrain on YAGSL. Out of the box YAGSL
 * builds the drive feedforward from the motor datasheet: kS of zero, kV of 12 volts divided by the
 * theoretical free speed, and kA of zero. So nothing pays for friction at low speed, kV is a
 * datasheet figure rather than this robot's, and acceleration is left entirely to the PID. A
 * measured feedforward per module puts each wheel within a few percent of its target before the
 * PID does anything, which is what lets the PID stay gentle.
 *
 * <p>The run is SysId's: a slow voltage ramp each way (quasistatic, which pins kS and kV), then a
 * sudden voltage step each way (dynamic, which pins kA). Steering holds every module straight
 * ahead throughout. The fit happens on the laptop, per module, from the voltage the controller
 * <b>actually applied</b> rather than the voltage asked for.
 *
 * <p>On the field it is sized to the floor you declared, using the drivetrain's nominal kV to
 * predict distance, and every powered phase is cut short if the robot reaches 85% of its space —
 * a cut-short phase still contributes its samples. Forward and reverse alternate, so the robot
 * ends near where it began.
 *
 * <p>On blocks the wheels carry no robot, so kA is meaningless there and the laptop says so. A
 * blocks run is still worth doing: kS per module, measured in the air, finds a binding module —
 * one wheel that needs noticeably more voltage to turn than the other three.
 */
final class DriveFeedforwardProcedure implements Procedure {
  private static final int PHASE_ALIGN = 0;
  private static final int PHASE_QS_FWD = 1;
  private static final int PHASE_QS_REV = 2;
  private static final int PHASE_DYN_FWD = 3;
  private static final int PHASE_DYN_REV = 4;
  private static final int PHASE_REST = 5;

  private Timeline timeline;
  private double rampVps;
  private double maxVolts;
  private double stepVolts;
  private final SharedDoubles state = new SharedDoubles(2); // phase, commanded volts
  private double phaseStartX;
  private double phaseStartY;
  private int lastSeg = -1;
  private boolean cutShort;
  private double budgetM;

  @Override
  public String name() {
    return "drive_ff";
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
    return env.allowsActuation;
  }

  /** Nominal kV from the module free speed: volts per (m/s). */
  private static double nominalKv(TestContext ctx) {
    return 12.0 / Math.max(0.5, ctx.io.maxModuleSpeedMps());
  }

  /** Builds the plan, sized to the environment. Shared by validate, budget and start. */
  private Timeline plan(TestContext ctx) {
    double kv = nominalKv(ctx);
    boolean field = ctx.env == TestEnvironment.FIELD;
    rampVps = ctx.args.get("ramp_vps", 1.0, 0.2, 3.0);
    double capVolts = ctx.speedCapMps * kv;
    maxVolts = ctx.args.get("max_v", field ? 7.0 : 6.0, 1.0, 10.0);
    stepVolts = ctx.args.get("step_v", 4.0, 1.0, 8.0);
    if (field || ctx.env == TestEnvironment.SIM) {
      maxVolts = Math.min(maxVolts, capVolts);
      stepVolts = Math.min(stepVolts, 0.9 * capVolts);
    }
    double quasiS = maxVolts / rampVps;
    double dynS = ctx.args.get("step_s", 1.0, 0.25, 3.0);
    if (field) {
      double usable = 0.8 * ctx.spaceForwardM;
      // Distance covered by a ramp from rest: x = rate*T^2 / (2*kV), ignoring friction (pessimistic).
      double rampLimitedS = Math.sqrt(2 * kv * usable / rampVps);
      quasiS = Math.min(quasiS, rampLimitedS);
      // A step covers about (V/kV)*T once moving; take that as the bound.
      dynS = Math.min(dynS, usable * kv / stepVolts);
      budgetM = Math.min(ctx.spaceForwardM, usable + 0.3);
    } else {
      budgetM = ctx.spaceForwardM;
    }
    quasiS = Math.max(1.0, quasiS);
    dynS = Math.max(0.25, dynS);
    double restS = ctx.args.get("rest_s", 1.0, 0.5, 3.0);
    return new Timeline()
        .add("align", 0.6, PHASE_ALIGN)
        .add("quasistatic+", quasiS, PHASE_QS_FWD)
        .add("rest", restS, PHASE_REST)
        .add("quasistatic-", quasiS, PHASE_QS_REV)
        .add("rest", restS, PHASE_REST)
        .add("dynamic+", dynS, PHASE_DYN_FWD)
        .add("rest", restS, PHASE_REST)
        .add("dynamic-", dynS, PHASE_DYN_REV)
        .add("rest", restS, PHASE_REST);
  }

  @Override
  public String validate(TestContext ctx) {
    Timeline t = plan(ctx);
    if (ctx.env == TestEnvironment.FIELD && t.get(1).durationS() < 2.0) {
      return String.format(
          "%.1f m of floor only allows a %.1f s ramp, too short to separate kS from kV. Give it"
              + " at least 2.5 m.",
          ctx.spaceForwardM, t.get(1).durationS());
    }
    return null;
  }

  @Override
  public double spaceBudgetM(TestContext ctx) {
    plan(ctx);
    return budgetM;
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
        .channel("cmd", () -> state.get(1));
    for (int i = 0; i < io.moduleCount(); i++) {
      final int m = i;
      String p = "m" + m + ".";
      ctx.sampler
          .channel(p + "volts", () -> io.driveVolts(m))
          .channel(p + "v", () -> io.driveMps(m))
          .channel(p + "pos", () -> io.drivePositionM(m))
          .channel(p + "amps", () -> io.driveAmps(m));
    }
    ctx.sampler
        .angle("heading", io::headingDeg)
        .channel("x", () -> io.pose()[0])
        .channel("y", () -> io.pose()[1])
        .channel("vbus", io::busVolts);
    ctx.meta("ramp_vps", rampVps);
    ctx.meta("max_v", maxVolts);
    ctx.meta("step_v", stepVolts);
    ctx.meta("quasistatic_s", timeline.get(1).durationS());
    ctx.meta("dynamic_s", timeline.get(5).durationS());
    ctx.meta("kv_nominal", nominalKv(ctx));
    ctx.meta("max_module_speed", io.maxModuleSpeedMps());
    ctx.meta("env_blocks", ctx.env == TestEnvironment.BLOCKS ? 1 : 0);
    io.applyFastTelemetry(true);
    cutShort = false;
    lastSeg = -1;
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    int seg = timeline.indexAt(t);
    if (seg >= timeline.size()) {
      return true;
    }
    DrivetrainIO io = ctx.io;
    if (seg != lastSeg) {
      double[] pose = io.pose();
      phaseStartX = pose[0];
      phaseStartY = pose[1];
      lastSeg = seg;
    }
    int phase = (int) timeline.get(seg).value();
    double into = timeline.timeInto(seg, t);
    double volts =
        switch (phase) {
          case PHASE_QS_FWD -> Math.min(rampVps * into, maxVolts);
          case PHASE_QS_REV -> -Math.min(rampVps * into, maxVolts);
          case PHASE_DYN_FWD -> stepVolts;
          case PHASE_DYN_REV -> -stepVolts;
          default -> 0.0;
        };

    if (ctx.env == TestEnvironment.FIELD && volts != 0) {
      double[] pose = io.pose();
      double travelled = Math.hypot(pose[0] - phaseStartX, pose[1] - phaseStartY);
      if (travelled > 0.85 * budgetM) {
        if (!cutShort) {
          ctx.note(String.format("Phase '%s' cut short at %.2f m to stay inside the space.",
              timeline.get(seg).label(), travelled));
        }
        cutShort = true;
        volts = 0;
        phase = PHASE_REST;
      }
    }

    state.set(0, phase);
    state.set(1, volts);
    for (int m = 0; m < io.moduleCount(); m++) {
      io.setSteerDeg(m, 0);
      io.setDriveVolts(m, phase == PHASE_ALIGN ? 0 : volts);
    }
    return false;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    state.set(1, 0);
    ctx.io.stop();
    ctx.io.applyFastTelemetry(false);
    ctx.meta("cut_short", cutShort ? 1 : 0);
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return timeline == null ? 0 : Math.min(1, t / timeline.totalS());
  }
}
