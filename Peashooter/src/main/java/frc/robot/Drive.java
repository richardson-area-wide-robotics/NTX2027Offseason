package frc.robot;

import java.io.File;
import java.io.IOException;
import java.util.function.DoubleSupplier;

import com.pathplanner.lib.auto.AutoBuilder;
import com.pathplanner.lib.config.PIDConstants;
import com.pathplanner.lib.config.RobotConfig;
import com.pathplanner.lib.controllers.PPHolonomicDriveController;

import edu.wpi.first.apriltag.AprilTag;
import edu.wpi.first.apriltag.AprilTagFieldLayout;
import edu.wpi.first.apriltag.AprilTagFields;
import edu.wpi.first.math.MathUtil;
import edu.wpi.first.math.controller.PIDController;
import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.math.kinematics.ChassisSpeeds;
import edu.wpi.first.math.trajectory.TrapezoidProfile;
import edu.wpi.first.networktables.StructPublisher;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.Filesystem;
import edu.wpi.first.wpilibj.Timer;
import edu.wpi.first.wpilibj.smartdashboard.SmartDashboard;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import swervelib.SwerveDrive;
import swervelib.SwerveModule;
import swervelib.parser.PIDFConfig;
import swervelib.parser.SwerveParser;
import swervelib.telemetry.SwerveDriveTelemetry;
import swervelib.telemetry.SwerveDriveTelemetry.TelemetryVerbosity;

public class Drive extends SubsystemBase {
    private SwerveDrive swerveDrive;
    private boolean fieldR = true;
    
    
    StructPublisher<Pose2d> posePublisher;


    public Drive() {
        File swerveConfigDirectory = new File(Filesystem.getDeployDirectory(), "swerve");
        try {
            swerveDrive = new SwerveParser(swerveConfigDirectory).createSwerveDrive(4.1,
                new Pose2d(new Translation2d(2, 2), new Rotation2d()));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        SwerveDriveTelemetry.verbosity = TelemetryVerbosity.HIGH;
    }

        @Override
    public void periodic(){
        posePublisher.set(swerveDrive.getPose());
    }
//
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

                swerveDrive::getPose,


                swerveDrive::resetOdometry,

                swerveDrive::getRobotVelocity,


                (speeds, feedforwards) -> {
                    swerveDrive.setChassisSpeeds(speeds);
                },


                new PPHolonomicDriveController(
                        new PIDConstants(5.0, 0.0, 0.1),
                        new PIDConstants(5.0, 0.0, 0.1)
                ),


                config,


                () -> DriverStation.getAlliance()
                        .map(alliance ->
                                alliance == DriverStation.Alliance.Red)
                        .orElse(false),


                this
        );
    }

    public Command drive(DoubleSupplier translationX, DoubleSupplier translationY, DoubleSupplier rotation) {

        return this.run(() -> {
            double max = swerveDrive.getMaximumChassisVelocity()*0.8;

            swerveDrive.drive(
                new Translation2d(
                    translationX.getAsDouble() * max,
                    translationY.getAsDouble() * max
                ),
                rotation.getAsDouble()*3,
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
