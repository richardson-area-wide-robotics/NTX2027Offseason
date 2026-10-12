package frc.lib.swervetune;

/**
 * Drives a measured straight line with no heading correction, then optionally comes back.
 *
 * <p>The acceptance test for everything else. With the heading controller off, whatever the robot
 * does is the drivetrain's own behavior: a module offset a degree out, one weak corner, or a gyro
 * scale error all show up as heading drift and sideways drift that a corrected run would hide.
 *
 * <p>Ground truth, in order of preference:
 *
 * <ol>
 *   <li><b>AprilTags</b>, when they are switched on and robot code has registered a vision source;
 *   <li><b>a tape measure</b> — the laptop asks for where the robot actually stopped, measured from
 *       a mark at the start;
 *   <li><b>the gyro alone</b> for heading drift, which needs no field at all.
 * </ol>
 *
 * <p>So this works on a practice field with no tags. Odometry is recorded too, but it is never
 * scored against itself: wheel odometry agreeing with wheel odometry proves nothing.
 */
final class StraightLineProcedure implements Procedure {
  private Timeline timeline;
  private double distanceM;
  private double speedMps;
  private double accel;
  private final SharedDoubles commanded = new SharedDoubles(1);

  @Override
  public String name() {
    return "straight";
  }

  @Override
  public boolean spinsWheels() {
    return true;
  }

  @Override
  public boolean movesChassis(TestContext ctx) {
    return true;
  }

  @Override
  public boolean allowedIn(TestEnvironment env) {
    return env.chassisCanMove;
  }

  private void pick(TestContext ctx) {
    speedMps = Math.min(ctx.args.get("speed", 1.0, 0.2, 4.0), ctx.speedCapMps);
    accel = ctx.args.get("accel", 1.0, 0.3, 3.0);
    double room = 0.75 * ctx.spaceForwardM;
    distanceM = Math.min(ctx.args.get("distance_m", Math.min(3.0, room), 0.5, 10.0), room);
  }

  /** Trapezoid profile: seconds to cover {@code d} at peak {@code v} with accel {@code a}. */
  static double profileSeconds(double d, double v, double a) {
    double accelD = v * v / a;
    if (accelD >= d) {
      return 2 * Math.sqrt(d / a);
    }
    return 2 * v / a + (d - accelD) / v;
  }

  /** Commanded speed {@code t} seconds into the profile. */
  static double profileSpeed(double t, double d, double v, double a) {
    double total = profileSeconds(d, v, a);
    if (t <= 0 || t >= total) {
      return 0;
    }
    double peak = Math.min(v, Math.sqrt(a * d));
    return Math.min(peak, Math.min(a * t, a * (total - t)));
  }

  @Override
  public String validate(TestContext ctx) {
    pick(ctx);
    if (ctx.spaceForwardM < 1.5) {
      return "A straight-line run needs at least 1.5 m of clear floor ahead.";
    }
    return null;
  }

  @Override
  public double spaceBudgetM(TestContext ctx) {
    pick(ctx);
    return Math.min(ctx.spaceForwardM, distanceM + 0.4);
  }

  @Override
  public double timeoutS(TestContext ctx) {
    pick(ctx);
    return 0.6 + 2 * profileSeconds(distanceM, speedMps, accel) + 3 + 3;
  }

  @Override
  public void start(TestContext ctx) {
    pick(ctx);
    double go = profileSeconds(distanceM, speedMps, accel);
    boolean comeBack = ctx.args.flag("return", true);
    timeline = new Timeline().add("align", 0.6, 0).add("out", go, 1).add("hold", 1.5, 0);
    if (comeBack) {
      timeline.add("back", go, -1).add("hold", 1.0, 0);
    }
    DrivetrainIO io = ctx.io;
    ctx.sampler
        .channel("cmd_vx", () -> commanded.get(0))
        .channel("x", () -> io.pose()[0])
        .channel("y", () -> io.pose()[1])
        .angle("heading", io::headingDeg)
        .channel("vx_vision", () -> visionAxis(ctx, 0))
        .channel("vy_vision", () -> visionAxis(ctx, 1))
        .channel("vbus", io::busVolts);
    for (int i = 0; i < io.moduleCount(); i++) {
      final int m = i;
      String p = "m" + m + ".";
      ctx.sampler.channel(p + "v", () -> io.driveMps(m)).angle(p + "steer", () -> io.steerDeg(m));
    }
    ctx.meta("distance_m", distanceM);
    ctx.meta("speed", speedMps);
    ctx.meta("accel", accel);
    ctx.meta("return", comeBack ? 1 : 0);
    ctx.meta("vision_in_use", ctx.visionInUse ? 1 : 0);
    if (!ctx.visionInUse) {
      ctx.note("No AprilTag ground truth: measure where the robot stopped with a tape from the"
          + " start mark, and enter it in the tool.");
    }
  }

  private static double visionAxis(TestContext ctx, int axis) {
    double[] p = ctx.visionPose == null ? null : ctx.visionPose.get();
    return p == null ? Double.NaN : p[axis];
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    int seg = timeline.indexAt(t);
    if (seg >= timeline.size()) {
      return true;
    }
    DrivetrainIO io = ctx.io;
    double dir = timeline.get(seg).value();
    if (seg == 0) {
      for (int m = 0; m < io.moduleCount(); m++) {
        io.setModuleState(m, 0, 0);
      }
      commanded.set(0, 0);
      return false;
    }
    double vx = dir == 0 ? 0 : dir * profileSpeed(timeline.timeInto(seg, t), distanceM, speedMps, accel);
    commanded.set(0, vx);
    if (dir == 0) {
      for (int m = 0; m < io.moduleCount(); m++) {
        io.setModuleState(m, 0, 0);
      }
    } else {
      io.driveRobotRelative(vx, 0, 0);
    }
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
