package frc.lib.slothtune;

import edu.wpi.first.math.util.Units;
import edu.wpi.first.networktables.DoubleArrayPublisher;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StringArrayPublisher;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * The laptop monitor's checks (tools/slothtune/monitor.py), run on the robot every loop so they
 * watch matches too, when no laptop is connected. Each keeps a count for the session, shown on
 * Robot Health, logged with AdvantageKit for the post-match summary, and published for the laptop,
 * which shows these flags instead of judging the same rules again, so none is reported twice.
 * Thresholds, hold times and words are the laptop's: a check must hold for its time before it
 * fires, and clears once its condition has been gone for a second.
 *
 * <p>Thirteen of the laptop's fifteen rules run here. The two that stay on the laptop, motor_hot
 * and motor_failing, only put words to the motor guard's stage and flags, which MotorGuard already
 * judges here every loop, logs, and shows on Robot Health; repeating them would show each twice.
 * The laptop also keeps every rule for robot code from before this, which publishes no flags.
 *
 * <p>Robot Health shows the checks a drive team acts on ({@link Show}). "A wheel well short of its
 * speed" and "a drive motor at high current, barely turning" are logged and sent to the laptop
 * but never shown there: both fire all match long while the robot pushes or is pushed.
 *
 * <p>Cheap enough for the 20 ms loop: {@link #update} allocates nothing (ModuleWatchTest measures
 * it) and does a fixed amount of work per module and motor. A flag's words are built only when
 * something shows them.
 */
final class ModuleWatch {
  /** Where a check looks: once per module, once for the whole robot, or once per swerve motor. */
  enum Scope {
    MODULE,
    ROBOT,
    MOTOR
  }

  /** When Robot Health shows a check that has happened. */
  enum Show {
    ALWAYS,
    /** Only while the motor guard watches no motor: otherwise its own lines already say it. */
    UNGUARDED,
    /** Never: it fires whenever the robot pushes or is pushed. Logged and on the laptop. */
    NEVER
  }

