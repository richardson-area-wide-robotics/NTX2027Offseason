package frc.robot.Subsystems;

import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkBase.ControlType;
import com.revrobotics.spark.SparkClosedLoopController;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.config.SparkFlexConfig;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;

public class Shooter extends SubsystemBase{
// ids 10, 11
SparkFlex leader = new SparkFlex(10, MotorType.kBrushless);
SparkFlex follower = new SparkFlex(11, MotorType.kBrushless);
SparkClosedLoopController leaderPID = leader.getClosedLoopController();

    public Shooter() {
        SparkFlexConfig leaderConfig = new SparkFlexConfig();
        leaderConfig.closedLoop.pid(0.0004, 0, 0);
        leaderConfig.idleMode(SparkFlexConfig.IdleMode.kCoast);

        SparkFlexConfig followerConfig = new SparkFlexConfig();
        followerConfig.follow(leader, true).idleMode(SparkFlexConfig.IdleMode.kCoast);

        leader.configure(leaderConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
        follower.configure(followerConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
    }

    public Command shootB() {
        return this.startEnd(() -> leaderPID.setSetpoint(2100, ControlType.kVelocity), () -> leader.set(0));
    }

    public Command shootA() {
        return this.startEnd(() -> leaderPID.setSetpoint(2900, ControlType.kVelocity), () -> leader.set(0));
    }
}