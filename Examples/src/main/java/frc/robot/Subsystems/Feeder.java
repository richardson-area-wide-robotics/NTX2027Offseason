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
import edu.wpi.first.wpilibj.DigitalInput;
import edu.wpi.first.wpilibj.RobotBase;
import edu.wpi.first.wpilibj.simulation.FlywheelSim;
import edu.wpi.first.wpilibj.simulation.RoboRioSim;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.lib.swervetune.MotorKind;
import frc.lib.swervetune.MotorWatcher;
import frc.lib.swervetune.SwerveTune;
import frc.lib.swervetune.TunableSystem;
import org.littletonrobotics.junction.Logger;

/**
 * A feeder roller with a beam break, from 2024 Crescendo (Feeder.java, team 8874's state code and
 * team 1745's): one NEO Vortex that pulls a note in until the beam breaks, then pushes it into the
 * shooter.
 *
 * <p>What changed for 2027:
 * <ul>
 *   <li>The roller runs a velocity loop, so a note arrives the same way whatever the battery. 2024
 *       ran it at full duty.</li>
 *   <li>"Has a note" is read from the beam break every time. 2024 latched it true after the first
 *       note and never cleared it, so autos waiting for a note finished at once.</li>
 *   <li>The Systems tab tunes it as a roller.</li>
 * </ul>
 *
 * <p>The roller's inertia is assumed for the simulator, where the beam is never broken.
 */
public class Feeder extends SubsystemBase {

  public static final double FEED_RPM = 3000;
  public static final double SHOOT_RPM = 6000;
  private static final double ROLLER_MOI = 0.000146;   // a two-inch, one-pound roller

  private static final double kV = 12.0 / 6784;
  private static final double kP = 0.0001;

  // 2024: CAN 11, beam break on DIO 0.
  private final SparkFlex motor = new SparkFlex(60, MotorType.kBrushless);
  private final RelativeEncoder speed = motor.getEncoder();
  private final DigitalInput beam = new DigitalInput(0);

  private SparkFlexSim motorSim;
  private FlywheelSim rollerSim;
  private double goal = 0;

  public Feeder() {
    SparkFlexConfig config = new SparkFlexConfig();
    config.idleMode(IdleMode.kBrake).smartCurrentLimit(60).inverted(true);
    config.closedLoop.p(kP);
    config.closedLoop.feedForward.kV(kV);
    motor.configure(config, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
    if (RobotBase.isSimulation()) {
      DCMotor vortex = DCMotor.getNeoVortex(1);
      motorSim = new SparkFlexSim(motor, vortex);
      rollerSim = new FlywheelSim(LinearSystemId.createFlywheelSystem(vortex, ROLLER_MOI, 1.0), vortex);
    }
  }

  public double rpm() {
    return speed.getVelocity();
  }

  /** A note breaks the beam: the sensor reads false. */
  public boolean hasNote() {
    return !beam.get();
  }

  @Override
  public void periodic() {
    if (goal == 0) motor.set(0);
    else motor.getClosedLoopController().setSetpoint(goal, ControlType.kVelocity);
    Logger.recordOutput("Feeder/RPM", speed.getVelocity());
    Logger.recordOutput("Feeder/HasNote", hasNote());
  }

  @Override
  public void simulationPeriodic() {
    double volts = RoboRioSim.getVInVoltage();
    rollerSim.setInputVoltage(motorSim.getAppliedOutput() * volts);
    rollerSim.update(0.02);
    motorSim.iterate(rollerSim.getAngularVelocityRPM(), volts, 0.02);
  }

  /** Pulls a note in and stops when the beam breaks. */
  public Command intakeNote() {
    return this.runEnd(() -> goal = FEED_RPM, () -> goal = 0).until(this::hasNote);
  }

  /** Pushes the note into the shooter while held. */
  public Command shoot() {
    return this.runEnd(() -> goal = SHOOT_RPM, () -> goal = 0);
  }

  public void watchMotors(MotorWatcher w) {
    w.watch("Feeder", motor, MotorKind.VORTEX);
  }

  /** The Systems tab: the roller's speed in motor RPM. */
  public void tuneWith(SwerveTune tune) {
    tune.system("Feeder", TunableSystem.Kind.ROLLER)
        .units("RPM")
        .velocity(speed::getVelocity)
        .goal(rpm -> goal = rpm)
        .stop(() -> goal = 0)
        .subsystem(this)
        .motors("Feeder")
        .sparkGains(motor);
  }
}
