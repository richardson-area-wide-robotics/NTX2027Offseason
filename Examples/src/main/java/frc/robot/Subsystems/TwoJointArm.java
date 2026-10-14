package frc.robot.Subsystems;

import com.revrobotics.AbsoluteEncoder;
import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;
import com.revrobotics.sim.SparkAbsoluteEncoderSim;
import com.revrobotics.sim.SparkMaxSim;
import com.revrobotics.spark.FeedbackSensor;
import com.revrobotics.spark.SparkBase.ControlType;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkMaxConfig;

import edu.wpi.first.math.system.plant.DCMotor;
import edu.wpi.first.math.trajectory.TrapezoidProfile;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.RobotBase;
import edu.wpi.first.wpilibj.simulation.RoboRioSim;
import edu.wpi.first.wpilibj.simulation.SingleJointedArmSim;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.Commands;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.lib.swervetune.MotorKind;
import frc.lib.swervetune.MotorWatcher;
import frc.lib.swervetune.SwerveTune;
import frc.lib.swervetune.TunableSystem;
import org.littletonrobotics.junction.Logger;

/**
 * A two-joint arm, from 2023 Charged Up (Arm.java on team 8874's state code; team 1745's main has
 * the same arm): a shoulder on two NEOs, the second following, and an elbow on one NEO, each read
 * by a through-bore absolute encoder on its SPARK MAX.
 *
 * <p>What changed for 2027:
 * <ul>
 *   <li>Angles are degrees. 2023 set a 2 pi factor and then wiped it with a factory reset, so its
 *       setpoints were raw 0-1 rotations.</li>
 *   <li>The shoulder's zero offset moves the encoder's wrap out of its travel. In 2023 the cone-high
 *       pose sat at 0.005 rotations, right beside the wrap: a little past it read 0.99.</li>
 *   <li>Every pose tucks the elbow first, then moves the shoulder, then the elbow, each waiting until
 *       that joint arrives. 2023 did this too, but its "done" check compared the wrong way round.</li>
 *   <li>Both joints move on motion profiles, and the Systems tab tunes each one.</li>
 * </ul>
 *
 * <p>The 2023 SysId fit kG 0.72 V (shoulder) and 0.77 V (elbow), never applied. Gravity on the elbow
 * depends on the shoulder's angle too, which a single joint's kCos can't follow: tune each with the
 * other held still. The simulator models each joint alone, without gravity; GEARING and the inertias
 * are assumed.
 */
public class TwoJointArm extends SubsystemBase {

  /** The 2023 poses (8874's state code), as degrees: shoulder, elbow. */
  public enum Pose {
    STOWED(234.0, 284.4),
    TIPPED_CONE(162.0, 190.4),
    STANDING_CONE(95.7, 111.6),
    CUBE_PICKUP(147.4, 209.2),
    CONE_MID(302.4, 216.0),
    CUBE_MID(295.2, 237.8),
    CONE_HIGH(37.8, 98.6),
    CUBE_HIGH(90.7, 198.1),
    SHELF(196.2, 298.8);

    public final double shoulder;
    public final double elbow;

    Pose(double shoulder, double elbow) {
      this.shoulder = shoulder;
      this.elbow = elbow;
    }
  }

  /** Where the elbow tucks before the shoulder moves: 2023's 0.83 rotations. */
  public static final double ELBOW_TUCKED = 298.8;
  /** The shoulder encoder's zero offset, rotations: 2023's raw readings plus 0.1, so cone-high is 37.8. */
  private static final double SHOULDER_ZERO_OFFSET = 0.9;
  private static final double TOLERANCE = 3.0;
  private static final double SHOULDER_MIN = 30, SHOULDER_MAX = 310;
  private static final double ELBOW_MIN = 90, ELBOW_MAX = 305;

  // Assumed for the simulator (see above).
  private static final double SHOULDER_GEARING = 100.0, SHOULDER_MOI = 1.5;
  private static final double ELBOW_GEARING = 80.0, ELBOW_MOI = 0.4;

