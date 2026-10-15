package frc.lib.slothtune;

import com.revrobotics.PersistMode;
import com.revrobotics.REVLibError;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkBase;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig;
import com.revrobotics.spark.config.SparkBaseConfigAccessor;
import com.revrobotics.spark.config.SparkFlexConfig;
import com.revrobotics.spark.config.SparkMaxConfig;
import java.util.ArrayList;
import java.util.List;

/**
 * A REV SPARK MAX or SPARK Flex, as the {@link MotorGuard} sees it.
 *
 * <p>Reads the controller's current limits once, at construction, and puts exactly those back when
 * a motor cools down - including a separate free-speed limit, if the robot code set one. Lowered
 * limits are sent with {@link PersistMode#kNoPersistParameters}, so a reboot always restores what
 * the code asked for.
 *
 * <p>In simulation the SPARK reads zero current and no temperature, so every reading is reported
 * as unknown rather than as a healthy zero.
 */
public final class SparkChannel implements MotorGuard.MotorChannel {
  private final SparkBase spark;
  private final boolean simulation;
  private final int stallLimitA;
  private final int freeLimitA;
  private final int limitRpm;
  private final double positionFactor;
  private final String bootReport;
  /** Its settings ("name=value;..."): read at startup, then each live change, listed under "live". */
  private volatile String settings;
  private final java.util.Map<String, String> settingsMap;
  private final java.util.Set<String> live = new java.util.LinkedHashSet<>();
  /** Every SPARK the guard watches, to record a live change on the right one. */
  private static final java.util.Map<SparkBase, SparkChannel> BY_SPARK =
      java.util.Collections.synchronizedMap(new java.util.WeakHashMap<>());
  private final String model;
  private final String firmware;
  /** Whether it follows another SPARK: tests drive the leader only. */
  private final boolean follower;
  /** Its closed loop's sensor: position and velocity, in the units its gains use. */
  private final java.util.function.DoubleSupplier feedbackPos;
  private final java.util.function.DoubleSupplier feedbackVel;

  public SparkChannel(SparkBase spark, boolean simulation) {
    this.spark = spark;
    this.simulation = simulation;
    SparkBaseConfigAccessor a = accessor(spark);
    int stall = 0;
    int free = 0;
    int rpm = 20000;
    double factor = 1;
    if (a != null && !simulation) {
      stall = a.getSmartCurrentLimit();
      free = a.getSmartCurrentFreeLimit();
      rpm = a.getSmartCurrentRPMLimit();
      factor = a.encoder.getPositionConversionFactor();
    }
    this.stallLimitA = stall;
    this.freeLimitA = free;
    this.limitRpm = rpm;
    this.positionFactor = factor;
    // What it remembers from before the robot code started - a brownout in the last match, a CAN
    // fault - is evidence worth keeping. Record it, then clear, so anything new means "since now".
    String report = "";
    if (!simulation) {
      java.util.List<String> seen = new ArrayList<>();
      if (spark.hasStickyFault()) {
        faults(spark.getStickyFaults(), seen);
      }
      if (spark.hasStickyWarning()) {
        SparkBase.Warnings w = spark.getStickyWarnings();
        if (w.brownout) seen.add("low supply voltage");
        if (w.overcurrent) seen.add("overcurrent");
        if (w.sensor) seen.add("sensor warning");
      }
      report = String.join(", ", seen);
      spark.clearFaults();
    }
    this.bootReport = report;
    this.settingsMap = readSettings(a);
    this.settings = join(settingsMap, live);
    BY_SPARK.put(spark, this);
    boolean follows = settingsMap.containsKey("follows");
    try {
      follows = spark.isFollower();
    } catch (RuntimeException e) {
      // It won't say: the configured leader stands.
    }
    this.follower = follows;
    java.util.function.DoubleSupplier[] fb = feedback(spark, settingsMap.get("sensor"));
    this.feedbackPos = fb[0];
    this.feedbackVel = fb[1];
    this.model = simulation ? "" : detectModel(spark);
    String fw = "";
    if (!simulation) {
      try {
        fw = spark.getFirmwareString();
      } catch (RuntimeException e) {
        fw = "";
      }
    }
    this.firmware = fw == null ? "" : fw;
  }

