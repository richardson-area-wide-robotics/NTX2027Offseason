package frc.robot;

import java.io.File;
import java.io.IOException;
import java.util.function.DoubleSupplier;

import edu.wpi.first.math.MathUtil;
import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
import edu.wpi.first.wpilibj.Filesystem;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import swervelib.SwerveDrive;
import swervelib.parser.SwerveParser;
import swervelib.telemetry.SwerveDriveTelemetry;
import swervelib.telemetry.SwerveDriveTelemetry;

public class Drive extends SubsystemBase {
    private SwerveDrive swerveDrive;
    // NEO, 5.50 gear ratio, 3in wheel: ~4.1 m/s free speed
    private static final double MAX_SPEED = 4.1;
    private static final double MAX_ROTATION = 2 * Math.PI;
    private boolean fieldR = true;

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
    }

    public Command drive(DoubleSupplier translationX, DoubleSupplier translationY, DoubleSupplier rotation) {
    return this.run(() -> {
        // Xbox stick: up/left are negative; WPILib: +x forward, +y left, +rot CCW
        swerveDrive.drive(new Translation2d(
                -MathUtil.applyDeadband(translationY.getAsDouble(), 0.08) * MAX_SPEED,
                -MathUtil.applyDeadband(translationX.getAsDouble(), 0.08) * MAX_SPEED),
            -MathUtil.applyDeadband(rotation.getAsDouble(), 0.08) * MAX_ROTATION,
            fieldR,
            false);
    });

    
}

    public Command toggleFieldRelative() {
    return this.runOnce(() -> fieldR = !fieldR);
}

    /** The YAGSL drive, for the swerve tuning tools. */
    public SwerveDrive getSwerveDrive() {
        return swerveDrive;
    }
}