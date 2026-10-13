# Controls review: Peashooter and Black team swerve

A review of both robots' swerve control as configured on the `StuartTesting` branch (October
2026), before any of it has been measured on carpet. Both are MAXSwerve-style: NEO Vortex drive on
SPARK Flex at 5.50:1 on 3 in wheels (about 4.9 m/s free), NEO 550 steering at 46.42:1, navX on SPI,
YAGSL
2026.4.1. Findings are ordered by how much they cost on the field. Each says what the swerve
tools do about it; most are measured, not guessed, by a step in the Guide tab.

## Summary

The structure is sound: closed-loop velocity on every module, field-relative teleop, cosine
compensation on, discretization on in teleop. What is missing is **measurement**. Every gain is a
template value, no feedforward has been measured, and Peashooter's PathPlanner model describes a
different robot. The order of work is the Guide tab's: offsets and directions, robot geometry,
steering, slip current, feedforward, drive gains, then autos.

## Findings

### 1. Peashooter's autos: the robot model now matches, except mass and MOI

PathPlanner's robot config described another robot (Kraken X60 at 5.143:1, a 48 mm wheel radius).
On this branch it now matches the code (decision 15): NEO Vortex at 5.50:1, 38.1 mm wheel radius,
modules 0.3048 m from center, 3.9 m/s, 40 A. Mass and moment of inertia are still the app's
defaults (74 kg, 6.883 kg·m²), so PathPlanner plans accelerations and turns from a guess. "Kishores
Auto" also runs "Shoot B", which the code never registers, so PathPlanner skips it without a word
(kept by name, decision 16).

**Do:** weigh the robot with bumpers and battery and put `robotMassKg` in `swervetune.json`; run
spin_ff for the moment of inertia; then the PathPlanner check offers both edits.

### 2. Peashooter's sticks may be reversed (check on blocks)

Peashooter passes the raw stick values into `swerveDrive.drive()`: left Y to x, left X to y,
right X to rotation. An Xbox stick reads negative pushed forward and left, and WPILib wants +x
forward, +y left and counter-clockwise positive. Black team negates all three, with a comment
saying why; Peashooter negates none. If Peashooter drives correctly today, something else is
compensating (a gyro zeroed facing the other way would fix translation but not rotation).

**Do:** on blocks, field-relative, robot facing away from the driver: stick forward must turn
every wheel to point away and roll forward; stick right must point them right; right stick right
must turn the robot clockwise. Then negate whatever is wrong, in `Robot.java`'s bindings, with a
comment. The Troubleshoot tab's "The robot goes the wrong way" walks through it.

### 3. No feedforward is measured, and the drive gains are at the extremes

