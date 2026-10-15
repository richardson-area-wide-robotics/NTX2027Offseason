package frc.lib.slothtune;

import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkBase;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig;
import com.revrobotics.spark.config.SparkBaseConfigAccessor;
import com.revrobotics.spark.config.SparkFlexConfig;
import com.revrobotics.spark.config.SparkMaxConfig;
import edu.wpi.first.math.util.Units;
import edu.wpi.first.wpilibj2.command.Subsystem;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Consumer;
import java.util.function.DoubleConsumer;
import java.util.function.DoubleSupplier;

/**
 * A mechanism the Systems tab can tune: a shooter's flywheel, an intake's pivot, an elevator. The
 * team's subsystem keeps its own control loop; it only tells the tool how to read the mechanism and
 * how to set its goal, so what gets tuned is exactly what runs in a match. Register one in the
 * subsystem, after {@link SlothTune#install}:
 *
 * <pre>
 *   tune.system("Intake pivot", TunableSystem.Kind.PIVOT)
 *       .units("motor rotations")
 *       .position(encoder::getPosition)
 *       .velocity(() -&gt; encoder.getVelocity() / 60)
 *       .goal(p -&gt; target = p)
 *       .stop(() -&gt; target = encoder.getPosition())
 *       .subsystem(this)
 *       .motors("Intake pivot")
 *       .sparkGains(pivotMotor);
 * </pre>
 *
 * <p>While a test runs the tool holds {@link #subsystem} (its default command stops) but its
 * {@code periodic()} keeps running, so a loop computed there keeps working. A position mechanism
 * is never tested until its limits are known: a person moves it by hand to both ends first (the
 * {@code system_limits} test), or slothtune.json's {@code "systems"} gives them.
 */
public final class TunableSystem {
  /** What kind of motion: a position mechanism needs limits before anything moves it. */
  public enum Kind {
    FLYWHEEL(false), ROLLER(false), PIVOT(true), ELEVATOR(true);

    final boolean positional;

    Kind(boolean positional) {
      this.positional = positional;
    }
  }

  /** A gain the tool may change live, never persisted: what reads it, what sets it, its range. */
  record Gain(String name, DoubleSupplier get, DoubleConsumer set, double min, double max) {}

  final String name;
  final Kind kind;
  String units = "";
  DoubleSupplier position = () -> Double.NaN;
  DoubleSupplier velocity = () -> Double.NaN;
  DoubleConsumer goal;
  Runnable stop;
  Subsystem subsystem;
  final List<String> motors = new ArrayList<>();
  final Map<String, Gain> gains = new LinkedHashMap<>();
  /** Limits in the mechanism's own units; NaN until known. Velocity in units per second. */
  volatile double min = Double.NaN;
  volatile double max = Double.NaN;
  double maxVelocity = Double.NaN;
  double maxAccel = Double.NaN;
  /** Where the limits came from: "slothtune.json", or "moved by hand" this session. */
  String limitsFrom = "";
  /** The goal last set, for the laptop's live view; NaN until one is. */
  volatile double lastGoal = Double.NaN;
  /** Gains saved in slothtune.json (the Systems tab's Save), applied as each is declared. */
  Map<String, Double> saved = Map.of();
  /** Where a line about a saved gain goes: the robot's startup report. */
  Consumer<String> report = line -> {};
  /** The SPARK whose closed loop {@link #sparkGains} tunes; null when the code tunes its own loop. */
  SparkBase spark;
  /**
   * The closed-loop mode the code last ran that SPARK in ("Position", "MAXMotionPosition",
   * "Velocity", ...): REV applies kV and kA only in some, so the tuner computes for this one.
   * Empty until seen; not changed while a test runs the motor itself.
   */
  volatile String control = "";

  TunableSystem(String name, Kind kind) {
    this.name = name;
    this.kind = kind;
  }

  /** The units the mechanism's position (or speed, for a flywheel) is read in: "RPM", "degrees". */
  public TunableSystem units(String units) {
    this.units = units;
    return this;
  }

  /** Where it is now, in its units. Needed for a pivot or elevator. */
  public TunableSystem position(DoubleSupplier position) {
    this.position = position;
    return this;
  }

  /** How fast it is moving: units per second, or for a flywheel its speed in its units. */
  public TunableSystem velocity(DoubleSupplier velocity) {
    this.velocity = velocity;
    return this;
  }

  /** Sets its goal through the subsystem's own loop: a position, or for a flywheel a speed. */
  public TunableSystem goal(DoubleConsumer goal) {
    this.goal = v -> {
      lastGoal = v;
      goal.accept(v);
    };
    return this;
  }

  /** What stopping means for it: a pivot holds where it is, a flywheel coasts down. */
  public TunableSystem stop(Runnable stop) {
    this.stop = stop;
    return this;
  }