  /**
   * What the controller says it is, asked over CAN. REVLib knows (it queries the device) but keeps
   * the method package-private, so it is reached by reflection; if that ever fails, the answer is
   * just "unknown".
   */
  static String detectModel(SparkBase spark) {
    try {
      java.lang.reflect.Method m = SparkBase.class.getDeclaredMethod("getSparkModel");
      m.setAccessible(true);
      Object v = m.invoke(spark);
      String s = String.valueOf(v);
      return s.equals("SparkMax") ? "SPARK MAX" : s.equals("SparkFlex") ? "SPARK Flex" : "";
    } catch (ReflectiveOperationException | RuntimeException e) {
      return "";
    }
  }

  @Override
  public String controllerModel() {
    return model;
  }

  @Override
  public String controllerClass() {
    return spark instanceof com.revrobotics.spark.SparkFlex ? "SPARK Flex" : "SPARK MAX";
  }

  @Override
  public String firmware() {
    return firmware;
  }

  /** Sticky faults it carried when the robot code started, before they were cleared. */
  public String bootReport() {
    return bootReport;
  }

  @Override
  public String settings() {
    return settings;
  }

  @Override
  public boolean clearStickyFaults() {
    if (!simulation) {
      spark.clearFaults();
    }
    return true;
  }

  /**
   * Its settings, asked once at startup (each is a parameter read over CAN): idle mode, inversion,
   * current limits, ramp rate, slot 0's PID and feedforward, MAXMotion's cruise speed, acceleration
   * and allowed error. A value it won't give, or a zero for an optional one, is left out.
   */
  static java.util.Map<String, String> readSettings(SparkBaseConfigAccessor a) {
    java.util.Map<String, String> out = new java.util.LinkedHashMap<>();
    if (a == null) {
      return out;
    }
    // REV's names start with a k (kBrake): "brake", "coast".
    put(out, "idle", () -> a.getIdleMode().name().replaceFirst("^k", "").toLowerCase(java.util.Locale.ROOT));
    put(out, "inverted", () -> a.getInverted() ? "yes" : "no");
    putNum(out, "stallA", () -> (double) a.getSmartCurrentLimit(), false);
    putNum(out, "freeA", () -> (double) a.getSmartCurrentFreeLimit(), true);
    putNum(out, "secondaryA", a::getSecondaryCurrentLimit, true);
    putNum(out, "rampS", a::getClosedLoopRampRate, true);
    putNum(out, "openRampS", a::getOpenLoopRampRate, true);
    putNum(out, "kP", a.closedLoop::getP, false);
    putNum(out, "kI", a.closedLoop::getI, false);
    putNum(out, "kD", a.closedLoop::getD, false);
    putNum(out, "iZone", a.closedLoop::getIZone, true);
    putNum(out, "kS", a.closedLoop.feedForward::getkS, true);
    putNum(out, "kV", a.closedLoop.feedForward::getkV, true);
    putNum(out, "kA", a.closedLoop.feedForward::getkA, true);
    putNum(out, "kG", a.closedLoop.feedForward::getkG, true);
    putNum(out, "kCos", a.closedLoop.feedForward::getkCos, true);
    putNum(out, "mmCruise", a.closedLoop.maxMotion::getCruiseVelocity, true);
    putNum(out, "mmAccel", a.closedLoop.maxMotion::getMaxAcceleration, true);
    putNum(out, "mmError", a.closedLoop.maxMotion::getAllowedProfileError, true);
    put(out, "sensor", () -> a.closedLoop.getFeedbackSensor().name().replaceFirst("^k", ""));
    // How its speed reading is filtered (each a window of positions, then an average of windows):
    // the hall sensor of a NEO on a SPARK MAX, and the quadrature encoders (a Vortex's own on a Flex).
    putNum(out, "uvwMs", () -> (double) a.encoder.getUvwMeasurementPeriod(), true);
    putNum(out, "uvwDepth", () -> (double) a.encoder.getUvwAverageDepth(), true);
    putNum(out, "quadMs", () -> (double) a.encoder.getQuadratureMeasurementPeriod(), true);
    putNum(out, "quadDepth", () -> (double) a.encoder.getQuadratureAverageDepth(), true);
    putNum(out, "follows", () -> (double) a.getFollowerModeLeaderId(), true);
    return out;
  }

