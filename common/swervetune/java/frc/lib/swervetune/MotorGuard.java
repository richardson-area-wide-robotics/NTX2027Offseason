package frc.lib.swervetune;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

/**
 * Watches every registered motor for heat, stalls and failure, and steps in before one burns out.
 *
 * <p>Three independent judges, and the worst one wins:
 *
 * <ul>
 *   <li><b>Heat model</b> - winding heat estimated from current ({@link MotorKind}). The only judge
 *       fast enough for a NEO 550, whose sensor lags its windings by tens of seconds.
 *   <li><b>Sensor temperature</b> - the SPARK's reading, a slow second opinion.
 *   <li><b>Stall timer</b> - at the current limit with the shaft barely turning: what a jam or a
 *       wedged mechanism produces. Not applied to drive motors, which stall in every pushing
 *       match; the heat model judges those.
 * </ul>
 *
 * <p>Stages, applied only when the stage changes and never saved to flash: <b>WARN</b> reports it;
 * <b>DERATE</b> halves the current limit; <b>SHUTOFF</b> drops it to 2 A, which leaves the motor
 * effectively off. Stepping back down needs the temperature 10 &deg;C and the heat estimate 10
 * points below the threshold, and a stall timer that has run all the way back to zero, so a motor
 * does not flicker between stages. While derated, the lower limit is re-sent every two seconds:
 * YAGSL re-sends its own whole configuration at times (brake mode, flash saves), which would
 * silently put the full limit back.
 *
 * <p><b>Overrides</b> are for a match where losing the motor costs more than the motor: they hold a
 * motor at DERATE instead of SHUTOFF for at most {@value #MAX_OVERRIDE_S} seconds. They never lift
 * the stall timer, and never hold off a sensor 10 &deg;C past shutoff or a heat estimate past 95% -
 * beyond those the motor is being destroyed anyway.
 *
 * <p>It also reports failures it cannot fix: output with no current (unplugged power, an open
 * phase, a burnt winding), a temperature sensor reading nonsense, and controller faults.
 *
 * <p>Free of WPILib and REVLib, so it is tested on a laptop with fake motors.
 */
public final class MotorGuard {
  /** How worried to be. Order matters: later is worse. */
  public enum Stage {
    OK,
    WARN,
    DERATE,
    SHUTOFF
  }

  /** Everything the guard needs from one motor controller. NaN means "not known". */
  public interface MotorChannel {
    double amps();

    double tempC();

    /** Applied output, -1 to 1. */
    double appliedDuty();

    /** Motor shaft rotations, before any gearing or conversion factor. */
    double motorRotations();

    /** Active faults, comma separated; empty when healthy. */
    String activeFaults();

    /** Faults since the last clear, comma separated. */
    String stickyFaults();

    /** The smart current limit configured when the guard starts, amps; 0 if unknown. */
    int configuredLimitA();

    /** Changes the smart current limit, never saved to flash. False if the controller refused. */
    boolean setCurrentLimit(int amps);

    /**
     * The supply voltage at the controller's own terminals. Compared with the PDH's voltage under
     * load, it shows the resistance of that controller's power wiring: a loose connection shows up
     * as a sag only that controller sees.
     */
    default double busVolts() {
      return Double.NaN;
    }

    /** Whether the controller is being heard on the CAN bus right now. */
    default boolean canPresent() {
      return true;
    }

    /** Whether the controller has rebooted - lost power, however briefly - since the flag was cleared. */
    default boolean resetSeen() {
      return false;
    }

    default void clearResetFlag() {}

    /** Whether the controller is warning of a low supply voltage right now. */
    default boolean brownoutWarning() {
      return false;
    }

    /** CAN ID, or -1 if unknown. */
    default int canId() {
      return -1;
    }

    /** What the controller itself says it is ("SPARK MAX", "SPARK Flex"); empty if it can't say. */
    default String controllerModel() {
      return "";
    }

    /** What the code created it as ("SPARK MAX", "SPARK Flex"); empty if unknown. */
    default String controllerClass() {
      return "";
    }

    /** The controller's firmware version; empty if unknown. */
    default String firmware() {
      return "";
    }

    /** True in simulation, where a controller has no real current or temperature to report. */
    default boolean simulated() {
      return false;
    }
  }

