package frc.robot;

import edu.wpi.first.wpilibj.GenericHID.RumbleType;
import edu.wpi.first.math.MathUtil;
import com.pathplanner.lib.auto.AutoBuilder;
import com.pathplanner.lib.auto.NamedCommands;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import edu.wpi.first.wpilibj2.command.Commands;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.lib.swervetune.AkLogging;
import frc.lib.swervetune.SwerveTune;
import frc.lib.swervetune.photonvision.PhotonVisionSetup;
import org.littletonrobotics.junction.LoggedRobot;
import frc.robot.Subsystems.Feeder;
import frc.robot.Subsystems.Intake;
import frc.robot.Subsystems.Shooter;

public class Robot extends LoggedRobot {

  Drive drive = new Drive();
  Feeder feeder = new Feeder();
  Intake intake = new Intake();
  Shooter shooter = new Shooter();
  CommandXboxController controller = new CommandXboxController(0);
  // Swerve tuning and troubleshooting tools; see docs/SWERVE_TUNING_GUIDE.md.
  SwerveTune tune = SwerveTune.install(drive.getSwerveDrive(), drive, "Peashooter");
  //CommandGenericHID controller = new CommandGenericHID(0);

  private Command autonomousCommand; 
  public Robot() {
    // AdvantageKit first: every match logged to the USB stick and streamed to AdvantageScope.
    AkLogging.start("Peashooter");
    // Heat, stall and failure protection for every mechanism motor; the swerve motors are
    // already watched.
    feeder.watchMotors(tune::watchMotor);
    intake.watchMotors(tune::watchMotor);
    shooter.watchMotors(tune::watchMotor);
    // Cameras: whatever swervetune.json's "vision" lists (none yet). Fitting one is a config change;
    // see docs/VISION_LUMA_PHOTONVISION.md.
    PhotonVisionSetup.install(tune);
    // Back button: hold off heat shutoffs for 20 s in a match (stalls still cut out).
    controller.back().onTrue(Commands.runOnce(() -> tune.overrideMotorShutoffs(20))
        // A short buzz says it took; the dashboard shows "Heat override ON" with the time left.
        .andThen(Commands.startEnd(() -> controller.setRumble(RumbleType.kBothRumble, 0.6),
            () -> controller.setRumble(RumbleType.kBothRumble, 0)).withTimeout(0.3)));

  
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
    tune.periodic();
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
