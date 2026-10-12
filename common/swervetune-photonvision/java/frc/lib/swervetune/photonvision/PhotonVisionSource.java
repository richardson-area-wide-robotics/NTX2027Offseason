package frc.lib.swervetune.photonvision;

import edu.wpi.first.apriltag.AprilTagFieldLayout;
import edu.wpi.first.math.geometry.Pose3d;
import edu.wpi.first.math.geometry.Transform3d;
import frc.lib.swervetune.VisionSource;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.photonvision.EstimatedRobotPose;
import org.photonvision.PhotonCamera;
import org.photonvision.PhotonPoseEstimator;
import org.photonvision.targeting.PhotonPipelineResult;
import org.photonvision.targeting.PhotonTrackedTarget;

/**
 * A PhotonVision camera - including a Luma P1 or P2, which run PhotonVision - as a
 * {@link VisionSource} for the swerve tools.
 *
 * <p><b>Optional.</b> This folder compiles only in a project that has the PhotonLib vendordep. Add it
 * when a camera is fitted, pinned to the 2026 release: the online vendordep URL now serves a 2027
 * alpha. Then add {@code ../common/swervetune-photonvision/java} to the project's sourceSets and:
 *
 * <pre>
 *   tune.setVisionSource(new PhotonVisionSource(
 *       "front", AprilTagFieldLayout.loadField(AprilTagFields.kDefaultField), ROBOT_TO_CAMERA));
 * </pre>
 *
 * <p>Uses the 2026 estimator API (strategy chosen per call; the constructor-chosen strategy and
 * {@code update()} are deprecated in 2026 and gone in 2027): a multi-tag solve done on the camera,
 * falling back to the least ambiguous single tag. Multi-tag needs PhotonVision's 3D mode and "Do
 * Multi-Target Estimation" switched on, and a calibrated camera - the Luma P1 image ships with
 * neither. See docs/VISION_LUMA_PHOTONVISION.md.
 *
 * <p>Calls {@link PhotonCamera#getAllUnreadResults()} once per loop, as PhotonLib requires; its queue
 * holds only 20 results.
 */
public final class PhotonVisionSource implements VisionSource {
  private final String name;
  private final PhotonCamera camera;
  private final PhotonPoseEstimator estimator;

  /**
   * @param cameraName exactly as the camera's PhotonVision web page shows it; a mismatch fails
   *     silently, with no error and no poses
   * @param layout the field's AprilTag layout (welded or AndyMark: they differ by up to 3.6 cm)
   * @param robotToCamera robot centre at the floor to the camera lens, metres and radians
   */
  public PhotonVisionSource(String cameraName, AprilTagFieldLayout layout, Transform3d robotToCamera) {
    this.name = cameraName;
    this.camera = new PhotonCamera(cameraName);
    this.estimator = new PhotonPoseEstimator(layout, robotToCamera);
  }

  /** Whether PhotonVision is answering for this camera. */
  public boolean isConnected() {
    return camera.isConnected();
  }

  @Override
  public List<Observation> poll() {
    List<Observation> out = new ArrayList<>();
    for (PhotonPipelineResult result : camera.getAllUnreadResults()) {
      if (!result.hasTargets()) {
        continue;
      }
      Optional<EstimatedRobotPose> est = estimator.estimateCoprocMultiTagPose(result);
      if (est.isEmpty()) {
        est = estimator.estimateLowestAmbiguityPose(result);
      }
      est.ifPresent(e -> out.add(toObservation(e)));
    }
    return out;
  }

  private Observation toObservation(EstimatedRobotPose e) {
    double nearest = Double.POSITIVE_INFINITY;
    double worstAmbiguity = 0;
    for (PhotonTrackedTarget t : e.targetsUsed) {
      nearest = Math.min(nearest, t.getBestCameraToTarget().getTranslation().getNorm());
      worstAmbiguity = Math.max(worstAmbiguity, t.getPoseAmbiguity());
    }
    Pose3d p = e.estimatedPose;
    return new Observation(
        p.getX(),
        p.getY(),
        p.getZ(),
        Math.toDegrees(p.getRotation().getZ()),
        e.timestampSeconds,
        e.targetsUsed.size(),
        e.targetsUsed.size() == 1 ? worstAmbiguity : 0,
        nearest,
        name);
  }
}