  /** One registered motor and what the guard knows about it. */
  public static final class Motor {
    public final String name;
    public final MotorKind kind;
    final MotorChannel channel;
    final boolean stallTimer;
    int baseLimitA;
    int activeLimitA;
    double riseC;
    double stallS;
    Stage stallLatch = Stage.OK;
    double noCurrentS;
    double lastRotations = Double.NaN;
    double rpm;
    Stage stage = Stage.OK;
    String cause = "";
    String flags = "";
    double overrideUntilS = Double.NEGATIVE_INFINITY;
    double lastLimitSendS = Double.NEGATIVE_INFINITY;
    double tempC = Double.NaN;
    double amps = Double.NaN;
    double busVolts = Double.NaN;
    boolean present = true;
    int dropouts;
    double lastDropS = Double.NEGATIVE_INFINITY;
    int resets;
    double lastResetS = Double.NEGATIVE_INFINITY;
    int brownouts;
    boolean brownout;

    Motor(String name, MotorKind kind, MotorChannel channel, boolean stallTimer) {
      this.name = name;
      this.kind = kind;
      this.channel = channel;
      this.stallTimer = stallTimer;
    }

    /** Estimated winding heat as a fraction of what burns it out: 0 cold, 1 failing. */
    public double heatFraction() {
      return riseC / MotorKind.FAILURE_RISE_C;
    }

    public Stage stage() {
      return stage;
    }

    /** Why it is at its stage, e.g. {@code "heat estimate 74%"}; empty when OK. */
    public String cause() {
      return cause;
    }

    /** Failures the guard cannot fix, e.g. an unplugged motor; empty when none. */
    public String flags() {
      return flags;
    }

    public double tempC() {
      return tempC;
    }

    public double amps() {
      return amps;
    }

    /** Whether it is heard on the CAN bus now. */
    public boolean present() {
      return present;
    }

    /** Times it has dropped off the CAN bus since the robot code started. */
    public int dropouts() {
      return dropouts;
    }

    public double lastDropS() {
      return lastDropS;
    }

    /** Times it has rebooted - lost power - since the robot code started. */
    public int resets() {
      return resets;
    }

    public double lastResetS() {
      return lastResetS;
    }

    /** Times it has warned of a low supply voltage. */
    public int brownouts() {
      return brownouts;
    }

    public int canId() {
      return channel.canId();
    }

    /** What the controller says it is; empty if it can't say. */
    public String controllerModel() {
      return channel.controllerModel();
    }

    /** What the code created it as. */
    public String controllerClass() {
      return channel.controllerClass();
    }

    public String firmware() {
      return channel.firmware();
    }

    /** Supply voltage at the controller, volts; NaN if unknown. */
    public double busVolts() {
      return busVolts;
    }

    public double stallSeconds() {
      return stallS;
    }

    public int baseLimitA() {
      return baseLimitA;
    }

    public int activeLimitA() {
      return activeLimitA;
    }

    public double overrideRemainingS(double nowS) {
      return Math.max(0, overrideUntilS - nowS);
    }
  }

  public static final double HYSTERESIS_C = 10;
  public static final double HYSTERESIS_HEAT = 0.10;
  public static final double MAX_OVERRIDE_S = 20;
  public static final int SHUTOFF_LIMIT_A = 2;
  static final double WARN_HEAT = 0.50;
  static final double DERATE_HEAT = 0.70;
  static final double SHUTOFF_HEAT = 0.85;
  static final double NO_OVERRIDE_HEAT = 0.95;
  static final double RESEND_S = 2.0;
  private static final int MAX_EVENTS = 20;

  private final Map<String, Motor> motors = new LinkedHashMap<>();
  private final List<String> report = new ArrayList<>();
  private final Deque<String> events = new ArrayDeque<>();
  private Consumer<String> alerts = s -> {};
  private double lastNowS = Double.NaN;
  private long eventCount;

  /** Where stage changes are announced as they happen, e.g. the Driver Station. */
  public void setAlertSink(Consumer<String> sink) {
    this.alerts = sink == null ? s -> {} : sink;
  }

  /**
   * Starts watching a motor.
   *
   * @param name unique, shown to students, e.g. {@code "Shooter left"}
   * @param enforcePolicy if the controller's current limit is above the team's policy for this kind
   *     of motor, lower it to the policy (not saved to flash) and say so
   */
  public Motor register(String name, MotorChannel channel, MotorKind kind, boolean enforcePolicy) {
    return register(name, channel, kind, enforcePolicy, true);
  }

