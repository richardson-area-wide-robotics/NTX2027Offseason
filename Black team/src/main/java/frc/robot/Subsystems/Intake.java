package frc.robot.subsystems;

import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkFlexConfig;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;

public class Intake extends SubsystemBase {
  private static final int MOTOR_ONE_ID = 13;
  private static final int MOTOR_TWO_ID = 15;
  private static final double IN_SPEED = 0.8;
  private static final double OUT_SPEED = -0.6;

  // Wheel Motors
  private final SparkFlex intakeSpinMotorOne = new SparkFlex(MOTOR_ONE_ID, MotorType.kBrushless);
  private final SparkFlex intakeSpinMotorTwo = new SparkFlex(MOTOR_TWO_ID, MotorType.kBrushless);

  public Intake() {
    SparkFlexConfig leaderConfig = new SparkFlexConfig();
    leaderConfig.idleMode(IdleMode.kCoast).smartCurrentLimit(40);
    intakeSpinMotorOne.configure(leaderConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);

    // Second wheel mirrors the first; flip the boolean if it spins the wrong way.
    SparkFlexConfig followerConfig = new SparkFlexConfig();
    followerConfig.idleMode(IdleMode.kCoast).smartCurrentLimit(40).follow(intakeSpinMotorOne, true);
    intakeSpinMotorTwo.configure(followerConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
  }

  public Command intake() {
    return this.startEnd(() -> intakeSpinMotorOne.set(IN_SPEED), () -> intakeSpinMotorOne.set(0));
  }

  public Command outtake() {
    return this.startEnd(() -> intakeSpinMotorOne.set(OUT_SPEED), () -> intakeSpinMotorOne.set(0));
  }
}