  /**
   * One check: its log name, the laptop's name for it, where it looks, how long the condition must
   * last, whether a tuning test confounds it (a test moves the modules on purpose), when Robot
   * Health shows it, what it means, and where to look. Module checks come first.
   */
  enum Rule {
    STEER_OFF("SteerOff", "steer_not_reaching", Scope.MODULE, 0.5, true, Show.ALWAYS,
        "steering more than 10\u00b0 from where it is told to point",
        "A loose or slipping module, a wrong offset, or steering gains too soft: Troubleshoot, "
            + "\"A wheel points the wrong way\"."),
    STEER_SWINGS("SteerOscillation", "steer_oscillation", Scope.MODULE, 0.3, true, Show.ALWAYS,
        "swinging back and forth around its angle",
        "Steering gains too high, or a loose module or encoder: Troubleshoot, \"A module shakes, "
            + "buzzes or oscillates\"."),
    SENSORS_DISAGREE("SensorsDisagree", "motor_vs_absolute", Scope.MODULE, 1.0, true, Show.ALWAYS,
        "steering motor encoder and absolute encoder more than 3\u00b0 apart",
        "A slipped pinion or a loose absolute encoder: the module points somewhere it doesn't think "
            + "it does. Troubleshoot, \"Lines up at boot, gets worse during a match\"."),
    ABSOLUTE_READ("AbsoluteReadIssue", "absolute_read_issue", Scope.MODULE, 0.2, false, Show.ALWAYS,
        "absolute encoder is not being read reliably",
        "A loose encoder cable, or its power or CAN: the module steers by its motor alone. "
            + "Troubleshoot, \"A module shakes, buzzes or oscillates\"."),
    BACKWARDS("Backwards", "drive_backwards", Scope.MODULE, 0.3, true, Show.ALWAYS,
        "wheel turning against its command",
        "An inverted drive motor or a module 180\u00b0 out: it fights the other three. Troubleshoot, "
            + "\"One wheel drives backwards or fights the others\"."),
    LAGGING("DriveLagging", "drive_lagging", Scope.MODULE, 1.0, true, Show.NEVER,
        "wheel is well short of its commanded speed",
        "Pushing or being pushed does this; one module alone points at friction or a weak motor: "
            + "Troubleshoot, \"The robot is slow\"."),
    STALL("Stall", "stall", Scope.MODULE, 0.4, true, Show.NEVER,
        "drive motor is at high current with the wheel barely turning",
        "Pushing a wall or a robot does this; otherwise the wheel is jammed or slipping: "
            + "Troubleshoot, \"Wheels spin when accelerating\"."),
    HOT("Hot", "hot", Scope.MODULE, 2.0, false, Show.UNGUARDED,
        "motor is over 70 \u00b0C",
        "Ease off and let it cool: with the motor guard off, nothing else protects it. "
            + "Troubleshoot, \"Stutters or browns out\"."),
    FAULTS("Faults", "faults", Scope.MODULE, 0.0, false, Show.UNGUARDED,
        "motor controller reports a fault",
        "Check its CAN and power plugs; the laptop's Wiring tab names the fault. Troubleshoot, "
            + "\"A module won't steer at all\"."),
    RATIO("DriveRatioMismatch", "drive_ratio_mismatch", Scope.MODULE, 0.0, true, Show.ALWAYS,
        "reports a different distance from the other modules while driving straight: more than "
            + "worn tread explains, so its gear ratio may differ",
        "Check that module's pinion, gears and wheel: Troubleshoot, \"A module seems geared "
            + "differently\"."),
    LOW_BATTERY("LowBattery", "low_battery", Scope.ROBOT, 0.25, false, Show.ALWAYS,
        "battery voltage is sagging below 8 V",
        "Swap in a charged battery, then check the battery leads and the main breaker: "
            + "Troubleshoot, \"Stutters or browns out\"."),
    GYRO("GyroProblem", "gyro_problem", Scope.ROBOT, 0.5, false, Show.ALWAYS,
        "gyro is not connected, still calibrating, or faulted",
        "Field-relative driving is wrong until it is back: check the gyro's cable, and keep the robot "
            + "still while it calibrates. Troubleshoot, \"Field-relative driving is off\"."),
    SIBLINGS("HotterThanSiblings", "motor_hotter_than_siblings", Scope.MOTOR, 5.0, false, Show.ALWAYS,
        "runs much hotter than the matching motors on the other modules: binding, a dragging "
            + "bearing or a failing motor",
        "Turn that module by hand: it should spin freely. Troubleshoot, \"A motor gets hot, goes "
            + "weak or cuts out\".");

    final String key;
    final String laptop;
    final Scope scope;
    final double holdS;
    final boolean motion;
    final Show show;
    final String what;
    final String look;

    Rule(String key, String laptop, Scope scope, double holdS, boolean motion, Show show, String what,
        String look) {
      this.key = key;
      this.laptop = laptop;
      this.scope = scope;
      this.holdS = holdS;
      this.motion = motion;
      this.show = show;
      this.what = what;
      this.look = look;
    }

    /** Whether Robot Health shows it, given whether the motor guard watches any motor. */
    boolean shows(boolean guarded) {
      return show == Show.ALWAYS || show == Show.UNGUARDED && !guarded;
    }
  }

  static final Rule[] RULES = Rule.values();
  /** How long a condition must be gone before its flag clears, seconds: the laptop's. */
  static final double CLEAR_S = 1.0;
  static final double SWING_WINDOW_S = 1.0;
  static final int SWINGS = 4;
  static final double HOT_C = 70;
  static final double LOW_BATTERY_V = 8.0;
  /** One swerve motor this much hotter than the median of its siblings, C, is not the duty cycle. */
  static final double SIBLING_HOT_C = 15.0;
  /** Straight-line driving each module must report before the ratio check judges, meters. */
  static final double RATIO_MIN_TRAVEL_M = 3.0;
  /** Worn tread is up to about 4%, one pinion tooth about 8%: between them, a wheel to measure. */
  static final double RATIO_FLAG = 0.05;
  /** Numbers per check for the laptop: active, episodes, since (robot s), and two readings. */
  static final int STRIDE = 5;
  /** Sign changes kept per module: far more than a second's worth at 50 Hz can ever need. */
  private static final int SWING_CAPACITY = 64;
  private static final String[] SUFFIXES = {" drive", " steer"};

