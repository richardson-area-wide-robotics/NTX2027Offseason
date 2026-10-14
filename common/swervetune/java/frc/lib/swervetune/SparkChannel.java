package frc.lib.swervetune;

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
  private final String model;
  private final String firmware;

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
  public boolean testDuty(double duty) {
    spark.set(Math.max(-1, Math.min(1, duty)));
    return true;
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
