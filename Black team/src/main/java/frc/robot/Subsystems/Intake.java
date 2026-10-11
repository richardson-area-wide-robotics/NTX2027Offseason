package frc.robot.subsystems;

import com.revrobotics.spark.SparkBase.PersistMode;
import com.revrobotics.spark.SparkBase.ResetMode;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkMaxConfig;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;

/** Simple intake: one NEO on a SPARK MAX, in or out. */
public class Intake extends SubsystemBase {

  private static final int CAN_ID = 9;
  private static final double IN_SPEED = 0.8;
  private static final double OUT_SPEED = -0.6;

  private final SparkMax motor = new SparkMax(CAN_ID, MotorType.kBrushless);

  public Intake() {
    SparkMaxConfig config = new SparkMaxConfig();
    config.idleMode(IdleMode.kCoast).inverted(false);
    motor.configure(config, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
  }

  /** Intake in while held. */
  public Command intakeIn() {
    return startEnd(() -> motor.set(IN_SPEED), motor::stopMotor);
  }

  /** Intake out while held. */
  public Command intakeOut() {
    return startEnd(() -> motor.set(OUT_SPEED), motor::stopMotor);
  }
}