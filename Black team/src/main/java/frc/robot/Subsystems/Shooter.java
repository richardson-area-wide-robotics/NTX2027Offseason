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
    
    public Shooter() {
    shooterMotorConfig.closedLoop.pid(1, 0, 0);
    shooterMotor.configure(shooterMotorConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
}

    public Command shootHub() {
        return this.startEnd(
            () -> shooterMotorPID.setSetpoint(1000, SparkMax.ControlType.kVelocity),
            () -> shooterMotor.set(0)
        );
    }
    public Command shootCornerA() {
        return this.startEnd(
            () -> shooterMotorPID.setSetpoint(2000, SparkMax.ControlType.kVelocity),
            () -> shooterMotor.set(0)
        );
    }
    public Command shootCornerB() {
        return this.startEnd(
            () -> shooterMotorPID.setSetpoint(2000, SparkMax.ControlType.kVelocity),
            () -> shooterMotor.set(0)
        );
    }
}