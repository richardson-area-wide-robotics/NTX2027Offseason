# NTX 2027 Offseason

Offseason robot code for FRC Team 1745 (Richardson Area Wide Robotics). This repo holds two WPILib Java projects. Each one is a YAGSL swerve drive that runs in simulation.

| Project | Description |
| --- | --- |
| [`Black team/`](Black%20team/) | Swerve drive project for the Black team.|
| [`Peashooter/`](Peashooter/) | Swerve drive project for Peashooter. |

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

## Vendor libraries

- [YAGSL](https://github.com/BroncBotz3481/YAGSL) for the swerve drive
- [REVLib](https://docs.revrobotics.com/revlib) for SPARK MAX
- [AdvantageKit](https://docs.advantagekit.org/) for logging
- [PathPlannerLib](https://pathplanner.dev/) for autonomous paths
- ReduxLib, ThriftyLib, WPILib New Commands
- Phoenix 6 (Black team only)
