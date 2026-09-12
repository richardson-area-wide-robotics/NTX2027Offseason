package frc.robot.Subsystems;

import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkFlexConfig;
import com.revrobotics.spark.config.SparkMaxConfig;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;

public class Feeder extends SubsystemBase{

    /*
     * 
     * 
     * 
     */
    
    SparkMax spindexterMotor = new SparkMax(1, MotorType.kBrushless);
    SparkMaxConfig spindexterConfig = new SparkMaxConfig();

    SparkFlex towerMotor = new SparkFlex(0, MotorType.kBrushless);
    SparkFlexConfig towerConfig = new SparkFlexConfig();
    
    public Feeder(){
        spindexterConfig.idleMode(SparkMaxConfig.IdleMode.kBrake);
        spindexterMotor.configure(towerConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
        towerConfig.idleMode(IdleMode.kBrake);  
        towerMotor.configure(towerConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
        
    }

    private void runFeeder(boolean forward){
        spindexterMotor.set(forward ? -1 : 1);
        towerMotor.set(forward ? -1 : 1);
    }

    private void stopFeeder() {
        spindexterMotor.stopMotor();
        towerMotor.stopMotor();
    }

    public Command load(boolean forward){
        return this.runEnd(() -> runFeeder(forward), () -> stopFeeder());
    }
}   
