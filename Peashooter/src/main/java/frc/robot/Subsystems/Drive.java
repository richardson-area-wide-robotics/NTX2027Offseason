package frc.robot.Subsystems;

import java.io.File;
import java.io.IOException;
import java.util.function.DoubleSupplier;

import com.pathplanner.lib.auto.AutoBuilder;
import com.pathplanner.lib.config.PIDConstants;
import com.pathplanner.lib.config.RobotConfig;
import com.pathplanner.lib.controllers.PPHolonomicDriveController;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.Filesystem;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import swervelib.SwerveDrive;
import swervelib.parser.SwerveParser;

public class Drive extends SubsystemBase {
    private SwerveDrive swerveDrive;
    private boolean fieldR = true;

    public Drive() {
        File swerveConfigDirectory = new File(Filesystem.getDeployDirectory(), "swerve");
        try {
            swerveDrive = new SwerveParser(swerveConfigDirectory).createSwerveDrive(4,
                new Pose2d(new Translation2d(2, 2), new Rotation2d()));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }
        public void setupPathPlanner() {

        RobotConfig config;

        try {
            config = RobotConfig.fromGUISettings();
        } catch (Exception e) {
            throw new RuntimeException(
                    "Failed to load PathPlanner RobotConfig",
                    e
            );
        }

        AutoBuilder.configure(
                // Robot pose supplier
                swerveDrive::getPose,

                // Reset robot odometry
                swerveDrive::resetOdometry,

                // Current robot-relative chassis speeds
                swerveDrive::getRobotVelocity,

                // Drive robot-relative
                (speeds, feedforwards) -> {
                    swerveDrive.setChassisSpeeds(speeds);
                },

                // Holonomic controller
                new PPHolonomicDriveController(
                        new PIDConstants(5.0, 0.0, 0.0),
                        new PIDConstants(5.0, 0.0, 0.0)
                ),

                // PathPlanner robot configuration
                config,

                // Mirror paths for red alliance
                () -> DriverStation.getAlliance()
                        .map(alliance ->
                                alliance == DriverStation.Alliance.Red)
                        .orElse(false),

                // Subsystem requirement
                this
        );
    }

    public Command drive(DoubleSupplier translationX, DoubleSupplier translationY, DoubleSupplier rotation) {
        return this.run(() -> {
            swerveDrive.drive(
                new Translation2d(
                    translationX.getAsDouble(),
                    translationY.getAsDouble()
                ),
                rotation.getAsDouble(),
                fieldR,
                false
            );
        });
    }
    
    public Command toggleFieldRelative() {
        return this.runOnce(() -> fieldR = !fieldR);
    }
    public Command resetPosition() {
        return this.runOnce(() -> swerveDrive.zeroGyro());
    }
    
}