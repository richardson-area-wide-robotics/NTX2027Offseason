package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import edu.wpi.first.math.geometry.Transform3d;
import edu.wpi.first.networktables.BooleanPublisher;
import edu.wpi.first.networktables.DoubleEntry;
import edu.wpi.first.networktables.DoubleArrayPublisher;
import edu.wpi.first.networktables.DoublePublisher;
import edu.wpi.first.networktables.IntegerPublisher;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StringArrayPublisher;
import edu.wpi.first.networktables.StringPublisher;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * The harness end to end, over a real (local) NetworkTables instance, with this test playing both
 * the laptop tool and the Driver Station.
 */
class SwerveTuneHarnessTest {
  private NetworkTableInstance nt;
  private FakeDrivetrain io;
  private SwerveTune tune;
  private final double[] now = {100.0};
  private final Signals ds = new Signals();
  private final Ownership owner = new Ownership();
  private long seq;
  private double heartbeat;

  private IntegerPublisher cmdSeq;
  private IntegerPublisher cmdBoot;
  private StringPublisher cmdTest;
  private StringPublisher cmdModule;
  private StringArrayPublisher argKeys;
  private DoubleArrayPublisher argValues;
  private StringPublisher envMode;
  private DoublePublisher spaceFwd;
  private DoublePublisher spaceSide;
  private DoublePublisher hb;
  private BooleanPublisher guiDeadman;

  static final class Signals implements RobotSignals {
    boolean enabled = true;
    boolean auto;
    boolean fms;
    double stick;
    boolean deadman;

    @Override
    public boolean enabled() {
      return enabled;
    }

    @Override
    public boolean autonomous() {
      return auto;
    }

    @Override
    public boolean testMode() {
      return false;
    }

    @Override
    public boolean eStopped() {
      return false;
    }

    @Override
    public boolean fmsAttached() {
      return fms;
    }

    @Override
    public double driverStickMax() {
      return stick;
    }

    double[] port1Axes = {0.02, -0.01, 0, 0, 0, 0};
    int port1Buttons;

    @Override
    public double[] stickAxes(int port) {
      return port == 1 ? port1Axes.clone() : new double[0];
    }

    @Override
    public int stickButtons(int port) {
      return port == 1 ? port1Buttons : 0;
    }

    @Override
    public String stickName(int port) {
      return port == 1 ? "Controller (Xbox One For Windows)" : "";
    }

    @Override
    public boolean controllerDeadman() {
      return deadman;
    }
  }

  static final class Ownership implements DriveOwnership {
    int acquired;
    int released;
    boolean held;

    @Override
    public void acquire() {
      acquired++;
      held = true;
    }

    @Override
    public void release() {
      released++;
      held = false;
    }

    @Override
    public boolean isHeld() {
      return held;
    }
  }

  @BeforeEach
  void setUp() {
    nt = NetworkTableInstance.create();
    io = new FakeDrivetrain();
    SwerveTuneConfig config = SwerveTuneConfig.parse(
        "{\"driveFeedforward\": {\"backright\": {\"kS\": 0.2, \"kV\": 2.5, \"kA\": 0.4}},"
        + " \"cameras\": {\"front\": {\"x\": 0.3, \"y\": -0.1, \"z\": 0.5, \"pitch\": -15, \"yaw\": 10},"
        + " \"rear\": {\"x\": 0.3}}, \"advantageScopeTuning\": true}");
    tune = new SwerveTune(io, nt, ds, () -> now[0], "test robot", config, false, owner, true);
    cmdSeq = nt.getIntegerTopic(SwerveTuneTopics.CMD_SEQ).publish();
    cmdBoot = nt.getIntegerTopic(SwerveTuneTopics.CMD_BOOT_ID).publish();
    cmdTest = nt.getStringTopic(SwerveTuneTopics.CMD_TEST).publish();
    cmdModule = nt.getStringTopic(SwerveTuneTopics.CMD_MODULE).publish();
    argKeys = nt.getStringArrayTopic(SwerveTuneTopics.CMD_ARG_KEYS).publish();
    argValues = nt.getDoubleArrayTopic(SwerveTuneTopics.CMD_ARG_VALUES).publish();
    envMode = nt.getStringTopic(SwerveTuneTopics.ENV_MODE).publish();
    spaceFwd = nt.getDoubleTopic(SwerveTuneTopics.ENV_SPACE_FORWARD).publish();
    spaceSide = nt.getDoubleTopic(SwerveTuneTopics.ENV_SPACE_SIDE).publish();
    hb = nt.getDoubleTopic(SwerveTuneTopics.CLIENT_HEARTBEAT).publish();
    guiDeadman = nt.getBooleanTopic(SwerveTuneTopics.CLIENT_DEADMAN).publish();
  }

  @AfterEach
  void tearDown() {
    nt.close();
  }

  /** On blocks, as a person would set it up: the chassis held still, the deadman held. */
  private void onBlocks() {
    envMode.set("BLOCKS");
    io.chassisMoves = false;
    ds.deadman = true;
  }

  private void loop(int n) {
    for (int i = 0; i < n; i++) {
      io.step(0.02);
      now[0] += 0.02;
      hb.set(++heartbeat);
      tune.periodic();
    }
  }

