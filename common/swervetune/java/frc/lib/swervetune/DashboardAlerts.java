package frc.lib.swervetune;

import edu.wpi.first.wpilibj.Alert;
import edu.wpi.first.wpilibj.Alert.AlertType;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Robot health on the Driver Station dashboard: WPILib Alerts in the group "Robot Health", which
 * Elastic and Shuffleboard both show as a list with red (error) and yellow (warning) marks. Glanceable
 * mid-match; the laptop's Wiring tab says where to look.
 *
 * <p>Alerts stay up until the robot code restarts, with counts, so the drive team sees after a match
 * what happened during it - a motor that dropped off the CAN bus for half a second in teleop is gone
 * from the live view by the time anyone looks.
 */
final class DashboardAlerts {
  static final String GROUP = "Robot Health";
  private final Map<String, Alert> alerts = new HashMap<>();

  private void set(String key, AlertType type, boolean on, String text) {
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

  /**
   * @param can {@code {utilization 0-1, busOffCount, txFullCount, receiveErrors, transmitErrors}},
   *     or empty if unknown
   */
  void update(List<MotorGuard.Motor> motors, double[] can) {
    for (MotorGuard.Motor m : motors) {
      String who = m.name + (m.canId() >= 0 ? " (CAN " + m.canId() + ")" : "");
      set(m.name + "/gone", AlertType.kError, !m.present(), who + " is not on the CAN bus");
      set(m.name + "/drops", AlertType.kWarning, m.present() && m.dropouts() > 0,
          who + " dropped off the CAN bus " + times(m.dropouts()));
      set(m.name + "/resets", AlertType.kWarning, m.resets() > 0,
          who + " lost power and rebooted " + times(m.resets()));
      set(m.name + "/brownouts", AlertType.kWarning, m.brownouts() > 0,
          who + " saw low supply voltage " + times(m.brownouts()));
      MotorGuard.Stage s = m.stage();
      set(m.name + "/heat", s == MotorGuard.Stage.SHUTOFF ? AlertType.kError : AlertType.kWarning,
          s != MotorGuard.Stage.OK, who + " " + s + ": " + m.cause());
      set(m.name + "/flags", AlertType.kError, !m.flags().isEmpty() && m.present(), who + ": " + m.flags());
    }
    if (can.length >= 5) {
      set("can/busoff", AlertType.kError, can[1] > 0,
          "CAN bus shut down " + times((int) can[1]) + ": check termination and every CAN connector");
      set("can/errors", AlertType.kWarning, can[3] > 0 || can[4] > 0,
          String.format("CAN bus errors now: %d receive, %d transmit", (int) can[3], (int) can[4]));
      set("can/busy", AlertType.kWarning, can[0] > 0.8,
          String.format("CAN bus %.0f%% busy: too many status frames", 100 * can[0]));
    }
  }

  private static String times(int n) {
    return n == 1 ? "once" : n + " times";
  }
}
