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
GAINS_APPLY_SEQ = ROOT + "/Gains/ApplySeq"
GAINS_BOOT_ID = ROOT + "/Gains/BootId"
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
LIVE_POSE = LIVE + "Pose"
LIVE_VISION_POSE = LIVE + "VisionPose"
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
TESTS = ("capture", "steer_step", "drive_step", "drive_ff", "spin", "straight")
