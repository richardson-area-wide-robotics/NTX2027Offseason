package frc.robot;

import edu.wpi.first.wpilibj.TimedRobot;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.robot.subsystems.Intake;
import frc.robot.subsystems.Shooter;

public class Robot extends TimedRobot {

  Drive drive = new Drive();
  Shooter shooter = new Shooter();
  Intake intake = new Intake();
  CommandXboxController controller = new CommandXboxController(0);

  public Robot() {

    drive.setDefaultCommand(drive.drive(
        () -> controller.getLeftX(),
        () -> controller.getLeftY(),
        () -> controller.getRightX()));

        controller.y().onTrue(drive.toggleFieldRelative());
    controller.a().whileTrue(shooter.shootHub());
    controller.b().whileTrue(shooter.shootCornerA());
    controller.povUp().whileTrue(shooter.shootIntake());
    controller.povUp().whileTrue(intake.intakeIn());
    controller.povDown().whileTrue(intake.intakeOut());

    controller.povLeft().whileTrue(intake.intakeIn());
    // other intakes during shoots
    //controller.a().whileTrue(intake.intakeIn());
    //controller.b().whileTrue(intake.intakeIn());
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
