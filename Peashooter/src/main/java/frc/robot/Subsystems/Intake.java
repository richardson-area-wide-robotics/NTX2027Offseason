package frc.robot.Subsystems;

import com.ctre.phoenix6.controls.DutyCycleOut;
import com.ctre.phoenix6.hardware.TalonFX;
import com.revrobotics.spark.SparkFlex;
import edu.wpi.first.wpilibj.Timer;
import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.FunctionalCommand;
import edu.wpi.first.wpilibj2.command.SequentialCommandGroup;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import java.util.concurrent.ForkJoinPool;
import com.revrobotics.spark.SparkLowLevel.MotorType;

public class Intake extends SubsystemBase {
  /*
  default command is going to be intake up
  when u click down on dpad it goes down
  dpad up the hopper goes down
  */
  /* We are making the code for a slapdown intake */

  // vars for the intake movement
  private static final double INTAKE_MOVE_SPEED = 1.0;
  private static final double INTAKE_MOVE_TIME_SECONDS = 1.0;
  public enum VerticalMotion {
    UP(true),
    DOWN(true),
    STATIONARY(false);

    private final boolean isMoving;

    VerticalMotion(boolean isMoving) {
      this.isMoving = isMoving;
    }

    public boolean isMoving() {
      return isMoving;
    }
  }

  // track position
  private VerticalMotion currentPosition = VerticalMotion.UP;

  // vars for spin thing
  private static final double INTAKE_SPIN_SPEED = 1.0;

  // timer
  private final Timer timer = new Timer();

  // Up down motor
  private final SparkFlex intakeMoveMotor = new SparkFlex(12, MotorType.kBrushless);

  //Wheel Motors
  private final SparkFlex intakeSpinMotorOne = new SparkFlex(13, MotorType.kBrushless);
  private final SparkFlex intakeSpinMotorTwo = new SparkFlex(15, MotorType.kBrushless);


  public Command moveIntakeCommand() {
    return new FunctionalCommand(
        () -> {
          timer.reset();
          timer.start();
        },

        () -> {
          if (currentPosition == VerticalMotion.UP) {
            intakeMoveMotor.set(INTAKE_MOVE_SPEED); // Move down
          } else if (currentPosition == VerticalMotion.DOWN) {
            intakeMoveMotor.set(-INTAKE_MOVE_SPEED); // Move up
          }
        },

        (interrupted) -> {
          intakeMoveMotor.set(0);
          timer.stop();
          if (!interrupted) {

            currentPosition =
                (currentPosition == VerticalMotion.UP) ? VerticalMotion.DOWN : VerticalMotion.UP;
          }
        },

        () -> timer.hasElapsed(INTAKE_MOVE_TIME_SECONDS), this);
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
