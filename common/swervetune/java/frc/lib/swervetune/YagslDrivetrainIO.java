package frc.lib.swervetune;

import com.revrobotics.PersistMode;
import com.revrobotics.REVLibError;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkBase;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkFlexConfig;
import com.revrobotics.spark.config.SparkMaxConfig;
import edu.wpi.first.math.controller.SimpleMotorFeedforward;
import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.math.kinematics.ChassisSpeeds;
import edu.wpi.first.math.kinematics.SwerveModuleState;
import edu.wpi.first.wpilibj.RobotController;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.function.Consumer;
import swervelib.SwerveDrive;
import swervelib.SwerveModule;
import swervelib.motors.SwerveMotor;
import swervelib.parser.PIDFConfig;
import swervelib.telemetry.SwerveDriveTelemetry;

/**
 * {@link DrivetrainIO} for YAGSL 2026.4.x on REV SPARK MAX and SPARK Flex.
 *
 * <p>The only class in the library that knows YAGSL or REVLib exist. Facts it depends on, each
 * checked against the YAGSL 2026.4.1 and REVLib 2026.0.5 sources rather than assumed:
 *
 * <ul>
 *   <li>YAGSL's {@code setAnglePIDF} and {@code setDrivePIDF} only edit YAGSL's own copy of the
 *       configuration. Nothing reaches the controller until the configuration is re-sent, and YAGSL
 *       re-sends it <b>with flash persistence whenever the robot is disabled</b>. So live changes are
 *       also sent here directly, as a minimal configuration, with {@link PersistMode#kNoPersistParameters}.
 *       REVLib only sends the parameters a configuration object actually sets.
 *   <li>The {@code "f"} value in {@code pidfproperties.json} is never sent to a SPARK by YAGSL. The
 *       drive feedforward is a separate {@link SimpleMotorFeedforward} on each module, which defaults
 *       to kS = 0, kV = 12 / theoretical free speed, kA = 0. {@link #applyDriveFeedforward} replaces it.
 *   <li>YAGSL's ramp rate applies to the <b>closed</b> loop as well as open loop, so a steering ramp
 *       rate slows every steering correction.
 *   <li>YAGSL sets the {@code quadrature} velocity filter, which a NEO's built-in hall sensor does not
 *       use; on a SPARK MAX the hall sensor's filter is the separate {@code uvw} setting.
 *   <li>The steering PID runs on the absolute encoder only when the steering conversion factor is
 *       exactly 360, and even then YAGSL keeps the offset in software unless
 *       {@code useExternalFeedbackSensor()} pushes it into the SPARK. {@link #useAbsoluteSteerFeedback}
 *       does both checks.
 *   <li>In simulation YAGSL's modules are driven by maple-sim's own controllers. Gains do nothing
 *       there; module angle and voltage go through maple-sim's characterisation hooks instead.
 * </ul>
 */
public final class YagslDrivetrainIO implements DrivetrainIO {
  private final SwerveDrive drive;
  private final SwerveModule[] modules;
  private final double[] steerCommandDeg;
  private final double[] driveCommandMps;
  private final double[] driveCommandVolts;
  private final double[][] feedforward;
  private final boolean sim;

  public YagslDrivetrainIO(SwerveDrive drive) {
    this.drive = drive;
    this.modules = drive.getModules();
    this.sim = SwerveDriveTelemetry.isSimulation;
    int n = modules.length;
    steerCommandDeg = new double[n];
    driveCommandMps = new double[n];
    driveCommandVolts = new double[n];
    feedforward = new double[n][];
    for (int m = 0; m < n; m++) {
      steerCommandDeg[m] = Double.NaN;
      driveCommandMps[m] = Double.NaN;
      SimpleMotorFeedforward ff = modules[m].getDefaultFeedforward();
      feedforward[m] = new double[] {ff.getKs(), ff.getKv(), ff.getKa()};
    }
  }

  // ------------------------------------------------------------------ identity

  @Override
  public int moduleCount() {
    return modules.length;
  }

  @Override
  public String moduleName(int m) {
    return modules[m].configuration.name;
  }

  @Override
  public double[] moduleLocationM(int m) {
    Translation2d t = modules[m].configuration.moduleLocation;
    return new double[] {t.getX(), t.getY()};
  }

