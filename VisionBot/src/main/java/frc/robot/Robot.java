package frc.robot;

import edu.wpi.first.math.geometry.Pose3d;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StructPublisher;
import edu.wpi.first.wpilibj.TimedRobot;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import org.littletonrobotics.junction.Logger;

public class Robot extends TimedRobot {

  Vision vision;
  StructPublisher<Pose3d> posePublisher =
      NetworkTableInstance.getDefault()
          .getStructTopic("MyPose", Pose3d.struct)
          .publish();
  public Robot() {
    vision = new Vision();
    
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
  public void teleopPeriodic() {
      vision.getRobotPose().ifPresent(pose ->
          posePublisher.set(pose)
      );
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
