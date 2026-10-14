package frc.lib.slothtune;

import edu.wpi.first.math.util.Units;

/**
 * Decides whether a camera pose is believable, and how much to trust it.
 *
 * <p>Ported from the 2026 robot's vision subsystem, where every gate came from a failure that
 * would otherwise have been fused into the pose estimate and reported with confidence. A wrong
 * vision pose is worse than none: the estimator believes it, so the robot drives precisely to the
 * wrong place. Every rejection says why, so a bad camera transform shows up as a climbing rejection
 * count with a reason, not as a robot that wanders.
 *
 * <p>Robot code can use this too, before {@code swerveDrive.addVisionMeasurement(...)}: the same
 * rules then guard both the tools' ground truth and the match pose estimate.
 */
public final class VisionGate {
  /** Thresholds. Defaults are the 2026 robot's, plus PhotonVision's own guidance. */
  public static final class Limits {
    /** Older than this and the frame no longer describes where the robot is, seconds. */
    public double maxAgeS = 0.5;
    /** Single tags are trusted only this close; error grows with distance squared, meters. */
    public double maxSingleTagDistanceM = 4.0;
    /** Multi-tag solves are constrained enough to use further out, meters. */
    public double maxMultiTagDistanceM = 6.0;
    /** A lone tag above this ambiguity has two valid solutions; PhotonVision's own figure. */
    public double maxSingleTagAmbiguity = 0.2;
    /** A solve this far above or below the floor is wrong, meters. */
    public double maxZErrorM = 0.4;
    /** Field size, meters. 2026 REBUILT is 16.54 x 8.07. */
    public double fieldLengthM = 16.54;

    public double fieldWidthM = 8.07;
    /** How far outside the perimeter a pose may land and still be believed, meters. */
    public double fieldMarginM = 0.5;
    /** A single tag claiming a bigger jump than this is likelier a misread ID than a teleport. */
    public double maxSingleTagJumpM = 1.5;
    /** Translational std dev for one tag at 1 m, meters; scaled by distance squared. */
    public double singleTagXyStdDevM = 0.35;
    /** Rotational std dev for one tag at 1 m, radians. */
    public double singleTagThetaStdDevRad = Math.toRadians(20.0);
    /** A multi-tag solve's error relative to a single tag's. */
    public double multiTagScale = 0.25;
  }

  /** Accepted with these standard deviations {@code {x m, y m, theta rad}}, or rejected with why. */
  public record Verdict(boolean accepted, String reason, double[] stdDevs) {}

  private final Limits limits;
  private long accepted;
  private long rejected;
  private String lastReject = "";

  public VisionGate(Limits limits) {
    this.limits = limits;
  }

  public VisionGate() {
    this(new Limits());
  }

  public Limits limits() {
    return limits;
  }

  /**
   * Checks one observation.
   *
   * @param o the camera's estimate
   * @param nowS robot clock, seconds
   * @param currentXy where the pose estimate has the robot now {@code {x, y}}, or null to skip the
   *     jump check
   */
  public Verdict check(VisionSource.Observation o, double nowS, double[] currentXy) {
    String why = reason(o, nowS, currentXy);
    if (why != null) {
      rejected++;
      lastReject = why;
      return new Verdict(false, why, null);
    }
    accepted++;
    return new Verdict(true, "", stdDevs(o.tagCount(), o.nearestTagM()));
  }

  private String reason(VisionSource.Observation o, double nowS, double[] currentXy) {
    if (o.tagCount() < 1) {
      return "no tags in the solve";
    }
    double age = nowS - o.timestampS();
    if (age > limits.maxAgeS) {
      return String.format("stale: %.2f s old", age);
    }
    if (age < -0.05) {
      return "timestamped in the future: the camera's clock is not the robot's";
    }
    boolean single = o.tagCount() == 1;
    double maxD = single ? limits.maxSingleTagDistanceM : limits.maxMultiTagDistanceM;
    if (o.nearestTagM() > maxD) {
      return String.format("tag too far: %.0f in (limit %.0f in)", Units.metersToInches(o.nearestTagM()),
          Units.metersToInches(maxD));
    }
    if (single && (o.ambiguity() < 0 || o.ambiguity() > limits.maxSingleTagAmbiguity)) {
      return String.format("ambiguous single tag: %.2f", o.ambiguity());
    }
    if (Math.abs(o.zM()) > limits.maxZErrorM) {
      return String.format("off the floor: z = %.1f in", Units.metersToInches(o.zM()));
    }
    double m = limits.fieldMarginM;
    if (o.xM() < -m || o.yM() < -m || o.xM() > limits.fieldLengthM + m || o.yM() > limits.fieldWidthM + m) {
      return String.format("off the field: (%.0f, %.0f) in", Units.metersToInches(o.xM()),
          Units.metersToInches(o.yM()));
    }
    if (single && currentXy != null) {
      double jump = Math.hypot(o.xM() - currentXy[0], o.yM() - currentXy[1]);
      if (jump > limits.maxSingleTagJumpM) {
        return String.format("single tag jumps %.0f in from the current pose", Units.metersToInches(jump));
      }
    }
    return null;
  }

  /** The 2026 model: error grows with distance squared and shrinks with tag count. */
  public double[] stdDevs(int tagCount, double nearestTagM) {
    double distance = Math.max(1.0, nearestTagM * nearestTagM);
    double count = Math.max(1, tagCount);
    double xy = limits.singleTagXyStdDevM * distance / count;
    double theta = limits.singleTagThetaStdDevRad * distance / count;
    if (tagCount > 1) {
      xy *= limits.multiTagScale;
      theta *= limits.multiTagScale;
    }
    return new double[] {xy, xy, theta};
  }

  public long accepted() {
    return accepted;
  }

  public long rejected() {
    return rejected;
  }

  public String lastReject() {
    return lastReject;
  }
}
