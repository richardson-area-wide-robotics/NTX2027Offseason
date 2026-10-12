package frc.lib.swervetune;

/**
 * Records every module sensor while commanding nothing.
 *
 * <p>Runs with the robot <b>disabled</b>, which makes it the safest test there is, and is the
 * basis for three laptop analyses:
 *
 * <ul>
 *   <li><b>health</b> — a couple of seconds standing still: sensor noise, absolute encoder read
 *       failures, steering motor encoder drifting from the absolute encoder, gyro drift.
 *   <li><b>hand check</b> — a person turns each wheel and each module by hand while this records.
 *       Proves every sign before anything is powered: drive encoder direction, steering direction,
 *       and that the steering gear ratio in the config matches the real one.
 *   <li><b>offsets</b> — every wheel set straight ahead by hand; the laptop computes new
 *       absolute encoder offsets from what was recorded.
 *   <li><b>gyro</b> — a minute standing still (drift, and the mount's tilt), or full turns ending
 *       back on a line (scale). Without coast it runs enabled too, and never takes the drivetrain,
 *       so a driver can turn the robot with the sticks while it records.
 * </ul>
 *
 * <p>With {@code coast=1} the motors are switched to coast so the modules can be turned by hand,
 * and switched back when it ends. The change is never written to flash, so a power cycle also
 * undoes it. If the robot is enabled while coasting, the capture ends at once.
 */
final class CaptureProcedure implements Procedure {
  private volatile boolean stopRequested;
  private boolean coastApplied;
  private double durationS;

  @Override
  public String name() {
    return "capture";
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
    if (ctx.args.flag("coast", false) && ctx.enabledAtStart) {
      return "Coast mode is only allowed while the robot is disabled. Disable it first.";
    }
    return null;
  }

  @Override
  public double timeoutS(TestContext ctx) {
    return ctx.args.get("duration_s", 5, 0.5, 120) + 2;
  }

  @Override
  public double sampleRateHz(TestContext ctx) {
    return ctx.args.get("rate_hz", 50, 10, 200);
  }

  @Override
  public void start(TestContext ctx) {
    stopRequested = false;
    durationS = ctx.args.get("duration_s", 5, 0.5, 120);
    DrivetrainIO io = ctx.io;
    for (int m : ctx.modules) {
      String p = "m" + m + ".";
      ctx.sampler
          .angle(p + "steer", () -> io.steerDeg(m))
          .angle(p + "motor", () -> io.steerMotorDeg(m))
          .angle(p + "raw", () -> io.steerRawDeg(m))
          .channel(p + "pos", () -> io.drivePositionM(m))
          .channel(p + "v", () -> io.driveMps(m))
          .channel(p + "amps", () -> io.driveAmps(m));
    }
    ctx.sampler
        .angle("heading", io::headingDeg)
        .channel("roll", () -> io.gyroTiltDeg()[0])
        .channel("pitch", () -> io.gyroTiltDeg()[1])
        .channel("ax", () -> io.accelMps2().map(a -> a[0]).orElse(Double.NaN))
        .channel("ay", () -> io.accelMps2().map(a -> a[1]).orElse(Double.NaN))
        .channel("vbus", io::busVolts);
    ctx.meta("duration_s", durationS);

    if (ctx.args.flag("coast", false)) {
      DrivetrainIO.ApplyResult r = io.setCoast(true);
      coastApplied = r.ok();
      ctx.note(r.ok() ? "Motors in coast for the capture." : "Coast refused: " + r.message());
    }
    ctx.meta("coast", coastApplied ? 1 : 0);
  }

  @Override
  public boolean execute(TestContext ctx, double t) {
    if (coastApplied && ctx.enabled.getAsBoolean()) {
      ctx.note("Robot was enabled while coasting; capture ended and brake restored.");
      return true;
    }
    return stopRequested || t >= durationS;
  }

  @Override
  public void end(TestContext ctx, boolean aborted) {
    if (coastApplied) {
      DrivetrainIO.ApplyResult r = ctx.io.setCoast(false);
      if (!r.ok()) {
        ctx.note("Could not restore brake mode: " + r.message() + ". Power cycle the robot.");
      }
      coastApplied = false;
    }
  }

  @Override
  public double progress(TestContext ctx, double t) {
    return Math.min(1.0, t / Math.max(0.1, durationS));
  }

  @Override
  public void requestStop() {
    stopRequested = true;
  }
}
