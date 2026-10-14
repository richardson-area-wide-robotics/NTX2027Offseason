package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import edu.wpi.first.networktables.DoublePublisher;
import edu.wpi.first.networktables.IntegerPublisher;
import edu.wpi.first.networktables.NetworkTableInstance;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Systems: limits found by hand, a closed-loop test that keeps inside them, and live gains. */
class SystemProceduresTest {
  /** A pivot whose position follows its goal by a set fraction each loop. */
  static final class Pivot {
    double pos = 5;
    double vel;
    double goal = Double.NaN;
    int stops;
    final List<Double> goals = new ArrayList<>();

    TunableSystem system() {
      TunableSystem s = new TunableSystem("Intake pivot", TunableSystem.Kind.PIVOT)
          .units("rot").position(() -> pos).velocity(() -> vel).motors("Intake pivot")
          .goal(g -> {
            goal = g;
            goals.add(g);
          })
          .stop(() -> stops++);
      return s;
    }

    void step(double dt) {
      if (Double.isFinite(goal)) {
        double before = pos;
        pos += 0.5 * (goal - pos);
        vel = (pos - before) / dt;
      }
    }
  }

  final FakeMotorChannel motor = new FakeMotorChannel(60);
  final MotorGuard guard = new MotorGuard();
  final MotorGuard.Motor guarded = guard.register("Intake pivot", motor, MotorKind.VORTEX, false);
  boolean enabled = false;

  TestContext ctx(TunableSystem s, String[] keys, double[] values) {
    TestContext c = new TestContext(new FakeDrivetrain(), TestArgs.of(keys, values), TestEnvironment.BLOCKS,
        new int[] {0, 1, 2, 3}, 1.0, 1.0, 1.0, false, Sampler.create(20000), enabled, () -> enabled, () -> null);
    c.systems = List.of(s);
    c.motors = List.of(guarded);
    return c;
  }

  // ---------------------------------------------------------------- limits by hand
  @Test
  void limitsAreFoundByHandWithTheRobotDisabledAndItsMotorsCoasting() {
    Pivot p = new Pivot();
    TunableSystem s = p.system();
    SystemLimitsProcedure proc = new SystemLimitsProcedure();
    enabled = true;
    assertNotNull(proc.validate(ctx(s, new String[] {"system"}, new double[] {0})), "never while enabled");
    enabled = false;
    TestContext c = ctx(s, new String[] {"system"}, new double[] {0});
    assertNull(proc.validate(c));
    proc.start(c);
    assertEquals(List.of(true), motor.coastCalls, "coasting, to move by hand");
    for (double x : new double[] {5, 2, 0.4, 3, 9, 17.6, 12}) {
      p.pos = x;
      proc.execute(c, 1);
    }
    proc.requestStop();
    assertTrue(proc.execute(c, 2));
    proc.end(c, false);
    assertEquals(List.of(true, false), motor.coastCalls, "back to brake, as it was");
    assertEquals(0.4, s.min, 1e-12);
    assertEquals(17.6, s.max, 1e-12);
    assertEquals("moved by hand", s.limitsFrom);
  }

  @Test
  void aMechanismNobodyMovedHasNoLimits() {
    Pivot p = new Pivot();
    TunableSystem s = p.system();
    SystemLimitsProcedure proc = new SystemLimitsProcedure();
    TestContext c = ctx(s, new String[] {"system"}, new double[] {0});
    proc.start(c);
    proc.execute(c, 1);
    proc.end(c, false);
    assertFalse(s.hasLimits());
  }

  // ---------------------------------------------------------------- the closed-loop test
  @Test
  void aPositionTestNeedsLimitsAndASpeedLimit() {
    Pivot p = new Pivot();
    TunableSystem s = p.system();
    SystemStepProcedure proc = new SystemStepProcedure();
    enabled = true;
    String[] k = {"system", "vmax", "amax", "a", "b"};
    assertNotNull(proc.validate(ctx(s, k, new double[] {0, 5, 20, 4, 14})), "no limits yet");
    s.setLimits(0, 18, "moved by hand");
    assertNull(proc.validate(ctx(s, k, new double[] {0, 5, 20, 4, 14})));
    assertNotNull(proc.validate(ctx(s, new String[] {"system", "a", "b"}, new double[] {0, 4, 14})), "no speed limit");
  }

  @Test
  void theGoalMovesAlongALimitedPathAndStaysInside() {
    Pivot p = new Pivot();
    TunableSystem s = p.system();
    s.setLimits(0, 18, "moved by hand");
    s.maxVelocity = 4;  // slothtune.json's cap, under the 10 asked
    SystemStepProcedure proc = new SystemStepProcedure();
    enabled = true;
    TestContext c = ctx(s, new String[] {"system", "vmax", "amax", "a", "b", "hold_s", "moves"},
        new double[] {0, 10, 20, -50, 50, 0.2, 2});
    proc.start(c);
    double t = 0;
    boolean done = false;
    double last = p.pos;
    double fastest = 0;
    while (!done && t < 60) {
      done = proc.execute(c, t);
      double g = p.goal;
      if (Double.isFinite(g)) {
        fastest = Math.max(fastest, Math.abs(g - last) / 0.01);
        last = g;
      }
      assertNull(proc.abortReason(c));
      p.step(0.01);
      t += 0.01;
    }
    assertTrue(done);
    double lo = p.goals.stream().mapToDouble(Double::doubleValue).min().orElseThrow();
    double hi = p.goals.stream().mapToDouble(Double::doubleValue).max().orElseThrow();
    assertEquals(0.9, lo, 1e-9, "goals clamped 5% inside the limits");
    assertEquals(17.1, hi, 1e-9);
    assertTrue(fastest <= 4 + 1e-6, "never faster than slothtune.json allows: " + fastest);
    proc.end(c, false);
    assertEquals(1, p.stops, "stopped the team's way at the end");
  }

