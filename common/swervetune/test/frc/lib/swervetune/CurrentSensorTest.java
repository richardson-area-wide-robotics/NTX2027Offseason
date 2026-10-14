package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/** A game piece sensed from a motor's own current: spin-up ignored, held long enough, latched. */
class CurrentSensorTest {
  private double t;

  private CurrentSensor sensor(String mode, double threshold) {
    CurrentSensor s = new CurrentSensor("Intake has piece", "Intake roller", null, null);
    SwerveTuneConfig.CurrentSensorConfig c = new SwerveTuneConfig.CurrentSensorConfig();
    c.mode = mode;
    c.thresholdA = threshold;
    c.holdS = 0.06;
    c.ignoreS = 0.3;
    s.configure(c);
    return s;
  }

  private void run(CurrentSensor s, double seconds, double amps, double duty, double pos) {
    for (int i = 0; i < Math.round(seconds / 0.02); i++) {
      t += 0.02;
      s.update(t, amps, duty, pos);
    }
  }

  @Test
  void aSpinUpSpikeIsIgnoredAndAPieceIsLatched() {
    CurrentSensor s = sensor("rise", 15);
    run(s, 0.2, 40, 0.6, Double.NaN);
    assertFalse(s.hasPiece(), "the spin-up spike, inside the ignore window");
    run(s, 1.0, 6, 0.6, Double.NaN);
    assertFalse(s.hasPiece(), "running empty");
    run(s, 0.04, 25, 0.6, Double.NaN);
    assertFalse(s.hasPiece(), "too short to count");
    run(s, 0.04, 6, 0.6, Double.NaN);
    run(s, 0.2, 25, 0.6, Double.NaN);
    assertTrue(s.hasPiece(), "a piece pushing against the roller");
    run(s, 1.0, 0, 0, Double.NaN);
    assertTrue(s.hasPiece(), "stopped with the piece in: still has it");
    assertFalse(s.detected());
    s.clear();
    assertFalse(s.hasPiece());
  }

  @Test
  void aDropAndUncalibrated() {
    CurrentSensor d = sensor("drop", 4);
    run(d, 1.0, 9, 0.5, Double.NaN);
    assertFalse(d.hasPiece());
    run(d, 0.2, 2, 0.5, Double.NaN);
    assertTrue(d.hasPiece());
    CurrentSensor never = sensor("rise", Double.NaN);
    run(never, 2, 60, 0.5, Double.NaN);
    assertFalse(never.hasPiece(), "uncalibrated: never");
    assertFalse(never.calibrated());
  }

  @Test
  void anArmAboveWhatItDrawsEmptyThere() {
    CurrentSensor a = sensor("aboveBaseline", 3);
    a.baseline = new double[][] {{0, 2}, {90, 8}};
    assertEquals(5, CurrentSensor.baselineAt(a.baseline, 45), 1e-9);
    run(a, 1.0, 7, 0.2, 45);
    assertFalse(a.hasPiece(), "2 A over the empty 5 A: under the 3 A threshold");
    run(a, 0.2, 9, 0.2, 45);
    assertTrue(a.hasPiece(), "4 A over");
  }
}
