package frc.lib.slothtune;

import edu.wpi.first.math.geometry.Pose2d;
import edu.wpi.first.math.geometry.Rotation3d;
import edu.wpi.first.math.geometry.Transform3d;
import edu.wpi.first.math.util.Units;
import edu.wpi.first.networktables.BooleanPublisher;
import edu.wpi.first.networktables.BooleanSubscriber;
import edu.wpi.first.networktables.DoubleArrayPublisher;
import edu.wpi.first.networktables.DoubleArraySubscriber;
import edu.wpi.first.networktables.DoublePublisher;
import edu.wpi.first.networktables.DoubleSubscriber;
import edu.wpi.first.networktables.IntegerPublisher;
import edu.wpi.first.networktables.IntegerSubscriber;
import edu.wpi.first.networktables.NetworkTableInstance;
import edu.wpi.first.networktables.StringArrayPublisher;
import edu.wpi.first.networktables.StringArraySubscriber;
import edu.wpi.first.networktables.StringPublisher;
import edu.wpi.first.networktables.StringSubscriber;
import edu.wpi.first.wpilibj.DriverStation;
import edu.wpi.first.wpilibj.Filesystem;
import edu.wpi.first.wpilibj.Notifier;
import edu.wpi.first.wpilibj.RobotBase;
import edu.wpi.first.wpilibj.Timer;
import edu.wpi.first.wpilibj.simulation.DriverStationSim;
import com.revrobotics.spark.SparkBase;
import edu.wpi.first.wpilibj2.command.Subsystem;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Random;
import java.util.function.DoubleSupplier;
import java.util.function.Supplier;
import swervelib.SwerveDrive;

/**
 * The robot side of the swerve tuning and troubleshooting tools.
 *
 * <p>Two lines put it on a robot:
 *
 * <pre>
 *   SlothTune tune = SlothTune.install(drive.getSwerveDrive(), drive, "Peashooter");
 *   // in robotPeriodic(), after CommandScheduler.getInstance().run():
 *   tune.periodic();
 * </pre>
 *
 * <p>From then on the laptop tool ({@code tools/slothtune}) can, over NetworkTables:
 *
 * <ul>
 *   <li>watch every module live — angle, setpoint, speed, current, temperature, faults;
 *   <li>run a test and get back every sample it recorded ({@link Procedure});
 *   <li>change gains on the running robot without a redeploy ({@link LiveGains}).
 * </ul>
 *
 * <p>The robot never judges a test. It moves the motors, records, and keeps everyone safe
 * ({@link SafetySupervisor}). Analysis, advice and config editing live in the laptop tool, so the
 * GUI a student uses and the command line an AI agent uses always give the same answer.
 *
 * <p><b>Nothing here changes how the robot drives</b> until a test is requested, a gain is changed
 * live, or {@code slothtune.json} asks for something at startup. A test only ever takes the
 * drivetrain while it runs, and hands it straight back to the driver when it ends.
 */
public final class SlothTune {
  /** Where a test is in its life. */
  public enum State {
    IDLE,
    WAITING,
    RUNNING,
    DONE,
    ABORTED
  }

  private static final double MAX_WAIT_S = 60;
  /** Floor space assumed in simulation when none is declared: the simulated field has no walls nearby. */
  private static final double SIM_SPACE_M = 8.0;

  private final DrivetrainIO io;
  /** What slothtune.json changed at startup, and each mechanism's saved gains as it registers. */
  private final List<String> startup = new ArrayList<>();
  private StringArrayPublisher startupReport;
  private final NetworkTableInstance nt;
  private final RobotSignals signals;
  private final DoubleSupplier clock;
  private final boolean simulation;
  private final DriveOwnership ownership;
  private final SlothTuneConfig config;
  private final SafetySupervisor supervisor;
  private final LiveGains gains;
  private final BatteryPicker battery;
  /** The module checks the laptop's monitor makes, here too, so they watch matches. */
  private ModuleWatch watch;
  private final long bootId;
  private final boolean manualSampling;
  private final Map<String, Supplier<Procedure>> procedures = new LinkedHashMap<>();
  private Supplier<double[]> pdhSource = AkLogging::pdhCurrents;
  private Supplier<double[]> pdhPowerSource = AkLogging::pdhPower;
  // The PDH's voltage and total current, read once per robot loop: the sampler runs on its own
  // thread and must not reach into AdvantageKit's snapshot while the loop is updating it.
  private volatile double pdhVolts = Double.NaN;
  private volatile double pdhAmps = Double.NaN;

  // laptop -> robot
  private final StringSubscriber envMode;
  private final BooleanSubscriber envTags;
  private final DoubleSubscriber spaceForward;
  private final DoubleSubscriber spaceSide;
  private final DoubleSubscriber speedCap;
  private final DoubleSubscriber heartbeat;
  private final BooleanSubscriber guiDeadman;
  private final IntegerSubscriber abortSeq;
  private final IntegerSubscriber cmdSeq;
  private final IntegerSubscriber cmdBootId;
  private final StringSubscriber cmdTest;
  private final StringSubscriber cmdModule;
  private final StringArraySubscriber cmdArgKeys;
  private final DoubleArraySubscriber cmdArgValues;
  private final BooleanSubscriber simEnable;

  // robot -> laptop
  private final StringPublisher envActive;
  private final BooleanPublisher visionAvailable;
  private final BooleanPublisher visionInUse;
  private final IntegerPublisher ackSeq;
  private final BooleanPublisher ackAccepted;
  private final StringPublisher ackMessage;
  private final IntegerPublisher statusSeq;
  private final StringPublisher statusTest;
  private final StringPublisher statusState;
  private final StringPublisher statusMessage;
  private final DoublePublisher statusProgress;
  private final BooleanPublisher statusDeadman;
  private final StringArrayPublisher statusLiveNames;
  private final DoubleArrayPublisher statusLiveRows;
  /** The channels a live view shows (those a test records), time first; and how many rows each loop. */
  private List<String> liveNames = List.of();
  private int liveRowCount;
  private final IntegerPublisher resultSeq;
  private final StringPublisher resultTest;
  private final StringPublisher resultOutcome;
  private final StringArrayPublisher resultChannels;
  private final StringArrayPublisher resultMetaKeys;
  private final DoubleArrayPublisher resultMetaValues;
  private final StringArrayPublisher resultNotes;
  private final Map<String, DoubleArrayPublisher> resultData = new HashMap<>();
  private final Map<String, DoubleArrayPublisher> live = new HashMap<>();

  // motor guard
  private final MotorGuard guard = new MotorGuard();
  /** Whether a bring-up motor test paused the robot's code: resumed when the test ends, however. */
  private boolean robotCodePaused;
  private final Map<String, StringArrayPublisher> liveStrings = new HashMap<>();
  private final List<String> drivetrainMotors = new ArrayList<>();
  private final List<Sensors.Registered> sensors = new ArrayList<>();
  private final List<TunableSystem> systems = new ArrayList<>();
  private final List<CurrentSensor> currentSensors = new ArrayList<>();
  private final List<HoldCurrent> holds = new ArrayList<>();
  private StringArrayPublisher pieceNames;
  private StringArrayPublisher pieceInfo;
  private DoubleArrayPublisher pieceValues;
  private StringArrayPublisher holdNames;
  private DoubleArrayPublisher holdValues;
  private SystemBoard systemBoard;
  private List<Sensors.Designed> designedSensors = List.of();
  private Sensors.Opener sensorPorts;
  private final IntegerSubscriber overrideSeq;
  private final IntegerSubscriber overrideBootId;
  private final StringSubscriber overrideName;
  private final DoubleSubscriber overrideSeconds;
  private final IntegerPublisher overrideAckSeq;
  private final StringPublisher overrideAckMessage;
  private final StringArrayPublisher motorsReport;
  private final StringArrayPublisher motorsEvents;
  private long lastOverrideSeq;
  private IntegerSubscriber clearSeq;
  private IntegerSubscriber clearBootId;
  private IntegerPublisher clearAckSeq;
  private StringPublisher clearAckMessage;
  private long lastClearSeq;
  private int publishedReportLines = -1;
  private DashboardAlerts dashboard;
  private double[] lastCan = new double[0];
  private long canErrorLoops;
  private long publishedEvents = -1;
  private final DoubleArrayPublisher livePose;
  private final DoubleArrayPublisher liveVisionPose;
  private final DoubleArrayPublisher liveAccel;
  private final DoublePublisher liveHeading;
  private final DoubleArrayPublisher liveGyroNumbers;
  /** The heading last loop, and when, for the turn rate; and the rate, smoothed over a few loops. */
  private double gyroLastDeg = Double.NaN;
  private double gyroLastS = Double.NaN;
  private double turnRateDegS = Double.NaN;
  private final DoublePublisher liveBus;
  private final DoublePublisher liveTimestamp;
  private final StringPublisher liveMode;
  private final BooleanPublisher liveFms;
  private final StringArrayPublisher liveFaults;
  private final StringArrayPublisher liveGyro;
  private final StringArrayPublisher liveGyroDetails;
  private double lastGyroDetails = -1;
  // When the gyro's light stops blinking (identify), in robot seconds; 0 when it isn't.
  private double identifyUntil = 0;
  private final DoubleArrayPublisher liveAbsIssue;

  // the run in progress, or the last one
  private Procedure proc;
  private TestContext ctx;
  private State state = State.IDLE;
  private String message = "Ready.";
  private String lastTest = "";
  private long activeSeq;
  private double requestedAtS;
  private double startedAtS;
  private double timeoutS;
  private double progress;
  private double[] startPose;
  private SafetySupervisor.TestProfile profile;
  private Notifier notifier;

  // bookkeeping
  private long lastCmdSeq;
  private long lastAbortSeq;
  private double lastHeartbeatValue = Double.NaN;
  private double lastHeartbeatS = Double.NEGATIVE_INFINITY;
  private double lastHeadingDeg = Double.NaN;
  private double lastHeadingS;
  private double yawRateDps;
  private final double[] accelWindow = new double[5];
  private int accelSamples;
  private boolean lastSimEnable;
  private Supplier<Optional<Pose2d>> vision;
  private VisionSource visionSource;
  private long visionFed;
  private final VisionGate visionGate = new VisionGate();
  // Read by the sampler thread (the straight-line test's vision channels).
  private volatile double[] lastVisionPose;
  private volatile double lastVisionTimeS = Double.NEGATIVE_INFINITY;
  private final DoubleArrayPublisher liveVisionCounts;
  private final StringPublisher liveVisionReject;

