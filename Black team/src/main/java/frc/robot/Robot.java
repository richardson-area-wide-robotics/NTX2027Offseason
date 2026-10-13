package frc.robot;

import edu.wpi.first.wpilibj.GenericHID.RumbleType;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import edu.wpi.first.wpilibj2.command.Commands;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.lib.swervetune.AkLogging;
import frc.lib.swervetune.SwerveTune;
import frc.lib.swervetune.photonvision.PhotonVisionSetup;
import org.littletonrobotics.junction.LoggedRobot;
import frc.robot.subsystems.Intake;
import frc.robot.subsystems.Shooter;

public class Robot extends LoggedRobot {

  Drive drive = new Drive();
  Shooter shooter = new Shooter();
  Intake intake = new Intake();
  CommandXboxController controller = new CommandXboxController(0);
  // Swerve tuning and troubleshooting tools; see docs/SWERVE_TUNING_GUIDE.md.
  SwerveTune tune = SwerveTune.install(drive.getSwerveDrive(), drive, "Black team");

  public Robot() {
    // AdvantageKit first: every match logged to the USB stick and streamed to AdvantageScope.
    AkLogging.start("Black team");
    // Heat, stall and failure protection for every mechanism motor; the swerve motors are
    // already watched.
    shooter.watchMotors(tune::watchMotor);
    intake.watchMotors(tune::watchMotor);
    // Cameras: whatever swervetune.json's "vision" lists (none yet). Fitting one is a config change;
    // see docs/VISION_LUMA_PHOTONVISION.md.
    PhotonVisionSetup.install(tune);
    // Back button: hold off heat shutoffs for 20 s in a match (stalls still cut out).
    controller.back().onTrue(Commands.runOnce(() -> tune.overrideMotorShutoffs(20))
        // A short buzz says it took; the dashboard shows "Heat override ON" with the time left.
        .andThen(Commands.startEnd(() -> controller.setRumble(RumbleType.kBothRumble, 0.6),
            () -> controller.setRumble(RumbleType.kBothRumble, 0)).withTimeout(0.3)));

    drive.setDefaultCommand(drive.drive(
        () -> controller.getLeftX(),
        () -> controller.getLeftY(),
        () -> controller.getRightX()));

        controller.y().onTrue(drive.toggleFieldRelative());
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

 

  @Override
  public void robotPeriodic() {
    CommandScheduler.getInstance().run();
    tune.periodic();
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
