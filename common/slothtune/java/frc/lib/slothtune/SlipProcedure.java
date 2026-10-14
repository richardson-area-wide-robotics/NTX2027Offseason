package frc.lib.slothtune;

/**
 * Finds the drive current at which each wheel starts to slip on this carpet, so the drive current
 * limit can sit just below it instead of at a number from a datasheet.
 *
 * <p>Why it matters: above the slip current, more current cannot push the robot any harder - the
 * carpet will not pass on more force - so it only spins the wheel. That wastes battery, heats the
 * motor, wears the tread, and makes odometry count distance the robot never traveled. A limit
 * just below slip gives the hardest acceleration the carpet allows and keeps every wheel gripping.
 *
 * <p>The method is the standard wall push. The robot sits with a bumper flat against a solid wall,
 * every module pointing into it. The drive voltage ramps up slowly; with the chassis held by the
 * wall the wheels cannot turn, so the current climbs with the voltage. When a wheel's push beats
 * the carpet's grip, that wheel starts to spin: its encoder speed jumps while the chassis stays
 * put. The highest current it carried before that is its breakaway current. Each wheel is cut the
 * moment it slips, to spare the tread; the others carry on until they slip too, or until the
 * current reaches the ceiling, which is never above the team's policy for the motor.
 *
 * <p>For the run only, the drive current limit is raised to the ceiling, never saved to flash, and
 * put back afterwards whatever happens. The laptop analyzes the samples and recommends a limit.
 *
 * <p>Wheels that turn at a current far too low to be slipping mean the robot is driving, not
 * pushing: it is not against a wall. The run stops at once and says so.
 */
final class SlipProcedure implements Procedure {
  /** Below this, a wheel that turns is driving the robot, not slipping on the carpet. */
  static final double MIN_PLAUSIBLE_SLIP_A = 8.0;
  private static final double ALIGN_S = 0.8;

  private double ceilingA;
  private double rampVps;
  private double slipSpeed;
  private double direction;
  private double restoreA;
  private boolean[] slipped;
  private int[] fastLoops;
  private double[] peakA;
  private double[] slipA;
  private double[] heldSince;
  private boolean[] capped;
  private boolean wallLost;
  private double lastVolts;
  private final SharedDoubles state = new SharedDoubles(2); // phase (0 align, 1 ramp), commanded volts