  /**
   * One loop's readings, filled in place by the caller; the arrays are read, never kept. Angles in
   * degrees, speeds in meters per second, distances in meters, one entry per module. A missing
   * array or value reads as unknown, and a check that needs it stays quiet.
   */
  static final class Inputs {
    boolean enabled;
    /** A tuning test is running: it moves the modules on purpose, so the motion checks rest. */
    boolean testing;
    /** On a field (the laptop says so, or the FMS is attached): the ratio check needs one. */
    boolean onField;
    double driveLimitA = 40;
    double[] steer;
    double[] steerSp;
    double[] steerMotor;
    double[] v;
    double[] vSp;
    double[] pos;
    double[] driveAmps;
    double[] driveTemp;
    double[] steerTemp;
    /** 1 where the last absolute encoder read failed. */
    double[] absIssue;
    String[] faults;
    double headingDeg = Double.NaN;
    double busVolts = Double.NaN;
    /** What the gyro is; null when its state is unknown. */
    String gyroType;
    boolean gyroConnected = true;
    boolean gyroCalibrating;
    String gyroFaults = "";
  }

  /** One check on one module, motor, or the whole robot. */
  static final class Flag {
    /** The module or motor; empty for the whole robot. */
    final String module;
    final Rule rule;
    /** Under RealOutputs, e.g. {@code SlothTune/Watch/frontleft/SteerOff}. */
    final String logKey;
    boolean active;
    /** Episodes this session: counted once each, so a long one is one, not one per loop. */
    int count;
    /** When the current (or last) episode's condition began, robot seconds. */
    double sinceS = Double.NaN;
    /** The readings its detail is made from, as last seen while the condition held. */
    double a = Double.NaN;
    double b = Double.NaN;
    String text = "";
    String text2 = "";
    /** The count AdvantageKit last logged; -1 before the first. */
    int loggedCount = -1;
    private double startS = Double.NaN;
    private double stopS = Double.NaN;
    private boolean counted;

    Flag(String module, Rule rule) {
      this.module = module;
      this.rule = rule;
      logKey = "SlothTune/Watch/" + (module.isEmpty() ? "Robot" : module) + "/" + rule.key;
    }

    /** Who it is about, as a line starts. */
    String label() {
      return module.isEmpty() ? "The robot" : module;
    }

    /** The readings in words, as the laptop puts them. Builds a string: not for every loop. */
    String detail() {
      switch (rule) {
        case STEER_OFF:
          return String.format(Locale.ROOT, "%+.1f\u00b0", a);
        case STEER_SWINGS:
          return String.format(Locale.ROOT, "%.0f swings/s", a);
        case SENSORS_DISAGREE:
          return String.format(Locale.ROOT, "%.1f\u00b0", a);
        case BACKWARDS:
          return String.format(Locale.ROOT, "%+.2f vs %+.2f ft/s", Units.metersToFeet(a),
              Units.metersToFeet(b));
        case LAGGING:
          return String.format(Locale.ROOT, "%.2f of %.2f ft/s", Units.metersToFeet(a),
              Units.metersToFeet(b));
        case STALL:
          return String.format(Locale.ROOT, "%.0f A", a);
        case HOT:
          return String.format(Locale.ROOT, "%.0f \u00b0C", a);
        case FAULTS:
          return text;
        case RATIO:
          return String.format(Locale.ROOT, "%+.1f%% over %.0f in", (a - 1) * 100,
              Units.metersToInches(b));
        case LOW_BATTERY:
          return Double.isFinite(a) ? String.format(Locale.ROOT, "%.1f V", a) : "";
        case GYRO:
          StringBuilder s = new StringBuilder(text);
          s.append(s.length() > 0 ? ", " : "").append(a == 1 ? "connected" : "NOT CONNECTED");
          s.append(b == 1 ? ", calibrating" : ", ready").append(text2.isEmpty() ? "" : ", " + text2);
          return s.toString();
        case SIBLINGS:
          return String.format(Locale.ROOT, "%.0f \u00b0C vs %.0f \u00b0C", a, b);
        default:
          return "";
      }
    }
  }

