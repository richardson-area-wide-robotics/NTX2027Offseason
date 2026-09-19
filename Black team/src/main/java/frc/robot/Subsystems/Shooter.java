package frc.robot.Subsystems;


import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.SparkClosedLoopController;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.config.SparkMaxConfig;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;

public class Shooter extends SubsystemBase {
    SparkMax shooterMotor = new SparkMax(0, MotorType.kBrushless);
    SparkMaxConfig shooterMotorConfig = new SparkMaxConfig();
    SparkClosedLoopController shooterMotorPID = shooterMotor.getClosedLoopController();
    public Command shootHub(){
       
        return this.startEnd(
            () -> shooterMotor.set(1),
            () -> shooterMotor.set(0)
        );
    }



}
