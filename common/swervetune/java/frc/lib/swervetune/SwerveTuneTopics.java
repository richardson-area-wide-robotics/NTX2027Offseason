package frc.lib.swervetune;

/**
 * Every NetworkTables name the robot shares with the laptop tools.
 *
 * <p>The Python side keeps the same names in {@code tools/swervetune/contract.py}, and
 * {@code tools/swervetune/tests/test_contract.py} reads this file and fails if the two disagree.
 * Change a name here and that test tells you where else it has to change.
 *
 * <p>Everything lives under one root so a dashboard filter of {@code /SwerveTune} shows the whole
 * conversation, and nothing here collides with YAGSL's own {@code SmartDashboard/swerve} tables.
 */
public final class SwerveTuneTopics {
  private SwerveTuneTopics() {}

  /** Bump when a topic's meaning changes, so an old laptop tool refuses a newer robot. */
  public static final int PROTOCOL_VERSION = 1;

  public static final String ROOT = "/SwerveTune";

  // ---------------------------------------------------------------- robot identity (robot -> laptop)
  public static final String PROTOCOL = ROOT + "/Protocol";
  /**
   * Random number chosen at every robot program start. Commands and gain changes must echo it.
   *
   * <p>NT4 servers keep a client's last values and a reconnecting client republishes them, so
   * without this a laptop reconnecting after a robot reboot would replay its last command — and
   * the robot would re-run a test nobody asked for.
   */
  public static final String BOOT_ID = ROOT + "/BootId";
  public static final String ROBOT_NAME = ROOT + "/RobotName";
  /** The roboRIO's image, e.g. {@code FRC_roboRIO2_2026_v2.0}; empty in the simulator. */
  public static final String ROBOT_IMAGE = ROOT + "/RobotImage";
  /** The WPILib the running code was built with, e.g. {@code 2026.2.1}. */
  public static final String ROBOT_WPILIB = ROOT + "/RobotWpilib";
  /** Lines describing what {@code swervetune.json} changed at startup, and any problems. */
  public static final String STARTUP_REPORT = ROOT + "/StartupReport";
  /** YAGSL module names in kinematics order, e.g. {@code frontleft}. */
  public static final String MODULE_NAMES = ROOT + "/ModuleNames";
  /** Module locations, meters, flattened {@code x0, y0, x1, y1, ...}. +x forward, +y left. */
  public static final String MODULE_LOCATIONS = ROOT + "/ModuleLocationsM";
  /** Free speed of a module from motor, gearing and wheel, m/s. What YAGSL desaturates to. */
  public static final String MAX_MODULE_SPEED = ROOT + "/MaxModuleSpeedMps";
  /** Where the steering PID gets its feedback: {@code motor} or {@code absolute}. */
  public static final String STEER_FEEDBACK = ROOT + "/SteerFeedback";

  // ---------------------------------------------------------------- environment (laptop -> robot)
  /** {@code UNSET}, {@code SIM}, {@code BLOCKS} or {@code FIELD}. See {@link TestEnvironment}. */
  public static final String ENV_MODE = ROOT + "/Env/Mode";
  /** Whether field AprilTags are present. Off on a practice field without tags. */
  public static final String ENV_APRILTAGS = ROOT + "/Env/AprilTags";
  /** Clear floor in front of the robot, meters. Motion tests are sized to fit inside it. */
  public static final String ENV_SPACE_FORWARD = ROOT + "/Env/SpaceForwardM";
  /** Clear floor to each side, meters. */
  public static final String ENV_SPACE_SIDE = ROOT + "/Env/SpaceSideM";
  /** Fastest any test may drive, m/s. */
  public static final String ENV_SPEED_CAP = ROOT + "/Env/SpeedCapMps";

  // ---------------------------------------------------------------- environment as the robot sees it
  public static final String ENV_ACTIVE = ROOT + "/Env/Active";
  /** True once robot code has registered a vision pose source. */
  public static final String ENV_VISION_AVAILABLE = ROOT + "/Env/VisionAvailable";
  /** True when tags are switched on AND a vision source exists, so ground truth is real. */
  public static final String ENV_VISION_IN_USE = ROOT + "/Env/VisionInUse";

