# Moving the swerve tools to 2027 (WPILib 2027, SystemCore, REVLib 2027)

Written October 2026, against **WPILib 2027 alpha 7**. REVLib's public changelog has no 2027
release yet (its latest is 2026.0.5), and YAGSL and AdvantageKit are still on 2026. Don't port
the competition robots until the vendors' 2027 libraries are out; this note is for whoever does it
then, and for keeping new code from making it harder.

## How the code is already set up for it

Each thing 2027 changes is kept behind one small piece, so porting means changing that piece and
nothing else:

| What changes in 2027 | Where it is confined |
|---|---|
| `DriverStation` splits into `MatchState` and `RobotState` | `RobotSignals.Wpilib` |
| Commands v3 (can't be installed alongside v2) | `DriveOwnership` / `CommandsV2` |
| WPILib's JSON library (Jackson to Avaje Jsonb) | `MiniJson` reads `swervetune.json` with neither |
| YAGSL, the motor vendor, the module hardware | `DrivetrainIO` / `YagslDrivetrainIO` |
| Camera libraries (PhotonLib's estimator API) | `VisionSource`; `PhotonVisionSource` is the only file importing PhotonLib |
| AdvantageKit | `AkLogging` is the only file importing it (plus `extends LoggedRobot` in each `Robot`) |
| pyntcore's method names (camelCase to snake_case) | `link.py`'s `_call` tries both |
| SystemCore's addresses (hostname `robot`, USB and Wi-Fi addresses) | `link.py`'s `candidate_hosts` already tries them |
| No SPI on SystemCore | The config lint flags an SPI gyro (both robots have a navX on SPI today; the Redux Canandgyro, on CAN, is the planned replacement) |

`Sampler`, `SafetySupervisor`, `MotorGuard`'s logic and `VisionGate` touch no WPILib API at all.

## The porting checklist

### WPILib

1. **Import each robot project** with the 2027 VS Code importer. It moves `edu.wpi.first` to
   `org.wpilib` (and subpackages) and fixes the robot construction. Java 25 is required.
2. **Constants are ALL_CAPS** (alpha 7), enum values included. `AkLogging.chooseFolder` compares
   against `RuntimeType.kRoboRIO2`; update it, and decide where SystemCore keeps logs (it has no
   roboRIO 1 / roboRIO 2 split).
3. **`DriverStation` split**: rewrite `RobotSignals.Wpilib` only. Test mode becomes Utility mode:
   the tools run tests in Teleop or Test, so check the mode names there.
4. **CAN devices take a `CANPort`** instead of an integer bus. SystemCore has several CAN buses:
   - each robot's subsystems need their bus;
   - `RobotSignals.canStatus()` reads one bus, and must become one per bus;
   - `DashboardAlerts` and the Wiring tab judge one bus. `wiring.json` already holds a list of
     buses, but `wiring.diagnose`, the schematic and the post-match summary only read the first.
5. **`Alert` moved to wpiutil** (`DashboardAlerts`).
6. **The AprilTag library is now a vendordep**, and `AprilTagFields` became part of `Fields`
   (`FieldLayouts`, `PhotonVisionSource`).
7. **SmartDashboard is gone** (it used NetworkTables 3). Peashooter's `Drive.java` puts two numbers
   there; move them to the Telemetry API or to AdvantageKit's `Logger.recordOutput`. The tools
   already use NetworkTables 4 only. The dashboard's **Battery** drop-down (`BatteryPicker`) is
   published as raw NT4 topics in the "String Chooser" shape under `/SmartDashboard/Battery`,
   without the SmartDashboard class, so it keeps working; check the 2027 dashboards still show
   that shape as a drop-down.
8. **`Command.schedule()` is deprecated** (Peashooter's `Robot.java` uses it for autonomous).
9. **Raw integer timestamps become nanoseconds** (`RobotController.getTime`, `getFPGATime`,
   `nt::Now`). DataLog files and NetworkTables still use microseconds, so the log tools
   (`logsummary`, `akit`, `pdhports`) are unaffected; check any new code that does arithmetic on
   raw timestamps.

### REVLib

- **Conversion factors are being dropped.** On 2026 SPARKs with YAGSL's factors, steering gains
  are duty cycle per degree and drive gains are duty cycle per (m/s). Without the factors they
  will be per motor rotation. Then the gain ranges in `LiveGains`, the advisor's suggestions and
  the saved gains in each robot's JSON all need converting, by the gear ratio and wheel size.
- The SPARK derivative term is per 1 ms controller step (REV kD = 1000 x WPILib's per-second kD);
  check it stays that way.
- MAXMotion is trapezoid-only; the S-curve option exists in the API but does nothing yet. The
  locked "second-order" Guide step assumes trapezoids.
- `SparkChannel` reads `getPeriodicStatus0()` for CAN presence and the sticky `hasReset` warning
  for reboots: check both still exist.

### YAGSL

YAGSL 2026.8 and later move to a new JSON schema (built on YAMS) with renamed fields, and old files
load without an error while silently dropping what was renamed. The config lint refuses to judge
a newer YAGSL than it knows (`YAGSL_SCHEMA_MAX` in `yagslcfg.py`); update the reader and the lint
before trusting either.

### AdvantageKit and PhotonLib

- `AkLogging.pdhCurrents()` reads the PDH through AdvantageKit's `ConduitApi`. Check it survives
  and still reports every channel; the PDH port finder depends on it.
- PhotonLib 2027 drops the constructor-chosen estimator strategy and `update()`.
  `PhotonVisionSource` already uses the per-call 2026 API.

### The laptop tools

- Python 3.12 and `pyntcore`; on 2027 pyntcore the snake_case names are handled. Re-run the
  Python tests (`py -3.12 -m unittest discover -s swervetune/tests` from `tools/`) against the
  2027 package.
- The CI "tools" job pins `robotpy-wpiutil<2027`; move the pin when the 2027 packages are
  released.

## Before calling it done

- Both robots build, and all Java tests pass (`./gradlew build`).
- Every Python test passes.
- In the simulator: connect, run `steer_step` and `drive_ff`, check the Motors, Wiring and Live
  tabs, and that AdvantageKit's PDH and CAN topics appear.
- On a robot: the Guide's first five steps, and one match log through the post-match summary.