  /**
   * Builds the harness for a YAGSL drivetrain and reads {@code deploy/swerve/slothtune.json}.
   *
   * @param swerveDrive the YAGSL drive
   * @param driveSubsystem the subsystem that owns it; held while a test runs
   * @param robotName shown on the laptop, e.g. the project folder name
   */
  public static SlothTune install(SwerveDrive swerveDrive, Subsystem driveSubsystem, String robotName) {
    Path file = Filesystem.getDeployDirectory().toPath().resolve("swerve").resolve("slothtune.json");
    SlothTuneConfig config = SlothTuneConfig.load(file);
    SlothTune tune = new SlothTune(
        new YagslDrivetrainIO(swerveDrive),
        NetworkTableInstance.getDefault(),
        new RobotSignals.Wpilib(
            config.driverPort, config.overrideAxes, config.deadmanPort, config.deadmanButton),
        Timer::getFPGATimestamp,
        robotName,
        config,
        RobotBase.isSimulation(),
        new DriveOwnership.CommandsV2(driveSubsystem),
        false);
    tune.dashboard = new DashboardAlerts();
    tune.dashboard.protectionOff(!config.motorGuard, !config.enforceCurrentPolicy);
    // The Wiring tab's map, if one has been saved and deployed: alerts then name PDH ports and CAN
    // neighbors.
    tune.dashboard.setWiring(WiringMap.load(Filesystem.getDeployDirectory().toPath().resolve("wiring.json")));
    // Bring-up's sensor readout: the design file's sensors, opened from their ports while it runs.
    tune.designedSensors = Sensors.loadDesign(
        Filesystem.getDeployDirectory().toPath().resolve("design").resolve("devices.json"));
    tune.sensorPorts = new Sensors.Wpilib();
    tune.guard.setAlertSink(text -> {
      System.out.println("[slothtune] motors: " + text);
      DriverStation.reportWarning("[motors] " + text, false);
    });
    return tune;
  }

  SlothTune(
      DrivetrainIO io,
      NetworkTableInstance nt,
      RobotSignals signals,
      DoubleSupplier clock,
      String robotName,
      SlothTuneConfig config,
      boolean simulation,
      DriveOwnership ownership,
      boolean manualSampling) {
    this.io = io;
    this.nt = nt;
    this.signals = signals;
    this.clock = clock;
    this.simulation = simulation;
    this.ownership = ownership;
    this.config = config;
    this.manualSampling = manualSampling;
    this.supervisor = new SafetySupervisor(config.limits);
    this.bootId = 1 + new Random().nextInt(Integer.MAX_VALUE - 1);

    procedures.put("capture", CaptureProcedure::new);
    procedures.put("steer_step", SteerStepProcedure::new);
    procedures.put("drive_step", DriveStepProcedure::new);
    procedures.put("drive_ff", DriveFeedforwardProcedure::new);
    procedures.put("spin", SpinProcedure::new);
    procedures.put("straight", StraightLineProcedure::new);
    procedures.put("slip", SlipProcedure::new);
    procedures.put("pdh_map", PdhMapProcedure::new);
    procedures.put("spin_ff", SpinFeedforwardProcedure::new);
    procedures.put("controller", ControllerProcedure::new);
    procedures.put("motor_test", MotorTestProcedure::new);
    procedures.put("sensors", SensorProcedure::new);
    procedures.put("can_load", CanLoadProcedure::new);
    procedures.put("system_limits", SystemLimitsProcedure::new);
    procedures.put("system_step", SystemStepProcedure::new);
    procedures.put("system_id", SystemIdProcedure::new);
    procedures.put("system_piece", PieceSenseProcedure::new);
    procedures.put("system_hold", HoldProcedure::new);

    startup.addAll(applyStartupConfig());

    envMode = nt.getStringTopic(SlothTuneTopics.ENV_MODE).subscribe("UNSET");
    envTags = nt.getBooleanTopic(SlothTuneTopics.ENV_APRILTAGS).subscribe(false);
    spaceForward = nt.getDoubleTopic(SlothTuneTopics.ENV_SPACE_FORWARD).subscribe(0);
    spaceSide = nt.getDoubleTopic(SlothTuneTopics.ENV_SPACE_SIDE).subscribe(0);
    speedCap = nt.getDoubleTopic(SlothTuneTopics.ENV_SPEED_CAP).subscribe(config.defaultSpeedCapMps);
    heartbeat = nt.getDoubleTopic(SlothTuneTopics.CLIENT_HEARTBEAT).subscribe(Double.NaN);
    guiDeadman = nt.getBooleanTopic(SlothTuneTopics.CLIENT_DEADMAN).subscribe(false);
    abortSeq = nt.getIntegerTopic(SlothTuneTopics.CLIENT_ABORT_SEQ).subscribe(0);
    cmdSeq = nt.getIntegerTopic(SlothTuneTopics.CMD_SEQ).subscribe(0);
    cmdBootId = nt.getIntegerTopic(SlothTuneTopics.CMD_BOOT_ID).subscribe(0);
    cmdTest = nt.getStringTopic(SlothTuneTopics.CMD_TEST).subscribe("");
    cmdModule = nt.getStringTopic(SlothTuneTopics.CMD_MODULE).subscribe("ALL");
    cmdArgKeys = nt.getStringArrayTopic(SlothTuneTopics.CMD_ARG_KEYS).subscribe(new String[0]);
    cmdArgValues = nt.getDoubleArrayTopic(SlothTuneTopics.CMD_ARG_VALUES).subscribe(new double[0]);
    simEnable = nt.getBooleanTopic(SlothTuneTopics.SIM_REQUEST_ENABLE).subscribe(false);
    overrideSeq = nt.getIntegerTopic(SlothTuneTopics.MOTORS_OVERRIDE_SEQ).subscribe(0);
    overrideBootId = nt.getIntegerTopic(SlothTuneTopics.MOTORS_OVERRIDE_BOOT_ID).subscribe(0);
    overrideName = nt.getStringTopic(SlothTuneTopics.MOTORS_OVERRIDE_NAME).subscribe("ALL");
    overrideSeconds = nt.getDoubleTopic(SlothTuneTopics.MOTORS_OVERRIDE_SECONDS).subscribe(0);
    overrideAckSeq = nt.getIntegerTopic(SlothTuneTopics.MOTORS_OVERRIDE_ACK_SEQ).publish();
    overrideAckMessage = nt.getStringTopic(SlothTuneTopics.MOTORS_OVERRIDE_ACK_MESSAGE).publish();
    clearSeq = nt.getIntegerTopic(SlothTuneTopics.MOTORS_CLEAR_SEQ).subscribe(0);
    clearBootId = nt.getIntegerTopic(SlothTuneTopics.MOTORS_CLEAR_BOOT_ID).subscribe(0);
    clearAckSeq = nt.getIntegerTopic(SlothTuneTopics.MOTORS_CLEAR_ACK_SEQ).publish();
    clearAckMessage = nt.getStringTopic(SlothTuneTopics.MOTORS_CLEAR_ACK_MESSAGE).publish();
    motorsReport = nt.getStringArrayTopic(SlothTuneTopics.MOTORS_REPORT).publish();
    motorsEvents = nt.getStringArrayTopic(SlothTuneTopics.MOTORS_EVENTS).publish();
    nt.getBooleanTopic(SlothTuneTopics.MOTORS_GUARD_ON).publish().set(config.motorGuard);
    watchDrivetrain();

    envActive = nt.getStringTopic(SlothTuneTopics.ENV_ACTIVE).publish();
    visionAvailable = nt.getBooleanTopic(SlothTuneTopics.ENV_VISION_AVAILABLE).publish();
    visionInUse = nt.getBooleanTopic(SlothTuneTopics.ENV_VISION_IN_USE).publish();
    ackSeq = nt.getIntegerTopic(SlothTuneTopics.ACK_SEQ).publish();
    ackAccepted = nt.getBooleanTopic(SlothTuneTopics.ACK_ACCEPTED).publish();
    ackMessage = nt.getStringTopic(SlothTuneTopics.ACK_MESSAGE).publish();
    statusSeq = nt.getIntegerTopic(SlothTuneTopics.STATUS_SEQ).publish();
    statusTest = nt.getStringTopic(SlothTuneTopics.STATUS_TEST).publish();
    statusState = nt.getStringTopic(SlothTuneTopics.STATUS_STATE).publish();
    statusMessage = nt.getStringTopic(SlothTuneTopics.STATUS_MESSAGE).publish();
    statusProgress = nt.getDoubleTopic(SlothTuneTopics.STATUS_PROGRESS).publish();
    statusDeadman = nt.getBooleanTopic(SlothTuneTopics.STATUS_DEADMAN_HELD).publish();
    statusLiveNames = nt.getStringArrayTopic(SlothTuneTopics.STATUS_LIVE_NAMES).publish();
    statusLiveRows = nt.getDoubleArrayTopic(SlothTuneTopics.STATUS_LIVE_ROWS).publish();
    resultSeq = nt.getIntegerTopic(SlothTuneTopics.RESULT_SEQ).publish();
    resultTest = nt.getStringTopic(SlothTuneTopics.RESULT_TEST).publish();
    resultOutcome = nt.getStringTopic(SlothTuneTopics.RESULT_OUTCOME).publish();
    resultChannels = nt.getStringArrayTopic(SlothTuneTopics.RESULT_CHANNELS).publish();
    resultMetaKeys = nt.getStringArrayTopic(SlothTuneTopics.RESULT_META_KEYS).publish();
    resultMetaValues = nt.getDoubleArrayTopic(SlothTuneTopics.RESULT_META_VALUES).publish();
    resultNotes = nt.getStringArrayTopic(SlothTuneTopics.RESULT_NOTES).publish();
    livePose = nt.getDoubleArrayTopic(SlothTuneTopics.LIVE_POSE).publish();
    liveVisionPose = nt.getDoubleArrayTopic(SlothTuneTopics.LIVE_VISION_POSE).publish();
    liveVisionCounts = nt.getDoubleArrayTopic(SlothTuneTopics.LIVE_VISION_COUNTS).publish();
    liveVisionReject = nt.getStringTopic(SlothTuneTopics.LIVE_VISION_LAST_REJECT).publish();
    liveAccel = nt.getDoubleArrayTopic(SlothTuneTopics.LIVE_ACCEL).publish();
    liveHeading = nt.getDoubleTopic(SlothTuneTopics.LIVE_HEADING_DEG).publish();
    liveGyroNumbers = nt.getDoubleArrayTopic(SlothTuneTopics.LIVE_GYRO_NUMBERS).publish();
    liveBus = nt.getDoubleTopic(SlothTuneTopics.LIVE_BUS_VOLTS).publish();
    liveTimestamp = nt.getDoubleTopic(SlothTuneTopics.LIVE_TIMESTAMP).publish();
    liveMode = nt.getStringTopic(SlothTuneTopics.LIVE_ROBOT_MODE).publish();
    liveFms = nt.getBooleanTopic(SlothTuneTopics.LIVE_FMS_ATTACHED).publish();
    liveFaults = nt.getStringArrayTopic(SlothTuneTopics.LIVE_FAULTS).publish();
    liveGyro = nt.getStringArrayTopic(SlothTuneTopics.LIVE_GYRO).publish();
    liveGyroDetails = nt.getStringArrayTopic(SlothTuneTopics.LIVE_GYRO_DETAILS).publish();
    liveAbsIssue = nt.getDoubleArrayTopic(SlothTuneTopics.LIVE_ABS_READ_ISSUE).publish();

    // Identity. Published once; the laptop reads it on connect.
    nt.getIntegerTopic(SlothTuneTopics.PROTOCOL).publish().set(SlothTuneTopics.PROTOCOL_VERSION);
    nt.getIntegerTopic(SlothTuneTopics.BOOT_ID).publish().set(bootId);
    nt.getStringTopic(SlothTuneTopics.ROBOT_NAME).publish().set(robotName);
    // Versions, for the laptop's network check: a Driver Station, image and code from different years
    // is one reason a robot won't run.
    nt.getStringTopic(SlothTuneTopics.ROBOT_IMAGE).publish().set(RobotImage.version());
    nt.getStringTopic(SlothTuneTopics.ROBOT_WPILIB).publish().set(edu.wpi.first.wpilibj.util.WPILibVersion.Version);
    String[] names = new String[io.moduleCount()];
    double[] locations = new double[2 * io.moduleCount()];
    for (int m = 0; m < io.moduleCount(); m++) {
      names[m] = io.moduleName(m);
      double[] xy = io.moduleLocationM(m);
      locations[2 * m] = xy[0];
      locations[2 * m + 1] = xy[1];
    }
    nt.getStringArrayTopic(SlothTuneTopics.MODULE_NAMES).publish().set(names);
    nt.getDoubleArrayTopic(SlothTuneTopics.MODULE_LOCATIONS).publish().set(locations);
    nt.getDoubleTopic(SlothTuneTopics.MAX_MODULE_SPEED).publish().set(io.maxModuleSpeedMps());
    nt.getStringTopic(SlothTuneTopics.STEER_FEEDBACK).publish().set(io.steerFeedback());
    startupReport = nt.getStringArrayTopic(SlothTuneTopics.STARTUP_REPORT).publish();
    startupReport.set(startup.toArray(new String[0]));

    gains = new LiveGains(nt, io, config, bootId);
    // The FPGA clock restarts only when the roboRIO powers up: early in it, this is a fresh power-on
    // (maybe a new battery); later, only the robot code restarted (the same battery).
    battery = new BatteryPicker(nt, config.batteries, clock.getAsDouble() < BatteryPicker.FRESH_POWER_ON_S,
        config.batteryGrades,
        // On the roboRIO, next to the robot program (survives power-offs); the simulator keeps none.
        RobotBase.isReal() ? Filesystem.getOperatingDirectory().toPath().resolve("slothtune-battery-picks.txt") : null);
    lastCmdSeq = cmdSeq.get();
    lastAbortSeq = abortSeq.get();
    lastOverrideSeq = overrideSeq.get();
    lastClearSeq = clearSeq.get();
    publishStatus(false);
  }

