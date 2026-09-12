package frc.robot;

import edu.wpi.first.wpilibj.TimedRobot;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.robot.Subsystems.Drive;
import frc.robot.Subsystems.Feeder;

public class Robot extends TimedRobot {

  Drive drive = new Drive();
  Feeder feeder = new Feeder();
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
