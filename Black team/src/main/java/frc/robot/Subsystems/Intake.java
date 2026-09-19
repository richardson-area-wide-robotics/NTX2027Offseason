package frc.robot.Subsystems;

import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;

public class Intake extends SubsystemBase{
    SparkFlex intakeMotor = new SparkFlex(0, MotorType.kBrushless);
    private double INTAKE_SPIN_SPEED = 1.0; 

    public Command spinIntakeCommand(){
        return this.runEnd(
            () -> intakeMotor.set(INTAKE_SPIN_SPEED),
            () -> intakeMotor.set(0)
        );
    }

    public Command reverseIntakeCommand() {
        return this.runEnd(
            () -> intakeMotor.set(-INTAKE_SPIN_SPEED),
            () -> intakeMotor.set(0)
        );
    }
}
