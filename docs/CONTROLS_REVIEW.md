# Controls review: Peashooter and Black team swerve

A review of both robots' swerve control as configured on the `StuartTesting` branch (October
2026), before any of it has been measured on carpet. Both are MAXSwerve-style: NEO drive at
5.50:1 on 3 in wheels (about 4.1 m/s free), NEO 550 steering at 46.42:1, navX on SPI, YAGSL
2026.4.1. Findings are ordered by how much they cost on the field. Each says what the swerve
tools do about it; most are measured, not guessed, by a step in the Guide tab.

## Summary

The structure is sound: closed-loop velocity on every module, field-relative teleop, cosine
compensation on, discretization on in teleop. What is missing is **measurement**. Every gain is a
template value, no feedforward has been measured, and Peashooter's PathPlanner model describes a
different robot. The order of work is the Guide tab's: offsets and directions, robot geometry,
steering, slip current, feedforward, drive gains, then autos.

## Findings

### 1. Peashooter's autos plan for a different robot (fix before any auto runs)

PathPlanner's robot config says Kraken X60 at 5.143:1 on a 48 mm wheel radius, modules 0.273 m
from center, 5.45 m/s, 74 kg and 6.883 kg·m² (the app's defaults). YAGSL says NEO at 5.50:1, 38.1
mm, 0.3048 m, 4.12 m/s. PathPlanner will plan accelerations and turns this robot can't make; the
robot falls behind every path and the holonomic controller (kP 5) chases the error.

**Do:** the Config tab lists each mismatch; fix them in PathPlanner's Settings, Robot Config. Weigh
the robot (with bumpers and battery) and put `robotMassKg` in `swervetune.json`; until MOI is
measured, the tool's estimate (6.62 kg·m², a 0.85 m slab) beats the default.

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

YAGSL's default drive feedforward is kV = 12 V / 4.1 m/s, about 2.9 V per m/s, with no kS. On
carpet, kS (the voltage to start the wheel moving) is typically 0.1 to 0.25 V; without it, slow
moves undershoot. Feedback has to make up the rest, but:

- **Peashooter: drive kP 1, kD 0.4.** kP 1 is four times the feedforward's own slope. The NEO's
  velocity measurement is coarse and lagged, so this buzzes and overshoots, and kD on a velocity
  loop mostly amplifies the measurement steps. Expect hot, noisy drive motors.
- **Black team: drive kP 0.002.** At 1 m/s of error it adds 0.2% output: the drive is effectively
  open loop on an unmeasured feedforward.

**Do:** Guide step 9: measure the feedforward per module (`drive_ff`, on the floor), then tune
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
1.19, a wheel breaks loose at about 47 A. Above that, hard acceleration spins wheels (odometry
counts distance the robot never covered) and four motors at 80 A ask 320 A of a 120 A main
breaker. Policy caps NEO 2.0 drive at 80 A; the right number for this carpet is lower.

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

### 8. Top speed has no headroom on Black team

Black team sets the maximum speed to 4.1 m/s, the free speed. At full stick the velocity loop has
nothing left to correct with, and as the battery sags it can't reach the setpoint at all.
Peashooter uses 3.9 m/s (95%).

**Do:** 3.9 m/s on Black team too, until the straight-line test shows the real top speed.

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

Both use a linear deadband (0.10 and 0.08) and full-scale linear output. Squaring the stick (keeping
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
