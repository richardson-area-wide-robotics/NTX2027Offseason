package frc.lib.swervetune;

import com.revrobotics.PersistMode;
import com.revrobotics.ResetMode;
import com.revrobotics.spark.SparkBase;
import com.revrobotics.spark.SparkFlex;
import com.revrobotics.spark.SparkMax;
import com.revrobotics.spark.config.SparkBaseConfig;
import com.revrobotics.spark.config.SparkBaseConfigAccessor;
import com.revrobotics.spark.config.SparkFlexConfig;
import com.revrobotics.spark.config.SparkMaxConfig;
import edu.wpi.first.wpilibj2.command.Subsystem;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import java.util.function.DoubleConsumer;
import java.util.function.DoubleSupplier;

/**
 * A mechanism the Systems tab can tune: a shooter's flywheel, an intake's pivot, an elevator. The
 * team's subsystem keeps its own control loop; it only tells the tool how to read the mechanism and
 * how to set its goal, so what gets tuned is exactly what runs in a match. Register one in the
 * subsystem, after {@link SwerveTune#install}:
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
 * {@code system_limits} test), or swervetune.json's {@code "systems"} gives them.
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
  /** Where the limits came from: "swervetune.json", or "moved by hand" this session. */
  String limitsFrom = "";
  /** The goal last set, for the laptop's live view; NaN until one is. */
  volatile double lastGoal = Double.NaN;

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

  /** A gain the tool may change live (never saved to the controller): its value, setter and range. */
  public TunableSystem gain(String name, DoubleSupplier get, DoubleConsumer set, double min, double max) {
    gains.put(name, new Gain(name, get, set, min, max));
    return this;
  }

  /**
   * The gains of a SPARK's own closed loop (slot 0): kP, kI, kD and its feedforward kS, kV, kA,
   * kG. Read back from the controller, set live and never persisted: the team's code puts its own
   * values back at the next restart, so a value to keep goes into the code.
   */
  public TunableSystem sparkGains(SparkBase spark) {
    var a = (spark instanceof SparkFlex flex ? (SparkBaseConfigAccessor) flex.configAccessor
        : ((SparkMax) spark).configAccessor).closedLoop;
    sparkGain(spark, "kP", a::getP, (c, v) -> c.closedLoop.p(v), 0, 10);
    sparkGain(spark, "kI", a::getI, (c, v) -> c.closedLoop.i(v), 0, 1);
    sparkGain(spark, "kD", a::getD, (c, v) -> c.closedLoop.d(v), 0, 50);
    sparkGain(spark, "kS", a.feedForward::getkS, (c, v) -> c.closedLoop.feedForward.kS(v), 0, 4);
    sparkGain(spark, "kV", a.feedForward::getkV, (c, v) -> c.closedLoop.feedForward.kV(v), 0, 20);
    sparkGain(spark, "kA", a.feedForward::getkA, (c, v) -> c.closedLoop.feedForward.kA(v), 0, 20);
    sparkGain(spark, "kG", a.feedForward::getkG, (c, v) -> c.closedLoop.feedForward.kG(v), -12, 12);
    return this;
  }

  private interface ConfigEdit {
    void edit(SparkBaseConfig c, double v);
  }

  private void sparkGain(SparkBase spark, String name, DoubleSupplier get, ConfigEdit edit, double min, double max) {
    gain(name, get, v -> {
      SparkBaseConfig c = spark instanceof SparkFlex ? new SparkFlexConfig() : new SparkMaxConfig();
      edit.edit(c, v);
      spark.configure(c, ResetMode.kNoResetSafeParameters, PersistMode.kNoPersistParameters);
    }, min, max);
  }

  /** Limits from a person moving it by hand, or from swervetune.json. */
  void setLimits(double lo, double hi, String from) {
    min = Math.min(lo, hi);
    max = Math.max(lo, hi);
    limitsFrom = from;
  }

  boolean hasLimits() {
    return Double.isFinite(min) && Double.isFinite(max) && max > min;
  }

  /** Applies {@code each} to every gain; for tests. */
  void forEachGain(Consumer<Gain> each) {
    gains.values().forEach(each);
  }
}
