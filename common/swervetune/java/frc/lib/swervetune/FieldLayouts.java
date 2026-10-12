package frc.lib.swervetune;

import edu.wpi.first.apriltag.AprilTag;
import edu.wpi.first.apriltag.AprilTagFieldLayout;
import edu.wpi.first.math.geometry.Pose3d;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.Filesystem;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * The AprilTag layout to localize with: the official one, with any tags the Calibrate tab's field
 * survey measured put where they really are.
 *
 * <p>Tag by tag, and only within {@value #TRUST_M} m and {@value #TRUST_DEG} degrees of the official
 * pose - a survey reading further off than that is more likely a misread than a real field, so that
 * tag keeps its official pose. A surveyed file made against the other field variant (welded or
 * AndyMark: the field sizes differ) is not used at all.
 *
 * <pre>
 *   AprilTagFieldLayout layout = FieldLayouts.load(
 *       AprilTagFieldLayout.loadField(AprilTagFields.kDefaultField)).layout();
 * </pre>
 */
public final class FieldLayouts {
  public static final double TRUST_M = 0.30;
  public static final double TRUST_DEG = 10.0;
  /** Where the survey's layout is deployed, under the deploy directory. */
  public static final String SURVEYED = "apriltags/surveyed.json";
  // The two 2026 variants differ by 2.3 cm in length; a survey copies its field size exactly.
  private static final double SAME_FIELD_M = 0.005;

  private FieldLayouts() {}

  /** The layout and a sentence saying where it came from. */
  public record Loaded(AprilTagFieldLayout layout, String summary) {}

  /** Loads the deployed survey, if any, over {@code official}, and says so on the Driver Station. */
  public static Loaded load(AprilTagFieldLayout official) {
    Path p = Filesystem.getDeployDirectory().toPath().resolve(SURVEYED);
    Loaded out;
    if (!Files.exists(p)) {
      out = new Loaded(official, "AprilTags: the official layout (no surveyed layout deployed).");
    } else {
      try {
        out = merge(official, new AprilTagFieldLayout(p));
      } catch (IOException | RuntimeException e) {
        out = new Loaded(official, "AprilTags: the official layout; " + SURVEYED + " could not be read ("
            + e.getMessage() + ").");
        DriverStation.reportWarning("[swervetune] " + out.summary(), false);
      }
    }
    System.out.println("[swervetune] " + out.summary());
    return out;
  }

  /** {@code official} with each surveyed tag that is close enough to its official pose. */
  static Loaded merge(AprilTagFieldLayout official, AprilTagFieldLayout surveyed) {
    if (Math.abs(official.getFieldLength() - surveyed.getFieldLength()) > SAME_FIELD_M
        || Math.abs(official.getFieldWidth() - surveyed.getFieldWidth()) > SAME_FIELD_M) {
      return new Loaded(official, "AprilTags: the official layout; the surveyed one was made for the"
          + " other field variant (welded or AndyMark), so it is not used. Survey again, or load the"
          + " matching official layout.");
    }
    List<AprilTag> tags = new ArrayList<>();
    int moved = 0;
    List<String> refused = new ArrayList<>();
    for (AprilTag t : official.getTags()) {
      Optional<Pose3d> s = surveyed.getTags().stream().filter(x -> x.ID == t.ID).map(x -> x.pose).findFirst();
      if (s.isPresent()) {
        double d = s.get().getTranslation().getDistance(t.pose.getTranslation());
        double ang = Math.toDegrees(s.get().getRotation().minus(t.pose.getRotation()).getAngle());
        if (d <= TRUST_M && ang <= TRUST_DEG) {
          tags.add(new AprilTag(t.ID, s.get()));
          if (d > 1e-4 || ang > 0.01) {
            moved++;
          }
          continue;
        }
        refused.add(t.ID + " (" + Math.round(d * 100) + " cm, " + Math.round(ang) + " deg)");
      }
      tags.add(t);
    }
    String summary = "AprilTags: the official layout with " + moved + " surveyed tag"
        + (moved == 1 ? "" : "s") + " moved to where they were measured"
        + (refused.isEmpty() ? "." : "; kept official for " + String.join(", ", refused)
            + ", too far off to trust.");
    if (!refused.isEmpty()) {
      DriverStation.reportWarning("[swervetune] " + summary, false);
    }
    return new Loaded(new AprilTagFieldLayout(tags, official.getFieldLength(), official.getFieldWidth()),
        summary);
  }
}
