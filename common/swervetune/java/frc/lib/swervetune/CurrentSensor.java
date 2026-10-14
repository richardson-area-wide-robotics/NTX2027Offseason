package frc.lib.swervetune;

import java.util.function.DoubleSupplier;

/**
 * A game piece sensed through a motor's own current, as its motor controller reports it: no extra
 * hardware. An intake's roller draws more when a piece goes in and pushes against it; an arm
 * draws more holding a piece than holding nothing at the same angle. Register one in the
 * subsystem, after its motor is watched ({@link SwerveTune#watchMotor}):
 *
 * <pre>
 *   intakeSensor = tune.currentSensor("Intake has piece", "Intake roller");
 *   new Trigger(intakeSensor::hasPiece).onTrue(stopIntake);
 *   // once the piece has gone: intakeSensor.clear();
 * </pre>
 *
 * <p>What counts as a piece lives in swervetune.json's {@code "currentSensors"}, which the Systems
 * tab's calibration writes from runs with a set number of pieces: the threshold, how long the
 * current must stay past it, and how long to ignore after the motor starts (its spin-up draws a
 * spike of its own). Until then it never sees a piece. Three ways to read the current:
 *
 * <ul>
 *   <li>{@code rise}: above the threshold (an intake grabbing a piece);
 *   <li>{@code drop}: below it (a roller that eases once the piece has passed);
 *   <li>{@code aboveBaseline}: above what it draws empty at this position, by the threshold (an
 *       arm carrying a piece). The empty current at each position is measured too.
 * </ul>
 */
public final class CurrentSensor {
  /** How the current says there is a piece. */
  public enum Mode {
    RISE, DROP, ABOVE_BASELINE;

    static Mode of(String s) {
      return switch (s == null ? "" : s) {
        case "drop" -> DROP;
        case "aboveBaseline" -> ABOVE_BASELINE;
        default -> RISE;
      };
    }

    String key() {
      return switch (this) {
        case RISE -> "rise";
        case DROP -> "drop";
        case ABOVE_BASELINE -> "aboveBaseline";
      };
    }
  }

  /** A motor running below this duty is stopped: nothing to sense. */
  static final double RUNNING_DUTY = 0.02;

  final String name;
  final String motorName;
  final MotorGuard.Motor motor;
  /** The mechanism's position, for {@code aboveBaseline}; null otherwise. */
  final DoubleSupplier position;
  Mode mode = Mode.RISE;
  /** Amps: past this is a piece (above the baseline by this, for {@code aboveBaseline}). NaN: not calibrated. */
  double thresholdA = Double.NaN;
  /** Seconds the current must stay past the threshold. */
  double holdS = 0.06;
  /** Seconds ignored after the motor starts: its spin-up spike. */
  double ignoreS = 0.25;
  /** {position, amps} pairs, by position: the empty current, for {@code aboveBaseline}. */
  double[][] baseline = new double[0][];

  private boolean detected;
  private boolean latched;
  private double pastSince = Double.NaN;
  private double runningSince = Double.NaN;
  private double amps = Double.NaN;

  CurrentSensor(String name, String motorName, MotorGuard.Motor motor, DoubleSupplier position) {
    this.name = name;
    this.motorName = motorName;
    this.motor = motor;
    this.position = position;
  }

  /** True from the moment a piece is sensed until {@link #clear}: what the robot code reads. */
  public boolean hasPiece() {
    return latched;
  }

  /** True only while the current says so right now. */
  public boolean detected() {
    return detected;
  }

  /** Forgets the piece: call it once the piece has gone (shot, dropped, handed on). */
  public void clear() {
    latched = false;
  }

  /** Whether the Systems tab's calibration has given it a threshold yet. */
  public boolean calibrated() {
    return Double.isFinite(thresholdA);
  }

  /** The motor's current now, amps. */
  public double amps() {
    return amps;
  }

  public String name() {
    return name;
  }

  void configure(SwerveTuneConfig.CurrentSensorConfig c) {
    if (c == null) {
      return;
    }
    mode = Mode.of(c.mode);
    thresholdA = c.thresholdA;
    holdS = c.holdS;
    ignoreS = c.ignoreS;
    baseline = c.baseline;
  }

  /** The empty current at a position, straight-line between the measured ones. */
  static double baselineAt(double[][] table, double pos) {
    if (table.length == 0 || !Double.isFinite(pos)) {
      return Double.NaN;
    }
    if (pos <= table[0][0]) {
      return table[0][1];
    }
    for (int i = 1; i < table.length; i++) {
      if (pos <= table[i][0]) {
        double f = (pos - table[i - 1][0]) / (table[i][0] - table[i - 1][0]);
        return table[i - 1][1] + f * (table[i][1] - table[i - 1][1]);
      }
    }
    return table[table.length - 1][1];
  }

  /** One robot loop: reads the motor and decides. */
  void update(double now) {
    if (motor == null) {
      detected = false;
      return;
    }
    update(now, motor.amps(), motor.duty, position == null ? Double.NaN : position.getAsDouble());
  }

  void update(double now, double ampsNow, double duty, double pos) {
    amps = ampsNow;
    boolean running = Double.isFinite(duty) ? Math.abs(duty) > RUNNING_DUTY : Double.isFinite(ampsNow) && ampsNow > 0.5;
    if (!running) {
      runningSince = Double.NaN;
      pastSince = Double.NaN;
      detected = false;
      return;
    }
    if (Double.isNaN(runningSince)) {
      runningSince = now;
    }
    boolean past = false;
    if (calibrated() && Double.isFinite(ampsNow) && now - runningSince >= ignoreS) {
      past = switch (mode) {
        case RISE -> ampsNow > thresholdA;
        case DROP -> ampsNow < thresholdA;
        case ABOVE_BASELINE -> {
          double base = baselineAt(baseline, pos);
          yield Double.isFinite(base) && ampsNow - base > thresholdA;
        }
      };
    }
    if (past) {
      if (Double.isNaN(pastSince)) {
        pastSince = now;
      }
      detected = now - pastSince >= holdS;
    } else {
      pastSince = Double.NaN;
      detected = false;
    }
    if (detected) {
      latched = true;
    }
  }
}
