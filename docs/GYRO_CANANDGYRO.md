# The gyro for 2027: Redux Canandgyro ("Boron")

Both robots use a navX on the roboRIO's MXP port today. SystemCore, the 2027 robot controller, has
no MXP or SPI port, so next season's gyro is the **Redux Robotics Canandgyro**, sold as the
**Boron**. Its library is ReduxLib (`vendordeps/ReduxLib-2026.1.2.json`, already in both robots),
and its setup tool is Redux's **Alchemist**. This page covers fitting it, setting it up, calibrating
it, and what Sloth Tune does with it.

## What it is

| | |
|---|---|
| Measures | Yaw (heading), pitch, roll, turn rate, acceleration, temperature |
| Range | ±2000 °/s turning, ±16 g acceleration |
| Drift (calibrated) | 0.2 °/hour standing still; 0.25 °/minute while moving |
| Power | 4.3 to 16 V, about 40 mA; reverse-polarity protected |
| CAN | CAN 2.0B at 1 Mbps. **Not CAN FD**, so not on a CANivore. About 2.2% of the bus at its defaults |
| Temperature | Keep it between 0 and 70 °C |

Yaw is counterclockwise positive, the same as WPILib.

## Fitting it

- **Z axis pointing up** (the label side up), as flat as you can make it.
- **In the middle of the robot** (seen from above). Near the edges of the chassis it feels extra
  acceleration when the robot turns, which costs accuracy.
- **Away from hard hits and vibration.** Heavy vibration or frequent collisions add drift while
  moving.
- **Wiring:** CAN High to the yellow terminal, CAN Low to the green, 12 V to the red, ground to the
  black (or the solder pads). It is a CAN device like any other on the chain: the bus still needs
  its 120 Ω terminator at each end (the Wiring tab checks that).
- Its case screw goes into plastic: don't overtighten it.

## Setting it up with Alchemist

Alchemist is Redux's desktop app (Windows, Mac, Linux):
<https://github.com/Redux-Robotics/Alchemist/releases>. It doesn't talk to the gyro directly. The
robot code, through ReduxLib, runs a small server on the robot (Redux CANLink, port 7244), and
Alchemist connects to that over the robot's network.

