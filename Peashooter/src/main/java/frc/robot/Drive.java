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
    private final AprilTagFieldLayout tags = AprilTagFieldLayout.loadField(AprilTagFields.kDefaultField);

    private double continuousHeading = 0;
    private Rotation2d lastHeading = new Rotation2d();
    private double lastDirectionDeg = 0;

    private static final String TUNE = "Tuning/";
    private static final double DEFAULT_TRANSLATION_P = 2.0; 
    private static final double DEFAULT_HEADING_P = 4.0;      
    private static final double DEFAULT_MAX_SPEED = 1.5;      
    private static final double DEFAULT_MAX_ACCEL = 2.0;      
    private static final double DEFAULT_MAX_SPIN = 180;       
    private static final double DEFAULT_MAX_SPIN_ACCEL = 360; 
    private static final double DEFAULT_TEST_DISTANCE = 2.0;  
    private static final double DEFAULT_SKEW_COMP = 0.1;      

    public Drive() {
        File swerveConfigDirectory = new File(Filesystem.getDeployDirectory(), "swerve");
        try {
            swerveDrive = new SwerveParser(swerveConfigDirectory).createSwerveDrive(4.1,
                new Pose2d(new Translation2d(2, 2), new Rotation2d()));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        SwerveDriveTelemetry.verbosity = TelemetryVerbosity.HIGH;

        swerveDrive.setChassisDiscretization(true, 0.02);
        swerveDrive.setAngularVelocityCompensation(true, true, DEFAULT_SKEW_COMP);

        for (SwerveModule m : swerveDrive.getModules()) {
            setModulePID(m,
                new PIDFConfig(0.05, 0, 0, 0, 0),
                new PIDFConfig(0.01, 0, 0.0001, 0, 0));
        }

        lastHeading = swerveDrive.getOdometryHeading();

        SmartDashboard.setDefaultNumber(TUNE + "Translation P", DEFAULT_TRANSLATION_P);
        SmartDashboard.setDefaultNumber(TUNE + "Heading P", DEFAULT_HEADING_P);
        SmartDashboard.setDefaultNumber(TUNE + "Max Speed (mps)", DEFAULT_MAX_SPEED);
        SmartDashboard.setDefaultNumber(TUNE + "Max Accel (mps2)", DEFAULT_MAX_ACCEL);
        SmartDashboard.setDefaultNumber(TUNE + "Max Spin (degps)", DEFAULT_MAX_SPIN);
        SmartDashboard.setDefaultNumber(TUNE + "Max Spin Accel (degps2)", DEFAULT_MAX_SPIN_ACCEL);
        SmartDashboard.setDefaultNumber(TUNE + "Test Distance (m)", DEFAULT_TEST_DISTANCE);
        SmartDashboard.setDefaultNumber(TUNE + "Skew Comp", DEFAULT_SKEW_COMP);
    }

    public ChassisSpeeds getSpeeds() {
        return swerveDrive.getRobotVelocity();
    }

    @Override
    public void periodic() {
        Rotation2d h = swerveDrive.getOdometryHeading();
        continuousHeading += h.minus(lastHeading).getRadians();
        lastHeading = h;

        var v = swerveDrive.getFieldVelocity();
        double speed = Math.hypot(v.vxMetersPerSecond, v.vyMetersPerSecond);
        if (speed > 0.05) {
            lastDirectionDeg = Math.toDegrees(Math.atan2(v.vyMetersPerSecond, v.vxMetersPerSecond));
        }

        Pose2d pose = swerveDrive.getPose();

        AprilTag nearest = null;
        double best = Double.MAX_VALUE;
        for (AprilTag t : tags.getTags()) {
            double d = pose.getTranslation().getDistance(t.pose.toPose2d().getTranslation());
            if (d < best) { best = d; nearest = t; }
        }

        SmartDashboard.putString("Telemetry", String.format(
            "Vx %+.2f m/s | Vy %+.2f m/s | Dir %+.0f deg | Pos (%.2f, %.2f) m | Gyro %+.1f deg | Tag %s",
            v.vxMetersPerSecond,
            v.vyMetersPerSecond,
            lastDirectionDeg,
            pose.getX(),
            pose.getY(),
            swerveDrive.getYaw().getDegrees(),
            nearest == null ? "--" : String.format("%d @ %.2f m", nearest.ID, best)));
    }

    private void setModulePID(SwerveModule module, PIDFConfig drive, PIDFConfig angle) {
        module.getDriveMotor().configurePIDF(drive);
        module.getAngleMotor().configurePIDF(angle);
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

    // ---------------------------------------------------------------------------------------------
    // Drive tests
    // ---------------------------------------------------------------------------------------------

    /**
     * Drives the "Tuning/Test Distance (m)" in a straight line while optionally spinning.
     *
     * @param forward  +1 forward, -1 backward, 0 none (robot-relative, from where the robot starts)
     * @param left     +1 left, -1 right, 0 none
     * @param spinDeg  total rotation during the move; 0 holds the starting heading, 360 does a full turn
     */
    public Command driveTest(double forward, double left, double spinDeg) {
        return new ProfiledMove(new Translation2d(forward, left), Math.toRadians(spinDeg));
    }

    /**
     * Moves the robot along a straight line and turns it at the same time, both following one
     * shared motion profile so the spin starts and finishes exactly with the translation.
     * Translation is field-relative, so spinning never bends the path. Feedforward from the
     * profile does most of the work; P loops on position and heading correct drift.
     */
    private class ProfiledMove extends Command {
        private final Translation2d direction; // robot-relative unit direction at start
        private final double spinRad;
        private final Timer timer = new Timer();
        private final PIDController xPid = new PIDController(0, 0, 0);
        private final PIDController yPid = new PIDController(0, 0, 0);
        private final PIDController headingPid = new PIDController(0, 0, 0);
        private final TrapezoidProfile.State startState = new TrapezoidProfile.State(0, 0);
        private final TrapezoidProfile.State goalState = new TrapezoidProfile.State(1, 0);

        private TrapezoidProfile profile;
        private double totalTime;
        private Translation2d startPos;
        private Translation2d delta;   // field-relative displacement for the whole move
        private double startHeading;
        private double maxSpeed;
        private double maxSpin;

        ProfiledMove(Translation2d direction, double spinRad) {
            this.direction = direction;
            this.spinRad = spinRad;
            addRequirements(Drive.this);
        }

        @Override
        public void initialize() {
            double kP = SmartDashboard.getNumber(TUNE + "Translation P", DEFAULT_TRANSLATION_P);
            xPid.setP(kP);
            yPid.setP(kP);
            headingPid.setP(SmartDashboard.getNumber(TUNE + "Heading P", DEFAULT_HEADING_P));
            xPid.reset();
            yPid.reset();
            headingPid.reset();
            swerveDrive.setAngularVelocityCompensation(true, true,
                SmartDashboard.getNumber(TUNE + "Skew Comp", DEFAULT_SKEW_COMP));

            maxSpeed = SmartDashboard.getNumber(TUNE + "Max Speed (mps)", DEFAULT_MAX_SPEED);
            double maxAccel = SmartDashboard.getNumber(TUNE + "Max Accel (mps2)", DEFAULT_MAX_ACCEL);
            maxSpin = Math.toRadians(SmartDashboard.getNumber(TUNE + "Max Spin (degps)", DEFAULT_MAX_SPIN));
            double maxSpinAccel = Math.toRadians(
                SmartDashboard.getNumber(TUNE + "Max Spin Accel (degps2)", DEFAULT_MAX_SPIN_ACCEL));
            double distance = SmartDashboard.getNumber(TUNE + "Test Distance (m)", DEFAULT_TEST_DISTANCE);

            Pose2d pose = swerveDrive.getPose();
            startPos = pose.getTranslation();
            delta = direction.times(distance).rotateBy(pose.getRotation());
            startHeading = continuousHeading;

            // Profile a progress value s from 0 to 1. Its limits are the tighter of the
            // translation and rotation limits, so neither axis exceeds its max.
            double length = delta.getNorm();
            double angle = Math.abs(spinRad);
            double sVel = Double.MAX_VALUE;
            double sAccel = Double.MAX_VALUE;
            if (length > 1e-6) {
                sVel = Math.min(sVel, maxSpeed / length);
                sAccel = Math.min(sAccel, maxAccel / length);
            }
            if (angle > 1e-6) {
                sVel = Math.min(sVel, maxSpin / angle);
                sAccel = Math.min(sAccel, maxSpinAccel / angle);
            }
            if (sVel == Double.MAX_VALUE) { sVel = 1; sAccel = 1; }

            profile = new TrapezoidProfile(new TrapezoidProfile.Constraints(sVel, sAccel));
            profile.calculate(0, startState, goalState);
            totalTime = profile.totalTime();
            timer.restart();
        }

        @Override
        public void execute() {
            TrapezoidProfile.State s = profile.calculate(timer.get(), startState, goalState);

            Translation2d target = startPos.plus(delta.times(s.position));
            Translation2d feedforward = delta.times(s.velocity);
            Translation2d pos = swerveDrive.getPose().getTranslation();

            double vx = feedforward.getX() + xPid.calculate(pos.getX(), target.getX());
            double vy = feedforward.getY() + yPid.calculate(pos.getY(), target.getY());
            Translation2d v = new Translation2d(vx, vy);
            double limit = maxSpeed * 1.2; // a little headroom for correction
            if (v.getNorm() > limit) {
                v = v.times(limit / v.getNorm());
            }

            double headingTarget = startHeading + spinRad * s.position;
            double omega = spinRad * s.velocity + headingPid.calculate(continuousHeading, headingTarget);
            omega = MathUtil.clamp(omega, -maxSpin * 1.2, maxSpin * 1.2);

            swerveDrive.drive(v, omega, true, false);
        }

        @Override
        public boolean isFinished() {
            double t = timer.get();
            if (t < totalTime) return false;
            if (t > totalTime + 1.5) return true; // don't hang if it can't settle
            Translation2d goal = startPos.plus(delta);
            boolean atPos = swerveDrive.getPose().getTranslation().getDistance(goal) < 0.03;
            boolean atHeading = Math.abs(startHeading + spinRad - continuousHeading) < Math.toRadians(2);
            return atPos && atHeading;
        }

        @Override
        public void end(boolean interrupted) {
            swerveDrive.drive(new Translation2d(), 0, true, false);
        }
    }

}
