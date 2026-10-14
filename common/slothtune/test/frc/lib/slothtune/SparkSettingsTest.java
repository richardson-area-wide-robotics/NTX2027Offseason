package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** A SPARK's settings as published: what it reported at startup, and what was changed live since. */
class SparkSettingsTest {

  @Test
  void startupSettingsThenTheLiveOnes() {
    Map<String, String> m = new LinkedHashMap<>();
    m.put("idle", "brake");
    m.put("kP", "0.01");
    Set<String> live = new LinkedHashSet<>();
    assertEquals("idle=brake;kP=0.01", SparkChannel.join(m, live));
    m.put("kP", "0.02");
    live.add("kP");
    assertEquals("idle=brake;kP=0.02;live=kP", SparkChannel.join(m, live));
  }

  @Test
  void theClearFaultsFrameIsWpilibsOwn() {
    // HAL_ClearREVPDHStickyFaults: PDH_CLEAR_FAULTS_FRAME_ID 0x8051b80, API from bits 6-15.
    assertEquals(110, AkLogging.PDH_CLEAR_FAULTS_API);
    assertEquals(5, AkLogging.REV_MANUFACTURER);
    assertEquals(8, AkLogging.POWER_DISTRIBUTION);
  }
}
