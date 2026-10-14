package frc.lib.slothtune;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.CommandScheduler;
import edu.wpi.first.wpilibj2.command.Commands;
import edu.wpi.first.wpilibj2.command.Subsystem;

/**
 * Takes the drivetrain away from the teleop default command while a test runs.
 *
 * <p>Without this the default drive command and the test would both write module setpoints every
 * loop and fight. Holding the drive subsystem's requirement makes the command scheduler suspend the
 * default command, and releasing it lets the default command resume — the driver gets the robot
 * back the moment a test ends or aborts.
 *
 * <p>The only place the library touches the command framework, so moving to Commands v3 (which in
 * 2027 cannot be installed alongside v2) means replacing {@link CommandsV2} and nothing else.
 */
public interface DriveOwnership {
  void acquire();

  void release();

  /** Whether the test still holds the drivetrain. */
  default boolean isHeld() {
    return true;
  }

  /**
   * Pauses all of the robot's code for a test that runs a mechanism's motor directly: every
   * command cancelled and the scheduler stopped, so no subsystem's periodic sets a motor.
   */
  default void pauseRobotCode() {}

  /** Undoes {@link #pauseRobotCode}: default commands come back on the next loop. */
  default void resumeRobotCode() {}

  /** Does nothing. For robots that drive without the command framework, and for tests. */
  DriveOwnership NONE =
      new DriveOwnership() {
        @Override
        public void acquire() {}

        @Override
        public void release() {}
      };

  /** Commands v2. */
  final class CommandsV2 implements DriveOwnership {
    private final Command hold;

    public CommandsV2(Subsystem drive) {
      // kCancelIncoming: a button bound to the drive subsystem (Y toggling field-relative) can't take
      // the drivetrain away mid-test; the scheduler refuses that command instead.
      hold = Commands.run(() -> {}, drive).withName("SlothTune test")
          .withInterruptBehavior(Command.InterruptionBehavior.kCancelIncoming);
    }

    @Override
    public boolean isHeld() {
      return hold.isScheduled();
    }

    @Override
    public void acquire() {
      if (!hold.isScheduled()) {
        CommandScheduler.getInstance().schedule(hold);
      }
    }

    @Override
    public void release() {
      if (hold.isScheduled()) {
        hold.cancel();
      }
    }

    @Override
    public void pauseRobotCode() {
      CommandScheduler.getInstance().cancelAll();
      CommandScheduler.getInstance().disable();
    }

    @Override
    public void resumeRobotCode() {
      CommandScheduler.getInstance().enable();
    }
  }
}
