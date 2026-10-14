package frc.lib.swervetune;

import edu.wpi.first.wpilibj2.command.Subsystem;
import java.util.function.DoubleConsumer;

/**
 * Holding a game piece by the motor's current limit, as the 2024 robot held its note: the roller
 * pushes into the piece at a small power, and the current limit, not the power, sets how hard. Too
 * little and a knock shakes the piece out; too much and the motor cooks while it waits. The
 * Systems tab tunes it the way the slip test tunes the drive current: with a piece in, it steps
 * the limit down while a person pulls the piece the same way each time, finds where it slips, and
 * holds at half as much again, then checks how fast the motor warms at that.
 *
 * <pre>
 *   intakeHold = tune.holdCurrent("Intake roller", intakeMotor::set).subsystem(this);
 *   // a command: intakeHold.on() when it starts, intakeHold.off() when it ends
 * </pre>
 *
 * <p>The motor guard knows it is a hold: the stall timer rests (a hold is a stall on purpose) while
 * its heat rules still apply, and a hot motor's hold is halved like any limit. swervetune.json's
 * {@code "holds"} gives the current and the power; until tuned, half the motor's limit at 0.25.
 */
public final class HoldCurrent {
  final String motorName;
  final MotorGuard.Motor motor;
  final DoubleConsumer setDuty;
  Subsystem subsystem;
  /** Amps the hold is limited to. */
  double currentA;
  /** The power it pushes with, -1 to 1 (its sign: which way is into the piece). */
  double duty = 0.25;
  /** Whether swervetune.json gave the current (the Systems tab's tuning). */
  boolean tuned;
  private volatile boolean on;

  HoldCurrent(String motorName, MotorGuard.Motor motor, DoubleConsumer setDuty) {
    this.motorName = motorName;
    this.motor = motor;
    this.setDuty = setDuty;
    this.currentA = motor == null ? 10 : Math.max(MotorGuard.SHUTOFF_LIMIT_A, motor.baseLimitA() / 2.0);
  }

  /** The subsystem that owns the motor, held while the tool tunes it. */
  public HoldCurrent subsystem(Subsystem subsystem) {
    this.subsystem = subsystem;
    return this;
  }

  /** Starts holding: the limit drops to the hold current, and the motor pushes at the hold power. */
  public void on() {
    run(currentA, duty);
  }

  /** Stops holding: the motor stops and its normal limit comes back. */
  public void off() {
    on = false;
    if (motor != null) {
      motor.release();
    }
    setDuty.accept(0);
  }

  /** Holding at any current and power: the tuning test's way in. */
  void run(double amps, double power) {
    on = true;
    if (motor != null) {
      motor.hold((int) Math.round(amps));
    }
    setDuty.accept(power);
  }

  public boolean isOn() {
    return on;
  }

  /** The hold current, amps. */
  public double amps() {
    return currentA;
  }

  /** The hold power, -1 to 1. */
  public double duty() {
    return duty;
  }

  public String name() {
    return motorName;
  }

  void configure(double[] c) {
    if (c == null) {
      return;
    }
    if (Double.isFinite(c[0]) && c[0] > 0) {
      currentA = c[0];
      tuned = true;
    }
    if (Double.isFinite(c[1])) {
      duty = Math.max(-1, Math.min(1, c[1]));
    }
  }
}
