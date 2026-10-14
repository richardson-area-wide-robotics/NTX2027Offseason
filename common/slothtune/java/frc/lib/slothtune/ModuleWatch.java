package frc.lib.slothtune;

import java.util.ArrayList;
import java.util.List;

/**
 * The laptop monitor's module checks, run on the robot every loop so they watch matches too, when
 * no laptop is connected: a module far from where it is told to point, its two steering sensors
 * disagreeing, a wheel turning against its command. Each keeps a count for the session, shown on
 * Robot Health and logged with AdvantageKit for the post-match summary. Thresholds are the
 * laptop's (tools/slothtune/monitor.py), so both say the same thing.
 *
 * <p>Left out on purpose: "a wheel well short of its speed", which fires all match long while the
 * robot is pushing or being pushed.
 */
final class ModuleWatch {
  /** One check: what it means, how long the condition must last, and its log name. */
  enum Rule {
    STEER_OFF("SteerOff", 0.5, "steering more than 10\u00b0 from where it is told to point",
        "A loose or slipping module, a wrong offset, or steering gains too soft: Troubleshoot, "
            + "\"A wheel points the wrong way\"."),
    SENSORS_DISAGREE("SensorsDisagree", 1.0, "steering motor encoder and absolute encoder more than 3\u00b0 apart",
        "A slipped pinion or a loose absolute encoder: the module points somewhere it doesn't think "
            + "it does. Troubleshoot, \"Lines up at boot, gets worse during a match\"."),
    BACKWARDS("Backwards", 0.3, "wheel turning against its command",
        "An inverted drive motor or a module 180\u00b0 out: it fights the other three. Troubleshoot, "
            + "\"One wheel drives backwards or fights the others\".");

    final String key;
    final double holdS;
    final String what;
    final String look;

    Rule(String key, double holdS, String what, String look) {
      this.key = key;
      this.holdS = holdS;
      this.what = what;
      this.look = look;
    }
  }

  /** One module's state for one check. */
  static final class Flag {
    final String module;
    final Rule rule;
    boolean active;
    int count;
    String detail = "";
    double sinceS = Double.NaN;

    Flag(String module, Rule rule) {
      this.module = module;
      this.rule = rule;
    }
  }

  private final List<Flag> flags = new ArrayList<>();
  private final String[] names;

  ModuleWatch(String[] moduleNames) {
    names = moduleNames.clone();
    for (String n : names) {
      for (Rule r : Rule.values()) {
        flags.add(new Flag(n, r));
      }
    }
  }

  private Flag flag(int module, Rule rule) {
    return flags.get(module * Rule.values().length + rule.ordinal());
  }

  /** Angle a minus b, wrapped into -180..180. */
  static double wrap180(double deg) {
    double w = ((deg + 180) % 360 + 360) % 360 - 180;
    return w == -180 ? 180 : w;
  }

  /** One loop's readings: angles in degrees, speeds in meters per second, per module. */
  void update(double nowS, boolean enabled, double[] steer, double[] steerSp, double[] steerMotor,
      double[] v, double[] vSp) {
    for (int m = 0; m < names.length && m < steer.length; m++) {
      boolean commanded = Double.isFinite(vSp[m]) && Math.abs(vSp[m]) > 0.1;
      double err = Double.isFinite(steerSp[m]) && Double.isFinite(steer[m])
          ? wrap180(steerSp[m] - steer[m]) : Double.NaN;
      raise(flag(m, Rule.STEER_OFF), nowS, enabled && commanded && Math.abs(err) > 10,
          String.format("%+.0f\u00b0", err));
      double gap = Double.isFinite(steerMotor[m]) && Double.isFinite(steer[m])
          ? Math.abs(wrap180(steer[m] - steerMotor[m])) : 0;
      boolean still = !Double.isFinite(v[m]) || Math.abs(v[m]) < 0.05;
      raise(flag(m, Rule.SENSORS_DISAGREE), nowS, still && gap > 3, String.format("%.1f\u00b0", gap));
      boolean backwards = enabled && commanded && Double.isFinite(v[m]) && v[m] * vSp[m] < 0
          && Math.abs(v[m]) > 0.1;
      raise(flag(m, Rule.BACKWARDS), nowS, backwards, String.format("%+.2f vs %+.2f m/s", v[m], vSp[m]));
    }
  }

  private static void raise(Flag f, double nowS, boolean condition, String detail) {
    if (!condition) {
      f.sinceS = Double.NaN;
      f.active = false;
      return;
    }
    if (Double.isNaN(f.sinceS)) {
      f.sinceS = nowS;
    }
    f.detail = detail;
    if (!f.active && nowS - f.sinceS >= f.rule.holdS) {
      // Counted once each time it starts, so a long episode is one, not one per loop.
      f.active = true;
      f.count++;
    }
  }

  List<Flag> flags() {
    return flags;
  }
}
