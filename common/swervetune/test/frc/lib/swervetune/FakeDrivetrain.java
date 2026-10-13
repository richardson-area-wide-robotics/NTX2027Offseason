package frc.lib.swervetune;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * A four-module drivetrain good enough to exercise the harness: steering and wheel speed follow
 * their commands with a lag, and the chassis either moves with the wheels (on the floor) or stays
 * put (on blocks). {@link #step} advances it.
 */
final class FakeDrivetrain implements DrivetrainIO {
  static final double[][] LOCATIONS = {{0.3, 0.3}, {0.3, -0.3}, {-0.3, 0.3}, {-0.3, -0.3}};
  static final String[] NAMES = {"frontleft", "frontright", "backleft", "backright"};

  final double[] steer = new double[4];
  final double[] steerCmd = {Double.NaN, Double.NaN, Double.NaN, Double.NaN};
  final double[] speed = new double[4];
  final double[] speedCmd = new double[4];
  final double[] position = new double[4];
  final double[] volts = new double[4];
  double heading;
  double x;
  double y;
  double bus = 12.6;
  boolean chassisMoves = true;
  /** Extra yaw rate injected regardless of wheels, deg/s: a robot being pushed, or not on blocks. */
  double injectedYawRate;
  double[] steerPid = {0.01, 0, 0.001, 0};
  double[] drivePid = {0.002, 0, 0, 0};
  double[][] ff = new double[4][];
  boolean gyroConnected = true;
  boolean gyroCalibrating = false;
  final List<String> applied = new ArrayList<>();
  /** Steering motors as the motor guard sees them: NEO 550s at 20 A. Drive motors are not watched. */
  final FakeMotorChannel[] steerMotors = {
    new FakeMotorChannel(20), new FakeMotorChannel(20), new FakeMotorChannel(20), new FakeMotorChannel(20)
  };
  boolean coast;
  boolean stopped;
  /**
   * Wall mode for the slip test: each wheel's breakaway current, amps, with a bumper against a
   * wall. Null when there is no wall. A wheel stays still until its current passes this.
   */
  double[] wallSlipA;
  final boolean[] slipping = new boolean[4];
  final double[] amps = new double[4];
  /** Each wheel's acceleration in the last step, m/s^2, for its current. */
  final double[] accel = new double[4];
  double driveLimitA = 40;
  final List<Integer> limitsSet = new ArrayList<>();

  /** How quickly a wheel follows its command, seconds. A wheel pushing a robot on carpet is slower. */
  double driveLagS = 0.08;

  /** Module free speed at 12 V, m/s: a NEO at 5.50:1 by default; 4.92 for the robots' Vortexes. */
  double freeSpeedMps = 4.12;

  FakeDrivetrain() {
    for (int m = 0; m < 4; m++) {
      ff[m] = new double[] {0, 2.9, 0};
    }
  }

  /** Advances the model by {@code dt} seconds. */
  void step(double dt) {
    double vx = 0;
    double vy = 0;
    double omega = 0;
    for (int m = 0; m < 4; m++) {
      if (Double.isFinite(steerCmd[m])) {
        double err = ((steerCmd[m] - steer[m] + 540) % 360) - 180;
        steer[m] = (steer[m] + err * Math.min(1, dt / 0.05) + 360) % 360;
      }
      double target = Double.isFinite(speedCmd[m]) ? speedCmd[m] : volts[m] / 12.0 * freeSpeedMps;
      if (wallSlipA != null) {
        // Against a wall the wheel is stalled: current is volts over the NEO's resistance, up to
        // the limit, until it beats the carpet's grip; then it spins and the current falls.
        double stalled = Math.min(Math.abs(volts[m]) / 0.114, driveLimitA);
        if (!slipping[m] && stalled >= wallSlipA[m]) {
          slipping[m] = true;
        }
        if (!slipping[m]) {
          speed[m] = 0;
          amps[m] = stalled;
          continue;
        }
        amps[m] = 0.6 * stalled;
      }
      double before = speed[m];
      speed[m] += (target - speed[m]) * Math.min(1, dt / driveLagS);
      accel[m] = dt > 0 ? (speed[m] - before) / dt : 0;
      position[m] += speed[m] * dt;
      double a = Math.toRadians(steer[m]);
      vx += speed[m] * Math.cos(a) / 4;
      vy += speed[m] * Math.sin(a) / 4;
      double[] r = LOCATIONS[m];
      // tangential component / radius
      omega += (-speed[m] * Math.cos(a) * r[1] + speed[m] * Math.sin(a) * r[0])
          / (r[0] * r[0] + r[1] * r[1]) / 4;
    }
    if (chassisMoves && wallSlipA == null) {
      double h = Math.toRadians(heading);
      x += (vx * Math.cos(h) - vy * Math.sin(h)) * dt;
      y += (vx * Math.sin(h) + vy * Math.cos(h)) * dt;
      heading += Math.toDegrees(omega) * dt;
    }
    heading += injectedYawRate * dt;
  }

  @Override
  public int moduleCount() {
    return 4;
  }

  @Override
  public String moduleName(int m) {
    return NAMES[m];
  }

  @Override
  public double[] moduleLocationM(int m) {
    return LOCATIONS[m].clone();
  }

  @Override
  public double maxModuleSpeedMps() {
    return freeSpeedMps;
  }

  @Override
  public double driveCurrentLimitA() {
    return driveLimitA;
  }

  @Override
  public ApplyResult setDriveCurrentLimit(int a) {
    driveLimitA = a;
    limitsSet.add(a);
    return ApplyResult.ok("drive current limit " + a + " A");
  }

  @Override
  public double driveGearRatio() {
    return 5.5;
  }

  @Override
  public double steerGearRatio() {
    return 46.42;
  }

  @Override
  public String steerFeedback() {
    return "motor";
  }

  @Override
  public double steerDeg(int m) {
    return steer[m];
  }

  @Override
  public double steerRawDeg(int m) {
    return (steer[m] + 90) % 360;
  }

  @Override
  public double steerMotorDeg(int m) {
    return steer[m];
  }

  @Override
  public double steerSetpointDeg(int m) {
    return steerCmd[m];
  }

  @Override
  public double driveMps(int m) {
    return speed[m];
  }

  @Override
  public double drivePositionM(int m) {
    return position[m];
  }

  @Override
  public double driveSetpointMps(int m) {
    return speedCmd[m];
  }

  @Override
  public double driveVolts(int m) {
    return Double.isFinite(speedCmd[m]) ? speedCmd[m] * 2.9 : volts[m];
  }

  @Override
  public double steerVolts(int m) {
    return 0;
  }

  @Override
  public double driveAmps(int m) {
    if (wallSlipA != null) {
      return amps[m];
    }
    // Friction, plus what it takes to speed the wheel up: just the wheel in the air (about 0.3 A
    // per m/s^2), or a quarter of the robot on the floor (about 5.7). Capped at the limit.
    double friction = Math.abs(speed[m]) > 0.01 ? 2.0 : 0.0;
    double perAccel = chassisMoves ? 5.7 : 0.3;
    return Math.min(driveLimitA, friction + perAccel * Math.abs(accel[m]));
  }

  @Override
  public double steerAmps(int m) {
    return 1;
  }

  @Override
  public double driveTempC(int m) {
    return 30;
  }

  @Override
  public double steerTempC(int m) {
    return 30;
  }

  @Override
  public String faults(int m) {
    return "";
  }

  @Override
  public boolean absoluteReadIssue(int m) {
    return false;
  }

  @Override
  public double headingDeg() {
    return heading;
  }

  @Override
  public Optional<double[]> accelMps2() {
    return Optional.of(new double[] {0, 0, 0});
  }

  @Override
  public GyroStatus gyroStatus() {
    return new GyroStatus("fake", gyroConnected, gyroCalibrating, "");
  }

  @Override
  public double[] pose() {
    return new double[] {x, y, heading};
  }

  final java.util.List<double[]> visionFed = new java.util.ArrayList<>();

  @Override
  public void addVisionMeasurement(double xM, double yM, double headingDeg, double timestampS,
      double sdXyM, double sdHeadingRad) {
    visionFed.add(new double[] {xM, yM, headingDeg, timestampS, sdXyM, sdHeadingRad});
  }

  @Override
  public double busVolts() {
    return bus;
  }

  @Override
  public void setSteerDeg(int m, double degrees) {
    steerCmd[m] = ((degrees % 360) + 360) % 360;
  }

  @Override
  public void setDriveVolts(int m, double v) {
    speedCmd[m] = Double.NaN;
    volts[m] = v;
  }

  @Override
  public void setModuleState(int m, double speedMps, double angleDeg) {
    steerCmd[m] = ((angleDeg % 360) + 360) % 360;
    speedCmd[m] = speedMps;
  }

  @Override
  public void driveRobotRelative(double vx, double vy, double omega) {
    for (int m = 0; m < 4; m++) {
      double[] r = LOCATIONS[m];
      double mx = vx - omega * r[1];
      double my = vy + omega * r[0];
      setModuleState(m, Math.hypot(mx, my), Math.toDegrees(Math.atan2(my, mx)));
    }
  }

  @Override
  public void stop() {
    stopped = true;
    for (int m = 0; m < 4; m++) {
      speedCmd[m] = 0;
      volts[m] = 0;
    }
  }

  @Override
  public ApplyResult setCoast(boolean coast) {
    this.coast = coast;
    applied.add("coast=" + coast);
    return ApplyResult.ok("coast " + coast);
  }

  @Override
  public ApplyResult applySteerPid(double kP, double kI, double kD, double iZone) {
    steerPid = new double[] {kP, kI, kD, iZone};
    applied.add("steerPid");
    return ApplyResult.ok("steer PID");
  }

  @Override
  public ApplyResult applyDrivePid(double kP, double kI, double kD, double iZone) {
    drivePid = new double[] {kP, kI, kD, iZone};
    applied.add("drivePid");
    return ApplyResult.ok("drive PID");
  }

  @Override
  public ApplyResult applyDriveFeedforward(int m, double kS, double kV, double kA) {
    ff[m] = new double[] {kS, kV, kA};
    applied.add("ff" + m);
    return ApplyResult.ok("ff " + m);
  }

  @Override
  public ApplyResult applyRampRates(double steerSeconds, double driveSeconds) {
    applied.add("ramp");
    return ApplyResult.ok("ramp");
  }

  @Override
  public ApplyResult applyDriveVelocityFilter(int periodMs, int averageDepth) {
    applied.add("filter " + periodMs + "x" + averageDepth);
    return ApplyResult.ok("filter");
  }

  @Override
  public ApplyResult applyFastTelemetry(boolean fast) {
    return ApplyResult.ok("fast " + fast);
  }

  @Override
  public ApplyResult applyEncoderAutoSync(boolean enabled, double deadbandDeg) {
    applied.add("sync " + enabled);
    return ApplyResult.ok("sync");
  }

  @Override
  public ApplyResult applyAngularVelocityCompensation(boolean teleop, boolean auto, double coefficient) {
    applied.add("angvel " + coefficient);
    return ApplyResult.ok("angvel");
  }

  @Override
  public ApplyResult applyChassisDiscretization(boolean teleop, boolean auto, double dtSeconds) {
    applied.add("disc");
    return ApplyResult.ok("disc");
  }

  @Override
  public ApplyResult useAbsoluteSteerFeedback() {
    applied.add("absolute");
    return ApplyResult.failed("fake: no absolute feedback");
  }

  @Override
  public double[] steerPid() {
    return steerPid.clone();
  }

  @Override
  public double[] drivePid() {
    return drivePid.clone();
  }

  @Override
  public double[] rampRates() {
    return new double[] {0.25, 0.25};
  }

  @Override
  public double[] driveFeedforward(int m) {
    return ff[m].clone();
  }

  @Override
  public MotorGuard.MotorChannel steerMotorChannel(int m) {
    return steerMotors[m];
  }

  @Override
  public MotorKind steerMotorKind() {
    return MotorKind.NEO_550;
  }
}