  // ------------------------------------------------------------------ motor guard

  private void watchDrivetrain() {
    if (!config.motorGuard) {
      guard.note("Motor guard switched off in slothtune.json: no heat, stall or failure"
          + " protection.");
      return;
    }
    if (simulation) {
      guard.note("Simulation: the SPARKs report no current or temperature here, so the heat, stall"
          + " and failure checks have nothing to judge. They run on the real robot.");
    }
    MotorKind drive = config.motorKinds.getOrDefault("drive", io.driveMotorKind());
    MotorKind steer = config.motorKinds.getOrDefault("steer", io.steerMotorKind());
    boolean anyDrive = false;
    boolean anySteer = false;
    for (int m = 0; m < io.moduleCount(); m++) {
      String module = io.moduleName(m);
      anyDrive |= watch(module + " drive", io.driveMotorChannel(m), drive, false, false);
      anySteer |= watch(module + " steer", io.steerMotorChannel(m), steer, false, true);
    }
    unknownNote(anyDrive, "Drive", drive, "drive");
    unknownNote(anySteer, "Steering", steer, "steer");
  }

  private void unknownNote(boolean watched, String what, MotorKind kind, String key) {
    if (watched && kind == MotorKind.NEO_UNKNOWN) {
      guard.note(String.format("%s motors: NEO V1.1 or NEO 2.0? They look identical electrically,"
          + " so the stricter %d A policy applies until slothtune.json says, e.g."
          + " \"motors\": {\"%s\": \"NEO 2.0\"}.", what, kind.policyAmps, key));
    }
  }

  /** Registers one motor; false if there was nothing to watch or the name was taken. */
  private boolean watch(String name, MotorGuard.MotorChannel channel, MotorKind kind,
      boolean mechanism, boolean stallTimer) {
    if (channel == null) {
      return false;
    }
    MotorKind k = config.motorKinds.getOrDefault(name, kind);
    try {
      guard.register(name, channel, k, config.enforceCurrentPolicy, stallTimer);
    } catch (IllegalArgumentException e) {
      guard.note(e.getMessage() + "; the second one is not watched.");
      return false;
    }
    if (channel instanceof SparkChannel sc && !sc.bootReport().isEmpty()) {
      guard.note(String.format("%s (CAN %d) reported since it powered on: %s.", name, channel.canId(),
          sc.bootReport()));
    }
    if (!mechanism) {
      drivetrainMotors.add(name);
    } else if (k == MotorKind.NEO_UNKNOWN) {
      guard.note(String.format("%s: a NEO of unknown version, so %d A. If it is a NEO 550 it needs"
          + " 20 A: say so in slothtune.json, \"motors\": {\"%s\": \"NEO 550\"}.", name,
          k.policyAmps, name));
    }
    return true;
  }

  /**
   * Watches a mechanism motor for heat, stalls and failure, and holds it to the team's current
   * policy. Call once per motor at startup, typically through a subsystem's {@code watchMotors}:
   *
   * <pre>
   *   shooter.watchMotors(tune::watchMotor);
   * </pre>
   *
   * @param name unique and readable, e.g. {@code "Shooter leader"}; slothtune.json's motor
   *     inventory can override the kind by this name
   * @param kind what the motor is. A SPARK MAX cannot tell a NEO 550 from a NEO: say which
   */
  public void watchMotor(String name, SparkBase spark, MotorKind kind) {
    if (config.motorGuard) {
      watch(name, new SparkChannel(spark, simulation), kind, true, true);
    }
  }

  /**
   * Shows a switch-like sensor (a beam break, a limit switch) in bring-up's live sensor readout, as
   * the code reads it. Call once per sensor at startup:
   *
   * <pre>
   *   tune.watchSensor("Intake beam", intakeBeam::get);
   * </pre>
   *
   * <p>The readout reads it from its own thread: pass the sensor's own read, not a field the robot
   * loop copies it into. A sensor the code reads must be registered to be seen: its port is taken,
   * so the readout can't open it.
   *
   * @param name as the design file names it, so the two are one sensor
   */
  public void watchSensor(String name, java.util.function.BooleanSupplier read) {
    addSensor(new Sensors.Registered(name, true, () -> read.getAsBoolean() ? 1 : 0));
  }

  /** As {@link #watchSensor(String, java.util.function.BooleanSupplier)}, for a number: an encoder, a distance. */
  public void watchSensor(String name, DoubleSupplier read) {
    addSensor(new Sensors.Registered(name, false, read));
  }

  /**
   * Registers a mechanism for the Systems tab and returns it to describe: how to read it, how to
   * set its goal, its subsystem, its motors and gains (see {@link TunableSystem}). slothtune.json's
   * {@code "systems"} entry of the same name gives its limits and its saved gains.
   */
  public TunableSystem system(String name, TunableSystem.Kind kind) {
    systems.removeIf(s -> s.name.equals(name));
    TunableSystem s = new TunableSystem(name, kind);
    s.saved = config.systemGains.getOrDefault(name, Map.of());
    s.report = this::startupLine;
    double[] lim = config.systems.get(name);
    if (lim != null) {
      if (Double.isFinite(lim[0]) && Double.isFinite(lim[1])) {
        s.setLimits(lim[0], lim[1], "slothtune.json");
      }
      s.maxVelocity = lim[2];
      s.maxAccel = lim[3];
    }
    systems.add(s);
    return s;
  }

  /** A line for the startup report after startup: a mechanism's saved gains, as it registers. */
  private void startupLine(String line) {
    startup.add(line);
    if (startupReport != null) {
      startupReport.set(startup.toArray(new String[0]));
    }
  }

  /**
   * A game piece sensed through a motor's own current (see {@link CurrentSensor}): the motor by the
   * name the motor guard watches it under, so watch it first. Its calibration comes from
   * slothtune.json's {@code "currentSensors"}, which the Systems tab writes.
   */
  public CurrentSensor currentSensor(String name, String motorName) {
    return currentSensor(name, motorName, null);
  }

  /**
   * As {@link #currentSensor(String, String)}, for an arm or elevator: {@code system} gives its
   * position, for the current it draws empty at each position ({@code aboveBaseline}).
   */
  public CurrentSensor currentSensor(String name, String motorName, TunableSystem system) {
    MotorGuard.Motor m = guard.motor(motorName);
    if (m == null) {
      DriverStation.reportWarning("SlothTune: current sensor '" + name + "' reads motor '" + motorName
          + "', which isn't watched; it will never see a piece. Watch the motor first.", false);
    }
    CurrentSensor s = new CurrentSensor(name, motorName, m, system == null ? null : system.position);
    s.configure(config.currentSensors.get(name));
    currentSensors.removeIf(x -> x.name.equals(name));
    currentSensors.add(s);
    return s;
  }

  /**
   * Holding a game piece by its motor's current limit (see {@link HoldCurrent}): the motor by its
   * watched name, and how to set its power. slothtune.json's {@code "holds"} gives the current.
   */
  public HoldCurrent holdCurrent(String motorName, java.util.function.DoubleConsumer setDuty) {
    MotorGuard.Motor m = guard.motor(motorName);
    if (m == null) {
      DriverStation.reportWarning("SlothTune: the hold for '" + motorName
          + "' has no watched motor of that name: its current limit won't change. Watch the motor first.", false);
    }
    HoldCurrent h = new HoldCurrent(motorName, m, setDuty);
    h.configure(config.holds.get(motorName));
    holds.removeIf(x -> x.motorName.equals(motorName));
    holds.add(h);
    return h;
  }