  @Test
  void itStopsPastTheLimitsOrTooFast() {
    Pivot p = new Pivot();
    TunableSystem s = p.system();
    s.setLimits(0, 18, "moved by hand");
    SystemStepProcedure proc = new SystemStepProcedure();
    enabled = true;
    TestContext c = ctx(s, new String[] {"system", "vmax", "amax", "a", "b"}, new double[] {0, 4, 20, 4, 14});
    proc.start(c);
    p.pos = 18.8;
    assertTrue(proc.abortReason(c).contains("went past its limits"), proc.abortReason(c));
    p.pos = 9;
    p.vel = 7;
    assertTrue(proc.abortReason(c).contains("faster than the test allows"), proc.abortReason(c));
  }

  @Test
  void aFlywheelRampsUpAndBackDownWithinItsTopSpeed() {
    double[] speed = {0};
    List<Double> goals = new ArrayList<>();
    TunableSystem s = new TunableSystem("Shooter", TunableSystem.Kind.FLYWHEEL).units("RPM")
        .velocity(() -> speed[0]).goal(g -> {
          goals.add(g);
          speed[0] = g;
        });
    SystemStepProcedure proc = new SystemStepProcedure();
    enabled = true;
    TestContext c = ctx(s, new String[] {"system", "vmax", "amax", "a", "b", "hold_s"}, new double[] {0, 3000, 2000, 2000, 5000, 0.2});
    assertNull(proc.validate(c), "a flywheel needs no limits");
    proc.start(c);
    double t = 0;
    while (!proc.execute(c, t) && t < 30) {
      t += 0.01;
    }
    assertEquals(3000, goals.stream().mapToDouble(Double::doubleValue).max().orElseThrow(), 1e-9, "5000 asked, 3000 allowed");
    assertEquals(0, goals.get(goals.size() - 1), 1e-9, "and back down");
  }

  @Test
  void theProfileReachesItsGoalWithinItsLimits() {
    double peak = 0;
    for (double t = 0; t < 10; t += 0.001) {
      double[] s = SystemStepProcedure.profile(2, 12, 3, 6, t);
      peak = Math.max(peak, Math.abs(s[1]));
    }
    assertEquals(3, peak, 1e-6);
    assertEquals(12, SystemStepProcedure.profile(2, 12, 3, 6, 100)[0], 1e-12);
    double[] tri = SystemStepProcedure.profile(0, 0.5, 10, 2, 0.5);
    assertTrue(tri[1] < 10, "a short move never reaches top speed");
  }

  // ---------------------------------------------------------------- live gains
  @Test
  void gainsChangeLiveWithinTheirRangeAndOnlyFromThisBoot() {
    NetworkTableInstance nt = NetworkTableInstance.create();
    try {
      double[] kp = {0.1};
      TunableSystem s = new TunableSystem("Intake pivot", TunableSystem.Kind.PIVOT).gain("kP", () -> kp[0], v -> kp[0] = v, 0, 1);
      List<TunableSystem> list = new ArrayList<>(List.of(s));
      SystemBoard board = new SystemBoard(nt, 42, list);
      board.periodic(null);
      DoublePublisher req = nt.getDoubleTopic(SlothTuneTopics.SYSTEMS_GAINS + "Intake pivot/kP").publish();
      IntegerPublisher seq = nt.getIntegerTopic(SlothTuneTopics.SYSTEMS_APPLY_SEQ).publish();
      IntegerPublisher boot = nt.getIntegerTopic(SlothTuneTopics.SYSTEMS_APPLY_BOOT_ID).publish();
      req.set(0.3);
      boot.set(41);
      seq.set(1);
      board.periodic(null);
      assertEquals(0.1, kp[0], 1e-12, "a value from before a restart is refused");
      req.set(0.3);
      boot.set(42);
      seq.set(2);
      board.periodic(null);
      assertEquals(0.3, kp[0], 1e-12);
      req.set(5);
      seq.set(3);
      board.periodic(null);
      assertEquals(0.3, kp[0], 1e-12, "out of range, refused");
      String status = nt.getStringTopic(SlothTuneTopics.SYSTEMS_APPLY_STATUS).subscribe("").get();
      assertTrue(status.contains("REFUSED"), status);
      req.set(0.4);
      seq.set(4);
      board.periodic("a test is running");
      assertEquals(0.3, kp[0], 1e-12, "never during a test");
    } finally {
      nt.close();
    }
  }
}
