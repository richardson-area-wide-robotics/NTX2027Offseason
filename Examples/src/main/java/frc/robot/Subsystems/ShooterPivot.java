package frc.robot.Subsystems;

import com.revrobotics.AbsoluteEncoder;
import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;
import com.revrobotics.sim.SparkAbsoluteEncoderSim;
import com.revrobotics.sim.SparkMaxSim;
import com.revrobotics.spark.FeedbackSensor;
import com.revrobotics.spark.SparkBase.ControlType;
import com.revrobotics.spark.SparkClosedLoopController;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkMaxConfig;

import edu.wpi.first.math.system.plant.DCMotor;
import edu.wpi.first.math.trajectory.TrapezoidProfile;
import edu.wpi.first.math.util.Units;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.RobotBase;
import edu.wpi.first.wpilibj.simulation.RoboRioSim;
import edu.wpi.first.wpilibj.simulation.SingleJointedArmSim;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.lib.swervetune.MotorKind;
import frc.lib.swervetune.MotorWatcher;
import frc.lib.swervetune.SwerveTune;
import frc.lib.swervetune.TunableSystem;
import java.util.function.DoubleSupplier;
import org.littletonrobotics.junction.Logger;

/**
 * A shooter pivot, from 2024 Crescendo (Pivot.java, the same on team 8874's state code and team
 * 1745's branches): two NEOs on SPARK MAXes, the left following the right, and a through-bore
 * absolute encoder on the pivot shaft read by the right SPARK.
 *
 * <p>What changed for 2027:
 * <ul>
 *   <li>Angles are degrees from the absolute encoder. 2024 used its raw 0-1 rotations, and sent
 *       presets declared in radians as if they were rotations.</li>
 *   <li>kCos holds it against gravity, and a motion profile moves its goal smoothly. 2024 had
 *       position PID only (P 4.0 per rotation), straight to each preset.</li>
 *   <li>Goals stay inside its travel in code. 2024's SPARK soft limits most likely acted on the
 *       motor's own encoder, not the absolute encoder: check that on the real robot before trusting
 *       them.</li>
 *   <li>The camera aim is kept: atan2(speaker height, distance).</li>
 * </ul>
 *
 * <p>The 2024 code had no gear ratio, arm length or mass. GEARING, ARM_M and ARM_KG are assumed for
 * the simulator; the encoder's zero, its resting angle, is assumed level for kCos.
 */
public class ShooterPivot extends SubsystemBase {

  // Assumed (see above).
  private static final double GEARING = 60.0;
  private static final double ARM_M = 0.3;
  private static final double ARM_KG = 6.0;

  // 2024's presets and soft limits, which were absolute-encoder rotations, as degrees.
  public static final double REST = 0.015 * 360;       // 5.4
  public static final double RANGE = 0.095 * 360;      // 34.2, "works for the second 8"
  public static final double SUBWOOFER = 0.135 * 360;  // 48.6
  public static final double AMP = 0.31 * 360;         // 111.6
  public static final double MIN = 0.01 * 360;         // 3.6
  public static final double MAX = 0.31 * 360;         // 111.6
  /** The speaker opening's height the 2024 aim used: 79 in. */
  private static final double SPEAKER_HEIGHT_M = Units.inchesToMeters(79);
  private static final double TOLERANCE = 1.0;

  // 2024: P 4.0 per rotation is 4.0 / 360 per degree. kCos is what the assumed physics give.
  private static final double kP = 4.0 / 360;
  private static final double kD = 0.5 / 360;
  private static final double kCos = 0.42;   // volts to hold it level
  private static final double CRUISE_DPS = 120;
  private static final double ACCEL_DPS2 = 400;

  // 2024: right CAN 9 (the leader), left CAN 10.
  private final SparkMax right = new SparkMax(52, MotorType.kBrushless);
  private final SparkMax left = new SparkMax(53, MotorType.kBrushless);
  private final SparkClosedLoopController controller = right.getClosedLoopController();
  private final AbsoluteEncoder angle = right.getAbsoluteEncoder();

  private double target = REST;
  private final TrapezoidProfile profile = new TrapezoidProfile(new TrapezoidProfile.Constraints(CRUISE_DPS, ACCEL_DPS2));
  private TrapezoidProfile.State setpoint = new TrapezoidProfile.State(REST, 0);

  private SparkMaxSim motorSim;
  private SparkAbsoluteEncoderSim angleSim;
  private SingleJointedArmSim armSim;