  private void send(String test, String module, String... args) {
    String[] keys = new String[args.length / 2];
    double[] vals = new double[args.length / 2];
    for (int i = 0; i < keys.length; i++) {
      keys[i] = args[2 * i];
      vals[i] = Double.parseDouble(args[2 * i + 1]);
    }
    argKeys.set(keys);
    argValues.set(vals);
    cmdTest.set(test);
    cmdModule.set(module);
    cmdBoot.set(tune.bootId());
    cmdSeq.set(++seq);
  }

  private String ackMessage() {
    return nt.getStringTopic(SwerveTuneTopics.ACK_MESSAGE).subscribe("").get();
  }

  private boolean ackAccepted() {
    return nt.getBooleanTopic(SwerveTuneTopics.ACK_ACCEPTED).subscribe(false).get();
  }

  private long resultSeq() {
    return nt.getIntegerTopic(SwerveTuneTopics.RESULT_SEQ).subscribe(-1).get();
  }

  private double[] data(String channel) {
    return nt.getDoubleArrayTopic(SwerveTuneTopics.RESULT_DATA + channel).subscribe(new double[0]).get();
  }

  @Test
  void aCommandTakingTheDrivetrainMidTestStopsIt() {
    onBlocks();
    loop(2);
    send("steer_step", "FL", "hold_s", "0.3", "settle_s", "0.2");
    loop(10);
    assertEquals(SwerveTune.State.RUNNING, tune.state(), tune.message());
    owner.held = false; // a button bound to the drive subsystem took it
    loop(2);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertTrue(tune.message().contains("Another command took the drivetrain"), tune.message());
  }

  @Test
  void steerStepOnBlocksRunsToTheEndAndPublishesEverySample() {
    onBlocks();
    loop(2);
    send("steer_step", "FL", "hold_s", "0.3", "settle_s", "0.2");
    loop(1);
    assertTrue(ackAccepted(), ackMessage());
    loop(200);
    assertEquals(SwerveTune.State.DONE, tune.state(), tune.message());
    assertEquals(seq, resultSeq());
    double[] sp = data("m0.sp");
    double[] steer = data("m0.steer");
    assertTrue(sp.length > 100, "one row per loop with manual sampling");
    assertEquals(sp.length, steer.length);
    double start = sp[0];
    assertTrue(Arrays.stream(sp).anyMatch(v -> Math.abs(v - (start + 90)) < 1e-6), "the 90 degree step ran");
    assertEquals(1, owner.acquired);
    assertFalse(owner.held, "the driver gets the robot back");
    assertTrue(io.stopped);
    List<String> channels = Arrays.asList(
        nt.getStringArrayTopic(SwerveTuneTopics.RESULT_CHANNELS).subscribe(new String[0]).get());
    assertEquals("t", channels.get(0));
    assertTrue(channels.contains("m0.motor"));
    assertFalse(channels.contains("m1.sp"), "only the module asked for");
  }

  @Test
  void aHotSteeringMotorStopsATestAndSaysWhich() {
    onBlocks();
    loop(2);
    send("steer_step", "FL", "hold_s", "2", "settle_s", "0.5");
    loop(1);
    assertTrue(ackAccepted(), ackMessage());
    loop(10);
    assertEquals(SwerveTune.State.RUNNING, tune.state(), tune.message());
    io.steerMotors[1].tempC = 56; // a NEO 550 past its 55 C derate line
    loop(3);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertTrue(tune.message().contains("frontright steer") && tune.message().contains("cool"),
        tune.message());
    String[] names = nt.getStringArrayTopic(SwerveTuneTopics.MOTORS_NAMES).subscribe(new String[0]).get();
    String[] stages = nt.getStringArrayTopic(SwerveTuneTopics.MOTORS_STAGE).subscribe(new String[0]).get();
    assertEquals("frontright steer", names[1]);
    assertEquals("DERATE", stages[1]);
    assertEquals(10, io.steerMotors[1].limit, "half of its 20 A");
    assertFalse(owner.held, "the driver gets the robot back");
  }

  @Test
  void aThermalOverrideFromTheLaptopIsAcknowledgedOnlyForThisBoot() {
    loop(2);
    IntegerPublisher oSeq = nt.getIntegerTopic(SwerveTuneTopics.MOTORS_OVERRIDE_SEQ).publish();
    IntegerPublisher oBoot = nt.getIntegerTopic(SwerveTuneTopics.MOTORS_OVERRIDE_BOOT_ID).publish();
    StringPublisher oName = nt.getStringTopic(SwerveTuneTopics.MOTORS_OVERRIDE_NAME).publish();
    DoublePublisher oSecs = nt.getDoubleTopic(SwerveTuneTopics.MOTORS_OVERRIDE_SECONDS).publish();
    var ack = nt.getStringTopic(SwerveTuneTopics.MOTORS_OVERRIDE_ACK_MESSAGE).subscribe("");
    oName.set("ALL");
    oSecs.set(15);
    oBoot.set(tune.bootId() + 1);
    oSeq.set(1);
    loop(2);
    assertTrue(ack.get().contains("earlier boot"), ack.get());
    oBoot.set(tune.bootId());
    oSeq.set(2);
    loop(2);
    assertTrue(ack.get().contains("Thermal override for every motor: 15 s"), ack.get());
    double[] left = nt.getDoubleArrayTopic(SwerveTuneTopics.MOTORS_OVERRIDE_S).subscribe(new double[0]).get();
    assertEquals(4, left.length);
    assertTrue(left[0] > 14 && left[0] <= 15, Arrays.toString(left));
  }

