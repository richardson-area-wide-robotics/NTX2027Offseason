package frc.robot.subsystems;

import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.SparkClosedLoopController;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.config.SparkMaxConfig;

import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.lib.swervetune.MotorKind;
import frc.lib.swervetune.MotorWatcher;

public class Shooter extends SubsystemBase {
    private final SparkMax shooterMotor = new SparkMax(10, MotorType.kBrushless);
    private final SparkMaxConfig shooterMotorConfig = new SparkMaxConfig();
    private final SparkClosedLoopController shooterMotorPID = shooterMotor.getClosedLoopController();
    
    public Shooter() {
    shooterMotorConfig.inverted(true);
    shooterMotorConfig.closedLoop.pid(1, 0, 0);
    shooterMotor.configure(shooterMotorConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
}

    public Command shootHub() {
        return this.startEnd(
            () -> shooterMotorPID.setSetpoint(3500, SparkMax.ControlType.kVelocity),
            () -> shooterMotor.set(0)
        );
    }
    public Command shootCornerA() {
        return this.startEnd(
            () -> shooterMotorPID.setSetpoint(5000, SparkMax.ControlType.kVelocity),
            () -> shooterMotor.set(0)
        );
    }
    public Command shootIntake() {
        return this.startEnd(
            () -> shooterMotor.set(-0.6),
            () -> shooterMotor.set(0)
        );
    }

    /** Lists this subsystem's motors for the motor guard (heat, stalls, failure). */
    public void watchMotors(MotorWatcher w) {
        // A SPARK MAX cannot tell a NEO 550 from a NEO: check what is fitted and correct this.
        w.watch("Shooter", shooterMotor, MotorKind.NEO_UNKNOWN);
    }
}
