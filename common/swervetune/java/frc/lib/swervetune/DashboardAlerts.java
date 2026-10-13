package frc.lib.swervetune;

import edu.wpi.first.wpilibj.Alert;
import edu.wpi.first.wpilibj.Alert.AlertType;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * Robot health on the Driver Station dashboard: WPILib Alerts in the group "Robot Health", which
 * Elastic and Shuffleboard both show as a list with red (error), yellow (warning) and info marks.
 * Glanceable mid-match; the laptop's Wiring tab says where to look.
 *
 * <p>The rule the drive team can trust: <b>red means broken now</b> - fix it before queuing.
 * Yellow is something that happened (a dropout, a reboot, a motor that overheated and has cooled)
 * or something to watch; it stays up with its count until the robot code restarts, so the team
 * sees after a match what happened during it. Info is for a programmer. Every line ends with what
 * to do.
 *
 * <p>An alert's color can't change once it is shown, so each severity has its own alert. And a
 * battery dip or a CAN glitch hits most motors at once: that becomes one line naming the shared
 * cause instead of one line per motor with the cause at the bottom.
 */
final class DashboardAlerts {
  static final String GROUP = "Robot Health";
  private final Map<String, Alert> alerts = new HashMap<>();
  private final boolean live;
  /** What is showing now, key to "kError: text", for tests and the log. */
  final Map<String, String> showing = new TreeMap<>();
  /** Where each motor is wired, so a line can say where to look. */
  private WiringMap wiring = WiringMap.NONE;

  DashboardAlerts() {
    this(true);
  }

  /** @param live false in tests: record what would show without creating WPILib Alerts */
  DashboardAlerts(boolean live) {
    this.live = live;
  }

  private void set(String key, AlertType type, boolean on, String text) {
    if (on) {
      showing.put(key, type.name() + ": " + text);
    } else {
      showing.remove(key);
    }
    if (!live) {
      return;
    }
    Alert a = alerts.get(key);
    if (a == null) {
      if (!on) {
        return;
      }
      a = new Alert(GROUP, text, type);
      alerts.put(key, a);
    }
    a.setText(text);
    a.set(on);
  }

  void setWiring(WiringMap wiring) {
    this.wiring = wiring == null ? WiringMap.NONE : wiring;
  }

  /** Asks which battery is in until someone picks one (each boot may be a new battery). */
  void battery(String id) {
    set("battery", AlertType.kWarning, id == null || id.isEmpty(),
        "Which battery is in? Pick its number under Battery.");
  }

  /**
   * @param can {@code {utilization 0-1, busOffCount, txFullCount, receiveErrors, transmitErrors,
   *     loopsWithErrors}}, or empty if unknown
   * @param overrideS seconds left on the driver's thermal override, 0 when off
   */
  void update(List<MotorGuard.Motor> motors, double[] can, double overrideS) {
    int n = motors.size();
    long browned = motors.stream().filter(m -> m.brownouts() > 0).count();
    long dropped = motors.stream().filter(m -> m.present() && m.dropouts() > 0).count();
    boolean brownFlood = n >= 4 && browned * 2 > n;
    boolean dropFlood = n >= 4 && dropped * 2 > n;
    set("flood/brownouts", AlertType.kWarning, brownFlood, browned + " motors saw low voltage at the same"
        + " time: the battery or its leads, not the motors. Check the battery and the main breaker.");
    set("flood/drops", AlertType.kWarning, dropFlood, dropped + " motors dropped off the CAN bus: the"
        + " CAN chain itself. Check the termination and the plugs nearest the roboRIO.");
    for (MotorGuard.Motor m : motors) {
      String who = m.name + (m.canId() >= 0 ? " (CAN " + m.canId() + ")" : "");
      String power = wiring.power(m.name);
      String cable = wiring.can(m.name);
      set(m.name + "/gone", AlertType.kError, !m.present(),
          who + " is off the CAN bus now: check its power" + power + " and CAN plugs" + cable);
      set(m.name + "/drops", AlertType.kWarning, m.present() && m.dropouts() > 0 && !dropFlood,
          who + " dropped off the CAN bus " + times(m.dropouts()) + ": wiggle-test its CAN plugs" + cable);
      set(m.name + "/resets", AlertType.kWarning, m.resets() > 0,
          who + " lost power and rebooted " + times(m.resets()) + ": check its power leads and breaker" + power);
      set(m.name + "/brownouts", AlertType.kWarning, m.brownouts() > 0 && !brownFlood,
          who + " got low voltage " + times(m.brownouts()) + ": check its power leads" + power);
      MotorGuard.Stage s = m.stage();
      set(m.name + "/shutoff", AlertType.kError, s == MotorGuard.Stage.SHUTOFF,
          who + " is cut to " + MotorGuard.SHUTOFF_LIMIT_A + " A until it cools (" + m.cause() + ")");
      set(m.name + "/hot", AlertType.kWarning, s == MotorGuard.Stage.DERATE || s == MotorGuard.Stage.WARN,
          s == MotorGuard.Stage.DERATE ? who + " is at half power to cool (" + m.cause() + "): ease off"
              : who + " is getting hot (" + m.cause() + "): ease off");
      boolean cooledOff = s == MotorGuard.Stage.OK && (m.shutoffs() > 0 || m.derates() > 0);
      set(m.name + "/overheated", AlertType.kWarning, cooledOff, who + " overheated this session ("
          + (m.shutoffs() > 0 ? "cut off " + times(m.shutoffs()) : "")
          + (m.shutoffs() > 0 && m.derates() > 0 ? ", " : "")
          + (m.derates() > 0 ? "half power " + times(m.derates()) : "")
          + "): give it less load or more cooling");
      set(m.name + "/flags", AlertType.kError, !m.flags().isEmpty() && m.present(), who + ": " + m.flags());
      set(m.name + "/history", AlertType.kWarning, !m.history().isEmpty() && m.present(),
          who + ": " + m.history() + ", clear now: watch it");
    }
    set("override", AlertType.kWarning, overrideS > 0, String.format("Heat override ON, %.0f s left:"
        + " shut-off motors run at half power; stalls still cut out. Back again restarts the 20 s.", overrideS));
    if (can.length >= 5) {
      set("can/busoff", AlertType.kError, can[1] > 0,
          "CAN bus shut down " + times((int) can[1]) + ": check termination and every CAN connector");
      // The error counters recover in milliseconds; the running count of loops that saw any keeps
      // the alert steady instead of blinking.
      int seen = can.length >= 6 ? (int) can[5] : (can[3] > 0 || can[4] > 0 ? 1 : 0);
      set("can/errors", AlertType.kWarning, seen > 0,
          "CAN bus errors in " + seen + " loop" + (seen == 1 ? "" : "s") + ": wiggle-test the CAN chain");
      set("can/busy", AlertType.kInfo, can[0] > 0.8, String.format("CAN bus %.0f%% busy (too many status"
          + " frames): tell a programmer", 100 * can[0]));
    }
  }

  private static String times(int n) {
    return n == 1 ? "once" : n + " times";
  }
}
