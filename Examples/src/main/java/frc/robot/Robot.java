package frc.robot;

import edu.wpi.first.math.MathUtil;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.lib.swervetune.AkLogging;
import frc.lib.swervetune.SwerveTune;
import frc.robot.Subsystems.Climber;
import frc.robot.Subsystems.Elevator;
import frc.robot.Subsystems.Feeder;
import frc.robot.Subsystems.Shooter;
import frc.robot.Subsystems.ShooterPivot;
import frc.robot.Subsystems.TwoJointArm;
import org.littletonrobotics.junction.LoggedRobot;

/**
 * Mechanisms from past seasons, rebuilt the way this repo's robots are written (YAGSL swerve,
 * REVLib 2026 SPARKs, AdvantageKit logging, the swerve tools), on one simulated robot. Each
 * subsystem says which season it came from and what changed; see README.md. Every mechanism with a
 * loop is registered with the Systems tab, and moves under WPILib's physics in the simulator.
 */
public class Robot extends LoggedRobot {

  Drive drive = new Drive();
  Elevator elevator = new Elevator();
  ShooterPivot pivot = new ShooterPivot();
  TwoJointArm arm = new TwoJointArm();
  Shooter shooter = new Shooter();
  Feeder feeder = new Feeder();
  Climber climber = new Climber();
  // Port 0 drives, port 1 is the tester's deadman (swervetune.json), port 2 runs the mechanisms.
  CommandXboxController driver = new CommandXboxController(0);
  CommandXboxController operator = new CommandXboxController(2);
  SwerveTune tune = SwerveTune.install(drive.getSwerveDrive(), drive, "Examples");

  public Robot() {
    AkLogging.start("Examples");
    elevator.watchMotors(tune::watchMotor);
    pivot.watchMotors(tune::watchMotor);
    arm.watchMotors(tune::watchMotor);
    shooter.watchMotors(tune::watchMotor);
    feeder.watchMotors(tune::watchMotor);
    climber.watchMotors(tune::watchMotor);
    // Mechanisms the Systems tab tunes, through each subsystem's own loop. The climber has none.
    elevator.tuneWith(tune);
    pivot.tuneWith(tune);
    arm.tuneWith(tune);
    shooter.tuneWith(tune);
    feeder.tuneWith(tune);

    drive.setDefaultCommand(drive.drive(
        () -> MathUtil.applyDeadband(driver.getLeftY(), 0.1),
        () -> MathUtil.applyDeadband(driver.getLeftX(), 0.1),
        () -> MathUtil.applyDeadband(driver.getRightX(), 0.1)));

    // 2025's elevator buttons.
    operator.y().onTrue(elevator.toL3());
    operator.x().onTrue(elevator.toL2());
    operator.b().onTrue(elevator.toL1());
    operator.a().onTrue(elevator.toBottom());
    // 2024's pivot presets on the d-pad.
    operator.povUp().onTrue(pivot.toAmp());
    operator.povRight().onTrue(pivot.toSubwoofer());
    operator.povLeft().onTrue(pivot.toRange());
    operator.povDown().onTrue(pivot.toRest());
    // 2024's shooter and feeder.
    operator.rightBumper().whileTrue(shooter.speaker());
    operator.leftBumper().whileTrue(feeder.intakeNote());
    operator.rightTrigger().whileTrue(feeder.shoot());
    // 2023's arm: cone high, and stowed.
    operator.start().onTrue(arm.moveTo(TwoJointArm.Pose.CONE_HIGH));
    operator.back().onTrue(arm.moveTo(TwoJointArm.Pose.STOWED));
    // 2025's climber, by hand.
    operator.leftStick().whileTrue(climber.climb());
    operator.rightStick().whileTrue(climber.release());
  }

  @Override
  public void robotPeriodic() {
    CommandScheduler.getInstance().run();
    tune.periodic();
  }
}