  /** The game-piece sensors and holds on NetworkTables, for the Systems tab. */
  private void publishPieces() {
    if (pieceNames == null) {
      pieceNames = nt.getStringArrayTopic(SlothTuneTopics.PIECE_NAMES).publish();
      pieceInfo = nt.getStringArrayTopic(SlothTuneTopics.PIECE_INFO).publish();
      pieceValues = nt.getDoubleArrayTopic(SlothTuneTopics.PIECE_VALUES).publish();
      holdNames = nt.getStringArrayTopic(SlothTuneTopics.HOLD_NAMES).publish();
      holdValues = nt.getDoubleArrayTopic(SlothTuneTopics.HOLD_VALUES).publish();
    }
    String[] n = new String[currentSensors.size()];
    String[] info = new String[n.length];
    double[] v = new double[4 * n.length];
    for (int i = 0; i < n.length; i++) {
      CurrentSensor s = currentSensors.get(i);
      n[i] = s.name;
      String sys = "";
      for (TunableSystem y : systems) {
        if (s.position != null && y.position == s.position || y.motors.contains(s.motorName)) {
          sys = y.name;
          break;
        }
      }
      info[i] = s.motorName + "|" + s.mode.key() + "|" + sys;
      v[4 * i] = s.amps();
      v[4 * i + 1] = s.detected() ? 1 : 0;
      v[4 * i + 2] = s.hasPiece() ? 1 : 0;
      v[4 * i + 3] = s.thresholdA;
    }
    pieceNames.set(n);
    pieceInfo.set(info);
    pieceValues.set(v);
    String[] hn = new String[holds.size()];
    double[] hv = new double[4 * hn.length];
    for (int i = 0; i < hn.length; i++) {
      HoldCurrent h = holds.get(i);
      hn[i] = h.motorName;
      hv[4 * i] = h.currentA;
      hv[4 * i + 1] = h.duty;
      hv[4 * i + 2] = h.isOn() ? 1 : 0;
      hv[4 * i + 3] = h.tuned ? 1 : 0;
    }
    holdNames.set(hn);
    holdValues.set(hv);
  }

  private void addSensor(Sensors.Registered s) {
    sensors.removeIf(x -> x.name().equals(s.name()));
    sensors.add(s);
  }

  /** The team's current policy for the drive motors, from slothtune.json's inventory. */
  private double drivePolicyA() {
    return config.motorKinds.getOrDefault("drive", io.driveMotorKind()).policyAmps;
  }

  /** The drive current limit in force now: the guard's, if it is watching, else YAGSL's. */
  private double driveLimitA() {
    for (String name : drivetrainMotors) {
      MotorGuard.Motor m = guard.motor(name);
      if (m != null && name.endsWith(" drive")) {
        return m.baseLimitA();
      }
    }
    return io.driveCurrentLimitA();
  }

  /** The guard itself, for robot code that wants to read a motor's state. */
  public MotorGuard motors() {
    return guard;
  }

  /**
   * Holds every motor's heat shutoff at half current for a while: for a match where losing a
   * motor costs more than the motor. Bind it to a button. Stalls still cut out.
   *
   * @return what happened, for a log or a dashboard
   */
  public String overrideMotorShutoffs(double seconds) {
    return guard.override("ALL", seconds, clock.getAsDouble());
  }

  /**
   * Motors cut off that the heat override can't bring back, e.g. {@code "Intake pivot (stalled:
   * clear the jam)"}; empty when none. Read it after {@link #overrideMotorShutoffs} to tell the
   * driver whether the override took: a long buzz when it didn't.
   */
  public List<String> motorsStillOff() {
    return guard.beyondOverride();
  }

  private void handleMotorOverride(double now) {
    long seq = overrideSeq.get();
    if (seq == lastOverrideSeq) {
      return;
    }
    lastOverrideSeq = seq;
    String msg = overrideBootId.get() != bootId
        ? "Ignored: that override was sent to an earlier boot of the robot."
        : guard.override(overrideName.get(), overrideSeconds.get(), now);
    overrideAckMessage.set(msg);
    overrideAckSeq.set(seq);
  }

  /** The laptop's Clear sticky faults: every controller's, the gyro's, and the guard's counts. */
  private void handleClearSticky() {
    long seq = clearSeq.get();
    if (seq == lastClearSeq) {
      return;
    }
    lastClearSeq = seq;
    String msg;
    if (clearBootId.get() != bootId) {
      msg = "Ignored: that was sent to an earlier boot of the robot.";
    } else {
      int n = guard.clearSticky();
      boolean gyro = io.gyroClearStickyFaults().ok();
      boolean pdh = AkLogging.clearPdhStickyFaults();
      msg = String.format(Locale.ROOT, "Cleared the sticky faults on %d controller%s%s%s, and the counts of drop-outs, "
          + "reboots and low supply.%s",
          n, n == 1 ? "" : "s", gyro ? ", the gyro" : "", pdh ? ", the PDH" : "",
          pdh ? "" : " No REV PDH answered, so its own faults are as they were.");
    }
    clearAckMessage.set(msg);
    clearAckSeq.set(seq);
  }

  private StringArrayPublisher liveStrings(String topic) {
    return liveStrings.computeIfAbsent(topic, k -> nt.getStringArrayTopic(k).publish());
  }

  private void publishMotors() {
    List<MotorGuard.Motor> list = guard.motors();
    int n = list.size();
    String[] names = new String[n];
    String[] kinds = new String[n];
    String[] stages = new String[n];
    String[] causes = new String[n];
    String[] flags = new String[n];
    String[] history = new String[n];
    String[] settings = new String[n];
    double[] duty = new double[n];
    double[] rpm = new double[n];
    double[] heat = new double[n];
    double[] temp = new double[n];
    double[] amps = new double[n];
    double[] limit = new double[n];
    double[] base = new double[n];
    double[] stall = new double[n];
    double[] override = new double[n];
    double[] present = new double[n];
    double[] drops = new double[n];
    double[] resets = new double[n];
    double[] brownouts = new double[n];
    double[] busVolts = new double[n];
    double[] canIds = new double[n];
    String[] models = new String[n];
    String[] classes = new String[n];
    String[] firmware = new String[n];
    double now = clock.getAsDouble();
    for (int i = 0; i < n; i++) {
      MotorGuard.Motor m = list.get(i);
      names[i] = m.name;
      kinds[i] = m.kind.label;
      stages[i] = m.stage().name();
      causes[i] = m.cause();
      flags[i] = m.flags();
      history[i] = m.history();
      settings[i] = m.settings();
      duty[i] = m.duty();
      rpm[i] = m.rpm();
      heat[i] = 100 * m.heatFraction();
      temp[i] = m.tempC();
      amps[i] = m.amps();
      limit[i] = m.activeLimitA();
      base[i] = m.baseLimitA();
      stall[i] = m.stallSeconds();
      override[i] = m.overrideRemainingS(now);
      present[i] = m.present() ? 1 : 0;
      drops[i] = m.dropouts();
      resets[i] = m.resets();
      brownouts[i] = m.brownouts();
      busVolts[i] = m.busVolts();
      canIds[i] = m.canId();
      models[i] = m.controllerModel();
      classes[i] = m.controllerClass();
      firmware[i] = m.firmware();
    }
    liveStrings(SlothTuneTopics.MOTORS_CONTROLLERS).set(models);
    liveStrings(SlothTuneTopics.MOTORS_CODE_CONTROLLERS).set(classes);
    liveStrings(SlothTuneTopics.MOTORS_FIRMWARE).set(firmware);
    liveStrings(SlothTuneTopics.MOTORS_SETTINGS).set(settings);
    liveArray(SlothTuneTopics.MOTORS_DUTY).set(duty);
    liveArray(SlothTuneTopics.MOTORS_PRESENT).set(present);
    liveArray(SlothTuneTopics.MOTORS_DROPOUTS).set(drops);
    liveArray(SlothTuneTopics.MOTORS_RESETS).set(resets);
    liveArray(SlothTuneTopics.MOTORS_BROWNOUTS).set(brownouts);
    liveArray(SlothTuneTopics.MOTORS_BUS_VOLTS).set(busVolts);
    liveArray(SlothTuneTopics.MOTORS_CAN_IDS).set(canIds);
    lastCan = signals.canStatus();
    if (lastCan.length >= 5) {
      // The error counters recover within milliseconds, so a laptop polling a few times a second
      // misses most glitches; a running count of loops that saw any does not.
      if (lastCan[3] > 0 || lastCan[4] > 0) {
        canErrorLoops++;
      }
      double[] withCount = java.util.Arrays.copyOf(lastCan, 6);
      withCount[5] = canErrorLoops;
      liveArray(SlothTuneTopics.WIRING_CAN).set(withCount);
    } else {
      liveArray(SlothTuneTopics.WIRING_CAN).set(lastCan);
    }
    if (dashboard != null) {
      double[] can = lastCan.length >= 5 ? java.util.Arrays.copyOf(lastCan, 6) : lastCan;
      if (can.length >= 6) {
        can[5] = canErrorLoops;
      }
      dashboard.update(list, can, guard.overrideRemainingS(now));
    }
    liveStrings(SlothTuneTopics.MOTORS_NAMES).set(names);
    liveStrings(SlothTuneTopics.MOTORS_KINDS).set(kinds);
    liveStrings(SlothTuneTopics.MOTORS_STAGE).set(stages);
    liveStrings(SlothTuneTopics.MOTORS_CAUSE).set(causes);
    liveStrings(SlothTuneTopics.MOTORS_FLAGS).set(flags);
    liveStrings(SlothTuneTopics.MOTORS_HISTORY).set(history);
    liveArray(SlothTuneTopics.MOTORS_RPM).set(rpm);
    liveArray(SlothTuneTopics.MOTORS_HEAT_PCT).set(heat);
    liveArray(SlothTuneTopics.MOTORS_TEMP_C).set(temp);
    liveArray(SlothTuneTopics.MOTORS_AMPS).set(amps);
    liveArray(SlothTuneTopics.MOTORS_LIMIT_A).set(limit);
    liveArray(SlothTuneTopics.MOTORS_BASE_LIMIT_A).set(base);
    liveArray(SlothTuneTopics.MOTORS_STALL_S).set(stall);
    liveArray(SlothTuneTopics.MOTORS_OVERRIDE_S).set(override);
    List<String> report = guard.report();
    if (report.size() != publishedReportLines) {
      publishedReportLines = report.size();
      motorsReport.set(report.toArray(new String[0]));
      for (String line : report) {
        System.out.println("[slothtune] motors: " + line);
      }
    }
    if (guard.eventCount() != publishedEvents) {
      publishedEvents = guard.eventCount();
      motorsEvents.set(guard.events().toArray(new String[0]));
    }
  }

  /** Applies what {@code slothtune.json} asks for, once, and says what it did. */
  /** A pod's values over the shared ones: NaN keeps the shared value. */
  static double[] merge(double[] own, double[] shared) {
    double[] out = shared.clone();
    for (int i = 0; i < Math.min(own.length, out.length); i++) {
      if (!Double.isNaN(own[i])) {
        out[i] = own[i];
      }
    }
    return out;
  }

