# The swerve tools

A browser app on the laptop that tunes and checks our YAGSL swerve drives (Peashooter and Black
team), keeps the motors from cooking themselves, and helps find wiring faults. It teaches as it
goes: hover any underlined word, or press **Lessons**, for the control theory behind it.

Much works without a robot too: most tuners and tools have a **Practice** button with made-up data, so
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

## The robot and Claude at the same time (two networks)

In the shop the laptop is on two networks at once: its own Wi-Fi on the school network, with the
VPN on it so Claude works, and a USB Wi-Fi adapter on the robot's radio. Only robot traffic
(`10.17.45.x` for Peashooter, `10.99.90.x` for Black team) may use the USB adapter; everything else,
the VPN included, must use the school Wi-Fi.

1. Leave the laptop's own Wi-Fi on the school network, and connect the VPN as usual.
2. Plug in the USB Wi-Fi adapter. In the Wi-Fi menu, pick that adapter from the list at the top
   (it shows as "Wi-Fi 2" or similar) and join the robot's network with it. Not the other way
   round: the school Wi-Fi stays on the laptop's own adapter.
3. In the app, press **Check the networks** (under Connect, or after a failed Connect), or run
   `py -3.12 tools/swervetune netcheck`. It says which network carries the robot, which carries
   Claude, and what to change.
4. **Once per laptop**, as Administrator, run the fix it gives you:

   ```
   powershell -ExecutionPolicy Bypass -File tools
obot_preflight.ps1 -Team 1745 -Fix
   ```

   The robot's radio hands out an internet gateway like any router. If Windows prefers the USB
   adapter, the internet goes there, the VPN follows it to a radio with no internet, and Claude
   drops. The fix sets the USB adapter's metric to 500 so it only ever carries robot traffic. It
   stays set for that adapter; nothing else changes.

If the check says the VPN blocks traffic outside the tunnel, robot packets die even with every
route right: turn off the VPN's kill switch (WireGuard: Edit the tunnel, untick **Block untunneled
traffic (kill-switch)**; other VPNs: allow local network access, or split tunneling). If Windows
drops the robot's Wi-Fi as soon as the school Wi-Fi connects, it is "minimizing simultaneous
connections": a mentor can turn that off in Group Policy (Network, Windows Connection Manager,
**Minimize the number of simultaneous connections to the Internet or a Windows Domain**: Disabled).

At events the robot radio joins the field, so in the pit connect with an Ethernet cable through a
USB Ethernet adapter instead; the same check and the same fix apply to it.

## Staying safe

- **The deadman.** On blocks and on the floor, nothing that moves a motor runs unless someone
  holds the deadman for the whole test: the tester's joystick right bumper (Driver Station port
  1), or **Hold to run** in the app's test banner, pressed with the mouse or a finger. Let go and it
  stops. No key does it: on the Driver Station laptop, SPACE is the E-STOP. Whoever holds it
  stands where they can see the wheels.
- **Tell it where the robot is.** "On blocks" means every wheel is off the ground. "On the
  floor" needs the clear distance ahead and to each side, measured. Before a blocks test that drives
  the wheels, they get a short kick (a quarter second): a wheel in the air spins up fast for little
  current, one carrying the robot doesn't, and then the test stops before it starts. If the robot
  turns while it's supposed to be on blocks, it stops too.
- **Stopping.** The red ABORT button or Esc stops everything. The Driver Station's disable is the
  real emergency stop and always works. Touching a joystick also hands the robot straight back.
- It will not run on a match field (FMS attached) or in autonomous, and it stops if the laptop
  disconnects, the battery sags, the robot hits something, or a motor gets too hot.

## The tabs

