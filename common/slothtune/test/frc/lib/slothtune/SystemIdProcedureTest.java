package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * Identification: on mechanisms with known physics, it finds the volts that hold them, sweeps and
 * steps them without leaving their travel, and stops on its own when something is wrong.
 */
class SystemIdProcedureTest {
  /** A mechanism with known physics, in its own units: friction, back-EMF, inertia, gravity. */
  static final class Plant {
    final TunableSystem.Kind kind;
    final double kS;
    final double kV;
    final double kA;
    final double kG;
    /** An arm's angle, radians per unit of its position (horizontal at zero). */
    double radPerUnit = 1;
    /** Its motor turns it the other way. */
    boolean reversed;
    double x;
    double v;
    double stopLo = Double.NEGATIVE_INFINITY;
    double stopHi = Double.POSITIVE_INFINITY;
    double lowest = Double.POSITIVE_INFINITY;
    double highest = Double.NEGATIVE_INFINITY;
    double fastest;
    /** The fastest it struck a stop, and how long it was pushed into one past 1 V. */
    double hitSpeed;
    double pushedIntoStopS;
    /** One count of its sensor: the position it reports is rounded to this (0: exact). */
    double count;
    /** Its reading freezes after this many steps (its sensor drops out); the motor's encoder doesn't. */
    int freezeAfter = Integer.MAX_VALUE;
    int steps;
    double frozen = Double.NaN;
    final FakeMotorChannel motor = new FakeMotorChannel(40);

    Plant(TunableSystem.Kind kind, double kS, double kV, double kA, double kG) {
      this.kind = kind;
      this.kS = kS;
      this.kV = kV;
      this.kA = kA;
      this.kG = kG;
    }

    void step(double dt) {
      double u = Double.isFinite(motor.testVolts) ? motor.testVolts : 0;
      if (reversed) {
        u = -u;
      }
      double h = 0.0005;
      for (int i = 0; i < Math.round(dt / h); i++) {
        double g = kind == TunableSystem.Kind.ELEVATOR ? kG
            : kind == TunableSystem.Kind.PIVOT ? kG * Math.cos(x * radPerUnit) : 0;
        double net = u - g - kV * v;
        if (v == 0 && Math.abs(net) <= kS) {
          continue;  // friction holds it
        }
        double a = (net - kS * Math.signum(v != 0 ? v : net)) / kA;
        double next = v + a * h;
        v = v != 0 && next * v < 0 ? 0 : next;  // friction stops it at zero
        x += v * h;
        if (x < stopLo || x > stopHi) {
          hitSpeed = Math.max(hitSpeed, Math.abs(v));
          x = Math.max(stopLo, Math.min(stopHi, x));
          v = 0;
        }
      }
      double g = kind == TunableSystem.Kind.ELEVATOR ? kG
          : kind == TunableSystem.Kind.PIVOT ? kG * Math.cos(x * radPerUnit) : 0;
      if ((x >= stopHi && u - g > 1) || (x <= stopLo && u - g < -1)) {
        pushedIntoStopS += dt;
      }
      if (++steps == freezeAfter) {
        frozen = reading();
      }
      lowest = Math.min(lowest, x);
      highest = Math.max(highest, x);
      fastest = Math.max(fastest, Math.abs(v));
      motor.feedbackPos = x;
      motor.feedbackVel = v;
    }

    /** Where its sensor says it is. */
    double reading() {
      if (!Double.isNaN(frozen)) {
        return frozen;
      }
      return count > 0 ? Math.round(x / count) * count : x;
    }
  }

  final MotorGuard guard = new MotorGuard();
  double now;

  TunableSystem system(Plant p, String name, String units) {
    TunableSystem s = new TunableSystem(name, p.kind).units(units).motors(name)
        .velocity(() -> p.v).goal(g -> {}).stop(() -> {});
    if (p.kind.positional) {
      s.position(p::reading);
    }
    return s;
  }

  TestContext ctx(TunableSystem s, List<MotorGuard.Motor> motors, String[] keys, double[] values) {
    TestContext c = new TestContext(new FakeDrivetrain(), TestArgs.of(keys, values), TestEnvironment.BLOCKS,
        new int[] {0, 1, 2, 3}, 1.0, 1.0, 1.0, false, Sampler.create(20000), true, () -> true, () -> null);
    c.systems = List.of(s);
    c.motors = motors;
    return c;
  }

