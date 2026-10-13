package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import frc.lib.swervetune.MotorGuard.Motor;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Red means broken now; yellow is history with its count; a shared cause is one line. */
class DashboardAlertsTest {
  private final MotorGuard guard = new MotorGuard();
  private final List<FakeMotorChannel> channels = new ArrayList<>();
  private final List<Motor> motors = new ArrayList<>();
  private final DashboardAlerts alerts = new DashboardAlerts(false);
  private double t;

  private FakeMotorChannel add(String name) {
    FakeMotorChannel c = new FakeMotorChannel(20);
    channels.add(c);
    motors.add(guard.register(name, c, MotorKind.NEO_550, false, false));
    return c;
  }

  private void run(double seconds) {
    for (long i = 0; i < Math.round(seconds / 0.02); i++) {
      channels.forEach(c -> c.advance(0.02));
      t += 0.02;
      guard.update(t);
    }
    alerts.update(motors, new double[0], guard.overrideRemainingS(t));
  }

  private String shown(String key) {
    return alerts.showing.getOrDefault(key, "");
  }

  @Test
  void aFaultThatAlreadyClearedIsYellowNotRed() {
    FakeMotorChannel c = add("Feeder");
    c.sticky = "sensor";
    run(0.1);
    assertEquals("", shown("Feeder/flags"), "nothing is broken now");
    assertTrue(shown("Feeder/history").startsWith("kWarning"), shown("Feeder/history"));
    c.faults = "gate driver";
    run(0.1);
    assertTrue(shown("Feeder/flags").startsWith("kError"), "an active fault is red");
  }

  @Test
  void aShutoffIsRedAndStaysCountedAfterItCools() {
    FakeMotorChannel c = add("Arm");
    c.ignoresLimit = true;
    c.demandA = 40;
    for (int i = 0; i < 3000 && !shown("Arm/shutoff").startsWith("kError"); i++) {
      run(0.02);
    }
    assertTrue(shown("Arm/shutoff").startsWith("kError"), "a cut motor is red, never a yellow warning");
    c.demandA = 0;
    for (int i = 0; i < 30000 && guard.motor("Arm").stage() != MotorGuard.Stage.OK; i++) {
      run(0.02);
    }
    assertEquals("", shown("Arm/shutoff"));
    assertTrue(shown("Arm/overheated").contains("cut off once"), shown("Arm/overheated"));
    assertTrue(shown("Arm/overheated").startsWith("kWarning"));
  }

  @Test
  void aBatteryDipOnMostMotorsIsOneLine() {
    for (int i = 0; i < 6; i++) {
      add("M" + i);
    }
    run(0.1);
    channels.forEach(c -> c.brownout = true);
    run(0.1);
    assertTrue(shown("flood/brownouts").contains("6 motors saw low voltage"), alerts.showing.toString());
    assertFalse(alerts.showing.keySet().stream().anyMatch(k -> k.startsWith("M") && k.endsWith("/brownouts")),
        "no line per motor: " + alerts.showing);
  }

  @Test
  void theDriversOverrideShowsWithTheTimeLeft() {
    add("Arm");
    run(0.1);
    assertEquals("", shown("override"));
    guard.override("ALL", 20, t);
    run(6);
    assertTrue(shown("override").contains("14 s left"), shown("override"));
  }
}
