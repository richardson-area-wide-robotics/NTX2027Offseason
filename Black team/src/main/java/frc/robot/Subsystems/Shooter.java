package frc.robot.Subsystems;

import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.SparkClosedLoopController;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.config.SparkMaxConfig;

import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;

public class Shooter extends SubsystemBase {
    private final SparkMax shooterMotor = new SparkMax(0, MotorType.kBrushless);
    private final SparkMaxConfig shooterMotorConfig = new SparkMaxConfig();
    private final SparkClosedLoopController shooterMotorPID = shooterMotor.getClosedLoopController();
    
    private double hubTargetRPM = 5000.0;
    private double cornerATargetRPM = 5000.0;
    private double cornerBTargetRPM = 5000.0;
    private double p = 0.0001;
    private double i = 0;
    private double d = 0;

    public Shooter() {
    shooterMotorConfig.closedLoop.pid(p, i, d);
    shooterMotor.configure(shooterMotorConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
}

    public Command shootHub() {
        return this.startEnd(
            () -> shooterMotorPID.setSetpoint(hubTargetRPM, SparkMax.ControlType.kVelocity),
            () -> shooterMotor.set(0)
        );
    }
    public Command shootCornerA() {
        return this.startEnd(
            () -> shooterMotorPID.setSetpoint(cornerATargetRPM, SparkMax.ControlType.kVelocity),
            () -> shooterMotor.set(0)
        );
    }
    public Command shootCornerB() {
        return this.startEnd(
            () -> shooterMotorPID.setSetpoint(cornerBTargetRPM, SparkMax.ControlType.kVelocity),
            () -> shooterMotor.set(0)
        );
    }
}