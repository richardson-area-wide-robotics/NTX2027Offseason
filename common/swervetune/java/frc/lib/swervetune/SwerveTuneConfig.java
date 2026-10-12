package frc.lib.swervetune;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Settings read from {@code deploy/swerve/swervetune.json}, next to YAGSL's own files.
 *
 * <p>YAGSL's JSON has nowhere to put a measured per-module feedforward, a velocity filter, or the
 * compensation switches YAGSL only exposes in code, so they live here and are applied once at
 * startup. The laptop tool writes this file when you press Save.
 *
 * <p><b>A missing or empty file changes nothing.</b> Every field defaults to "leave YAGSL as it
 * is", so dropping the library into a robot does not alter how it drives until somebody measures
 * something and chooses to keep it. That is deliberate: change one thing, measure it, keep it or
 * revert it.
 */
public final class SwerveTuneConfig {
  /** {@code motor} (YAGSL's default for these robots) or {@code absolute}. */
  public String steerFeedback = "motor";

  public boolean encoderAutoSync = false;
  public double encoderAutoSyncDeadbandDeg = 1.0;

  /** Drive motor velocity measurement window, ms. 0 leaves the controller's default. */
  public int driveVelocityPeriodMs = 0;

  /** Drive motor velocity averaging depth. 0 leaves the controller's default. */
  public int driveVelocityDepth = 0;

  /** Measured feedforward by YAGSL module name: {@code {kS, kV, kA}}. Absent means YAGSL's default. */
  public final Map<String, double[]> driveFeedforward = new LinkedHashMap<>();

  public boolean angularVelocityCompensationTeleop = false;
  public boolean angularVelocityCompensationAuto = false;
  public double angularVelocityCoefficient = 0.0;

  /** Null leaves YAGSL's default (teleop on, auto off). */
  public Boolean chassisDiscretizationTeleop = null;

  public Boolean chassisDiscretizationAuto = null;
  public double chassisDiscretizationDtS = 0.02;

  /** Driver controller port. Moving its sticks takes control back from any test. */
  public int driverPort = 0;

  /**
   * Controller port for the deadman. A second pad, held by whoever is watching the robot, so the
   * deadman never shares a button with a robot function: Peashooter's right bumper runs the feeder.
   */
  public int deadmanPort = 1;

  /** Button held as the deadman on the field. 6 is the right bumper on an Xbox pad. */
  public int deadmanButton = 6;

  /** Axes that, if moved, take control back from a test. Left X, left Y, right X on an Xbox pad. */
  public int[] overrideAxes = {0, 1, 4};

  public double defaultSpeedCapMps = 1.0;
  public double maxSpeedCapMps = 3.0;

  public final SafetySupervisor.Limits limits = new SafetySupervisor.Limits();

  /** Problems found while reading, shown on the laptop at connect. */
  public final List<String> warnings = new ArrayList<>();

  /** Reads the file, or returns the do-nothing defaults if it is missing or unreadable. */
  public static SwerveTuneConfig load(Path file) {
    SwerveTuneConfig c = new SwerveTuneConfig();
    if (file == null || !Files.exists(file)) {
      c.warnings.add("No swervetune.json; running with YAGSL's own settings unchanged.");
      return c;
    }
    try {
      return parse(Files.readString(file, StandardCharsets.UTF_8));
    } catch (IOException | RuntimeException e) {
      c.warnings.add("Could not read " + file.getFileName() + ": " + e.getMessage()
          + ". Running with YAGSL's own settings unchanged.");
      return c;
    }
  }

