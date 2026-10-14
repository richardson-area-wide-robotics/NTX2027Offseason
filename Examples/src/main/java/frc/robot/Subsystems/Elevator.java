package frc.robot.Subsystems;

import com.revrobotics.PersistMode;
import com.revrobotics.RelativeEncoder;
import com.revrobotics.ResetMode;
import com.revrobotics.sim.SparkFlexSim;
import com.revrobotics.spark.SparkBase.ControlType;
import com.revrobotics.spark.SparkClosedLoopController;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkFlexConfig;

import edu.wpi.first.math.system.plant.DCMotor;
import edu.wpi.first.math.trajectory.TrapezoidProfile;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.RobotBase;
import edu.wpi.first.wpilibj.simulation.ElevatorSim;
import edu.wpi.first.wpilibj.simulation.RoboRioSim;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.lib.slothtune.MotorKind;
import frc.lib.slothtune.MotorWatcher;
import frc.lib.slothtune.SlothTune;
import frc.lib.slothtune.TunableSystem;
import org.littletonrobotics.junction.Logger;

/**
 * An elevator, from 2025 Reefscape (ElevatorSubsystem, the same on team 8874's state code and on
 * main): one NEO Vortex on a SPARK Flex lifting the carriage to the coral levels.
 *
 * <p>What changed for 2027:
 * <ul>
 *   <li>Positions are meters of carriage travel. 2025 used raw motor rotations.</li>
 *   <li>A motion profile moves its goal smoothly, and kG holds it up. 2025 jumped straight to each
 *       setpoint and held it with a constant 3% duty. (MAXMotion can run the profile on the SPARK
 *       instead; REVLib's simulator doesn't run it reliably yet, so this profiles in code.)</li>
 *   <li>Soft limits at both ends. 2025 had none.</li>
 *   <li>The setpoint commands require the subsystem. In 2025 they didn't, so the hold command
 *       fought them and a setpoint only held while its button was held.</li>
 *   <li>The Systems tab tunes it.</li>
 * </ul>
 *
 * <p>The 2025 code had no gear ratio, drum size or carriage mass. GEARING, DRUM_DIAMETER_M and
 * CARRIAGE_KG below are assumed, so the simulator has something to lift: measure the real robot's
 * before using them.
 */
public class Elevator extends SubsystemBase {

  // Assumed (see above): a 5:1 gearbox driving a 22-tooth #25 sprocket (1.76 in pitch diameter).
  private static final double GEARING = 5.0;
  private static final double DRUM_DIAMETER_M = 0.0447;
  private static final double CARRIAGE_KG = 4.5;
  private static final double METERS_PER_MOTOR_ROTATION = Math.PI * DRUM_DIAMETER_M / GEARING;

  // 2025's setpoints, which were motor rotations, as meters of travel.
  public static final double BOTTOM = 0.2 * METERS_PER_MOTOR_ROTATION;
  public static final double INTAKE = 13.6 * METERS_PER_MOTOR_ROTATION;
  public static final double L1 = 16.0 * METERS_PER_MOTOR_ROTATION;
  public static final double L2 = 25.3 * METERS_PER_MOTOR_ROTATION;
  public static final double L3 = 40.5 * METERS_PER_MOTOR_ROTATION;
  /** Just past L3: the soft limit. */
  public static final double MAX_HEIGHT = 42.0 * METERS_PER_MOTOR_ROTATION;
  private static final double TOLERANCE = 0.01;

  // Gains. kG is what the assumed physics give (a ReCalc link with the same numbers is in
  // slothtune.json); kP corrects what is left. 2025 had kP 0.1 per motor rotation and nothing else.
  private static final double kP = 8.0;
  private static final double kD = 0.0;
  private static final double kG = 0.40;   // volts to hold the carriage up
  private static final double CRUISE_MPS = 1.5;
  private static final double ACCEL_MPS2 = 6.0;

  // 2025: CAN 9. Every example has its own CAN ID so they can share one simulated robot.
  private final SparkFlex motor = new SparkFlex(51, MotorType.kBrushless);
  private final SparkClosedLoopController controller = motor.getClosedLoopController();
  private final RelativeEncoder encoder = motor.getEncoder();