  @Override
  public String name() {
    return "slip";
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
  public boolean pushesWall() {
    return true;
  }

  @Override
  public boolean allowedIn(TestEnvironment env) {
    // On blocks a free wheel spins at once and measures nothing. Simulation only proves plumbing.
    return env == TestEnvironment.FIELD || env == TestEnvironment.SIM;
  }

  private void plan(TestContext ctx) {
    ceilingA = Math.min(ctx.args.get("ceiling_a", ctx.drivePolicyA, 10, 80), ctx.drivePolicyA);
    rampVps = ctx.args.get("ramp_vps", 1.0, 0.3, 3.0);
    slipSpeed = ctx.args.get("slip_mps", 0.15, 0.05, 0.5);
    direction = ctx.args.get("direction", 1, -1, 1) < 0 ? -1 : 1;
  }

  @Override
  public String validate(TestContext ctx) {
    plan(ctx);
    if (ceilingA < 10) {
      return "The current ceiling is below 10 A; nothing would slip.";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    plan(ctx);
    return ALIGN_S + 12.0 / rampVps + 3;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return 200;
  }

  @Override
  public void start(TestContext ctx) {
    plan(ctx);
    DrivetrainIO io = ctx.io;
    int n = io.moduleCount();
    slipped = new boolean[n];
    fastLoops = new int[n];
    peakA = new double[n];
    slipA = new double[n];
    heldSince = new double[n];
    capped = new boolean[n];
    java.util.Arrays.fill(slipA, Double.NaN);
    java.util.Arrays.fill(heldSince, Double.NaN);
    wallLost = false;
    restoreA = ctx.driveLimitA;
    ctx.sampler
        .channel("phase", () -> state.get(0))
        .channel("cmd", () -> state.get(1));
    for (int i = 0; i < n; i++) {
      final int m = i;
      String p = "m" + m + ".";
      ctx.sampler
          .channel(p + "volts", () -> io.driveVolts(m))
          .channel(p + "amps", () -> io.driveAmps(m))
          .channel(p + "v", () -> io.driveMps(m))
          .channel(p + "pos", () -> io.drivePositionM(m));
    }
    ctx.sampler
        .angle("heading", io::headingDeg)
        .channel("x", () -> io.pose()[0])
        .channel("y", () -> io.pose()[1])
        .channel("ax", () -> io.accelMps2().map(a -> a[0]).orElse(Double.NaN))
        .channel("ay", () -> io.accelMps2().map(a -> a[1]).orElse(Double.NaN))
        .channel("vbus", io::busVolts);
    DrivetrainIO.ApplyResult r = io.setDriveCurrentLimit((int) Math.round(ceilingA));
    ctx.note("Drive current limit raised to " + Math.round(ceilingA) + " A for the run: " + r.message());
    ctx.meta("ceiling_a", ceilingA);
    ctx.meta("policy_a", ctx.drivePolicyA);
    ctx.meta("limit_before_a", restoreA);
    ctx.meta("ramp_vps", rampVps);
    ctx.meta("slip_mps", slipSpeed);
    ctx.meta("direction", direction);
    ctx.meta("min_plausible_slip_a", MIN_PLAUSIBLE_SLIP_A);
    io.applyFastTelemetry(true);
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    DrivetrainIO io = ctx.io;
    int n = io.moduleCount();
    if (t < ALIGN_S) {
      state.set(0, 0);
      state.set(1, 0);
      for (int m = 0; m < n; m++) {
        io.setSteerDeg(m, 0);
        io.setDriveVolts(m, 0);
      }
      return false;
    }
    double volts = Math.min(12.0, rampVps * (t - ALIGN_S));
    lastVolts = volts;
    state.set(0, 1);
    state.set(1, direction * volts);
    boolean allDone = true;
    for (int m = 0; m < n; m++) {
      io.setSteerDeg(m, 0);
      if (slipped[m] || capped[m]) {
        io.setDriveVolts(m, 0);
        continue;
      }
      double amps = Math.abs(io.driveAmps(m));
      double speed = Math.abs(io.driveMps(m));
      if (Double.isFinite(amps)) {
        peakA[m] = Math.max(peakA[m], amps);
      }
      fastLoops[m] = speed > slipSpeed ? fastLoops[m] + 1 : 0;
      if (fastLoops[m] >= 2) {
        if (peakA[m] < MIN_PLAUSIBLE_SLIP_A) {
          wallLost = true;
          ctx.note(String.format("%s turned at only %.1f A: the robot is driving, not slipping. Put"
              + " a bumper flat against a solid wall and run again.", io.moduleName(m), peakA[m]));
          return true;
        }
        slipped[m] = true;
        slipA[m] = peakA[m];
        ctx.meta("slip_t_m" + m, t);
        ctx.note(String.format("%s slipped at %.1f A.", io.moduleName(m), peakA[m]));
        io.setDriveVolts(m, 0);
        continue;
      }
      // Held at the ceiling without slipping: the carpet grips better than the ceiling allows.
      if (amps >= 0.95 * ceilingA) {
        if (Double.isNaN(heldSince[m])) {
          heldSince[m] = t;
        }
      } else {
        heldSince[m] = Double.NaN;
      }
      if (!Double.isNaN(heldSince[m]) && t - heldSince[m] >= 0.5) {
        capped[m] = true;
        ctx.note(String.format("%s held %.0f A without slipping: the carpet grips better than the"
            + " ceiling allows.", io.moduleName(m), ceilingA));
        io.setDriveVolts(m, 0);
        continue;
      }
      allDone = false;
      io.setDriveVolts(m, direction * volts);
    }
    return allDone || volts >= 12.0;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    DrivetrainIO io = ctx.io;
    state.set(1, 0);
    io.stop();
    DrivetrainIO.ApplyResult r = io.setDriveCurrentLimit((int) Math.round(restoreA));
    if (!r.ok()) {
      ctx.note("Could not put the drive current limit back to " + Math.round(restoreA) + " A ("
          + r.message() + "). Restart the robot code before driving.");
    }
    // SlothTune.finish puts the status frames back, and says if it couldn't.
    for (int m = 0; m < (slipA == null ? 0 : slipA.length); m++) {
      ctx.meta("slip_a_m" + m, slipA[m]);
      ctx.meta("peak_a_m" + m, peakA[m]);
    }
    ctx.meta("wall_lost", wallLost ? 1 : 0);
    ctx.meta("final_volts", lastVolts);
  }

  @Override
  public double progress(TestContext ctx, double t) {
    double rampS = ALIGN_S + Math.min(12.0, ceilingA * 0.15) / rampVps;
    return Math.min(1, t / Math.max(1, rampS));
  }
}