  /**
   * The gyro's own commands, from the laptop's Calibrate tab: calibrate (robot disabled, so nothing
   * moves it), blink its light for a while so a person can find it, or clear its sticky faults.
   */
  private DrivetrainIO.ApplyResult gyroCommand(String cmd, TestArgs args, double now) {
    switch (cmd) {
      case "gyro_calibrate":
        if (signals.enabled()) {
          return DrivetrainIO.ApplyResult.failed("Disable the robot first: the gyro must stay still while it calibrates.");
        }
        return io.gyroCalibrate();
      case "gyro_identify":
        DrivetrainIO.ApplyResult r = io.gyroIdentify(true);
        if (r.ok()) {
          identifyUntil = now + args.get("seconds", 10, 1, 60);
        }
        return r;
      case "gyro_identify_stop":
        identifyUntil = 0;
        return io.gyroIdentify(false);
      case "gyro_clear_faults":
        return io.gyroClearStickyFaults();
      default:
        return DrivetrainIO.ApplyResult.failed("Unknown gyro command '" + cmd + "'.");
    }
  }

  private List<String> applyStartupConfig() {
    List<String> report = new ArrayList<>(config.warnings);
    if (config.canandgyroApply) {
      DrivetrainIO.ApplyResult g = io.applyGyroFramePeriods(config.canandgyroYawMs / 1000.0,
          config.canandgyroAngularPositionMs / 1000.0, config.canandgyroAngularVelocityMs / 1000.0,
          config.canandgyroAccelerationMs / 1000.0, config.canandgyroStatusMs / 1000.0);
      if (!g.message().isEmpty()) {
        report.add(g.message());
      }
    }
    if (!config.visionCameras.isEmpty()) {
      report.add("Vision: " + String.join(", ", config.visionCameras) + (config.feedPoseEstimator
          ? "; accepted poses feed the pose estimator"
          : "; poses shown on the Live tab only (vision.feedPoseEstimator is off)"));
    }
    if ("absolute".equals(config.steerFeedback)) {
      report.add("Steer feedback: " + io.useAbsoluteSteerFeedback().message());
    }
    if (config.encoderAutoSync) {
      report.add(io.applyEncoderAutoSync(true, config.encoderAutoSyncDeadbandDeg).message());
    }
    if (config.driveVelocityPeriodMs > 0 && config.driveVelocityDepth > 0) {
      report.add(io.applyDriveVelocityFilter(config.driveVelocityPeriodMs, config.driveVelocityDepth)
          .message());
    }
    for (Map.Entry<String, double[]> e : config.driveFeedforward.entrySet()) {
      int m = moduleIndex(e.getKey());
      if (m < 0) {
        report.add("driveFeedforward names a module that does not exist: " + e.getKey());
        continue;
      }
      double[] f = e.getValue();
      report.add(io.applyDriveFeedforward(m, f[0], f[1], f[2]).message());
    }
    // A pod's own gains, over the shared ones: a value it doesn't give keeps the shared one.
    for (Map.Entry<String, Map<String, double[]>> e : config.podGains.entrySet()) {
      int m = moduleIndex(e.getKey());
      if (m < 0) {
        report.add("podGains names a module that does not exist: " + e.getKey());
        continue;
      }
      double[] s = e.getValue().get("steer");
      if (s != null) {
        double[] k = merge(s, io.steerPid(m));
        report.add(io.applySteerPid(m, k[0], k[1], k[2], k[3]).message());
      }
      double[] d = e.getValue().get("drive");
      if (d != null) {
        double[] k = merge(d, io.drivePid(m));
        report.add(io.applyDrivePid(m, k[0], k[1], k[2], k[3]).message());
      }
    }
    if (config.angularVelocityCompensationTeleop || config.angularVelocityCompensationAuto) {
      report.add(io.applyAngularVelocityCompensation(
              config.angularVelocityCompensationTeleop,
              config.angularVelocityCompensationAuto,
              config.angularVelocityCoefficient)
          .message());
    }
    if (config.chassisDiscretizationTeleop != null || config.chassisDiscretizationAuto != null) {
      report.add(io.applyChassisDiscretization(
              config.chassisDiscretizationTeleop == null || config.chassisDiscretizationTeleop,
              config.chassisDiscretizationAuto != null && config.chassisDiscretizationAuto,
              config.chassisDiscretizationDtS)
          .message());
    }
    if (report.isEmpty()) {
      report.add("slothtune.json changes nothing in the drive train; YAGSL runs exactly as configured.");
    }
    for (String line : report) {
      System.out.println("[slothtune] " + line);
    }
    return report;
  }

  /**
   * Gives tests AprilTag ground truth. Call once from robot code that has a vision pose; the
   * laptop's AprilTags switch then decides whether it is used. Without this, tests use the gyro and
   * a tape measure instead — tuning works on a practice field with no tags at all.
   */
  public void setVisionPoseSupplier(Supplier<Optional<Pose2d>> visionPose) {
    this.vision = visionPose;
  }

  /**
   * Gives tests AprilTag ground truth from cameras, every observation checked by
   * {@link VisionGate} first. Preferred over {@link #setVisionPoseSupplier}: rejected frames are
   * counted with a reason, so a bad camera transform shows up as a rejection count, not as a
   * confidently wrong test result. For the Luma P1/P2, wrap PhotonLib; see
   * docs/VISION_LUMA_PHOTONVISION.md.
   */
  public void setVisionSource(VisionSource source) {
    this.visionSource = source;
  }

  /** The gate the tools use, so robot code can apply the same rules to its pose estimator. */
  public VisionGate visionGate() {
    return visionGate;
  }

  private void pollVision(double now) {
    if (visionSource == null) {
      return;
    }
    double[] pose = io.pose();
    for (VisionSource.Observation o : visionSource.poll()) {
      VisionGate.Verdict v = visionGate.check(o, now, new double[] {pose[0], pose[1]});
      if (v.accepted() && o.timestampS() >= lastVisionTimeS) {
        lastVisionPose = new double[] {o.xM(), o.yM(), o.headingDeg()};
        lastVisionTimeS = o.timestampS();
      }
      if (v.accepted() && config.feedPoseEstimator) {
        double[] sd = VisionTrust.stdDevs(o);
        io.addVisionMeasurement(o.xM(), o.yM(), o.headingDeg(), o.timestampS(), sd[0], sd[1]);
        visionFed++;
      }
    }
    liveVisionCounts.set(new double[] {visionGate.accepted(), visionGate.rejected()});
    liveVisionReject.set(visionGate.lastReject());
    List<VisionSource.TagSighting> seen = visionSource.sightings();
    double[] flat = new double[seen.size() * 10];
    String[] cams = new String[seen.size()];
    for (int i = 0; i < seen.size(); i++) {
      VisionSource.TagSighting s = seen.get(i);
      System.arraycopy(new double[] {s.tagId(), s.xM(), s.yM(), s.zM(), s.qw(), s.qx(), s.qy(), s.qz(),
          s.ambiguity(), s.timestampS()}, 0, flat, 10 * i, 10);
      cams[i] = s.camera();
    }
    liveArray(SlothTuneTopics.LIVE_VISION_SIGHTINGS).set(flat);
    liveStrings(SlothTuneTopics.LIVE_VISION_SIGHTING_CAMERAS).set(cams);
  }

  /** The cameras slothtune.json's {@code "vision"} lists, for {@code PhotonVisionSetup}. */
  public List<String> visionCameras() {
    return List.copyOf(config.visionCameras);
  }

  /** Which official AprilTag layout the cameras start from: "welded" or "andymark". */
  public String visionField() {
    return config.visionField;
  }

  /** Camera poses handed to the drivetrain's pose estimator since boot. */
  public long visionPosesFed() {
    return visionFed;
  }

  /**
   * Where camera {@code name} sits on the robot, from slothtune.json's {@code "cameras"} (which the
   * Calibrate tab measures), for {@code PhotonVisionSource}. Empty when it isn't there yet.
   */
  public Optional<Transform3d> cameraMount(String name) {
    double[] v = config.cameras.get(name);
    if (v == null) {
      return Optional.empty();
    }
    return Optional.of(new Transform3d(v[0], v[1], v[2],
        new Rotation3d(Math.toRadians(v[3]), Math.toRadians(v[4]), Math.toRadians(v[5]))));
  }

  /** True while a test is driving the motors. A drive command can check this and stand down. */
  public boolean isTestActive() {
    return state == State.RUNNING && proc != null && proc.spinsWheels();
  }

  /** Why the live gains last changed, as the match log records it. */
  String gainsReason() {
    return gains.reason();
  }

  /** The environment the robot believes it is in. Simulation always reports SIM. */
  public TestEnvironment environment() {
    if (simulation) {
      return TestEnvironment.SIM;
    }
    TestEnvironment env = TestEnvironment.parse(envMode.get());
    return env == TestEnvironment.SIM ? TestEnvironment.UNSET : env;
  }

  /** Call every robot loop, after the command scheduler. Never throws. */
  public void periodic() {
    double now = clock.getAsDouble();
    try {
      trackClient(now);
      trackChassis(now);
      guard.update(now);
      readPdhPower();
      String batteryId = battery.update(now, nt.getConnections().length, io.busVolts(), !signals.enabled());
      if (dashboard != null) {
        dashboard.battery(batteryId);
      }
      AkLogging.recordBattery(batteryId);
      pollVision(now);
      publishLive(now);
      publishMotors();
      handleMotorOverride(now);
      handleClearSticky();
      AkLogging.record(io, guard.motors(), state == State.RUNNING ? lastTest : "");
      handleSimEnable();
      // No gain changes during a match or a test, from any path: the laptop, an agent, AdvantageScope.
      String gainsBlocked = signals.fmsAttached() ? "the FMS is attached"
          : state == State.RUNNING || state == State.WAITING ? "a test is running" : null;
      gains.poll(gainsBlocked);
      gains.pollTuning(gainsBlocked);
      if (systemBoard == null) {
        systemBoard = new SystemBoard(nt, bootId, systems);
      }
      systemBoard.periodic(gainsBlocked);
      for (CurrentSensor s : currentSensors) {
        s.update(now);
      }
      publishPieces();
      Map<String, Double> gainsNow = gains.takeChanged();
      if (gainsNow != null) {
        AkLogging.recordGains(gainsNow, gains.reason());
      }
      handleAbort();
      handleCommand(now);
      runActive(now);
    } catch (RuntimeException e) {
      DriverStation.reportError("[slothtune] " + e, e.getStackTrace());
      if (proc != null) {
        finish(State.ABORTED, "The tuning harness hit an error and stopped the test: " + e);
      }
    }
    publishStatus(isDeadmanHeld(now));
    publishLive();
  }

