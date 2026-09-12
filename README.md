# NTX 2027 Offseason

Offseason robot code for FRC Team 7525 (Richardson Area Wide Robotics). This repo holds two WPILib Java projects. Each one is a YAGSL swerve drive that runs in simulation.

| Project | Description |
| --- | --- |
| [`Black team/`](Black%20team/) | Swerve drive project for the Black team. Also includes the CTRE Phoenix 6 vendordep. |
| [`Peashooter/`](Peashooter/) | Swerve drive project for Peashooter. |

Right now the robot code in both projects is the same. The assignment for each one is in its own readme ([Black team](Black%20team/readme.md), [Peashooter](Peashooter/README.md)).

## Requirements

- [WPILib 2026](https://docs.wpilib.org/en/stable/docs/zero-to-robot/step-2/wpilib-setup.html). It installs VS Code, JDK 17, and the simulator.
- An Xbox-style controller for driving in sim. The keyboard works too.

## Building and running

Every project builds on its own with Gradle. Open a project folder (for example `Peashooter/`) in WPILib VS Code, or `cd` into it before running commands. Don't run them from the repo root.

```bash
./gradlew build          # compile and run tests
./gradlew simulateJava   # launch the robot in the simulator GUI
./gradlew deploy         # deploy to the roboRIO (team 7525)
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

## CI

Each project has a GitHub Classroom workflow (`.github/workflows/classroom.yml`) that runs `gradle build`. GitHub only runs workflows from the repo root's `.github/` folder, so these don't run in this repo. They're left over from the original Classroom assignments.
