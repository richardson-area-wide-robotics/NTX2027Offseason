"""REV's published numbers for the hardware on these robots, in one place.

Collected from docs.revrobotics.com, revrobotics.com product pages and datasheets, and REV's
release notes on 2026-10-12 (``COLLECTED``). Every value cites the page it came from; where REV's
own pages disagree, the note says so and the value used is the one REV's spec table gives.
``docs/REV_HARDWARE.md`` is the readable version, for students.

What REV doesn't publish, nobody should invent: no Kt, winding resistance or maximum temperature
for any motor, no NEO 2.0 encoder resolution, no CAN bitrate, no voltage-compensation formula.

The robots run YAGSL, not REV's MAXSwerve Java template; nothing here comes from the template.
"""

from __future__ import annotations

import re

COLLECTED = "2026-10-12"
DOCS = "https://docs.revrobotics.com/brushless"

# ---------------------------------------------------------------------------- motors
# All at 12 V: "All of the data listed on the product page and motor testing was run at 12V" (FAQ).
MOTORS = {
    "neo": {
        "label": "NEO V1.1", "part": "REV-21-1650", "kv_rpm_per_v": 473, "free_rpm": 5676, "free_a": 1.8,
        "stall_a": 105, "stall_nm": 2.6, "peak_w": 406, "counts_per_rev": {"SPARK MAX": 42, "SPARK Flex": 42},
        "mass_kg": 0.425, "shaft": "8 mm keyed", "current_limit_a": (40, 60),
        "note": "Empirical, measured with a SPARK MAX. Theoretical: 150 A, 2.8 ft·lb (3.75 N·m), 540 W. Discontinued; "
                "replaced by the NEO 2.0.",
        "locked_rotor": {60: "fails after about 105 s stalled", 80: "torque collapses after about 43 s"},
        "source": "https://docs.revrobotics.com/brushless/neo/v1.1",
    },
    "neo2": {
        "label": "NEO 2.0", "part": "REV-21-1653", "kv_rpm_per_v": 473, "free_rpm": 5676, "free_a": 1.8,
        "stall_a": 150, "stall_nm": 3.75, "peak_w": 540, "counts_per_rev": {},
        "mass_kg": 0.364, "shaft": "15T spline", "current_limit_a": None,
        "note": "REV's table mixes the NEO V1.1's empirical speed with its theoretical stall numbers; no "
                "NEO 2.0 current-limit advice or encoder resolution is published. It spins exactly like a "
                "V1.1, so only a person can tell them apart: spline shaft, detachable sensor cable, 1.9 in (48 mm) body.",
        "source": "https://docs.revrobotics.com/brushless/neo/2.0",
    },
    "vortex": {
        "label": "NEO Vortex", "part": "REV-21-1652", "kv_rpm_per_v": 565, "free_rpm": 6784, "free_a": 3.6,
        "stall_a": 211, "stall_nm": 3.6, "peak_w": 640, "counts_per_rev": {"SPARK Flex": 7168, "SPARK MAX": 42},
        "mass_kg": 0.447, "shaft": "1/2 in hex spindle (docked)", "current_limit_a": (80, 80),
        "note": "Docks to a SPARK Flex, or runs from a SPARK MAX through the Solo Adapter (REV-11-2828) with "
                "only 42 counts a turn. Some REV pages say 560 or 550 Kv; the spec table says 565 "
                "(6784 rpm / 12 V).",
        "source": "https://docs.revrobotics.com/brushless/neo/vortex",
    },
    "neo550": {
        "label": "NEO 550", "part": "REV-21-1651", "kv_rpm_per_v": 917, "free_rpm": 11000, "free_a": 1.4,
        "stall_a": 100, "stall_nm": 0.97, "peak_w": 279, "counts_per_rev": {"SPARK MAX": 42, "SPARK Flex": 42},
        "mass_kg": 0.142, "shaft": "1/8 in (3.175 mm)", "current_limit_a": (20, 40),
        "note": "Low thermal mass: at a stall it survived 220 s at 20 A, about 27 s at 40 A, 5.5 s at 60 A and "
                "2 s at 80 A (the SPARK's default limit).",
        "locked_rotor": {20: "survived the 220 s test", 40: "about 27 s", 60: "about 5.5 s", 80: "about 2 s"},
        "source": "https://docs.revrobotics.com/brushless/neo/550",
    },
}
# The motor guard's labels (MotorKind.java) to the keys above.
LABEL_TO_KEY = {"NEO V1.1": "neo", "NEO 2.0": "neo2", "NEO Vortex": "vortex", "NEO 550": "neo550"}

