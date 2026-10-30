package frc.lib.slothtune;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.networktables.DoubleArrayPublisher;
import edu.wpi.first.networktables.DoublePublisher;
import edu.wpi.first.networktables.IntegerPublisher;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StringArrayPublisher;
import edu.wpi.first.networktables.StringPublisher;
import frc.lib.slothtune.ManeuverCatalog.Maneuver;
import java.util.List;
import org.junit.jupiter.api.Test;

/** The accuracy maneuvers driven on the fake drivetrain: leg by leg, inside the floor, to the plan. */
class ManeuverProcedureTest {
  private static final double DT = 0.02;

  private static TestContext context(FakeDrivetrain io, double cap, double forward, double side, TestArgs args) {
    return new TestContext(io, args, TestEnvironment.FIELD, new int[] {0, 1, 2, 3}, cap, forward, side,
        false, Sampler.create(64), true, () -> true, () -> null);
  }

  private static TestArgs index(int i) {
    return TestArgs.empty().with("index", i);
  }

  /** What one run did, from the outside. */
  static final class Run {
    boolean done;
    String stopped;
    double maxWheelMps;
    double maxFromStartM;
    TestContext ctx;
    ManeuverProcedure proc;

    double meta(String key) {
      Double v = ctx.meta().get(key);
      return v == null ? Double.NaN : v;
    }
  }

  /** The harness's order each loop: the procedure's own stop, then a step, then the physics. */
  private static Run run(FakeDrivetrain io, TestContext c) {
    Run r = new Run();
    r.ctx = c;
    r.proc = new ManeuverProcedure();
    assertNull(r.proc.validate(c));
    double limit = r.proc.timeoutS(c);
    r.proc.start(c);
    double x0 = io.x;
    double y0 = io.y;
    double t = 0;
    while (t < limit) {
      String stop = r.proc.abortReason(c);
      if (stop != null) {
        r.stopped = stop;
        break;
      }
      if (r.proc.execute(c, t)) {
        r.done = true;
        break;
      }
      io.step(DT);
      t += DT;
      for (int m = 0; m < 4; m++) {
        r.maxWheelMps = Math.max(r.maxWheelMps, Math.abs(io.speed[m]));
      }
      r.maxFromStartM = Math.max(r.maxFromStartM, Math.hypot(io.x - x0, io.y - y0));
    }
    r.proc.end(c, !r.done);
    return r;
  }

  @Test
  void everyManeuverEndsWhereThePlanSaysOnPerfectWheels() {
    // The fake's odometry is the truth, so what is left is the closed loop's own residual.
    List<Maneuver> all = ManeuverCatalog.all();
    for (int i = 0; i < all.size(); i++) {
      Maneuver m = all.get(i);
      FakeDrivetrain io = new FakeDrivetrain();
      io.heading = 30; // the plan is in the start's frame, wherever the robot faces
      Run r = run(io, context(io, 1.5, 10, 10, index(i)));
      assertTrue(r.done, m.name() + " stopped: " + r.stopped);
      assertEquals(1, r.meta("complete"), 1e-9, m.name());
      assertEquals(m.legs().size(), r.meta("legs_done"), 1e-9, m.name());
      Pose2d plan = ManeuverCatalog.expectedPose(new Pose2d(), m.legs());
      assertEquals(plan.getX(), r.meta("expected_x"), 1e-9, m.name());
      assertEquals(plan.getY(), r.meta("expected_y"), 1e-9, m.name());
      double off = Math.hypot(r.meta("end_x") - plan.getX(), r.meta("end_y") - plan.getY());
      assertTrue(off < m.budgetM(), m.name() + " ended " + off + " m from the plan, budget " + m.budgetM());
      double heading = ManeuverProcedure.wrapDeg(r.meta("end_deg") - plan.getRotation().getDegrees());
      assertEquals(0, heading, 0.5, m.name());
      assertEquals(m.totalTurnDeg(), r.meta("gyro_turned_deg"), 1.0 * m.legs().size(), m.name());
      for (int k = 0; k < m.legs().size(); k++) {
        assertEquals(1, r.meta("leg" + k + "_settled"), 1e-9, m.name() + " leg " + k);
      }
    }
  }

