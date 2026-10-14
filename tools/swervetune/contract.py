"""NetworkTables names shared with the robot.

The robot keeps the same names in
``common/swervetune/java/frc/lib/swervetune/SwerveTuneTopics.java``; ``tests/test_contract.py``
reads that file and fails if the two disagree, so a rename on one side cannot silently break the
other.
"""

PROTOCOL_VERSION = 1

ROOT = "/SwerveTune"

# robot identity
PROTOCOL = ROOT + "/Protocol"
BOOT_ID = ROOT + "/BootId"
ROBOT_NAME = ROOT + "/RobotName"
STARTUP_REPORT = ROOT + "/StartupReport"
MODULE_NAMES = ROOT + "/ModuleNames"
MODULE_LOCATIONS = ROOT + "/ModuleLocationsM"
MAX_MODULE_SPEED = ROOT + "/MaxModuleSpeedMps"
STEER_FEEDBACK = ROOT + "/SteerFeedback"

# environment
ENV_MODE = ROOT + "/Env/Mode"
ENV_APRILTAGS = ROOT + "/Env/AprilTags"
ENV_SPACE_FORWARD = ROOT + "/Env/SpaceForwardM"
ENV_SPACE_SIDE = ROOT + "/Env/SpaceSideM"
ENV_SPEED_CAP = ROOT + "/Env/SpeedCapMps"
ENV_ACTIVE = ROOT + "/Env/Active"
ENV_VISION_AVAILABLE = ROOT + "/Env/VisionAvailable"
ENV_VISION_IN_USE = ROOT + "/Env/VisionInUse"

# client presence
CLIENT_HEARTBEAT = ROOT + "/Client/Heartbeat"
CLIENT_DEADMAN = ROOT + "/Client/Deadman"
CLIENT_ABORT_SEQ = ROOT + "/Client/AbortSeq"

# commands
CMD_SEQ = ROOT + "/Cmd/Seq"
CMD_BOOT_ID = ROOT + "/Cmd/BootId"
CMD_TEST = ROOT + "/Cmd/Test"
CMD_MODULE = ROOT + "/Cmd/Module"
CMD_ARG_KEYS = ROOT + "/Cmd/ArgKeys"
CMD_ARG_VALUES = ROOT + "/Cmd/ArgValues"

# acknowledgement
ACK_SEQ = ROOT + "/Ack/Seq"
ACK_ACCEPTED = ROOT + "/Ack/Accepted"
ACK_MESSAGE = ROOT + "/Ack/Message"

# status
STATUS_SEQ = ROOT + "/Status/Seq"
STATUS_TEST = ROOT + "/Status/Test"
STATUS_STATE = ROOT + "/Status/State"
STATUS_MESSAGE = ROOT + "/Status/Message"
STATUS_PROGRESS = ROOT + "/Status/Progress"
STATUS_DEADMAN_HELD = ROOT + "/Status/DeadmanHeld"

# results
RESULT_SEQ = ROOT + "/Result/Seq"
RESULT_TEST = ROOT + "/Result/Test"
RESULT_OUTCOME = ROOT + "/Result/Outcome"
RESULT_CHANNELS = ROOT + "/Result/Channels"
RESULT_DATA = ROOT + "/Result/Data/"
RESULT_META_KEYS = ROOT + "/Result/MetaKeys"
RESULT_META_VALUES = ROOT + "/Result/MetaValues"
RESULT_NOTES = ROOT + "/Result/Notes"

# live gains
GAINS = ROOT + "/Gains/"
# The same gains, where AdvantageScope's tuning mode can edit them (with advantageScopeTuning on),
# plus Status: what happened to the last edit.
TUNING = "/Tuning/SwerveTune/"
GAINS_APPLY_SEQ = ROOT + "/Gains/ApplySeq"
GAINS_BOOT_ID = ROOT + "/Gains/BootId"
GAINS_REASON = ROOT + "/Gains/Reason"
GAINS_APPLIED = ROOT + "/Gains/Applied/"
GAINS_APPLIED_SEQ = ROOT + "/Gains/AppliedSeq"
GAINS_APPLY_STATUS = ROOT + "/Gains/ApplyStatus"

