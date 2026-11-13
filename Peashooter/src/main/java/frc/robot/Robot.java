package frc.robot;

import edu.wpi.first.math.MathUtil;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.kinematics.ChassisSpeeds;
import edu.wpi.first.units.measure.Angle;

import com.pathplanner.lib.auto.AutoBuilder;
import com.pathplanner.lib.auto.NamedCommands;
import com.reduxrobotics.canand.CanandEventLoop;
import com.reduxrobotics.sensors.canandgyro.Canandgyro;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj.TimedRobot;
import edu.wpi.first.wpilibj.smartdashboard.SmartDashboard;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.robot.Subsystems.Feeder;
import frc.robot.Subsystems.Intake;
import frc.robot.Subsystems.Shooter;
import swervelib.SwerveDrive;
import swervelib.encoders.SwerveAbsoluteEncoder;

public class Robot extends TimedRobot {

  Drive drive = new Drive();
  Feeder feeder = new Feeder();
  Intake intake = new Intake();
  Shooter shooter = new Shooter();
  CommandXboxController controller = new CommandXboxController(0);
  //CommandGenericHID controller = new CommandGenericHID(0);

  private final Canandgyro m_gyro = new Canandgyro(40);

  private Command autonomousCommand; 
  public Robot() {
    CanandEventLoop.getInstance();
  
    NamedCommands.registerCommand("Shoot Hub", shooter.shootA());
    NamedCommands.registerCommand("Shoot Corner", shooter.shootCorner());
    NamedCommands.registerCommand("Shoot Tower", shooter.shootB());
    NamedCommands.registerCommand("Intake Balls", intake.spinIntakeCommand());
    NamedCommands.registerCommand("Reverse Intake", intake.reverseIntakeCommand());
    NamedCommands.registerCommand("Move Intake Up", intake.retractIntakeCommand());
    NamedCommands.registerCommand("Move Intake Down", intake.deployIntakeCommand());
    NamedCommands.registerCommand("Load Feeder", feeder.load(true));
    NamedCommands.registerCommand("Unload Feeder", feeder.load(false));

    drive.setupPathPlanner();

    drive.setDefaultCommand(drive.drive(
        () -> MathUtil.applyDeadband(controller.getLeftY(), 0.1),
        () -> MathUtil.applyDeadband(controller.getLeftX(), 0.1),
        () -> MathUtil.applyDeadband(controller.getRightX(), 0.1)
      )
    );

    

    controller.rightBumper().whileTrue(feeder.load(true));
    controller.leftBumper().whileTrue(feeder.load(false));
    controller.y().onTrue(drive.resetPosition());
    controller.rightTrigger().whileTrue(intake.spinIntakeCommand());
    controller.leftTrigger().whileTrue(intake.reverseIntakeCommand());
    controller.povUp().whileTrue(intake.retractIntakeCommand());
    controller.povDown().whileTrue(intake.deployIntakeCommand());
    controller.b().whileTrue(shooter.shootB());
    controller.a().whileTrue(shooter.shootA());
    controller.x().whileTrue(shooter.shootX());

  }

  @Override
  public void robotPeriodic() {
    CommandScheduler.getInstance().run();

    ChassisSpeeds speeds = drive.getSpeeds();
    SmartDashboard.putNumber("Velocity X", speeds.vxMetersPerSecond);
    SmartDashboard.putNumber("Velocity Y", speeds.vyMetersPerSecond);
  }

  @Override
  public void autonomousInit() {
    autonomousCommand = AutoBuilder.buildAuto("W auto");
    if (autonomousCommand != null) { autonomousCommand.schedule(); }
  }

  @Override
  public void autonomousPeriodic() {}

  @Override
  public void teleopInit() {}

  @Override
  public void teleopPeriodic() {
    double heading = m_gyro.getYaw();
  
    double degrees = heading * 360.0;
    SmartDashboard.putNumber("Robot Heading", degrees);
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