YAGSL's default drive feedforward is kV = 12 V over the module's free speed for the configured
motor and gearing: 2.44 V per m/s for these Vortexes at 5.50:1 on 3 in wheels (checked in YAGSL
2026.4.1's bytecode; `createSwerveDrive(MAX_SPEED)` does not change it). That is the right slope
for a free wheel. It has no kS and no kA: on carpet the wheel needs 0.1 to 0.25 V just to start
moving, and extra volts to accelerate a 55 kg robot, so slow moves undershoot and starts lag.
Feedback has to make up the difference, but:

- **Peashooter: drive kP 1, kD 0.4.** kP 1 is several times the feedforward's own slope. The
  measured velocity is filtered and lags, so a gain this big buzzes and overshoots, and kD on a
  velocity loop mostly amplifies measurement noise. Expect hot, noisy drive motors.
- **Black team: drive kP 0.002.** At 1 m/s of error it adds 0.2% output: the drive is effectively
  open loop on an unmeasured feedforward.

**Do:** the Guide's feedforward step: measure it per module (`drive_ff`, on the floor), then tune
drive kP up from about 0.04 with `drive_step`. Drop kD to 0.

### 4. Steering is soft and slew-limited

- **kP 0.01** (duty cycle per degree): 1 degree of error asks for 0.12 V, less than a NEO 550 on
  carpet needs to move. Small corrections stop short, and each degree is about 1.7 cm of sideways
  drift per meter driven.
- **Ramp rate 0.25 s on both loops.** YAGSL applies it to closed-loop output too, so every
  steering correction is slew-limited: pure lag in a position loop. The 20 A current limit already
  protects the motor. The drive ramp slows the velocity loop the same way, and PathPlanner sees it
  as lag.

**Do:** Guide step 7: `steer_step` on blocks, then on the floor, starting with the ramp at 0. Drive
ramp 0.05 s or less.

### 5. The drive current limit isn't set from grip

Black team runs 80 A per drive motor, Peashooter 40 A. At an assumed 55 kg and a carpet grip of
1.19, a Vortex at this gearing breaks its wheel loose at about 69 A (it makes less torque per amp
than a NEO). Above that, hard acceleration spins wheels (odometry counts distance the robot never
covered) and four motors at 80 A ask 320 A of a 120 A main breaker. Peashooter's 40 A grips but
gives away acceleration. Policy caps the Vortex at 80 A; the right number for this carpet is a
little under where it slips.

**Do:** Guide step 8: the slip test pushes against a wall, finds where each wheel lets go, and
recommends a limit just under it.

### 6. Steering trusts one encoder read at boot

Both robots steer on the NEO 550's own encoder, copied once from the absolute encoder at startup.
A bad read, or a skipped gear tooth, leaves a module pointed wrong until the next reboot.

**Do:** turn on `encoderAutoSync` in `swervetune.json` (re-copies when the two disagree by more than
a degree, while still), or steer on the absolute encoder. Test either on blocks.

### 7. Offsets look copied

Black team: two modules share an identical offset, and frontright's drive inversion differs from
the others (the classic sign of an offset 180 degrees out, "fixed" by inverting the motor: it
drives, but its angle reads backwards). Peashooter: three offsets are exact multiples of 90.

**Do:** Guide steps 3 and 4: the hand check, then capture offsets with every bevel gear facing the
same way.

### 8. Top speed is set well under what the Vortexes can do

The Vortexes' free speed at this gearing is about 4.9 m/s. The code tells YAGSL 3.9 m/s
(Peashooter, 79%) and 4.1 m/s (Black team, 83%): safe headroom for the velocity loop and a sagging
battery, but full stick is slower than the robot can go, and PathPlanner plans with the same number.

**Do:** once the straight-line test has measured the real top speed on carpet, set `MAX_SPEED` to
about 90% of it on both robots; the PathPlanner check then asks to update PathPlanner too.

What full stick needs from the battery: YAGSL turns on the SPARKs' voltage compensation at 12 V
(`optimalVoltage`), so a command means the same volts on any battery until the battery can't
supply them. At these speeds the Vortexes need about kS + kV x MAX_SPEED: roughly 9.7 V on
Peashooter and 10.2 V on Black team (estimates until drive_ff measures kV). The ES17-12 is 12 V
nominal, about 12.7 to 13 V charged and at rest, and sags by its resistance times the current
(datasheet: about 12 mOhm for the battery alone). A drive_ff on the floor reports both numbers for
the battery that was in, and the current at which full stick starts to slow.

### 9. Turning while driving drifts sideways

When the robot translates and rotates at once, the module states computed at the start of a loop
are wrong by the end of it, so the path curves. YAGSL corrects this in teleop (discretization,
dt 0.02 s) but not in autonomous, and angular velocity compensation, which covers the measurement
lag, is off with a coefficient of 0.

**Do:** turn discretization on for autonomous too (`chassisDiscretization` in `swervetune.json`);
measure the angular velocity coefficient with a drive-and-spin before enabling it.

### 10. Heading drifts with no rotation command

With the rotation stick centered, carpet scrub slowly turns the robot. YAGSL's heading correction
(off on both) holds the heading with the heading PID already in `controllerproperties.json`.

**Do:** try `setHeadingCorrection(true)` in teleop once steering and drive are tuned; check it
lets go the moment the driver rotates.

### 11. Teleop input shaping

Both use a linear deadband (0.10 and 0.08), round on the driving stick (its distance from center,
so a gentle diagonal keeps both axes), and full-scale linear output. Squaring the stick (keeping
its sign) gives finer control at low speed with the same top speed, and a translation slew-rate
limit stops the driver from asking for more acceleration than the wheels can grip. Rotation is 3
rad/s on Peashooter and 6.3 rad/s on Black team; the modules allow about 9.5 rad/s, and YAGSL
scales wheel speeds down when translation plus rotation exceeds what a module can do.

### 12. Telemetry at HIGH

Both set YAGSL's telemetry verbosity to HIGH, which publishes every module's raw data to
NetworkTables every loop. AdvantageKit now logs the swerve states the tools and AdvantageScope
need. In matches, use a lower level and watch loop time: the post-match summary reports loop
overruns.

### 13. 2027: the navX is on SPI

SystemCore has no SPI port. The planned Redux Canandgyro (CAN) solves it. See `MIGRATION_2027.md`.

## What was checked

The YAGSL JSON files, both `Drive.java` and `Robot.java` files, the PathPlanner settings, and
YAGSL 2026.4.1's defaults read from its jar (cosine compensation on, discretization on in teleop
only, angular velocity compensation off). Nothing here was measured on a robot yet: the numbers
above that matter (feedforward, gains, slip current, top speed) are exactly what the Guide's steps
measure.