# live telemetry
LIVE = ROOT + "/Live/"
LIVE_STEER_DEG = LIVE + "SteerDeg"
LIVE_STEER_SETPOINT_DEG = LIVE + "SteerSetpointDeg"
LIVE_STEER_MOTOR_DEG = LIVE + "SteerMotorDeg"
LIVE_STEER_RAW_DEG = LIVE + "SteerRawDeg"
LIVE_DRIVE_MPS = LIVE + "DriveMps"
LIVE_DRIVE_SETPOINT_MPS = LIVE + "DriveSetpointMps"
LIVE_DRIVE_POSITION_M = LIVE + "DrivePositionM"
LIVE_DRIVE_VOLTS = LIVE + "DriveVolts"
LIVE_STEER_VOLTS = LIVE + "SteerVolts"
LIVE_DRIVE_AMPS = LIVE + "DriveAmps"
LIVE_STEER_AMPS = LIVE + "SteerAmps"
LIVE_DRIVE_TEMP_C = LIVE + "DriveTempC"
LIVE_STEER_TEMP_C = LIVE + "SteerTempC"
LIVE_FAULTS = LIVE + "Faults"
LIVE_ABS_READ_ISSUE = LIVE + "AbsoluteReadIssue"
LIVE_HEADING_DEG = LIVE + "HeadingDeg"
LIVE_ACCEL = LIVE + "AccelMps2"
LIVE_GYRO = LIVE + "Gyro"
LIVE_POSE = LIVE + "Pose"
LIVE_VISION_POSE = LIVE + "VisionPose"

# motor guard, robot -> laptop: every watched motor, swerve and mechanism; arrays follow Names
MOTORS = ROOT + "/Motors/"
MOTORS_NAMES = MOTORS + "Names"
MOTORS_KINDS = MOTORS + "Kinds"
MOTORS_STAGE = MOTORS + "Stage"
MOTORS_HEAT_PCT = MOTORS + "HeatPct"
MOTORS_TEMP_C = MOTORS + "TempC"
MOTORS_AMPS = MOTORS + "Amps"
MOTORS_LIMIT_A = MOTORS + "LimitA"
MOTORS_BASE_LIMIT_A = MOTORS + "BaseLimitA"
MOTORS_STALL_S = MOTORS + "StallS"
MOTORS_OVERRIDE_S = MOTORS + "OverrideS"
MOTORS_CAUSE = MOTORS + "Cause"
MOTORS_FLAGS = MOTORS + "Flags"
MOTORS_HISTORY = MOTORS + "History"
MOTORS_RPM = MOTORS + "Rpm"
MOTORS_EVENTS = MOTORS + "Events"
MOTORS_REPORT = MOTORS + "Report"
MOTORS_GUARD_ON = MOTORS + "GuardOn"
MOTORS_PRESENT = MOTORS + "Present"
MOTORS_DROPOUTS = MOTORS + "Dropouts"
MOTORS_RESETS = MOTORS + "Resets"
MOTORS_BROWNOUTS = MOTORS + "Brownouts"
MOTORS_BUS_VOLTS = MOTORS + "BusVolts"
MOTORS_CAN_IDS = MOTORS + "CanIds"
MOTORS_CONTROLLERS = MOTORS + "Controllers"            # what each controller says it is
MOTORS_CODE_CONTROLLERS = MOTORS + "CodeControllers"   # what the code created it as
MOTORS_FIRMWARE = MOTORS + "Firmware"

# Which battery is in: a "String Chooser" a dashboard shows as a drop-down; a client writes "selected".
BATTERY_CHOOSER = "/SmartDashboard/Battery/"
BATTERY_SELECTED = BATTERY_CHOOSER + "selected"
BATTERY_OPTIONS = BATTERY_CHOOSER + "options"
BATTERY_ACTIVE = BATTERY_CHOOSER + "active"
BATTERY_ID = ROOT + "/Battery/Id"
BATTERY_REST_VOLTS = ROOT + "/Battery/RestVolts"
BATTERY_CHECK = ROOT + "/Battery/Check"
BATTERY_NEXT = ROOT + "/Battery/Next"
# Utilization 0-1, bus-off count, TX-full count, receive errors, transmit errors, and the running
# count of robot loops that saw any receive or transmit error (the wiggle test watches that one).
WIRING_CAN = ROOT + "/Wiring/Can"

# AdvantageKit's own live topics (NT4Publisher), read for power and CAN health.
AK = "/AdvantageKit"
AK_PDH_CURRENTS = AK + "/PowerDistribution/ChannelCurrent"
AK_PDH_VOLTAGE = AK + "/PowerDistribution/Voltage"
AK_PDH_FAULTS = AK + "/PowerDistribution/Faults"
AK_PDH_STICKY = AK + "/PowerDistribution/StickyFaults"
AK_BATTERY = AK + "/SystemStats/BatteryVoltage"
AK_BROWNED_OUT = AK + "/SystemStats/BrownedOut"

