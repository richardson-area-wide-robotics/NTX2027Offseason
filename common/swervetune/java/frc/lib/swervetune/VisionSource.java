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
   * @param xM field x, metres, WPILib blue-origin field frame
   * @param yM field y, metres
   * @param zM height of the solved robot origin, metres; near zero for a believable solve
   * @param headingDeg robot heading, degrees, counter-clockwise positive
   * @param timestampS when the frame was captured, robot clock seconds (PhotonLib already reports
   *     this timebase)
   * @param tagCount tags used in the solve
   * @param ambiguity worst single-tag pose ambiguity, 0 to 1; above 0.2 is a coin flip; -1 unknown
   * @param nearestTagM distance to the nearest tag used, metres
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
}