  /** Runs it to the end, the plant moving between loops; the reason it stopped, or null when it finished. */
  String run(SystemIdProcedure proc, TestContext c, Plant p) {
    now = 0;
    assertNull(proc.validate(c));
    proc.start(c);
    c.sampler.start(() -> now);
    String why = null;
    for (; now < proc.timeoutS(c); now += 0.02) {
      boolean done = proc.execute(c, now);
      why = proc.abortReason(c);
      if (done || why != null) {
        break;
      }
      c.sampler.sampleNow();  // as the robot's sampler: where it is, and the volts it is about to hold
      p.step(0.02);
    }
    proc.end(c, why != null);
    c.sampler.stop();
    return why == null && now >= proc.timeoutS(c) ? "timed out" : why;
  }

  static double[] col(TestContext c, String name) {
    Map<String, double[]> m = c.sampler.snapshot();
    assertTrue(m.containsKey(name), name);
    return m.get(name);
  }

  @Test
  void itPausesTheRobotsCodeAndRunsOnBlocksOrInTheSimulatorOnly() {
    SystemIdProcedure p = new SystemIdProcedure();
    assertTrue(p.pausesRobotCode(), "its subsystem would set the same motors every loop");
    assertTrue(p.spinsWheels(), "deadman and heartbeat apply");
    assertTrue(p.allowedIn(TestEnvironment.BLOCKS));
    assertTrue(p.allowedIn(TestEnvironment.SIM));
    assertFalse(p.allowedIn(TestEnvironment.FIELD));
  }

