package frc.robot;

import com.reduxrobotics.canand.CanandEventLoop;
import com.reduxrobotics.sensors.canandgyro.Canandgyro;

import edu.wpi.first.wpilibj.TimedRobot;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.robot.Subsystems.*;

public class Robot extends TimedRobot {
  Canandgyro canandgyro = new Canandgyro(12);
  Vision vision = new Vision();
  Drive drive = new Drive();
  Shooter shooter = new Shooter();
  Intake intake = new Intake();
  CommandXboxController controller = new CommandXboxController(0);


  public Robot() {
   

    drive.setDefaultCommand(drive.drive(
        () -> controller.getLeftX(),
        () -> controller.getLeftY(),
        () -> -controller.getRightX()));

        controller.y().onTrue(drive.zeroGyro());
    controller.rightTrigger().whileTrue(shooter.shootHub());
    controller.b().whileTrue(shooter.shootCornerA());
    controller.leftTrigger().whileTrue(shooter.shootIntake());
    controller.leftTrigger().whileTrue(intake.intakeIn());
    controller.povDown().whileTrue(intake.intakeOut());

    controller.povLeft().whileTrue(intake.intakeIn());
    // other intakes during shoots
    //controller.a().whileTrue(intake.intakeIn());
    //controller.b().whileTrue(intake.intakeIn());
  
}

 
  public void robotInit(){
    CanandEventLoop.getInstance();
    canandgyro.startCalibration();
  }
  @Override
  public void robotPeriodic() {
    CommandScheduler.getInstance().run();
    drive.addVisionMeasurement(vision.poseEstimations, vision.poseEstimationsTimestamps, vision.calculateStdDeviations());
    vision.clearResults();
  }

  @Override
  public void autonomousInit() {}

  @Override
  public void autonomousPeriodic() {}

  @Override
  public void teleopInit() {    if(canandgyro.isCalibrating()) {System.err.println("Teleop started before Gyro finished calibrating;\nyou're on your own now");}
}

  @Override
  public void teleopPeriodic() {
  }

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