  // ---------------------------------------------------------------- client presence
  /** Any increasing number, written by the laptop at 10 Hz or faster. Stale means the laptop is gone. */
  public static final String CLIENT_HEARTBEAT = ROOT + "/Client/Heartbeat";
  /** GUI hold-to-run. Only the GUI writes it, and only while a key is physically held. */
  public static final String CLIENT_DEADMAN = ROOT + "/Client/Deadman";
  /** Bump to abort whatever is running. */
  public static final String CLIENT_ABORT_SEQ = ROOT + "/Client/AbortSeq";

  // ---------------------------------------------------------------- commands (laptop -> robot)
  /** Bump after writing the other Cmd topics; the robot acts once per new value. */
  public static final String CMD_SEQ = ROOT + "/Cmd/Seq";
  /** Must equal {@link #BOOT_ID} or the command is ignored. */
  public static final String CMD_BOOT_ID = ROOT + "/Cmd/BootId";
  public static final String CMD_TEST = ROOT + "/Cmd/Test";
  /** {@code ALL}, a YAGSL module name, or {@code FL}/{@code FR}/{@code BL}/{@code BR}. */
  public static final String CMD_MODULE = ROOT + "/Cmd/Module";
  public static final String CMD_ARG_KEYS = ROOT + "/Cmd/ArgKeys";
  public static final String CMD_ARG_VALUES = ROOT + "/Cmd/ArgValues";

  // ---------------------------------------------------------------- acknowledgement (robot -> laptop)
  // The answer to the most recent command: accepted, or refused and why. Kept apart from Status
  // so a command refused while another test runs is not lost under that test's progress updates.
  public static final String ACK_SEQ = ROOT + "/Ack/Seq";
  public static final String ACK_ACCEPTED = ROOT + "/Ack/Accepted";
  public static final String ACK_MESSAGE = ROOT + "/Ack/Message";

  // ---------------------------------------------------------------- status (robot -> laptop)
  public static final String STATUS_SEQ = ROOT + "/Status/Seq";
  public static final String STATUS_TEST = ROOT + "/Status/Test";
  /** {@code IDLE}, {@code WAITING}, {@code RUNNING}, {@code DONE}, {@code ABORTED}, {@code REFUSED}. */
  public static final String STATUS_STATE = ROOT + "/Status/State";
  public static final String STATUS_MESSAGE = ROOT + "/Status/Message";
  public static final String STATUS_PROGRESS = ROOT + "/Status/Progress";
  public static final String STATUS_DEADMAN_HELD = ROOT + "/Status/DeadmanHeld";

  // ---------------------------------------------------------------- results (robot -> laptop)
  public static final String RESULT_SEQ = ROOT + "/Result/Seq";
  public static final String RESULT_TEST = ROOT + "/Result/Test";
  /** {@code DONE} or {@code ABORTED}. An aborted run still publishes what it gathered. */
  public static final String RESULT_OUTCOME = ROOT + "/Result/Outcome";
  public static final String RESULT_CHANNELS = ROOT + "/Result/Channels";
  /** Prefix for one {@code double[]} per channel: {@code RESULT_DATA + channelName}. */
  public static final String RESULT_DATA = ROOT + "/Result/Data/";
  public static final String RESULT_META_KEYS = ROOT + "/Result/MetaKeys";
  public static final String RESULT_META_VALUES = ROOT + "/Result/MetaValues";
  /** Free-text notes, one per line, e.g. why a run was cut short. */
  public static final String RESULT_NOTES = ROOT + "/Result/Notes";

  // ---------------------------------------------------------------- live gains (both directions)
  /** Prefix for gain topics, e.g. {@code /SwerveTune/Gains/Steer/kP}. See {@link LiveGains}. */
  public static final String GAINS = ROOT + "/Gains/";

  /**
   * Every live gain again, in the table AdvantageScope's tuning mode can edit (when
   * {@code advantageScopeTuning} is on), plus {@code Status}: what happened to the last edit.
   */
  public static final String TUNING = "/Tuning/SwerveTune/";
  /** Bump after writing gain topics; the robot applies the whole set once per new value. */
  public static final String GAINS_APPLY_SEQ = ROOT + "/Gains/ApplySeq";
  /** Must equal {@link #BOOT_ID} or the gain change is ignored. */
  public static final String GAINS_BOOT_ID = ROOT + "/Gains/BootId";
  /** Why the laptop asked for this change, a short sentence; logged with the gains. */
  public static final String GAINS_REASON = ROOT + "/Gains/Reason";
  /** Robot's echo of every gain it is actually running, {@code GAINS_APPLIED + key}. */
  public static final String GAINS_APPLIED = ROOT + "/Gains/Applied/";
  public static final String GAINS_APPLIED_SEQ = ROOT + "/Gains/AppliedSeq";
  public static final String GAINS_APPLY_STATUS = ROOT + "/Gains/ApplyStatus";

