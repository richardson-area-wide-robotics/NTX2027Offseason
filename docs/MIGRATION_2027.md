# Moving Sloth Tune to 2027 (WPILib 2027, SystemCore, REVLib 2027)

Written October 2026, against **WPILib 2027 alpha 7**. REVLib's public changelog has no 2027
release yet (its latest is 2026.0.5), and YAGSL and AdvantageKit are still on 2026. Don't port
the competition robots until the vendors' 2027 libraries are out; this note is for whoever does it
then, and for keeping new code from making it harder.

## How the code is already set up for it

Each thing 2027 changes sits behind a small piece where it could be kept there, but not every one
is in a single file. These are the files that change, counted from what each one imports (October
2026); the robot projects' own code is listed separately, because it is most of the work:

| What changes in 2027 | Library files that change | Robot code that changes |
|---|---|---|
| `DriverStation` splits into `MatchState` and `RobotState` | `RobotSignals.Wpilib` for every read; `reportWarning`/`reportError` calls in `SlothTune`, `AkLogging`, `FieldLayouts` and `PhotonVisionSetup` if those move | Any subsystem reading the match state |
| Commands v3 (can't be installed alongside v2) | `DriveOwnership` / `CommandsV2`, and `SlothTune.install`, which builds it | All of it: both `Robot.java`, every subsystem, the controller bindings, PathPlanner's `NamedCommands` |
| REVLib's 2027 API | `SparkChannel`, `YagslDrivetrainIO`, `MotorWatcher`, and `SlothTune`'s `watchMotor` overloads | Every subsystem that builds a `SparkMax` or `SparkFlex` (Peashooter's Shooter, Intake and Feeder; Black team's Shooter and Intake) |
| YAGSL, the module hardware | `DrivetrainIO` / `YagslDrivetrainIO`, and `SlothTune.install`, which takes a `SwerveDrive` | Each `Drive.java`, and the JSON files (see YAGSL below) |
| Gyros: no SPI on SystemCore | `YagslDrivetrainIO` (it reads the navX and the Canandgyro directly) | `swervedrive.json`'s IMU; the navX comes off, and the Canandgyro (Boron) goes on: [GYRO_CANANDGYRO.md](GYRO_CANANDGYRO.md). ReduxLib 2027 moves it to `com.reduxrobotics.canandgyro` with a `CANPort`; YAGSL 2027 calls it `canandgyro_can` |
| Alerts | `DashboardAlerts` | None |
| WPILib's JSON library (Jackson to Avaje Jsonb) | None: `MiniJson` reads `slothtune.json` with neither | None |
| Camera libraries (PhotonLib's estimator API) | `PhotonVisionSource` and `PhotonVisionSetup` only; `VisionSource` keeps PhotonLib out of the rest | `vendordeps/photonlib.json` in each robot |
| AdvantageKit | `AkLogging` only | `extends LoggedRobot` in each `Robot` |
| pyntcore's method names (camelCase to snake_case) | `link.py`'s `_call` tries both | None |
| SystemCore's addresses (hostname `robot`, USB and Wi-Fi addresses) | `link.py`'s `candidate_hosts` already tries them | None |

`Sampler`, `SafetySupervisor`, `MotorGuard`'s logic, `VisionGate` and `VisionTrust` touch no WPILib
API at all. In the library that is about a dozen files of 41 (39 in `slothtune`, 2 in its
PhotonVision adapter); in the robot projects, nearly every file.

Three more, outside that table:

- **Vendordeps the library always needs.** `YagslDrivetrainIO` imports the navX (Studica) and
  Canandgyro (ReduxLib) libraries directly, so every robot keeps both vendordeps until it is split,
  even after the navX comes off.
- **PathPlannerLib 2027**, and the `settings.json` fields `ppcheck` reads (`robotMass`,
  `robotMOI`, `wheelCOF`, `driveCurrentLimit`, `maxDriveSpeed`, the module offsets): check them
  against the 2027 file before trusting the PathPlanner check.
- **REVLib deprecations already in the code**: Black team's `Intake.java` uses
  `SparkBase.PersistMode` and `ResetMode`, which REVLib 2026 marks for removal.

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
   - `DashboardAlerts` judges one bus's health. The Wiring tab already maps, draws and checks
     every bus in `wiring.json` (each in its CTRE cable color, CAN-L green); what it lacks is a
     per-bus utilization and error count from the robot, so publish one per bus.
5. **`Alert` moved to wpiutil** (`DashboardAlerts`).
   **Sensor ports:** bring-up's live sensor readout opens the design file's sensors with
   `DigitalInput`, `AnalogInput`, `DutyCycleEncoder` and `Encoder` (`Sensors.Wpilib`). SystemCore's
   ports are configured differently: rewrite that one class, and the port ranges the design check
   uses (`design.RIO_PORTS` covers only the roboRIO).
6. **The AprilTag library is now a vendordep**, and `AprilTagFields` became part of `Fields`
   (`PhotonVisionSetup`, which picks the welded or AndyMark layout; `FieldLayouts` and
   `PhotonVisionSource` take a layout object and don't name the enum).
7. **SmartDashboard is gone** (it used NetworkTables 3). Peashooter's `Drive.java` puts two numbers
   there; move them to the Telemetry API or to AdvantageKit's `Logger.recordOutput`. The tools
   already use NetworkTables 4 only. The dashboard's **Battery** drop-down (`BatteryPicker`) is
   published as raw NT4 topics in the "String Chooser" shape under `/SmartDashboard/Battery`,
   without the SmartDashboard class, so it keeps working. Elastic's 2027 alphas read a chooser
   from `selected/tune` and `selected/value` instead of `selected` and `active` (2026); move
   `BatteryPicker` to whatever WPILib 2027's chooser publishes, and regenerate the drive team's
   layout (`tools/slothtune/elastic.py`).
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
- From REV's 2027 alpha release notes (checked 2026-10-12, latest 2027.0.0-alpha-8):
  - alpha-2 wraps every reading in a `Signal`: call `.get()`, and `.isValid()` says whether it is
    fresh. Every `SparkChannel` and `YagslDrivetrainIO` read changes.
  - alpha-7 constructors take a `CANPort`, and `getBusId()` became `getCanPort()`.
  - alpha-7 removes the hall-sensor velocity averaging settings for a new firmware filter
    (defaults: depth 8, sample delta 20). `applyDriveVelocityFilter` and the `Drive/VelPeriodMs`,
    `Drive/VelDepth` live gains need redoing; so does `revspecs.drive_speed_sensor`.
  - The 2027 API keeps the SPARK model enum `protected` with no public getter. `SparkChannel`
    reaches it by reflection, and `MotorGuardTest` fails the build the day that method is gone,
    rather than letting model detection go quiet.
- Firmware: REV Hardware Client 2 is the only updater for 2026 and later firmware; it also
  supports SystemCore.

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
  Python tests (`py -3.12 -m unittest discover -s slothtune/tests` from `tools/`) against the
  2027 package.
- The CI "tools" job pins `robotpy-wpiutil<2027`; move the pin when the 2027 packages are
  released.

## Before calling it done

- Both robots build, and all Java tests pass (`./gradlew build`).
- Every Python test passes.
- In the simulator: connect, run `steer_step` and `drive_ff`, check the Motors, Wiring and Live
  tabs, and that AdvantageKit's PDH and CAN topics appear.
- On a robot: the Guide's first five steps, and one match log through the post-match summary.