  @Test
  void theLegsGoInTheCatalogsMetaForTheLaptop() {
    FakeDrivetrain io = new FakeDrivetrain();
    Run r = run(io, context(io, 1.0, 10, 10, index(20)));
    Maneuver square = ManeuverCatalog.byIndex(20);
    assertEquals(20, r.meta("maneuver_index"), 1e-9);
    assertEquals(square.id(), r.meta("maneuver_id"), 1e-9);
    assertEquals(ManeuverCatalog.Family.DIFFERENT_PATH.ordinal(), r.meta("family"), 1e-9);
    assertEquals(1, r.meta("returns"), 1e-9);
    assertEquals(8, r.meta("legs"), 1e-9);
    assertEquals(0, r.meta("leg0_turn"), 1e-9);
    assertEquals(ManeuverCatalog.FIVE_FEET_M, r.meta("leg0_value"), 1e-9);
    assertEquals(1, r.meta("leg1_turn"), 1e-9);
    assertEquals(90, r.meta("leg1_value"), 1e-9);
    assertEquals(square.budgetM(), r.meta("budget_m"), 1e-9);
    assertTrue(r.ctx.notes().get(0).contains("OB_diff_square5ft"), r.ctx.notes().toString());
    assertTrue(r.ctx.notes().stream().anyMatch(n -> n.contains("measure where its center stopped")),
        "without AprilTags it asks for a tape");
  }

  @Test
  void aManeuverThatDoesNotFitTheFloorIsRefused() {
    FakeDrivetrain io = new FakeDrivetrain();
    ManeuverProcedure p = new ManeuverProcedure();
    // 10 ft out and 10 ft to the side, plus room for the robot's corners as it turns.
    String why = p.validate(context(io, 1.0, 3.0, 3.0, index(0)));
    assertNotNull(why);
    assertTrue(why.contains("P_10ft_L90_fwd10ft") && why.contains("clear floor"), why);
    assertNull(p.validate(context(io, 1.0, 3.7, 3.7, index(0))));
    // A straight out-and-back needs little to the side.
    assertNull(p.validate(context(io, 1.0, 3.7, 0.6, index(16))));
    assertNotNull(p.validate(context(io, 1.0, 3.7, 0.6, index(20))));
  }

  @Test
  void itIsPickedByIndexOrById() {
    FakeDrivetrain io = new FakeDrivetrain();
    ManeuverProcedure p = new ManeuverProcedure();
    assertTrue(p.validate(context(io, 1, 10, 10, TestArgs.empty())).startsWith("Pick a maneuver"));
    assertTrue(p.validate(context(io, 1, 10, 10, index(25))).startsWith("No maneuver at index 25"));
    assertTrue(p.validate(context(io, 1, 10, 10, TestArgs.empty().with("index", 2.5)))
        .startsWith("No maneuver at index 2.5"));
    assertTrue(p.validate(context(io, 1, 10, 10, TestArgs.empty().with("id", 12345)))
        .startsWith("No maneuver has that id"));
    TestContext byId = context(io, 1, 10, 10, TestArgs.empty().with("id", 131818226));
    assertNull(p.validate(byId));
    p.start(byId);
    assertEquals(20, byId.meta().get("maneuver_index"), 1e-9, "OB_diff_square5ft, found by its id");
  }

  @Test
  void onlyOnTheFloor() {
    ManeuverProcedure p = new ManeuverProcedure();
    assertTrue(p.allowedIn(TestEnvironment.FIELD));
    assertFalse(p.allowedIn(TestEnvironment.BLOCKS));
    assertFalse(p.allowedIn(TestEnvironment.SIM));
    assertFalse(p.allowedIn(TestEnvironment.UNSET));
    assertTrue(p.spinsWheels() && p.movesChassis(null));
  }

  @Test
  void neverFasterThanTheCapAndInsideItsOwnFence() {
    FakeDrivetrain io = new FakeDrivetrain();
    int i = ManeuverCatalog.all().indexOf(ManeuverCatalog.all().stream()
        .filter(m -> m.name().equals("P_10ft_L270_rev10ft")).findFirst().orElseThrow());
    TestContext c = context(io, 0.8, 10, 10,
        index(i).with("speed", 4.0).with("turn_dps", 360).with("accel", 3.0));
    Run r = run(io, c);
    assertTrue(r.done, r.stopped);
    assertTrue(r.maxWheelMps <= 0.8 + 0.02, "wheels reached " + r.maxWheelMps + " m/s");
    assertEquals(0.8, r.meta("speed"), 1e-9, "asked for 4 m/s, held to the cap");
    double fence = new ManeuverProcedure().spaceBudgetM(context(io, 0.8, 10, 10, index(i)));
    assertTrue(r.maxFromStartM < fence, r.maxFromStartM + " m out, fence " + fence);
    assertTrue(fence < Math.hypot(ManeuverCatalog.TEN_FEET_M, ManeuverCatalog.TEN_FEET_M) + 0.5);
  }

  @Test
  void aPoseThatStopsChangingStopsTheRun() {
    FakeDrivetrain io = new FakeDrivetrain();
    io.chassisMoves = false; // wheels turn, the robot goes nowhere: odometry the run can't steer by
    Run r = run(io, context(io, 1.0, 10, 10, index(16)));
    assertFalse(r.done);
    assertNotNull(r.stopped);
    assertTrue(r.stopped.contains("pose stopped changing"), r.stopped);
    assertEquals(0, r.meta("complete"), 1e-9);
    assertTrue(io.stopped, "the wheels are stopped");
  }

