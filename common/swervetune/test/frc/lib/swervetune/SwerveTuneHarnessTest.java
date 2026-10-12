package frc.lib.swervetune;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import edu.wpi.first.networktables.BooleanPublisher;
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
  }

  @BeforeEach
  void setUp() {
    nt = NetworkTableInstance.create();
    io = new FakeDrivetrain();
    SwerveTuneConfig config = SwerveTuneConfig.parse(
        "{\"driveFeedforward\": {\"backright\": {\"kS\": 0.2, \"kV\": 2.5, \"kA\": 0.4}}}");
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
  void steerStepOnBlocksRunsToTheEndAndPublishesEverySample() {
    envMode.set("BLOCKS");
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
    envMode.set("BLOCKS");
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

  @Test
  void aCommandForAnEarlierRobotProgramIsIgnored() {
    envMode.set("BLOCKS");
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
    envMode.set("BLOCKS");
    loop(1);
    send("straight", "ALL");
    loop(2);
    assertFalse(ackAccepted());
    assertTrue(ackMessage().contains("on the floor"), ackMessage());
  }

  @Test
  void aSecondCommandWhileBusyIsRefusedAndTheFirstCarriesOn() {
    envMode.set("BLOCKS");
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
    envMode.set("BLOCKS");
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
    envMode.set("BLOCKS");
    loop(1);
    send("drive_step", "ALL");
    loop(10);
    io.injectedYawRate = 60;
    loop(20);
    assertEquals(SwerveTune.State.ABORTED, tune.state());
    assertTrue(tune.message().contains("NOT on blocks"), tune.message());
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
    envMode.set("BLOCKS");
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
  void startupConfigAppliesMeasuredFeedforwardByModuleName() {
    assertArrayEquals(new double[] {0.2, 2.5, 0.4}, io.ff[3], 1e-12);
    assertArrayEquals(new double[] {0, 2.9, 0}, io.ff[0], 1e-12);
  }

  @Test
  void unknownTestsAndModulesAreNamedInTheRefusal() {
    envMode.set("BLOCKS");
    loop(1);
    send("wiggle", "ALL");
    loop(1);
    assertTrue(ackMessage().contains("Known:"));
    send("steer_step", "XX");
    loop(1);
    assertTrue(ackMessage().contains("Unknown module"));
  }
}
