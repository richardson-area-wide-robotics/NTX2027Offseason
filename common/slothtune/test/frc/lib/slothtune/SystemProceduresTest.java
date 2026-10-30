package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import edu.wpi.first.networktables.DoublePublisher;
import edu.wpi.first.networktables.IntegerPublisher;
import edu.wpi.first.networktables.NetworkTableInstance;
import java.util.ArrayList;
import java.util.List;
import java.util.function.DoubleConsumer;
import java.util.function.DoubleUnaryOperator;
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
    /** What its sensor reports for where it is: exactly that, until a test breaks it. */
    DoubleUnaryOperator sensor = x -> x;
    /** Something holds it: it stays where it is whatever its goal. */
    boolean jammed;

    TunableSystem system() {
      TunableSystem s = new TunableSystem("Intake pivot", TunableSystem.Kind.PIVOT)
          .units("rot").position(() -> sensor.applyAsDouble(pos)).velocity(() -> vel).motors("Intake pivot")
          .goal(g -> {
            goal = g;
            goals.add(g);
          })
          .stop(() -> stops++);
      return s;
    }

    void step(double dt) {
      if (jammed) {
        vel = 0;
        return;
      }
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

  @Test
  void enablingTheRobotWhileItIsMovedByHandStopsItAndPutsItsMotorsBack() {
    Pivot p = new Pivot();
    TunableSystem s = p.system();
    SystemLimitsProcedure proc = new SystemLimitsProcedure();
    TestContext c = ctx(s, new String[] {"system"}, new double[] {0});
    assertNull(proc.validate(c));
    proc.start(c);
    for (double x : new double[] {5, 2, 9}) {
      p.pos = x;
      assertFalse(proc.execute(c, 1));
      assertNull(proc.abortReason(c));
    }
    enabled = true;  // someone enables it with hands on the mechanism: its code would drive it
    String why = proc.abortReason(c);
    assertNotNull(why, "it ends at once");
    assertTrue(why.contains("enabled") && why.contains("idle mode"), why);
    proc.end(c, true);  // as the harness does after a stop
    assertEquals(List.of(true, false), motor.coastCalls, "back to brake, as it was");
    assertFalse(s.hasLimits(), "a run cut short sets no limits");
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

  /** When {@link #runStep} stopped, seconds into the test. */
  double stoppedAt;

  /**
   * Runs the closed-loop test as the harness does (its stop checked, then a loop), the pivot moving
   * between loops and {@code each} called after every move; why it stopped, or null when it finished.
   */
  String runStep(SystemStepProcedure proc, TestContext c, Pivot p, DoubleConsumer each) {
    proc.start(c);
    for (double t = 0; t < 60; t += 0.01) {
      stoppedAt = t;
      String why = proc.abortReason(c);
      if (why != null) {
        return why;
      }
      if (proc.execute(c, t)) {
        return null;
      }
      p.step(0.01);
      each.accept(t + 0.01);
    }
    return "timed out";
  }

  static final String[] STEP_KEYS = {"system", "vmax", "amax", "a", "b", "hold_s"};
  static final double[] STEP_ARGS = {0, 4, 20, 4, 14, 0.2};

  @Test
  void aLostPositionReadingStopsTheClosedLoopTest() {
    Pivot p = new Pivot();
    TunableSystem s = p.system();
    s.setLimits(0, 18, "moved by hand");
    SystemStepProcedure proc = new SystemStepProcedure();
    enabled = true;
    TestContext c = ctx(s, STEP_KEYS, STEP_ARGS);
    proc.start(c);
    assertNull(proc.abortReason(c));
    p.sensor = x -> Double.NaN;  // its sensor unplugged: the code reads NaN
    String why = proc.abortReason(c);
    assertNotNull(why, "it can't keep it inside its limits blind");
    assertTrue(why.contains("can't read Intake pivot's position"), why);
  }

  @Test
  void aFrozenPositionReadingStopsTheClosedLoopTest() {
    // Its sensor drops out mid-move: the code's position stops changing, its SPARK's encoder doesn't.
    Pivot p = new Pivot();
    TunableSystem s = p.system();
    s.setLimits(0, 18, "moved by hand");
    SystemStepProcedure proc = new SystemStepProcedure();
    enabled = true;
    double[] froze = {Double.NaN, Double.NaN};
    String why = runStep(proc, ctx(s, STEP_KEYS, STEP_ARGS), p, t -> {
      motor.feedbackPos = 25 * p.pos;  // the SPARK's own encoder, in motor rotations
      if (t >= 1.5 && Double.isNaN(froze[0])) {
        double at = p.pos;
        p.sensor = x -> at;
        froze[0] = t;
        froze[1] = at;
      }
    });
    assertNotNull(why, "it noticed");
    assertTrue(why.contains("stopped changing"), why);
    assertTrue(stoppedAt - froze[0] < SystemIdProcedure.FROZEN_S + 0.1, "promptly: " + (stoppedAt - froze[0]));
    assertTrue(p.pos - froze[1] < 3, "it went on blind only a little: " + (p.pos - froze[1]));
  }

  @Test
  void aJammedMechanismStopsTheClosedLoopTestButHardWorkWhileMovingDoesNot() {
    // Drawing high current all the way, moving and holding at its goals: no jam.
    motor.demandA = 60;
    Pivot free = new Pivot();
    TunableSystem s = free.system();
    s.setLimits(0, 18, "moved by hand");
    enabled = true;
    assertNull(runStep(new SystemStepProcedure(), ctx(s, STEP_KEYS, STEP_ARGS), free, t -> {}));
    // Something catches it halfway: the goal moves on, it doesn't, and its loop pushes harder.
    motor.demandA = 0;
    Pivot p = new Pivot();
    TunableSystem s2 = p.system();
    s2.setLimits(0, 18, "moved by hand");
    double[] jammedAt = {Double.NaN};
    String why = runStep(new SystemStepProcedure(), ctx(s2, STEP_KEYS, STEP_ARGS), p, t -> {
      if (t >= 1.5 && !p.jammed) {
        p.jammed = true;
        motor.demandA = 60;
        jammedAt[0] = t;
      }
    });
    assertNotNull(why, "it noticed");
    assertTrue(why.contains("jammed"), why);
    double after = stoppedAt - jammedAt[0];
    assertTrue(after >= SystemIdProcedure.STALL_S && after < SystemIdProcedure.STALL_S + 0.15, "after " + after);
    // A flywheel that won't turn while its motor pulls hard: the same.
    FakeMotorChannel shooter = new FakeMotorChannel(60);
    shooter.demandA = 60;
    TunableSystem fly = new TunableSystem("Shooter", TunableSystem.Kind.FLYWHEEL).units("RPM").motors("Shooter")
        .velocity(() -> 0).goal(g -> {}).stop(() -> {});
    TestContext c = ctx(fly, new String[] {"system", "vmax", "amax", "a", "b"}, new double[] {0, 3000, 2000, 2000, 3000});
    c.motors = List.of(new MotorGuard().register("Shooter", shooter, MotorKind.VORTEX, false));
    SystemStepProcedure proc = new SystemStepProcedure();
    proc.start(c);
    String flyWhy = null;
    for (double t = 0; t < 2 && flyWhy == null; t += 0.01) {
      proc.execute(c, t);
      flyWhy = proc.abortReason(c);
    }
    assertNotNull(flyWhy, "a flywheel jam");
    assertTrue(flyWhy.contains("jammed"), flyWhy);
  }

  // ---------------------------------------------------------------- a stop that throws
  @Test
  void aMechanismWhoseStopThrowsHasItsMotorsZeroedAndTheErrorReported() {
    FakeMotorChannel follower = new FakeMotorChannel(60);
    follower.follower = true;
    Pivot p = new Pivot();
    TunableSystem s = p.system().motors("Intake pivot follower").stop(() -> {
      throw new IllegalStateException("its stop is broken");
    });
    s.setLimits(0, 18, "moved by hand");
    SystemStepProcedure proc = new SystemStepProcedure();
    enabled = true;
    TestContext c = ctx(s, STEP_KEYS, STEP_ARGS);
    c.motors = List.of(guarded, guard.register("Intake pivot follower", follower, MotorKind.VORTEX, false));
    proc.start(c);
    proc.execute(c, 0);
    assertThrows(IllegalStateException.class, () -> proc.end(c, true), "reported, not swallowed");
    assertEquals(0, motor.testDuty, 1e-12, "its motor set to zero output directly");
    assertEquals(0, follower.testDutyCalls, "a follower follows its leader: commanding it would end that");
    assertTrue(c.notes().stream().anyMatch(n -> n.contains("its stop is broken") && n.contains("set to zero output")),
        c.notes().toString());
  }

  @Test
  void aHoldWhoseStopThrowsHasItsMotorZeroed() {
    FakeMotorChannel roller = new FakeMotorChannel(40);
    MotorGuard.Motor m = guard.register("Intake roller", roller, MotorKind.NEO_V1_1, false);
    HoldCurrent h = new HoldCurrent("Intake roller", m, d -> {
      if (d == 0) {
        throw new IllegalStateException("its setter is broken");
      }
    });
    TestContext c = ctx(new Pivot().system(), new String[] {"hold"}, new double[] {0});
    c.holds = List.of(h);
    c.motors = List.of(guarded, m);
    HoldProcedure proc = new HoldProcedure();
    enabled = true;
    assertNull(proc.validate(c));
    proc.start(c);
    proc.execute(c, 0);  // seating, holding at its start current
    assertThrows(IllegalStateException.class, () -> proc.end(c, true), "reported, not swallowed");
    assertEquals(0, roller.testDuty, 1e-12, "its motor set to zero output directly");
    assertEquals(0, m.holdAmps(), "its normal limit back");
    assertTrue(c.notes().stream().anyMatch(n -> n.contains("its setter is broken") && n.contains("zero output")),
        c.notes().toString());
  }

  @Test
  void aPieceTestWhoseStopThrowsHasItsMotorsZeroed() {
    FakeMotorChannel roller = new FakeMotorChannel(40);
    MotorGuard.Motor m = guard.register("Intake roller", roller, MotorKind.NEO_V1_1, false);
    double[] speed = {0};
    TunableSystem s = new TunableSystem("Intake roller", TunableSystem.Kind.ROLLER).units("RPM")
        .motors("Intake roller").velocity(() -> speed[0]).goal(g -> speed[0] = g).stop(() -> {
          throw new IllegalStateException("its stop is broken");
        });
    TestContext c = ctx(s, new String[] {"sensor", "system", "goal"}, new double[] {0, 0, 2000});
    c.currentSensors = List.of(new CurrentSensor("Intake has piece", "Intake roller", m, null));
    c.motors = List.of(m);
    PieceSenseProcedure proc = new PieceSenseProcedure();
    enabled = true;
    assertNull(proc.validate(c));
    proc.start(c);
    assertThrows(IllegalStateException.class, () -> proc.end(c, true), "reported, not swallowed");
    assertEquals(0, roller.testDuty, 1e-12, "its motor set to zero output directly");
  }

  @Test
  void aMechanismInMetersIsWordedInInchesAndItsNumbersStayInMeters() {
    Pivot p = new Pivot();
    TunableSystem s = p.system().units("meters");
    assertEquals("in", s.shownUnits());
    assertEquals(39.37, s.shown(1), 0.01);
    assertEquals("deg", new TunableSystem("Arm", TunableSystem.Kind.PIVOT).units("radians").shownUnits());
    assertEquals("RPM", new TunableSystem("Shooter", TunableSystem.Kind.FLYWHEEL).units("RPM").shownUnits());
    assertEquals(3000, new TunableSystem("Shooter", TunableSystem.Kind.FLYWHEEL).units("RPM").shown(3000), 1e-12);
    s.setLimits(0, 18, "moved by hand");
    SystemStepProcedure proc = new SystemStepProcedure();
    enabled = true;
    TestContext c = ctx(s, new String[] {"system", "vmax", "amax", "a", "b"}, new double[] {0, 4, 20, 4, 14});
    proc.start(c);
    p.pos = 18.8;
    String why = proc.abortReason(c);
    assertTrue(why.contains("(740.157, limits 0.000 to 708.661 in)"), why);
    assertEquals(18, s.max, 1e-12, "the limits stay in the mechanism's own units");
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

  // ---------------------------------------------------------------- homing
  /** A pivot whose saved limits (0 to 18) were found on another boot: this boot it reads 5 at its lower end. */
  TunableSystem unhomedPivot(Pivot p) {
    TunableSystem s = p.system();
    s.setLimits(0, 18, "slothtune.json");
    s.homed = false;  // as SlothTune#system leaves it on a real robot
    return s;
  }

  @Test
  void anUnhomedPivotIsNeverMovedByATest() {
    Pivot p = new Pivot();
    TunableSystem s = unhomedPivot(p);
    enabled = true;
    String why = new SystemStepProcedure().validate(
        ctx(s, new String[] {"system", "vmax", "amax", "a", "b"}, new double[] {0, 5, 20, 4, 14}));
    assertNotNull(why);
    assertTrue(why.startsWith("Home Intake pivot first"), why);
    assertTrue(new SystemIdProcedure().validate(ctx(s, new String[] {"system", "vmax"}, new double[] {0, 5}))
        .startsWith("Home Intake pivot first"));
  }

  @Test
  void homingAtTheLowerEndMovesTheSavedLimitsIntoThisBootsReadings() {
    Pivot p = new Pivot();  // it rests at its lower end, reading 5
    TunableSystem s = unhomedPivot(p);
    SystemHomeProcedure proc = new SystemHomeProcedure();
    TestContext c = ctx(s, new String[] {"system", "end"}, new double[] {0, 0});
    assertNull(proc.validate(c));
    proc.start(c);
    double t = 0;
    while (!proc.execute(c, t)) {
      assertNull(proc.abortReason(c));
      t += 0.02;
    }
    proc.end(c, false);
    assertTrue(s.homed);
    assertEquals(5, s.min, 1e-9);
    assertEquals(23, s.max, 1e-9, "the same range, shifted by what its encoder reads now");
    assertNull(new SystemStepProcedure().validate(
        ctx(s, new String[] {"system", "vmax", "amax", "a", "b"}, new double[] {0, 5, 20, 8, 18})));
  }

  @Test
  void homingAtTheUpperEndUsesTheUpperLimit() {
    Pivot p = new Pivot();
    p.pos = 16;  // held at its upper end, which was saved as 18
    TunableSystem s = unhomedPivot(p);
    SystemHomeProcedure proc = new SystemHomeProcedure();
    TestContext c = ctx(s, new String[] {"system", "end"}, new double[] {0, 1});
    proc.start(c);
    for (double t = 0; !proc.execute(c, t); t += 0.02) {
      assertNull(proc.abortReason(c));
    }
    proc.end(c, false);
    assertEquals(-2, s.min, 1e-9);
    assertEquals(16, s.max, 1e-9);
  }

  @Test
  void homingRefusesWhileEnabledWithoutSavedLimitsOrForAFlywheel() {
    Pivot p = new Pivot();
    TunableSystem s = unhomedPivot(p);
    SystemHomeProcedure proc = new SystemHomeProcedure();
    enabled = true;
    assertTrue(proc.validate(ctx(s, new String[] {"system", "end"}, new double[] {0, 0})).startsWith("Disable"));
    enabled = false;
    TunableSystem none = new Pivot().system();
    none.homed = false;
    assertTrue(proc.validate(ctx(none, new String[] {"system", "end"}, new double[] {0, 0})).contains("no saved limits"));
    TunableSystem wheel = new TunableSystem("Shooter", TunableSystem.Kind.FLYWHEEL);
    assertTrue(proc.validate(ctx(wheel, new String[] {"system", "end"}, new double[] {0, 0})).contains("spins freely"));
  }

  @Test
  void homingStopsIfItMovesOrTheRobotIsEnabledAndLeavesItUnhomed() {
    Pivot p = new Pivot();
    TunableSystem s = unhomedPivot(p);
    SystemHomeProcedure proc = new SystemHomeProcedure();
    TestContext c = ctx(s, new String[] {"system", "end"}, new double[] {0, 0});
    proc.start(c);
    proc.execute(c, 0);
    p.pos = 5.5;  // still being moved: 0.5 of an 18 range is more than 1%
    proc.execute(c, 0.02);
    String why = proc.abortReason(c);
    assertNotNull(why);
    assertTrue(why.contains("hold it still"), why);
    proc.end(c, true);
    assertFalse(s.homed);
    assertEquals(0, s.min, 1e-12, "limits untouched");

    p.pos = 5;
    proc.start(c);
    proc.execute(c, 0);
    enabled = true;
    assertTrue(proc.abortReason(c).contains("enabled"));
    proc.end(c, true);
    assertFalse(s.homed);
  }

  // ---------------------------------------------------------------- limits by hand: the two readings agree
  /** Moves it through {@code path} by hand while its motor's own encoder reads {@code encoder(pos)}. */
  TestContext movedByHand(Pivot p, TunableSystem s, java.util.function.DoubleUnaryOperator encoder, double[] path) {
    SystemLimitsProcedure proc = new SystemLimitsProcedure();
    TestContext c = ctx(s, new String[] {"system"}, new double[] {0});
    proc.start(c);
    for (double x : path) {
      p.pos = x;
      motor.feedbackPos = encoder.applyAsDouble(x);
      proc.execute(c, 1);
    }
    proc.requestStop();
    proc.execute(c, 2);
    proc.end(c, false);
    return c;
  }

  static double[] sweep() {
    double[] path = new double[40];
    for (int i = 0; i < path.length; i++) {
      path[i] = i < 20 ? i : 39 - i;  // up to 19 and back
    }
    return path;
  }

  @Test
  void movedByHandItsReadingAndItsMotorsEncoderAgree() {
    Pivot p = new Pivot();
    TunableSystem s = p.system();
    TestContext c = movedByHand(p, s, x -> -3 * x + 7, sweep());  // geared, other units, the other way: still a line
    assertEquals(1.0, Math.abs(c.meta().get("sensor_r")), 1e-9);
    assertEquals(-3.0, c.meta().get("sensor_ratio"), 1e-9);
    assertFalse(c.notes().stream().anyMatch(n -> n.contains("didn't move together")), c.notes().toString());
  }

  @Test
  void aSlippingBeltShowsAsTheTwoReadingsDisagreeing() {
    Pivot p = new Pivot();
    TunableSystem s = p.system();
    // The belt skips on the way back: the motor's encoder stops following past halfway.
    double[] path = sweep();
    SystemLimitsProcedure proc = new SystemLimitsProcedure();
    TestContext c = ctx(s, new String[] {"system"}, new double[] {0});
    proc.start(c);
    for (int i = 0; i < path.length; i++) {
      p.pos = path[i];
      motor.feedbackPos = i < 30 ? path[i] : path[29];
      proc.execute(c, 1);
    }
    proc.requestStop();
    proc.execute(c, 2);
    proc.end(c, false);
    assertTrue(Math.abs(c.meta().get("sensor_r")) < SystemLimitsProcedure.AGREE_R, c.meta().toString());
    assertTrue(c.notes().stream().anyMatch(n -> n.contains("didn't move together")), c.notes().toString());
  }
}
