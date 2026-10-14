package frc.lib.slothtune.photonvision;

import edu.wpi.first.apriltag.AprilTagFieldLayout;
import edu.wpi.first.apriltag.AprilTagFields;
import edu.wpi.first.math.geometry.Transform3d;
import edu.wpi.first.wpilibj.DriverStation;
import frc.lib.slothtune.FieldLayouts;
import frc.lib.slothtune.SlothTune;
import frc.lib.slothtune.VisionSource;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Every camera slothtune.json lists, as Sloth Tune's vision source: one call in Robot, and
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
  public static List<String> install(SlothTune tune) {
    List<String> names = tune.visionCameras();
    if (names.isEmpty()) {
      return List.of();
    }
    // The event's field: welded or AndyMark ("vision": {"field": ...}); kDefaultField is always welded.
    AprilTagFields official = "andymark".equals(tune.visionField())
        ? AprilTagFields.k2026RebuiltAndymark : AprilTagFields.k2026RebuiltWelded;
    FieldLayouts.Loaded field = FieldLayouts.load(AprilTagFieldLayout.loadField(official));
    if (!field.summary().isEmpty()) {
      DriverStation.reportWarning("[slothtune] AprilTags: " + field.summary(), false);
    }
    List<VisionSource> sources = new ArrayList<>();
    for (String name : names) {
      Optional<Transform3d> mount = tune.cameraMount(name);
      PhotonVisionSource camera = new PhotonVisionSource(name, field.layout(), mount.orElse(new Transform3d()));
      if (mount.isPresent()) {
        sources.add(camera);
      } else {
        DriverStation.reportWarning("[slothtune] camera " + name + ": no measured mount yet, so tag"
            + " sightings only. Measure it on the Calibrate tab, then redeploy.", false);
        sources.add(VisionSource.sightingsOnly(camera));
      }
    }
    tune.setVisionSource(VisionSource.all(sources));
    return names;
  }
}
