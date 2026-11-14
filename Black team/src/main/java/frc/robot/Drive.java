package frc.robot;

import java.io.File;
import java.io.IOException;
import java.util.List;
import java.util.function.DoubleSupplier;

import org.photonvision.EstimatedRobotPose;

import com.pathplanner.lib.auto.AutoBuilder;
import com.pathplanner.lib.config.PIDConstants;
import com.pathplanner.lib.config.RobotConfig;
import com.pathplanner.lib.controllers.PPHolonomicDriveController;

import edu.wpi.first.math.MathUtil;
import edu.wpi.first.math.Matrix;
import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.math.numbers.N1;
import edu.wpi.first.math.numbers.N3;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StructPublisher;
import edu.wpi.first.util.sendable.Sendable;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.Filesystem;
import edu.wpi.first.wpilibj.smartdashboard.SmartDashboard;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import swervelib.SwerveDrive;
import swervelib.SwerveModule;
import swervelib.parser.PIDFConfig;
import swervelib.parser.SwerveParser;
import swervelib.simulation.ironmaple.simulation.opponentsim.SmartOpponentConfig.ModuleConfig;
import swervelib.telemetry.SwerveDriveTelemetry;
import swervelib.telemetry.SwerveDriveTelemetry.TelemetryVerbosity;

public class Drive extends SubsystemBase {
    private SwerveDrive swerveDrive;
    // NEO, 5.50 gear ratio, 3in wheel: ~4.1 m/s free speed
    private static final double MAX_SPEED = 4.1;
    private static final double MAX_ROTATION = 2 * Math.PI;
    private boolean fieldR = true;
    StructPublisher<Pose2d> posePublisher;
    
            

     Drive() {
        SwerveDriveTelemetry.verbosity = SwerveDriveTelemetry.TelemetryVerbosity.HIGH;
        File swerveConfigDirectory = new File(Filesystem.getDeployDirectory(), "swerve");
        try {
            SwerveDriveTelemetry.verbosity = SwerveDriveTelemetry.TelemetryVerbosity.HIGH;
            swerveDrive = new SwerveParser(swerveConfigDirectory).createSwerveDrive(MAX_SPEED,
             new Pose2d(new Translation2d(2,2), new Rotation2d()));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        SwerveDriveTelemetry.verbosity = TelemetryVerbosity.HIGH;
       posePublisher = NetworkTableInstance.getDefault()
            .getStructTopic("Pose", swerveDrive.getPose().struct).publish();
    }

    private void setModulePID(SwerveModule module, PIDFConfig drive, PIDFConfig angle) {
        module.getDriveMotor().configurePIDF(drive);
        module.getAngleMotor().configurePIDF(angle);
    }
    
    public Command drive(DoubleSupplier translationX, DoubleSupplier translationY, DoubleSupplier rotation) {
    return this.run(() -> {
        // Xbox stick: up/left are negative; WPILib: +x forward, +y left, +rot CCW
        swerveDrive.drive(new Translation2d(
                MathUtil.applyDeadband(translationY.getAsDouble(), 0.08) * MAX_SPEED,
                MathUtil.applyDeadband(translationX.getAsDouble(), 0.08) * MAX_SPEED),
            -MathUtil.applyDeadband(rotation.getAsDouble(), 0.08) * MAX_ROTATION,
            fieldR,
            false);
    });

    
    }  

    public void addVisionMeasurement(List<EstimatedRobotPose> poses, List<Double> timestamps, List<Matrix<N3,N1>> listOfVisionMeasurementStdDevs) {
        for(int i = 0; i < poses.size(); i++){
            swerveDrive.addVisionMeasurement(poses.get(i).estimatedPose.toPose2d(), timestamps.get(i), listOfVisionMeasurementStdDevs.get(i));
        }
    }

    public Command toggleFieldRelative() {
        return this.runOnce(() -> fieldR = !fieldR);
    }

    public Command resetGyro() {
        return this.runOnce(() -> swerveDrive.zeroGyro());
    }

    @Override
    public void periodic(){
        posePublisher.set(swerveDrive.getPose());
    }
    

}