  // 2023: shoulder CAN 10 (leader) and 9, elbow CAN 11.
  private final SparkMax shoulder = new SparkMax(54, MotorType.kBrushless);
  private final SparkMax shoulderFollower = new SparkMax(55, MotorType.kBrushless);
  private final SparkMax elbow = new SparkMax(56, MotorType.kBrushless);
  private final AbsoluteEncoder shoulderAngle = shoulder.getAbsoluteEncoder();
  private final AbsoluteEncoder elbowAngle = elbow.getAbsoluteEncoder();

  private double shoulderTarget = Pose.STOWED.shoulder;
  private double elbowTarget = Pose.STOWED.elbow;
  // 90 degrees a second at most, reached in half a second: a long arm moves gently.
  private final TrapezoidProfile profile = new TrapezoidProfile(new TrapezoidProfile.Constraints(90, 180));
  private TrapezoidProfile.State shoulderSetpoint = new TrapezoidProfile.State(shoulderTarget, 0);
  private TrapezoidProfile.State elbowSetpoint = new TrapezoidProfile.State(elbowTarget, 0);

  private SparkMaxSim shoulderSim, elbowSim;
  private SparkAbsoluteEncoderSim shoulderAngleSim, elbowAngleSim;
  private SingleJointedArmSim shoulderJoint, elbowJoint;