  // ---------------------------------------------------------------- live telemetry (robot -> laptop)
  // Arrays are indexed by module, in MODULE_NAMES order. Published every robot loop.
  public static final String LIVE = ROOT + "/Live/";
  public static final String LIVE_STEER_DEG = LIVE + "SteerDeg";
  public static final String LIVE_STEER_SETPOINT_DEG = LIVE + "SteerSetpointDeg";
  /** Steering motor's own encoder, in module degrees. Should track SteerDeg within a degree or two. */
  public static final String LIVE_STEER_MOTOR_DEG = LIVE + "SteerMotorDeg";
  /** Absolute encoder before the YAGSL offset is subtracted. This is what offsets are taken from. */
  public static final String LIVE_STEER_RAW_DEG = LIVE + "SteerRawDeg";
  public static final String LIVE_DRIVE_MPS = LIVE + "DriveMps";
  public static final String LIVE_DRIVE_SETPOINT_MPS = LIVE + "DriveSetpointMps";
  public static final String LIVE_DRIVE_POSITION_M = LIVE + "DrivePositionM";
  public static final String LIVE_DRIVE_VOLTS = LIVE + "DriveVolts";
  public static final String LIVE_STEER_VOLTS = LIVE + "SteerVolts";
  public static final String LIVE_DRIVE_AMPS = LIVE + "DriveAmps";
  public static final String LIVE_STEER_AMPS = LIVE + "SteerAmps";
  public static final String LIVE_DRIVE_TEMP_C = LIVE + "DriveTempC";
  public static final String LIVE_STEER_TEMP_C = LIVE + "SteerTempC";
  public static final String LIVE_FAULTS = LIVE + "Faults";
  public static final String LIVE_ABS_READ_ISSUE = LIVE + "AbsoluteReadIssue";
  /** Heading as odometry uses it: degrees, counter-clockwise positive. */
  public static final String LIVE_HEADING_DEG = LIVE + "HeadingDeg";
  /** Field-relative acceleration from the IMU, m/s^2, {@code x, y, z}. Empty if the IMU has none. */
  public static final String LIVE_ACCEL = LIVE + "AccelMps2";
  /** Gyro {@code {type, connected|NOT CONNECTED, calibrating|ready, faults}}. */
  public static final String LIVE_GYRO = LIVE + "Gyro";
  /** Game-piece current sensors: names, "motor|mode|system" each, and {amps, detected, hasPiece, threshold} each. */
  public static final String PIECE_NAMES = ROOT + "/Pieces/Names";
  public static final String PIECE_INFO = ROOT + "/Pieces/Info";
  public static final String PIECE_VALUES = ROOT + "/Pieces/Values";
  /** Holds: motor names, and {amps, duty, on, tuned} each. */
  public static final String HOLD_NAMES = ROOT + "/Holds/Names";
  public static final String HOLD_VALUES = ROOT + "/Holds/Values";
  /** More about the gyro, "name=value" lines: temperature, firmware, sticky faults (a Canandgyro's). */
  public static final String LIVE_GYRO_DETAILS = LIVE + "GyroDetails";
  /** Odometry pose, {@code x m, y m, heading deg}. */
  public static final String LIVE_POSE = LIVE + "Pose";
  /** Vision pose when one is in use, same layout as LIVE_POSE; empty otherwise. */
  public static final String LIVE_VISION_POSE = LIVE + "VisionPose";