  /** The subsystem that owns it, held while a test runs. */
  public TunableSystem subsystem(Subsystem subsystem) {
    this.subsystem = subsystem;
    return this;
  }

  /** Its motors, by the names the motor guard watches them under: their current is recorded. */
  public TunableSystem motors(String... names) {
    motors.addAll(List.of(names));
    return this;
  }

  /**
   * A gain the tool may change live (never saved to the controller): its value, setter and range.
   * A value for it in slothtune.json's {@code systems.<name>.gains} (the Systems tab's Save) is set
   * here, as the robot starts, and said in the startup report; one outside the range is skipped.
   */
  public TunableSystem gain(String name, DoubleSupplier get, DoubleConsumer set, double min, double max) {
    gains.put(name, new Gain(name, get, set, min, max));
    Double v = saved.get(name);
    if (v != null) {
      if ((Double.isNaN(min) || v >= min) && (Double.isNaN(max) || v <= max)) {
        set.accept(v);
        report.accept(String.format(Locale.ROOT, "%s: %s %s from slothtune.json", this.name, name, num(v)));
      } else {
        report.accept(String.format(Locale.ROOT, "%s: %s %s in slothtune.json is outside %s to %s, so not applied",
            this.name, name, num(v), num(min), num(max)));
      }
    }
    return this;
  }

  private static String num(double v) {
    return String.format(Locale.ROOT, "%.6g", v).replaceAll("(\\.\\d*?)0+(e|$)", "$1$2").replace(".e", "e")
        .replaceAll("\\.$", "");
  }

  /**
   * The gains of a SPARK's own closed loop (slot 0): kP, kI, kD and its feedforward kS, kV, kA,
   * kG. Read back from the controller, set live and never persisted to it: at the next restart the
   * code's own values come back, then any saved in slothtune.json (see {@link #gain}).
   */
  public TunableSystem sparkGains(SparkBase spark) {
    this.spark = spark;
    SparkBaseConfigAccessor all = spark instanceof SparkFlex flex ? flex.configAccessor
        : ((SparkMax) spark).configAccessor;
    var a = all.closedLoop;
    // Wide: their size depends on the code's units (an elevator in meters wants a kP far above one in
    // motor rotations) and REV's kD and kI are per millisecond; the tuner keeps every change sane.
    sparkGain(spark, "kP", a::getP, (c, v) -> c.closedLoop.p(v), 0, 1000);
    sparkGain(spark, "kI", a::getI, (c, v) -> c.closedLoop.i(v), 0, 100);
    sparkGain(spark, "kD", a::getD, (c, v) -> c.closedLoop.d(v), 0, 100000);
    sparkGain(spark, "kS", a.feedForward::getkS, (c, v) -> c.closedLoop.feedForward.kS(v), 0, 4);
    sparkGain(spark, "kV", a.feedForward::getkV, (c, v) -> c.closedLoop.feedForward.kV(v), 0, 20);
    sparkGain(spark, "kA", a.feedForward::getkA, (c, v) -> c.closedLoop.feedForward.kA(v), 0, 20);
    sparkGain(spark, "kG", a.feedForward::getkG, (c, v) -> c.closedLoop.feedForward.kG(v), -12, 12);
    // An arm's gravity: volts at horizontal, scaled by the cosine of its angle (kCosRatio sets the units).
    sparkGain(spark, "kCos", a.feedForward::getkCos, (c, v) -> c.closedLoop.feedForward.kCos(v), -12, 12);
    // MAXMotion's profile: cruise speed and acceleration, in the SPARK's speed units (and per second).
    sparkGain(spark, "mmCruise", a.maxMotion::getCruiseVelocity, (c, v) -> c.closedLoop.maxMotion.cruiseVelocity(v), 0, 1e6);
    sparkGain(spark, "mmAccel", a.maxMotion::getMaxAcceleration, (c, v) -> c.closedLoop.maxMotion.maxAcceleration(v), 0, 1e7);
    // Voltage compensation: its output scaled to this many volts whatever the battery holds; 0 is off.
    sparkGain(spark, "vComp", () -> all.getVoltageCompensationEnabled() ? all.getVoltageCompensation() : 0,
        (c, v) -> {
          if (v > 0) {
            c.voltageCompensation(v);
          } else {
            c.disableVoltageCompensation();
          }
        }, 0, 13);
    // Its speed filter: a window of positions (ms), then an average of that many windows. A Flex's
    // built-in encoder is quadrature (windows every ms, overlapping: about (ms + depth) / 2 ms late);
    // a SPARK MAX's NEO is read by its hall sensors (windows end to end: about ms x depth / 2 late).
    if (spark instanceof SparkFlex) {
      sparkGain(spark, "velMs", () -> all.encoder.getQuadratureMeasurementPeriod(),
          (c, v) -> c.encoder.quadratureMeasurementPeriod((int) Math.round(v)), 1, 100);
      sparkGain(spark, "velDepth", () -> all.encoder.getQuadratureAverageDepth(),
          (c, v) -> c.encoder.quadratureAverageDepth((int) Math.round(v)), 1, 64);
    } else {
      sparkGain(spark, "velMs", () -> all.encoder.getUvwMeasurementPeriod(),
          (c, v) -> c.encoder.uvwMeasurementPeriod((int) Math.round(v)), 8, 64);
      sparkGain(spark, "velDepth", () -> all.encoder.getUvwAverageDepth(),
          (c, v) -> c.encoder.uvwAverageDepth(powerOfTwo(v)), 1, 8);
    }
    return this;
  }