  /**
   * Starts watching a motor, choosing whether the stall timer applies.
   *
   * @param stallTimer false for a drive motor: a robot stalls its drive motors in every pushing
   *     match, and cutting them for that would lose the match. The heat model and the sensor still
   *     protect it.
   */
  public Motor register(String name, MotorChannel channel, MotorKind kind, boolean enforcePolicy,
      boolean stallTimer) {
    if (motors.containsKey(name)) {
      throw new IllegalArgumentException("A motor called " + name + " is already registered");
    }
    Motor m = new Motor(name, kind, channel, stallTimer);
    int configured = channel.configuredLimitA();
    m.baseLimitA = configured > 0 ? configured : kind.policyAmps;
    if (channel.simulated()) {
      m.baseLimitA = kind.policyAmps;
    } else if (configured <= 0) {
      report.add(String.format("%s (%s): could not read its current limit; assuming the %d A policy.",
          name, kind.label, kind.policyAmps));
    } else if (configured > kind.policyAmps) {
      if (enforcePolicy && channel.setCurrentLimit(kind.policyAmps)) {
        report.add(String.format("%s (%s): current limit %d A is over the %d A policy; lowered to %d A"
            + " until reboot. Set it in the code to make this permanent.", name, kind.label,
            configured, kind.policyAmps, kind.policyAmps));
        m.baseLimitA = kind.policyAmps;
      } else {
        report.add(String.format("%s (%s): current limit %d A is over the %d A policy.", name,
            kind.label, configured, kind.policyAmps));
      }
    }
    m.activeLimitA = m.baseLimitA;
    motors.put(name, m);
    return m;
  }

  /** What registration found and changed, for the startup report. */
  public List<String> report() {
    return List.copyOf(report);
  }

  /** Adds a line to the startup report. */
  public void note(String line) {
    report.add(line);
  }

  /** How many events there have ever been, so a publisher can tell when to re-send them. */
  public long eventCount() {
    return eventCount;
  }

  /** Stage changes, newest last, at most twenty. */
  public List<String> events() {
    return List.copyOf(events);
  }

  public List<Motor> motors() {
    return List.copyOf(motors.values());
  }

  public Motor motor(String name) {
    return motors.get(name);
  }

  /**
   * Holds one motor, or every motor with {@code "ALL"}, at DERATE instead of SHUTOFF for a while.
   * Zero seconds cancels.
   *
   * @return what happened, for the person who asked
   */
  public String override(String name, double seconds, double nowS) {
    double s = Math.max(0, Math.min(MAX_OVERRIDE_S, seconds));
    List<Motor> targets = "ALL".equalsIgnoreCase(name)
        ? List.copyOf(motors.values())
        : motors.containsKey(name) ? List.of(motors.get(name)) : List.of();
    if (targets.isEmpty()) {
      return "No motor called " + name + ".";
    }
    for (Motor m : targets) {
      m.overrideUntilS = nowS + s;
    }
    String who = targets.size() == 1 ? targets.get(0).name : "every motor";
    String text = s == 0
        ? "Thermal override canceled for " + who + "."
        : String.format("Thermal override for %s: %.0f s. Heat shutoffs are held at half current;"
            + " stalls still cut out.", who, s);
    event(nowS, text);
    return text;
  }

  /** Call every robot loop. */
  public void update(double nowS) {
    double dt = Double.isNaN(lastNowS) ? 0.02 : Math.max(0, Math.min(0.2, nowS - lastNowS));
    lastNowS = nowS;
    for (Motor m : motors.values()) {
      step(m, nowS, dt);
    }
  }

  /** The motor at the worst stage among those named, or null if none of them are registered. */
  public Motor worst(List<String> names) {
    Motor worst = null;
    for (String n : names) {
      Motor m = motors.get(n);
      if (m != null && (worst == null || m.stage.ordinal() > worst.stage.ordinal())) {
        worst = m;
      }
    }
    return worst;
  }