| Tab | What it's for |
|---|---|
| **Bring-up** | A newly built robot against its design file: the code, the robot off, the first power-on, each motor and shared shaft, then a signed report. Start here with a new robot. |
| **Guide** | The path to a tight swerve, step by step. Start here once the robot is brought up. |
| **Live** | Every module's angle and speed, what was asked against what happened. |
| **Motors** | Each motor's heat, current and health. Warns before a motor overheats, and stops one that's stalled or failing. |
| **Wiring** | The CAN chain and power feeds as a map, live. Finds loose plugs and bad power leads, finds which PDH port feeds each motor, and walks you through a wiggle test. Every device, the PDH's ports and each finding are shown on FIRST's own control-system drawing (WPILib's REV layout, CC BY 4.0), with the part in question outlined and the parts our robots don't use, such as pneumatics, faded. Troubleshoot's power and CAN checks use the same drawing. Each CAN bus is drawn in its cable color with its name (Drive train, Intake); the termination check takes two meter readings per bus to tell a missing terminator from one that isn't working or a broken cable; and each controller's faults, now and since the code started, are in Where to look. |
| **Tune drive train** | The test-and-adjust loop for each controller, with annotated graphs: what the controller saw, what it did, and what a change would do. **Each pod** first: one pod's steer motor, then its drive motor, each with that pod's own gains (saved to swervetune.json's `podGains` only where they differ from pidfproperties.json); **Use on every pod** when they all want the same. Then **Whole drive train**: all pods together on the shared gains, feedforward, slip current, spin and straight line. Faults on the motors being tuned show above it. |
| **Calibrate** | Measuring the robot itself: module positions, wheel sizes, the gyro, mass and moment of inertia, each camera's lens (PhotonVision, with the team's 9 x 11 in 8 x 8 ChArUco board, drawn), where the cameras sit, and where the field's AprilTags really are. Faults on the motors and gyro a measurement depends on show with it. |
| **Joysticks** | Checks the drive team's joysticks, no robot needed: stick drift against the code's deadband, reach, triggers, and buttons that bounce. |
| **Troubleshoot** | Describe what the robot is doing wrong; it asks questions and points at the cause. **Robot messages** lists every error and warning the robot has reported since you connected (its console on a real robot, its alerts on any), each once with how often and how recently, so what keeps coming back stands out. |
| **Config** | Checks the swerve config files for mistakes, with one-click fixes. |
| **Runs** | Every saved test, and **Match logs**: what went wrong in a match and where to look. |

## Bringing up a new robot (the Bring-up tab)

When the mechanical and electrical teams hand over a newly built robot, start in **Bring-up**,
before the Guide. It checks the robot against its **design file**
(`src/main/deploy/design/devices.json`): every motor in YAGSL's style (`"type"`, `"id"`,
`"canbus"`), with its PDH port and breaker, inversion, brake or coast, current limit, gear ratio,
which way is positive, and which motors share a shaft; every sensor on its port; each CAN bus by
its cable color (CTRE's cable: a color with green, green is CAN-L), so a SystemCore robot's buses
are told apart.

1. **The design file.** *Draft from the code*, or *Import a spreadsheet (CSV)* from the design
   team, then go through it with the mechanical and electrical leads and fill in what the code
   can't know (breakers, gear ratios, which way is positive). The command line does the same:
   `py -3.12 tools/swervetune design --project Peashooter`.
2. **The code against the design.** CAN IDs, a SPARK MAX created for a SPARK Flex, a follower set
   the wrong way, a port: fix whichever one is wrong.
3. **Robot off:** breakers, terminators (about 60 ohm across CAN-H and CAN-L), battery, radio.
4. **First power-on:** every controller heard (Motors), the CAN cable in order (Wiring), then
   every sensor: **Start the live readout** shows each sensor's value as the robot reads it, and
   ticks each one the moment it changes, while someone trips them by hand (block the beam, press
   the switch, turn the encoder). The robot reads the sensors the code registers
   (`tune.watchSensor("Intake beam", beam::get)`) and opens the design file's others from their
   ports for the readout only; a port the code already uses needs registering to be seen.
5. **Each mechanism motor alone**, on blocks with the deadman held: it runs at 8% for 0.6 s with
   the robot's own code paused, and you say which way it went. Its encoder always agrees with
   the code, so only a person can tell if that is the right way.
6. **Motors that share a shaft:** first one alone with the others held at zero, so the shaft
   turns them; each must turn the way its own setting expects. Then all together: if two push
   against each other the robot stops it at once.
7. **The drivetrain:** the Guide's path, below.
8. **Sign off:** each lead types their name; the report is written, dated, into the robot's
   `bringup` folder. Commit it with the code.

## The path (the Guide tab)

The same 16 steps, with the same numbers, as the Guide tab:

1. Connect and check the configuration.
2. Sensor health (robot disabled).
3. Hand check: every module straight with its bevel gear to the robot's left, then turn each wheel
   and module by hand, then the whole robot counter-clockwise; the app checks every sensor, the gyro
   included, counts the right way.
4. Set the wheel offsets (wheels straight, bevel gears to the left, a straight-edge squared to the
   frame).
5. On blocks: every wheel drives the right way. The first step with the robot enabled.
6. Steering, on blocks.
7. Measure the robot: module positions with a tape measure, wheel sizes with a push (Calibrate).
8. Steering, on the floor.
9. Find where the wheels slip, so the drive current limit sits just under it.
10. Measure the feedforward.
11. Drive speed.
12. Spin check.
13. Straight line (graded on a tape, or AprilTags at both ends).
14. Drive it with the sticks: forward, sideways and turning each go the right way.
15. Advanced: motion profiles. Optional, and locked until steering and drive pass on the floor.
16. Save and commit.

Each step says where the robot must be (and checks it), why it matters, what you need, and what
to do. A step ticks itself off when a test on the real robot passes; simulator and practice runs
never tick a step.

## Where to start, and what to do next, in each tool

Calibrate, Config, Motors, Wiring and Controllers each open with a card: what the tool is for,
what to bring, and its jobs in order, each marked **done**, **needs a fix**, **to do**,
**later** (with a button to what it waits for), **optional** or **not needed**. The highlighted
job is the one to do next; **Start here** or **Next** goes to it. The marks come from evidence:
the robot's files, the runs saved on this laptop, what each tool measured, and the live robot.
When a panel's job checks out, the panel says so and offers the next one; when a tool is done, its
card points to the next tool or back to the Guide.

Every panel's instructions sit in a **How to do it** block. The **How-to instructions** switch on
any card shows or folds all of them; leave it on while learning. The `setup` command gives an AI
agent the same cards (`swervetune setup --project Peashooter`).

## Redo one part

Already set up, and one thing changed? The Guide's **Already set up? Redo one part** checks only
that part, and leaves the rest of the robot's settings and results alone:

| Part | Its checklist |
|---|---|
| A swerve module (replaced, rebuilt, acting up) | Both controllers heard, sensor health, hand check of that module, its offset only, its direction on blocks, steering on blocks on that module, feedforward against the other three |
| A motor or controller | Heard with its CAN ID, its type, its PDH port; then its module, if it's a swerve motor |
| The gyro | Health, turned by hand (counter-clockwise reads positive), a minute standing still, full turns, a spin check |
| A camera (moved, bumped, replaced) | Listed for the robot, its position measured again |
| A new field or event | Welded or AndyMark, the tag survey, the survey uploaded to each camera |
| Wheels or tread | Wheel sizes, then a straight line on a tape |

Starting a part stamps the time: only what is done from then on counts for it, because the part
changed. Its steps run on that part alone (the tuner opens on that module; its offset is the only
one written).

## Tuning from AdvantageScope

The same live gains are in AdvantageScope too. Connect it with the **NetworkTables 4
(AdvantageKit)** live source, turn on tuning mode (the slider icon), and open the **Tuning,
SwerveTune** table: type a new value and press Enter. The robot checks it against the same limits
as the app, and puts the field back to what is really running if it refuses (`Status`, in the same
table, says why). Edits wait while a test is running and are refused with the FMS attached. The
app and AdvantageScope always show the same values, and every change goes into the match log.
`"advantageScopeTuning": true` in `swervetune.json` turns this on; both robots have it on.

## Keeping PathPlanner in step

PathPlanner keeps its own copy of the robot (`deploy/pathplanner/settings.json`) and plans every
auto from it. The Config tab's **PathPlanner against the code** panel compares every setting with
where the truth lives (the YAGSL files, `MAX_SPEED` in `Drive.java`, and the mass and moment of
inertia measured in the Calibrate tab), checks each path's speed and acceleration limits against
what the robot can do, and checks every named command an auto uses is registered in the code.
**Make PathPlanner match the code** writes the settings with a diff preview; close the PathPlanner
app first, or it writes its old values back. The same check runs as `py -3.12 tools/swervetune
ppcheck`, and on every pull request as the suggested "PathPlanner matches the code" check.

## Mechanism designs from ReCalc and AMBcalc

If a mechanism was designed in [ReCalc](https://www.reca.lc/) or [AMBcalc](https://ambcalc.com/),
paste its share link into the Config tab's **Mechanism designs** panel. The link holds the whole
design (motor, count, gearing, arm or spool or wheel, load, current limit), so nothing is fetched.
The tool names the mechanism from the calculator (a flywheel is "Shooter" until you rename it),
attaches the motors whose names start with that name, and checks the design against the robot:

- the motor really fitted and how many, and the team's current policy for it;
- velocity setpoints in that subsystem's code that the motor can never reach (Peashooter's
  `shootX()` asks its Vortexes for 9999 rpm; their free speed is 6784);
- for an arm, whether the motors can hold the load out level at the design's current limit;
- for a drivetrain link, the YAGSL gearing, wheel and mass, and PathPlanner's wheel grip;
- with **Check against the newest match log**, what the robot measured: each motor's speed per volt
  (which tells a NEO from a Vortex whatever the files say) and how long it sat at its current limit.

It fills in only what a design should decide: a drivetrain's gearing when it is one REV sells, the
robot's mass until it is weighed, and the motor type of a mechanism motor nobody has named yet.
Never the drive current limit: the slip test measures that. Saved designs keep only the link, in
`swervetune.json` under `"designs"`.

## Saving what you find

Gains changed live (in the app or in AdvantageScope) are lost when the robot code restarts. **Save to the robot files** shows
exactly which lines change (a diff) before it writes anything. Then:

1. Redeploy, reconnect, and check the startup list on the Live tab shows your new values.
2. Commit on your own branch and open a pull request (see `CONTRIBUTING.md`).

## Batteries

The team's batteries are MK ES17-12s: "12 V" on the label, about 12.7 to 13 V charged and at rest,
and less under load. How far a battery's voltage drops per amp (its **sag**, in milliohms) is what
tells a good one from a tired one. A tired battery makes the robot slow at full stick, and if it
drops below about 6.8 V the roboRIO browns out and cuts the motors.

**Number every battery** (a big number in paint marker on the case). Then, after every swap:

1. Turn the robot on and connect. The dashboard shows a yellow alert, *Which battery is in?*,
   and this app opens the battery picker by itself.
2. Tap the number on the battery: the **Battery** drop-down on the Driver Station dashboard, or the
   big buttons here (the **Battery** chip in the top bar opens them any time).
3. Each button shows how that battery did last time: **good**, **practice** (fine for practice,
   keep it out of matches if better ones are charged) or **retire**.

**On the Driver Station laptop**, load the drive team's Elastic layout (Elastic: File >
Open Layout, `tools/swervetune/elastic/drive-team-layout.json`), and again whenever that file changes. One tab with the Battery drop-down,
a **Battery check** line ("Battery 7: 12.84 V at rest, charged") and the robot's health alerts. See
[At the cart](#at-the-cart-the-drive-teams-checklist) below.

Picking takes two seconds and is the whole job. Every wheel test and every match log you open
then measures that battery, and **How each battery is doing** in the picker shows each one over
the season. A loose Anderson connector or main-breaker bolt looks exactly like a tired battery, so
check those before retiring one. The list of numbers lives in `swervetune.json` (`"batteries"`);
**Edit the battery list** changes it.

## At the cart: the drive team's checklist

Everything the drive team does at the cart is on the one Elastic tab, and none of it needs this
laptop. The battery grades on it come from the laptop: after the batteries have been measured,
open the Battery tab, press **Send the grades to the robot**, and redeploy. Do it before an event.

1. **Pick the battery** after every swap, then read the **Battery check** line. *Charged* is ready;
   *partly charged* is fine for practice; *CHARGE IT before a match* means swap it. *Practice only*
   or *RETIRE it* after that is the battery's grade from its measured sag; *next: 3* is the battery
   to put in next (graded best, then the one picked longest ago). "Resting
   voltage read once the robot is disabled" means it was picked while enabled: it fills in by itself
   a couple of seconds after the robot is disabled.
2. **Read Robot Health.** The colors mean one thing each:
   - **Red: broken now.** A motor off the CAN bus, a motor cut off for heat, an active controller
     fault. Fix it before queuing.
   - **Yellow: it happened, or watch it.** A dropout, a reboot, low voltage, a motor that got hot
     and cooled, a fault that has already cleared. Each keeps its count until the robot code
     restarts, so after a match the list says what went wrong during it. Check it in the pit.
   - **Info: tell a programmer.** Nothing the drive team can fix at the cart.

   When most motors report the same thing at once (low voltage, CAN dropouts) it shows as one line
   naming the shared cause, the battery or the CAN chain, not a line per motor.
   Once the Wiring tab's map is saved and deployed, each line also says where to look: a power
   fault names the motor's PDH port, a CAN fault the devices either side of it on the cable (only
   after the cable order has been checked on the robot).
