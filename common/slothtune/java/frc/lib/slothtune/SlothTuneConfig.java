package frc.lib.slothtune;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Settings read from {@code deploy/swerve/slothtune.json}, next to YAGSL's own files.
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
public final class SlothTuneConfig {
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

  /**
   * A pod's own PID, by YAGSL module name, then "steer" or "drive": {@code {p, i, d, iz}}, any of
   * them NaN to keep the shared value from pidfproperties.json. Absent means the shared gains.
   */
  public final Map<String, Map<String, double[]>> podGains = new LinkedHashMap<>();

  /**
   * A system's limits, by its registered name: {@code {min, max, maxVelocity, maxAccel}} in its own
   * units, NaN where not given. The robot enforces them in every system test.
   */
  public final Map<String, double[]> systems = new LinkedHashMap<>();

  public boolean angularVelocityCompensationTeleop = false;
  public boolean angularVelocityCompensationAuto = false;
  public double angularVelocityCoefficient = 0.0;

  /** Null leaves YAGSL's default (teleop on, auto off). */
  public Boolean chassisDiscretizationTeleop = null;

  public Boolean chassisDiscretizationAuto = null;
  public double chassisDiscretizationDtS = 0.02;

  /** The driver's joystick port. Moving its sticks takes control back from any test. */
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

  /** Watch every motor for heat, stalls and failure ({@link MotorGuard}). */
  public boolean motorGuard = true;
  /**
   * Publish the live gains under {@code /Tuning/SlothTune}, where AdvantageScope's tuning mode can
   * edit them. Off unless the file says so.
   */
  public boolean advantageScopeTuning = false;

  /** Lower any current limit above the team policy for its motor, until the next reboot. */
  public boolean enforceCurrentPolicy = true;

  /**
   * What each motor really is, by {@code "drive"}, {@code "steer"} or a motor's full name such as
   * {@code "Shooter leader"}. A NEO V1.1 and a NEO 2.0 cannot be told apart electrically, and a NEO
   * 550 on a SPARK MAX looks like any NEO, so only this inventory can say.
   */
  public final Map<String, MotorKind> motorKinds = new LinkedHashMap<>();

  /**
   * Where each camera sits on the robot, by the name its PhotonVision page shows: {@code {x, y, z}}
   * meters from the robot's center at the floor (x forward, y left, z up), then {@code {roll,
   * pitch, yaw}} degrees (pitch negative when the camera looks up). The Calibrate tab measures them.
   */
  public final Map<String, double[]> cameras = new LinkedHashMap<>();

  /**
   * The cameras the robot uses, by their PhotonVision names ({@code "vision": {"cameras":
   * ["front"]}}). Empty: no camera. Listing one is all it takes once PhotonLib is in the build:
   * {@code PhotonVisionSetup.install} makes a source for each.
   */
  public final List<String> visionCameras = new ArrayList<>();

  /**
   * Whether accepted vision poses go into the drivetrain's own pose estimator ({@code "vision":
   * {"feedPoseEstimator": true}}), which every auto and field-relative drive uses. Off until a
   * camera's mount is measured and its poses look right on the Live tab: a wrong mount pulls the
   * robot's idea of where it is off by the same mistake.
   */
  public boolean feedPoseEstimator = false;

  /**
   * Which official AprilTag layout the cameras start from: {@code "welded"} (default) or
   * {@code "andymark"}, as the event's field is built ({@code "vision": {"field": ...}}). The field
   * survey says which fits; a surveyed layout for the other one is set aside.
   */
  public String visionField = "welded";

  /**
   * The team's batteries, by the number written on each: the choices in the dashboard's Battery
   * drop-down. Empty means 1 to 12.
   */
  public final List<String> batteries = new ArrayList<>();

  /**
   * Each battery's grade from its measured sag, written by the laptop's Battery tab ("Send the
   * grades to the robot"): {@code "good"}, {@code "practice"} or {@code "retire"}. A battery not
   * listed hasn't been measured. The dashboard's Battery check line shows it, and the next battery
   * to use is chosen from it, so the drive team needs no laptop at the cart.
   */
  public final Map<String, String> batteryGrades = new java.util.LinkedHashMap<>();

  /**
   * How often a Canandgyro reports each reading, in milliseconds (slothtune.json "canandgyro"). YAGSL
   * resets the gyro to its factory settings at every startup, so these are applied after it, each
   * time, and not saved on the gyro. 0 leaves a reading as YAGSL left it. The defaults: yaw 10 (its
   * own default), angular position 10 (YAGSL's heading comes from this one; its own default is 20),
   * angular velocity and acceleration 20 (its own 100 is too slow for impact detection and YAGSL's
   * angular velocity compensation), status 100.
   */
  public boolean canandgyroApply = true;
  public double canandgyroYawMs = 10;
  public double canandgyroAngularPositionMs = 10;
  public double canandgyroAngularVelocityMs = 20;
  public double canandgyroAccelerationMs = 20;
  public double canandgyroStatusMs = 100;

