package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

/** Bring-up's motor test: who runs, at what, for how long, and when it stops on its own. */
class MotorTestProcedureTest {
  final FakeMotorChannel leader = new FakeMotorChannel(80);
  final FakeMotorChannel partner = new FakeMotorChannel(80);
  final FakeMotorChannel follower = new FakeMotorChannel(80);
  final MotorGuard guard = new MotorGuard();
  final List<MotorGuard.Motor> motors = List.of(
      guard.register("Roller A", leader, MotorKind.VORTEX, false),
      guard.register("Roller B", partner, MotorKind.VORTEX, false),
      guard.register("Shooter follower", follower, MotorKind.VORTEX, false));

  TestContext ctx(String[] keys, double[] values) {
    TestContext c = new TestContext(new FakeDrivetrain(), TestArgs.of(keys, values), TestEnvironment.BLOCKS,
        new int[] {0, 1, 2, 3}, 1.0, 1.0, 1.0, false, Sampler.create(2000), true, () -> true, () -> null);
    c.motors = motors;
    return c;
  }

  @Test
  void itRunsOnBlocksOnlyAndPausesTheRobotCode() {
    MotorTestProcedure p = new MotorTestProcedure();
    assertTrue(p.pausesRobotCode(), "a subsystem setting its motor every loop would fight the test");
    assertTrue(p.spinsWheels(), "it commands motors: deadman and heartbeat apply");
    assertTrue(p.allowedIn(TestEnvironment.BLOCKS));
    assertFalse(p.allowedIn(TestEnvironment.FIELD));
  }

  @Test
  void itRefusesNoMotorOrOneTheRobotDoesntHave() {
    MotorTestProcedure p = new MotorTestProcedure();
    assertNotNull(p.validate(ctx(new String[] {}, new double[] {})), "nothing to run");
    assertNotNull(p.validate(ctx(new String[] {"drive"}, new double[] {8})), "bit 3: a fourth motor");
    assertNull(p.validate(ctx(new String[] {"drive"}, new double[] {1})));
  }

  @Test
  void theDrivenMotorRunsLowAndBrieflyThePartnerIsHeldTheFollowerOnlyWatched() {
    MotorTestProcedure p = new MotorTestProcedure();
    // drive Roller A, hold Roller B at zero, watch the follower; ask for far too much output.
    TestContext c = ctx(new String[] {"drive", "zero", "watch", "duty", "pulse"}, new double[] {1, 2, 4, 0.5, 0.4});
    c.sampler.start(() -> 0);
    p.start(c);
    double t = 0;
    for (; t < MotorTestProcedure.QUIET_S - 0.01; t += 0.02) {
      assertFalse(p.execute(c, t));
      assertEquals(0, leader.testDuty, 1e-9, "the quiet baseline");
    }
    double peak = 0;
    for (; t < MotorTestProcedure.QUIET_S + 0.4 - 0.01; t += 0.02) {
      p.execute(c, t);
      peak = Math.max(peak, leader.testDuty);
      assertEquals(0, partner.testDuty, 1e-9, "held at zero so its shaft partner can turn it");
    }
    assertEquals(0.15, peak, 1e-9, "the output is capped at 15%");
    boolean done = false;
    for (; t < 3 && !done; t += 0.02) {
      done = p.execute(c, t);
    }
    assertTrue(done);
    assertEquals(0, leader.testDuty, 1e-9, "stopped after the pulse");
    assertEquals(0, follower.testDutyCalls, "a follower is never commanded: it would leave follow mode");
    p.end(c, false);
    assertEquals(0, leader.testDuty, 1e-9);
  }

  @Test
  void aNegativeSignRunsItBackwards() {
    MotorTestProcedure p = new MotorTestProcedure();
    TestContext c = ctx(new String[] {"drive", "sign"}, new double[] {1, -1});
    c.sampler.start(() -> 0);
    p.start(c);
    p.execute(c, MotorTestProcedure.QUIET_S + 0.1);
    assertEquals(-0.08, leader.testDuty, 1e-9);
  }

  @Test
  void itStopsWhenADrivenMotorPullsHardWithoutTurning() {
    MotorTestProcedure p = new MotorTestProcedure();
    TestContext c = ctx(new String[] {"drive"}, new double[] {1});
    c.sampler.start(() -> 0);
    p.start(c);
    leader.demandA = 40; // fighting its partner: high current, the shaft doesn't move
    double t = MotorTestProcedure.QUIET_S;
    for (int i = 0; i < 5; i++, t += 0.02) {
      p.execute(c, t);
    }
    assertNull(p.abortReason(c), "a moment's spike is not a stall");
    for (int i = 0; i < 6; i++, t += 0.02) {
      p.execute(c, t);
    }
    String why = p.abortReason(c);
    assertNotNull(why);
    assertTrue(why.contains("Roller A"), why);
    assertTrue(why.contains("pushing against each other"), why);
  }

  @Test
  void highCurrentWhileTurningIsNotAStall() {
    MotorTestProcedure p = new MotorTestProcedure();
    TestContext c = ctx(new String[] {"drive"}, new double[] {1});
    c.sampler.start(() -> 0);
    p.start(c);
    leader.demandA = 40;
    double t = MotorTestProcedure.QUIET_S;
    for (int i = 0; i < 20; i++, t += 0.02) {
      leader.rotations += 0.1; // 5 rotations a second
      p.execute(c, t);
    }
    assertNull(p.abortReason(c));
  }
}
