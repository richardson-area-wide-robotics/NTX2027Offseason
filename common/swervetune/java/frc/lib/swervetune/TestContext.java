package frc.lib.swervetune;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BooleanSupplier;
import java.util.function.Supplier;

/** What a running {@link Procedure} can see and use. One per test run. */
public final class TestContext {
  public final DrivetrainIO io;
  public final TestArgs args;
  public final TestEnvironment env;
  /** Modules this run is about, by index. All modules for chassis tests. */
  public final int[] modules;
  /** Fastest any wheel may be commanded, m/s. */
  public final double speedCapMps;
  /** Clear floor ahead and to the side, metres. */
  public final double spaceForwardM;

  public final double spaceSideM;
  /** Whether AprilTag ground truth is available for this run. */
  public final boolean visionInUse;

  public final Sampler sampler;
  /** Whether the robot was enabled when the test was requested. */
  public final boolean enabledAtStart;
  /** Whether the robot is enabled now. */
  public final BooleanSupplier enabled;
  /** Vision pose {@code {x, y, deg}} when vision is in use and has one, otherwise null. */
  public final Supplier<double[]> visionPose;

  /** The team's current policy for the drive motors, amps: no test may exceed it. */
  public double drivePolicyA = 80;
  /** The drive current limit in force when the test started, amps, to put back afterwards. */
  public double driveLimitA = 40;
  /**
   * Every PDH channel's current this loop, amps, from AdvantageKit's snapshot; empty when there is
   * none (AdvantageKit not started, or no PDH on the bus).
   */
  public Supplier<double[]> pdhCurrents = () -> new double[0];

  private final Map<String, Double> meta = new LinkedHashMap<>();
  private final List<String> notes = new ArrayList<>();

  public TestContext(
      DrivetrainIO io,
      TestArgs args,
      TestEnvironment env,
      int[] modules,
      double speedCapMps,
      double spaceForwardM,
      double spaceSideM,
      boolean visionInUse,
      Sampler sampler,
      boolean enabledAtStart,
      BooleanSupplier enabled,
      Supplier<double[]> visionPose) {
    this.io = io;
    this.args = args;
    this.env = env;
    this.modules = modules;
    this.speedCapMps = speedCapMps;
    this.spaceForwardM = spaceForwardM;
    this.spaceSideM = spaceSideM;
    this.visionInUse = visionInUse;
    this.sampler = sampler;
    this.enabledAtStart = enabledAtStart;
    this.enabled = enabled;
    this.visionPose = visionPose;
  }

  /** Records a number the laptop needs to interpret the run, such as a step size or a budget. */
  public void meta(String key, double value) {
    meta.put(key, value);
  }

  /** Records a sentence for the person reading the result. */
  public void note(String text) {
    notes.add(text);
  }

  public Map<String, Double> meta() {
    return meta;
  }

  public List<String> notes() {
    return notes;
  }

  public boolean isSelected(int module) {
    for (int m : modules) {
      if (m == module) {
        return true;
      }
    }
    return false;
  }

  /** The lesser of forward and side space: what a test may use when it could go either way. */
  public double tightestSpaceM() {
    return Math.min(spaceForwardM, spaceSideM);
  }
}