  private double meta(String key) {
    String[] keys = nt.getStringArrayTopic(SwerveTuneTopics.RESULT_META_KEYS).subscribe(new String[0]).get();
    double[] vals = nt.getDoubleArrayTopic(SwerveTuneTopics.RESULT_META_VALUES).subscribe(new double[0]).get();
    for (int i = 0; i < keys.length; i++) {
      if (keys[i].equals(key)) {
        return vals[i];
      }
    }
    return Double.NaN;
  }

  private String notes() {
    return String.join(" | ", nt.getStringArrayTopic(SwerveTuneTopics.RESULT_NOTES).subscribe(new String[0]).get());
  }

  @Test
  void slipTestFindsEachWheelsBreakawayAndPutsTheLimitBack() {
    double[] truth = {38, 42, 45, 41};
    io.wallSlipA = truth.clone();
    envMode.set("FIELD");
    ds.deadman = true;
    loop(2);
    send("slip", "ALL", "ceiling_a", "80"); // over the 60 A policy for a NEO of unknown version
    loop(1);
    assertTrue(ackAccepted(), ackMessage());
    loop(900);
    assertEquals(SwerveTune.State.DONE, tune.state(), tune.message() + " " + notes());
    for (int m = 0; m < 4; m++) {
      assertEquals(truth[m], meta("slip_a_m" + m), 0.5, "module " + m);
      assertTrue(io.slipping[m]);
    }
    assertEquals(60, meta("ceiling_a"), 1e-9, "never above the policy");
    assertEquals(List.of(60, 40), io.limitsSet, "raised for the run, then put back");
    assertEquals(0, meta("wall_lost"), 1e-9);
    assertFalse(owner.held);
  }

  @Test
  void aCarpetThatOutgripsTheCeilingIsReportedNotForced() {
    io.wallSlipA = new double[] {70, 70, 70, 70};
    envMode.set("FIELD");
    ds.deadman = true;
    loop(2);
    send("slip", "ALL", "ceiling_a", "50");
    loop(1);
    assertTrue(ackAccepted(), ackMessage());
    loop(900);
    assertEquals(SwerveTune.State.DONE, tune.state(), tune.message());
    for (int m = 0; m < 4; m++) {
      assertTrue(Double.isNaN(meta("slip_a_m" + m)), "nothing slipped");
      assertEquals(50, meta("peak_a_m" + m), 0.5);
    }
    assertEquals(40, io.driveLimitA, 1e-9);
  }

  @Test
  void slipTestStopsIfTheRobotIsNotAgainstAWall() {
    envMode.set("FIELD");
    ds.deadman = true;
    loop(2);
    send("slip", "ALL");
    loop(1);
    assertTrue(ackAccepted(), ackMessage());
    loop(200);
    assertEquals(SwerveTune.State.DONE, tune.state(), tune.message());
    assertEquals(1, meta("wall_lost"), 1e-9);
    assertTrue(notes().contains("driving, not slipping"), notes());
    assertEquals(40, io.driveLimitA, 1e-9);
  }

  @Test
  void slipTestIsRefusedOnBlocks() {
    onBlocks();
    loop(2);
    send("slip", "ALL");
    loop(1);
    assertFalse(ackAccepted());
    assertTrue(ackMessage().contains("cannot run"), ackMessage());
  }

  @Test
  void aCommandForAnEarlierRobotProgramIsIgnored() {
    onBlocks();
    loop(1);
    cmdTest.set("steer_step");
    cmdModule.set("ALL");
    cmdBoot.set(tune.bootId() + 1);
    cmdSeq.set(++seq);
    loop(3);
    assertFalse(ackAccepted());
    assertTrue(ackMessage().contains("earlier run"));
    assertEquals(SwerveTune.State.IDLE, tune.state());
  }

  @Test
  void motionNeedsADeclaredEnvironment() {
    loop(1);
    send("steer_step", "ALL");
    loop(2);
    assertFalse(ackAccepted());
    assertTrue(ackMessage().contains("Say where the robot is"), ackMessage());
  }

  @Test
  void straightLineIsRefusedOnBlocks() {
    onBlocks();
    loop(1);
    send("straight", "ALL");
    loop(2);
    assertFalse(ackAccepted());
    assertTrue(ackMessage().contains("on the floor"), ackMessage());
  }

  @Test
  void aSecondCommandWhileBusyIsRefusedAndTheFirstCarriesOn() {
    onBlocks();
    loop(1);
    send("steer_step", "ALL");
    loop(5);
    send("drive_step", "ALL");
    loop(1);
    assertFalse(ackAccepted());
    assertTrue(ackMessage().startsWith("Busy"));
    assertEquals(SwerveTune.State.RUNNING, tune.state());
  }

