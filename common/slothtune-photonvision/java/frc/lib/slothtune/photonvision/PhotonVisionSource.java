package frc.lib.slothtune.photonvision;

import edu.wpi.first.apriltag.AprilTagFieldLayout;
import edu.wpi.first.math.geometry.Pose3d;
import edu.wpi.first.math.geometry.Quaternion;
import edu.wpi.first.math.geometry.Transform3d;
import frc.lib.slothtune.VisionSource;
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
 * {@link VisionSource} for Sloth Tune.
 *
 * <p><b>Optional.</b> This folder compiles only in a project that has the PhotonLib vendordep. Add it
 * when a camera is fitted, pinned to the 2026 release: the online vendordep URL now serves a 2027
 * alpha. Then add {@code ../common/slothtune-photonvision/java} to the project's sourceSets and:
 *
 * <pre>
 *   AprilTagFieldLayout field = FieldLayouts.load(
 *       AprilTagFieldLayout.loadField(AprilTagFields.kDefaultField)).layout();
 *   tune.setVisionSource(new PhotonVisionSource(
 *       "front", field, tune.cameraMount("front").orElse(ROUGH_ROBOT_TO_CAMERA)));
 * </pre>
 *
 * <p>{@code FieldLayouts.load} puts in the tag positions the Calibrate tab's field survey measured,
 * if one is deployed.
 *
 * <p>{@code cameraMount} reads where the camera sits from slothtune.json, which the Calibrate tab
 * measures; until then, a tape-measured guess keeps the robot running.
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
  private List<TagSighting> sightings = List.of();

  /**
   * @param cameraName exactly as the camera's PhotonVision web page shows it; a mismatch fails
   *     silently, with no error and no poses
   * @param layout the field's AprilTag layout (welded or AndyMark: they differ by up to 3.6 cm)
   * @param robotToCamera robot center at the floor to the camera lens, meters and radians
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
      List<TagSighting> seen = new ArrayList<>();
      for (PhotonTrackedTarget t : result.getTargets()) {
        if (t.getFiducialId() < 0) {
          continue;
        }
        Transform3d c2t = t.getBestCameraToTarget();
        Quaternion q = c2t.getRotation().getQuaternion();
        seen.add(new TagSighting(name, t.getFiducialId(), c2t.getX(), c2t.getY(), c2t.getZ(),
            q.getW(), q.getX(), q.getY(), q.getZ(), t.getPoseAmbiguity(), result.getTimestampSeconds()));
      }
      sightings = seen;
      Optional<EstimatedRobotPose> est = estimator.estimateCoprocMultiTagPose(result);
      if (est.isEmpty()) {
        est = estimator.estimateLowestAmbiguityPose(result);
      }
      est.ifPresent(e -> out.add(toObservation(e)));
    }
    return out;
  }

  @Override
  public List<TagSighting> sightings() {
    return sightings;
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