  @Override
  public double maxModuleSpeedMps() {
    return drive.getMaximumModuleDriveVelocity();
  }

  @Override
  public double driveCurrentLimitA() {
    return modules[0].configuration.physicalCharacteristics.driveMotorCurrentLimit;
  }

  @Override
  public double driveGearRatio() {
    return modules[0].configuration.conversionFactors.drive.gearRatio;
  }

  @Override
  public double steerGearRatio() {
    return modules[0].configuration.conversionFactors.angle.gearRatio;
  }

  @Override
  public String steerFeedback() {
    return modules[0].getAngleMotor().usingExternalFeedbackSensor() ? "absolute" : "motor";
  }

  // ------------------------------------------------------------------ reads

  @Override
  public double steerDeg(int m) {
    return modules[m].getAbsolutePosition();
  }

  @Override
  public double steerRawDeg(int m) {
    if (sim || modules[m].getAbsoluteEncoder() == null) {
      return modules[m].getAbsolutePosition();
    }
    return modules[m].getAbsoluteEncoder().getAbsolutePosition();
  }

  @Override
  public double steerMotorDeg(int m) {
    return modules[m].getRelativePosition();
  }

  @Override
  public double steerSetpointDeg(int m) {
    if (Double.isFinite(steerCommandDeg[m])) {
      return steerCommandDeg[m];
    }
    SwerveModuleState[] desired = SwerveDriveTelemetry.desiredStatesObj;
    return desired != null && desired[m] != null ? desired[m].angle.getDegrees() : Double.NaN;
  }

  @Override
  public double driveMps(int m) {
    return sim ? modules[m].getState().speedMetersPerSecond : modules[m].getDriveMotor().getVelocity();
  }

  @Override
  public double drivePositionM(int m) {
    return sim ? modules[m].getPosition().distanceMeters : modules[m].getDriveMotor().getPosition();
  }

  @Override
  public double driveSetpointMps(int m) {
    if (Double.isFinite(driveCommandMps[m])) {
      return driveCommandMps[m];
    }
    SwerveModuleState[] desired = SwerveDriveTelemetry.desiredStatesObj;
    return desired != null && desired[m] != null ? desired[m].speedMetersPerSecond : Double.NaN;
  }

  private static SparkBase spark(SwerveMotor motor) {
    return motor.getMotor() instanceof SparkBase s ? s : null;
  }

  private static double volts(SwerveMotor motor) {
    SparkBase s = spark(motor);
    return s == null ? motor.getVoltage() : s.getAppliedOutput() * s.getBusVoltage();
  }

  @Override
  public double driveVolts(int m) {
    // In simulation YAGSL drives maple-sim directly and the SPARK never sees the command, so its
    // applied output reads zero; report what was commanded instead.
    return sim ? driveCommandVolts[m] : volts(modules[m].getDriveMotor());
  }

  @Override
  public double steerVolts(int m) {
    return volts(modules[m].getAngleMotor());
  }

  @Override
  public double driveAmps(int m) {
    SparkBase s = spark(modules[m].getDriveMotor());
    return s == null ? Double.NaN : s.getOutputCurrent();
  }

  @Override
  public double steerAmps(int m) {
    SparkBase s = spark(modules[m].getAngleMotor());
    return s == null ? Double.NaN : s.getOutputCurrent();
  }

  @Override
  public double driveTempC(int m) {
    SparkBase s = spark(modules[m].getDriveMotor());
    return s == null ? Double.NaN : s.getMotorTemperature();
  }

  @Override
  public double steerTempC(int m) {
    SparkBase s = spark(modules[m].getAngleMotor());
    return s == null ? Double.NaN : s.getMotorTemperature();
  }

  @Override
  public String faults(int m) {
    List<String> out = new ArrayList<>();
    describe("drive", spark(modules[m].getDriveMotor()), out);
    describe("steer", spark(modules[m].getAngleMotor()), out);
    return String.join(", ", out);
  }