  @Test
  void disablingMidRunAbortsCleanlyAndStillPublishesTheData() {
    onBlocks();
    loop(1);
    send("steer_step", "ALL");
    loop(30);
    ds.enabled = false;
    loop(2);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertTrue(tune.message().contains("disabled"));
    assertEquals(seq, resultSeq());
    assertEquals("ABORTED", nt.getStringTopic(SwerveTuneTopics.RESULT_OUTCOME).subscribe("").get());
    assertTrue(data("m0.sp").length > 10);
    assertFalse(owner.held);
  }

  @Test
  void theChassisTurningOnBlocksStopsTheTest() {
    onBlocks();
    loop(1);
    send("drive_step", "ALL");
    loop(10);
    io.injectedYawRate = 60;
    loop(20);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertTrue(tune.message().contains("NOT on blocks"), tune.message());
  }

  @Test
  void onBlocksNothingSpinsUntilTheDeadmanIsHeld() {
    onBlocks();
    ds.deadman = false;
    loop(1);
    send("drive_step", "ALL");
    loop(10);
    assertTrue(ackAccepted(), ackMessage());
    assertEquals(SwerveTune.State.WAITING, tune.state());
    assertTrue(tune.message().contains("deadman"), tune.message());
    assertEquals(0, io.speed[0], 1e-9);
    ds.deadman = true;
    loop(30); // the lift check first: a 0.12 s pulse, then the wheels coast still
    assertEquals(SwerveTune.State.RUNNING, tune.state(), tune.message());
    loop(10);
    ds.deadman = false;
    loop(1);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertTrue(tune.message().contains("Deadman released"), tune.message());
  }

  @Test
  void aRobotOnTheFloorCalledBlocksStopsWhenItsWheelsCarryIt() {
    // B1 in the review: a drive test on carpet, told "blocks", drove 1.4 m without one abort.
    onBlocks();
    io.chassisMoves = true; // it is really on the floor,
    // so each wheel speeds up like one pushing a quarter of a 55 kg robot (kA/kV, about 0.13 s). The
    // lift check is an open-loop pulse, so whatever gains the test would use don't matter.
    io.driveLagS = 0.13;
    loop(1);
    send("drive_step", "ALL");
    loop(200);
    assertEquals(SwerveTune.State.ABORTED, tune.state(), tune.message());
    assertTrue(tune.message().startsWith("NOT on blocks"), tune.message());
    // The lift check stops it before the test itself starts: a pulse of a few centimeters.
    assertTrue(tune.message().contains("short pulse"), tune.message());
    double travel = Math.hypot(io.x, io.y);
    assertTrue(travel < 0.15, "stopped within a few centimeters: " + travel);
  }

  @Test
  void onBlocksTheLiftCheckPassesAndTheTestRuns() {
    onBlocks();
    loop(1);
    send("drive_step", "ALL");
    loop(3);
    assertEquals(SwerveTune.State.WAITING, tune.state());
    assertTrue(tune.message().contains("off the floor"), tune.message());
    loop(30);
    assertEquals(SwerveTune.State.RUNNING, tune.state(), tune.message());
  }

  @Test
  void lettingGoMidPulseStopsTheLiftCheck() {
    onBlocks();
    loop(1);
    send("drive_step", "ALL");
    loop(4); // inside the 0.12 s pulse
    ds.deadman = false;
    loop(1);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertTrue(tune.message().startsWith("Stopped during the lift check"), tune.message());
    assertEquals(0, io.volts[0], 1e-9, "the motors stopped");
  }

  @Test
  void aSteeringTestOnBlocksNeedsNoLiftCheck() {
    onBlocks();
    loop(1);
    send("steer_step", "FL", "hold_s", "0.3", "settle_s", "0.2");
    loop(3);
    assertEquals(SwerveTune.State.RUNNING, tune.state(), tune.message());
  }

  @Test
  void onTheFieldNothingMovesUntilTheDeadmanIsHeld() {
    envMode.set("FIELD");
    spaceFwd.set(6);
    spaceSide.set(6);
    loop(1);
    send("drive_step", "ALL");
    loop(10);
    assertTrue(ackAccepted(), ackMessage());
    assertEquals(SwerveTune.State.WAITING, tune.state());
    assertTrue(tune.message().contains("deadman"));
    assertEquals(0, io.speed[0], 1e-9);
    ds.deadman = true;
    loop(3);
    assertEquals(SwerveTune.State.RUNNING, tune.state());
    loop(20);
    ds.deadman = false;
    loop(1);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertTrue(tune.message().contains("Deadman released"));
  }

  @Test
  void guiDeadmanOnlyCountsWhileTheLaptopIsAlive() {
    envMode.set("FIELD");
    spaceFwd.set(6);
    spaceSide.set(6);
    guiDeadman.set(true);
    loop(1);
    send("spin", "ALL");
    loop(5);
    assertEquals(SwerveTune.State.RUNNING, tune.state(), tune.message());
    // the laptop freezes: heartbeat stops, deadman topic still reads true
    for (int i = 0; i < 40; i++) {
      io.step(0.02);
      now[0] += 0.02;
      tune.periodic();
    }
    assertEquals(SwerveTune.State.ABORTED, tune.state());
  }