  @Test
  void profilePositionCoversTheDistance() {
    assertEquals(0, ManeuverProcedure.profilePosition(0, 3, 1, 1), 1e-12);
    assertEquals(3, ManeuverProcedure.profilePosition(99, 3, 1, 1), 1e-12);
    double total = StraightLineProcedure.profileSeconds(3, 1, 1);
    double covered = 0;
    for (double t = 0; t < total; t += 0.0005) {
      covered += StraightLineProcedure.profileSpeed(t, 3, 1, 1) * 0.0005;
      assertEquals(covered, ManeuverProcedure.profilePosition(t + 0.0005, 3, 1, 1), 0.01);
    }
  }

  // ------------------------------------------------------------------ through the harness

  @Test
  void theHarnessRunsItOnTheFloorWithTheDeadmanAndRefusesItOnBlocks() {
    NetworkTableInstance nt = NetworkTableInstance.create();
    try {
      FakeDrivetrain io = new FakeDrivetrain();
      double[] now = {100.0};
      SlothTuneHarnessTest.Signals ds = new SlothTuneHarnessTest.Signals();
      SlothTuneHarnessTest.Ownership owner = new SlothTuneHarnessTest.Ownership();
      SlothTune tune = new SlothTune(io, nt, ds, () -> now[0], "test robot", SlothTuneConfig.parse("{}"),
          false, owner, true);
      IntegerPublisher seq = nt.getIntegerTopic(SlothTuneTopics.CMD_SEQ).publish();
      IntegerPublisher boot = nt.getIntegerTopic(SlothTuneTopics.CMD_BOOT_ID).publish();
      StringPublisher test = nt.getStringTopic(SlothTuneTopics.CMD_TEST).publish();
      StringPublisher module = nt.getStringTopic(SlothTuneTopics.CMD_MODULE).publish();
      StringArrayPublisher keys = nt.getStringArrayTopic(SlothTuneTopics.CMD_ARG_KEYS).publish();
      DoubleArrayPublisher vals = nt.getDoubleArrayTopic(SlothTuneTopics.CMD_ARG_VALUES).publish();
      StringPublisher env = nt.getStringTopic(SlothTuneTopics.ENV_MODE).publish();
      DoublePublisher fwd = nt.getDoubleTopic(SlothTuneTopics.ENV_SPACE_FORWARD).publish();
      DoublePublisher side = nt.getDoubleTopic(SlothTuneTopics.ENV_SPACE_SIDE).publish();
      DoublePublisher hb = nt.getDoubleTopic(SlothTuneTopics.CLIENT_HEARTBEAT).publish();
      double[] beat = {0};
      Runnable tick = () -> {
        io.step(DT);
        now[0] += DT;
        hb.set(++beat[0]);
        tune.periodic();
      };
      long[] n = {0};
      Runnable send = () -> {
        keys.set(new String[] {"index"});
        vals.set(new double[] {17}); // OB_same_straight5ft
        test.set("maneuver");
        module.set("ALL");
        boot.set(tune.bootId());
        seq.set(++n[0]);
      };
      var ackOk = nt.getBooleanTopic(SlothTuneTopics.ACK_ACCEPTED).subscribe(false);
      var ackMsg = nt.getStringTopic(SlothTuneTopics.ACK_MESSAGE).subscribe("");

      env.set("BLOCKS");
      io.chassisMoves = false;
      ds.deadman = true;
      tick.run();
      send.run();
      tick.run();
      assertFalse(ackOk.get());
      assertTrue(ackMsg.get().contains("cannot run") && ackMsg.get().contains("on the floor"), ackMsg.get());

      env.set("FIELD");
      io.chassisMoves = true;
      fwd.set(3.0);
      side.set(1.0);
      ds.deadman = false;
      tick.run();
      send.run();
      for (int i = 0; i < 10; i++) {
        tick.run();
      }
      assertTrue(ackOk.get(), ackMsg.get());
      assertEquals(SlothTune.State.WAITING, tune.state(), "nothing moves until the deadman is held");
      ds.deadman = true;
      for (int i = 0; i < 1500 && tune.state() != SlothTune.State.DONE; i++) {
        tick.run();
      }
      assertEquals(SlothTune.State.DONE, tune.state(), tune.message());
      String[] metaKeys = nt.getStringArrayTopic(SlothTuneTopics.RESULT_META_KEYS).subscribe(new String[0]).get();
      assertTrue(List.of(metaKeys).containsAll(List.of("end_x", "end_y", "end_deg", "expected_x", "budget_m")));
      assertFalse(owner.held, "the driver gets the robot back");
    } finally {
      nt.close();
    }
  }
}