  private final List<Flag> flags = new ArrayList<>();
  private final String[] names;
  private final int moduleRules;
  private final Inputs legacy = new Inputs();
  /** Bumped whenever a flag starts, stops or counts, or the motors change: Robot Health redraws then. */
  private int changes;
  /** Bumped whenever the list of flags changes, so the laptop is sent their names again. */
  private int layout;

  // steer_oscillation: per module, a queue of the times of the sample before each sign change.
  private final double[][] swingT;
  private final int[] swingHead;
  private final int[] swingSize;
  private final int[] lastSign;
  private final double[] lastSignT;

  // drive_ratio_mismatch: meters each module reported while the chassis drove straight.
  private final double[] travel;
  private final double[] ratioPos;
  private final double[] scratch;
  private double ratioHeading;
  private boolean ratioLast;

  // motor_hotter_than_siblings: the motor guard's motors, those a check watches, and their group.
  private MotorGuard.Motor[] motors = new MotorGuard.Motor[0];
  private Flag[] motorFlags = new Flag[0];
  private int[] motorGroup = new int[0];
  private double[] temps = new double[0];
  private double[] sorted = new double[0];

  ModuleWatch(String[] moduleNames) {
    names = moduleNames.clone();
    int perModule = 0;
    for (Rule r : RULES) {
      perModule += r.scope == Scope.MODULE ? 1 : 0;
    }
    moduleRules = perModule;
    for (String n : names) {
      for (int i = 0; i < moduleRules; i++) {
        flags.add(new Flag(n, RULES[i]));
      }
    }
    for (Rule r : RULES) {
      if (r.scope == Scope.ROBOT) {
        flags.add(new Flag("", r));
      }
    }
    int n = names.length;
    swingT = new double[n][SWING_CAPACITY];
    swingHead = new int[n];
    swingSize = new int[n];
    lastSign = new int[n];
    lastSignT = new double[n];
    travel = new double[n];
    ratioPos = new double[n];
    scratch = new double[n];
  }

  Flag flag(int module, Rule rule) {
    return flags.get(module * moduleRules + rule.ordinal());
  }

  /** The whole robot's flag for a robot-wide check. */
  Flag robot(Rule rule) {
    return flags.get(names.length * moduleRules + rule.ordinal() - moduleRules);
  }

  int moduleCount() {
    return names.length;
  }

  /** How many motors the motor guard watched when they were last bound. */
  int motorCount() {
    return motors.length;
  }

  /** Whether the motor guard watches any motor: its own checks then cover heat and faults. */
  boolean guarded() {
    return motors.length > 0;
  }

  int changes() {
    return changes;
  }

  int layout() {
    return layout;
  }

  /**
   * The motor guard's motors, whenever that list changes (a mechanism registers its motors after
   * the drivetrain). The swerve motors, named "... drive" and "... steer", are compared with their
   * siblings; a motor already watched keeps its count.
   */
  void bindMotors(List<MotorGuard.Motor> list) {
    Map<String, Flag> old = new HashMap<>();
    for (Flag f : motorFlags) {
      if (f != null) {
        old.put(f.module, f);
      }
    }
    flags.removeIf(f -> f.rule.scope == Scope.MOTOR);
    int n = list.size();
    motors = list.toArray(new MotorGuard.Motor[0]);
    motorFlags = new Flag[n];
    motorGroup = new int[n];
    temps = new double[n];
    sorted = new double[n];
    for (int i = 0; i < n; i++) {
      String name = motors[i].name;
      motorGroup[i] = -1;
      for (int g = 0; g < SUFFIXES.length; g++) {
        if (name.endsWith(SUFFIXES[g])) {
          motorGroup[i] = g;
        }
      }
      if (motorGroup[i] >= 0) {
        Flag f = old.get(name);
        motorFlags[i] = f != null ? f : new Flag(name, Rule.SIBLINGS);
        flags.add(motorFlags[i]);
      }
    }
    changes++;
    layout++;
  }

  /** Angle a minus b, wrapped into -180..180. */
  static double wrap180(double deg) {
    double w = ((deg + 180) % 360 + 360) % 360 - 180;
    return w == -180 ? 180 : w;
  }

  private static double at(double[] a, int i) {
    return a != null && i < a.length ? a[i] : Double.NaN;
  }