  @Test
  void itNeedsLimitsATopSpeedAndALeader() {
    Plant p = new Plant(TunableSystem.Kind.ELEVATOR, 0.1, 3.8, 0.067, 0.65);
    TunableSystem s = system(p, "Elevator", "meters");
    List<MotorGuard.Motor> ms = List.of(guard.register("Elevator", p.motor, MotorKind.VORTEX, false));
    SystemIdProcedure proc = new SystemIdProcedure();
    assertNotNull(proc.validate(ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 1.5})), "no limits");
    s.setLimits(0, 1.18, "slothtune.json");
    assertNotNull(proc.validate(ctx(s, ms, new String[] {"system"}, new double[] {0})), "no top speed");
    assertNull(proc.validate(ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 1.5})));
    p.motor.follower = true;
    assertNotNull(proc.validate(ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 1.5})),
        "a follower alone: its leader isn't listed");
    assertNotNull(proc.validate(ctx(s, List.of(), new String[] {"system", "vmax"}, new double[] {0, 1.5})),
        "no motor the guard watches");
  }

  @Test
  void anElevatorOnItsBottomStopFindsItsHoldAndStaysInside() {
    Plant p = new Plant(TunableSystem.Kind.ELEVATOR, 0.1, 3.8, 0.067, 0.65);
    p.stopLo = 0;
    p.stopHi = 1.18;
    p.motor.coastNow = true;
    FakeMotorChannel follower = new FakeMotorChannel(40);
    follower.follower = true;
    TunableSystem s = system(p, "Elevator", "meters").motors("Elevator follower");
    s.setLimits(0, 1.18, "slothtune.json");
    List<MotorGuard.Motor> ms = List.of(guard.register("Elevator", p.motor, MotorKind.VORTEX, false),
        guard.register("Elevator follower", follower, MotorKind.VORTEX, false));
    TestContext c = ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 1.5});
    String why = run(new SystemIdProcedure(), c, p);
    assertNull(why, why);
    Map<String, Double> meta = c.meta();
    // Seen once it is moving, a little past each edge of the band; the hold between them is what counts.
    assertEquals(0.65 + 0.1 + 0.05, meta.get("u_up"), 0.07, "motion up starts above gravity plus friction");
    assertEquals(0.65 - 0.1 - 0.05, meta.get("u_dn"), 0.07, "and down below gravity less friction");
    assertEquals(0.65, meta.get("u_hold"), 0.06);
    assertTrue(p.lowest >= 0 && p.highest <= 1.18 - 0.02, "never past its window: " + p.highest);
    assertTrue(p.highest > 1.0, "the sweeps cross its travel: " + p.highest);
    double[] stage = col(c, "stage");
    for (SystemIdProcedure.Stage st : List.of(SystemIdProcedure.Stage.FIND, SystemIdProcedure.Stage.SWEEP,
        SystemIdProcedure.Stage.STEP, SystemIdProcedure.Stage.HOLD)) {
      assertTrue(java.util.Arrays.stream(stage).anyMatch(x -> x == st.ordinal()), st + " recorded");
    }
    for (String ch : List.of("pos", "vel", "cmd", "batt", "spos", "svel", "volts0", "bus0", "amps0", "volts1")) {
      col(c, ch);
    }
    assertTrue(Double.isNaN(follower.testVolts), "a follower is never driven: it would leave follow mode");
    assertEquals(meta.get("u_hold"), p.motor.testVolts, 0.3, "it holds until its code is back");
    assertEquals(List.of(false, true), p.motor.coastCalls, "brake for the test, then coast as it was");
    assertEquals(List.of(SystemIdProcedure.SIGNAL_MS, 0), p.motor.signalCalls, "fast signals, then put back");
    assertEquals(List.of(SystemIdProcedure.SIGNAL_MS, 0), follower.signalCalls);
  }

  @Test
  void aSlowHeavyElevatorStartingMidwayAlsoFinishes() {
    Plant p = new Plant(TunableSystem.Kind.ELEVATOR, 0.15, 9.0, 0.35, 0.45);
    p.x = 0.5;
    p.stopLo = 0;
    p.stopHi = 1.0;
    TunableSystem s = system(p, "Lift", "meters");
    s.setLimits(0, 1.0, "moved by hand");
    List<MotorGuard.Motor> ms = List.of(guard.register("Lift", p.motor, MotorKind.NEO_V1_1, false));
    TestContext c = ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 1.0});
    String why = run(new SystemIdProcedure(), c, p);
    assertNull(why, why);
    assertEquals(0.45, c.meta().get("u_hold"), 0.08);
    assertTrue(p.lowest >= 0.0 && p.highest <= 1.0, p.lowest + " to " + p.highest);
  }

  @Test
  void anArmWhoseGravityChangesWithItsAngleStaysInside() {
    double deg = Math.PI / 180;
    Plant p = new Plant(TunableSystem.Kind.PIVOT, 0.1, 1.2 * deg, 0.08 * deg, 0.6);
    p.radPerUnit = deg;
    p.x = 3.6;  // resting on its stop, where its lower limit was found by hand
    p.stopLo = 3.6;
    p.stopHi = 111.6;
    TunableSystem s = system(p, "Shooter pivot", "degrees");
    s.setLimits(3.6, 111.6, "slothtune.json");
    List<MotorGuard.Motor> ms = List.of(guard.register("Shooter pivot", p.motor, MotorKind.NEO_V1_1, false));
    TestContext c = ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 120});
    String why = run(new SystemIdProcedure(), c, p);
    assertNull(why, why);
    // Past 90 degrees its gravity pulls the other way: braking at the hold found low down would carry it
    // into its stop. The map's hold and the governor stop it inside its window.
    assertTrue(p.highest < 111.6 - 1, "never reaches its stop: " + p.highest);
    assertTrue(p.lowest > 3.6 - 1e-9, "nor its low one: " + p.lowest);
    assertTrue(p.highest > 95, "the sweeps cross its travel: " + p.highest);
  }

  /** An arm on the test's own travel (3.6 to 111.6 degrees, past straight up), resting on its low stop. */
  Plant arm(double kS, double kA, double kG) {
    double deg = Math.PI / 180;
    Plant p = new Plant(TunableSystem.Kind.PIVOT, kS, 1.2 * deg, kA * deg, kG);
    p.radPerUnit = deg;
    p.x = 3.6;
    p.stopLo = 3.6;
    p.stopHi = 111.6;
    return p;
  }

  String runArm(Plant p) {
    TunableSystem s = system(p, "Shooter pivot", "degrees");
    s.setLimits(3.6, 111.6, "slothtune.json");
    // Its own guard: one test runs several arms under the same name.
    List<MotorGuard.Motor> ms = List.of(new MotorGuard().register("Shooter pivot", p.motor, MotorKind.NEO_V1_1, false));
    return run(new SystemIdProcedure(), ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 120}), p);
  }

  @Test
  void aStrongArmNeverStrikesAStop() {
    // The code review's cases: with gravity at 1.5 V, and at 2 V with three times the inertia and
    // little friction, braking at a hold measured low down drove it into its stops at up to half its
    // top speed, and the run still finished. Whatever it ends with, it never strikes a stop.
    for (double[] c : new double[][] {{0.1, 0.08, 1.5}, {0.03, 0.24, 2.0}, {0.1, 0.08, 0.6}}) {
      Plant p = arm(c[0], c[1], c[2]);
      String why = runArm(p);
      String what = "kS " + c[0] + ", kA " + c[1] + ", kG " + c[2] + ": " + why;
      assertTrue(p.hitSpeed < 0.02 * 120, "struck a stop at " + p.hitSpeed + " deg/s; " + what);
      assertTrue(p.fastest < 0.95 * 120, "never near its top speed: " + p.fastest + "; " + what);
      if (why == null) {
        assertTrue(p.highest > 90, "a finished run crossed its travel: " + p.highest + "; " + what);
      }
    }
  }

  @Test
  void anArmRestingOnItsHighStopIsntPushedIntoIt() {
    // Past straight up its gravity holds it on its high stop: the seesaw starts toward the middle.
    Plant p = arm(0.1, 0.08, 1.2);
    p.x = 111.6;
    String why = runArm(p);
    assertTrue(p.pushedIntoStopS < 0.3, "pushed into its stop for " + p.pushedIntoStopS + " s; " + why);
    assertTrue(p.hitSpeed < 0.02 * 120, "struck a stop at " + p.hitSpeed);
  }

  @Test
  void anElevatorRestingOnItsTopStopIsntPushedIntoIt() {
    Plant p = new Plant(TunableSystem.Kind.ELEVATOR, 0.1, 3.8, 0.067, 0.65);
    p.stopLo = 0;
    p.stopHi = 1.18;
    p.x = 1.18;
    TunableSystem s = system(p, "Elevator", "meters");
    s.setLimits(0, 1.18, "slothtune.json");
    List<MotorGuard.Motor> ms = List.of(guard.register("Elevator", p.motor, MotorKind.VORTEX, false));
    String why = run(new SystemIdProcedure(), ctx(s, ms, new String[] {"system", "vmax", "hold"}, new double[] {0, 1.5, 0.65}), p);
    assertTrue(p.pushedIntoStopS < 0.3, "pushed into its stop for " + p.pushedIntoStopS + " s; " + why);
    assertTrue(p.hitSpeed < 0.02 * 1.5, "struck a stop at " + p.hitSpeed);
  }

  @Test
  void aCoarseSensorStillFindsTheBand() {
    // A NEO's hall sensor on a slow elevator: one count is 1 mm, and a count's flicker isn't motion.
    Plant p = new Plant(TunableSystem.Kind.ELEVATOR, 0.1, 3.8, 0.067, 0.65);
    p.count = 0.001;
    p.stopLo = 0;
    p.stopHi = 1.18;
    TunableSystem s = system(p, "Elevator", "meters");
    s.setLimits(0, 1.18, "slothtune.json");
    List<MotorGuard.Motor> ms = List.of(guard.register("Elevator", p.motor, MotorKind.VORTEX, false));
    TestContext c = ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 1.5});
    String why = run(new SystemIdProcedure(), c, p);
    assertNull(why, why);
    assertEquals(0.65, c.meta().get("u_hold"), 0.08);
    assertTrue(p.hitSpeed < 0.02 * 1.5, "struck a stop at " + p.hitSpeed);
  }

  @Test
  void aFrozenPositionReadingStopsIt() {
    // Its sensor drops out mid-sweep: the code's position stops changing, its motor's encoder doesn't.
    Plant p = new Plant(TunableSystem.Kind.ELEVATOR, 0.1, 3.8, 0.067, 0.65);
    p.stopLo = 0;
    p.stopHi = 1.18;
    TunableSystem s = system(p, "Elevator", "meters");
    s.setLimits(0, 1.18, "slothtune.json");
    List<MotorGuard.Motor> ms = List.of(guard.register("Elevator", p.motor, MotorKind.VORTEX, false));
    TestContext c = ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 1.5});
    // Find where the sweeps are under way, then freeze there.
    SystemIdProcedure proc = new SystemIdProcedure();
    p.freezeAfter = 400;
    String why = run(proc, c, p);
    assertNotNull(why, "it noticed");
    assertTrue(why.contains("stopped changing"), why);
    assertTrue(p.hitSpeed < 0.02 * 1.5, "stopped before it struck a stop: " + p.hitSpeed);
  }

  @Test
  void itRecordsALeaderFirst() {
    Plant p = new Plant(TunableSystem.Kind.ELEVATOR, 0.1, 3.8, 0.067, 0.65);
    p.stopLo = 0;
    p.stopHi = 1.18;
    FakeMotorChannel follower = new FakeMotorChannel(40);
    follower.follower = true;
    TunableSystem s = system(p, "Elevator", "meters").motors("Elevator follower");
    s.setLimits(0, 1.18, "slothtune.json");
    // The follower registered first: volts0 must still be the motor it drives.
    List<MotorGuard.Motor> ms = List.of(guard.register("Elevator follower", follower, MotorKind.VORTEX, false),
        guard.register("Elevator", p.motor, MotorKind.VORTEX, false));
    TestContext c = ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 1.5});
    assertNull(run(new SystemIdProcedure(), c, p));
    assertTrue(c.notes().stream().anyMatch(n -> n.startsWith("motor 0: Elevator (driven)")), c.notes().toString());
  }

  @Test
  void aFlywheelRampsUpAndDownAndEndsAtRest() {
    Plant p = new Plant(TunableSystem.Kind.FLYWHEEL, 0.2, 0.002, 0.0006, 0);
    TunableSystem s = system(p, "Shooter", "RPM");
    List<MotorGuard.Motor> ms = List.of(guard.register("Shooter", p.motor, MotorKind.VORTEX, false));
    // 85% of 5000 RPM needs about 9 V on this one.
    TestContext c = ctx(s, ms, new String[] {"system", "vmax", "volts_max"}, new double[] {0, 5000, 11});
    String why = run(new SystemIdProcedure(), c, p);
    assertNull(why, why);
    assertTrue(p.fastest > 0.8 * 5000 && p.fastest < 5000, "near its top speed, never past: " + p.fastest);
    assertTrue(c.meta().containsKey("peak_0"));
    assertEquals(0, p.motor.testVolts, 1e-9, "it coasts down when done");
    double[] cmd = col(c, "cmd");
    assertTrue(java.util.Arrays.stream(cmd).allMatch(u -> u >= -1e-9), "one way only for a flywheel");
    assertTrue(p.motor.coastCalls.isEmpty(), "a flywheel's idle mode is left alone");
  }

  @Test
  void aRollerGoesBothWays() {
    Plant p = new Plant(TunableSystem.Kind.ROLLER, 0.2, 0.002, 0.0003, 0);
    TunableSystem s = system(p, "Feeder", "RPM");
    List<MotorGuard.Motor> ms = List.of(guard.register("Feeder", p.motor, MotorKind.NEO_V1_1, false));
    TestContext c = ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 4000});
    assertNull(run(new SystemIdProcedure(), c, p));
    double[] cmd = col(c, "cmd");
    assertTrue(java.util.Arrays.stream(cmd).anyMatch(u -> u < -1), "and back");
  }

  @Test
  void anInvertedMotorStopsItBeforeItLeavesItsTravel() {
    Plant p = new Plant(TunableSystem.Kind.ELEVATOR, 0.1, 3.8, 0.067, 0.65);
    p.reversed = true;
    p.x = 0.6;
    p.stopLo = 0;
    p.stopHi = 1.18;
    TunableSystem s = system(p, "Elevator", "meters");
    s.setLimits(0, 1.18, "slothtune.json");
    List<MotorGuard.Motor> ms = List.of(guard.register("Elevator", p.motor, MotorKind.VORTEX, false));
    TestContext c = ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 1.5});
    String why = run(new SystemIdProcedure(), c, p);
    assertNotNull(why);
    assertTrue(why.contains("inversion"), why);
    assertTrue(p.fastest < 0.5 * 1.5, "stopped before it got fast: " + p.fastest);
  }

  @Test
  void aJammedMechanismStopsIt() {
    Plant p = new Plant(TunableSystem.Kind.ELEVATOR, 50, 3.8, 0.067, 0.65);
    TunableSystem s = system(p, "Elevator", "meters");
    s.setLimits(0, 1.18, "slothtune.json");
    List<MotorGuard.Motor> ms = List.of(guard.register("Elevator", p.motor, MotorKind.VORTEX, false));
    TestContext c = ctx(s, ms, new String[] {"system", "vmax"}, new double[] {0, 1.5});
    String why = run(new SystemIdProcedure(), c, p);
    assertNotNull(why);
    assertTrue(why.contains("didn't start moving"), why);
    assertTrue(Math.abs(p.motor.testVolts) <= SystemIdProcedure.FIND_CAP + 0.1);
  }
}
