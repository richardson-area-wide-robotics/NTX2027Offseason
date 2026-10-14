package frc.lib.swervetune;

import java.util.Optional;

/**
 * Everything the tuning harness needs from a swerve drivetrain, and nothing else.
 *
 * <p>The harness talks only to this interface. {@link YagslDrivetrainIO} implements it for YAGSL on
 * REV hardware, and the unit tests implement it with a fake. That split is the future-proofing:
 * when WPILib 2027, SystemCore, a new YAGSL or a different motor vendor changes how a module is
 * read or driven, the change is confined to one adapter class, and every test procedure, safety
 * rule and laptop tool carries on unchanged.
 *
 * <p>Units are fixed here so they cannot drift: meters, meters per second, degrees, volts, amps.
 * Angles are counter-clockwise positive seen from above, as WPILib uses them.
 */
public interface DrivetrainIO {

  /**
   * What the gyro is and whether it can be trusted right now.
   *
   * @param type what is fitted, e.g. {@code navX}, {@code Canandgyro}, {@code simulated}
   * @param connected reporting at all
   * @param calibrating still settling after power-on; it must be kept still until this is false
   * @param faults active faults, comma separated; empty when healthy
   */
  record GyroStatus(String type, boolean connected, boolean calibrating, String faults) {}

  /**
   * Starts the gyro's own calibration: a Canandgyro's takes about 7 s with the robot kept still. A
   * gyro that calibrates only when it powers on (a navX) says so.
   */
  default ApplyResult gyroCalibrate() {
    return ApplyResult.failed("This gyro calibrates itself when it powers on; there is nothing to start.");
  }

  /** Blinks the gyro's light so a person can find it on the robot, or stops (a Canandgyro's party mode). */
  default ApplyResult gyroIdentify(boolean on) {
    return ApplyResult.failed("This gyro has no light the robot code can blink.");
  }

  /** Clears the faults the gyro remembers after they have gone (its sticky faults). */
  default ApplyResult gyroClearStickyFaults() {
    return ApplyResult.failed("This gyro keeps no sticky faults.");
  }

  /** More about the gyro, as "name=value" lines (temperature, firmware, sticky); empty when unknown. */
  default String[] gyroDetails() {
    return new String[0];
  }

  /**
   * How often the gyro reports each reading, in seconds (0 leaves one as it is): a Canandgyro's yaw,
   * angular position, angular velocity, acceleration and status frames. Not saved on the gyro, so it
   * is applied at every startup (YAGSL resets the gyro to its factory settings when it starts). An
   * empty message means this gyro has no such settings.
   */
  default ApplyResult applyGyroFramePeriods(double yawS, double angularPositionS, double angularVelocityS,
      double accelerationS, double statusS) {
    return ApplyResult.ok("");
  }

  /** Result of a live configuration change. */
  record ApplyResult(boolean ok, String message) {
    public static ApplyResult ok(String message) {
      return new ApplyResult(true, message);
    }

    public static ApplyResult failed(String message) {
      return new ApplyResult(false, message);
    }
  }

  // ------------------------------------------------------------------ identity
  int moduleCount();

  /** Configuration name, e.g. {@code frontleft}. */
  String moduleName(int module);

  /** Module position from robot center, meters, {@code {x, y}}. */
  double[] moduleLocationM(int module);

  /** Free speed of a module from motor, gearing and wheel diameter, m/s. */
  double maxModuleSpeedMps();

  /** Drive current limit from the configuration, amps. */
  double driveCurrentLimitA();

  /** Configured drive reduction, motor turns per wheel turn. */
  double driveGearRatio();

  /** Configured steering reduction, motor turns per module turn. */
  double steerGearRatio();

  /** {@code motor} or {@code absolute}: what the steering PID uses for feedback. */
  String steerFeedback();

  // ------------------------------------------------------------------ per-module reads
  /** Steering angle as YAGSL believes it, offset applied, [0, 360). */
  double steerDeg(int module);

  /** Absolute encoder exactly as the sensor reports it, before any YAGSL offset. */
  double steerRawDeg(int module);

  /** The steering motor's own encoder in module degrees. Not wrapped. */
  double steerMotorDeg(int module);

  /** Last steering setpoint sent, degrees, or NaN if none. */
  double steerSetpointDeg(int module);

  double driveMps(int module);

  double drivePositionM(int module);

  /** Last drive setpoint sent, m/s, or NaN if none. */
  double driveSetpointMps(int module);

  double driveVolts(int module);

  double steerVolts(int module);

  double driveAmps(int module);

  double steerAmps(int module);

  double driveTempC(int module);

  double steerTempC(int module);

  /** Active faults and warnings for both controllers, comma separated; empty when healthy. */
  String faults(int module);

  /** True when the last absolute encoder read failed and YAGSL fell back to the motor encoder. */
  boolean absoluteReadIssue(int module);

  // ------------------------------------------------------------------ chassis reads
  /** Heading as odometry uses it, degrees, counter-clockwise positive. Unwrapped is not required. */
  double headingDeg();

  /**
   * The gyro's own roll and pitch, degrees, before any zeroing: on a level floor, how far the gyro
   * is mounted off level. NaN when the gyro can't say.
   */
  default double[] gyroTiltDeg() {
    return new double[] {Double.NaN, Double.NaN};
  }