  /** A current sensor's calibration (slothtune.json "currentSensors", by the sensor's name). */
  public static final class CurrentSensorConfig {
    public String mode = "rise";
    public double thresholdA = Double.NaN;
    public double holdS = 0.06;
    public double ignoreS = 0.25;
    public double[][] baseline = new double[0][];
  }

  /** Each current sensor's calibration, by its name (the Systems tab writes them). */
  public final Map<String, CurrentSensorConfig> currentSensors = new LinkedHashMap<>();

  /** Each hold's {current amps, power -1 to 1}, by its motor's name (slothtune.json "holds"). */
  public final Map<String, double[]> holds = new LinkedHashMap<>();

  /** Problems found while reading, shown on the laptop at connect. */
  public final List<String> warnings = new ArrayList<>();

  /** A Canandgyro frame period: 0 (leave it), or 1 ms up to the gyro's own limit; else the default. */
  private static double framePeriod(SlothTuneConfig c, Map<String, Object> gyro, String key, double fallback, double max) {
    double v = num(gyro.get(key), fallback);
    if (v != 0 && (v < 1 || v > max)) {
      c.warnings.add("canandgyro." + key + " must be 0 or 1 to " + (int) max + " ms; got " + v + ". Using " + (int) fallback + ".");
      return fallback;
    }
    return v;
  }

