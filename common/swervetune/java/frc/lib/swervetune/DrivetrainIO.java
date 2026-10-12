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
 * <p>Units are fixed here so they cannot drift: metres, metres per second, degrees, volts, amps.
 * Angles are counter-clockwise positive seen from above, as WPILib uses them.
 */
public interface DrivetrainIO {

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

  /** Module position from robot centre, metres, {@code {x, y}}. */
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

  /** Field-frame acceleration, m/s^2, {@code {x, y, z}}, if the IMU reports it. */
  Optional<double[]> accelMps2();

  /** Odometry pose, {@code {x m, y m, heading deg}}. */
  double[] pose();

  double busVolts();

  // ------------------------------------------------------------------ actuation, for tests only
  /** Drives one module's steering to an angle, directly, with no optimisation or anti-jitter. */
  void setSteerDeg(int module, double degrees);

  /** Open-loop drive voltage for one module. */
  void setDriveVolts(int module, double volts);

  /**
   * One module through the same path teleop uses: optimisation, cosine compensation and the
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

  /** {@code {steer seconds, drive seconds}}. */
  double[] rampRates();

  /** {@code {kS, kV, kA}} currently used by one module. */
  double[] driveFeedforward(int module);
}
