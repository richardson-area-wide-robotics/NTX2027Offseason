package frc.robot.Subsystems;

import com.revrobotics.PersistMode;
import com.revrobotics.RelativeEncoder;
import com.revrobotics.ResetMode;
import com.revrobotics.sim.SparkFlexSim;
import com.revrobotics.spark.SparkBase.ControlType;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkFlexConfig;

import edu.wpi.first.math.system.plant.DCMotor;
import edu.wpi.first.math.system.plant.LinearSystemId;
import edu.wpi.first.wpilibj.RobotBase;
import edu.wpi.first.wpilibj.simulation.FlywheelSim;
import edu.wpi.first.wpilibj.simulation.RoboRioSim;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.Commands;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.lib.slothtune.MotorKind;
import frc.lib.slothtune.MotorWatcher;
import frc.lib.slothtune.SlothTune;
import frc.lib.slothtune.TunableSystem;
import org.littletonrobotics.junction.Logger;

/**
 * A two-wheel shooter with a kicker, from 2024 Crescendo (Shooter.java, team 8874's state code and
 * team 1745's): a left and a right flywheel, each its own NEO Vortex, run at different speeds to
 * spin the note, and a kicker that feeds it in.
 *
 * <p>What changed for 2027:
 * <ul>
 *   <li>Each wheel runs a velocity loop with kV, in wheel RPM. 2024 ran them open loop (left 0.6,
 *       right 0.4 for the speaker); its velocity loop and feedforward were written but never used.</li>
 *   <li>The kicker feeds only once both wheels are at speed. 2024 fed when the driver pressed A.</li>
 *   <li>Each wheel is its own system in the Systems tab.</li>
 * </ul>
 *
 * <p>2024's encoders reported twice the motor's RPM (a factor of 2.0, never explained): read here
 * as a 1:2 belt up to the wheels, so the speeds are the wheels'. The wheel inertia is assumed for
 * the simulator. Another flywheel, Peashooter's (from 2026), is in Peashooter.
 */
public class Shooter extends SubsystemBase {

  /** Belt up to the wheels: two wheel turns per motor turn (2024's factor of 2.0). */
  private static final double WHEEL_PER_MOTOR = 2.0;
  /** Each wheel's inertia, kg m^2: assumed (four-inch wheels on the shaft). */
  private static final double WHEEL_MOI = 0.001;

  // 2024's speaker shot was left 0.6, right 0.4 open loop: two-thirds as fast on the right.
  public static final double SPEAKER_LEFT_RPM = 8000;
  public static final double SPEAKER_RIGHT_RPM = 8000 * 0.4 / 0.6;
  public static final double AMP_RPM = 1300;
  private static final double KICKER_SPEED = 0.75;
  private static final double READY_FRACTION = 0.03;

  // About 12 V at the wheels' free speed (6784 motor RPM times 2), so kP only corrects the rest.
  private static final double kV = 12.0 / (6784 * WHEEL_PER_MOTOR);
  private static final double kP = 0.0002;

  // 2024: left CAN 14, right 13, kicker 12.
  private final SparkFlex left = new SparkFlex(57, MotorType.kBrushless);
  private final SparkFlex right = new SparkFlex(58, MotorType.kBrushless);
  private final SparkFlex kicker = new SparkFlex(59, MotorType.kBrushless);
  private final RelativeEncoder leftSpeed = left.getEncoder();
  private final RelativeEncoder rightSpeed = right.getEncoder();

  private double leftGoal = 0, rightGoal = 0;

  private SparkFlexSim leftSim, rightSim;
  private FlywheelSim leftWheel, rightWheel;

