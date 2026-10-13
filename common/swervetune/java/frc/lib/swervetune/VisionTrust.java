package frc.lib.swervetune;

/**
 * How far to trust one camera pose, as the standard deviations WPILib's pose estimator takes.
 *
 * <p>A tag's pose error grows with the square of its distance, and shrinks with every extra tag in
 * the solve. A single tag's heading is a coin flip between two mirror solutions, so it never
 * changes the heading: the gyro decides that. The numbers are a starting point: if poses jump on
 * the Live tab, raise them; if the estimate drifts between sightings, lower them.
 */
public final class VisionTrust {
  /** Meters of x and y error at 1 m for one tag. */
  public static final double XY_PER_M2 = 0.04;
  public static final double XY_FLOOR_M = 0.02;
  /** Radians of heading error at 1 m for a multi-tag solve. */
  public static final double HEADING_PER_M2 = 0.10;
  public static final double HEADING_FLOOR_RAD = 0.05;
  /** A heading nothing should believe: the estimator then ignores it. */
  public static final double IGNORE = 1e6;

  private VisionTrust() {}

  /** {@code {sd x and y in meters, sd heading in radians}} for one observation. */
  public static double[] stdDevs(VisionSource.Observation o) {
    double d = Math.max(0.5, Double.isFinite(o.nearestTagM()) ? o.nearestTagM() : 4.0);
    int n = Math.max(1, o.tagCount());
    double xy = XY_FLOOR_M + XY_PER_M2 * d * d / n;
    double heading = n >= 2 ? HEADING_FLOOR_RAD + HEADING_PER_M2 * d * d / n : IGNORE;
    return new double[] {xy, heading};
  }
}