3. **The heat override.** In the last seconds of a match, when losing a motor costs more than the
   motor, the driver presses **Back**: a short buzz, and Robot Health shows **Heat override ON**
   with the seconds left. Motors cut off for heat run at half power for 20 seconds; stalls still
   cut out, and a motor already past saving stays off. A **long buzz** means one of those is still
   off, and the override line names it. Each press restarts the 20 seconds.

## The drive team's joysticks

Plug a joystick into the laptop with USB, open **Joysticks**, press any button on it, and name
it (Driver, Operator, Spare 1). Then run the five steps; it takes about a minute:

1. **Hands off**: where each stick rests when nobody touches it.
2. **Circle the sticks**: whether each reaches full deflection in every direction.
3. **Flick and let go**: whether the spring brings it back to center every time.
4. **Squeeze the triggers**: 0 at rest, 1 squeezed.
5. **Press every button**: each press seen once. A worn button "bounces", and the robot sees a
   double-tap.

The report says whether the joystick is fit for a match and what deadband it needs. Peashooter's
code ignores stick values under 0.1, Black team's under 0.08; a stick that drifts past that makes
the robot creep by itself. The driving stick's deadband is round (its distance from center), so
the check judges that stick by how far from center it rests; the turning stick, by its one axis. Check every joystick at the start of an event and after one is
dropped, and save each check: **Every joystick checked** shows which ones are wearing out.
Xbox joysticks have no gyro (and the Driver Station can't read a PlayStation joystick's), so
drift here means the sticks.