  public Shooter() {
    left.configure(wheel(true), ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
    right.configure(wheel(false), ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
    SparkFlexConfig k = new SparkFlexConfig();
    k.idleMode(IdleMode.kCoast).smartCurrentLimit(60);
    kicker.configure(k, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);

    if (RobotBase.isSimulation()) {
      DCMotor vortex = DCMotor.getNeoVortex(1);
      leftSim = new SparkFlexSim(left, vortex);
      rightSim = new SparkFlexSim(right, vortex);
      // WPILib's gearing is motor turns per wheel turn: 1/2 for a belt up.
      leftWheel = new FlywheelSim(LinearSystemId.createFlywheelSystem(vortex, WHEEL_MOI, 1 / WHEEL_PER_MOTOR), vortex);
      rightWheel = new FlywheelSim(LinearSystemId.createFlywheelSystem(vortex, WHEEL_MOI, 1 / WHEEL_PER_MOTOR), vortex);
    }
  }

  private static SparkFlexConfig wheel(boolean inverted) {
    SparkFlexConfig c = new SparkFlexConfig();
    c.idleMode(IdleMode.kCoast).smartCurrentLimit(60).inverted(inverted);
    c.encoder.velocityConversionFactor(WHEEL_PER_MOTOR).positionConversionFactor(WHEEL_PER_MOTOR);
    c.closedLoop.p(kP);
    c.closedLoop.feedForward.kV(kV);
    return c;
  }

  @Override
  public void periodic() {
    spin(left, leftGoal);
    spin(right, rightGoal);
    Logger.recordOutput("Shooter/LeftRPM", leftSpeed.getVelocity());
    Logger.recordOutput("Shooter/RightRPM", rightSpeed.getVelocity());
  }

  private static void spin(SparkFlex wheel, double rpm) {
    if (rpm == 0) wheel.set(0);  // coasts down: no braking against a spinning wheel
    else wheel.getClosedLoopController().setSetpoint(rpm, ControlType.kVelocity);
  }

  @Override
  public void simulationPeriodic() {
    double volts = RoboRioSim.getVInVoltage();
    simulate(leftSim, leftWheel, volts);
    simulate(rightSim, rightWheel, volts);
  }

  private static void simulate(SparkFlexSim sim, FlywheelSim wheel, double volts) {
    wheel.setInputVoltage(sim.getAppliedOutput() * volts);
    wheel.update(0.02);
    sim.iterate(wheel.getAngularVelocityRPM(), volts, 0.02);
  }

  public double leftRpm() { return leftSpeed.getVelocity(); }
  public double rightRpm() { return rightSpeed.getVelocity(); }

  public boolean atSpeed() {
    return leftGoal > 0 && Math.abs(leftSpeed.getVelocity() - leftGoal) < READY_FRACTION * leftGoal
        && Math.abs(rightSpeed.getVelocity() - rightGoal) < READY_FRACTION * Math.max(rightGoal, 1);
  }

  /** Spins both wheels, then kicks once they are at speed; stops everything when released. */
  public Command shoot(double leftRpm, double rightRpm) {
    return this.runEnd(() -> {
      leftGoal = leftRpm;
      rightGoal = rightRpm;
      kicker.set(atSpeed() ? KICKER_SPEED : 0);
    }, () -> {
      leftGoal = 0;
      rightGoal = 0;
      kicker.set(0);
    });
  }

  public Command speaker() { return shoot(SPEAKER_LEFT_RPM, SPEAKER_RIGHT_RPM); }
  public Command amp() { return shoot(AMP_RPM, AMP_RPM); }
  public Command stop() { return Commands.runOnce(() -> { leftGoal = 0; rightGoal = 0; kicker.set(0); }, this); }

  public void watchMotors(MotorWatcher w) {
    w.watch("Shooter left", left, MotorKind.VORTEX);
    w.watch("Shooter right", right, MotorKind.VORTEX);
    w.watch("Shooter kicker", kicker, MotorKind.VORTEX);
  }

  /** The Systems tab: each wheel on its own, in wheel RPM. */
  public void tuneWith(SlothTune tune) {
    tune.system("Shooter left", TunableSystem.Kind.FLYWHEEL)
        .units("wheel RPM")
        .velocity(leftSpeed::getVelocity)
        .goal(rpm -> leftGoal = rpm)
        .stop(() -> leftGoal = 0)
        .subsystem(this)
        .motors("Shooter left")
        .sparkGains(left);
    tune.system("Shooter right", TunableSystem.Kind.FLYWHEEL)
        .units("wheel RPM")
        .velocity(rightSpeed::getVelocity)
        .goal(rpm -> rightGoal = rpm)
        .stop(() -> rightGoal = 0)
        .subsystem(this)
        .motors("Shooter right")
        .sparkGains(right);
  }
}
