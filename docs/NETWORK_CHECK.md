# Checking a robot's network

Use this when the Driver Station can't reach a robot, and the first time on each robot to check the
swerve tools read the real hardware right.

**What it is:** **Check the networks** reads the Driver Station, this laptop's address, the
firewall, the radios and, once connected, the robot. It changes nothing.

**What you need:**
- About 15 minutes per robot.
- The Driver Station laptop.
- The robot, on and disabled. Nothing moves during any of this.
- An Ethernet cable.

## Once, on the Driver Station laptop

1. **Get the tools.** The laptop needs this repository on the `StuartTesting` branch, up to date
   (`git pull`), and Python 3.12. The guide's
   [Setting up](SWERVE_TUNING_GUIDE.md#setting-up-once-per-laptop) section covers this.
2. **Install the Driver Station.** It comes with FRC Game Tools 2026, then the latest update for it.
   - Its Diagnostics tab shows its version, which must be 26.x.
3. **Open the Driver Station once.**
   - On the Setup tab (the gear), set **Team Number** to the robot's.
   - When Windows asks about the firewall, allow it on **both** private and public networks.

## For each robot

| Robot | Team number | Robot radio | Robot |
| --- | --- | --- | --- |
| Peashooter | 1745 | 10.17.45.1 | 10.17.45.2 |
| Black team | 9990 | 10.99.90.1 | 10.99.90.2 |
| A test robot such as 17451 | 17451 | 10.174.51.1 | 10.174.51.2 |

1. **Power it up and wait.** Turn the robot on, leave it disabled, and wait a minute.
   - On the robot radio, **PWR** should be solid.
   - **SYS** solid means it's linked to the access point.
   - Write down what SYS does: solid, blinking about once a second, or off.
2. **Join its network.** Use the access point radio's network (a cable, or its Wi-Fi), or a cable
   into the robot radio's **DS** port.
3. **Set the Driver Station** to this robot's team number (Setup tab, the gear).
4. **Start the tools and check.** From the repository folder:

   ```
   py -3.12 tools/swervetune gui
   ```

   - Pick the robot's project (Peashooter or Black team).
   - On the **Troubleshoot** tab, press **Check the networks** (top right). It takes about 15
     seconds.
5. **Fix the red lines.** Fix each one, using the table below, then **Check again**. Repeat until
   nothing is red.
6. **Check again while connected.**
   - Pick **Robot (team number)** and press **Connect**.
   - On the **Troubleshoot** tab, press **Check the networks** again. Connected, it also reads the
     roboRIO's image.
7. **Save it.** Press **Save a copy to send**. The file goes in `tools/swervetune/reports/`, named
   after the robot and the time.
8. **Read the radio's firmware.** Open `http://10.TE.AM.1/` (for Peashooter, `http://10.17.45.1/`)
   in a browser. Write down the firmware version at the bottom of its page, or that none is shown.

Without the app, step 4 can run in a terminal instead. It saves the file too:

```
py -3.12 tools/swervetune netcheck --project Peashooter --save
```

## What the red lines mean

| It says | Do this |
| --- | --- |
| Driver Station from another year | Install FRC Game Tools 2026, then its latest update. |
| The Driver Station is set to another team | Setup tab (the gear): Team Number for this robot. |
| Got no address (169.254.x) | Wait a minute for the radio. On a cable, use the radio's **DS** port. |
| Set to 192.168.69.x, or set by hand to another team's address | That adapter's settings: IP assignment **Automatic (DHCP)**. |
| A radio on its factory setting (team 1), or set for another team | Configure that radio for this team: the guide's [radio section](SWERVE_TUNING_GUIDE.md#the-radio-vh-109). |
| The access point radio answers; the robot radio doesn't | The robot radio still has an event's settings, or doesn't match the access point. Set it again: the guide's [radio section](SWERVE_TUNING_GUIDE.md#the-radio-vh-109). |
| Windows Firewall has no rule letting the Driver Station in | Windows Security, Firewall, **Allow an app through firewall**: tick Driver Station for Private and Public. |
| Another firewall is running | Allow the Driver Station in it too, or turn it off while on the robot's network. |
| roboRIO image is from another year | Image the roboRIO with the roboRIO Imaging Tool (FRC Game Tools 2026). |
| The link to the robot dropped (from the Driver Station's log) | Troubleshoot: **The robot keeps losing communication**. |
| Browned out (from the Driver Station's log) | Charge or swap the battery; check its leads are tight. |
| The camera runs another PhotonVision than the robot code's PhotonLib | Make them the same: flash the camera with that release's Luma P1 image (or upload its `linuxarm64` .jar on the camera's Settings page), or change `vendordeps/photonlib.json`. |
| A library or PhotonLib has a newer version (amber, Software versions) | Not urgent. Update it with WPILib's **Manage Vendor Libraries**, build, and test on the robot before an event. PhotonLib and the camera go together. |

The yellow lines are worth reading but don't stop the robot. Troubleshoot's **Connecting to the
robot** symptoms walk through the same causes one question at a time.

## This weekend: send the results back

For each robot, send:

1. **The saved file** from step 7: `tools/swervetune/reports/netcheck-<robot>-<time>.json`.
2. **What the SYS light did** (step 1).
3. **The firmware version** the radio's page shows, or "none shown" (step 8).
4. **Anything the check got wrong:** a red line for something that was fine, or nothing said about
   something that was broken.
5. **If the robot dropped out**, that session's Driver Station logs: the `.dslog` and `.dsevents`
   files with its date and time, in `C:\Users\Public\Documents\FRC\Log Files`. They hold the
   link's timing and the Driver Station's messages; no passwords.

Paste the file's contents into a Claude Code session on this repository, or attach the file, with
items 2 to 5.

**What's in the file:**
- Every result, and the facts behind them: the Driver Station's version and team number, this
  laptop's adapters and their addresses, the firewall's rules for the Driver Station, and which
  radios answered.
- From the radio's page, only its firmware line.
- **No passwords.** Anything there that looks like a key is hidden. The folder isn't committed to
  git.

**What it confirms:**
- that the tools read the firmware version the way the radio's page shows it;
- that they find the Driver Station's team number in its settings file;
- with a dropped session's logs, that the tools read a dropped link in the Driver Station's log.

Both are checked so far only against the radio's and the Driver Station's documentation.