  private void readPdhPower() {
    double[] p = pdhPowerSource.get();
    boolean ok = p != null && p.length >= 2 && Double.isFinite(p[0]) && p[0] > 1;
    pdhVolts = ok ? p[0] : Double.NaN;
    pdhAmps = ok ? p[1] : Double.NaN;
  }

  // ------------------------------------------------------------------ client and chassis tracking

  private void trackClient(double now) {
    double hb = heartbeat.get();
    if (Double.isFinite(hb) && Double.compare(hb, lastHeartbeatValue) != 0) {
      lastHeartbeatValue = hb;
      lastHeartbeatS = now;
    }
  }

  private void trackChassis(double now) {
    double heading = io.headingDeg();
    if (Double.isFinite(lastHeadingDeg) && now > lastHeadingS) {
      double d = heading - lastHeadingDeg;
      d = ((d + 540) % 360) - 180;
      yawRateDps = d / (now - lastHeadingS);
    }
    lastHeadingDeg = heading;
    lastHeadingS = now;

    Optional<double[]> a = io.accelMps2();
    if (a.isPresent()) {
      accelWindow[accelSamples % accelWindow.length] = Math.hypot(a.get()[0], a.get()[1]);
      accelSamples++;
    }
  }

  private boolean isDeadmanHeld(double now) {
    boolean gui = guiDeadman.get() && now - lastHeartbeatS < config.limits.heartbeatTimeoutS;
    return gui || signals.controllerDeadman();
  }

  private SafetySupervisor.Inputs gatherInputs(double now) {
    SafetySupervisor.Inputs in = new SafetySupervisor.Inputs();
    in.env = environment();
    in.enabled = signals.enabled();
    in.fmsAttached = signals.fmsAttached();
    in.autonomous = signals.autonomous();
    in.nowS = now;
    in.heartbeatAgeS = now - lastHeartbeatS;
    in.guiDeadman = guiDeadman.get() && in.heartbeatAgeS < config.limits.heartbeatTimeoutS;
    in.controllerDeadman = signals.controllerDeadman();
    in.driverStickMax = signals.driverStickMax();
    if (startPose != null) {
      double[] p = io.pose();
      in.displacementM = Math.hypot(p[0] - startPose[0], p[1] - startPose[1]);
    }
    double limit = Math.max(1, io.driveCurrentLimitA());
    int modules = io.moduleCount();
    in.driveAmps = new double[modules];
    in.wheelSpeedsMps = new double[modules];
    in.moduleNames = new String[modules];
    for (int m = 0; m < modules; m++) {
      double v = Math.abs(io.driveMps(m));
      in.maxWheelSpeedMps = Math.max(in.maxWheelSpeedMps, v);
      in.driveAmps[m] = io.driveAmps(m);
      in.wheelSpeedsMps[m] = v;
      in.moduleNames[m] = io.moduleName(m);
      double frac = in.driveAmps[m] / limit;
      if (frac > in.maxDriveCurrentFraction) {
        in.maxDriveCurrentFraction = frac;
        in.speedAtMaxCurrentMps = v;
      }
    }
    in.yawRateDps = yawRateDps;
    if (accelSamples > 0) {
      in.horizontalAccelMps2 = accelWindow[(accelSamples - 1) % accelWindow.length];
      int n = Math.min(accelSamples, accelWindow.length);
      double sum = 0;
      for (int k = 0; k < n; k++) {
        sum += accelWindow[k];
      }
      in.horizontalAccelSmoothedMps2 = sum / n;
    }
    in.busVolts = io.busVolts();
    DrivetrainIO.GyroStatus gyro = io.gyroStatus();
    in.gyroConnected = gyro.connected();
    in.gyroCalibrating = gyro.calibrating();
    MotorGuard.Motor worst = guard.worst(drivetrainMotors);
    if (worst != null && worst.stage().ordinal() >= MotorGuard.Stage.DERATE.ordinal()) {
      in.hotMotor = String.format("The %s motor is at %s (%s).", worst.name, worst.stage(),
          worst.cause());
    }
    return in;
  }

  // ------------------------------------------------------------------ commands

  private void handleAbort() {
    long seq = abortSeq.get();
    if (seq != lastAbortSeq) {
      lastAbortSeq = seq;
      if (proc != null) {
        finish(State.ABORTED, "Aborted from the laptop.");
      }
    }
  }

  private void ack(long seq, boolean accepted, String why) {
    ackAccepted.set(accepted);
    ackMessage.set(why);
    ackSeq.set(seq);
  }

  private void handleCommand(double now) {
    long seq = cmdSeq.get();
    if (seq == lastCmdSeq) {
      return;
    }
    lastCmdSeq = seq;
    if (cmdBootId.get() != bootId) {
      ack(seq, false, "Ignored: this command was sent to an earlier run of the robot program.");
      return;
    }
    String test = cmdTest.get().trim().toLowerCase(Locale.ROOT);
    if (test.equals("stop")) {
      if (proc != null) {
        proc.requestStop();
      }
      ack(seq, true, "Stop requested.");
      return;
    }
    if (test.equals("abort")) {
      if (proc != null) {
        finish(State.ABORTED, "Aborted from the laptop.");
      }
      ack(seq, true, "Aborted.");
      return;
    }
    if (proc != null) {
      ack(seq, false, "Busy: '" + proc.name() + "' is still " + state.name().toLowerCase(Locale.ROOT)
          + ". Stop or abort it first.");
      return;
    }
    if (test.startsWith("gyro_")) {
      DrivetrainIO.ApplyResult r = gyroCommand(test, TestArgs.of(cmdArgKeys.get(), cmdArgValues.get()), now);
      ack(seq, r.ok(), r.message());
      return;
    }
    Supplier<Procedure> factory = procedures.get(test);
    if (factory == null) {
      ack(seq, false, "Unknown test '" + test + "'. Known: " + String.join(", ", procedures.keySet()));
      return;
    }
    int[] modules = parseModules(cmdModule.get());
    if (modules == null) {
      ack(seq, false, "Unknown module '" + cmdModule.get() + "'. Use ALL, FL, FR, BL, BR or a"
          + " module name.");
      return;
    }

    TestEnvironment env = environment();
    Procedure p = factory.get();
    if (!p.allowedIn(env)) {
      ack(seq, false, "'" + test + "' cannot run with the robot declared " + env + "."
          + (env == TestEnvironment.BLOCKS ? " It needs the robot on the floor." : "")
          + (env == TestEnvironment.UNSET ? " Say where the robot is first." : ""));
      return;
    }
    double cap = Math.max(0.1, Math.min(config.maxSpeedCapMps, speedCap.get()));
    TestArgs args = TestArgs.of(cmdArgKeys.get(), cmdArgValues.get());
    Sampler sampler = Sampler.create(16);
    double fwd = Math.max(0, spaceForward.get());
    double side = Math.max(0, spaceSide.get());
    if (env == TestEnvironment.SIM) {
      fwd = Math.max(fwd, SIM_SPACE_M);
      side = Math.max(side, SIM_SPACE_M);
    }
    TestContext c = new TestContext(io, args, env, modules, cap, fwd, side, visionInUseNow(),
        sampler, signals.enabled(),
        signals::enabled, this::visionPoseArray);
    c.drivePolicyA = drivePolicyA();
    c.driveLimitA = driveLimitA();
    c.pdhCurrents = pdhSource;
    c.signals = signals;
    c.motors = guard.motors();
    c.sensors = List.copyOf(sensors);
    c.designedSensors = designedSensors;
    c.sensorPorts = sensorPorts;
    c.systems = List.copyOf(systems);
    c.currentSensors = List.copyOf(currentSensors);
    c.holds = List.copyOf(holds);
    String why = p.validate(c);
    if (why != null) {
      ack(seq, false, why);
      return;
    }
    // A test that commands volts, not speed, says how fast its volts can spin the wheels, so the
    // overspeed stop sits above that rather than at the speed cap it never asked for.
    SafetySupervisor.TestProfile prof = new SafetySupervisor.TestProfile(
        p.spinsWheels(), p.movesChassis(c), Math.max(cap, p.expectedTopSpeedMps(c)),
        p.spaceBudgetM(c), p.pushesWall());
    why = supervisor.refuseStart(gatherInputs(now), prof, p.needsEnabled());
    if (why != null) {
      ack(seq, false, why);
      return;
    }

    int capacity = (int) Math.min(40000, p.sampleRateHz(c) * (p.timeoutS(c) + 2) + 16);
    ctx = new TestContext(io, args, env, modules, cap, c.spaceForwardM, c.spaceSideM,
        c.visionInUse, Sampler.create(capacity), c.enabledAtStart, signals::enabled,
        this::visionPoseArray);
    ctx.drivePolicyA = c.drivePolicyA;
    ctx.driveLimitA = c.driveLimitA;
    ctx.pdhCurrents = pdhSource;
    ctx.signals = signals;
    ctx.motors = c.motors;
    ctx.sensors = c.sensors;
    ctx.designedSensors = c.designedSensors;
    ctx.sensorPorts = c.sensorPorts;
    ctx.systems = c.systems;
    ctx.currentSensors = c.currentSensors;
    ctx.holds = c.holds;
    proc = p;
    profile = prof;
    activeSeq = seq;
    lastTest = test;
    resetLift();
    state = State.WAITING;
    message = "Accepted, waiting to start.";
    progress = 0;
    requestedAtS = now;
    ack(seq, true, "Accepted.");
  }

  /** {@code ALL}, empty, a comma list of module names or FL/FR/BL/BR. Null if anything is unknown. */
  int[] parseModules(String text) {
    int n = io.moduleCount();
    if (text == null || text.isBlank() || text.trim().equalsIgnoreCase("ALL")) {
      int[] all = new int[n];
      for (int m = 0; m < n; m++) {
        all[m] = m;
      }
      return all;
    }
    List<Integer> picked = new ArrayList<>();
    for (String part : text.split(",")) {
      int m = moduleIndex(part.trim());
      if (m < 0) {
        return null;
      }
      if (!picked.contains(m)) {
        picked.add(m);
      }
    }
    return picked.stream().mapToInt(Integer::intValue).toArray();
  }

  private int moduleIndex(String key) {
    String k = key.toLowerCase(Locale.ROOT);
    for (int m = 0; m < io.moduleCount(); m++) {
      String name = io.moduleName(m).toLowerCase(Locale.ROOT);
      if (name.equals(k) || abbreviation(name).equals(k)) {
        return m;
      }
    }
    return -1;
  }

  /** {@code frontleft} becomes {@code fl}, {@code back_right} becomes {@code br}. */
  static String abbreviation(String name) {
    String n = name.toLowerCase(Locale.ROOT);
    String fb = n.contains("front") ? "f" : n.contains("back") || n.contains("rear") ? "b" : "";
    String lr = n.contains("left") ? "l" : n.contains("right") ? "r" : "";
    return fb + lr;
  }

