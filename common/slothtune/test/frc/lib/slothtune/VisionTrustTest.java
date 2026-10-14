package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class VisionTrustTest {
  private static VisionSource.Observation obs(int tags, double distM) {
    return new VisionSource.Observation(3, 2, 0, 90, 10, tags, 0.05, distM, "front");
  }

  @Test
  void fartherAndFewerTagsAreTrustedLess() {
    double[] near2 = VisionTrust.stdDevs(obs(2, 1.5));
    double[] far2 = VisionTrust.stdDevs(obs(2, 4));
    double[] near1 = VisionTrust.stdDevs(obs(1, 1.5));
    assertTrue(far2[0] > near2[0]);
    assertTrue(near1[0] > near2[0]);
    assertEquals(0.02 + 0.04 * 4 / 1, VisionTrust.stdDevs(obs(1, 2))[0], 1e-12, "one tag at 2 m: 0.18 m");
  }

  @Test
  void aSingleTagNeverMovesTheHeading() {
    assertEquals(VisionTrust.IGNORE, VisionTrust.stdDevs(obs(1, 1))[1]);
    assertTrue(VisionTrust.stdDevs(obs(3, 2))[1] < 1);
  }

  @Test
  void aCameraStillBeingMeasuredGivesSightingsButNoPoses() {
    VisionSource.TagSighting seen = new VisionSource.TagSighting("front", 7, 1.5, 0.1, 0.2, 1, 0, 0, 0, 0.05, 12);
    VisionSource raw = new VisionSource() {
      @Override
      public List<Observation> poll() {
        return List.of(obs(2, 2));
      }

      @Override
      public List<TagSighting> sightings() {
        return List.of(seen);
      }
    };
    VisionSource s = VisionSource.sightingsOnly(raw);
    assertEquals(List.of(), s.poll());
    assertEquals(List.of(seen), s.sightings());
    VisionSource both = VisionSource.all(List.of(raw, raw));
    assertEquals(2, both.poll().size());
    assertEquals(2, both.sightings().size());
  }

  @Test
  void theSwitchAndTheCamerasComeFromTheConfig() {
    SlothTuneConfig off = SlothTuneConfig.parse("{\"vision\": {\"cameras\": [\"front\", \"front\", \"rear\"]}}");
    assertEquals(List.of("front", "rear"), off.visionCameras);
    assertEquals(false, off.feedPoseEstimator);
    SlothTuneConfig on = SlothTuneConfig.parse(
        "{\"vision\": {\"cameras\": [\"front\"], \"feedPoseEstimator\": true}}");
    assertTrue(on.feedPoseEstimator);
    assertTrue(on.warnings.stream().anyMatch(w -> w.contains("no measured mount")), on.warnings.toString());
  }
}