  private void step(Motor m, double nowS, double dt) {
    MotorKind k = m.kind;
    // Wiring: is it still on the bus, has it rebooted, is its supply sagging?
    boolean present = m.channel.canPresent();
    if (m.present && !present) {
      m.dropouts++;
      m.lastDropS = nowS;
      event(nowS, m.name + " dropped off the CAN bus. Check its CAN plugs and the cable before it.");
    } else if (!m.present && present) {
      event(nowS, m.name + " is back on the CAN bus.");
    }
    m.present = present;
    if (!present) {
      // Its readings are frozen at the last frame heard: judge nothing from them.
      m.amps = Double.NaN;
      m.lastRotations = Double.NaN;
      m.flags = "not heard on the CAN bus";
      return;
    }
    if (m.channel.resetSeen()) {
      m.resets++;
      m.lastResetS = nowS;
      m.channel.clearResetFlag();
      event(nowS, m.name + " rebooted: it lost power for a moment. Check its power leads, the PDH"
          + " port and its breaker.");
    }
    boolean bo = m.channel.brownoutWarning();
    if (bo && !m.brownout) {
      m.brownouts++;
    }
    m.brownout = bo;
    double amps = m.channel.amps();
    double temp = m.channel.tempC();
    double duty = m.channel.appliedDuty();
    double rot = m.channel.motorRotations();
    m.amps = amps;
    m.tempC = temp;
    m.busVolts = m.channel.busVolts();
    if (Double.isFinite(rot) && Double.isFinite(m.lastRotations) && dt > 0) {
      m.rpm = (rot - m.lastRotations) / dt * 60.0;
    }
    m.lastRotations = rot;
    boolean turning = Math.abs(m.rpm) > 0.05 * k.freeRpm;

    // Heat model: rise' = (k I^2 - rise) / tau.
    if (Double.isFinite(amps)) {
      m.riseC += (k.kRisePerAmp2 * amps * amps - m.riseC) * dt / k.tauS;
      m.riseC = Math.max(0, m.riseC);
    }
    double heat = m.heatFraction();

    // Stall timer: pushing at whatever limit is in force with the shaft barely turning. Runs at
    // full rate at the full limit, half rate when derated (a quarter of the heat), and holds while
    // shut off and still being driven into the jam; it only runs down once the push stops.
    boolean pushing = Double.isFinite(amps) && amps >= 0.8 * m.activeLimitA && !turning;
    if (!m.stallTimer) {
      m.stallS = 0;
    } else if (pushing) {
      m.stallS += m.activeLimitA >= m.baseLimitA ? dt : m.activeLimitA > SHUTOFF_LIMIT_A ? dt / 2 : 0;
    } else {
      m.stallS = Math.max(0, m.stallS - dt);
    }
    Stage stallNow = m.stallS >= k.stallCutS ? Stage.SHUTOFF
        : m.stallS >= k.stallCutS / 3 ? Stage.DERATE
        : m.stallS >= 3 ? Stage.WARN : Stage.OK;
    m.stallLatch = m.stallS == 0 ? Stage.OK : max(m.stallLatch, stallNow);

    Stage sensor = sensorStage(k, temp, 0);
    Stage model = heatStage(heat, 0);
    Stage target = max(sensor, max(model, m.stallLatch));

    // Step down only once comfortably clear of the stage being left.
    if (target.ordinal() < m.stage.ordinal()) {
      Stage cool = max(max(sensorStage(k, temp, HYSTERESIS_C), heatStage(heat, HYSTERESIS_HEAT)),
          m.stallLatch);
      target = cool.ordinal() < m.stage.ordinal() ? cool : m.stage;
    }

    // An override holds a heat SHUTOFF at DERATE, within absolute limits; never a stall.
    boolean overriding = nowS < m.overrideUntilS;
    boolean beyondSaving = (Double.isFinite(temp) && temp >= k.shutoffC + HYSTERESIS_C)
        || heat >= NO_OVERRIDE_HEAT;
    boolean held = false;
    if (overriding && target == Stage.SHUTOFF && m.stallLatch != Stage.SHUTOFF && !beyondSaving) {
      target = Stage.DERATE;
      held = true;
    }

    String cause = describe(m, target, sensor, model, temp, heat);
    if (held) {
      cause += String.format(" - override holding it on for %.0f s more", m.overrideUntilS - nowS);
    }

    int limit = switch (target) {
      case OK, WARN -> m.baseLimitA;
      case DERATE -> Math.max(SHUTOFF_LIMIT_A, m.baseLimitA / 2);
      case SHUTOFF -> SHUTOFF_LIMIT_A;
    };
    // Send at once on a stage change; retry a refused send twice a second, not every loop
    // (each send is a blocking CAN transaction); and re-send a lowered limit every two seconds.
    double sinceSend = nowS - m.lastLimitSendS;
    boolean send = (limit != m.activeLimitA && (target != m.stage || sinceSend >= 0.5))
        || (limit != m.baseLimitA && sinceSend >= RESEND_S);
    if (send) {
      if (m.channel.setCurrentLimit(limit)) {
        m.activeLimitA = limit;
      }
      m.lastLimitSendS = nowS;
    }
    if (target != m.stage) {
      String verb = target.ordinal() > m.stage.ordinal() ? "up" : "down";
      event(nowS, String.format("%s %s %s -> %s: %s; limit %d A", m.name, verb, m.stage, target,
          cause.isEmpty() ? "cooled" : cause, m.activeLimitA));
      m.stage = target;
    }
    m.cause = cause;

    // Failures the guard can only report.
    List<String> flags = new ArrayList<>();
    boolean noCurrent = Math.abs(duty) > 0.25 && Double.isFinite(amps) && amps < 0.5 && !turning;
    m.noCurrentS = noCurrent ? m.noCurrentS + dt : 0;
    if (m.noCurrentS > 0.5) {
      flags.add("output but no current: unplugged power, an open phase or a burnt winding");
    }
    if (Double.isFinite(temp) && (temp <= 0 || temp >= 150)) {
      flags.add(String.format("temperature sensor reads %.0f C: unplugged or faulty", temp));
    }
    String active = m.channel.activeFaults();
    if (active != null && !active.isEmpty()) {
      flags.add("faults: " + active);
    }
    String sticky = m.channel.stickyFaults();
    if (sticky != null && !sticky.isEmpty()) {
      flags.add("since last cleared: " + sticky);
    }
    String isA = m.channel.controllerModel();
    String cls = m.channel.controllerClass();
    if (isA != null && cls != null && !isA.isEmpty() && !cls.isEmpty() && !isA.equals(cls)) {
      flags.add("is a " + isA + " but the code created a " + cls
          + ": create it as new " + javaClass(isA) + "(...), or for a swerve motor fix the YAGSL type");
    }
    m.flags = String.join("; ", flags);
  }