  // ------------------------------------------------------------------ the run

  private void runActive(double now) {
    if (proc == null) {
      return;
    }
    boolean guarded = proc.needsEnabled() || proc.spinsWheels();
    // The environment is fixed when the test is accepted. Changing it mid-test (to "unset" when
    // something looks wrong, say) would otherwise switch off the field checks while it still drives.
    TestEnvironment declared = environment();
    if (declared != ctx.env) {
      finish(State.ABORTED, "The environment changed from " + ctx.env + " to " + declared
          + " during the test. Set it before a test, never during one.");
      return;
    }
    SafetySupervisor.Inputs in = gatherInputs(now);

    if (state == State.WAITING) {
      if (guarded) {
        SafetySupervisor.Verdict v = supervisor.check(in, profile, false);
        if (v.action() == SafetySupervisor.Action.ABORT) {
          finish(State.ABORTED, v.reason());
          return;
        }
        if (v.action() == SafetySupervisor.Action.WAIT) {
          if (!Double.isNaN(liftStartS) && !liftPassed) {
            // Mid-pulse, a wait (the deadman let go) is a stop: the motors are running.
            finish(State.ABORTED, "Stopped during the lift check: " + v.reason());
            return;
          }
          message = v.reason();
          if (now - requestedAtS > MAX_WAIT_S) {
            finish(State.ABORTED, "Gave up after a minute waiting: " + v.reason());
          }
          return;
        }
      } else if (in.fmsAttached) {
        finish(State.ABORTED, "FMS attached.");
        return;
      }
      if (guarded && needsLift()) {
        liftCheck(now);
        if (state != State.WAITING || !liftPassed) {
          return;
        }
      }
      begin(now);
      return;
    }

    double t = now - startedAtS;
    if (guarded) {
      SafetySupervisor.Verdict v = supervisor.check(in, profile, true);
      if (v.action() != SafetySupervisor.Action.CONTINUE) {
        finish(State.ABORTED, v.reason());
        return;
      }
    } else if (in.fmsAttached) {
      // A capture or joystick check started in the pit must not run on into a match.
      finish(State.ABORTED, "FMS attached: a match is starting.");
      return;
    }
    if (t > timeoutS) {
      finish(State.ABORTED, String.format("Ran past its %.0f s time limit.", timeoutS));
      return;
    }
    String stop = proc.abortReason(ctx);
    if (stop != null) {
      finish(State.ABORTED, stop);
      return;
    }
    if (proc.spinsWheels() && !proc.pausesRobotCode() && !ownership.isHeld()) {
      finish(State.ABORTED, "Another command took the drivetrain during the test, so nothing it"
          + " measured from there is the test's. Keep drive buttons alone while a test runs.");
      return;
    }
    boolean done = proc.execute(ctx, t);
    progress = proc.progress(ctx, t);
    String live = proc.liveMessage(ctx, t);
    if (live != null) {
      message = live;
    }
    if (manualSampling || proc.samplesEachLoop()) {
      ctx.sampler.sampleNow();
    }
    if (done) {
      finish(State.DONE, "Finished.");
    }
  }

  // ------------------------------------------------------------------ the lift check
  private double liftStartS = Double.NaN;
  private double liftLastS;
  private double[] liftAmpS;
  private double[] liftPeakMps;
  private boolean liftJudged;
  private boolean liftPassed;

  private void resetLift() {
    liftStartS = Double.NaN;
    liftJudged = false;
    liftPassed = false;
  }

  private boolean needsLift() {
    return ctx.env == TestEnvironment.BLOCKS && proc.drivesWheels() && !liftPassed;
  }

  /**
   * Before a blocks test that drives the wheels: a short pulse on every drive motor. A wheel in the
   * air gains speed fast for little current; one carrying the robot needs many times the current for
   * less speed. Two or more wheels like that and the robot is on the floor, whatever it was told:
   * the test stops before it starts. Decided by physics, not by the test's own gains.
   */
  private void liftCheck(double now) {
    SafetySupervisor.Limits lim = supervisor.limits();
    int n = io.moduleCount();
    if (Double.isNaN(liftStartS)) {
      ownership.acquire();
      liftStartS = now;
      liftLastS = now;
      liftAmpS = new double[n];
      liftPeakMps = new double[n];
      for (int m = 0; m < n; m++) {
        io.setDriveVolts(m, lim.liftVolts);
      }
      message = "Checking the wheels are off the floor: a short pulse.";
      return;
    }
    double dt = now - liftLastS;
    liftLastS = now;
    double el = now - liftStartS;
    for (int m = 0; m < n; m++) {
      if (el <= lim.liftPulseS + 1e-6) {
        liftAmpS[m] += Math.abs(io.driveAmps(m)) * dt;
      }
      // The speed reading lags a status frame: watch one loop past the pulse.
      if (el <= lim.liftPulseS + 0.025) {
        liftPeakMps[m] = Math.max(liftPeakMps[m], Math.abs(io.driveMps(m)));
      }
    }
    if (el < lim.liftPulseS) {
      return;
    }
    for (int m = 0; m < n; m++) {
      io.setDriveVolts(m, 0);
    }
    if (!liftJudged && el >= lim.liftPulseS + 0.02) {
      liftJudged = true;
      double[] ratio = new double[n];
      int carrying = 0;
      int judged = 0;
      for (int m = 0; m < n; m++) {
        if (liftAmpS[m] < 0.05) {
          ratio[m] = Double.NaN; // no current read: can't judge this wheel
          continue;
        }
        judged++;
        ratio[m] = liftPeakMps[m] / liftAmpS[m];
        if (ratio[m] < lim.liftMinMpsPerAmpS) {
          carrying++;
        }
      }
      double[] sorted = java.util.Arrays.stream(ratio).filter(Double::isFinite).sorted().toArray();
      double median = sorted.length == 0 ? Double.NaN : sorted[sorted.length / 2];
      ctx.meta("lift_mps_per_amp_s", median);
      if (carrying >= Math.max(2, (judged + 1) / 2)) {
        finish(State.ABORTED, String.format("NOT on blocks: a short pulse sped the wheels up only %.2f ft/s per"
                + " amp-second (wheels in the air reach over %.1f), so they are carrying weight: the robot is on"
                + " the floor, or the wheels touch the blocks. Put it on blocks, or set On the floor.",
            Units.metersToFeet(median), Units.metersToFeet(lim.liftMinMpsPerAmpS)));
        return;
      }
      ctx.note(String.format("Lift check: wheels free (%.2f ft/s per amp-second).", Units.metersToFeet(median)));
    }
    if (el >= lim.liftPulseS + lim.liftSettleS) {
      liftPassed = true;
    }
  }

  private void begin(double now) {
    supervisor.reset();
    startPose = io.pose();
    if (proc.pausesRobotCode()) {
      // The drivetrain stopped first: with the scheduler paused nothing else will command it.
      io.stop();
      ownership.pauseRobotCode();
      robotCodePaused = true;
    } else if (proc.spinsWheels()) {
      ownership.acquire();
    }
    try {
      proc.start(ctx);
    } catch (RuntimeException e) {
      state = State.RUNNING; // so finish() publishes what little there is
      finish(State.ABORTED, "The test could not start: " + e);
      return;
    }
    if (proc.spinsWheels() && ctx.env != TestEnvironment.SIM && Double.isFinite(pdhVolts)) {
      // The battery as the PDH sees it: with the motors' current, the laptop measures how far
      // this battery sags per amp, which is what decides brownouts and top speed.
      ctx.sampler.channel("pdh_v", () -> pdhVolts).channel("ibatt", () -> pdhAmps);
    }
    double comp = io.compensationVolts();
    if (Double.isFinite(comp) && comp > 0) {
      ctx.meta("comp_volts", comp);
    }
    double rate = proc.sampleRateHz(ctx);
    ctx.meta("sample_rate_hz", rate);
    ctx.meta("env_code", ctx.env.ordinal());
    ctx.meta("speed_cap", ctx.speedCapMps);
    ctx.meta("space_forward_m", ctx.spaceForwardM);
    ctx.meta("space_side_m", ctx.spaceSideM);
    ctx.meta("vision_in_use", ctx.visionInUse ? 1 : 0);
    ctx.meta("boot_id", bootId);
    // Self-describing results: the laptop checks real against configured ratios from these.
    ctx.meta("drive_gear_ratio", io.driveGearRatio());
    ctx.meta("steer_gear_ratio", io.steerGearRatio());
    ctx.meta("steer_feedback_absolute", "absolute".equals(io.steerFeedback()) ? 1 : 0);
    ctx.note("Environment: " + ctx.env + (ctx.visionInUse ? ", AprilTags in use" : ", no AprilTags"));
    ctx.note("Battery: " + (battery.current().isEmpty() ? "not picked" : battery.current()));
    ctx.sampler.start(clock);
    // The live view: what a mechanism's tests record that a person wants to watch (its target, where
    // it is, the volts asked), the newest 0.6 s of it each loop. NetworkTables sends about every
    // 100 ms, so each send overlaps the last and the laptop misses no row.
    List<String> recorded = ctx.sampler.names();
    liveNames = new ArrayList<>(List.of("t"));
    for (String n : LIVE_CHANNELS) {
      if (recorded.contains(n)) {
        liveNames.add(n);
      }
    }
    liveRowCount = (int) Math.min(64, Math.ceil(0.6 * rate) + 1);
    statusLiveNames.set(liveNames.toArray(new String[0]));
    statusLiveRows.set(new double[0]);
    if (!manualSampling && !proc.samplesEachLoop()) {
      notifier = new Notifier(ctx.sampler::sampleNow);
      notifier.setName("SlothTune sampler");
      notifier.startPeriodic(1.0 / rate);
    }
    timeoutS = proc.timeoutS(ctx);
    startedAtS = now;
    state = State.RUNNING;
    message = "Running.";
  }

  /**
   * Puts every swerve SPARK's status frames back to YAGSL's periods after a wheel test sped them up.
   * Left fast, they keep the CAN bus about 60% busier until the robot restarts, so a refusal is
   * tried once more and then reported.
   */
  private void restoreStatusFrames() {
    DrivetrainIO.ApplyResult r;
    try {
      r = io.applyFastTelemetry(false);
      if (!r.ok()) {
        r = io.applyFastTelemetry(false);
      }
    } catch (RuntimeException e) {
      r = DrivetrainIO.ApplyResult.failed(e.toString());
    }
    if (!r.ok()) {
      String why = "Couldn't put the status frames back to normal (" + r.message() + "): the CAN bus"
          + " stays busier until the robot restarts.";
      ctx.note(why);
      DriverStation.reportWarning("[slothtune] " + why, false);
    }
  }