  private static void describe(String which, SparkBase s, List<String> out) {
    if (s == null) {
      return;
    }
    if (s.hasActiveFault()) {
      SparkBase.Faults f = s.getFaults();
      if (f.can) out.add(which + " CAN fault");
      if (f.sensor) out.add(which + " sensor fault");
      if (f.motorType) out.add(which + " motor type fault");
      if (f.temperature) out.add(which + " over temperature");
      if (f.gateDriver) out.add(which + " gate driver fault");
      if (f.escEeprom) out.add(which + " EEPROM fault");
      if (f.firmware) out.add(which + " firmware fault");
      if (f.other) out.add(which + " fault");
    }
    if (s.hasActiveWarning()) {
      SparkBase.Warnings w = s.getWarnings();
      if (w.brownout) out.add(which + " brownout");
      if (w.overcurrent) out.add(which + " overcurrent");
      if (w.stall) out.add(which + " stall");
      if (w.sensor) out.add(which + " sensor warning");
      if (w.hasReset) out.add(which + " controller reset");
      if (w.escEeprom || w.extEeprom) out.add(which + " EEPROM warning");
    }
    if (s.getLastError() != REVLibError.kOk) {
      out.add(which + " " + s.getLastError());
    }
  }

  @Override
  public boolean absoluteReadIssue(int m) {
    return !sim && modules[m].getAbsoluteEncoderReadIssue();
  }

  @Override
  public double headingDeg() {
    return drive.getYaw().getDegrees();
  }

  @Override
  public Optional<double[]> accelMps2() {
    return drive.getAccel().map(a -> new double[] {a.getX(), a.getY(), a.getZ()});
  }

  @Override
  public double[] pose() {
    Pose2d p = drive.getPose();
    return new double[] {p.getX(), p.getY(), p.getRotation().getDegrees()};
  }

  @Override
  public double busVolts() {
    return RobotController.getBatteryVoltage();
  }

  // ------------------------------------------------------------------ actuation

  @Override
  public void setSteerDeg(int m, double degrees) {
    double wrapped = ((degrees % 360) + 360) % 360;
    steerCommandDeg[m] = wrapped;
    if (sim) {
      return; // applied with the drive voltage below, through maple-sim
    }
    modules[m].getAngleMotor().setReference(wrapped, 0);
  }

  @Override
  public void setDriveVolts(int m, double volts) {
    driveCommandMps[m] = Double.NaN;
    driveCommandVolts[m] = volts;
    if (sim) {
      double angle = Double.isFinite(steerCommandDeg[m]) ? steerCommandDeg[m] : steerDeg(m);
      modules[m].getSimModule().runDriveMotorCharacterization(Rotation2d.fromDegrees(angle), volts);
      return;
    }
    modules[m].getDriveMotor().setVoltage(volts);
  }

  @Override
  public void setModuleState(int m, double speedMps, double angleDeg) {
    steerCommandDeg[m] = Double.NaN;
    driveCommandMps[m] = speedMps;
    modules[m].setDesiredState(new SwerveModuleState(speedMps, Rotation2d.fromDegrees(angleDeg)), false, true);
  }

  @Override
  public void driveRobotRelative(double vx, double vy, double omega) {
    clearCommands();
    drive.drive(new ChassisSpeeds(vx, vy, omega), false, new Translation2d());
  }

  private void clearCommands() {
    for (int m = 0; m < modules.length; m++) {
      steerCommandDeg[m] = Double.NaN;
      driveCommandMps[m] = Double.NaN;
      driveCommandVolts[m] = Double.NaN;
    }
  }

  @Override
  public void stop() {
    clearCommands();
    if (sim) {
      drive.drive(new ChassisSpeeds(), false, new Translation2d());
      return;
    }
    // Zero volts in brake mode, rather than a closed-loop "go to zero": if the velocity loop is the
    // thing misbehaving, asking it to stop is asking the faulty part for help.
    for (SwerveModule module : modules) {
      module.getDriveMotor().setVoltage(0);
      module.getAngleMotor().setReference(module.getAbsolutePosition(), 0);
    }
  }

  // ------------------------------------------------------------------ live configuration

