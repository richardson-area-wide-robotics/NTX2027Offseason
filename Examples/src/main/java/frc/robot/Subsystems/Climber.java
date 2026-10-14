package frc.robot.Subsystems;

import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkLowLevel.MotorType;
import com.revrobotics.spark.config.SparkBaseConfig.IdleMode;
import com.revrobotics.spark.config.SparkFlexConfig;

import edu.wpi.first.wpilibj2.command.Command;
import edu.wpi.first.wpilibj2.command.SubsystemBase;
import frc.lib.slothtune.MotorKind;
import frc.lib.slothtune.MotorWatcher;

/**
 * A winch climber, from 2025 Reefscape (DeepClimbSubsystem): two NEO Vortexes, the second
 * following the first and turning the other way, run by hand.
 *
 * <p>It stays a mechanism with nothing to tune: no sensor, no setpoint, no loop. The Systems tab
 * lists it with its motors; it becomes tunable once it has an encoder setpoint (and limits, found by
 * hand). What changed for 2027: a current limit on each motor (2025 had none).
 */
public class Climber extends SubsystemBase {

  private static final double SPEED = 0.3;

  // 2025: CAN 13, and 14 following.
  private final SparkFlex leader = new SparkFlex(61, MotorType.kBrushless);
  private final SparkFlex follower = new SparkFlex(62, MotorType.kBrushless);

  public Climber() {
    SparkFlexConfig config = new SparkFlexConfig();
    config.idleMode(IdleMode.kBrake).smartCurrentLimit(60);
    leader.configure(config, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
    SparkFlexConfig follow = new SparkFlexConfig();
    follow.idleMode(IdleMode.kBrake).smartCurrentLimit(60).follow(leader, true);
    follower.configure(follow, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
  }

  /** Winds in (climbs) while held. */
  public Command climb() {
    return this.runEnd(() -> leader.set(SPEED), () -> leader.set(0));
  }

  /** Lets out while held. */
  public Command release() {
    return this.runEnd(() -> leader.set(-SPEED), () -> leader.set(0));
  }

  public void watchMotors(MotorWatcher w) {
    w.watch("Climber", leader, MotorKind.VORTEX);
    w.watch("Climber follower", follower, MotorKind.VORTEX);
  }
}
