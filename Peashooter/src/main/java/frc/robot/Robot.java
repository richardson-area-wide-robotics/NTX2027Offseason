package frc.robot;

import java.lang.reflect.InaccessibleObjectException;

import edu.wpi.first.wpilibj.TimedRobot;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.robot.Subsystems.Drive;
import frc.robot.Subsystems.Feeder;
import frc.robot.Subsystems.Intake;

public class Robot extends TimedRobot {

  Drive drive = new Drive();
  Feeder feeder = new Feeder();
  Intake intake = new Intake();
  CommandXboxController controller = new CommandXboxController(0);

  public Robot() {

    drive.setDefaultCommand(drive.drive(
        () -> controller.getLeftX(),
        () -> controller.getLeftY(),
        () -> controller.getRightX()
      )
    );

    controller.rightBumper().whileTrue(feeder.load(true)); //load
    controller.leftBumper().whileTrue(feeder.load(false)); //unload
    controller.a().onTrue(drive.toggleFieldRelative());
    controller.rightTrigger().whileTrue(intake.spinIntakeCommand()); //balls in
    controller.leftTrigger().whileTrue(intake.reverseIntakeCommand()); //balls out
    controller.povUp().onTrue(intake.moveIntakeCommand());//switch intake command
    controller.povDown().onTrue(intake.moveIntakeCommand()); //switch i

}

  @Override
  public void robotPeriodic() {
    CommandScheduler.getInstance().run();
  }

  @Override
  public void autonomousInit() {}

  @Override
  public void autonomousPeriodic() {}

  @Override
  public void teleopInit() {}

  @Override
  public void teleopPeriodic() {}

  @Override
  public void disabledInit() {}

  @Override
  public void disabledPeriodic() {}

  @Override
  public void testInit() {}

  @Override
  public void testPeriodic() {}

  @Override
  public void simulationInit() {}

  @Override
  public void simulationPeriodic() {}
}