  /** Sends a minimal configuration to every SPARK of one kind, never persisted. */
  private ApplyResult configureAll(boolean driveMotors, boolean steerMotors, Consumer<SparkBaseConfig> edit) {
    if (sim) {
      return ApplyResult.ok("simulation: recorded only");
    }
    List<String> failures = new ArrayList<>();
    for (SwerveModule module : modules) {
      List<SwerveMotor> targets = new ArrayList<>();
      if (driveMotors) {
        targets.add(module.getDriveMotor());
      }
      if (steerMotors) {
        targets.add(module.getAngleMotor());
      }
      for (SwerveMotor motor : targets) {
        SparkBase s = spark(motor);
        if (s == null) {
          failures.add(module.configuration.name + " is not a SPARK");
          continue;
        }
        SparkBaseConfig cfg = s instanceof SparkFlex ? new SparkFlexConfig() : new SparkMaxConfig();
        edit.accept(cfg);
        REVLibError err = s.configure(cfg, ResetMode.kNoResetSafeParameters, PersistMode.kNoPersistParameters);
        if (err != REVLibError.kOk) {
          failures.add(module.configuration.name + " CAN " + s.getDeviceId() + ": " + err);
        }
      }
    }
    return failures.isEmpty() ? ApplyResult.ok("") : ApplyResult.failed(String.join("; ", failures));
  }

  private static ApplyResult label(ApplyResult r, String what) {
    return r.ok()
        ? ApplyResult.ok(what + (r.message().isEmpty() ? "" : " (" + r.message() + ")"))
        : ApplyResult.failed(what + " failed: " + r.message());
  }

  @Override
  public ApplyResult setCoast(boolean coast) {
    // Restoring puts back YAGSL's own choice: drive in brake, steering in coast.
    ApplyResult d = configureAll(true, false, c -> c.idleMode(coast ? IdleMode.kCoast : IdleMode.kBrake));
    ApplyResult s = configureAll(false, true, c -> c.idleMode(IdleMode.kCoast));
    return d.ok() && s.ok()
        ? ApplyResult.ok(coast ? "all motors coasting" : "drive motors back in brake")
        : ApplyResult.failed(d.message() + " " + s.message());
  }

  @Override
  public ApplyResult applySteerPid(double kP, double kI, double kD, double iZone) {
    for (SwerveModule module : modules) {
      module.setAnglePIDF(new PIDFConfig(kP, kI, kD, 0, iZone));
    }
    return label(configureAll(false, true, c -> c.closedLoop.pid(kP, kI, kD).iZone(iZone)),
        String.format("steer PID %.5g/%.3g/%.4g", kP, kI, kD));
  }

  @Override
  public ApplyResult applyDrivePid(double kP, double kI, double kD, double iZone) {
    for (SwerveModule module : modules) {
      module.setDrivePIDF(new PIDFConfig(kP, kI, kD, 0, iZone));
    }
    return label(configureAll(true, false, c -> c.closedLoop.pid(kP, kI, kD).iZone(iZone)),
        String.format("drive PID %.5g/%.3g/%.4g", kP, kI, kD));
  }

  @Override
  public ApplyResult applyDriveFeedforward(int m, double kS, double kV, double kA) {
    modules[m].setFeedforward(new SimpleMotorFeedforward(kS, kV, kA));
    feedforward[m] = new double[] {kS, kV, kA};
    return ApplyResult.ok(String.format("%s feedforward kS %.3f kV %.3f kA %.3f",
        moduleName(m), kS, kV, kA));
  }

  @Override
  public ApplyResult applyRampRates(double steerSeconds, double driveSeconds) {
    ApplyResult s = configureAll(false, true,
        c -> c.closedLoopRampRate(steerSeconds).openLoopRampRate(steerSeconds));
    ApplyResult d = configureAll(true, false,
        c -> c.closedLoopRampRate(driveSeconds).openLoopRampRate(driveSeconds));
    return s.ok() && d.ok()
        ? ApplyResult.ok(String.format("ramp steer %.2f s, drive %.2f s", steerSeconds, driveSeconds))
        : ApplyResult.failed("ramp rates failed: " + s.message() + " " + d.message());
  }

  @Override
  public ApplyResult applyDriveVelocityFilter(int periodMs, int depth) {
    if (sim) {
      return ApplyResult.ok("simulation: velocity filter recorded only");
    }
    List<String> failures = new ArrayList<>();
    for (SwerveModule module : modules) {
      SparkBase s = spark(module.getDriveMotor());
      if (s == null) {
        continue;
      }
      REVLibError err;
      if (s instanceof SparkMax max) {
        SparkMaxConfig cfg = new SparkMaxConfig();
        // A NEO's built-in encoder is a hall sensor: the uvw settings, not quadrature.
        cfg.encoder.uvwMeasurementPeriod(periodMs).uvwAverageDepth(depth);
        err = max.configure(cfg, ResetMode.kNoResetSafeParameters, PersistMode.kNoPersistParameters);
      } else {
        SparkFlexConfig cfg = new SparkFlexConfig();
        cfg.encoder.quadratureMeasurementPeriod(periodMs).quadratureAverageDepth(depth);
        err = s.configure(cfg, ResetMode.kNoResetSafeParameters, PersistMode.kNoPersistParameters);
      }
      if (err != REVLibError.kOk) {
        failures.add(module.configuration.name + ": " + err);
      }
    }
    return failures.isEmpty()
        ? ApplyResult.ok(String.format("drive velocity filter %d ms x %d", periodMs, depth))
        : ApplyResult.failed("velocity filter failed: " + String.join("; ", failures));
  }

