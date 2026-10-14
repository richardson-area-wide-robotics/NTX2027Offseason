package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import edu.wpi.first.apriltag.AprilTag;
import edu.wpi.first.apriltag.AprilTagFieldLayout;
import edu.wpi.first.math.geometry.Pose3d;
import edu.wpi.first.math.geometry.Rotation3d;
import java.util.List;
import org.junit.jupiter.api.Test;

class FieldLayoutsTest {
  private static AprilTagFieldLayout layout(double length, AprilTag... tags) {
    return new AprilTagFieldLayout(List.of(tags), length, 8.069);
  }

  private static AprilTag tag(int id, double x, double y, double yawDeg) {
    return new AprilTag(id, new Pose3d(x, y, 1.12, new Rotation3d(0, 0, Math.toRadians(yawDeg))));
  }

  @Test
  void surveyedTagsReplaceOfficialOnesThatAreCloseEnough() {
    AprilTagFieldLayout official = layout(16.541, tag(1, 11.0, 3.0, 180), tag(2, 4.0, 4.0, 0), tag(3, 5, 5, 90));
    AprilTagFieldLayout surveyed = layout(16.541, tag(1, 11.04, 3.0, 180), tag(2, 4.0, 4.0, 3), tag(3, 5.5, 5, 90));
    FieldLayouts.Loaded l = FieldLayouts.merge(official, surveyed);
    assertEquals(11.04, l.layout().getTagPose(1).orElseThrow().getX(), 1e-9, "4 cm: measured");
    assertEquals(3, Math.toDegrees(l.layout().getTagPose(2).orElseThrow().getRotation().getZ()), 1e-9);
    assertEquals(5.0, l.layout().getTagPose(3).orElseThrow().getX(), 1e-9, "50 cm: kept official");
    assertTrue(l.summary().contains("2 surveyed tags moved"), l.summary());
    assertTrue(l.summary().contains("kept official for 3 (20 in"), l.summary());
  }

  @Test
  void aSurveyOfTheOtherFieldVariantIsNotUsed() {
    AprilTagFieldLayout official = layout(16.541, tag(1, 11.0, 3.0, 180));
    FieldLayouts.Loaded l = FieldLayouts.merge(official, layout(16.518, tag(1, 11.02, 3.0, 180)));
    assertSame(official, l.layout());
    assertTrue(l.summary().contains("other field variant"), l.summary());
  }

  @Test
  void tagsTheSurveyNeverSawKeepTheirOfficialPose() {
    AprilTagFieldLayout official = layout(16.541, tag(1, 11.0, 3.0, 180), tag(2, 4.0, 4.0, 0));
    FieldLayouts.Loaded l = FieldLayouts.merge(official, layout(16.541, tag(1, 11.0, 3.0, 180)));
    assertEquals(4.0, l.layout().getTagPose(2).orElseThrow().getX(), 1e-12);
    assertTrue(l.summary().contains("0 surveyed tags moved"), l.summary());
  }
}
