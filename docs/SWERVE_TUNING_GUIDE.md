# The swerve tools

A browser app on the laptop that tunes and checks our YAGSL swerve drives (Peashooter and Black
team), keeps the motors from cooking themselves, and helps find wiring faults. It teaches as it
goes: hover any underlined word, or press **Lessons**, for the control theory behind it.

Everything works without a robot too: each tool has a **Practice** button with made-up data, so
you can learn it at home.

## Setting up (once per laptop)

1. Install WPILib 2026 (it brings the JDK and VS Code), and Python 3.12 from python.org.
2. In a terminal, install the one Python package the tools need:

   ```
   py -3.12 -m pip install pyntcore
   ```

3. Clone the repository, or pull the latest.

## Starting it

From the repository folder:

```
py -3.12 tools/swervetune gui
```

Your browser opens at `http://127.0.0.1:5806/`. Pick the **robot code** (Peashooter or Black
team), then who to talk to: the robot (by team number) or the **simulator on this laptop**, and
press **Connect**. The chips across the top show the robot, battery voltage, where the robot
thinks it is, AprilTags and the deadman.

To use the simulator, start it first from VS Code (WPILib: Simulate Robot Code) or with
`./gradlew simulateJava` in the robot's folder.

## Staying safe

- **The deadman.** Nothing that spins a wheel runs unless someone holds SPACE in the app (or the
  tester's controller bumper) for the whole test. Let go and it stops.
- **Tell it where the robot is.** "On blocks" means every wheel is off the ground. "On the
  floor" needs the clear distance ahead and to each side, measured. If the robot is turning while
  it's supposed to be on blocks, it stops: it knows it's on the floor.
- **Stopping.** The red ABORT button or Esc stops everything. The Driver Station's disable is the
  real emergency stop and always works. Touching a joystick also hands the robot straight back.
- It will not run on a match field (FMS attached) or in autonomous, and it stops if the laptop
  disconnects, the battery sags, the robot hits something, or a motor gets too hot.

## The tabs

| Tab | What it's for |
|---|---|
| **Guide** | The path to a tight swerve, step by step. Start here. |
| **Live** | Every module's angle and speed, what was asked against what happened. |
| **Motors** | Each motor's heat, current and health. Warns before a motor overheats, and stops one that's stalled or failing. |
| **Wiring** | The CAN chain and power feeds as a map, live. Finds loose plugs and bad power leads, finds which PDH port feeds each motor, and walks you through a wiggle test. |
| **Tune** | The test-and-adjust loop for each controller, with annotated graphs: what the controller saw, what it did, and what a change would do. |
| **Calibrate** | Measuring the robot itself: module positions, wheel sizes, where the cameras sit, and where the field's AprilTags really are. |
| **Troubleshoot** | Describe what the robot is doing wrong; it asks questions and points at the cause. |
| **Config** | Checks the swerve config files for mistakes, with one-click fixes. |
| **Runs** | Every saved test, and **Match logs**: what went wrong in a match and where to look. |

## The path (the Guide tab)

1. Connect and check the configuration.
2. Sensor health (robot disabled).
3. Hand check: turn each wheel and module by hand; the app checks every sensor counts the right way.
4. Set the absolute encoder offsets (wheels straight, bevel gears to one side).
5. On blocks: every wheel drives the right way.
6. Measure the robot: module positions with a tape measure, wheel sizes with a push.
7. Steering on blocks, then on the floor.
8. Find where the wheels slip, so the drive current limit sits just under it.
9. Measure the feedforward, then tune drive speed.
10. Spin and straight-line checks.
11. Advanced: motion profiles. This step stays locked until steering and drive pass on the floor.
12. Save, redeploy, and commit.

Each step says why it matters, what you need, and what to do. Steps tick themselves off when a
test passes.

## Saving what you find

Gains changed live are lost when the robot code restarts. **Save to the robot files** shows
exactly which lines change (a diff) before it writes anything. Then:

1. Redeploy, reconnect, and check the startup list on the Live tab shows your new values.
2. Commit on your own branch and open a pull request (see `CONTRIBUTING.md`).

## After a match

AdvantageKit logs every match: to the USB stick in the roboRIO, or on a roboRIO 2 without a stick,
to its SD card (`/home/lvuser/logs`). A roboRIO 1 without a stick keeps no logs, so keep a FAT32
stick in it. Download them with AdvantageScope, then open **Runs, Match logs** and point it at
the folder. It lists brownouts, CAN dropouts, controllers that rebooted, breakers that tripped and
motors that overheated, each with the time in the match, and the place on the wiring map to check.

AdvantageScope layouts for both robots are in `tools/swervetune/advantagescope/`.

## On the robot

The robot code already has everything the tools need:

- `AkLogging.start(...)` first in `Robot`'s constructor (AdvantageKit logging).
- Each subsystem registers its motors with the motor guard, which enforces the current policy:
  NEO Vortex 80 A, NEO 2.0 80 A, NEO V1.1 60 A, NEO 550 20 A.
- The driver controller's **Back** button holds thermal shutoffs off for 20 seconds, for when
  losing a motor costs more than the motor. It never lifts a stall cutout.

## Going deeper: every SPARK's CAN traffic (optional)

The Wiring tab works from what the robot code reads. For a fault it can't pin down, URCL (from
Team 6328) logs every status frame each SPARK sends, into the same AdvantageKit log. It isn't
installed; to add it:

1. Vendor libraries, install online:
   `https://raw.githubusercontent.com/Mechanical-Advantage/URCL/main/URCL.json`
2. In `AkLogging.start`, just before `Logger.start()`:

   ```java
   Logger.registerURCL(URCL.startExternal(Map.of(5, "frontleft drive", 6, "frontleft steer")));
   ```

   The map names devices by CAN ID (the Wiring tab's map lists them); unnamed ones keep a default.

It runs in its own thread (under 0.1 ms a loop). A SPARK only sends the frames something has
asked for, so it logs what the robot code reads. Its data doesn't replay in AdvantageKit's replay
mode.

## For AI agents

`py -3.12 tools/swervetune --help` lists the command line, and `py -3.12 tools/swervetune brief`
prints the rules an agent follows (`docs/AGENT_TUNING.md`).

## When the tools themselves misbehave

- **"pyntcore is not installed"**: run the pip command above with `py -3.12`.
- **Can't connect**: is the laptop on the robot's network (or is the simulator running)? Is the
  team number right? The robot code must be this branch's: the tools check they match.
- **A Python change doesn't show up**: stop the app (Ctrl+C) and start it again. Browser-only
  changes just need a page reload.
