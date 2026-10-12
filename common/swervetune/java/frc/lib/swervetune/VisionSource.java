package frc.lib.swervetune;

import java.util.List;

/**
 * Robot poses from cameras, whatever the camera.
 *
 * <p>The tuning tools never talk to a camera library. Robot code wraps its own - PhotonLib for the
 * Luma P1/P2, which run PhotonVision - in this interface and hands it to
 * {@link SwerveTune#setVisionSource}. Keeping vendor code out of the library is what lets it carry on
 * unchanged when PhotonLib, the Luma image or WPILib's packages change for 2027.
 */
public interface VisionSource {

  /**
   * One pose estimate from one camera frame.
   *
   * @param xM field x, meters, WPILib blue-origin field frame
   * @param yM field y, meters
   * @param zM height of the solved robot origin, meters; near zero for a believable solve
   * @param headingDeg robot heading, degrees, counter-clockwise positive
   * @param timestampS when the frame was captured, robot clock seconds (PhotonLib already reports
   *     this timebase)
   * @param tagCount tags used in the solve
   * @param ambiguity worst single-tag pose ambiguity, 0 to 1; above 0.2 is a coin flip; -1 unknown
   * @param nearestTagM distance to the nearest tag used, meters
   * @param camera which camera, for telemetry
   */
  record Observation(
      double xM,
      double yM,
      double zM,
      double headingDeg,
      double timestampS,
      int tagCount,
      double ambiguity,
      double nearestTagM,
      String camera) {}

  /** Every new observation since the last call. Called once per robot loop. */
  List<Observation> poll();

  /**
   * One AprilTag in one camera frame, exactly as the camera saw it: the tag's pose in the camera's
   * frame, WPILib axes (x out of the lens, y left, z up; the tag's own x axis points out of its
   * face). Nothing is filtered: these are for measuring where the camera sits.
   *
   * @param camera which camera
   * @param tagId the tag's ID
   * @param xM tag center, meters, in the camera frame
   * @param qw tag rotation in the camera frame, as a quaternion (w, x, y, z)
   * @param ambiguity this tag's pose ambiguity, 0 to 1; -1 unknown
   * @param timestampS when the frame was captured, robot clock seconds
   */
  record TagSighting(
      String camera,
      int tagId,
      double xM,
      double yM,
      double zM,
      double qw,
      double qx,
      double qy,
      double qz,
      double ambiguity,
      double timestampS) {}

  /**
   * The tags in the newest frame from each camera, from the frames {@link #poll} last read. Empty
   * when this source cannot say; then the camera calibration has nothing to work with.
   */
  default List<TagSighting> sightings() {
    return List.of();
  }
}