  @Test
  void driverTouchingTheSticksTakesTheRobotBack() {
    onBlocks();
    loop(1);
    send("drive_step", "ALL");
    loop(10);
    ds.stick = 0.6;
    loop(1);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertFalse(owner.held);
  }

  @Test
  void captureRunsDisabledAndCoastIsAlwaysUndone() {
    ds.enabled = false;
    loop(1);
    send("capture", "ALL", "duration_s", "0.5", "coast", "1");
    loop(40);
    assertEquals(SwerveTune.State.DONE, tune.state(), tune.message());
    assertEquals(List.of("coast=true", "coast=false"),
        io.applied.stream().filter(s -> s.startsWith("coast")).toList());
    assertEquals(0, owner.acquired, "a capture never takes the drivetrain");
  }

  @Test
  void enablingWhileCoastingEndsTheCapture() {
    ds.enabled = false;
    loop(1);
    send("capture", "ALL", "duration_s", "30", "coast", "1");
    loop(5);
    ds.enabled = true;
    loop(2);
    assertEquals(SwerveTune.State.DONE, tune.state());
    assertFalse(io.coast);
  }

  @Test
  void liveGainsApplyTogetherAndRefuseOutOfRangeGroupsWhole() {
    loop(1);
    DoublePublisher kp = nt.getDoubleTopic(SwerveTuneTopics.GAINS + "Steer/kP").publish();
    DoublePublisher kd = nt.getDoubleTopic(SwerveTuneTopics.GAINS + "Steer/kD").publish();
    DoublePublisher driveKp = nt.getDoubleTopic(SwerveTuneTopics.GAINS + "Drive/kP").publish();
    IntegerPublisher apply = nt.getIntegerTopic(SwerveTuneTopics.GAINS_APPLY_SEQ).publish();
    IntegerPublisher boot = nt.getIntegerTopic(SwerveTuneTopics.GAINS_BOOT_ID).publish();
    kp.set(0.02);
    kd.set(0.05);
    driveKp.set(50); // absurd
    boot.set(tune.bootId());
    apply.set(1);
    loop(2);
    assertArrayEquals(new double[] {0.02, 0, 0.05, 0}, io.steerPid, 1e-12);
    assertEquals(0.002, io.drivePid[0], 1e-12, "the out-of-range group never reached the motor");
    String status = nt.getStringTopic(SwerveTuneTopics.GAINS_APPLY_STATUS).subscribe("").get();
    assertTrue(status.contains("REFUSED") && status.contains("Drive/kP"), status);
    double echoed = nt.getDoubleTopic(SwerveTuneTopics.GAINS_APPLIED + "Drive/kP").subscribe(-1).get();
    assertEquals(0.002, echoed, 1e-12, "the echo shows what is really running");
  }

  @Test
  void onePodsGainsChangeThatPodOnlyAndTheSharedGainsResetEveryPod() {
    loop(1);
    String fl = io.moduleName(0);
    DoublePublisher podKp = nt.getDoubleTopic(SwerveTuneTopics.GAINS + "Pod/" + fl + "/Steer/kP").publish();
    DoublePublisher kp = nt.getDoubleTopic(SwerveTuneTopics.GAINS + "Steer/kP").publish();
    IntegerPublisher apply = nt.getIntegerTopic(SwerveTuneTopics.GAINS_APPLY_SEQ).publish();
    IntegerPublisher boot = nt.getIntegerTopic(SwerveTuneTopics.GAINS_BOOT_ID).publish();
    boot.set(tune.bootId());
    podKp.set(0.03);
    apply.set(1);
    loop(2);
    assertArrayEquals(new double[] {0.03, 0, 0.001, 0}, io.podSteerPid[0], 1e-12, "the pod's own, the rest kept");
    assertNull(io.podSteerPid[1], "the other pods untouched");
    assertEquals(0.01, io.steerPid[0], 1e-12, "the shared gains untouched");
    double echoed = nt.getDoubleTopic(SwerveTuneTopics.GAINS_APPLIED + "Pod/" + fl + "/Steer/kP").subscribe(-1).get();
    assertEquals(0.03, echoed, 1e-12);
    // The shared gains go to every pod, and every pod's echo says so.
    kp.set(0.02);
    apply.set(2);
    loop(2);
    assertNull(io.podSteerPid[0], "the shared gains replaced the pod's own");
    echoed = nt.getDoubleTopic(SwerveTuneTopics.GAINS_APPLIED + "Pod/" + fl + "/Steer/kP").subscribe(-1).get();
    assertEquals(0.02, echoed, 1e-12);
  }

  @Test
  void aPodsOwnGainKeepsTheSharedOnesItDoesNotGive() {
    assertArrayEquals(new double[] {0.03, 0, 0.002, 0},
        SwerveTune.merge(new double[] {0.03, Double.NaN, 0.002, Double.NaN}, new double[] {0.01, 0, 0.001, 0}), 1e-12);
  }

