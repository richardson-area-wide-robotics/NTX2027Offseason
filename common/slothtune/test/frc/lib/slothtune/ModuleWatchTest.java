package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/** The laptop monitor's module checks, on the robot: held long enough, counted once per episode. */
class ModuleWatchTest {
  private final ModuleWatch w = new ModuleWatch(new String[] {"frontleft", "frontright"});
  private double t;

  /** Runs for a while with module 0 at these readings and module 1 behaving. */
  private void run(double seconds, boolean enabled, double steer, double sp, double motor, double v, double vSp) {
    for (int i = 0; i < Math.round(seconds / 0.02); i++) {
      t += 0.02;
      w.update(t, enabled, new double[] {steer, 0}, new double[] {sp, 0}, new double[] {motor, 0},
          new double[] {v, 0}, new double[] {vSp, 0});
    }
  }

  private ModuleWatch.Flag flag(String module, ModuleWatch.Rule r) {
    return w.flags().stream().filter(f -> f.module.equals(module) && f.rule == r).findFirst().orElseThrow();
  }

  @Test
  void steeringOffItsAngleCountsOnceAfterHalfASecond() {
    run(0.3, true, 0, 30, 0, 1.0, 1.0);
    assertEquals(0, flag("frontleft", ModuleWatch.Rule.STEER_OFF).count, "not yet: a quick move is fine");
    run(0.4, true, 0, 30, 0, 1.0, 1.0);
    var f = flag("frontleft", ModuleWatch.Rule.STEER_OFF);
    assertEquals(1, f.count);
    assertTrue(f.active);
    run(2.0, true, 0, 30, 0, 1.0, 1.0);
    assertEquals(1, f.count, "one long episode is one");
    run(0.2, true, 30, 30, 30, 1.0, 1.0);
    run(0.8, true, 0, 30, 0, 1.0, 1.0);
    assertEquals(2, f.count, "a new episode counts again");
    assertEquals(0, flag("frontright", ModuleWatch.Rule.STEER_OFF).count);
  }

  @Test
  void anglesWrapAroundAndDisabledIsQuiet() {
    run(1.0, true, 179, -179, 179, 1.0, 1.0);
    assertEquals(0, flag("frontleft", ModuleWatch.Rule.STEER_OFF).count, "179 and -179 are 2 degrees apart");
    run(1.0, false, 0, 90, 0, 0, 1.0);
    assertEquals(0, flag("frontleft", ModuleWatch.Rule.STEER_OFF).count, "disabled: nothing is commanded");
  }

  @Test
  void theTwoSteeringSensorsDisagreeingWhileStill() {
    run(1.2, false, 10, 10, 15, 0, 0);
    assertEquals(1, flag("frontleft", ModuleWatch.Rule.SENSORS_DISAGREE).count, "5 degrees apart, standing still");
    run(1.2, false, 10, 10, 12, 0, 0);
    assertFalse(flag("frontleft", ModuleWatch.Rule.SENSORS_DISAGREE).active, "2 degrees is within 3");
    run(1.2, true, 10, 10, 15, 2.0, 2.0);
    assertEquals(1, flag("frontleft", ModuleWatch.Rule.SENSORS_DISAGREE).count, "moving: the motor encoder lags; not judged");
  }

  @Test
  void aWheelTurningAgainstItsCommand() {
    run(0.5, true, 0, 0, 0, -0.8, 1.0);
    assertEquals(1, flag("frontleft", ModuleWatch.Rule.BACKWARDS).count);
    run(0.5, true, 0, 0, 0, 0.05, 1.0);
    assertFalse(flag("frontleft", ModuleWatch.Rule.BACKWARDS).active, "barely turning is not backwards");
  }

  @Test
  void robotHealthKeepsTheCount() {
    DashboardAlerts alerts = new DashboardAlerts(false);
    run(0.6, true, 0, 0, 0, -0.8, 1.0);
    alerts.modules(w.flags());
    String line = alerts.showing.get("watch/frontleft/Backwards");
    assertTrue(line.startsWith("kWarning") && line.contains("once this session"), line);
    run(0.5, true, 0, 0, 0, 1.0, 1.0);
    alerts.modules(w.flags());
    assertTrue(alerts.showing.get("watch/frontleft/Backwards").contains("once this session"), "kept after it stops");
  }
}