  /** The original three module checks' readings alone; the other checks see nothing and stay quiet. */
  void update(double nowS, boolean enabled, double[] steer, double[] steerSp, double[] steerMotor,
      double[] v, double[] vSp) {
    legacy.enabled = enabled;
    legacy.steer = steer;
    legacy.steerSp = steerSp;
    legacy.steerMotor = steerMotor;
    legacy.v = v;
    legacy.vSp = vSp;
    update(nowS, legacy);
  }

  /** One loop. Allocates nothing. */
  void update(double nowS, Inputs in) {
    boolean on = in.enabled;
    boolean judge = !in.testing;
    double limit = Double.isFinite(in.driveLimitA) && in.driveLimitA > 0 ? in.driveLimitA : 40;
    for (int m = 0; m < names.length; m++) {
      double steer = at(in.steer, m);
      double sp = at(in.steerSp, m);
      double v = at(in.v, m);
      double vSp = at(in.vSp, m);
      boolean commanded = Double.isFinite(vSp) && Math.abs(vSp) > 0.1;
      double err = Double.isFinite(sp) && Double.isFinite(steer) ? wrap180(sp - steer) : Double.NaN;
      raise(flag(m, Rule.STEER_OFF), nowS, judge && on && commanded && Math.abs(err) > 10, err, 0);

      int swings = swings(m, nowS, judge && on ? err : Double.NaN, judge);
      raise(flag(m, Rule.STEER_SWINGS), nowS, judge && on && swings >= SWINGS, swings, 0);

      double motor = at(in.steerMotor, m);
      double gap = Double.isFinite(motor) && Double.isFinite(steer) ? Math.abs(wrap180(steer - motor)) : 0;
      boolean still = !Double.isFinite(v) || Math.abs(v) < 0.05;
      raise(flag(m, Rule.SENSORS_DISAGREE), nowS, judge && still && gap > 3, gap, 0);

      raise(flag(m, Rule.ABSOLUTE_READ), nowS, at(in.absIssue, m) == 1, 0, 0);

      boolean backwards = on && commanded && Double.isFinite(v) && v * vSp < 0 && Math.abs(v) > 0.1;
      raise(flag(m, Rule.BACKWARDS), nowS, judge && backwards, v, vSp);

      boolean lag = on && Double.isFinite(v) && Double.isFinite(vSp) && Math.abs(vSp) > 0.5
          && !backwards && Math.abs(v - vSp) / Math.abs(vSp) > 0.3;
      raise(flag(m, Rule.LAGGING), nowS, judge && lag, v, vSp);

      double amps = at(in.driveAmps, m);
      raise(flag(m, Rule.STALL), nowS, judge && on && amps > 0.85 * limit && Double.isFinite(v)
          && Math.abs(v) < 0.15, amps, 0);

      // With the motor guard watching, its kind-aware heat rules replace this one.
      double hottest = hottest(at(in.driveTemp, m), at(in.steerTemp, m));
      raise(flag(m, Rule.HOT), nowS, !guarded() && hottest > HOT_C, hottest, 0);

      String faults = in.faults != null && m < in.faults.length && in.faults[m] != null ? in.faults[m] : "";
      Flag ff = flag(m, Rule.FAULTS);
      raise(ff, nowS, !faults.isEmpty(), true, 0, 0);
      if (!faults.isEmpty()) {
        ff.text = faults;
      }
    }
    ratio(nowS, in);

    raise(robot(Rule.LOW_BATTERY), nowS, on && in.busVolts < LOW_BATTERY_V, in.busVolts, 0);
    Flag g = robot(Rule.GYRO);
    String gyroFaults = in.gyroFaults == null ? "" : in.gyroFaults;
    boolean badGyro = in.gyroType != null && (!in.gyroConnected || in.gyroCalibrating || !gyroFaults.isEmpty());
    // Every power-on calibrates, robot disabled: that alone isn't an episode worth counting.
    boolean countGyro = !in.gyroConnected || !gyroFaults.isEmpty() || on;
    raise(g, nowS, badGyro, countGyro, in.gyroConnected ? 1 : 0, in.gyroCalibrating ? 1 : 0);
    if (badGyro) {
      g.text = in.gyroType;
      g.text2 = gyroFaults;
    }
    siblings(nowS);
  }