  /** Parses the text of a config file. Unknown keys are ignored; bad values become warnings. */
  @SuppressWarnings("unchecked")
  public static SwerveTuneConfig parse(String text) {
    SwerveTuneConfig c = new SwerveTuneConfig();
    Object root = MiniJson.parse(text);
    if (!(root instanceof Map)) {
      c.warnings.add("swervetune.json is not a JSON object; ignored.");
      return c;
    }
    Map<String, Object> m = (Map<String, Object>) root;

    String fb = str(m.get("steerFeedback"), "motor");
    if (fb.equals("motor") || fb.equals("absolute")) {
      c.steerFeedback = fb;
    } else {
      c.warnings.add("steerFeedback must be \"motor\" or \"absolute\"; got \"" + fb + "\".");
    }

    Map<String, Object> sync = map(m.get("encoderAutoSync"));
    c.encoderAutoSync = bool(sync.get("enabled"), false);
    c.encoderAutoSyncDeadbandDeg = num(sync.get("deadbandDeg"), 1.0);

    Map<String, Object> filter = map(m.get("driveVelocityFilter"));
    c.driveVelocityPeriodMs = (int) num(filter.get("periodMs"), 0);
    c.driveVelocityDepth = (int) num(filter.get("depth"), 0);

    for (Map.Entry<String, Object> e : map(m.get("driveFeedforward")).entrySet()) {
      Map<String, Object> ff = map(e.getValue());
      double ks = num(ff.get("kS"), Double.NaN);
      double kv = num(ff.get("kV"), Double.NaN);
      double ka = num(ff.get("kA"), 0.0);
      if (Double.isNaN(ks) || Double.isNaN(kv)) {
        c.warnings.add("driveFeedforward." + e.getKey() + " needs kS and kV; ignored.");
        continue;
      }
      c.driveFeedforward.put(e.getKey(), new double[] {ks, kv, ka});
    }

    Map<String, Object> avc = map(m.get("angularVelocityCompensation"));
    c.angularVelocityCompensationTeleop = bool(avc.get("teleop"), false);
    c.angularVelocityCompensationAuto = bool(avc.get("auto"), false);
    c.angularVelocityCoefficient = num(avc.get("coefficient"), 0.0);

    Map<String, Object> disc = map(m.get("chassisDiscretization"));
    if (disc.containsKey("teleop")) {
      c.chassisDiscretizationTeleop = bool(disc.get("teleop"), true);
    }
    if (disc.containsKey("auto")) {
      c.chassisDiscretizationAuto = bool(disc.get("auto"), false);
    }
    c.chassisDiscretizationDtS = num(disc.get("dtSeconds"), 0.02);

    Map<String, Object> op = map(m.get("operator"));
    c.driverPort = (int) num(op.get("driverPort"), 0);
    c.deadmanPort = (int) num(op.get("deadmanPort"), 1);
    c.deadmanButton = (int) num(op.get("deadmanButton"), 6);
    Object axes = op.get("overrideAxes");
    if (axes instanceof List<?> list) {
      int[] a = new int[list.size()];
      for (int k = 0; k < a.length; k++) {
        a[k] = (int) num(list.get(k), 0);
      }
      c.overrideAxes = a;
    }
    c.limits.driverOverride = num(op.get("overrideThreshold"), c.limits.driverOverride);

    Map<String, Object> t = map(m.get("testLimits"));
    c.defaultSpeedCapMps = num(t.get("defaultSpeedCapMps"), c.defaultSpeedCapMps);
    c.maxSpeedCapMps = num(t.get("maxSpeedCapMps"), c.maxSpeedCapMps);
    c.limits.minStartVoltsField = num(t.get("minStartVoltsField"), c.limits.minStartVoltsField);
    c.limits.minStartVoltsBlocks = num(t.get("minStartVoltsBlocks"), c.limits.minStartVoltsBlocks);
    c.limits.impactMps2 = num(t.get("impactMps2"), c.limits.impactMps2);
    c.limits.blocksYawRateDps = num(t.get("blocksYawRateDps"), c.limits.blocksYawRateDps);
    return c;
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> map(Object o) {
    return o instanceof Map ? (Map<String, Object>) o : Map.of();
  }

  private static double num(Object o, double fallback) {
    return o instanceof Double d && Double.isFinite(d) ? d : fallback;
  }

  private static boolean bool(Object o, boolean fallback) {
    return o instanceof Boolean b ? b : fallback;
  }

  private static String str(Object o, String fallback) {
    return o instanceof String s ? s : fallback;
  }
}