  /** The settings as published: each "name=value", then "live=" the names changed live. */
  static String join(java.util.Map<String, String> map, java.util.Set<String> live) {
    StringBuilder b = new StringBuilder();
    map.forEach((k, v) -> b.append(b.length() == 0 ? "" : ";").append(k).append('=').append(v));
    if (!live.isEmpty()) {
      b.append(b.length() == 0 ? "" : ";").append("live=").append(String.join(",", live));
    }
    return b.toString();
  }

  /**
   * A setting changed live on this SPARK (the Tune or Systems tab): recorded on its settings and
   * listed as live, so the laptop shows what it runs now, not only what it started with. Pairs of
   * name and value; a SPARK the guard doesn't watch is ignored.
   */
  public static void note(SparkBase spark, Object... nameValue) {
    SparkChannel ch = spark == null ? null : BY_SPARK.get(spark);
    if (ch == null) {
      return;
    }
    synchronized (ch) {
      for (int i = 0; i + 1 < nameValue.length; i += 2) {
        String k = String.valueOf(nameValue[i]);
        Object v = nameValue[i + 1];
        ch.settingsMap.put(k, v instanceof Number n ? num(n.doubleValue()) : String.valueOf(v));
        ch.live.add(k);
      }
      ch.settings = join(ch.settingsMap, ch.live);
    }
  }

  private static String num(double v) {
    return String.format(java.util.Locale.ROOT, "%.6g", v).replaceAll("(\\.\\d*?)0+(e|$)", "$1$2")
        .replace(".e", "e").replaceAll("\\.$", "");
  }

  private static void put(java.util.Map<String, String> out, String key, java.util.function.Supplier<String> get) {
    try {
      String v = get.get();
      if (v != null && !v.isEmpty()) {
        out.put(key, v.replace(";", ",").replace("=", ":"));
      }
    } catch (RuntimeException e) {
      // This controller won't say: leave it out.
    }
  }

  private static void putNum(java.util.Map<String, String> out, String key, java.util.function.DoubleSupplier get,
      boolean skipZero) {
    try {
      double v = get.getAsDouble();
      if (Double.isFinite(v) && !(skipZero && v == 0)) {
        out.put(key, num(v));
      }
    } catch (RuntimeException e) {
      // This controller won't say: leave it out.
    }
  }

  @Override
  public boolean canPresent() {
    // REVLib returns no status frame once none has arrived for 500 ms.
    return simulation || spark.getPeriodicStatus0() != null;
  }

  @Override
  public boolean resetSeen() {
    return !simulation && spark.hasStickyWarning() && spark.getStickyWarnings().hasReset;
  }

  @Override
  public void clearResetFlag() {
    if (!simulation) {
      spark.clearFaults();
    }
  }

  @Override
  public boolean brownoutWarning() {
    return !simulation && spark.hasActiveWarning() && spark.getWarnings().brownout;
  }

  @Override
  public int canId() {
    return spark.getDeviceId();
  }

  private static SparkBaseConfigAccessor accessor(SparkBase s) {
    if (s instanceof SparkMax max) {
      return max.configAccessor;
    }
    if (s instanceof SparkFlex flex) {
      return flex.configAccessor;
    }
    return null;
  }