  /** A hall sensor's average depth must be 1, 2, 4 or 8: the nearest. */
  static int powerOfTwo(double v) {
    int best = 1;
    for (int d : new int[] {1, 2, 4, 8}) {
      if (Math.abs(d - v) < Math.abs(best - v)) {
        best = d;
      }
    }
    return best;
  }

  /**
   * Notes the mode the code runs its SPARK in; called while no test is running it. A closed loop,
   * once seen, stays: a shooter idles at duty cycle 0 between shots and runs its velocity loop when
   * it shoots, and the velocity loop is the one to tune. Open loop only until a closed loop is seen.
   */
  void noteControl() {
    if (spark == null) {
      return;
    }
    try {
      var t = spark.getClosedLoopController().getControlType();
      if (t != null) {
        String name = t.name().replaceFirst("^k", "");
        boolean open = name.equals("DutyCycle") || name.equals("Voltage");
        if (!open || control.isEmpty() || control.equals("DutyCycle") || control.equals("Voltage")) {
          control = name;
        }
      }
    } catch (RuntimeException e) {
      // It won't say: keep what was seen.
    }
  }

  private interface ConfigEdit {
    void edit(SparkBaseConfig c, double v);
  }

  private void sparkGain(SparkBase spark, String name, DoubleSupplier get, ConfigEdit edit, double min, double max) {
    gain(name, get, v -> {
      SparkBaseConfig c = spark instanceof SparkFlex ? new SparkFlexConfig() : new SparkMaxConfig();
      edit.edit(c, v);
      spark.configure(c, ResetMode.kNoResetSafeParameters, PersistMode.kNoPersistParameters);
      SparkChannel.note(spark, name, v);
    }, min, max);
  }

  /** Limits from a person moving it by hand, or from slothtune.json. */
  void setLimits(double lo, double hi, String from) {
    min = Math.min(lo, hi);
    max = Math.max(lo, hi);
    limitsFrom = from;
  }

  boolean hasLimits() {
    return Double.isFinite(min) && Double.isFinite(max) && max > min;
  }

  /**
   * The unit a person reads this mechanism's numbers in: the team's (inches, ft/s, degrees,
   * pounds, foot-pounds) for one read in meters, radians, kilograms or newton-meters, its own
   * otherwise (RPM, motor rotations, degrees). Only the words convert: its goal, limits and every
   * recorded number stay in its own units. tools/slothtune/units.py's system_unit is the laptop's
   * twin of this.
   */
  String shownUnits() {
    return shownUnit().label();
  }

  /** A value in its own units (or its units per second), in {@link #shownUnits()}. */
  double shown(double v) {
    return v * shownUnit().factor();
  }

  private record Shown(String label, double factor) {}

  private Shown shownUnit() {
    String u = units == null ? "" : units.trim().toLowerCase(Locale.ROOT);
    return switch (u) {
      case "m", "meter", "meters", "metre", "metres" -> new Shown("in", Units.metersToInches(1));
      case "m/s", "mps", "meters per second" -> new Shown("ft/s", Units.metersToFeet(1));
      case "cm", "centimeters" -> new Shown("in", Units.metersToInches(0.01));
      case "mm", "millimeters" -> new Shown("in", Units.metersToInches(0.001));
      case "rad", "radian", "radians" -> new Shown("deg", Units.radiansToDegrees(1));
      case "rad/s", "radians per second" -> new Shown("deg/s", Units.radiansToDegrees(1));
      case "kg", "kilograms" -> new Shown("lb", Units.kilogramsToLbs(1));
      case "nm", "n*m", "n-m", "n\u00b7m", "newton meters" -> new Shown("ft-lb", 1 / 1.3558179483);
      default -> new Shown(units == null ? "" : units, 1);
    };
  }

  /** Applies {@code each} to every gain; for tests. */
  void forEachGain(Consumer<Gain> each) {
    gains.values().forEach(each);
  }
}