  @Override
  public ApplyResult applyFastTelemetry(boolean fast) {
    // Restores YAGSL's own periods: absolute and motor position 20 ms, applied output 10 ms.
    int pos = fast ? 5 : 20;
    int out = fast ? 5 : 10;
    ApplyResult s = configureAll(false, true, c -> c.signals
        .absoluteEncoderPositionPeriodMs(pos)
        .primaryEncoderPositionPeriodMs(pos)
        .appliedOutputPeriodMs(out));
    ApplyResult d = configureAll(true, false, c -> c.signals
        .primaryEncoderVelocityPeriodMs(fast ? 5 : 20)
        .appliedOutputPeriodMs(out));
    return s.ok() && d.ok()
        ? ApplyResult.ok(fast ? "fast status frames" : "normal status frames")
        : ApplyResult.failed(s.message() + " " + d.message());
  }

  @Override
  public ApplyResult applyEncoderAutoSync(boolean enabled, double deadbandDeg) {
    drive.setModuleEncoderAutoSynchronize(enabled, deadbandDeg);
    return ApplyResult.ok(enabled
        ? String.format("steering encoder auto-sync on, %.2f deg deadband", deadbandDeg)
        : "steering encoder auto-sync off");
  }

  @Override
  public ApplyResult applyAngularVelocityCompensation(boolean teleop, boolean auto, double coefficient) {
    drive.setAngularVelocityCompensation(teleop, auto, coefficient);
    return ApplyResult.ok(String.format("angular velocity compensation %.3f (teleop %s, auto %s)%s",
        coefficient, teleop, auto, sim ? " - YAGSL ignores this in simulation" : ""));
  }

  @Override
  public ApplyResult applyChassisDiscretization(boolean teleop, boolean auto, double dtSeconds) {
    drive.setChassisDiscretization(teleop, auto, dtSeconds);
    return ApplyResult.ok(String.format("chassis discretization teleop %s, auto %s, dt %.3f%s",
        teleop, auto, dtSeconds, sim ? " - YAGSL ignores this in simulation" : ""));
  }

  @Override
  public ApplyResult useAbsoluteSteerFeedback() {
    for (SwerveModule module : modules) {
      if (module.configuration.conversionFactors.angle.factor != 360) {
        return ApplyResult.failed(String.format(
            "needs \"angle\": {\"factor\": 360} in physicalproperties.json; %s has %.4f. Steering"
                + " stays on the motor encoder.",
            module.configuration.name, module.configuration.conversionFactors.angle.factor));
      }
    }
    drive.useExternalFeedbackSensor();
    for (SwerveModule module : modules) {
      if (!module.getAngleMotor().usingExternalFeedbackSensor()) {
        return ApplyResult.failed(module.configuration.name
            + " refused the absolute encoder as feedback; steering stays on the motor encoder.");
      }
    }
    return ApplyResult.ok("steering on the absolute encoder, offsets pushed to each SPARK");
  }

  // ------------------------------------------------------------------ what is applied

  @Override
  public double[] steerPid() {
    PIDFConfig p = modules[0].getAnglePIDF();
    return new double[] {p.p, p.i, p.d, p.iz};
  }

  @Override
  public double[] drivePid() {
    PIDFConfig p = modules[0].getDrivePIDF();
    return new double[] {p.p, p.i, p.d, p.iz};
  }

  @Override
  public double[] rampRates() {
    var pc = modules[0].configuration.physicalCharacteristics;
    return new double[] {pc.angleMotorRampRate, pc.driveMotorRampRate};
  }

  @Override
  public double[] driveFeedforward(int m) {
    return feedforward[m].clone();
  }
}