  @Test
  void aGainChangeCarriesItsReasonIntoTheLog() {
    loop(1);
    assertEquals("the values in the files, at startup", tune.gainsReason());
    DoublePublisher kp = nt.getDoubleTopic(SwerveTuneTopics.GAINS + "Steer/kP").publish();
    StringPublisher why = nt.getStringTopic(SwerveTuneTopics.GAINS_REASON).publish();
    IntegerPublisher apply = nt.getIntegerTopic(SwerveTuneTopics.GAINS_APPLY_SEQ).publish();
    IntegerPublisher boot = nt.getIntegerTopic(SwerveTuneTopics.GAINS_BOOT_ID).publish();
    boot.set(tune.bootId());
    kp.set(0.015);
    why.set("Tune tab, advice: Steering overshoots 18%");
    apply.set(1);
    loop(2);
    assertEquals(0.015, io.steerPid[0], 1e-12);
    assertEquals("Tune tab, advice: Steering overshoots 18%", tune.gainsReason());
    kp.set(0.012);
    why.set("");
    apply.set(2);
    loop(2);
    assertEquals("from the laptop, no reason given", tune.gainsReason());
  }

  @Test
  void changingTheEnvironmentMidTestStopsIt() {
    onBlocks();
    loop(2);
    send("steer_step", "FL", "hold_s", "2", "settle_s", "0.5");
    loop(1);
    assertTrue(ackAccepted(), ackMessage());
    loop(10);
    assertEquals(SwerveTune.State.RUNNING, tune.state(), tune.message());
    envMode.set("UNSET"); // what someone would naturally do when it looks wrong
    loop(2);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertTrue(tune.message().contains("environment changed"), tune.message());
    assertTrue(io.stopped);
  }

  @Test
  void noGainChangesWithTheFmsAttached() {
    ds.fms = true;
    loop(1);
    DoublePublisher kp = nt.getDoubleTopic(SwerveTuneTopics.GAINS + "Steer/kP").publish();
    IntegerPublisher apply = nt.getIntegerTopic(SwerveTuneTopics.GAINS_APPLY_SEQ).publish();
    IntegerPublisher boot = nt.getIntegerTopic(SwerveTuneTopics.GAINS_BOOT_ID).publish();
    kp.set(0.02);
    boot.set(tune.bootId());
    apply.set(1);
    loop(2);
    assertEquals(0.01, io.steerPid[0], 1e-12, "a match is no time to change gains");
    String status = nt.getStringTopic(SwerveTuneTopics.GAINS_APPLY_STATUS).subscribe("").get();
    assertTrue(status.contains("REFUSED") && status.contains("FMS"), status);
    double echoed = nt.getDoubleTopic(SwerveTuneTopics.GAINS_APPLIED + "Steer/kP").subscribe(-1).get();
    assertEquals(0.01, echoed, 1e-12);
  }

  @Test
  void aCaptureStopsWhenTheFmsAttaches() {
    ds.enabled = false;
    loop(1);
    send("capture", "ALL", "duration_s", "30");
    loop(5);
    ds.fms = true;
    loop(2);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertTrue(tune.message().contains("FMS"), tune.message());
  }

  @Test
  void startupConfigAppliesMeasuredFeedforwardByModuleName() {
    assertArrayEquals(new double[] {0.2, 2.5, 0.4}, io.ff[3], 1e-12);
    assertArrayEquals(new double[] {0, 2.9, 0}, io.ff[0], 1e-12);
  }

  @Test
  void thePdhMapPulsesOneMotorAtATimeAndRecordsEveryChannel() {
    // Drive motor m on PDH port 2m, steering motor m on port 2m + 1; a steady 3 A on port 20.
    tune.setPdhSource(() -> {
      double[] a = new double[24];
      for (int m = 0; m < 4; m++) {
        a[2 * m] = Math.abs(io.driveVolts(m)) * 0.5;
        a[2 * m + 1] = Math.abs(io.steerSetpointDeg(m) - io.steerDeg(m)) > 1 ? 1.5 : 0;
      }
      a[20] = 3;
      return a;
    });
    io.chassisMoves = false; // on blocks
    onBlocks();
    loop(2);
    send("pdh_map", "ALL");
    loop(1);
    assertTrue(ackAccepted(), ackMessage());
    loop(700);
    assertEquals(SwerveTune.State.DONE, tune.state(), tune.message());
    double[] slot = data("slot");
    double[] on = data("on");
    double[] p2 = data("pdh2");
    assertEquals(24, Arrays.stream(nt.getStringArrayTopic(SwerveTuneTopics.RESULT_CHANNELS)
        .subscribe(new String[0]).get()).filter(c -> c.startsWith("pdh")).count());
    // The PDH snapshot is taken at the start of a loop, so it lags the command by one sample.
    for (int i = 1; i < slot.length; i++) {
      boolean pulsedNowOrJustBefore = (slot[i] == 2 && on[i] == 1) || (slot[i - 1] == 2 && on[i - 1] == 1);
      if (!pulsedNowOrJustBefore) {
        assertTrue(p2[i] < 0.01, "port 2 only draws while its own motor is pulsed (sample " + i + ")");
      }
    }
    assertTrue(Arrays.stream(p2).max().orElse(0) > 1, "and it does draw then");
    assertTrue(io.stopped);
  }

