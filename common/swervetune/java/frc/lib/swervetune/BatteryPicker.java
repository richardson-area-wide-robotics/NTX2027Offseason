package frc.lib.swervetune;

import edu.wpi.first.networktables.DoublePublisher;
import edu.wpi.first.networktables.IntegerPublisher;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StringArrayPublisher;
import edu.wpi.first.networktables.StringPublisher;
import edu.wpi.first.networktables.StringSubscriber;
import java.util.ArrayList;
import java.util.List;

/**
 * Which battery is in, picked by the drive team.
 *
 * <p>Batteries are swapped with the robot off, so every boot may be a different battery: the pick
 * starts empty, a dashboard alert asks for it, and the drive team picks the number written on the
 * battery - from the "Battery" drop-down on the Driver Station dashboard (Elastic and Shuffleboard
 * show it as one), or the big buttons in the laptop's Live tab. From then on every test run and
 * the match log carry it, so the laptop can follow each battery's sag over the season and name the
 * tired one before it browns out a match.
 *
 * <p>It is published as the same topics WPILib's {@code SendableChooser} uses, so it needs no
 * SmartDashboard (gone in WPILib 2027). A dashboard that reconnects after the robot reboots may send
 * back the pick it had before - the battery from before the swap - so a pick that arrives within
 * {@link #RESTORE_WINDOW_S} of a dashboard connecting is cleared, and the drive team picks again.
 */
final class BatteryPicker {
  static final double RESTORE_WINDOW_S = 3.0;
  static final List<String> DEFAULT_ROSTER = numbers(12);

  private final List<String> roster;
  private final StringSubscriber selected;
  private final StringPublisher clearSelected;
  private final StringPublisher active;
  private final StringPublisher id;
  private final DoublePublisher restVolts;
  // Held so they stay published for the life of the robot program.
  private final StringPublisher type;
  private final IntegerPublisher instance;
  private final StringArrayPublisher options;
  private final StringPublisher defaultPick;

  private String current = "";
  private String lastSeen = "";
  private int dashboards = -1;
  private double ignoreUntilS = Double.NEGATIVE_INFINITY;

  BatteryPicker(NetworkTableInstance nt, List<String> roster) {
    this.roster = roster == null || roster.isEmpty() ? DEFAULT_ROSTER : List.copyOf(roster);
    String t = SwerveTuneTopics.BATTERY_CHOOSER;
    type = nt.getStringTopic(t + ".type").publish();
    type.set("String Chooser");
    instance = nt.getIntegerTopic(t + ".instance").publish();
    instance.set(0);
    options = nt.getStringArrayTopic(SwerveTuneTopics.BATTERY_OPTIONS).publish();
    options.set(this.roster.toArray(new String[0]));
    defaultPick = nt.getStringTopic(t + "default").publish();
    defaultPick.set("");
    active = nt.getStringTopic(SwerveTuneTopics.BATTERY_ACTIVE).publish();
    active.set("");
    selected = nt.getStringTopic(SwerveTuneTopics.BATTERY_SELECTED).subscribe("");
    clearSelected = nt.getStringTopic(SwerveTuneTopics.BATTERY_SELECTED).publish();
    id = nt.getStringTopic(SwerveTuneTopics.BATTERY_ID).publish();
    id.set("");
    restVolts = nt.getDoubleTopic(SwerveTuneTopics.BATTERY_REST_VOLTS).publish();
    restVolts.set(Double.NaN);
  }

  /**
   * Once per robot loop.
   *
   * @param dashboards how many NetworkTables clients are connected now
   * @param busVolts the battery voltage now, kept as its resting voltage if the robot is disabled
   * @return the battery picked since boot, or "" until someone picks
   */
  String update(double nowS, int dashboards, double busVolts, boolean disabled) {
    if (this.dashboards >= 0 && dashboards > this.dashboards) {
      ignoreUntilS = nowS + RESTORE_WINDOW_S;
    }
    this.dashboards = dashboards;
    String s = selected.get();
    s = s == null ? "" : s.trim();
    if (s.equals(lastSeen)) {
      return current;
    }
    lastSeen = s;
    if (s.isEmpty() || s.equals(current)) {
      return current;
    }
    if (nowS < ignoreUntilS) {
      // A dashboard putting back what it had before this boot: clear it so the next pick, even of
      // the same number, is a change the robot sees.
      clearSelected.set("");
      lastSeen = "";
      return current;
    }
    current = s;
    id.set(s);
    active.set(s);
    restVolts.set(disabled && Double.isFinite(busVolts) && busVolts > 1 ? busVolts : Double.NaN);
    return current;
  }

  String current() {
    return current;
  }

  List<String> roster() {
    return roster;
  }

  private static List<String> numbers(int n) {
    List<String> out = new ArrayList<>();
    for (int i = 1; i <= n; i++) {
      out.add(Integer.toString(i));
    }
    return List.copyOf(out);
  }
}
