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
import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.math.kinematics.ChassisSpeeds;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.Filesystem;
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
    private final AprilTagFieldLayout tags = AprilTagFieldLayout.loadField(AprilTagFields.kDefaultField);

    public Drive() {
        File swerveConfigDirectory = new File(Filesystem.getDeployDirectory(), "swerve");
        try {
            swerveDrive = new SwerveParser(swerveConfigDirectory).createSwerveDrive(100,
                new Pose2d(new Translation2d(2, 2), new Rotation2d()));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        SwerveDriveTelemetry.verbosity = TelemetryVerbosity.HIGH;

        swerveDrive.setChassisDiscretization(true, 0.02);

        var modules = swerveDrive.getModuleMap();
    
        setModulePID(modules.get("backright"),
            new PIDFConfig(0.002, 0, 0, 0, 0),
            new PIDFConfig(0.01, 0, 0, 0, 0));

        setModulePID(modules.get("frontright"),
            new PIDFConfig(0.05, 0, 0, 0, 0),
            new PIDFConfig(0.008, 0, 0.0001, 0, 0));

        setModulePID(modules.get("backleft"),
            new PIDFConfig(0.002, 0, 0, 0, 0),
            new PIDFConfig(0.01, 0, 0, 0, 0));

        setModulePID(modules.get("frontleft"),
            new PIDFConfig(0.05, 0, 0.0001, 0, 0),
            new PIDFConfig(0.008, 0, 0.0001, 0, 0));

    }

    public ChassisSpeeds getSpeeds() {
        return swerveDrive.getRobotVelocity();
    }

    @Override
    public void periodic() {
        var v = swerveDrive.getFieldVelocity();
        SmartDashboard.putNumber("Velocity X (mps)", v.vxMetersPerSecond);
        SmartDashboard.putNumber("Velocity Y (mps)", v.vyMetersPerSecond);
        SmartDashboard.putNumber("Speed (mps)", Math.hypot(v.vxMetersPerSecond, v.vyMetersPerSecond));
        SmartDashboard.putNumber("Direction (deg)", Math.toDegrees(Math.atan2(v.vyMetersPerSecond, v.vxMetersPerSecond)));

        // Distance from odometry pose to the nearest AprilTag on the field
        Translation2d pos = swerveDrive.getPose().getTranslation();
        AprilTag nearest = null;
        double best = Double.MAX_VALUE;
        for (AprilTag t : tags.getTags()) {
            double d = pos.getDistance(t.pose.toPose2d().getTranslation());
            if (d < best) { best = d; nearest = t; }
        }
        if (nearest != null) {
            SmartDashboard.putNumber("Nearest Tag ID", nearest.ID);
            SmartDashboard.putNumber("Nearest Tag Dist (m)", best);
        }
    }

    private void setModulePID(SwerveModule module, PIDFConfig drive, PIDFConfig angle) {
        module.getDriveMotor().configurePIDF(drive);
        module.getAngleMotor().configurePIDF(angle);
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
                
                swerveDrive::getPose,

                
                swerveDrive::resetOdometry,

                swerveDrive::getRobotVelocity,

                
                (speeds, feedforwards) -> {
                    swerveDrive.setChassisSpeeds(speeds);
                },

               
                new PPHolonomicDriveController(
                        new PIDConstants(5.0, 0.0, 0.1),
                        new PIDConstants(5.0, 0.0, 0.0)
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
            SmartDashboard.putNumber("x", translationX.getAsDouble());
            SmartDashboard.putNumber("y", translationY.getAsDouble());
            SmartDashboard.putNumber("rot", rotation.getAsDouble());

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