  @Test
  void theControllerCheckRecordsWhatTheRobotReceives() {
    ds.enabled = false;
    loop(2);
    send("controller", "ALL", "port", "1", "duration_s", "1");
    loop(1);
    assertTrue(ackAccepted(), ackMessage());
    for (int i = 0; i < 80 && tune.state() != SwerveTune.State.DONE; i++) {
      ds.port1Buttons = (i / 10) % 2 == 0 ? 0b10 : 0; // B pressed and released
      loop(1);
    }
    assertEquals(SwerveTune.State.DONE, tune.state(), tune.message());
    double[] a0 = data("a0");
    double[] b = data("buttons");
    assertTrue(a0.length > 10);
    assertEquals(0.02, a0[0], 1e-12);
    assertTrue(Arrays.stream(b).anyMatch(v -> v == 2) && Arrays.stream(b).anyMatch(v -> v == 0));
    assertEquals(1, meta("port"), 1e-12);
    assertTrue(notes().contains("Xbox One"), notes());
  }

  @Test
  void theControllerCheckRefusesAnEmptyPort() {
    ds.enabled = false;
    loop(2);
    send("controller", "ALL", "port", "3");
    loop(1);
    assertFalse(ackAccepted());
    assertTrue(ackMessage().contains("No controller on Driver Station port 3"), ackMessage());
  }

  @Test
  void wheelTestsRecordTheBatteryAsThePdhSeesIt() {
    // A 12.6 V battery that sags 20 milliohms per amp; the drive motors draw 3 A per volt.
    double[] amps = {0};
    tune.setPdhSource(() -> new double[24]);
    tune.setPdhPowerSource(() -> new double[] {12.6 - 0.020 * amps[0], amps[0]});
    io.chassisMoves = false;
    onBlocks();
    loop(2);
    send("pdh_map", "ALL");
    loop(1);
    assertTrue(ackAccepted(), ackMessage());
    for (int i = 0; i < 900 && tune.state() != SwerveTune.State.DONE; i++) {
      double sum = 0;
      for (int m = 0; m < 4; m++) {
        sum += Math.abs(io.driveVolts(m)) * 3;
      }
      amps[0] = sum;
      loop(1);
    }
    assertEquals(SwerveTune.State.DONE, tune.state(), tune.message());
    double[] v = data("pdh_v");
    double[] a = data("ibatt");
    assertTrue(v.length > 10 && v.length == a.length);
    assertTrue(Arrays.stream(a).max().orElse(0) > 5, "it saw the motors draw");
    for (int i = 0; i < v.length; i++) {
      assertEquals(12.6 - 0.020 * a[i], v[i], 1e-9, "volts and amps are from the same loop");
    }
    assertTrue(Double.isNaN(meta("comp_volts")), "the fake drivetrain does not compensate");
  }

  @Test
  void onAVortexTheBlocksPulsesDoNotTripTheOverspeedStopAtTheDefaultCap() {
    // 4 V spins a free Vortex wheel at 5.50:1 to 1.64 m/s; the speed cap is 1.0. The stop must
    // allow for the volts the test itself commands, or the PDH finder can never finish.
    io.freeSpeedMps = 4.92;
    tune.setPdhSource(() -> new double[24]);
    io.chassisMoves = false;
    onBlocks();
    loop(2);
    send("pdh_map", "ALL");
    loop(1);
    assertTrue(ackAccepted(), ackMessage());
    loop(700);
    assertEquals(SwerveTune.State.DONE, tune.state(), tune.message());
  }

  @Test
  void thePdhMapRefusesWithoutAPdhToRead() {
    onBlocks();
    loop(2);
    send("pdh_map", "ALL");
    loop(1);
    assertFalse(ackAccepted());
    assertTrue(ackMessage().contains("No PDH currents"), ackMessage());
  }

  @Test
  void cameraMountsComeFromTheConfigAndAnIncompleteOneIsNotUsed() {
    Transform3d front = tune.cameraMount("front").orElseThrow();
    assertEquals(0.3, front.getX(), 1e-12);
    assertEquals(-0.1, front.getY(), 1e-12);
    assertEquals(0.5, front.getZ(), 1e-12);
    assertEquals(-15, Math.toDegrees(front.getRotation().getY()), 1e-9, "pitch, negative looking up");
    assertEquals(10, Math.toDegrees(front.getRotation().getZ()), 1e-9);
    assertTrue(tune.cameraMount("rear").isEmpty(), "x alone is not a mount");
    assertTrue(tune.cameraMount("left").isEmpty());
  }

  private VisionSource oneGoodPose() {
    return new VisionSource() {
      @Override
      public List<Observation> poll() {
        double[] p = io.pose();
        return List.of(new Observation(p[0] + 0.05, p[1], 0.0, p[2], now[0], 2, 0.05, 2.0, "front"));
      }
    };
  }

  @Test
  void visionPosesStayOutOfThePoseEstimatorUntilSwitchedOn() {
    tune.setVisionSource(oneGoodPose());
    loop(10);
    assertEquals(0, io.visionFed.size(), "off by default: a wrong mount would pull the pose off");
    assertEquals(0, tune.visionPosesFed());
  }

