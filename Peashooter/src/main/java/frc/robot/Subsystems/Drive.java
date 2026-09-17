package frc.robot.Subsystems;

import java.io.File;
import java.io.IOException;
import java.util.function.DoubleSupplier;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation2d;
import edu.wpi.first.math.geometry.Translation2d;
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
            swerveDrive = new SwerveParser(swerveConfigDirectory).createSwerveDrive(400,
                new Pose2d(new Translation2d(2, 2), new Rotation2d()));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
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