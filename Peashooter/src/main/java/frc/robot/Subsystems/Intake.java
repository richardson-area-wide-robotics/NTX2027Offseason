package frc.robot.Subsystems;

import com.revrobotics.PersistMode;
import com.revrobotics.RelativeEncoder;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkBase.ControlType;
import com.revrobotics.spark.SparkClosedLoopController;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.config.SparkFlexConfig;

import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.Commands;
import edu.wpi.first.wpilibj2.command.SubsystemBase;

public class Intake extends SubsystemBase {

  private static final double INTAKE_UP_POSITION = 0.0;
  private static final double INTAKE_DOWN_POSITION = 10.0;

  // pid
  private static final double kP = 0.1;
  private static final double kI = 0.0;
  private static final double kD = 0.0;

  private static final double INTAKE_SPIN_SPEED = 1.0;

  // Up down motor
  private final SparkFlex intakeMoveMotor = new SparkFlex(12, MotorType.kBrushless);
  private final SparkClosedLoopController moveController = intakeMoveMotor.getClosedLoopController();
  private final RelativeEncoder moveEncoder = intakeMoveMotor.getEncoder(); 

  // Wheel Motors
  private final SparkFlex intakeSpinMotorOne = new SparkFlex(13, MotorType.kBrushless);
  private final SparkFlex intakeSpinMotorTwo = new SparkFlex(15, MotorType.kBrushless);

  private double targetPosition = INTAKE_UP_POSITION;

  public Intake() {
    SparkFlexConfig moveConfig = new SparkFlexConfig();
    moveConfig.closedLoop.p(kP).i(kI).d(kD);
    intakeMoveMotor.configure(moveConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
  }

  @Override
  public void periodic() {
    if (DriverStation.isDisabled()) {
      targetPosition = moveEncoder.getPosition();
      return;
    }
    moveController.setSetpoint(targetPosition, ControlType.kPosition);
  }

  public Command moveIntakeCommand() {
    return Commands.runOnce(() -> {
      boolean isUp = Math.abs(targetPosition - INTAKE_UP_POSITION)
                   < Math.abs(targetPosition - INTAKE_DOWN_POSITION);
      targetPosition = isUp ? INTAKE_DOWN_POSITION : INTAKE_UP_POSITION;
    });
  }

  // Intake Balls Command
  public Command spinIntakeCommand() {
    return this.runEnd(
        () -> {
          intakeSpinMotorOne.set(INTAKE_SPIN_SPEED);
          intakeSpinMotorTwo.set(-INTAKE_SPIN_SPEED);
        },
        () -> {
          intakeSpinMotorOne.set(0);
          intakeSpinMotorTwo.set(0);
        });
  }

  // Outake Balls Command
  public Command reverseIntakeCommand() {
    return this.runEnd(
        () -> {
          intakeSpinMotorOne.set(-INTAKE_SPIN_SPEED);
          intakeSpinMotorTwo.set(INTAKE_SPIN_SPEED);
        },
        () -> {
          intakeSpinMotorOne.set(0);
          intakeSpinMotorTwo.set(0);
        });
  }
}
