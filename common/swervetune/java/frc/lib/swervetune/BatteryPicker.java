package frc.lib.swervetune;

import edu.wpi.first.networktables.DoublePublisher;
import edu.wpi.first.networktables.IntegerPublisher;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StringArrayPublisher;
import edu.wpi.first.networktables.StringPublisher;
import edu.wpi.first.networktables.StringSubscriber;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

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
 * SmartDashboard (gone in WPILib 2027). A dashboard that reconnects sends back the pick it had
 * before - including one already connected when the robot code starts. After a fresh power-on that
 * pick is the battery from before the swap, so until the first pick of this power-on, a pick arriving
 * within {@link #RESTORE_WINDOW_S} of a dashboard connecting is cleared and the drive team picks
 * again. (After that first pick a new connection, which every laptop command is, never blanks it.)
 * After a code restart (a redeploy, the roboRIO still powered) it is the same battery, and the
 * restored pick is kept.
 *
 * <p>The resting voltage is the bus voltage once the robot has been disabled for {@link
 * #REST_SETTLE_S}: at the pick when it already has been, otherwise as soon as it has, with no second
 * pick (a dashboard doesn't send a pick of the number it already shows).
 *
 * <p>Each battery's grade comes from the laptop, saved into {@code swervetune.json} and deployed;
 * the order batteries were picked in is kept on the roboRIO across power-ons. From those it names
 * the battery to put in next, as the laptop's Battery tab does: never the one in now, a borrowed or
 * a retired one; good before practice before not yet measured; then the one picked longest ago,
 * the likeliest to be charged and cool.
 */
final class BatteryPicker {
  static final double RESTORE_WINDOW_S = 3.0;
  /** Disabled this long, the battery has recovered from the last load enough to read at rest. */
  static final double REST_SETTLE_S = 2.0;
  /** Robot code starting this soon after the roboRIO powered up counts as a fresh power-on. */
  static final double FRESH_POWER_ON_S = 120.0;
  static final List<String> DEFAULT_ROSTER = numbers(12);
  static final String BORROWED = "Borrowed";
  /** Resting voltage of a charged ES17-12, and the line below which it needs charging (battery.py). */
  static final double CHARGED_V = 12.7;
  static final double CHARGE_IT_V = 12.3;

  private final List<String> roster;
  private final Map<String, String> grades;
  private final Path useLog;
  /** Battery id to the order it was last picked in (higher is more recent), across power-ons. */
  private final Map<String, Long> lastPicked = new LinkedHashMap<>();
  private final StringPublisher next;
  private final StringSubscriber selected;
  private final StringPublisher clearSelected;
  private final StringPublisher active;
  private final StringPublisher id;
  private final DoublePublisher restVolts;
  private final StringPublisher check;
  // Held so they stay published for the life of the robot program.
  private final StringPublisher type;
  private final IntegerPublisher instance;
  private final StringArrayPublisher options;
  private final StringPublisher defaultPick;

  private String current = "";
  private String lastSeen = "";
  private int dashboards = 0;
  private final boolean freshPowerOn;
  private double ignoreUntilS = Double.NEGATIVE_INFINITY;
  private double disabledSinceS = Double.NaN;
  private double rest = Double.NaN;

  BatteryPicker(NetworkTableInstance nt, List<String> roster) {
    this(nt, roster, true);
  }

  BatteryPicker(NetworkTableInstance nt, List<String> roster, boolean freshPowerOn) {
    this(nt, roster, freshPowerOn, Map.of(), null);
  }

  /**
   * @param freshPowerOn true when the roboRIO has just powered up (a battery may have been swapped);
   *     false when only the robot code restarted
   * @param grades battery id to "good", "practice" or "retire", from the laptop's measurements
   * @param useLog where the order of picks is kept across power-ons, or null to keep it in memory
   */
  BatteryPicker(NetworkTableInstance nt, List<String> roster, boolean freshPowerOn,
      Map<String, String> grades, Path useLog) {
    this.freshPowerOn = freshPowerOn;
    this.grades = grades == null ? Map.of() : Map.copyOf(grades);
    this.useLog = useLog;
    readUseLog();
    this.roster = roster == null || roster.isEmpty() ? DEFAULT_ROSTER : List.copyOf(roster);
    String t = SwerveTuneTopics.BATTERY_CHOOSER;
    type = nt.getStringTopic(t + ".type").publish();
    type.set("String Chooser");
    instance = nt.getIntegerTopic(t + ".instance").publish();
    instance.set(0);
    options = nt.getStringArrayTopic(SwerveTuneTopics.BATTERY_OPTIONS).publish();
    // "Borrowed" for a battery without a team number, so the drive team never has to guess one.
    List<String> choices = new ArrayList<>(this.roster);
    if (!choices.contains(BORROWED)) {
      choices.add(BORROWED);
    }
    options.set(choices.toArray(new String[0]));
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
    check = nt.getStringTopic(SwerveTuneTopics.BATTERY_CHECK).publish();
    next = nt.getStringTopic(SwerveTuneTopics.BATTERY_NEXT).publish();
    publishCheck();
  }

  /** The battery to put in next, or "" when every other one is in use, borrowed or retired. */
  String next() {
    String best = "";
    int bestRank = Integer.MAX_VALUE;
    long bestPicked = Long.MAX_VALUE;
    for (String id : roster) {
      String g = grades.get(id);
      if (id.equals(current) || id.equals(BORROWED) || "retire".equals(g)) {
        continue;
      }
      int rank = "good".equals(g) ? 0 : "practice".equals(g) ? 1 : 2;
      long picked = lastPicked.getOrDefault(id, -1L); // never picked here: as rested as any
      if (rank < bestRank || (rank == bestRank && picked < bestPicked)) {
        best = id;
        bestRank = rank;
        bestPicked = picked;
      }
    }
    return best;
  }

  /** What the grade adds to the check line. */
  static String gradeText(String grade) {
    return grade == null ? "" : switch (grade) {
      case "practice" -> " \u00b7 practice only";
      case "retire" -> " \u00b7 RETIRE it: it sagged hard";
      default -> "";
    };
  }

  /** The check line with the battery's grade and the one to use next. */
  static String checkText(String battery, double rest, String grade, String nextId) {
    String n = nextId == null || nextId.isEmpty() ? "" : nextId;
    if (battery.isEmpty()) {
      return checkText(battery, rest) + (n.isEmpty() ? "" : " (next to use: " + n + ")");
    }
    return checkText(battery, rest) + gradeText(grade) + (n.isEmpty() ? "" : " \u00b7 next: " + n);
  }

  private void publishCheck() {
    String n = next();
    next.set(n);
    check.set(checkText(current, rest, grades.get(current), n));
  }

  private void readUseLog() {
    if (useLog == null || !Files.exists(useLog)) {
      return;
    }
    try {
      for (String line : Files.readAllLines(useLog, StandardCharsets.UTF_8)) {
        int eq = line.lastIndexOf('=');
        if (eq > 0) {
          try {
            lastPicked.put(line.substring(0, eq).trim(), Long.parseLong(line.substring(eq + 1).trim()));
          } catch (NumberFormatException e) {
            // a damaged line is a battery with no record, nothing worse
          }
        }
      }
    } catch (IOException e) {
      // no record: every battery is as rested as any
    }
  }

  private void recordPick(String id) {
    long seq = lastPicked.values().stream().mapToLong(Long::longValue).max().orElse(0) + 1;
    lastPicked.remove(id);
    lastPicked.put(id, seq);
    if (useLog == null) {
      return;
    }
    StringBuilder sb = new StringBuilder("# Order batteries were picked in (swervetune). Safe to delete.\n");
    lastPicked.forEach((k, v) -> sb.append(k).append('=').append(v).append('\n'));
    try {
      Files.createDirectories(useLog.toAbsolutePath().getParent());
      Files.writeString(useLog, sb.toString(), StandardCharsets.UTF_8);
    } catch (IOException e) {
      // The next-battery choice falls back to this boot's picks; nothing else depends on it.
    }
  }

  /** The drive team's one line: which battery, its resting voltage, and what to do. */
  static String checkText(String battery, double rest) {
    if (battery.isEmpty()) {
      return "Pick the battery number";
    }
    if (!Double.isFinite(rest)) {
      return "Battery " + battery + ": resting voltage read once the robot is disabled";
    }
    return String.format("Battery %s: %.2f V at rest, %s", battery, rest,
        rest >= CHARGED_V ? "charged" : rest >= CHARGE_IT_V ? "partly charged" : "CHARGE IT before a match");
  }

  /**
   * Once per robot loop.
   *
   * @param dashboards how many NetworkTables clients are connected now
   * @param busVolts the battery voltage now, kept as its resting voltage if the robot is disabled
   * @return the battery picked since boot, or "" until someone picks
   */
  String update(double nowS, int dashboards, double busVolts, boolean disabled) {
    // A dashboard appearing (including one already there at the first loop) may put back its old pick.
    if (dashboards > this.dashboards && current.isEmpty()) {
      ignoreUntilS = nowS + RESTORE_WINDOW_S;
    }
    this.dashboards = dashboards;
    if (!disabled) {
      disabledSinceS = Double.NaN;
    } else if (Double.isNaN(disabledSinceS)) {
      disabledSinceS = nowS;
    }
    boolean atRest = disabled && nowS - disabledSinceS >= REST_SETTLE_S && Double.isFinite(busVolts) && busVolts > 1;
    if (!current.isEmpty() && Double.isNaN(rest) && atRest) {
      // Picked while enabled (or just after): read it now that it has rested.
      rest = busVolts;
      restVolts.set(rest);
      publishCheck();
    }
    String s = selected.get();
    s = s == null ? "" : s.trim();
    if (s.equals(lastSeen)) {
      return current;
    }
    lastSeen = s;
    if (s.isEmpty() || s.equals(current)) {
      return current;
    }
    if (nowS < ignoreUntilS && freshPowerOn) {
      // A dashboard putting back what it had before this power-on: clear it so the next pick, even
      // of the same number, is a change the robot sees.
      clearSelected.set("");
      lastSeen = "";
      return current;
    }
    current = s;
    id.set(s);
    active.set(s);
    recordPick(s);
    rest = atRest ? busVolts : Double.NaN;
    restVolts.set(rest);
    publishCheck();
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
