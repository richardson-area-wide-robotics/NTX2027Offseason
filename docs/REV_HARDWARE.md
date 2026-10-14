# Our hardware: REV's numbers

The motors, motor controllers, swerve modules and battery on Peashooter and Black team, with the
numbers their makers publish and where each comes from. Collected 2026-10-12 from
[docs.revrobotics.com](https://docs.revrobotics.com/brushless), REV's product pages and datasheets,
REV's release notes, and MK Battery's datasheet. The tools read the same numbers from
`tools/slothtune/revspecs.py`; a test keeps the two, the practice pod and the robot code in step.

The robots run **YAGSL**, not REV's MAXSwerve Java template. Nothing here comes from the template,
and its constants (max speed, slew rates) don't apply to our code.

## What is on the robots

| Where | Motor | Controller |
|---|---|---|
| Swerve drive (both robots) | NEO Vortex | SPARK Flex |
| Swerve steering (both robots) | NEO 550 | SPARK MAX |
| Peashooter: Spindexter | NEO 2.0 | SPARK MAX |
| Peashooter: Tower, intake, shooter | NEO Vortex | SPARK Flex |
| Black team: intake, shooter | NEO 2.0 | SPARK MAX |

The Motors tab shows this live: what the code creates, what each controller says it is, its
firmware, and the motor.

## Motors

All at 12 V: "All of the data listed on the product page and motor testing was run at 12V" (REV FAQ).

| | NEO V1.1 | NEO 2.0 | NEO Vortex | NEO 550 |
|---|---|---|---|---|
| Part | REV-21-1650 | REV-21-1653 | REV-21-1652 | REV-21-1651 |
| Kv (rpm per volt) | 473 | 473 | 565 | 917 |
| Free speed | 5676 rpm | 5676 rpm | 6784 rpm | 11000 rpm |
| Free current | 1.8 A | 1.8 A | 3.6 A | 1.4 A |
| Stall current | 105 A | 150 A | 211 A | 100 A |
| Stall torque | 2.6 N·m | 3.75 N·m | 3.6 N·m | 0.97 N·m |
| Peak power | 406 W | 540 W | 640 W | 279 W |
| Encoder | 42 counts/turn (hall) | not published | 7168 counts/turn on a SPARK Flex; 42 through the Solo Adapter on a SPARK MAX | 42 counts/turn (hall) |
| Weight | 425 g | 364 g | 447 g | 142 g |
| Shaft | 8 mm keyed | 15T spline | 1/2 in hex spindle (docked) | 1/8 in |
| REV's current-limit advice | 40 to 60 A | none published | 80 A | 20 to 40 A |
| Our policy | 60 A | 80 A | 80 A | 20 A |
| Docs | [NEO V1.1](https://docs.revrobotics.com/brushless/neo/v1.1) | [NEO 2.0](https://docs.revrobotics.com/brushless/neo/2.0) | [Vortex](https://docs.revrobotics.com/brushless/neo/vortex) | [NEO 550](https://docs.revrobotics.com/brushless/neo/550) |

What these numbers mean for us:

- **A NEO V1.1 and a NEO 2.0 spin exactly alike** (same Kv, same free speed), so no measurement can
  tell them apart; only a person can. Look at the shaft (2.0: spline; V1.1: keyed round), the
  sensor cable (2.0: unplugs; V1.1: fixed) and the body (2.0: 48 mm long with flats; V1.1: 58 mm round).
  The NEO V1.1 is discontinued.
- **A Vortex spins about 20% faster per volt than a NEO.** That is how a floor drive_ff run names
  the drive motors (NEO about 473 rpm per volt, Vortex 565, NEO 550 917).
- **The NEO 550 cooks fast when it can't turn.** REV's locked-rotor test: it survived 220 s at
  20 A, failed after about 27 s at 40 A, 5.5 s at 60 A and 2 s at 80 A (the SPARK's default limit).
  That is why steering runs at 20 A. A NEO V1.1 stalled at 60 A failed after about 105 s.
- REV doesn't publish torque per amp (Kt), winding resistance or a maximum temperature for any of
  these, or the NEO 2.0's encoder resolution. The tools work these out from the numbers above
  rather than invent them.

Where REV's own pages disagree:
- The NEO 2.0 table mixes the NEO V1.1's measured speed with its theoretical stall numbers
  (150 A, 3.75 N·m are the V1.1's theoretical values; its measured ones are 105 A and 2.6 N·m).
- The Vortex's Kv is 565 in the spec table (6784 rpm / 12 V), 560 in a feature list, and 550 in an
  older "pre-production" table. The tools use 565.
- The NEO 2.0 product page lists "REV-21-1651" in its kit contents; that is the NEO 550's part number.

## Motor controllers

| | SPARK MAX | SPARK Flex |
|---|---|---|
| Part | REV-11-2158 | REV-11-2159 |
| Supply | 5.5 to 24 V (30 V absolute max) | 6 to 24 V (30 V absolute max) |
| Browns out below | 5.5 V | 4.5 V |
| Continuous current | 60 A | 60 A (tested for 3 minutes) |
| Peak current | 100 A for 2 s | 100 A for 2 s |
| Motors | NEO, NEO 2.0, NEO 550; a Vortex through the Solo Adapter | Vortex docked; NEO and NEO 550 through the Flex Dock |
| Newest firmware | 26.1.5 (2026-03-12) | 26.1.6 (2026-03-16) |
| REVLib class | `SparkMax` | `SparkFlex` |
| Docs | [specs](https://docs.revrobotics.com/brushless/spark-max/specs) | [specs](https://docs.revrobotics.com/brushless/spark-flex/specs) |

- **Firmware**: REVLib 2026.0.5 (what the robots use) warns about any SPARK not on 2026 firmware.
  Update with **REV Hardware Client 2**; Client 1 can't install 2026 firmware. The Motors tab flags
  old firmware. Firmware notes: [REV-Software-Binaries releases](https://github.com/REVrobotics/REV-Software-Binaries/releases).
- **Each SPARK reports which kind it is** over CAN, so the robot flags one the code created as the
  other kind at boot.
- **The battery browns out the roboRIO (about 6.8 V) before any SPARK** (5.5 V and 4.5 V).
- **Current**: the smart current limit holds the motor's *phase* current; what the PDH measures is
  the battery side, which is less at low speed. `getOutputCurrent()` is phase current.
- **Voltage compensation**: YAGSL turns it on at 12 V for every swerve SPARK, so a duty of 0.5
  means 6 V on any battery, until the battery sags below what is asked. REV documents the setting
  but not its formula.
- **Speed measurement on the drive**: a Vortex on a SPARK Flex counts 7168 steps a turn, and YAGSL
  sets its speed window to 10 ms × 2. (A NEO on a SPARK MAX counts 42 and keeps the SPARK's
  32 ms × 8 window; YAGSL's setting doesn't reach a hall sensor.) The tools' delay advice and
  predictions use the right one for each robot.

## The swerve modules: MAXSwerve (REV-21-3005)

From the [product page](https://www.revrobotics.com/rev-21-3005/) and REV's
[build guide](https://docs.revrobotics.com/ion-build/build-guides/maxswerve-module-assembly).

**Drive gearing.** Every ratio is 3:1 at the bevel times spur over pinion. Our robots run **Low,
5.50:1** (12T pinion, 22T spur).

| REV's name | Ratio | Pinion | Spur | Free speed, NEO | Free speed, Vortex |
|---|---|---|---|---|---|
| Low | 5.50:1 | 12T | 22T | 4.12 m/s | 4.92 m/s |
| Medium | 5.08:1 | 13T | 22T | 4.46 m/s | 5.33 m/s |
| High | 4.71:1 | 14T | 22T | 4.80 m/s | 5.74 m/s |
| Extra High 1 | 4.50:1 | 14T | 21T | 5.03 m/s | 6.01 m/s |
| Extra High 2 | 4.29:1 | 14T | 20T | 5.28 m/s | 6.32 m/s |
| Extra High 3 | 4.00:1 | 15T | 20T | 5.66 m/s | 6.77 m/s |
| Extra High 4 | 3.75:1 | 16T | 20T | 6.04 m/s | 7.22 m/s |
| Extra High 5 | 3.56:1 | 16T | 19T | 6.36 m/s | 7.60 m/s |

The Extra High gears come in the Gear Ratio Upgrade Kit (REV-21-3008). A NEO 2.0 needs the 15T
Spline Input Kit (REV-21-3009). Free speeds are motor free speed through the gearing on a new 3 in
wheel; the robot's real top speed on carpet is lower, and the straight-line test measures it.

**Steering.** NEO 550 through an UltraPlanetary (4:1 and 3:1 cartridges, really 76:21 and 84:29)
to the steering gear: 46.42:1 exactly (9424:203).

**Absolute encoder.** A Through Bore Encoder turned 1:1 by the steering gear, wired to the
steering SPARK MAX's data port through the Absolute Encoder Adapter. V1 is 10-bit (about 0.35°),
V2 12-bit (±0.5°).

**Zeroing (REV's way).** In REV Hardware Client: Utilities, Absolute Encoder; fit the Calibration
Tool lip-side to the module with the bevel gear at the orange dot, then Set Zero Offset. The Guide
tab's offset step does the same job in YAGSL's terms.

**Wheel.** 3 in nominal. Replace the plastic V2 wheel when its tread is gone (REV advises at 1/2 in
of depth lost); replace spiky tread at 1/8 in less diameter or on flat spots. A worn wheel makes
the robot travel less than odometry thinks; the Calibrate tab's push test measures each wheel.

**Geometry.** The wheel's center is 1.75 in in from the module's outer edge; the module takes 2×1
tube or MAXTube. 1720 g each with a NEO.

**Upkeep.** REV's [pre-match checklist](https://docs.revrobotics.com/ion-build/motion/maxswerve/maxswerve-module-inspection):
wheel wear, fork and axle screws, bevel gears, hub bolts, grease, the six UltraPlanetary bolts,
both encoder cables on the steering SPARK, and the drive and steering turning independently.

## The battery: MK ES17-12

From MK Battery's [datasheet](https://revrobotics.com/content/docs/ES17-12_User_Guide.pdf): 12 V
nominal; 18 Ah drained over 20 hours, but 9.6 Ah at 18 A and 6.3 Ah at 54 A; about 12 mΩ inside
(measured at 1 kHz); 270 A for at most 5 s; 5.86 kg.

"12 V" is the label. Charged and rested it reads about 12.7 to 13 V; under load it sags by its
resistance times the current. The tools measure each battery's sag in every wheel test and match
log; see **Batteries** in `SWERVE_TUNING_GUIDE.md` for how the drive team picks which one is in.