  @Override
  public boolean simulated() {
    return simulation;
  }

  @Override
  public double amps() {
    return simulation ? Double.NaN : spark.getOutputCurrent();
  }

  @Override
  public double tempC() {
    return simulation ? Double.NaN : spark.getMotorTemperature();
  }

  @Override
  public double busVolts() {
    return simulation ? Double.NaN : spark.getBusVoltage();
  }

  @Override
  public double appliedDuty() {
    return simulation ? Double.NaN : spark.getAppliedOutput();
  }

  @Override
  public double motorRotations() {
    if (simulation || positionFactor == 0) {
      return Double.NaN;
    }
    return spark.getEncoder().getPosition() / positionFactor;
  }

  @Override
  public String activeFaults() {
    if (simulation) {
      return "";
    }
    List<String> out = new ArrayList<>();
    if (spark.hasActiveFault()) {
      faults(spark.getFaults(), out);
    }
    if (spark.hasActiveWarning()) {
      // Overcurrent and stall warnings are what a current limit doing its job looks like.
      SparkBase.Warnings w = spark.getWarnings();
      if (w.brownout) out.add("brownout");
      if (w.sensor) out.add("sensor warning");
      if (w.hasReset) out.add("controller reset");
      if (w.escEeprom || w.extEeprom) out.add("EEPROM warning");
    }
    return String.join(", ", out);
  }

  @Override
  public String stickyFaults() {
    if (simulation || !spark.hasStickyFault()) {
      return "";
    }
    List<String> out = new ArrayList<>();
    faults(spark.getStickyFaults(), out);
    return String.join(", ", out);
  }

  private static void faults(SparkBase.Faults f, List<String> out) {
    if (f.sensor) out.add("sensor (encoder or hall cable)");
    if (f.motorType) out.add("motor type");
    if (f.temperature) out.add("over temperature");
    if (f.gateDriver) out.add("gate driver (a burnt phase or shorted motor lead)");
    if (f.can) out.add("CAN");
    if (f.escEeprom) out.add("EEPROM");
    if (f.firmware) out.add("firmware");
    if (f.other) out.add("other");
  }

  @Override
  public int configuredLimitA() {
    return stallLimitA;
  }

  @Override
  public Boolean coast() {
    SparkBaseConfigAccessor a = accessor(spark);
    if (simulation || a == null) {
      return null;
    }
    return a.getIdleMode() == SparkBaseConfig.IdleMode.kCoast;
  }

  @Override
  public boolean setCoast(boolean coast) {
    if (simulation) {
      return true;
    }
    SparkBaseConfig c = spark instanceof SparkFlex ? new SparkFlexConfig() : new SparkMaxConfig();
    c.idleMode(coast ? SparkBaseConfig.IdleMode.kCoast : SparkBaseConfig.IdleMode.kBrake);
    return spark.configure(c, ResetMode.kNoResetSafeParameters, PersistMode.kNoPersistParameters) == REVLibError.kOk;
  }

  @Override
  public boolean testDuty(double duty) {
    spark.set(Math.max(-1, Math.min(1, duty)));
    return true;
  }

  @Override
  public boolean testVolts(double volts) {
    // Voltage control: the SPARK scales its output by its own supply, so the motor gets these volts
    // however the battery sags (until the battery is below them).
    spark.setVoltage(Math.max(-12, Math.min(12, volts)));
    return true;
  }

  @Override
  public boolean follower() {
    return follower;
  }

  @Override
  public double appliedVolts() {
    // REVLib's simulated SPARK keeps its output and supply up to date, so these read in simulation too.
    return spark.getAppliedOutput() * spark.getBusVoltage();
  }

  @Override
  public double feedbackPosition() {
    try {
      return feedbackPos.getAsDouble();
    } catch (RuntimeException e) {
      return Double.NaN;
    }
  }

