package frc.robot;

import edu.wpi.first.wpilibj.GenericHID.RumbleType;
import edu.wpi.first.math.MathUtil;
import edu.wpi.first.math.VecBuilder;
import edu.wpi.first.math.Vector;
import edu.wpi.first.math.numbers.N2;
import com.pathplanner.lib.auto.AutoBuilder;
import com.pathplanner.lib.auto.NamedCommands;
import com.pathplanner.lib.commands.FollowPathCommand;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import edu.wpi.first.wpilibj2.command.Commands;
import edu.wpi.first.wpilibj2.command.button.CommandXboxController;
import frc.lib.slothtune.AkLogging;
import frc.lib.slothtune.SlothTune;
import frc.lib.slothtune.photonvision.PhotonVisionSetup;
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
  SlothTune tune = SlothTune.install(drive.getSwerveDrive(), drive, "Peashooter");
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
    // Mechanisms the Systems tab tunes, through each subsystem's own loop.
    shooter.tuneWith(tune);
    intake.tuneWith(tune);
    // Cameras: whatever slothtune.json's "vision" lists (none yet). Fitting one is a config change;
    // see docs/VISION_LUMA_PHOTONVISION.md.
    PhotonVisionSetup.install(tune);
    // Back button: hold off heat shutoffs for 20 s in a match (stalls still cut out).
    controller.back().onTrue(Commands.runOnce(() -> tune.overrideMotorShutoffs(20))
        // A short buzz says it took. A long one says a motor is still off (stalled, or too hot to
        // save) and Robot Health names it. "Heat override ON" shows the time left.
        .andThen(Commands.either(
            Commands.startEnd(() -> controller.setRumble(RumbleType.kBothRumble, 1.0),
                () -> controller.setRumble(RumbleType.kBothRumble, 0)).withTimeout(1.0),
            Commands.startEnd(() -> controller.setRumble(RumbleType.kBothRumble, 0.6),
                () -> controller.setRumble(RumbleType.kBothRumble, 0)).withTimeout(0.3),
            () -> !tune.motorsStillOff().isEmpty())));

  
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
    // The auto is built here, at boot, not when auto starts. The first path command after a boot
    // has to load every PathPlanner class, and building the auto reads its files: done in
    // autonomousInit, that held up the first auto after every boot (the second always worked).
    // The warmup follows a made-up path in the background while disabled so that loading is done
    // before the match; it never drives the robot (PathPlanner's docs: pathplanner.dev).
    autonomousCommand = AutoBuilder.buildAuto("W auto");
    CommandScheduler.getInstance().schedule(FollowPathCommand.warmupCommand());

    // The left stick is deadbanded by its distance from center (a round deadband), not each axis on
    // its own, so a gentle diagonal push keeps both axes instead of snapping to a straight line.
    drive.setDefaultCommand(drive.drive(
        () -> leftStick().get(0),
        () -> leftStick().get(1),
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

  /** The left stick as (Y, X), zero within 0.1 of center and rescaled from there: a round deadband. */
  private Vector<N2> leftStick() {
    return MathUtil.applyDeadband(VecBuilder.fill(controller.getLeftY(), controller.getLeftX()), 0.1);
  }

  @Override
  public void robotPeriodic() {
    CommandScheduler.getInstance().run();
    tune.periodic();
  }

  @Override
  public void autonomousInit() {
    if (autonomousCommand != null) { CommandScheduler.getInstance().schedule(autonomousCommand); }
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