  /** Reads the file, or returns the do-nothing defaults if it is missing or unreadable. */
  public static SlothTuneConfig load(Path file) {
    SlothTuneConfig c = new SlothTuneConfig();
    if (file == null || !Files.exists(file)) {
      c.warnings.add("No slothtune.json; running with YAGSL's own settings unchanged.");
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
  public static SlothTuneConfig parse(String text) {
    SlothTuneConfig c = new SlothTuneConfig();
    Object root = MiniJson.parse(text);
    if (!(root instanceof Map)) {
      c.warnings.add("slothtune.json is not a JSON object; ignored.");
      return c;
    }
    Map<String, Object> m = (Map<String, Object>) root;

    String fb = str(m.get("steerFeedback"), "motor");
    if (fb.equals("motor") || fb.equals("absolute")) {
      c.steerFeedback = fb;
    } else {
      c.warnings.add("steerFeedback must be \"motor\" or \"absolute\"; got \"" + fb + "\".");
    }

    for (Map.Entry<String, Object> e : map(m.get("currentSensors")).entrySet()) {
      Map<String, Object> s = map(e.getValue());
      CurrentSensorConfig cs = new CurrentSensorConfig();
      cs.mode = str(s.get("mode"), "rise");
      if (!List.of("rise", "drop", "aboveBaseline").contains(cs.mode)) {
        c.warnings.add("currentSensors." + e.getKey() + ".mode must be rise, drop or aboveBaseline; using rise.");
        cs.mode = "rise";
      }
      cs.thresholdA = num(s.get("thresholdA"), Double.NaN);
      cs.holdS = Math.max(0, num(s.get("holdS"), 0.06));
      cs.ignoreS = Math.max(0, num(s.get("ignoreS"), 0.25));
      List<double[]> base = new ArrayList<>();
      if (s.get("baseline") instanceof List<?> rows) {
        for (Object r : rows) {
          if (r instanceof List<?> pair && pair.size() >= 2 && pair.get(0) instanceof Number p && pair.get(1) instanceof Number a) {
            base.add(new double[] {p.doubleValue(), a.doubleValue()});
          }
        }
      }
      base.sort((x, y) -> Double.compare(x[0], y[0]));
      cs.baseline = base.toArray(new double[0][]);
      c.currentSensors.put(e.getKey(), cs);
    }
    for (Map.Entry<String, Object> e : map(m.get("holds")).entrySet()) {
      Map<String, Object> h = map(e.getValue());
      c.holds.put(e.getKey(), new double[] {num(h.get("currentA"), Double.NaN), num(h.get("duty"), Double.NaN)});
    }

    Map<String, Object> gyro = map(m.get("canandgyro"));
    c.canandgyroApply = bool(gyro.get("apply"), true);
    c.canandgyroYawMs = framePeriod(c, gyro, "yawFramePeriodMs", c.canandgyroYawMs, 65535);
    c.canandgyroAngularPositionMs = framePeriod(c, gyro, "angularPositionFramePeriodMs", c.canandgyroAngularPositionMs, 65535);
    c.canandgyroAngularVelocityMs = framePeriod(c, gyro, "angularVelocityFramePeriodMs", c.canandgyroAngularVelocityMs, 65535);
    c.canandgyroAccelerationMs = framePeriod(c, gyro, "accelerationFramePeriodMs", c.canandgyroAccelerationMs, 65535);
    c.canandgyroStatusMs = framePeriod(c, gyro, "statusFramePeriodMs", c.canandgyroStatusMs, 16383);
    if (c.canandgyroStatusMs == 0) {
      c.warnings.add("canandgyro.statusFramePeriodMs can't be 0 (it carries the faults); using 100.");
      c.canandgyroStatusMs = 100;
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

    for (Map.Entry<String, Object> e : map(m.get("podGains")).entrySet()) {
      Map<String, double[]> pod = new LinkedHashMap<>();
      for (String loop : new String[] {"steer", "drive"}) {
        Map<String, Object> g = map(map(e.getValue()).get(loop));
        if (!g.isEmpty()) {
          pod.put(loop, new double[] {num(g.get("p"), Double.NaN), num(g.get("i"), Double.NaN),
              num(g.get("d"), Double.NaN), num(g.get("iz"), Double.NaN)});
        }
      }
      if (!pod.isEmpty()) {
        c.podGains.put(e.getKey(), pod);
      }
    }

    for (Map.Entry<String, Object> e : map(m.get("systems")).entrySet()) {
      Map<String, Object> s = map(e.getValue());
      c.systems.put(e.getKey(), new double[] {num(s.get("min"), Double.NaN), num(s.get("max"), Double.NaN),
          num(s.get("maxVelocity"), Double.NaN), num(s.get("maxAccel"), Double.NaN)});
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

    Map<String, Object> motors = map(m.get("motors"));
    c.motorGuard = bool(motors.get("guard"), true);
    c.advantageScopeTuning = bool(m.get("advantageScopeTuning"), false);
    c.enforceCurrentPolicy = bool(motors.get("enforcePolicy"), true);
    for (Map.Entry<String, Object> e : motors.entrySet()) {
      if (e.getKey().equals("guard") || e.getKey().equals("enforcePolicy")
          || e.getKey().startsWith("_")) {
        continue;
      }
      String kind = str(e.getValue(), "");
      String k = kind.toLowerCase(java.util.Locale.ROOT);
      if (!(k.contains("neo") || k.contains("vortex") || k.contains("550") || k.contains("flex"))) {
        c.warnings.add("motors." + e.getKey() + ": \"" + kind + "\" is not a REV motor this knows"
            + " (NEO V1.1, NEO 2.0, NEO 550, NEO Vortex); ignored.");
        continue;
      }
      c.motorKinds.put(e.getKey(), MotorKind.parse(kind));
    }

    if (m.get("batteries") instanceof List<?> list) {
      for (Object b : list) {
        String id = b instanceof Number n && n.doubleValue() == Math.rint(n.doubleValue())
            ? Long.toString(n.longValue()) : str(b, "").trim();
        if (!id.isEmpty() && !c.batteries.contains(id)) {
          c.batteries.add(id);
        }
      }
    }

    for (Map.Entry<String, Object> e : map(m.get("batteryGrades")).entrySet()) {
      String g = str(e.getValue(), "").trim().toLowerCase(java.util.Locale.ROOT);
      if (e.getKey().startsWith("_")) {
        continue;
      }
      if (g.equals("good") || g.equals("practice") || g.equals("retire")) {
        c.batteryGrades.put(e.getKey().trim(), g);
      } else {
        c.warnings.add("batteryGrades: battery " + e.getKey() + " has grade \"" + g
            + "\"; expected good, practice or retire. Ignored.");
      }
    }

    for (Map.Entry<String, Object> e : map(m.get("cameras")).entrySet()) {
      if (e.getKey().startsWith("_")) {
        continue;
      }
      Map<String, Object> cam = map(e.getValue());
      double[] v = {num(cam.get("x"), Double.NaN), num(cam.get("y"), Double.NaN),
          num(cam.get("z"), Double.NaN), num(cam.get("roll"), 0), num(cam.get("pitch"), 0),
          num(cam.get("yaw"), 0)};
      if (!Double.isFinite(v[0]) || !Double.isFinite(v[1]) || !Double.isFinite(v[2])) {
        c.warnings.add("cameras." + e.getKey() + ": needs x, y and z in meters; ignored.");
        continue;
      }
      c.cameras.put(e.getKey(), v);
    }

    Map<String, Object> vision = map(m.get("vision"));
    if (vision.get("cameras") instanceof List<?> list) {
      for (Object o : list) {
        String n = str(o, "").trim();
        if (!n.isEmpty() && !c.visionCameras.contains(n)) {
          c.visionCameras.add(n);
        }
      }
    }
    c.feedPoseEstimator = Boolean.TRUE.equals(vision.get("feedPoseEstimator"));
    String field = str(vision.get("field"), "welded").trim().toLowerCase(java.util.Locale.ROOT);
    if (field.equals("welded") || field.equals("andymark")) {
      c.visionField = field;
    } else {
      c.warnings.add("vision: field must be \"welded\" or \"andymark\"; got \"" + field + "\". Using welded.");
    }
    if (c.feedPoseEstimator) {
      for (String n : c.visionCameras) {
        if (!c.cameras.containsKey(n)) {
          c.warnings.add("vision: camera " + n + " has no measured mount in \"cameras\", so its poses"
              + " are not fed to the pose estimator. Measure it on the Calibrate tab.");
        }
      }
    }

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