  @Override
  public double feedbackVelocity() {
    try {
      return feedbackVel.getAsDouble();
    } catch (RuntimeException e) {
      return Double.NaN;
    }
  }

  /**
   * Its closed loop's sensor, as configured: the built-in encoder, an absolute encoder, or an
   * alternate (MAX) or external (Flex) encoder. Read through REVLib's own objects, so the
   * conversion factors and the velocity filter are the ones its gains see.
   */
  private static java.util.function.DoubleSupplier[] feedback(SparkBase spark, String sensor) {
    try {
      if ("AbsoluteEncoder".equals(sensor)) {
        var e = spark.getAbsoluteEncoder();
        return new java.util.function.DoubleSupplier[] {e::getPosition, e::getVelocity};
      }
      if ("AlternateOrExternalEncoder".equals(sensor)) {
        var e = spark instanceof SparkFlex flex ? flex.getExternalEncoder() : ((SparkMax) spark).getAlternateEncoder();
        return new java.util.function.DoubleSupplier[] {e::getPosition, e::getVelocity};
      }
      var e = spark.getEncoder();
      return new java.util.function.DoubleSupplier[] {e::getPosition, e::getVelocity};
    } catch (RuntimeException e) {
      return new java.util.function.DoubleSupplier[] {() -> Double.NaN, () -> Double.NaN};
    }
  }

  /** What it sent before a test sped its signals up, to put back; null when not sped up. */
  private int[] savedSignals;

  @Override
  public synchronized boolean fastSignals(int ms) {
    if (simulation) {
      return true;
    }
    SparkBaseConfigAccessor a = accessor(spark);
    if (a == null) {
      return false;
    }
    int[] p;
    if (ms > 0) {
      if (savedSignals == null) {
        var s = a.signals;
        savedSignals = new int[] {s.getPrimaryEncoderPositionPeriodMs(), s.getPrimaryEncoderVelocityPeriodMs(),
            s.getAbsoluteEncoderPositionPeriodMs(), s.getAbsoluteEncoderVelocityPeriodMs(),
            s.getAppliedOutputPeriodMs(), s.getBusVoltagePeriodMs(), s.getOutputCurrentPeriodMs()};
      }
      boolean abs = "AbsoluteEncoder".equals(settingsMap.get("sensor"));
      p = new int[] {ms, ms, abs ? ms : savedSignals[2], abs ? ms : savedSignals[3], ms, ms, ms};
    } else if (savedSignals != null) {
      p = savedSignals;
      savedSignals = null;
    } else {
      return true;
    }
    SparkBaseConfig c = spark instanceof SparkFlex ? new SparkFlexConfig() : new SparkMaxConfig();
    c.signals.primaryEncoderPositionPeriodMs(p[0]).primaryEncoderVelocityPeriodMs(p[1])
        .absoluteEncoderPositionPeriodMs(p[2]).absoluteEncoderVelocityPeriodMs(p[3])
        .appliedOutputPeriodMs(p[4]).busVoltagePeriodMs(p[5]).outputCurrentPeriodMs(p[6]);
    return spark.configure(c, ResetMode.kNoResetSafeParameters, PersistMode.kNoPersistParameters) == REVLibError.kOk;
  }

  @Override
  public boolean setCurrentLimit(int amps) {
    if (simulation) {
      return true;
    }
    SparkBaseConfig cfg = spark instanceof SparkFlex ? new SparkFlexConfig() : new SparkMaxConfig();
    if (amps == stallLimitA) {
      cfg.smartCurrentLimit(stallLimitA, freeLimitA, limitRpm);
    } else {
      cfg.smartCurrentLimit(amps, freeLimitA == 0 ? 0 : Math.min(freeLimitA, amps), limitRpm);
    }
    return spark.configure(cfg, ResetMode.kNoResetSafeParameters, PersistMode.kNoPersistParameters)
        == REVLibError.kOk;
  }
}