  private static String describe(Motor m, Stage target, Stage sensor, Stage model, double temp,
      double heat) {
    if (target == Stage.OK) {
      return "";
    }
    List<String> why = new ArrayList<>();
    if (m.stallLatch.ordinal() >= Stage.WARN.ordinal()) {
      why.add(String.format("stalled %.0f s", m.stallS));
    }
    if (model.ordinal() >= Stage.WARN.ordinal() || heat >= WARN_HEAT - HYSTERESIS_HEAT) {
      why.add(String.format("heat estimate %.0f%%", 100 * heat));
    }
    if (sensor.ordinal() >= Stage.WARN.ordinal()
        || (Double.isFinite(temp) && temp >= m.kind.warnC - HYSTERESIS_C)) {
      why.add(String.format("sensor %.0f C", temp));
    }
    String text = String.join(", ", why);
    boolean cooling = target.ordinal() > max(sensor, max(model, m.stallLatch)).ordinal();
    return cooling ? "cooling: " + text : text;
  }

  private static Stage sensorStage(MotorKind k, double temp, double margin) {
    if (!Double.isFinite(temp)) {
      return Stage.OK;
    }
    double t = temp + margin;
    return t >= k.shutoffC ? Stage.SHUTOFF : t >= k.derateC ? Stage.DERATE
        : t >= k.warnC ? Stage.WARN : Stage.OK;
  }

  private static Stage heatStage(double heat, double margin) {
    double h = heat + margin;
    return h >= SHUTOFF_HEAT ? Stage.SHUTOFF : h >= DERATE_HEAT ? Stage.DERATE
        : h >= WARN_HEAT ? Stage.WARN : Stage.OK;
  }

  private void event(double nowS, String text) {
    String line = String.format("%.1f s  %s", nowS, text);
    events.addLast(line);
    eventCount++;
    while (events.size() > MAX_EVENTS) {
      events.removeFirst();
    }
    alerts.accept(text);
  }

  private static Stage max(Stage a, Stage b) {
    return a.ordinal() >= b.ordinal() ? a : b;
  }

  /** The REVLib class for a controller model: "SPARK Flex" is {@code SparkFlex}, else {@code SparkMax}. */
  static String javaClass(String model) {
    return "SPARK Flex".equals(model) ? "SparkFlex" : "SparkMax";
  }
}
