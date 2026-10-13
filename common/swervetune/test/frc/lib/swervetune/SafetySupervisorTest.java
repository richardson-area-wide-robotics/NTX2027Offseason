package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import frc.lib.swervetune.SafetySupervisor.Action;
import frc.lib.swervetune.SafetySupervisor.Inputs;
import frc.lib.swervetune.SafetySupervisor.TestProfile;
import frc.lib.swervetune.SafetySupervisor.Verdict;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class SafetySupervisorTest {
  private SafetySupervisor sup;
  private final TestProfile driving = new TestProfile(true, true, 1.0, 2.0);
  private final TestProfile steering = new TestProfile(true, false, 1.0, 0.0);
  private final TestProfile capture = new TestProfile(false, false, 1.0, 0.0);

  @BeforeEach
  void setUp() {
    sup = new SafetySupervisor(new SafetySupervisor.Limits());
  }

  private static Inputs ok(TestEnvironment env) {
    Inputs in = new Inputs();
    in.env = env;
    in.enabled = true;
    in.heartbeatAgeS = 0.05;
    in.busVolts = 12.5;
    in.horizontalAccelMps2 = 0.1;
    in.horizontalAccelSmoothedMps2 = 0.1;
    in.controllerDeadman = true;
    return in;
  }

  @Test
  void healthyFieldRunWithDeadmanContinues() {
    Inputs in = ok(TestEnvironment.FIELD);
    in.controllerDeadman = true;
    assertTrue(sup.check(in, driving, true).isOk());
  }

  @Test
  void fieldWaitsForDeadmanBeforeStartAndAbortsWhenReleased() {
    Inputs in = ok(TestEnvironment.FIELD);
    in.controllerDeadman = false;
    assertEquals(Action.WAIT, sup.check(in, driving, false).action());
    assertEquals(Action.ABORT, sup.check(in, driving, true).action());
  }

  @Test
  void guiDeadmanCountsAsWellAsTheController() {
    Inputs in = ok(TestEnvironment.FIELD);
    in.controllerDeadman = false;
    in.guiDeadman = true;
    assertTrue(sup.check(in, driving, true).isOk());
  }

  @Test
  void blocksNeedsTheDeadmanToo() {
    // "Blocks" is only what someone told the tool; a held deadman proves a person is watching.
    Inputs in = ok(TestEnvironment.BLOCKS);
    in.controllerDeadman = false;
    assertEquals(Action.WAIT, sup.check(in, steering, false).action());
    assertEquals(Action.ABORT, sup.check(in, steering, true).action());
    in.controllerDeadman = true;
    assertTrue(sup.check(in, steering, true).isOk());
  }

  @Test
  void theSimulatorNeedsNoDeadman() {
    Inputs in = ok(TestEnvironment.SIM);
    in.controllerDeadman = false;
    assertTrue(sup.check(in, steering, true).isOk());
  }

  private static Inputs wheels(Inputs in, double now, double amps, double speed) {
    in.nowS = now;
    in.driveAmps = new double[] {amps, 2, 2, 2};
    in.wheelSpeedsMps = new double[] {speed, 1, 1, 1};
    in.moduleNames = new String[] {"frontleft", "frontright", "backleft", "backright"};
    return in;
  }

  @Test
  void aWheelThatWorksLikeItCarriesWeightIsNotOnBlocks() {
    // On the floor: 20 A for 0.2 s and the wheel gains only 0.5 m/s.
    Inputs in = ok(TestEnvironment.BLOCKS);
    for (int k = 0; k <= 10; k++) {
      Verdict v = sup.check(wheels(in, k * 0.02, 20, k * 0.05), driving, true);
      if (k < 8) {
        assertTrue(v.isOk(), "not yet sustained at " + k);
      } else {
        assertEquals(Action.ABORT, v.action());
        assertTrue(v.reason().startsWith("NOT on blocks: the frontleft wheel"), v.reason());
        return;
      }
    }
  }

  @Test
  void aWheelSpinningUpInTheAirIsFine() {
    // In the air: a burst of current while the speed jumps, then friction.
    Inputs in = ok(TestEnvironment.BLOCKS);
    double[][] samples = {{30, 0}, {25, 1.6}, {3, 2.4}, {2.5, 2.5}, {2.5, 2.5}, {2.5, 2.5}};
    for (int k = 0; k < 30; k++) {
      double[] s = samples[Math.min(k, samples.length - 1)];
      assertTrue(sup.check(wheels(in, k * 0.02, s[0], s[1]), driving, true).isOk(), "sample " + k);
    }
  }

  @Test
  void aBriefSurgeIsNotCarrying() {
    // A long run of high current is needed: one that keeps restarting never adds up.
    Inputs in = ok(TestEnvironment.BLOCKS);
    for (int k = 0; k < 40; k++) {
      double amps = k % 4 == 0 ? 20 : 2;
      assertTrue(sup.check(wheels(in, k * 0.02, amps, 1.0), driving, true).isOk(), "sample " + k);
    }
  }

  @Test
  void disabledWaitsBeforeStartAndAbortsAfter() {
    Inputs in = ok(TestEnvironment.BLOCKS);
    in.enabled = false;
    assertEquals(Action.WAIT, sup.check(in, steering, false).action());
    assertEquals(Action.ABORT, sup.check(in, steering, true).action());
  }

  @Test
  void staleHeartbeatAborts() {
    Inputs in = ok(TestEnvironment.BLOCKS);
    in.heartbeatAgeS = 2;
    assertEquals(Action.ABORT, sup.check(in, steering, true).action());
  }

  @Test
  void driverStickAborts() {
    Inputs in = ok(TestEnvironment.BLOCKS);
    in.driverStickMax = 0.5;
    var v = sup.check(in, steering, true);
    assertEquals(Action.ABORT, v.action());
    assertTrue(v.reason().contains("Driver"));
  }

  @Test
  void blocksInterlockNeedsTheConditionSustained() {
    Inputs in = ok(TestEnvironment.BLOCKS);
    in.yawRateDps = 45;
    in.nowS = 10.0;
    assertTrue(sup.check(in, steering, true).isOk(), "one sample is noise, not motion");
    in.nowS = 10.2;
    var v = sup.check(in, steering, true);
    assertEquals(Action.ABORT, v.action());
    assertTrue(v.reason().contains("NOT on blocks"));
  }

  @Test
  void blocksInterlockResetsWhenTheConditionClears() {
    Inputs in = ok(TestEnvironment.BLOCKS);
    in.yawRateDps = 45;
    in.nowS = 10.0;
    sup.check(in, steering, true);
    in.yawRateDps = 0;
    in.nowS = 10.1;
    sup.check(in, steering, true);
    in.yawRateDps = 45;
    in.nowS = 10.2;
    assertTrue(sup.check(in, steering, true).isOk(), "the timer must restart, not resume");
  }

  @Test
  void smoothedAccelTriggersBlocksInterlockButRawSpikeDoesNot() {
    Inputs in = ok(TestEnvironment.BLOCKS);
    in.horizontalAccelMps2 = 9; // a single jolt
    in.horizontalAccelSmoothedMps2 = 0.5;
    in.nowS = 1;
    sup.check(in, steering, true);
    in.nowS = 1.3;
    assertTrue(sup.check(in, steering, true).isOk());
    in.horizontalAccelSmoothedMps2 = 4;
    in.nowS = 1.4;
    sup.check(in, steering, true);
    in.nowS = 1.6;
    assertEquals(Action.ABORT, sup.check(in, steering, true).action());
  }

  @Test
  void fieldImpactAbortsImmediately() {
    Inputs in = ok(TestEnvironment.FIELD);
    in.controllerDeadman = true;
    in.horizontalAccelMps2 = 20;
    var v = sup.check(in, driving, true);
    assertEquals(Action.ABORT, v.action());
    assertTrue(v.reason().startsWith("Impact"));
  }

  @Test
  void fieldGeofence() {
    Inputs in = ok(TestEnvironment.FIELD);
    in.controllerDeadman = true;
    in.displacementM = 2.1;
    assertEquals(Action.ABORT, sup.check(in, driving, true).action());
    in.displacementM = 1.9;
    assertTrue(sup.check(in, driving, true).isOk());
  }

  @Test
  void stallNeedsHighCurrentLowSpeedSustained() {
    Inputs in = ok(TestEnvironment.FIELD);
    in.controllerDeadman = true;
    in.maxDriveCurrentFraction = 0.95;
    in.speedAtMaxCurrentMps = 0.05;
    in.nowS = 5;
    assertTrue(sup.check(in, driving, true).isOk());
    in.nowS = 5.5;
    assertEquals(Action.ABORT, sup.check(in, driving, true).action());
  }

  @Test
  void aWallPushExpectsTheStallButNotMotion() {
    TestProfile wall = new TestProfile(true, false, 1.0, 0.0, true);
    Inputs in = ok(TestEnvironment.FIELD);
    in.controllerDeadman = true;
    in.maxDriveCurrentFraction = 0.95;
    in.speedAtMaxCurrentMps = 0.0;
    in.nowS = 5;
    assertTrue(sup.check(in, wall, true).isOk());
    in.nowS = 8;
    assertTrue(sup.check(in, wall, true).isOk(), "stalled against the wall is the test");
    in.displacementM = 0.4;
    var v = sup.check(in, wall, true);
    assertEquals(Action.ABORT, v.action());
    assertTrue(v.reason().contains("not against a solid wall"), v.reason());
  }

  @Test
  void overspeedAborts() {
    Inputs in = ok(TestEnvironment.BLOCKS);
    in.maxWheelSpeedMps = 2.0;
    assertEquals(Action.ABORT, sup.check(in, driving, true).action());
  }

  @Test
  void simulationIgnoresBatteryAndOverspeed() {
    Inputs in = ok(TestEnvironment.SIM);
    in.busVolts = 0;
    in.maxWheelSpeedMps = 9;
    in.nowS = 1;
    sup.check(in, driving, true);
    in.nowS = 2;
    assertTrue(sup.check(in, driving, true).isOk());
  }

  @Test
  void captureNeedsNothingButNoFms() {
    Inputs in = new Inputs();
    in.enabled = true;
    assertTrue(sup.check(in, capture, true).isOk());
  }

  @Test
  void refusals() {
    Inputs in = ok(TestEnvironment.UNSET);
    assertNotNull(sup.refuseStart(in, steering, true), "motion needs a declared environment");
    assertNull(sup.refuseStart(in, capture, false), "capture runs anywhere");

    in = ok(TestEnvironment.FIELD);
    in.busVolts = 11.5;
    assertTrue(sup.refuseStart(in, driving, true).contains("Battery"));
    in.busVolts = 12.5;
    assertNull(sup.refuseStart(in, driving, true));
    assertNotNull(sup.refuseStart(in, new TestProfile(true, true, 1.0, 0.0), true),
        "a driving test needs a declared space");

    in.fmsAttached = true;
    assertTrue(sup.refuseStart(in, capture, false).contains("FMS"));
    in.fmsAttached = false;
    in.autonomous = true;
    assertNotNull(sup.refuseStart(in, steering, true));
  }

  @Test
  void aDeadGyroBlindsTheInterlocksSoMotionIsRefused() {
    Inputs in = ok(TestEnvironment.BLOCKS);
    in.gyroConnected = false;
    assertTrue(sup.refuseStart(in, steering, true).contains("gyro"));
    assertEquals(Action.ABORT, sup.check(in, steering, true).action());
    Inputs sim = ok(TestEnvironment.SIM);
    sim.gyroConnected = false;
    assertNull(sup.refuseStart(sim, steering, true), "simulation has no physical gyro to lose");
  }

  @Test
  void aCalibratingGyroMeansWaitBeforeAndStopAfter() {
    Inputs in = ok(TestEnvironment.FIELD);
    in.controllerDeadman = true;
    in.gyroCalibrating = true;
    var before = sup.check(in, driving, false);
    assertEquals(Action.WAIT, before.action());
    assertTrue(before.reason().contains("still"));
    assertEquals(Action.ABORT, sup.check(in, driving, true).action());
  }

  @Test
  void parseNeverGuessesAnEnvironmentThatAllowsMotion() {
    assertEquals(TestEnvironment.FIELD, TestEnvironment.parse(" field "));
    assertEquals(TestEnvironment.UNSET, TestEnvironment.parse("feild"));
    assertEquals(TestEnvironment.UNSET, TestEnvironment.parse(null));
  }
}