1. **Deploy robot code that uses ReduxLib** (both robots' code does). The robot's console shows
   `[redux-canlink] Redux CANLink has started on port 7244.`
2. In Alchemist, type the team number (or connect by USB to `172.22.11.2`) and press
   **Connect to CANBus!**. It says **Connected!**.
3. **Find the gyro:** press **Blink LEDs**. The Calibrate tab's **Blink its light** does the same
   once the gyro has its ID.
4. **Give it its own CAN ID.** A new Canandgyro comes as ID 0, and Redux advise against using 0
   (the tools warn about it). Type the new ID in **CAN ID** under Device Overview and press
   **save**. Two devices with one ID blink red and blue in turn: blink to find one, give it a new
   ID, and repeat. If Alchemist can't see both, power-cycle the robot and restart Alchemist.
5. **Update its firmware:** **Upload Firmware**, **fetch new updates**, then
   **install downloaded firmware**. The Calibrate tab shows the firmware it is running.
6. Put the ID in the robot code (next section).

ReduxLib also serves a web page with the same basics (change the ID, blink the light, update the
firmware) at `http://roborio-TEAM-frc.local:7244` (for team 1745, `roborio-1745-frc.local`). Use it
if Alchemist won't connect. Alchemist's last release is from December 2024, and whether it works
with ReduxLib 2026 hasn't been confirmed.

## In the robot code

In `src/main/deploy/swerve/swervedrive.json`, with YAGSL 2026.4.1:

```json
"imu": {"type": "canandgyro", "id": 12, "canbus": ""},
"invertedIMU": false
```

Things YAGSL 2026.4.1 does with it that matter:

- **It resets the gyro to its factory settings every time the robot code starts.** Anything set in
  Alchemist other than the CAN ID is lost, so the robot code sets the report rates again
  afterwards (below).
- **It reads the heading from the gyro's angular position (a quaternion)**, not the yaw reading.
- **It ignores `canbus`**: it always opens the gyro on the robot controller's own bus. The config
  check says so if the field is filled in.
- **Its acceleration is about 16,384 times too small** (it scales a reading that is already in g).
  The swerve library reads the gyro's acceleration directly instead, so the impact and lifted-robot
  checks work.

Check it with the Calibrate tab's gyro step (below) and the Guide's gyro direction check before
driving: the heading must go up when the robot turns counterclockwise. If it goes the wrong way,
flip `invertedIMU`.

## Calibrating

**At power-on** it calibrates itself. Its light is **solid yellow** until it is done (a few
seconds, the robot kept still), then **slow green**. It works while yellow, but less accurately.
**Keep the robot still for about 7 seconds after turning it on.**

**Again, from the tool:** Calibrate tab, **4. Gyro**, **Calibrate it**. The robot must be
**disabled**, and the robot must stay completely still for about 7 seconds. Do this:

- if the robot was moving or bumped when it powered on (the standing-still drift will be high);
- after a hard hit;
- when **Record a minute still** shows more than 0.5° a minute of drift.

A calibration started from the tool is **not saved** on the gyro: it calibrates again at the next
power-on. Then run the step's two checks:

1. **Record a minute still:** under 0.5° a minute of drift.
2. **Full turns:** each turn reads within 1% of 360°. The team corrects the scale only when it is
   more than 1% off.

The Calibrate tab also shows what the gyro reports about itself: connected, calibrating, its
temperature, its firmware, and its faults now and earlier. **Clear its sticky faults** forgets the
ones that have gone, so you can see which come back.

## Report rates (how often it sends each reading)

Set in `slothtune.json`, applied by the robot code at every startup after YAGSL's reset, and not
saved on the gyro (so its flash isn't worn by writing them every boot). The Calibrate tab's
**Canandgyro report rates** shows and saves them; each one explains itself on hover.

| Reading | `slothtune.json` key | Ours (ms) | Redux default (ms) | Why ours |
|---|---|---|---|---|
| Yaw | `canandgyro.yawFramePeriodMs` | 10 | 10 | Redux's default |
| Angular position | `canandgyro.angularPositionFramePeriodMs` | 10 | 20 | YAGSL's heading comes from this: half the delay |
| Angular velocity | `canandgyro.angularVelocityFramePeriodMs` | 20 | 100 | YAGSL's angular velocity compensation needs it fresh |
| Acceleration | `canandgyro.accelerationFramePeriodMs` | 20 | 100 | The impact and lifted-robot checks read it; 100 ms can miss a short hit |
| Status | `canandgyro.statusFramePeriodMs` | 100 | 100 | Faults and temperature; it can't be 0 |

`0` leaves a reading as YAGSL left it; `"canandgyro": {"apply": false}` leaves all of them. All
together these come to about 3% of the CAN bus.

## Faults and its light

The Live data and the Calibrate tab show its faults in words. Its light's colors are in
Troubleshoot, **Status lights**, **Canandgyro**, with the row the robot says it should be showing
marked.

| Fault | Means | Do |
|---|---|---|
| restarted (earlier) | It lost power at some point | Check its power wiring if this keeps coming back |
| CAN ID conflict | Another device has its ID (red and blue in turn) | Give one of them a new ID in Alchemist |
| CAN error | A CAN bus fault (slow red) | Check its CAN wiring |
| out of temperature range | Too hot or too cold | Move it away from hot motors |
| hardware fault | It can't read its own sensor (red and yellow in turn) | Power-cycle; if it comes back, contact Redux |
| rotation rate / acceleration saturated | Turned faster than ±2000 °/s or hit harder than ±16 g | Expect less accuracy for a while |

While it is calibrating, the tools refuse to start a test: a test needs the gyro.

## For the 2027 port

- ReduxLib 2027 moves the class to `com.reduxrobotics.canandgyro`, and its CAN bus argument becomes
  a `CANPort`.
- YAGSL 2027 names it `"gyro": {"type": "canandgyro_can", ...}` with `"gyroAxis": "yaw"` and
  `"gyroInvert"`, and it doesn't add ReduxLib for you.

See docs/MIGRATION_2027.md.

## Sources

- Redux Robotics: <https://docs.reduxrobotics.com/canandgyro/> (overview, specifications, LED codes,
  calibrating, settings, faults, known issues) and Alchemist,
  <https://docs.reduxrobotics.com/alchemist/>.
- ReduxLib 2026.1.2 API: <https://apidocs.reduxrobotics.com/v2026.1.2/java/>. The method names the
  robot code uses were checked against the library itself.
- YAGSL 2026.4.1's source, for the factory reset, the heading frame and the acceleration scale.
