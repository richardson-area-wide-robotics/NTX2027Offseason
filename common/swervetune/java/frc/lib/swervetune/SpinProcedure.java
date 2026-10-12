package frc.lib.swervetune;

/**
 * Spins in place one way, then the other, through kinematics.
 *
 * <p>On the floor it compares three rotation rates — commanded, what the gyro saw, and what the
 * wheels imply ({@code wheel speed / module radius}) — which separates the usual suspects:
 *
 * <ul>
 *   <li>gyro and wheels agree but both short of the command: the drive loop is not keeping up;
 *   <li>wheels faster than the gyro: wheels slipping, or module locations in the config are wrong;
 *   <li>gyro rotating the wrong way: an inverted IMU, which makes field-relative drive and every
 *       heading controller fight itself.
 * </ul>
 *
 * <p>On blocks the wheels should form a circle and the gyro should stay perfectly still — if it
 * moves, the safety supervisor stops the test because the robot is not on blocks.
 */
final class SpinProcedure implements Procedure {
  private Timeline timeline;
  private double omega;
  private final SharedDoubles commanded = new SharedDoubles(1);

  @Override
  public String name() {
    return "spin";
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

  /** Distance from robot center to the furthest module, meters. */
  static double maxRadius(DrivetrainIO io) {
    double r = 0.1;
    for (int m = 0; m < io.moduleCount(); m++) {
      double[] xy = io.moduleLocationM(m);
      r = Math.max(r, Math.hypot(xy[0], xy[1]));
    }
    return r;
  }

  private double pickOmega(TestContext ctx) {
    double capOmega = ctx.speedCapMps / maxRadius(ctx.io);
    return Math.min(ctx.args.get("omega", 1.5, 0.2, 6.0), capOmega);
  }

  @Override
  public String validate(TestContext ctx) {
    if (ctx.env == TestEnvironment.FIELD) {
      double need = maxRadius(ctx.io) + 0.5;
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
    return 0.6 + 2 * ctx.args.get("duration_s", 2.5, 1.0, 6.0) + 2 * 0.8 + 3;
  }

  @Override
  public void start(TestContext ctx) {
    omega = pickOmega(ctx);
    double spinS = ctx.args.get("duration_s", 2.5, 1.0, 6.0);
    timeline = new Timeline()
        .add("align", 0.6, 0)
        .add("ccw", spinS, omega)
        .add("rest", 0.8, 0)
        .add("cw", spinS, -omega)
        .add("rest", 0.8, 0);
    DrivetrainIO io = ctx.io;
    ctx.sampler.channel("cmd_omega", () -> commanded.get(0)).angle("heading", io::headingDeg);
    for (int i = 0; i < io.moduleCount(); i++) {
      final int m = i;
      String p = "m" + m + ".";
      double[] xy = io.moduleLocationM(m);
      ctx.meta(p + "x", xy[0]);
      ctx.meta(p + "y", xy[1]);
      ctx.sampler
          .channel(p + "v", () -> io.driveMps(m))
          .angle(p + "steer", () -> io.steerDeg(m));
    }
    ctx.sampler
        .channel("x", () -> io.pose()[0])
        .channel("y", () -> io.pose()[1])
        .channel("ax", () -> io.accelMps2().map(a -> a[0]).orElse(Double.NaN))
        .channel("ay", () -> io.accelMps2().map(a -> a[1]).orElse(Double.NaN))
        .channel("vbus", io::busVolts);
    ctx.meta("omega", omega);
    ctx.meta("spin_s", spinS);
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    int seg = timeline.indexAt(t);
    if (seg >= timeline.size()) {
      return true;
    }
    DrivetrainIO io = ctx.io;
    if (seg == 0) {
      // Point every module along its tangent first, so the spin starts clean.
      for (int m = 0; m < io.moduleCount(); m++) {
        double[] xy = io.moduleLocationM(m);
        io.setModuleState(m, 0, Math.toDegrees(Math.atan2(xy[0], -xy[1])));
      }
      commanded.set(0, 0);
      return false;
    }
    double w = timeline.get(seg).value();
    commanded.set(0, w);
    io.driveRobotRelative(0, 0, w);
    return false;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    commanded.set(0, 0);
    ctx.io.stop();
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return timeline == null ? 0 : Math.min(1, t / timeline.totalS());
  }
}