  private double target = BOTTOM;
  private final TrapezoidProfile profile = new TrapezoidProfile(new TrapezoidProfile.Constraints(CRUISE_MPS, ACCEL_MPS2));
  private TrapezoidProfile.State setpoint = new TrapezoidProfile.State();

  // The simulator: the SPARK and the carriage it lifts. Never built on the real robot.
  private SparkFlexSim motorSim;
  private ElevatorSim liftSim;

  public Elevator() {
    SparkFlexConfig config = new SparkFlexConfig();
    config.idleMode(IdleMode.kBrake).smartCurrentLimit(80);
    config.encoder.positionConversionFactor(METERS_PER_MOTOR_ROTATION)
        .velocityConversionFactor(METERS_PER_MOTOR_ROTATION / 60.0);
    config.softLimit.forwardSoftLimit(MAX_HEIGHT).forwardSoftLimitEnabled(true)
        .reverseSoftLimit(0.0).reverseSoftLimitEnabled(true);
    config.closedLoop.p(kP).d(kD);
    config.closedLoop.feedForward.kG(kG);
    motor.configure(config, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
    // Like 2025: it starts at the bottom, so that is zero.
    encoder.setPosition(0.0);

    if (RobotBase.isSimulation()) {
      DCMotor vortex = DCMotor.getNeoVortex(1);
      motorSim = new SparkFlexSim(motor, vortex);
      liftSim = new ElevatorSim(vortex, GEARING, CARRIAGE_KG, DRUM_DIAMETER_M / 2, 0.0, MAX_HEIGHT + 0.02, true, 0.0);
    }
  }

  @Override
  public void periodic() {
    if (DriverStation.isDisabled()) {
      // Enabling never jumps to an old goal: it holds where it is.
      target = encoder.getPosition();
      setpoint = new TrapezoidProfile.State(target, 0);
    } else {
      // Each loop, the profile's next step toward the goal; the SPARK's own loop follows it.
      setpoint = profile.calculate(0.02, setpoint, new TrapezoidProfile.State(target, 0));
      controller.setSetpoint(setpoint.position, ControlType.kPosition);
    }
    Logger.recordOutput("Elevator/GoalMeters", target);
    Logger.recordOutput("Elevator/PositionMeters", encoder.getPosition());
  }

  @Override
  public void simulationPeriodic() {
    double volts = RoboRioSim.getVInVoltage();
    liftSim.setInputVoltage(motorSim.getAppliedOutput() * volts);
    liftSim.update(0.02);
    motorSim.iterate(liftSim.getVelocityMetersPerSecond(), volts, 0.02);
    motorSim.setPosition(liftSim.getPositionMeters());
  }

  /** Stops where it is now: the goal and the profile both. */
  private void holdHere() {
    target = encoder.getPosition();
    setpoint = new TrapezoidProfile.State(target, 0);
  }

  public double position() {
    return encoder.getPosition();
  }

  public boolean atTarget() {
    return Math.abs(encoder.getPosition() - target) < TOLERANCE;
  }

  /** Goes to a height, meters, and finishes when it is there. */
  public Command goTo(double meters) {
    return this.run(() -> target = Math.max(0.0, Math.min(MAX_HEIGHT, meters))).until(this::atTarget);
  }

  public Command toBottom() { return goTo(BOTTOM); }
  public Command toIntake() { return goTo(INTAKE); }
  public Command toL1() { return goTo(L1); }
  public Command toL2() { return goTo(L2); }
  public Command toL3() { return goTo(L3); }

  /** Lists this subsystem's motors for the motor guard (heat, stalls, failure). */
  public void watchMotors(MotorWatcher w) {
    w.watch("Elevator", motor, MotorKind.VORTEX);
  }

  /** The Systems tab: its height in meters, set through target, which periodic() sends to the SPARK. */
  public void tuneWith(SlothTune tune) {
    tune.system("Elevator", TunableSystem.Kind.ELEVATOR)
        .units("meters")
        .position(encoder::getPosition)
        .velocity(encoder::getVelocity)
        .goal(m -> target = m)
        .stop(this::holdHere)
        .subsystem(this)
        .motors("Elevator")
        .sparkGains(motor);
  }
}