  private void finish(State outcome, String reason) {
    boolean started = state == State.RUNNING;
    try {
      if (started) {
        proc.end(ctx, outcome != State.DONE);
      }
    } catch (RuntimeException e) {
      ctx.note("Cleanup raised " + e + "; motors stopped anyway.");
    }
    if (proc.spinsWheels()) {
      try {
        io.stop();
      } catch (RuntimeException e) {
        DriverStation.reportError("[slothtune] could not stop motors: " + e, false);
      }
      restoreStatusFrames();
    }
    if (notifier != null) {
      notifier.stop();
      notifier.close();
      notifier = null;
    }
    ctx.sampler.stop();
    ownership.release();
    if (robotCodePaused) {
      ownership.resumeRobotCode();
      robotCodePaused = false;
    }
    if (outcome == State.ABORTED) {
      ctx.note("Stopped early: " + reason);
    }
    if (started) {
      publishResult(outcome);
    }
    state = outcome;
    message = reason;
    progress = outcome == State.DONE ? 1 : progress;
    startPose = null;
    proc = null;
  }

  private void publishResult(State outcome) {
    Map<String, double[]> data = ctx.sampler.snapshot();
    if (ctx.sampler.overflowed()) {
      ctx.note("Sample buffer filled; the end of the run was not recorded.");
    }
    for (Map.Entry<String, double[]> e : data.entrySet()) {
      resultData
          .computeIfAbsent(e.getKey(),
              k -> nt.getDoubleArrayTopic(SlothTuneTopics.RESULT_DATA + k).publish())
          .set(e.getValue());
    }
    String[] keys = ctx.meta().keySet().toArray(new String[0]);
    double[] values = new double[keys.length];
    for (int i = 0; i < keys.length; i++) {
      values[i] = ctx.meta().get(keys[i]);
    }
    resultMetaKeys.set(keys);
    resultMetaValues.set(values);
    resultNotes.set(ctx.notes().toArray(new String[0]));
    resultTest.set(lastTest);
    resultOutcome.set(outcome.name());
    resultChannels.set(data.keySet().toArray(new String[0]));
    resultSeq.set(activeSeq); // last: the laptop reads everything else once this changes
    nt.flush();
  }

  // ------------------------------------------------------------------ telemetry

  /**
   * The gyro's numbers for the Live tab. The turn rate is the heading's change over each loop
   * (wrapped across 180), smoothed over about 0.1 s, so it reads the same from any gyro and in the
   * simulator.
   */
  private void publishGyroNumbers(double now) {
    double h = io.headingDeg();
    if (Double.isFinite(h) && Double.isFinite(gyroLastDeg) && now > gyroLastS) {
      double d = ((h - gyroLastDeg + 540) % 360) - 180;
      double rate = d / (now - gyroLastS);
      turnRateDegS = Double.isFinite(turnRateDegS) ? turnRateDegS + 0.3 * (rate - turnRateDegS) : rate;
    } else if (!Double.isFinite(h)) {
      turnRateDegS = Double.NaN;  // no heading, no rate: never the last one, frozen
    }
    gyroLastDeg = h;
    gyroLastS = now;
    double[] tilt = io.gyroTiltDeg();
    liveGyroNumbers.set(new double[] {h, turnRateDegS, tilt.length > 0 ? tilt[0] : Double.NaN,
        tilt.length > 1 ? tilt[1] : Double.NaN});
  }

  /** What a running test's live view shows, when the test records it. */
  static final List<String> LIVE_CHANNELS = List.of("pos", "vel", "sp", "goal", "cmd", "stage", "volts0");

  private void publishLive() {
    if (state == State.RUNNING && ctx != null && liveNames.size() > 1) {
      statusLiveRows.set(ctx.sampler.tail(liveNames, liveRowCount));
    }
  }

  private void publishStatus(boolean deadmanHeld) {
    envActive.set(environment().name());
    visionAvailable.set(vision != null || visionSource != null);
    visionInUse.set(visionInUseNow());
    statusSeq.set(activeSeq);
    statusTest.set(lastTest);
    statusState.set(state.name());
    statusMessage.set(message);
    statusProgress.set(progress);
    statusDeadman.set(deadmanHeld);
  }

  private boolean visionInUseNow() {
    return (vision != null || visionSource != null) && envTags.get();
  }

  private double[] visionPoseArray() {
    if (!visionInUseNow()) {
      return null;
    }
    if (visionSource != null) {
      boolean fresh = clock.getAsDouble() - lastVisionTimeS < visionGate.limits().maxAgeS;
      return fresh ? lastVisionPose : null;
    }
    return vision.get()
        .map(p -> new double[] {p.getX(), p.getY(), p.getRotation().getDegrees()})
        .orElse(null);
  }

  private DoubleArrayPublisher liveArray(String topic) {
    return live.computeIfAbsent(topic, k -> nt.getDoubleArrayTopic(k).publish());
  }

  private void publishLive(double now) {
    int n = io.moduleCount();
    double[] steer = new double[n];
    double[] steerSp = new double[n];
    double[] steerMotor = new double[n];
    double[] steerRaw = new double[n];
    double[] driveV = new double[n];
    double[] driveSp = new double[n];
    double[] drivePos = new double[n];
    double[] driveVolts = new double[n];
    double[] steerVolts = new double[n];
    double[] driveAmps = new double[n];
    double[] steerAmps = new double[n];
    double[] driveTemp = new double[n];
    double[] steerTemp = new double[n];
    double[] absIssue = new double[n];
    String[] faults = new String[n];
    for (int m = 0; m < n; m++) {
      steer[m] = io.steerDeg(m);
      steerSp[m] = io.steerSetpointDeg(m);
      steerMotor[m] = io.steerMotorDeg(m);
      steerRaw[m] = io.steerRawDeg(m);
      driveV[m] = io.driveMps(m);
      driveSp[m] = io.driveSetpointMps(m);
      drivePos[m] = io.drivePositionM(m);
      driveVolts[m] = io.driveVolts(m);
      steerVolts[m] = io.steerVolts(m);
      driveAmps[m] = io.driveAmps(m);
      steerAmps[m] = io.steerAmps(m);
      driveTemp[m] = io.driveTempC(m);
      steerTemp[m] = io.steerTempC(m);
      absIssue[m] = io.absoluteReadIssue(m) ? 1 : 0;
      faults[m] = io.faults(m);
    }
    liveArray(SlothTuneTopics.LIVE_STEER_DEG).set(steer);
    liveArray(SlothTuneTopics.LIVE_STEER_SETPOINT_DEG).set(steerSp);
    liveArray(SlothTuneTopics.LIVE_STEER_MOTOR_DEG).set(steerMotor);
    liveArray(SlothTuneTopics.LIVE_STEER_RAW_DEG).set(steerRaw);
    liveArray(SlothTuneTopics.LIVE_DRIVE_MPS).set(driveV);
    liveArray(SlothTuneTopics.LIVE_DRIVE_SETPOINT_MPS).set(driveSp);
    liveArray(SlothTuneTopics.LIVE_DRIVE_POSITION_M).set(drivePos);
    liveArray(SlothTuneTopics.LIVE_DRIVE_VOLTS).set(driveVolts);
    liveArray(SlothTuneTopics.LIVE_STEER_VOLTS).set(steerVolts);
    liveArray(SlothTuneTopics.LIVE_DRIVE_AMPS).set(driveAmps);
    liveArray(SlothTuneTopics.LIVE_STEER_AMPS).set(steerAmps);
    liveArray(SlothTuneTopics.LIVE_DRIVE_TEMP_C).set(driveTemp);
    liveArray(SlothTuneTopics.LIVE_STEER_TEMP_C).set(steerTemp);
    liveAbsIssue.set(absIssue);
    liveFaults.set(faults);
    if (watch == null) {
      String[] mods = new String[n];
      for (int m = 0; m < n; m++) {
        mods[m] = io.moduleName(m);
      }
      watch = new ModuleWatch(mods);
    }
    // A tuning test makes big steering errors on purpose: it isn't a module going wrong.
    if (state != State.RUNNING && state != State.WAITING) {
      watch.update(now, signals.enabled(), steer, steerSp, steerMotor, driveV, driveSp);
    }
    if (dashboard != null) {
      dashboard.modules(watch.flags());
    }
    AkLogging.recordWatch(watch.flags());
    DrivetrainIO.GyroStatus gyro = io.gyroStatus();
    liveGyro.set(new String[] {gyro.type(), gyro.connected() ? "connected" : "NOT CONNECTED",
        gyro.calibrating() ? "calibrating" : "ready", gyro.faults()});
    if (now - lastGyroDetails >= 0.5) {
      lastGyroDetails = now;
      liveGyroDetails.set(io.gyroDetails());
    }
    if (identifyUntil > 0 && now >= identifyUntil) {
      identifyUntil = 0;
      io.gyroIdentify(false);
    }
    livePose.set(io.pose());
    double[] vp = visionPoseArray();
    liveVisionPose.set(vp == null ? new double[0] : vp);
    liveAccel.set(io.accelMps2().orElse(new double[0]));
    liveHeading.set(io.headingDeg());
    publishGyroNumbers(now);
    liveBus.set(io.busVolts());
    liveTimestamp.set(now);
    liveFms.set(signals.fmsAttached());
    liveMode.set(
        signals.eStopped() ? "ESTOP"
            : !signals.enabled() ? "DISABLED"
            : signals.autonomous() ? "AUTO"
            : signals.testMode() ? "TEST"
            : "TELEOP");
  }

  private void handleSimEnable() {
    if (!simulation) {
      return;
    }
    // Act only on values a client actually wrote. Reading the current value instead would see the
    // default (false) as soon as the client that enabled the robot disconnected, and disable it.
    for (var v : simEnable.readQueue()) {
      boolean want = v.value;
      if (want != lastSimEnable) {
        lastSimEnable = want;
        DriverStationSim.setDsAttached(true);
        DriverStationSim.setAutonomous(false);
        DriverStationSim.setTest(false);
        DriverStationSim.setEnabled(want);
        DriverStationSim.notifyNewData();
      }
    }
  }

  // ------------------------------------------------------------------ for tests
  State state() {
    return state;
  }

  String message() {
    return message;
  }

  long bootId() {
    return bootId;
  }

  /** Where tests read the PDH's channel currents from, in place of AdvantageKit. */
  void setPdhSource(Supplier<double[]> source) {
    pdhSource = source;
  }

  /** The battery picked since boot, or "". */
  String batteryId() {
    return battery.current();
  }

  /** Where the PDH's {@code {volts, total amps}} are read from, in place of AdvantageKit. */
  void setPdhPowerSource(Supplier<double[]> source) {
    pdhPowerSource = source;
  }
}
