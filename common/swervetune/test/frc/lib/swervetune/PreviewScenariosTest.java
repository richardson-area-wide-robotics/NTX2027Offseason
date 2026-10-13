package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * The drive team's dashboard at a few moments, from the robot code itself: the Robot Health alerts
 * and the Battery check line, built by the real MotorGuard, ModuleWatch, DashboardAlerts and
 * BatteryPicker. Every run checks them; with SWERVETUNE_PREVIEW_OUT set it also writes them where
 * the laptop's preview (tools/swervetune/preview) reads them, so the preview shows the words the
 * robot really sends.
 */
class PreviewScenariosTest {
  private final Map<String, String> json = new LinkedHashMap<>();

  private static String q(String s) {
    StringBuilder b = new StringBuilder("\"");
    for (char c : s.toCharArray()) {
      if (c == '"' || c == '\\') b.append('\\').append(c);
      else if (c < 0x20) b.append(' ');
      else if (c > 126) b.append(String.format("\\u%04x", (int) c));
      else b.append(c);
    }
    return b.append('"').toString();
  }

  private void scenario(String name, String check, Map<String, String> showing) {
    StringBuilder s = new StringBuilder("{\"check\": ").append(q(check)).append(", \"alerts\": [");
    boolean first = true;
    for (var e : showing.entrySet()) {
      s.append(first ? "\n    " : ",\n    ").append(q(e.getValue()));
      first = false;
    }
    json.put(name, s.append(first ? "]}" : "\n  ]}").toString());
  }

  static final class Rig {
    final MotorGuard guard = new MotorGuard();
    final List<FakeMotorChannel> ch = new ArrayList<>();
    final List<MotorGuard.Motor> motors = new ArrayList<>();
    final DashboardAlerts alerts = new DashboardAlerts(false);
    double t;

    // Peashooter's own CAN IDs, so each alert names the plug a person would check.
    static final Map<String, Integer> IDS = Map.of("frontleft drive", 5, "Shooter leader", 10, "Intake pivot", 12, "Spindexter", 14);

    FakeMotorChannel add(String name, MotorKind kind, int limit, boolean stall) {
      FakeMotorChannel c = new FakeMotorChannel(limit);
      c.canId = IDS.getOrDefault(name, 7);
      ch.add(c);
      motors.add(guard.register(name, c, kind, false, stall));
      return c;
    }

    void run(double s, double[] can) {
      for (long i = 0; i < Math.round(s / 0.02); i++) {
        ch.forEach(c -> c.advance(0.02));
        t += 0.02;
        guard.update(t);
      }
      alerts.update(motors, can, guard.overrideRemainingS(t));
    }

    MotorGuard.Motor m(String n) {
      return guard.motor(n);
    }
  }

  private static long count(Map<String, String> showing, String level) {
    return showing.values().stream().filter(v -> v.startsWith(level + ": ")).count();
  }

