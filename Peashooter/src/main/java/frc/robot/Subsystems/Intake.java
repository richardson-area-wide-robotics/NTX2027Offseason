package frc.robot.Subsystems;

import edu.wpi.first.wpilibj.Timer;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.FunctionalCommand;
import edu.wpi.first.wpilibj2.command.SubsystemBase;

import com.revrobotics.spark.SparkBase.ControlType;
import com.revrobotics.spark.SparkClosedLoopController;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkFlexConfig;
import com.revrobotics.spark.config.SparkMaxConfig;


public class Intake extends SubsystemBase {

  private static final double POSITION_TOLERANCE = 0.5;
  public static boolean INTAKE_IS_UP = true;
 

  private static final double INTAKE_UP_POSITION = 0.0;
  private static final double INTAKE_DOWN_POSITION = 10.0;
 
  //pid
  private static final double kP = 0.1;
  private static final double kI = 0.0;
  private static final double kD = 0.0;
 
  private static final double INTAKE_SPIN_SPEED = 1.0;
 
  // Up down motor
  private final SparkFlex intakeMoveMotor = new SparkFlex(12, MotorType.kBrushless);
  private final SparkClosedLoopController moveController = intakeMoveMotor.getClosedLoopController();
 
  // Wheel Motors
  private final SparkFlex intakeSpinMotorOne = new SparkFlex(13, MotorType.kBrushless);
  private final SparkFlex intakeSpinMotorTwo = new SparkFlex(15, MotorType.kBrushless);


  public Intake() {
    SparkFlexConfig moveConfig = new SparkFlexConfig();
    moveConfig.closedLoop.p(kP).i(kI).d(kD);
    intakeMoveMotor.configure(moveConfig, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
  }

 private double targetPosition() {
    return INTAKE_IS_UP ? INTAKE_DOWN_POSITION : INTAKE_UP_POSITION;
  }
 
  public Command moveIntakeCommand() {
    return new FunctionalCommand(
        () -> moveController.setSetpoint(targetPosition(), ControlType.kPosition),
 
        () -> {},
        
        (interrupted) -> {
          if (interrupted) {
            intakeMoveMotor.set(0);
          } else {
            INTAKE_IS_UP = !INTAKE_IS_UP;
          }
        },

        () -> Math.abs(intakeMoveMotor.getEncoder().getPosition() - targetPosition()) <= POSITION_TOLERANCE,
 
        this);
  }

  // Intake Balls Command
  public Command spinIntakeCommand() {
    return this.runEnd(
        () -> {
          intakeSpinMotorOne.set(INTAKE_SPIN_SPEED);
          intakeSpinMotorTwo.set(INTAKE_SPIN_SPEED);
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
          intakeSpinMotorTwo.set(-INTAKE_SPIN_SPEED);
        },
        () -> {
          intakeSpinMotorOne.set(0);
          intakeSpinMotorTwo.set(0);
        });
  }
}


/* change timer to move to and pid setpoint
 * make it so if you can cancel it by pressing again if it is less than 50% done
 * private commands
 */