  public ShooterPivot() {
    SparkMaxConfig config = new SparkMaxConfig();
    config.idleMode(IdleMode.kBrake).smartCurrentLimit(40).inverted(true);
    // Both encoders in degrees of the pivot: the absolute one on its shaft, the motor's through GEARING.
    config.absoluteEncoder.positionConversionFactor(360).velocityConversionFactor(6.0);
    config.encoder.positionConversionFactor(360 / GEARING).velocityConversionFactor(6.0 / GEARING);
    config.closedLoop.feedbackSensor(FeedbackSensor.kAbsoluteEncoder).p(kP).d(kD).positionWrappingEnabled(false);
    // kCosRatio turns the encoder's degrees into rotations of the pivot for the cosine.
    config.closedLoop.feedForward.kCos(kCos).kCosRatio(1.0 / 360);
    right.configure(config, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);

    SparkMaxConfig follower = new SparkMaxConfig();
    follower.idleMode(IdleMode.kBrake).smartCurrentLimit(40).follow(right, true);
    left.configure(follower, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);

    if (RobotBase.isSimulation()) {
      DCMotor neos = DCMotor.getNEO(2);
      motorSim = new SparkMaxSim(right, neos);
      angleSim = motorSim.getAbsoluteEncoderSim();
      // WPILib's arm is a uniform rod, its weight halfway out: 1.5 times this point mass's distance
      // pulls the same, so kCos from the physics holds it.
      armSim = new SingleJointedArmSim(neos, GEARING, ARM_KG * ARM_M * ARM_M, 1.5 * ARM_M,
          Math.toRadians(MIN), Math.toRadians(MAX), true, Math.toRadians(REST));
      angleSim.setPosition(REST);
    }
  }

  @Override
  public void periodic() {
    if (DriverStation.isDisabled()) {
      holdHere();
    } else {
      setpoint = profile.calculate(0.02, setpoint, new TrapezoidProfile.State(target, 0));
      controller.setSetpoint(setpoint.position, ControlType.kPosition);
    }
    Logger.recordOutput("ShooterPivot/GoalDegrees", target);
    Logger.recordOutput("ShooterPivot/AngleDegrees", angle.getPosition());
  }

  @Override
  public void simulationPeriodic() {
    double volts = RoboRioSim.getVInVoltage();
    armSim.setInputVoltage(motorSim.getAppliedOutput() * volts);
    armSim.update(0.02);
    double degPerS = Math.toDegrees(armSim.getVelocityRadPerSec());
    double degrees = Math.toDegrees(armSim.getAngleRads());
    motorSim.iterate(degPerS, volts, 0.02);
    motorSim.setPosition(degrees);
    angleSim.setPosition(degrees);
    angleSim.setVelocity(degPerS);
  }

  /** Stops where it is now: the goal and the profile both. */
  private void holdHere() {
    target = angle.getPosition();
    setpoint = new TrapezoidProfile.State(target, 0);
  }

  public double degrees() {
    return angle.getPosition();
  }

  public boolean atTarget() {
    return Math.abs(angle.getPosition() - target) < TOLERANCE;
  }

  /** Goes to an angle, degrees, kept inside its travel, and finishes when it is there. */
  public Command goTo(double degrees) {
    return this.run(() -> target = clamp(degrees)).until(this::atTarget);
  }

  public Command toRest() { return goTo(REST); }
  public Command toRange() { return goTo(RANGE); }
  public Command toSubwoofer() { return goTo(SUBWOOFER); }
  public Command toAmp() { return goTo(AMP); }

  /** Aims at the speaker from a distance, meters, for as long as it runs: 2024's camera aim. */
  public Command aimAtSpeaker(DoubleSupplier distanceMeters) {
    return this.run(() -> target = clamp(Math.toDegrees(Math.atan2(SPEAKER_HEIGHT_M, distanceMeters.getAsDouble()))));
  }

  private static double clamp(double degrees) {
    return Math.max(MIN, Math.min(MAX, degrees));
  }

  public void watchMotors(MotorWatcher w) {
    w.watch("Shooter pivot right", right, MotorKind.NEO_V1_1);
    w.watch("Shooter pivot left", left, MotorKind.NEO_V1_1);
  }

  /** The Systems tab: its angle in degrees from the absolute encoder, through its own loop. */
  public void tuneWith(SwerveTune tune) {
    tune.system("Shooter pivot", TunableSystem.Kind.PIVOT)
        .units("degrees")
        .position(angle::getPosition)
        .velocity(angle::getVelocity)
        .goal(d -> target = clamp(d))
        .stop(this::holdHere)
        .subsystem(this)
        .motors("Shooter pivot right", "Shooter pivot left")
        .sparkGains(right);
  }
}