  @Test
  void theDashboardAtEachMoment() throws Exception {
    double[] quietCan = {0.42, 0, 0, 0, 0, 0};
    var grades = Map.of("3", "good", "4", "good", "7", "good", "2", "practice", "5", "retire");

    // Just switched on: nobody has picked the battery yet.
    Rig a = new Rig();
    a.add("frontleft drive", MotorKind.VORTEX, 80, false);
    a.run(0.2, quietCan);
    a.alerts.battery("");
    scenario("booted", BatteryPicker.checkText("", Double.NaN, null, "3"), a.alerts.showing);
    assertEquals(1, a.alerts.showing.size(), "only the battery question");

    // Ready to queue: battery 7, charged, nothing wrong.
    Rig b = new Rig();
    b.add("frontleft drive", MotorKind.VORTEX, 80, false);
    b.run(0.2, quietCan);
    b.alerts.battery("7");
    scenario("ready", BatteryPicker.checkText("7", 12.84, grades.get("7"), "3"), b.alerts.showing);
    assertTrue(b.alerts.showing.isEmpty(), "nothing to fix before queuing");

    // After a rough match.
    Rig c = new Rig();
    FakeMotorChannel fl = c.add("frontleft drive", MotorKind.VORTEX, 80, false);
    FakeMotorChannel shooter = c.add("Shooter leader", MotorKind.VORTEX, 80, false);
    FakeMotorChannel pivot = c.add("Intake pivot", MotorKind.VORTEX, 80, true);
    FakeMotorChannel spin = c.add("Spindexter", MotorKind.NEO_2_0, 80, false);
    spin.model = "SPARK Flex";
    spin.codeClass = "SPARK MAX";
    c.run(0.2, quietCan);
    for (int i = 0; i < 2; i++) { // frontleft drive drops off the bus twice
      fl.present = false;
      c.run(0.3, quietCan);
      fl.present = true;
      c.run(0.3, quietCan);
    }
    // The pivot ran hot, was halved, then cooled.
    pivot.ignoresLimit = true;
    pivot.demandA = 70;
    pivot.rpm = 3000;
    for (int i = 0; i < 4000 && c.m("Intake pivot").stage() != MotorGuard.Stage.DERATE; i++) c.run(0.02, quietCan);
    pivot.demandA = 0;
    for (int i = 0; i < 40000 && c.m("Intake pivot").stage() != MotorGuard.Stage.OK; i++) c.run(0.02, quietCan);
    // The shooter is cut off for heat right now.
    shooter.ignoresLimit = true;
    shooter.demandA = 90;
    shooter.rpm = 3000;
    for (int i = 0; i < 6000 && c.m("Shooter leader").stage() != MotorGuard.Stage.SHUTOFF; i++) c.run(0.02, quietCan);
    c.run(0.02, new double[] {0.55, 0, 0, 2, 0, 14});
    ModuleWatch w = new ModuleWatch(new String[] {"frontright"});
    double tt = 0;
    for (int ep = 0; ep < 3; ep++) {
      for (int i = 0; i < 40; i++) {
        w.update(tt += 0.02, true, new double[] {0}, new double[] {25}, new double[] {0}, new double[] {1}, new double[] {1});
      }
      for (int i = 0; i < 5; i++) {
        w.update(tt += 0.02, true, new double[] {25}, new double[] {25}, new double[] {25}, new double[] {1}, new double[] {1});
      }
    }
    c.alerts.modules(w.flags());
    c.alerts.battery("2");
    scenario("after_match", BatteryPicker.checkText("2", Double.NaN, grades.get("2"), "3"), c.alerts.showing);
    assertEquals(1, count(c.alerts.showing, "kError"), "the shooter cut off for heat");
    assertTrue(count(c.alerts.showing, "kWarning") >= 3, "CAN errors, the dropout, the wandering module");

    // The driver pressed Back: the heat override, with a stalled motor it can't save.
    Rig d = new Rig();
    FakeMotorChannel arm = d.add("Shooter leader", MotorKind.VORTEX, 80, false);
    FakeMotorChannel jam = d.add("Intake pivot", MotorKind.VORTEX, 80, true);
    arm.ignoresLimit = true;
    arm.demandA = 90;
    arm.rpm = 3000;
    jam.demandA = 100;
    for (int i = 0; i < 6000 && (d.m("Shooter leader").stage() != MotorGuard.Stage.SHUTOFF
        || d.m("Intake pivot").stage() != MotorGuard.Stage.SHUTOFF); i++) {
      d.run(0.02, quietCan);
    }
    d.guard.override("ALL", 20, d.t);
    d.run(6, quietCan);
    d.alerts.battery("3");
    scenario("override", BatteryPicker.checkText("3", 12.71, grades.get("3"), "7"), d.alerts.showing);
    assertTrue(d.alerts.showing.values().stream().anyMatch(v -> v.contains("Heat override ON")));

    // A battery below the charge line, everything else fine: the longest Battery check line.
    Rig e = new Rig();
    e.add("frontleft drive", MotorKind.VORTEX, 80, false);
    e.run(0.2, quietCan);
    e.alerts.battery("4");
    String low = BatteryPicker.checkText("4", 12.21, grades.get("4"), "3");
    scenario("charge_it", low, e.alerts.showing);
    assertTrue(low.contains("CHARGE IT"), low);

    String out = System.getenv("SWERVETUNE_PREVIEW_OUT");
    if (out != null && !out.isBlank()) {
      StringBuilder s = new StringBuilder("{");
      json.forEach((k, v) -> s.append(s.length() > 1 ? ",\n " : "\n ").append(q(k)).append(": ").append(v));
      Files.writeString(Path.of(out), s.append("\n}\n").toString());
    }
  }
}
