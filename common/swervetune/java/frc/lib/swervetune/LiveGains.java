package frc.lib.swervetune;

import edu.wpi.first.networktables.DoubleEntry;
import edu.wpi.first.networktables.DoublePublisher;
import edu.wpi.first.networktables.IntegerPublisher;
import edu.wpi.first.networktables.IntegerSubscriber;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StringPublisher;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Gains that can be changed on the running robot from the laptop, without a redeploy.
 *
 * <p>The laptop writes any of the {@code /SwerveTune/Gains/...} values, then bumps
 * {@code ApplySeq}. The robot applies the whole set together, once, so a P and a D changed at the
 * same moment land together rather than one loop apart.
 *
 * <p>With {@code "advantageScopeTuning": true} in swervetune.json, every gain is also published
 * under {@code /Tuning/SwerveTune/...}, the table AdvantageScope's tuning mode edits. An edit there
 * goes through the same bounds; it is refused while a test is running (it would spoil the
 * measurement) or with the FMS attached, and the field then snaps back to what is really running.
 * Both views always show the same values, whoever changed them.
 *
 * <p>Three rules hold everywhere:
 *
 * <ul>
 *   <li><b>Never persisted.</b> Nothing here is written to a motor controller's flash. A power cycle
 *       or a restart puts back whatever the JSON files say. To keep a value, the laptop tool writes
 *       it into the JSON and you redeploy, so the repository is always the source of truth.
 *   <li><b>Bounded here, not just on the laptop.</b> A value outside {@link #SPECS} is refused for its
 *       whole group, so a mistyped decimal point from any client cannot reach a motor.
 *   <li><b>Echoed.</b> {@code Gains/Applied/...} always shows what the robot is actually running, so
 *       the laptop never has to assume a write landed.
 * </ul>
 *
 * <p>Units are the motor controller's own. On the SPARKs with YAGSL's conversion factors, steering
 * gains are duty cycle per degree and drive gains are duty cycle per (m/s). The derivative term on a
 * SPARK is per 1 ms controller step, not per second. These units change when REVLib drops
 * conversion factors in 2027; see {@code docs/MIGRATION_2027.md}.
 */
final class LiveGains {
  /** A tunable value and the range the robot will accept. */
  record Spec(String key, double min, double max, String group) {}

  static final List<Spec> SPECS = new ArrayList<>();

  private static void spec(String key, double min, double max, String group) {
    SPECS.add(new Spec(key, min, max, group));
  }

  static {
    spec("Steer/kP", 0, 0.2, "steerPid");
    spec("Steer/kI", 0, 0.01, "steerPid");
    spec("Steer/kD", 0, 2.0, "steerPid");
    spec("Steer/IZone", 0, 90, "steerPid");
    spec("Drive/kP", 0, 2.0, "drivePid");
    spec("Drive/kI", 0, 0.5, "drivePid");
    spec("Drive/kD", 0, 5.0, "drivePid");
    spec("Drive/IZone", 0, 5, "drivePid");
    spec("Steer/RampS", 0, 1.0, "ramp");
    spec("Drive/RampS", 0, 1.0, "ramp");
    spec("Drive/VelPeriodMs", 0, 64, "velFilter");
    spec("Drive/VelDepth", 0, 8, "velFilter");
    spec("Chassis/AngVelCoeff", -0.3, 0.3, "angVel");
    spec("EncoderSync/Enabled", 0, 1, "encSync");
    spec("EncoderSync/DeadbandDeg", 0.25, 10, "encSync");
  }

  /** Bounds for every module's feedforward. */
  static final Spec FF_KS = new Spec("kS", 0, 1.5, "ff");

  static final Spec FF_KV = new Spec("kV", 0.5, 8.0, "ff");
  static final Spec FF_KA = new Spec("kA", 0, 4.0, "ff");

  private final DrivetrainIO io;
  private final long bootId;
  private final Map<String, Spec> specByKey = new LinkedHashMap<>();
  private final Map<String, DoubleEntry> requested = new LinkedHashMap<>();
  private final Map<String, DoublePublisher> applied = new LinkedHashMap<>();
  private final Map<String, Double> current = new LinkedHashMap<>();
  private final IntegerSubscriber applySeq;
  private final IntegerSubscriber applyBootId;
  private final IntegerPublisher appliedSeq;
  private final StringPublisher status;
  private long lastSeq;
  /** AdvantageScope's view, when the tuning bridge is on: the entries and what was last shown. */
  private final Map<String, DoubleEntry> tuning = new LinkedHashMap<>();
  private final Map<String, Double> shown = new LinkedHashMap<>();
  private final StringPublisher tuningStatus;
  /** Whether a gain changed since {@link #takeChanged} was last asked; true at the start. */
  private boolean changed = true;

  LiveGains(NetworkTableInstance nt, DrivetrainIO io, SwerveTuneConfig config, long bootId) {
    this.io = io;
    this.bootId = bootId;
    for (Spec s : SPECS) {
      specByKey.put(s.key(), s);
    }
    for (int m = 0; m < io.moduleCount(); m++) {
      String base = "FF/" + io.moduleName(m) + "/";
      specByKey.put(base + "kS", new Spec(base + "kS", FF_KS.min(), FF_KS.max(), "ff:" + m));
      specByKey.put(base + "kV", new Spec(base + "kV", FF_KV.min(), FF_KV.max(), "ff:" + m));
      specByKey.put(base + "kA", new Spec(base + "kA", FF_KA.min(), FF_KA.max(), "ff:" + m));
    }

    double[] sp = io.steerPid();
    double[] dp = io.drivePid();
    double[] ramps = io.rampRates();
    current.put("Steer/kP", sp[0]);
    current.put("Steer/kI", sp[1]);
    current.put("Steer/kD", sp[2]);
    current.put("Steer/IZone", sp[3]);
    current.put("Drive/kP", dp[0]);
    current.put("Drive/kI", dp[1]);
    current.put("Drive/kD", dp[2]);
    current.put("Drive/IZone", dp[3]);
    current.put("Steer/RampS", ramps[0]);
    current.put("Drive/RampS", ramps[1]);
    current.put("Drive/VelPeriodMs", (double) config.driveVelocityPeriodMs);
    current.put("Drive/VelDepth", (double) config.driveVelocityDepth);
    current.put("Chassis/AngVelCoeff", config.angularVelocityCoefficient);
    current.put("EncoderSync/Enabled", config.encoderAutoSync ? 1.0 : 0.0);
    current.put("EncoderSync/DeadbandDeg", config.encoderAutoSyncDeadbandDeg);
    for (int m = 0; m < io.moduleCount(); m++) {
      double[] ff = io.driveFeedforward(m);
      String base = "FF/" + io.moduleName(m) + "/";
      current.put(base + "kS", ff[0]);
      current.put(base + "kV", ff[1]);
      current.put(base + "kA", ff[2]);
    }

    for (Map.Entry<String, Double> e : current.entrySet()) {
      DoubleEntry entry = nt.getDoubleTopic(SwerveTuneTopics.GAINS + e.getKey()).getEntry(e.getValue());
      entry.set(e.getValue());
      requested.put(e.getKey(), entry);
      DoublePublisher pub = nt.getDoubleTopic(SwerveTuneTopics.GAINS_APPLIED + e.getKey()).publish();
      pub.set(e.getValue());
      applied.put(e.getKey(), pub);
    }
    applySeq = nt.getIntegerTopic(SwerveTuneTopics.GAINS_APPLY_SEQ).subscribe(0);
    applyBootId = nt.getIntegerTopic(SwerveTuneTopics.GAINS_BOOT_ID).subscribe(0);
    appliedSeq = nt.getIntegerTopic(SwerveTuneTopics.GAINS_APPLIED_SEQ).publish();
    status = nt.getStringTopic(SwerveTuneTopics.GAINS_APPLY_STATUS).publish();
    lastSeq = applySeq.get();
    appliedSeq.set(lastSeq);
    status.set("Running the gains from the JSON files.");
    if (config.advantageScopeTuning) {
      for (Map.Entry<String, Double> e : current.entrySet()) {
        DoubleEntry entry = nt.getDoubleTopic(SwerveTuneTopics.TUNING + e.getKey()).getEntry(e.getValue());
        entry.set(e.getValue());
        tuning.put(e.getKey(), entry);
        shown.put(e.getKey(), e.getValue());
      }
      tuningStatus = nt.getStringTopic(SwerveTuneTopics.TUNING + "Status").publish();
      tuningStatus.set("Edit a value to try it live. Not saved: use Save in the swerve tools to keep it.");
    } else {
      tuningStatus = null;
    }
  }

  /**
   * Every gain, if any changed since the last call (and on the first call), else null. Asked from
   * the robot loop, so AdvantageKit records it in that loop's cycle.
   */
  Map<String, Double> takeChanged() {
    if (!changed) {
      return null;
    }
    changed = false;
    return Map.copyOf(current);
  }

  /** Current value of a gain the robot is running. */
  double get(String key) {
    Double v = current.get(key);
    return v == null ? Double.NaN : v;
  }

  /**
   * Applies a new set if the laptop has asked for one. Call every loop.
   *
   * @param blockedReason why changes can't be applied right now (the FMS is attached, a test is
   *     running), or null when they can; the same gate as AdvantageScope's edits
   */
  void poll(String blockedReason) {
    long seq = applySeq.get();
    if (seq == lastSeq) {
      return;
    }
    lastSeq = seq;
    if (applyBootId.get() != bootId) {
      status.set("Ignored a gain change meant for an earlier run of the robot program.");
      appliedSeq.set(seq);
      return;
    }
    if (blockedReason != null) {
      sync(); // the laptop's boxes go back to what is really running
      status.set("REFUSED: not applied while " + blockedReason + ".");
      appliedSeq.set(seq);
      return;
    }

    Map<String, Double> wanted = new LinkedHashMap<>();
    for (Map.Entry<String, DoubleEntry> e : requested.entrySet()) {
      wanted.put(e.getKey(), e.getValue().get());
    }
    String msg = apply(wanted);
    appliedSeq.set(seq);
    status.set(msg);
  }

  /**
   * Applies AdvantageScope's edits, if the tuning bridge is on and anything was edited. Call every
   * loop.
   *
   * @param blockedReason why edits can't be applied right now, or null when they can
   */
  void pollTuning(String blockedReason) {
    if (tuning.isEmpty()) {
      return;
    }
    Map<String, Double> wanted = new LinkedHashMap<>(current);
    List<String> edited = new ArrayList<>();
    for (Map.Entry<String, DoubleEntry> e : tuning.entrySet()) {
      double v = e.getValue().get();
      if (Double.compare(v, shown.get(e.getKey())) != 0) {
        wanted.put(e.getKey(), v);
        edited.add(e.getKey());
      }
    }
    if (edited.isEmpty()) {
      return;
    }
    String msg;
    if (blockedReason != null) {
      msg = "Not applied (" + String.join(", ", edited) + "): " + blockedReason + ".";
      sync();
    } else {
      msg = apply(wanted);
    }
    tuningStatus.set(msg);
    status.set(msg);
  }

  /**
   * Applies every group with a changed value, refusing a whole group if any value in it is out of
   * bounds, then shows what is really running everywhere. Returns the sentence for a person.
   */
  private String apply(Map<String, Double> wanted) {
    // Which groups changed, and which are out of bounds.
    Map<String, List<String>> changedGroups = new LinkedHashMap<>();
    List<String> refused = new ArrayList<>();
    for (Map.Entry<String, Double> e : wanted.entrySet()) {
      double now = current.get(e.getKey());
      double want = e.getValue();
      if (Double.compare(now, want) == 0) {
        continue;
      }
      Spec spec = specByKey.get(e.getKey());
      if (!Double.isFinite(want) || want < spec.min() || want > spec.max()) {
        refused.add(String.format("%s=%s is outside [%s, %s]", e.getKey(), want, spec.min(), spec.max()));
        changedGroups.computeIfAbsent(spec.group(), g -> new ArrayList<>()).add("!");
        continue;
      }
      changedGroups.computeIfAbsent(spec.group(), g -> new ArrayList<>()).add(e.getKey());
    }

    List<String> done = new ArrayList<>();
    for (Map.Entry<String, List<String>> g : changedGroups.entrySet()) {
      if (g.getValue().contains("!")) {
        continue; // a group with any out-of-range value is refused whole
      }
      DrivetrainIO.ApplyResult r = applyGroup(g.getKey(), wanted);
      if (r.ok()) {
        for (Spec s : specByKey.values()) {
          if (s.group().equals(g.getKey())) {
            current.put(s.key(), wanted.get(s.key()));
          }
        }
        done.add(r.message());
      } else {
        refused.add(r.message());
      }
    }

    sync();
    if (!done.isEmpty()) {
      changed = true;
    }
    String msg = done.isEmpty() ? "Nothing changed." : "Applied: " + String.join("; ", done) + ".";
    if (!refused.isEmpty()) {
      msg += " REFUSED: " + String.join("; ", refused) + ".";
    }
    return msg + " Not saved: Save in the tool to keep it.";
  }

  /** Puts what is really running back on every view: the laptop's, the echo, AdvantageScope's. */
  private void sync() {
    for (Map.Entry<String, Double> e : current.entrySet()) {
      if (Double.compare(requested.get(e.getKey()).get(), e.getValue()) != 0) {
        requested.get(e.getKey()).set(e.getValue());
      }
      applied.get(e.getKey()).set(e.getValue());
      DoubleEntry t = tuning.get(e.getKey());
      if (t != null) {
        if (Double.compare(t.get(), e.getValue()) != 0) {
          t.set(e.getValue());
        }
        shown.put(e.getKey(), e.getValue());
      }
    }
  }

  private DrivetrainIO.ApplyResult applyGroup(String group, Map<String, Double> w) {
    if (group.startsWith("ff:")) {
      int m = Integer.parseInt(group.substring(3));
      String base = "FF/" + io.moduleName(m) + "/";
      return io.applyDriveFeedforward(m, w.get(base + "kS"), w.get(base + "kV"), w.get(base + "kA"));
    }
    return switch (group) {
      case "steerPid" -> io.applySteerPid(
          w.get("Steer/kP"), w.get("Steer/kI"), w.get("Steer/kD"), w.get("Steer/IZone"));
      case "drivePid" -> io.applyDrivePid(
          w.get("Drive/kP"), w.get("Drive/kI"), w.get("Drive/kD"), w.get("Drive/IZone"));
      case "ramp" -> io.applyRampRates(w.get("Steer/RampS"), w.get("Drive/RampS"));
      case "velFilter" -> {
        int period = (int) Math.round(w.get("Drive/VelPeriodMs"));
        int depth = (int) Math.round(w.get("Drive/VelDepth"));
        if (period < 8 || depth < 1) {
          yield DrivetrainIO.ApplyResult.failed(
              "Drive velocity filter needs period >= 8 ms and depth >= 1; the controller's own"
                  + " default cannot be restored live, only by restarting");
        }
        yield io.applyDriveVelocityFilter(period, depth);
      }
      case "angVel" -> {
        double c = w.get("Chassis/AngVelCoeff");
        yield io.applyAngularVelocityCompensation(c != 0, c != 0, c);
      }
      case "encSync" -> io.applyEncoderAutoSync(
          w.get("EncoderSync/Enabled") != 0, w.get("EncoderSync/DeadbandDeg"));
      default -> DrivetrainIO.ApplyResult.failed("unknown group " + group);
    };
  }
}
