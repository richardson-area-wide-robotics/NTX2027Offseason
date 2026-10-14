package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import frc.lib.slothtune.VisionSource.Observation;
import org.junit.jupiter.api.Test;

class VisionGateTest {
  private final VisionGate gate = new VisionGate();
  private final double now = 100.0;
  private final double[] here = {3.0, 4.0};

  private static Observation obs(double x, double y, double z, double t, int tags, double amb, double d) {
    return new Observation(x, y, z, 0, t, tags, amb, d, "cam");
  }

  @Test
  void aGoodMultiTagSolveIsAcceptedAndTrustedMore() {
    var multi = gate.check(obs(3.1, 4.0, 0.02, 99.95, 3, 0.05, 2.0), now, here);
    var single = gate.check(obs(3.1, 4.0, 0.02, 99.95, 1, 0.05, 2.0), now, here);
    assertTrue(multi.accepted());
    assertTrue(single.accepted());
    assertTrue(multi.stdDevs()[0] < single.stdDevs()[0] / 4, "multi-tag is trusted far more");
  }

  @Test
  void everyGateSaysWhy() {
    String[][] cases = {
      {"stale", "3.0,4.0,0,99.0,2,0.1,2"},
      {"future", "3.0,4.0,0,100.5,2,0.1,2"},
      {"too far", "3.0,4.0,0,99.95,1,0.1,4.5"},
      {"ambiguous", "3.0,4.0,0,99.95,1,0.35,2"},
      {"off the floor", "3.0,4.0,0.9,99.95,2,0.1,2"},
      {"off the field", "20.0,4.0,0,99.95,2,0.1,2"},
      {"jumps", "6.0,4.0,0,99.95,1,0.1,2"},
      {"no tags", "3.0,4.0,0,99.95,0,0.1,2"},
    };
    for (String[] c : cases) {
      String[] p = c[1].split(",");
      var v = gate.check(obs(Double.parseDouble(p[0]), Double.parseDouble(p[1]), Double.parseDouble(p[2]),
          Double.parseDouble(p[3]), Integer.parseInt(p[4]), Double.parseDouble(p[5]),
          Double.parseDouble(p[6])), now, here);
      assertFalse(v.accepted(), c[0]);
      assertTrue(v.reason().contains(c[0]), c[0] + " -> " + v.reason());
    }
    assertEquals(8, gate.rejected());
    assertTrue(gate.lastReject().contains("no tags"));
  }

  @Test
  void multiTagMayCorrectALargeErrorButASingleTagMayNot() {
    assertTrue(gate.check(obs(6.0, 4.0, 0, 99.95, 2, 0.1, 2), now, here).accepted());
    assertFalse(gate.check(obs(6.0, 4.0, 0, 99.95, 1, 0.1, 2), now, here).accepted());
  }

  @Test
  void stdDevsMatchThe2026Model() {
    assertArrayEquals(new double[] {0.35, 0.35, Math.toRadians(20)}, gate.stdDevs(1, 1.0), 1e-12);
    assertArrayEquals(new double[] {0.35 * 4, 0.35 * 4, Math.toRadians(20) * 4}, gate.stdDevs(1, 2.0), 1e-12);
    assertEquals(0.35 * 4 / 2 * 0.25, gate.stdDevs(2, 2.0)[0], 1e-12);
  }
}