# motor guard, laptop -> robot
MOTORS_OVERRIDE_SEQ = MOTORS + "Override/Seq"
MOTORS_OVERRIDE_BOOT_ID = MOTORS + "Override/BootId"
MOTORS_OVERRIDE_NAME = MOTORS + "Override/Name"
MOTORS_OVERRIDE_SECONDS = MOTORS + "Override/Seconds"
MOTORS_OVERRIDE_ACK_SEQ = MOTORS + "Override/AckSeq"
MOTORS_OVERRIDE_ACK_MESSAGE = MOTORS + "Override/AckMessage"
LIVE_VISION_COUNTS = LIVE + "VisionCounts"
LIVE_VISION_LAST_REJECT = LIVE + "VisionLastReject"
# Each camera's newest tags, 10 numbers a tag: ID, x y z (m) and quaternion w x y z of the tag in the
# camera frame, ambiguity, timestamp; and which camera saw each.
LIVE_VISION_SIGHTINGS = LIVE + "VisionSightings"
LIVE_VISION_SIGHTING_CAMERAS = LIVE + "VisionSightingCameras"
LIVE_BUS_VOLTS = LIVE + "BusVolts"
LIVE_ROBOT_MODE = LIVE + "RobotMode"
LIVE_FMS_ATTACHED = LIVE + "FmsAttached"
LIVE_TIMESTAMP = LIVE + "Timestamp"

# simulation only
SIM_REQUEST_ENABLE = ROOT + "/Sim/RequestEnable"

# Live per-module arrays, in the order the GUI shows them.
LIVE_MODULE_ARRAYS = {
    "steer": LIVE_STEER_DEG,
    "steer_sp": LIVE_STEER_SETPOINT_DEG,
    "steer_motor": LIVE_STEER_MOTOR_DEG,
    "steer_raw": LIVE_STEER_RAW_DEG,
    "v": LIVE_DRIVE_MPS,
    "v_sp": LIVE_DRIVE_SETPOINT_MPS,
    "pos": LIVE_DRIVE_POSITION_M,
    "drive_volts": LIVE_DRIVE_VOLTS,
    "steer_volts": LIVE_STEER_VOLTS,
    "drive_amps": LIVE_DRIVE_AMPS,
    "steer_amps": LIVE_STEER_AMPS,
    "drive_temp": LIVE_DRIVE_TEMP_C,
    "steer_temp": LIVE_STEER_TEMP_C,
    "abs_issue": LIVE_ABS_READ_ISSUE,
}

# Per-motor columns of the motor guard's table.
MOTOR_STRINGS = {
    "name": MOTORS_NAMES,
    "kind": MOTORS_KINDS,
    "stage": MOTORS_STAGE,
    "cause": MOTORS_CAUSE,
    "flags": MOTORS_FLAGS,
    "history": MOTORS_HISTORY,
    "controller": MOTORS_CONTROLLERS,
    "code_controller": MOTORS_CODE_CONTROLLERS,
    "firmware": MOTORS_FIRMWARE,
}
MOTOR_NUMBERS = {
    "heat_pct": MOTORS_HEAT_PCT,
    "rpm": MOTORS_RPM,
    "temp": MOTORS_TEMP_C,
    "amps": MOTORS_AMPS,
    "limit": MOTORS_LIMIT_A,
    "base_limit": MOTORS_BASE_LIMIT_A,
    "stall_s": MOTORS_STALL_S,
    "override_s": MOTORS_OVERRIDE_S,
    "present": MOTORS_PRESENT,
    "dropouts": MOTORS_DROPOUTS,
    "resets": MOTORS_RESETS,
    "brownouts": MOTORS_BROWNOUTS,
    "bus_volts": MOTORS_BUS_VOLTS,
    "can_id": MOTORS_CAN_IDS,
}
STAGES = ("OK", "WARN", "DERATE", "SHUTOFF")