  @Test
  void switchedOnAcceptedPosesFeedThePoseEstimatorWithTheirTrust() {
    SwerveTuneConfig on = SwerveTuneConfig.parse("{\"vision\": {\"cameras\": [\"front\"], \"feedPoseEstimator\": true},"
        + " \"cameras\": {\"front\": {\"x\": 0.3, \"y\": 0, \"z\": 0.5}}}");
    tune = new SwerveTune(io, nt, ds, () -> now[0], "test robot", on, false, owner, true);
    tune.setVisionSource(oneGoodPose());
    loop(10);
    assertTrue(io.visionFed.size() >= 5, "fed " + io.visionFed.size());
    double[] f = io.visionFed.get(0);
    assertEquals(0.02 + 0.04 * 4 / 2, f[4], 1e-9, "two tags at 2 m");
    assertEquals(tune.visionPosesFed(), io.visionFed.size());
    assertEquals(List.of("front"), tune.visionCameras());
  }

  @Test
  void everyTagInTheNewestFramesIsPublishedForCalibration() {
    tune.setVisionSource(new VisionSource() {
      @Override
      public List<Observation> poll() {
        return List.of();
      }

      @Override
      public List<TagSighting> sightings() {
        return List.of(new TagSighting("front", 7, 1.5, 0.1, 0.2, 1, 0, 0, 0, 0.05, 12.5),
            new TagSighting("rear", 3, 2.0, -0.4, 0.1, 0, 0, 0, 1, -1, 12.6));
      }
    });
    loop(1);
    double[] flat = nt.getDoubleArrayTopic(SwerveTuneTopics.LIVE_VISION_SIGHTINGS).subscribe(new double[0]).get();
    String[] cams = nt.getStringArrayTopic(SwerveTuneTopics.LIVE_VISION_SIGHTING_CAMERAS).subscribe(new String[0]).get();
    assertEquals(20, flat.length);
    assertArrayEquals(new double[] {7, 1.5, 0.1, 0.2, 1, 0, 0, 0, 0.05, 12.5}, Arrays.copyOf(flat, 10), 1e-12);
    assertEquals(3, flat[10]);
    assertArrayEquals(new String[] {"front", "rear"}, cams);
  }

  private DoubleEntry tuning(String key) {
    return nt.getDoubleTopic(SwerveTuneTopics.TUNING + key).getEntry(Double.NaN);
  }

  private String tuningStatus() {
    return nt.getStringTopic(SwerveTuneTopics.TUNING + "Status").subscribe("").get();
  }

  @Test
  void anAdvantageScopeEditAppliesAndBothViewsAgree() {
    loop(1);
    assertEquals(0.01, tuning("Steer/kP").get(), 1e-12, "AdvantageScope sees what is running");
    tuning("Steer/kP").set(0.02);
    loop(2);
    assertEquals(0.02, io.steerPid[0], 1e-12);
    assertEquals(0.001, io.steerPid[2], 1e-12, "the rest of the group is kept");
    double echoed = nt.getDoubleTopic(SwerveTuneTopics.GAINS_APPLIED + "Steer/kP").subscribe(-1).get();
    assertEquals(0.02, echoed, 1e-12, "the laptop sees it too");
    assertTrue(tuningStatus().startsWith("Applied"), tuningStatus());
  }

  @Test
  void anOutOfRangeEditSnapsBack() {
    loop(1);
    tuning("Drive/kP").set(50);
    loop(2);
    assertEquals(0.002, io.drivePid[0], 1e-12, "never reached the motor");
    assertEquals(0.002, tuning("Drive/kP").get(), 1e-12, "AdvantageScope shows what is really running");
    assertTrue(tuningStatus().contains("REFUSED"), tuningStatus());
  }

  @Test
  void editsWaitUntilNoTestIsRunning() {
    onBlocks();
    loop(2);
    send("steer_step", "FL", "hold_s", "0.3", "settle_s", "0.2");
    loop(5);
    tuning("Steer/kP").set(0.03);
    loop(2);
    assertEquals(0.01, io.steerPid[0], 1e-12, "a mid-test change would spoil the measurement");
    assertEquals(0.01, tuning("Steer/kP").get(), 1e-12);
    assertTrue(tuningStatus().contains("a test is running"), tuningStatus());
  }

  @Test
  void aLaptopChangeShowsUpInAdvantageScope() {
    loop(1);
    DoublePublisher kp = nt.getDoubleTopic(SwerveTuneTopics.GAINS + "Steer/kP").publish();
    IntegerPublisher apply = nt.getIntegerTopic(SwerveTuneTopics.GAINS_APPLY_SEQ).publish();
    IntegerPublisher boot = nt.getIntegerTopic(SwerveTuneTopics.GAINS_BOOT_ID).publish();
    kp.set(0.015);
    boot.set(tune.bootId());
    apply.set(7);
    loop(2);
    assertEquals(0.015, tuning("Steer/kP").get(), 1e-12);
    loop(2);
    String status = nt.getStringTopic(SwerveTuneTopics.GAINS_APPLY_STATUS).subscribe("").get();
    assertTrue(status.startsWith("Applied"), "AdvantageScope's echo is not mistaken for an edit: " + status);
  }

  @Test
  void unknownTestsAndModulesAreNamedInTheRefusal() {
    onBlocks();
    loop(1);
    send("wiggle", "ALL");
    loop(1);
    assertTrue(ackMessage().contains("Known:"));
    send("steer_step", "XX");
    loop(1);
    assertTrue(ackMessage().contains("Unknown module"));
  }
}
