package frc.lib.swervetune.photonvision;

import edu.wpi.first.apriltag.AprilTagFieldLayout;
import edu.wpi.first.apriltag.AprilTagFields;
import edu.wpi.first.math.geometry.Transform3d;
import edu.wpi.first.wpilibj.DriverStation;
import frc.lib.swervetune.FieldLayouts;
import frc.lib.swervetune.SwerveTune;
import frc.lib.swervetune.VisionSource;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Every camera swervetune.json lists, as the swerve tools' vision source: one call in Robot, and
 * fitting a camera is a config change.
 *
 * <pre>
 *   "vision": {"cameras": ["front"], "feedPoseEstimator": false},
 *   "cameras": {"front": {"x": 0.30, "y": 0.0, "z": 0.25, "pitch": -15}}
 * </pre>
 *
 * <p>A camera with a measured mount (the Calibrate tab writes {@code "cameras"}) gives robot poses:
 * the Live tab shows them, the straight-line test measures with them, and with
 * {@code feedPoseEstimator} on they correct the drivetrain's own pose. A camera listed before its
 * mount is measured gives tag sightings only, which is exactly what the Calibrate tab needs to
 * measure the mount. A name that matches no camera on the network just never sees anything.
 */
public final class PhotonVisionSetup {
  private PhotonVisionSetup() {}

  /** Makes a source for every listed camera and hands them to {@code tune}. Returns their names. */
  public static List<String> install(SwerveTune tune) {
    List<String> names = tune.visionCameras();
    if (names.isEmpty()) {
      return List.of();
    }
    FieldLayouts.Loaded field = FieldLayouts.load(AprilTagFieldLayout.loadField(AprilTagFields.kDefaultField));
    if (!field.summary().isEmpty()) {
      DriverStation.reportWarning("[swervetune] AprilTags: " + field.summary(), false);
    }
    List<VisionSource> sources = new ArrayList<>();
    for (String name : names) {
      Optional<Transform3d> mount = tune.cameraMount(name);
      PhotonVisionSource camera = new PhotonVisionSource(name, field.layout(), mount.orElse(new Transform3d()));
      if (mount.isPresent()) {
        sources.add(camera);
      } else {
        DriverStation.reportWarning("[swervetune] camera " + name + ": no measured mount yet, so tag"
            + " sightings only. Measure it on the Calibrate tab, then redeploy.", false);
        sources.add(VisionSource.sightingsOnly(camera));
      }
    }
    tune.setVisionSource(VisionSource.all(sources));
    return names;
  }
}