  /**
   * Acceleration, m/s^2, {@code {x, y, z}}, if the IMU reports it. A navX gives it in the field frame
   * with gravity removed; a Canandgyro in its own frame with gravity in z. Horizontal magnitude, which
   * is all the safety rules use, is the same either way for a gyro mounted flat.
   */
  Optional<double[]> accelMps2();

  /** The gyro's health. Motion tests wait for a calibrating gyro and stop if it drops out. */
  GyroStatus gyroStatus();

  /** Odometry pose, {@code {x m, y m, heading deg}}. */
  double[] pose();

  /**
   * One camera pose for the drivetrain's own pose estimator, with how far to trust it (standard
   * deviations: meters for x and y, radians for heading). Does nothing on a drivetrain without one.
   */
  default void addVisionMeasurement(double xM, double yM, double headingDeg, double timestampS,
      double sdXyM, double sdHeadingRad) {}

  double busVolts();

  /**
   * The voltage the motor controllers compensate to, or NaN if they don't. YAGSL turns voltage
   * compensation on for every module at {@code optimalVoltage} (12 V): a closed-loop output of 0.5
   * then means 6 V whatever the battery reads, until the battery sags below what is asked.
   */
  default double compensationVolts() {
    return Double.NaN;
  }

  // ------------------------------------------------------------------ actuation, for tests only
  /** Drives one module's steering to an angle, directly, with no optimization or anti-jitter. */
  void setSteerDeg(int module, double degrees);

  /** Open-loop drive voltage for one module. */
  void setDriveVolts(int module, double volts);

  /**
   * One module through the same path teleop uses: optimization, cosine compensation and the
   * module's drive feedforward. This is what a velocity step should exercise.
   */
  void setModuleState(int module, double speedMps, double angleDeg);

  /** Whole-chassis command through kinematics, robot-relative. */
  void driveRobotRelative(double vxMps, double vyMps, double omegaRadPerS);

  /** Zero output on every motor. */
  void stop();

  // ------------------------------------------------------------------ live configuration, never persisted
  /** Coast or brake on every motor. Only ever called while disabled. */
  ApplyResult setCoast(boolean coast);

  ApplyResult applySteerPid(double kP, double kI, double kD, double iZone);

  ApplyResult applyDrivePid(double kP, double kI, double kD, double iZone);

  /** One pod's steering PID; the other pods keep theirs. */
  default ApplyResult applySteerPid(int module, double kP, double kI, double kD, double iZone) {
    return ApplyResult.failed("this drivetrain sets steering gains on every pod at once");
  }

  /** One pod's drive PID; the other pods keep theirs. */
  default ApplyResult applyDrivePid(int module, double kP, double kI, double kD, double iZone) {
    return ApplyResult.failed("this drivetrain sets drive gains on every pod at once");
  }

  /** Drive feedforward for one module: volts = kS*sgn(v) + kV*v + kA*a. */
  ApplyResult applyDriveFeedforward(int module, double kS, double kV, double kA);

  ApplyResult applyRampRates(double steerSeconds, double driveSeconds);

  /** How the drive motor's built-in encoder turns counts into a velocity. Lag versus noise. */
  ApplyResult applyDriveVelocityFilter(int periodMs, int averageDepth);

  /** Faster status frames while a test samples, slower again after. */
  ApplyResult applyFastTelemetry(boolean fast);

  /** Re-syncs the steering motor encoder to the absolute encoder when the module is still. */
  ApplyResult applyEncoderAutoSync(boolean enabled, double deadbandDeg);

  /** YAGSL's translate-while-rotating skew correction. A coefficient of 0 does nothing. */
  ApplyResult applyAngularVelocityCompensation(boolean teleop, boolean auto, double coefficient);

  /** Discretises chassis speeds over one loop so translating while turning does not skew. */
  ApplyResult applyChassisDiscretization(boolean teleop, boolean auto, double dtSeconds);

  /**
   * Startup only: steer on the absolute encoder instead of the motor encoder. Needs the steering
   * conversion factor to be 360 in the YAGSL configuration; refuses otherwise.
   */
  ApplyResult useAbsoluteSteerFeedback();

  // ------------------------------------------------------------------ what is applied now
  /** {@code {kP, kI, kD, iZone}} in the controller's own units. */
  double[] steerPid();

  double[] drivePid();

  /** One pod's steering PID, {@code {kP, kI, kD, iZone}}. */
  default double[] steerPid(int module) {
    return steerPid();
  }

  /** One pod's drive PID. */
  default double[] drivePid(int module) {
    return drivePid();
  }

  /** {@code {steer seconds, drive seconds}}. */
  double[] rampRates();

  /** {@code {kS, kV, kA}} currently used by one module. */
  double[] driveFeedforward(int module);

  /**
   * Sets every drive motor's smart current limit, never saved to flash. For the slip test, which
   * raises it for the run and puts it back.
   */
  default ApplyResult setDriveCurrentLimit(int amps) {
    return ApplyResult.failed("this drivetrain cannot change its current limit");
  }

  // ------------------------------------------------------------------ motor protection
  /** One module's drive motor controller, for the {@link MotorGuard}; null if it cannot be watched. */
  default MotorGuard.MotorChannel driveMotorChannel(int module) {
    return null;
  }

  default MotorGuard.MotorChannel steerMotorChannel(int module) {
    return null;
  }

  /** The best guess at what the drive motors are, before swervetune.json's inventory says. */
  default MotorKind driveMotorKind() {
    return MotorKind.NEO_UNKNOWN;
  }

  default MotorKind steerMotorKind() {
    return MotorKind.NEO_UNKNOWN;
  }
}
