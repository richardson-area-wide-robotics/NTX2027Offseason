package frc.lib.swervetune;

/**
 * Step response of the drive velocity loop, all four modules together.
 *
 * <p>Modules are pointed one way and held there, then commanded through a list of speeds
 * through the same path teleop uses — YAGSL's optimisation, cosine compensation and the module
 * drive feedforward — so what is measured is what the driver gets.
 *
 * <p><b>Where you run it changes what it means.</b> On {@link TestEnvironment#BLOCKS} a wheel spins
 * against nothing but its own inertia, roughly a fiftieth of what it sees carrying the robot.
 * The same gains are therefore far more aggressive in the air than on carpet. Blocks runs are
 * good for direction, friction (kS), and the delay of the velocity measurement; the gains you
 * keep must come from a {@link TestEnvironment#FIELD} run.
 *
 * <p>On the field the default profile goes out and comes back — forward steps, stop, the same
 * steps reversed — so the robot ends near where it began and the run fits in less floor. The
 * geofence is the furthest the commanded profile reaches plus a stopping margin, and the run is
 * refused if that does not fit inside the clear floor you declared.
 */
final class DriveStepProcedure implements Procedure {
  /** Deceleration used to size the stopping margin, m/s^2. Deliberately pessimistic. */
  private static final double STOPPING_DECEL = 2.0;

  private double[] speeds;
  private double holdS;
  private double alignS;
  private double angleDeg;
  private final SharedDoubles commanded = new SharedDoubles(1);
  private Timeline timeline;

  @Override
  public String name() {
    return "drive_step";
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

  private double[] pickSpeeds(TestContext ctx) {
    double[] custom = ctx.args.list("s");
    if (custom != null) {
      return custom;
    }
    double cap = ctx.speedCapMps;
    if (ctx.env.chassisCanMove) {
      return new double[] {0.5 * cap, cap, 0, -0.5 * cap, -cap, 0};
    }
    return new double[] {0.25 * cap, 0.5 * cap, cap, 0.5 * cap, 0, -0.5 * cap, 0};
  }

  /** Furthest the commanded profile gets from the start, plus room to stop. */
  double excursionM(double[] profile, double hold) {
    double x = 0;
    double furthest = 0;
    double fastest = 0;
    for (double v : profile) {
      x += v * hold;
      furthest = Math.max(furthest, Math.abs(x));
      fastest = Math.max(fastest, Math.abs(v));
    }
    return furthest + fastest * fastest / (2 * STOPPING_DECEL) + 0.15;
  }

  @Override
  public String validate(TestContext ctx) {
    double[] profile = pickSpeeds(ctx);
    double hold = ctx.args.get("hold_s", 0.8, 0.3, 3);
    for (double v : profile) {
      if (Math.abs(v) > ctx.speedCapMps + 1e-6) {
        return String.format("Speed %.2f m/s is over the %.2f m/s cap.", v, ctx.speedCapMps);
      }
    }
    if (ctx.env == TestEnvironment.FIELD) {
      double needed = excursionM(profile, hold);
      double have = spaceFor(ctx);
      if (needed > have) {
        return String.format(
            "This run needs %.1f m of clear floor and you declared %.1f m. Lower the speed cap,"
                + " shorten hold_s, or find more room.",
            needed, have);
      }
    }
    return null;
  }

  private double spaceFor(TestContext ctx) {
    double a = Math.abs(ctx.args.get("angle_deg", 0) % 180);
    return a < 1 || a > 179 ? ctx.spaceForwardM : ctx.tightestSpaceM();
  }

  @Override
  public double spaceBudgetM(TestContext ctx) {
    return Math.min(spaceFor(ctx), excursionM(pickSpeeds(ctx), ctx.args.get("hold_s", 0.8, 0.3, 3)) + 0.3);
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return 1 + pickSpeeds(ctx).length * ctx.args.get("hold_s", 0.8, 0.3, 3) + 3;
  }

  @Override
  public void start(TestContext ctx) {
    speeds = pickSpeeds(ctx);
    holdS = ctx.args.get("hold_s", 0.8, 0.3, 3);
    alignS = ctx.args.get("align_s", 0.6, 0.3, 2);
    angleDeg = ctx.args.get("angle_deg", 0, -360, 360);
    timeline = new Timeline().add("align", alignS, 0);
    for (double v : speeds) {
      timeline.add("speed", holdS, v);
    }

    DrivetrainIO io = ctx.io;
    ctx.sampler.channel("sp", () -> commanded.get(0));
    for (int i = 0; i < io.moduleCount(); i++) {
      final int m = i;
      String p = "m" + m + ".";
      ctx.sampler
          .channel(p + "v", () -> io.driveMps(m))
          .channel(p + "spm", () -> io.driveSetpointMps(m))
          .channel(p + "volts", () -> io.driveVolts(m))
          .channel(p + "amps", () -> io.driveAmps(m))
          .angle(p + "steer", () -> io.steerDeg(m));
    }
    ctx.sampler
        .angle("heading", io::headingDeg)
        .channel("x", () -> io.pose()[0])
        .channel("y", () -> io.pose()[1])
        .channel("ax", () -> io.accelMps2().map(a -> a[0]).orElse(Double.NaN))
        .channel("ay", () -> io.accelMps2().map(a -> a[1]).orElse(Double.NaN))
        .channel("vbus", io::busVolts);
    ctx.meta("hold_s", holdS);
    ctx.meta("align_s", alignS);
    ctx.meta("angle_deg", angleDeg);
    ctx.meta("max_module_speed", io.maxModuleSpeedMps());
    ctx.meta("current_limit_a", io.driveCurrentLimitA());
    for (int i = 0; i < speeds.length; i++) {
      ctx.meta("speed" + i, speeds[i]);
    }
    if (ctx.env == TestEnvironment.BLOCKS) {
      ctx.note("On blocks: use this run for direction, friction and measurement delay. Keep gains"
          + " from a FIELD run; free wheels make every gain look stronger than it is.");
    }
    io.applyFastTelemetry(true);
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    int seg = timeline.indexAt(t);
    if (seg >= timeline.size()) {
      return true;
    }
    double v = timeline.get(seg).value();
    commanded.set(0, v);
    for (int m = 0; m < ctx.io.moduleCount(); m++) {
      ctx.io.setModuleState(m, v, angleDeg);
    }
    return false;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    commanded.set(0, 0);
    ctx.io.stop();
    ctx.io.applyFastTelemetry(false);
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return timeline == null ? 0 : Math.min(1, t / timeline.totalS());
  }
}