  private void raise(Flag f, double nowS, boolean condition, double a, double b) {
    raise(f, nowS, condition, true, a, b);
  }

  /** The laptop's rule: hold for the rule's time to fire, gone for a second to clear. */
  private void raise(Flag f, double nowS, boolean condition, boolean countable, double a, double b) {
    if (condition) {
      f.a = a;
      f.b = b;
      f.stopS = Double.NaN;
      if (Double.isNaN(f.startS)) {
        f.startS = nowS;
      }
      if (!f.active && nowS - f.startS >= f.rule.holdS) {
        f.active = true;
        f.sinceS = f.startS;
        f.counted = false;
        changes++;
      }
      if (f.active && countable && !f.counted) {
        f.counted = true;
        f.count++;
        changes++;
      }
      return;
    }
    f.startS = Double.NaN;
    if (f.active) {
      if (Double.isNaN(f.stopS)) {
        f.stopS = nowS;
      }
      if (nowS - f.stopS >= CLEAR_S) {
        f.active = false;
        f.stopS = Double.NaN;
        changes++;
      }
    }
  }

  /**
   * Adds one steering error sample (NaN for none) and returns how many times the error changed
   * sign in the last second, ignoring errors under 1 degree: the laptop's count, kept as a queue of
   * the sample before each change so a sample's age decides when it drops out.
   */
  private int swings(int m, double nowS, double err, boolean judge) {
    if (!judge) {
      lastSign[m] = 0;
    } else if (Double.isFinite(err) && Math.abs(err) >= 1.0) {
      int s = err > 0 ? 1 : -1;
      if (lastSign[m] != 0 && s != lastSign[m] && nowS - lastSignT[m] <= SWING_WINDOW_S) {
        if (swingSize[m] == SWING_CAPACITY) {
          swingHead[m] = (swingHead[m] + 1) % SWING_CAPACITY;
          swingSize[m]--;
        }
        swingT[m][(swingHead[m] + swingSize[m]) % SWING_CAPACITY] = lastSignT[m];
        swingSize[m]++;
      }
      lastSign[m] = s;
      lastSignT[m] = nowS;
    }
    while (swingSize[m] > 0 && nowS - swingT[m][swingHead[m]] > SWING_WINDOW_S) {
      swingHead[m] = (swingHead[m] + 1) % SWING_CAPACITY;
      swingSize[m]--;
    }
    return swingSize[m];
  }

  private static double hottest(double drive, double steer) {
    double h = 0;
    if (Double.isFinite(drive)) {
      h = Math.max(h, drive);
    }
    if (Double.isFinite(steer)) {
      h = Math.max(h, steer);
    }
    return h;
  }

  /**
   * The passive drive-ratio check: on a field, only, where the chassis makes every wheel cover the
   * same ground. Adds up what each module reports while all point the same way, all turn, and the
   * heading holds; once each has 3 m, a module more than 5% off the median is flagged.
   */
  private void ratio(double nowS, Inputs in) {
    int n = names.length;
    boolean straight = in.enabled && in.onField && !in.testing && n >= 3 && Double.isFinite(in.headingDeg);
    double first = at(in.steer, 0);
    for (int m = 0; straight && m < n; m++) {
      double p = at(in.pos, m);
      double s = at(in.steer, m);
      double v = at(in.v, m);
      straight = Double.isFinite(p) && Double.isFinite(s) && Double.isFinite(v)
          && Math.abs(wrap180(s - first)) < 3.0 && Math.abs(v) > 0.3;
    }
    if (straight && ratioLast && Math.abs(wrap180(in.headingDeg - ratioHeading)) < 0.5) {
      for (int m = 0; m < n; m++) {
        travel[m] += Math.abs(in.pos[m] - ratioPos[m]);
      }
    }
    if (straight) {
      System.arraycopy(in.pos, 0, ratioPos, 0, n);
      ratioHeading = in.headingDeg;
    }
    ratioLast = straight;
    if (n < 3) {
      return;
    }
    for (int m = 0; m < n; m++) {
      if (!(travel[m] >= RATIO_MIN_TRAVEL_M)) {
        return;
      }
    }
    System.arraycopy(travel, 0, scratch, 0, n);
    sort(scratch, n);
    double med = median(scratch, n, -1);
    for (int m = 0; m < n; m++) {
      double r = travel[m] / med;
      raise(flag(m, Rule.RATIO), nowS, Math.abs(r - 1) > RATIO_FLAG, r, travel[m]);
    }
  }