# Mirrors MotorKind.java: label, the team's current policy in amps, and the sensor temperatures
# that warn, derate and shut off, in C. The contract test checks every number.
MOTOR_KINDS = {
    "NEO_550": ("NEO 550", 20, 45, 55, 65),
    "NEO_V1_1": ("NEO V1.1", 60, 70, 80, 90),
    "NEO_2_0": ("NEO 2.0", 80, 70, 80, 90),
    "NEO_UNKNOWN": ("NEO (1.1 or 2.0?)", 60, 70, 80, 90),
    "VORTEX": ("NEO Vortex", 80, 85, 100, 110),
}
# Why the robot refused or stopped a test, as a short code an agent can act on. The robot sends
# sentences for people; these match them, most specific first. OTHER means read the message.
STOP_CODES = [
    # Bring-up's motor test.
    ("without turning", "JAMMED"), ("No motors are registered", "NO_MOTORS"), ("can't be run by a test", "NOT_SUPPORTED"),
    ("names a motor the robot", "BAD_ARGS"), ("No motor to run", "BAD_ARGS"),
    ("took the drivetrain", "DRIVETRAIN_TAKEN"), ("FMS", "FMS_ATTACHED"), ("autonomous", "AUTONOMOUS"), ("Say where the robot is", "ENV_UNSET"),
    ("environment changed", "ENV_CHANGED"), ("heartbeat", "NO_HEARTBEAT"), ("gyro", "GYRO"),
    ("clear floor", "NO_SPACE"), ("eadman", "DEADMAN"), ("stick", "DRIVER_INPUT"),
    ("NOT on blocks", "NOT_ON_BLOCKS"), ("Impact", "IMPACT"), ("Left the declared space", "GEOFENCE"),
    ("solid wall", "NO_WALL"), ("motor is at", "MOTOR_GUARD"), ("stalled", "STALL"), ("Wheel speed", "OVERSPEED"),
    ("current limit was cut", "MOTOR_GUARD"), ("m of floor only allows", "NO_SPACE"), ("Spinning needs", "NO_SPACE"),
    ("cannot run with the robot declared", "WRONG_PLACE"), ("Busy:", "BUSY"), ("not applied while", "GAINS_REFUSED"),
    ("attery", "BATTERY"), ("Robot disabled", "DISABLED"), ("only allowed while the robot is disabled", "NEEDS_DISABLED"),
    ("time limit", "TIMEOUT"), ("Aborted from the laptop", "ABORTED_BY_PERSON"), ("controller", "NO_CONTROLLER"),
    ("PDH", "NO_PDH"), ("already running", "BUSY"), ("Not connected", "NOT_CONNECTED"), ("No answer", "NOT_CONNECTED"),
    ("error", "ROBOT_ERROR"), ("could not start", "ROBOT_ERROR"),
    # The test's own arguments: fix the command, not the robot.
    ("current ceiling", "BAD_ARGS"), ("At most", "BAD_ARGS"), ("Steps must stay", "BAD_ARGS"), ("Pick at least", "BAD_ARGS"),
    ("m/s cap", "BAD_ARGS"), ("Unknown module", "BAD_ARGS"),
    # Waited a minute for a condition; the reason after the colon usually matched above.
    ("Gave up", "WAITED_TOO_LONG"),
    # Stopped mid lift check: the reason after the colon (the deadman, above) usually matched.
    ("Enable the robot", "DISABLED"), ("lift check", "ABORTED_BY_PERSON"),
]


def stop_code(message):
    """``"IMPACT"`` for "Impact: 14.2 m/s^2. ...": the code for a refusal or abort message."""
    m = str(message or "")
    return next((code for key, code in STOP_CODES if key in m), "OTHER")


# Longest thermal override the robot grants, seconds (MotorGuard.MAX_OVERRIDE_S).
MAX_OVERRIDE_S = 20


def motor_kind_from_text(text):
    """MotorKind.parse in Python: an inventory name or YAGSL type to a MOTOR_KINDS key."""
    t = (text or "").lower().replace(" ", "").replace(".", "")
    if "550" in t:
        return "NEO_550"
    if "vortex" in t or "sparkflex" in t:
        return "VORTEX"
    if "neo20" in t or "neo2_0" in t or "neo_2_0" in t or t == "neo2":
        return "NEO_2_0"
    if "neo11" in t or "neov11" in t or "neo_v1_1" in t or "neo1_1" in t:
        return "NEO_V1_1"
    return "NEO_UNKNOWN"


# Gains the robot accepts live, and the range it accepts them in. Mirrors LiveGains.SPECS; the
# contract test checks both the names and the bounds.
GAIN_SPECS = {
    "Steer/kP": (0, 0.2),
    "Steer/kI": (0, 0.01),
    "Steer/kD": (0, 2.0),
    "Steer/IZone": (0, 90),
    "Drive/kP": (0, 2.0),
    "Drive/kI": (0, 0.5),
    "Drive/kD": (0, 5.0),
    "Drive/IZone": (0, 5),
    "Steer/RampS": (0, 1.0),
    "Drive/RampS": (0, 1.0),
    "Drive/VelPeriodMs": (0, 64),
    "Drive/VelDepth": (0, 8),
    "Chassis/AngVelCoeff": (-0.3, 0.3),
    "EncoderSync/Enabled": (0, 1),
    "EncoderSync/DeadbandDeg": (0.25, 10),
}
FF_SPECS = {"kS": (0, 1.5), "kV": (0.5, 8.0), "kA": (0, 4.0)}

ENVIRONMENTS = ("UNSET", "SIM", "BLOCKS", "FIELD")
TESTS = ("capture", "steer_step", "drive_step", "drive_ff", "spin", "straight", "slip", "pdh_map", "spin_ff",
         "controller", "motor_test")