  public TwoJointArm() {
    // 2023: shoulder P 3, elbow P 4 and D 0.65, per rotation; here per degree.
    shoulder.configure(joint(3.0 / 360, 0, false, SHOULDER_ZERO_OFFSET, 40, SHOULDER_GEARING),
        ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
    SparkMaxConfig follower = new SparkMaxConfig();
    follower.idleMode(IdleMode.kBrake).smartCurrentLimit(40).follow(shoulder, true);
    shoulderFollower.configure(follower, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
    elbow.configure(joint(4.0 / 360, 0.65 / 360, true, 0.0, 60, ELBOW_GEARING),
        ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);

    if (RobotBase.isSimulation()) {
      shoulderSim = new SparkMaxSim(shoulder, DCMotor.getNEO(2));
      elbowSim = new SparkMaxSim(elbow, DCMotor.getNEO(1));
      shoulderAngleSim = shoulderSim.getAbsoluteEncoderSim();
      elbowAngleSim = elbowSim.getAbsoluteEncoderSim();
      shoulderJoint = new SingleJointedArmSim(DCMotor.getNEO(2), SHOULDER_GEARING, SHOULDER_MOI, 0.8,
          Math.toRadians(SHOULDER_MIN), Math.toRadians(SHOULDER_MAX), false, Math.toRadians(shoulderTarget));
      elbowJoint = new SingleJointedArmSim(DCMotor.getNEO(1), ELBOW_GEARING, ELBOW_MOI, 0.6,
          Math.toRadians(ELBOW_MIN), Math.toRadians(ELBOW_MAX), false, Math.toRadians(elbowTarget));
      shoulderAngleSim.setPosition(shoulderTarget);
      elbowAngleSim.setPosition(elbowTarget);
    }
  }

  private static SparkMaxConfig joint(double p, double d, boolean inverted, double zeroOffset, int amps, double gearing) {
    SparkMaxConfig c = new SparkMaxConfig();
    c.idleMode(IdleMode.kBrake).smartCurrentLimit(amps).inverted(inverted);
    // Both encoders in degrees of the joint: the absolute one on its shaft, the motor's through the gearing.
    c.absoluteEncoder.positionConversionFactor(360).velocityConversionFactor(6.0).zeroOffset(zeroOffset);
    c.encoder.positionConversionFactor(360 / gearing).velocityConversionFactor(6.0 / gearing);
    c.closedLoop.feedbackSensor(FeedbackSensor.kAbsoluteEncoder).p(p).d(d).positionWrappingEnabled(false);
    c.closedLoop.feedForward.kCosRatio(1.0 / 360);
    return c;
  }

  @Override
  public void periodic() {
    if (DriverStation.isDisabled()) {
      holdShoulder();
      holdElbow();
    } else {
      shoulderSetpoint = profile.calculate(0.02, shoulderSetpoint, new TrapezoidProfile.State(shoulderTarget, 0));
      elbowSetpoint = profile.calculate(0.02, elbowSetpoint, new TrapezoidProfile.State(elbowTarget, 0));
      shoulder.getClosedLoopController().setSetpoint(shoulderSetpoint.position, ControlType.kPosition);
      elbow.getClosedLoopController().setSetpoint(elbowSetpoint.position, ControlType.kPosition);
    }
    Logger.recordOutput("Arm/ShoulderDegrees", shoulderAngle.getPosition());
    Logger.recordOutput("Arm/ElbowDegrees", elbowAngle.getPosition());
  }

  @Override
  public void simulationPeriodic() {
    double volts = RoboRioSim.getVInVoltage();
    step(shoulderSim, shoulderAngleSim, shoulderJoint, volts);
    step(elbowSim, elbowAngleSim, elbowJoint, volts);
  }

  private static void step(SparkMaxSim sim, SparkAbsoluteEncoderSim angle, SingleJointedArmSim joint, double volts) {
    joint.setInputVoltage(sim.getAppliedOutput() * volts);
    joint.update(0.02);
    double degPerS = Math.toDegrees(joint.getVelocityRadPerSec());
    double degrees = Math.toDegrees(joint.getAngleRads());
    sim.iterate(degPerS, volts, 0.02);
    sim.setPosition(degrees);
    angle.setPosition(degrees);
    angle.setVelocity(degPerS);
  }

  private void holdShoulder() {
    shoulderTarget = shoulderAngle.getPosition();
    shoulderSetpoint = new TrapezoidProfile.State(shoulderTarget, 0);
  }

  private void holdElbow() {
    elbowTarget = elbowAngle.getPosition();
    elbowSetpoint = new TrapezoidProfile.State(elbowTarget, 0);
  }

  public double shoulderDegrees() { return shoulderAngle.getPosition(); }
  public double elbowDegrees() { return elbowAngle.getPosition(); }

  private boolean shoulderAt(double deg) { return Math.abs(shoulderAngle.getPosition() - deg) < TOLERANCE; }
  private boolean elbowAt(double deg) { return Math.abs(elbowAngle.getPosition() - deg) < TOLERANCE; }

  /** Elbow tucked, then the shoulder, then the elbow: the arm never swings out with the elbow open. */
  public Command moveTo(Pose pose) {
    return Commands.sequence(
        this.run(() -> elbowTarget = ELBOW_TUCKED).until(() -> elbowAt(ELBOW_TUCKED)),
        this.run(() -> shoulderTarget = pose.shoulder).until(() -> shoulderAt(pose.shoulder)),
        this.run(() -> elbowTarget = pose.elbow).until(() -> elbowAt(pose.elbow)));
  }

  public void watchMotors(MotorWatcher w) {
    w.watch("Arm shoulder", shoulder, MotorKind.NEO_V1_1);
    w.watch("Arm shoulder follower", shoulderFollower, MotorKind.NEO_V1_1);
    w.watch("Arm elbow", elbow, MotorKind.NEO_V1_1);
  }

  /** The Systems tab: each joint on its own, in degrees, while the other holds still. */
  public void tuneWith(SwerveTune tune) {
    tune.system("Arm shoulder", TunableSystem.Kind.PIVOT)
        .units("degrees")
        .position(shoulderAngle::getPosition)
        .velocity(shoulderAngle::getVelocity)
        .goal(d -> shoulderTarget = Math.max(SHOULDER_MIN, Math.min(SHOULDER_MAX, d)))
        .stop(this::holdShoulder)
        .subsystem(this)
        .motors("Arm shoulder", "Arm shoulder follower")
        .sparkGains(shoulder);
    tune.system("Arm elbow", TunableSystem.Kind.PIVOT)
        .units("degrees")
        .position(elbowAngle::getPosition)
        .velocity(elbowAngle::getVelocity)
        .goal(d -> elbowTarget = Math.max(ELBOW_MIN, Math.min(ELBOW_MAX, d)))
        .stop(this::holdElbow)
        .subsystem(this)
        .motors("Arm elbow")
        .sparkGains(elbow);
  }
}