To check a joystick exactly as the robot receives it, plug it into the Driver Station laptop,
connect this app to the robot, keep the robot disabled, and set **Read from** to the robot's
port 0 (driver) or 1. The robot records each step and the same checks judge it; a button that
bounces there is one the robot code will act on.

## After a match

AdvantageKit logs every match: to the USB stick in the roboRIO, or on a roboRIO 2 without a stick,
to its SD card (`/home/lvuser/logs`). A roboRIO 1 without a stick keeps no logs, so keep a FAT32
stick in it. Download them with AdvantageScope, then open **Runs, Match logs** and point it at
the folder. It lists brownouts, CAN dropouts, controllers that rebooted, breakers that tripped and
motors that overheated, each with the time in the match, and the place on the wiring map to check.
It also measures the battery that was picked, so a match counts toward that battery's history.

AdvantageScope layouts for both robots are in `tools/swervetune/advantagescope/`.

## On the robot

The robot code already has everything the tools need:

- `AkLogging.start(...)` first in `Robot`'s constructor (AdvantageKit logging).
- Each subsystem registers its motors with the motor guard, which enforces the current policy:
  NEO Vortex 80 A, NEO 2.0 80 A, NEO V1.1 60 A, NEO 550 20 A.
- The driver's joystick **Back** button lets motors cut off for heat run at half power for 20
  seconds, with a short buzz and a "Heat override ON" alert, for when losing a motor costs more
  than the motor. It never lifts a stall cutout; a long buzz says a motor stayed off.

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
  team number right? The robot code must be this branch's: the tools check they match. With two
  networks or a VPN, press **Check the networks**.
- **A Python change doesn't show up**: stop the app (Ctrl+C) and start it again. Browser-only
  changes just need a page reload.
