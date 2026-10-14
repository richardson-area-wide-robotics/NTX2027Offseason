package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

/** The roboRIO image version, read the way GradleRIO reads it. */
class RobotImageTest {
  @Test
  void readsTheImageVersionLine() {
    String ini = "[ImageInfo]\nIMAGEDESCRIPTION = \"roboRIO 2 image\"\nIMAGEVERSION = \"FRC_roboRIO2_2026_v2.0\"\n";
    assertEquals("FRC_roboRIO2_2026_v2.0", RobotImage.parse(ini));
  }

  @Test
  void nothingToReadIsEmpty() {
    assertEquals("", RobotImage.parse(""));
    assertEquals("", RobotImage.parse(null));
    assertEquals("", RobotImage.parse("IMAGEDESCRIPTION = \"no version here\""));
  }

  @Test
  void offARoboRioThereIsNoImage() {
    // The test machine, like the simulator, has no roboRIO image file.
    assertEquals("", RobotImage.version());
  }
}