  // ---------------------------------------------------------------- motor guard, robot -> laptop
  /** Every watched motor, swerve and mechanism alike; the arrays below follow this order. */
  public static final String MOTORS = ROOT + "/Motors/";
  public static final String MOTORS_NAMES = MOTORS + "Names";
  /** {@link MotorKind#label}, e.g. {@code "NEO 550"}. */
  public static final String MOTORS_KINDS = MOTORS + "Kinds";
  /** OK, WARN, DERATE or SHUTOFF. */
  public static final String MOTORS_STAGE = MOTORS + "Stage";
  /** Heat estimate, percent of what burns the windings out. */
  public static final String MOTORS_HEAT_PCT = MOTORS + "HeatPct";
  public static final String MOTORS_TEMP_C = MOTORS + "TempC";
  public static final String MOTORS_AMPS = MOTORS + "Amps";
  /** Current limit in force now, amps. */
  public static final String MOTORS_LIMIT_A = MOTORS + "LimitA";
  /** Current limit when cool, amps. */
  public static final String MOTORS_BASE_LIMIT_A = MOTORS + "BaseLimitA";
  public static final String MOTORS_STALL_S = MOTORS + "StallS";
  public static final String MOTORS_OVERRIDE_S = MOTORS + "OverrideS";
  /** Why each motor is at its stage; empty when OK. */
  public static final String MOTORS_CAUSE = MOTORS + "Cause";
  /** Failures the guard cannot fix: unplugged, open phase, faults. Empty when none. */
  public static final String MOTORS_FLAGS = MOTORS + "Flags";
  /** Faults latched earlier and no longer active ("faults since last cleared: ..."). Empty when none. */
  public static final String MOTORS_HISTORY = MOTORS + "History";
  /** Each motor's speed now, rpm. */
  public static final String MOTORS_RPM = MOTORS + "Rpm";
  /** Stage changes, newest last. */
  public static final String MOTORS_EVENTS = MOTORS + "Events";
  /** What registration found: limits over policy, unknown motor types. */
  public static final String MOTORS_REPORT = MOTORS + "Report";
  /** 1 while the controller is heard on the CAN bus, 0 when it is not. */
  public static final String MOTORS_PRESENT = MOTORS + "Present";
  /** Times each has dropped off the CAN bus since the robot code started. */
  public static final String MOTORS_DROPOUTS = MOTORS + "Dropouts";
  /** Times each has rebooted, which means it lost power. */
  public static final String MOTORS_RESETS = MOTORS + "Resets";
  /** Times each has warned of low supply voltage. */
  public static final String MOTORS_BROWNOUTS = MOTORS + "Brownouts";
  /** Supply voltage at each controller, volts. */
  public static final String MOTORS_BUS_VOLTS = MOTORS + "BusVolts";
  public static final String MOTORS_CAN_IDS = MOTORS + "CanIds";

  /** What each controller says it is ("SPARK MAX", "SPARK Flex"), empty if it can't say. */
  public static final String MOTORS_CONTROLLERS = MOTORS + "Controllers";

  /** What the code created each controller as. */
  public static final String MOTORS_CODE_CONTROLLERS = MOTORS + "CodeControllers";

  /** Each controller's firmware version. */
  public static final String MOTORS_FIRMWARE = MOTORS + "Firmware";

  // ---------------------------------------------------------------- battery

  /**
   * Which battery is in, as a "String Chooser": the topics WPILib's SendableChooser publishes, which
   * Elastic and Shuffleboard show as a drop-down named Battery. A dashboard writes {@code selected}.
   */
  public static final String BATTERY_CHOOSER = "/SmartDashboard/Battery/";

  public static final String BATTERY_SELECTED = BATTERY_CHOOSER + "selected";
  public static final String BATTERY_OPTIONS = BATTERY_CHOOSER + "options";
  public static final String BATTERY_ACTIVE = BATTERY_CHOOSER + "active";

  /** The battery picked since this boot; empty until someone picks. */
  public static final String BATTERY_ID = ROOT + "/Battery/Id";

  /** The battery voltage when it was picked with the robot disabled: its resting voltage. */
  public static final String BATTERY_REST_VOLTS = ROOT + "/Battery/RestVolts";
  /** One line for the drive team: "Battery 7: 12.84 V at rest, charged". */
  public static final String BATTERY_CHECK = ROOT + "/Battery/Check";
  /** The battery to put in next: graded best, then the one picked longest ago; empty if none. */
  public static final String BATTERY_NEXT = ROOT + "/Battery/Next";

  /**
   * The CAN bus: utilization 0-1, bus-off count, TX-full count, receive errors, transmit errors,
   * and how many robot loops have seen any receive or transmit error since the code started.
   */
  public static final String WIRING_CAN = ROOT + "/Wiring/Can";

  /** False when swervetune.json switched the guard off. */
  public static final String MOTORS_GUARD_ON = MOTORS + "GuardOn";