# ---------------------------------------------------------------------------- controllers
CONTROLLERS = {
    "SPARK MAX": {
        "part": "REV-11-2158", "volts": (5.5, 24.0), "abs_max_v": 30.0, "brownout_v": 5.5,
        "continuous_a": 60, "peak_a": 100, "peak_s": 2, "latest_firmware": "26.1.5",
        "firmware_date": "2026-03-12", "java_class": "SparkMax",
        "source": "https://docs.revrobotics.com/brushless/spark-max/specs",
    },
    "SPARK Flex": {
        "part": "REV-11-2159", "volts": (6.0, 24.0), "abs_max_v": 30.0, "brownout_v": 4.5,
        "continuous_a": 60, "peak_a": 100, "peak_s": 2, "latest_firmware": "26.1.6",
        "firmware_date": "2026-03-16", "java_class": "SparkFlex",
        "source": "https://docs.revrobotics.com/brushless/spark-flex/specs",
    },
}
FIRMWARE_SOURCE = "https://github.com/REVrobotics/REV-Software-Binaries/releases"
# REVLib 2026.0.5 warns about SPARKs not on 2026 firmware, and REV Hardware Client 2 (needed for
# 26.x) is the only one that updates them; Client 1 handles only 2025 and earlier.
MIN_SEASON_FIRMWARE = 26
REVLIB = {"2026": "2026.0.5", "2027": "2027.0.0-alpha-8"}


def firmware_tuple(text):
    """``"v26.1.5"`` or ``"26.1.5"`` -> ``(26, 1, 5)``; None if it isn't a version."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def firmware_finding(controller, firmware):
    """``(level, title, why)`` for a controller's firmware, or None when it is current or unknown."""
    have = firmware_tuple(firmware)
    spec = CONTROLLERS.get(controller)
    if not have or not spec:
        return None
    latest = spec["latest_firmware"]
    if have[0] < MIN_SEASON_FIRMWARE:
        return ("warn", f"{controller} firmware {firmware} is from before 2026",
                f"REVLib 2026 expects 2026 firmware. Update to {latest} with REV Hardware Client 2 "
                "(Client 1 can't install 2026 firmware).")
    if have < firmware_tuple(latest):
        return ("info", f"{controller} firmware {firmware}; the newest is {latest}",
                f"REV released {latest} on {spec['firmware_date']}. Update with REV Hardware Client 2 "
                "between events, not at one.")
    return None


# ---------------------------------------------------------------------------- velocity measurement
def drive_speed_sensor(kind):
    """How a drive motor's speed is measured on these robots: ``(period_ms, depth, counts_per_rev, words)``.

    A Vortex on a SPARK Flex: 7168 counts a turn, and YAGSL sets the Flex's encoder window to
    10 ms x 2 (SparkFlexSwerve.configureIntegratedEncoder). A NEO on a SPARK MAX: the 42-count hall
    sensor, which YAGSL's quadrature setting doesn't reach, so the SPARK's 32 ms x 8 default stands.
    """
    if kind == "vortex":
        return 10, 2, 7168, "the Vortex's 7168-count encoder, averaged over 10 ms x 2 (YAGSL's setting)"
    return 32, 8, 42, "the NEO's 42-count hall sensor, averaged over 32 ms x 8 (the SPARK's default)"


# ---------------------------------------------------------------------------- MAXSwerve
MAXSWERVE = {
    "part": "REV-21-3005",
    # Name, ratio, pinion, spur. Every ratio is 3:1 bevel times spur over pinion.
    "drive_ratios": [
        ("Low", 5.50, "12T", "22T"), ("Medium", 5.08, "13T", "22T"), ("High", 4.71, "14T", "22T"),
        ("Extra High 1", 4.50, "14T", "21T"), ("Extra High 2", 4.29, "14T", "20T"),
        ("Extra High 3", 4.00, "15T", "20T"), ("Extra High 4", 3.75, "16T", "20T"),
        ("Extra High 5", 3.56, "16T", "19T"),
    ],
    # REV's free speeds, m/s, by ratio and motor.
    "free_speed_mps": {5.50: {"neo": 4.12, "vortex": 4.92}, 5.08: {"neo": 4.46, "vortex": 5.33},
                       4.71: {"neo": 4.80, "vortex": 5.74}, 4.50: {"neo": 5.03, "vortex": 6.01},
                       4.29: {"neo": 5.28, "vortex": 6.32}, 4.00: {"neo": 5.66, "vortex": 6.77},
                       3.75: {"neo": 6.04, "vortex": 7.22}, 3.56: {"neo": 6.36, "vortex": 7.60}},
    "steer_ratio": 9424 / 203,
    "wheel_d_in": 3.0,
    "wheel_center_from_edge_in": 1.75,
    "mass_kg_with_neo": 1.72,
    "abs_encoder": "Through Bore Encoder on the steering gear, 1:1; V1 is 10-bit (about 0.35°), V2 12-bit",
    "tread": "Plastic V2 wheel: replace when the tread is gone; REV advises at 1/2 in depth loss. "
             "Spiky tread: replace at 1/8 in less diameter, or on flat spots.",
    "source": "https://www.revrobotics.com/rev-21-3005/",
}
