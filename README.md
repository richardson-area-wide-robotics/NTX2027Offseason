# NTX 2027 Offseason

Offseason robot code for FRC Team 1745 (Richardson Area Wide Robotics). This repo holds three WPILib Java projects. Each one is a YAGSL swerve drive that runs in simulation.

| Project | Description |
| --- | --- |
| [`Black team/`](Black%20team/) | Swerve drive project for the Black team. Also includes the CTRE Phoenix 6 vendordep. |
| [`Peashooter/`](Peashooter/) | Swerve drive project for Peashooter. |
| [`Examples/`](Examples/) | Simulator only: mechanisms from past seasons (an elevator, a shooter pivot, a two-joint arm, a two-wheel shooter, a feeder, a climber), rebuilt the way these robots are written, to practice tuning in the Systems tab. |

## Team numbers

Each robot's team number is in its project's `.wpilib/wpilib_preferences.json`. `./gradlew deploy`
and the swerve tools use it to find the robot, so the robot's radio and the Driver Station must be set
to the same number.

| Robot | Team number |
| --- | --- |
| Peashooter | 1745 |
| Black team | 9990, the number it was given at competition |
| Test robots | 17451, 17452 and so on |

When a robot won't connect, see [Checking a robot's network](docs/NETWORK_CHECK.md).

Right now the robot code in Black team and Peashooter is the same. The assignment for each one is in its own readme ([Black team](Black%20team/readme.md), [Peashooter](Peashooter/README.md)).

## Requirements

- [WPILib 2026](https://docs.wpilib.org/en/stable/docs/zero-to-robot/step-2/wpilib-setup.html). It installs VS Code, JDK 17, and the simulator.
- An Xbox-style controller for driving in sim. The keyboard works too.

## Building and running

Every project builds on its own with Gradle. Open a project folder (for example `Peashooter/`) in WPILib VS Code, or `cd` into it before running commands. Don't run them from the repo root.

```bash
./gradlew build          # compile and run tests
./gradlew simulateJava   # launch the robot in the simulator GUI
./gradlew deploy         # deploy to the roboRIO (the project's team number, above)
```

On Windows, use `gradlew.bat` in place of `./gradlew`. In VS Code you can also run **WPILib: Simulate Robot Code** or **WPILib: Deploy Robot Code** from the command palette.

## Controls

The drive command uses the controller on port 0.

| Input | Action |
| --- | --- |
| Left stick | Translate |
| Right stick X | Rotate |
| A button | Switch between field-relative (the default) and robot-relative driving |

## Code layout

```
<project>/
├── src/main/java/frc/robot/
│   ├── Main.java      # entry point
│   ├── Robot.java     # TimedRobot: creates Drive, binds controls
│   └── Drive.java     # swerve subsystem (YAGSL SwerveDrive + drive commands)
├── src/main/deploy/swerve/   # YAGSL JSON config, deployed to the roboRIO
└── vendordeps/               # third-party library definitions
```

## Swerve configuration

The files in `src/main/deploy/swerve/` define a four-module swerve with these parts:

- **Drive motors:** NEOs on SPARK MAX, 5.50:1 reduction, 3 in wheels
- **Steer motors:** NEO 550s on SPARK MAX, 46.42:1 reduction, absolute encoders plugged into the SPARK MAX
- **Gyro:** navX over SPI
- **Module spacing:** 24 in × 24 in (each module is ±12 in from center)

| Module | Drive CAN ID | Steer CAN ID |
| --- | --- | --- |
| Front left | 32 | 31 |
| Front right | 12 | 11 |
| Back left | 42 | 4 |
| Back right | 22 | 21 |

The robot starts at pose (2 m, 2 m) facing 0°.

## Vendor libraries

- [YAGSL](https://github.com/BroncBotz3481/YAGSL) for the swerve drive
- [REVLib](https://docs.revrobotics.com/revlib) for SPARK MAX
- [AdvantageKit](https://docs.advantagekit.org/) for logging
- [PathPlannerLib](https://pathplanner.dev/) for autonomous paths
- ReduxLib, ThriftyLib, WPILib New Commands
- Phoenix 6 (Black team only)

## Contributing

`main` is protected. Branch, open a pull request, get a green build and an approval, then merge — [CONTRIBUTING.md](CONTRIBUTING.md) walks through it.

## Swerve tools

`tools/swervetune` is a browser app for tuning and checking both robots' swerve drives, watching the
motors, and finding wiring faults: `py -3.12 tools/swervetune gui`. Start with
[`docs/SWERVE_TUNING_GUIDE.md`](docs/SWERVE_TUNING_GUIDE.md). Also in `docs/`: the
[controls review](docs/CONTROLS_REVIEW.md), [vision setup](docs/VISION_LUMA_PHOTONVISION.md),
the [brief for AI agents](docs/AGENT_TUNING.md), [notes for 2027](docs/MIGRATION_2027.md), [next year's gyro, the Canandgyro](docs/GYRO_CANANDGYRO.md) and
[REV's numbers for our motors, controllers, swerve modules and battery](docs/REV_HARDWARE.md).

To show the tools and the drive team's dashboard to someone away from the robot, run Peashooter in
the simulator and then `py -3.12 -m swervetune.preview.make` from `tools/`. It records the real app
and builds a clickable copy in `tools/swervetune/preview/site/` that runs in any browser, with no
robot needed ([how it works](tools/swervetune/preview/make.py)).

## CI

[`.github/workflows/build.yml`](.github/workflows/build.yml) runs `./gradlew build` on both projects for every pull request into `main`, and again on `main` after a merge. The `CI` check has to be green before a pull request can merge. Mentor notes are in [`.github/README-ci.md`](.github/README-ci.md).

Each project also still carries a GitHub Classroom workflow at `<project>/.github/workflows/classroom.yml`. GitHub only runs workflows from the repo root's `.github/` folder, so those don't run — they're leftovers from the original Classroom assignments.