  // ---------------------------------------------------------------- systems (TunableSystem)
  public static final String SYSTEMS = ROOT + "/Systems/";
  /** Each registered system, in order: its name, kind (FLYWHEEL, PIVOT...), units and motors (comma list). */
  public static final String SYSTEMS_NAMES = SYSTEMS + "Names";
  public static final String SYSTEMS_KINDS = SYSTEMS + "Kinds";
  public static final String SYSTEMS_UNITS = SYSTEMS + "Units";
  public static final String SYSTEMS_MOTORS = SYSTEMS + "Motors";
  /** Live, one entry per system: position, velocity (units/s, or the flywheel's speed), last goal. */
  public static final String SYSTEMS_POSITION = SYSTEMS + "Position";
  public static final String SYSTEMS_VELOCITY = SYSTEMS + "Velocity";
  public static final String SYSTEMS_GOAL = SYSTEMS + "Goal";
  /** Four per system: min, max, max velocity, max acceleration (NaN where unknown). */
  public static final String SYSTEMS_LIMITS = SYSTEMS + "Limits";
  /** Where each system's limits came from: "swervetune.json", "moved by hand", or "". */
  public static final String SYSTEMS_LIMITS_FROM = SYSTEMS + "LimitsFrom";
  /** Every live gain as "system/gain|min|max". */
  public static final String SYSTEMS_GAIN_NAMES = SYSTEMS + "GainNames";
  /** Requested gains, laptop -> robot: SYSTEMS_GAINS + "system/gain". */
  public static final String SYSTEMS_GAINS = SYSTEMS + "Gains/";
  /** What each gain really is now. */
  public static final String SYSTEMS_GAINS_APPLIED = SYSTEMS + "Applied/";
  /** Bumped to apply the requested gains; ignored unless the boot id matches. */
  public static final String SYSTEMS_APPLY_SEQ = SYSTEMS + "ApplySeq";
  public static final String SYSTEMS_APPLY_BOOT_ID = SYSTEMS + "ApplyBootId";
  public static final String SYSTEMS_APPLIED_SEQ = SYSTEMS + "AppliedSeq";
  public static final String SYSTEMS_APPLY_STATUS = SYSTEMS + "ApplyStatus";

  // ---------------------------------------------------------------- motor guard, laptop -> robot
  /** Bumped to request an override; ignored unless {@link #MOTORS_OVERRIDE_BOOT_ID} matches. */
  public static final String MOTORS_OVERRIDE_SEQ = MOTORS + "Override/Seq";
  public static final String MOTORS_OVERRIDE_BOOT_ID = MOTORS + "Override/BootId";
  /** A motor name, or ALL. */
  public static final String MOTORS_OVERRIDE_NAME = MOTORS + "Override/Name";
  /** Seconds, at most {@link MotorGuard#MAX_OVERRIDE_S}; 0 cancels. */
  public static final String MOTORS_OVERRIDE_SECONDS = MOTORS + "Override/Seconds";
  public static final String MOTORS_OVERRIDE_ACK_SEQ = MOTORS + "Override/AckSeq";
  public static final String MOTORS_OVERRIDE_ACK_MESSAGE = MOTORS + "Override/AckMessage";
  /** Vision observations so far, {@code {accepted, rejected}}. */
  public static final String LIVE_VISION_COUNTS = LIVE + "VisionCounts";
  /** Why the most recent rejected observation was rejected. */
  public static final String LIVE_VISION_LAST_REJECT = LIVE + "VisionLastReject";

  /**
   * The tags in each camera's newest frame, 10 numbers a tag: tag ID, the tag's x, y, z (meters)
   * and quaternion w, x, y, z in the camera frame, ambiguity, timestamp. For the camera calibration.
   */
  public static final String LIVE_VISION_SIGHTINGS = LIVE + "VisionSightings";

  /** Which camera saw each tag in {@link #LIVE_VISION_SIGHTINGS}, in the same order. */
  public static final String LIVE_VISION_SIGHTING_CAMERAS = LIVE + "VisionSightingCameras";
  public static final String LIVE_BUS_VOLTS = LIVE + "BusVolts";
  /** {@code DISABLED}, {@code TELEOP}, {@code AUTO}, {@code TEST}, or {@code ESTOP}. */
  public static final String LIVE_ROBOT_MODE = LIVE + "RobotMode";
  public static final String LIVE_FMS_ATTACHED = LIVE + "FmsAttached";
  /** Robot-side timestamp of this sample, seconds. */
  public static final String LIVE_TIMESTAMP = LIVE + "Timestamp";

  // ---------------------------------------------------------------- simulation only
  /** Lets a laptop tool enable the simulated robot without the sim GUI. Ignored on a real robot. */
  public static final String SIM_REQUEST_ENABLE = ROOT + "/Sim/RequestEnable";
}