  /**
   * Swerve motors come in matched sets doing nearly the same work; one far hotter than the median
   * of the rest is mechanical drag or a dying motor, whatever the absolute number.
   */
  private void siblings(double nowS) {
    for (int g = 0; g < SUFFIXES.length; g++) {
      int k = 0;
      for (int i = 0; i < motors.length; i++) {
        temps[i] = motors[i].tempC();
        if (motorGroup[i] == g && plausible(temps[i])) {
          sorted[k++] = temps[i];
        }
      }
      sort(sorted, k);
      for (int i = 0; i < motors.length; i++) {
        if (motorGroup[i] != g) {
          continue;
        }
        double t = temps[i];
        if (!plausible(t) || k < 3) {
          raise(motorFlags[i], nowS, false, 0, 0);
          continue;
        }
        int skip = 0;
        while (skip < k - 1 && sorted[skip] != t) {
          skip++;
        }
        double mid = median(sorted, k, skip);
        raise(motorFlags[i], nowS, t - mid > SIBLING_HOT_C, t, mid);
      }
    }
  }

  private static boolean plausible(double c) {
    return Double.isFinite(c) && c > 0 && c < 150;
  }

  /** Insertion sort of the first n: a handful of numbers, and no allocation. */
  private static void sort(double[] a, int n) {
    for (int i = 1; i < n; i++) {
      double x = a[i];
      int j = i - 1;
      while (j >= 0 && a[j] > x) {
        a[j + 1] = a[j];
        j--;
      }
      a[j + 1] = x;
    }
  }

  /** Median of the first n of a sorted array, leaving out the one at {@code skip} (-1 for none). */
  private static double median(double[] sortedValues, int n, int skip) {
    int c = skip >= 0 ? n - 1 : n;
    int lo = (c - 1) / 2;
    int hi = c / 2;
    double a = sortedValues[lo >= skip && skip >= 0 ? lo + 1 : lo];
    double b = sortedValues[hi >= skip && skip >= 0 ? hi + 1 : hi];
    return (a + b) / 2;
  }

  /** Every check's state for the laptop, {@link #STRIDE} numbers each, in {@link #flags} order. */
  void fill(double[] out) {
    for (int i = 0; i < flags.size() && (i + 1) * STRIDE <= out.length; i++) {
      Flag f = flags.get(i);
      int o = i * STRIDE;
      out[o] = f.active ? 1 : 0;
      out[o + 1] = f.count;
      out[o + 2] = f.sinceS;
      out[o + 3] = f.a;
      out[o + 4] = f.b;
    }
  }

  List<Flag> flags() {
    return flags;
  }

  /**
   * Publishes the checks for the laptop: the laptop's name for each and who it is about ("" for the
   * whole robot) when that list changes, and their state every loop (NetworkTables sends only what
   * changed).
   */
  static final class Board {
    private final StringArrayPublisher rules;
    private final StringArrayPublisher who;
    private final DoubleArrayPublisher values;
    private int layout = -1;
    private double[] buf = new double[0];

    Board(NetworkTableInstance nt) {
      rules = nt.getStringArrayTopic(SlothTuneTopics.WATCH_RULES).publish();
      who = nt.getStringArrayTopic(SlothTuneTopics.WATCH_WHO).publish();
      values = nt.getDoubleArrayTopic(SlothTuneTopics.WATCH_VALUES).publish();
    }

    void publish(ModuleWatch w) {
      boolean renamed = layout != w.layout;
      if (renamed) {
        layout = w.layout;
        buf = new double[w.flags.size() * STRIDE];
      }
      w.fill(buf);
      values.set(buf);
      if (renamed) {
        int n = w.flags.size();
        String[] r = new String[n];
        String[] o = new String[n];
        for (int i = 0; i < n; i++) {
          r[i] = w.flags.get(i).rule.laptop;
          o[i] = w.flags.get(i).module;
        }
        rules.set(r);
        who.set(o);
      }
    }
  }
}
