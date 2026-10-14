# Examples: past seasons' mechanisms, rebuilt

This project runs only in the simulator. It is one robot carrying a mechanism of each kind the
team has built since 2022. Each one is rebuilt the way this repo's robots are written:

- the YAGSL swerve drive and Sloth Tune, copied from Peashooter;
- the feeder's note sensed by its roller's current and held by a current limit, as in 2024 (`Feeder.tuneWith`), for the Systems tab's Game pieces;
- REVLib 2026 SPARKs running their own loops;
- AdvantageKit logging.

Each mechanism is registered with the tools' **Systems** tab and moves under WPILib's physics
models, so you can practice tuning without a robot.

Peashooter already has a flywheel and an intake pivot, both from 2026. This project adds the other
kinds.

## Running it

```bash
cd Examples
./gradlew simulateJava
```

Then, from the repository folder, run `py -3.12 tools/slothtune gui`. Pick **Examples** and
**Simulator on this laptop**, press **Connect**, and open the **Systems** tab.

In the simulator the test report says what it saw: tracking, overshoot, settling. It never scores
the run, and nothing done here counts for a real robot.

The operator joystick is on Driver Station port 2:

| Button | What it does |
|---|---|
| Y / X / B / A | Elevator to L3 / L2 / L1 / bottom |
| D-pad | Shooter pivot presets: up amp, right subwoofer, left range, down rest |
| Right bumper | Shooter (speaker) |
| Left bumper | Feeder intake |
| Right trigger | Feeder shoot |
| Start / back | Arm to cone high / stowed |
| Left / right stick press | Climber in / out |

## The examples

| Subsystem | From | Kind | In the Systems tab |
|---|---|---|---|
| `Elevator` | 2025 Reefscape, `ElevatorSubsystem` (8874 state code and main) | Elevator, one Vortex | "Elevator", meters |
| `ShooterPivot` | 2024 Crescendo, `Pivot` (8874 state code, 1745 branches) | Pivot, two NEOs, absolute encoder | "Shooter pivot", degrees |
| `TwoJointArm` | 2023 Charged Up, `Arm` (8874 state code, 1745 main) | Two-joint arm, absolute encoders | "Arm shoulder" and "Arm elbow", degrees |
| `Shooter` | 2024 Crescendo, `Shooter` | Two flywheels (left/right spin) and a kicker | "Shooter left" and "Shooter right", wheel RPM |
| `Feeder` | 2024 Crescendo, `Feeder` | Roller with a beam break | "Feeder", RPM |
| `Climber` | 2025 Reefscape, `DeepClimbSubsystem` | Winch, two Vortexes, open loop | Listed, nothing to tune |

Every subsystem's comment says what changed for 2027. In short:

- **Positions are in the mechanism's own units:** meters and degrees. The old code used raw motor
  or encoder rotations.
- **A motion profile moves each goal smoothly.** The old code jumped straight to each setpoint.
- **Gravity is held by feedforward:** kG for the elevator, kCos for the pivot. The old code used
  a constant duty, or nothing.
- **Velocity loops with kV** for the flywheels and the feeder. The old code ran them open loop.
- **The old bugs are fixed** (listed below).
- **Each example has its own CAN ID** (51 to 62), so all of them fit on one robot. Each comment
  gives the original ID.

**The physical numbers are assumed.** None of the past code had gear ratios, drum sizes, masses
or arm lengths. The simulator still needs some, so each subsystem has assumed values, marked as
assumed. `src/main/deploy/swerve/slothtune.json` carries a ReCalc link for each mechanism with
the same numbers. Measure the real mechanism before using any of them on a robot.

## What the simulator taught us (REVLib 2026.0.5)

- **The SPARK's own loops run in the simulator.** That covers the position and velocity PID and
  the feedforward (kS, kV, kG, kCos), but only when the code calls the SPARK simulator's
  `iterate` each loop.
- **MAXMotion didn't run reliably.** It didn't move the pivot at all, and with kP 8 the elevator
  swung from end to end. So these examples profile the goal in code (WPILib's `TrapezoidProfile`)
  and send each step to the SPARK's position loop. On the real robot, MAXMotion can do the same
  job on the SPARK.
- **Set the motor's encoder in the mechanism's units** (degrees, meters) and pass the simulator
  the mechanism's speed in those units. With the encoder left in motor rotations, the simulated
  pivot never left its hard stop.
- **WPILib's arm model is a uniform rod,** its weight halfway out. To simulate a weight at a
  distance, give the model 1.5 times that distance.

## Every mechanism from 2022 to 2026

This catalog comes from the past seasons' repositories, read in October 2026. Positions were raw
motor rotations unless noted, and no code had masses or arm lengths.

| Season | Mechanism | Hardware and control | Rebuilt here? |
|---|---|---|---|
| 2022 Rapid React | Intake roller | SPARK MAX lead and follower, open loop | No: a plain roller |
| 2022 | "Flappy bird" arm | 2 NEOs, 144:1, soft limits 0 / -26.5 rotations, bang-bang | No: the 2024 pivot covers it |
| 2022 | Hangar and traversal climbers | Elevator and pivot, onboard position PID, timed sequences, pneumatic hooks | No: the elevator covers it |
| 2023 Charged Up | Two-joint arm | Shoulder 2 NEOs, elbow 1 NEO, absolute encoders | Yes: `TwoJointArm` |
| 2023 | Intake | NEO 550, open loop, current-limited stall hold | No: a plain roller |
| 2024 Crescendo | Shooter | 3 Vortexes, open loop | Yes: `Shooter` |
| 2024 | Shooter pivot | 2 NEOs, absolute encoder, position PID | Yes: `ShooterPivot` |
| 2024 | Feeder | Vortex and a beam break | Yes: `Feeder` |
| 2024 | Intake, climber | Open-loop roller, two-sided open-loop winch | No |
| 2025 Reefscape | Elevator | Vortex, position PID | Yes: `Elevator` |
| 2025 | Drawbridge, boom stick | Vortex pivots, P only, mostly run by hand | No: the pivot covers them |
| 2025 | Outtake | Vortex roller, two beam breaks | No: the feeder covers it |
| 2025 | Deep climb | 2 Vortexes, open loop | Yes: `Climber` |
| 2026 Rebuilt | Shooter, intake pivot and rollers, feeder | Peashooter's mechanisms | In Peashooter |

No season had a turret, a hood, a telescope or a wrist.

## Bugs in the old code, worth knowing

- **Integer division zeroed a conversion factor** (2023 offseason): `(4096/8192) * 2 * Math.PI`
  is 0 in Java.
- **A factory reset after setting a conversion factor wiped it** (2023). The setpoints were raw
  encoder rotations, though the comments said radians.
- **Presets declared in radians were sent as rotations** (2024 pivot).
- **Soft limits configured for the absolute encoder** most likely acted on the motor's own encoder
  (2024 pivot).
- **Setpoint commands didn't require their subsystem** (2025 elevator), so the hold command fought
  them.
- **A `switch` missing a `break`** made two shooter states run at idle speed (2024 shooter).
- **A "has a note" flag latched true and was never cleared** (2024 feeder), so autos waiting for a
  note finished at once.
- **Blocking `while` loops inside commands** (2024 climber leveling, a 2025 beam-break branch)
  would stall the scheduler.
- **An exact `==` compare on a double** (2023 main) never matched.
