# Robot day: bringing up a live robot

A first session with a real robot, with someone helping from a distance (Claude, over chat, on this
same laptop) while a person stands at the robot. Sloth Tune's `session` command walks the steps in
order, runs the tool's own checks for each, and keeps a record you can send afterwards.

The order is how a robot is brought up: **connect**, **bring-up** (robot disabled, then on blocks),
**tuning**, **testing** on the floor, set-up for **a field or competition**, then **troubleshooting**,
where you cause a known fault on purpose and the tool must spot it. That last part tests Sloth Tune
itself as much as the robot.

## Before you go

1. **Deploy the newest robot code** from the team repo's StuartTesting branch (`cd "Black team"`,
   `./gradlew deploy`, robot connected). The robot code now has homing, the deadman's port 1 check and
   its own module checks. The session's `link` step fails until it is deployed.
2. On the laptop: pull StuartTesting, then `py -3.12 -m pip install -r tools/requirements.txt`.
3. Charge the batteries: 12.4 V or more at rest.
4. Driver Station: the driver's controller at **port 0**, the deadman's controller at **port 1**
   (USB tab; drag to reorder).
5. Bring blocks that hold the wheels off the floor, a straight-edge, a tape measure and painter's tape.

## The laptop on two networks

One adapter on the internet (Claude), one on the robot. For the first session, put the robot on
**Ethernet** (a USB Ethernet adapter to the radio): Wi-Fi to a radio on a bench is the first thing to
rule out when a link drops.

```
py -3.12 tools/slothtune netcheck --project "Black team"
```

It finds the adapter on 10.17.45.x, checks robot traffic leaves by it and everything else by the
internet adapter, and says the one fix if not (run as Administrator, with `-Fix`). If the Driver
Station shows communications but no robot code while Sloth Tune connects fine, Windows calls the
robot's network Public and its firewall is blocking the Driver Station there: allow it.

## Running the session

From the repo's root folder:

```
py -3.12 tools/slothtune session start --project "Black team" --who "Stuart"
py -3.12 tools/slothtune session next                 # the step to do now: where, what, what passes
py -3.12 tools/slothtune session check hand-wheels    # the tool's checks for one step
py -3.12 tools/slothtune session check directions --blocks
py -3.12 tools/slothtune session mark directions pass --note "all four rolled forward"
py -3.12 tools/slothtune session issue "the Motors tab showed ..."   # something wrong with Sloth Tune
py -3.12 tools/slothtune session plan                 # every step and where it stands
py -3.12 tools/slothtune session report               # the write-up, beside the record
```

- A step where you move something (the hand checks, the deadman, the faults) **counts down and
  beeps**: start when you hear GO, stop at the double beep.
- A step on blocks needs `--blocks`: it means a person looked and the wheels are free.
- A floor step needs the environment set first, with the clear floor measured:
  `py -3.12 tools/slothtune env --mode FIELD --space 120 --side 60 --bumpers --project "Black team"`.
- Some things only a person can see (which way a wheel turned on blocks, the sticks). The tool does
  its part, then says what to watch and how to mark it.
- A check that crashes is recorded as an error and the session goes on. That is a Sloth Tune defect:
  add a line with `session issue`.

The record and report are in `tools/slothtune/runs/sessions/` (a JSON record and a Markdown report),
and every run is in `tools/slothtune/runs/`. Neither is committed.

## The steps

| Phase | Steps | Where the robot is |
|---|---|---|
| 1. Connect | network, link, config, versions, battery, deadman | On, disabled |
| 2. Bring-up | controllers, can, health, hand-wheels, hand-steer, hand-gyro, offsets, directions, joysticks, pdh | Disabled; directions and pdh on blocks |
| 3. Tuning | steer-blocks, steer-floor, slip, ff, drive, systems | Blocks, then the floor |
| 4. Testing | spin, straight, maneuver, sticks | The floor, room to drive |
| 5. A field or competition | pathplanner, vision, venue | The field |
| 6. Troubleshooting | watch, fault-encoder, fault-controller, fault-deadman, fault-link, diagnose | Disabled; fault-deadman on blocks |

## Safety

- Nothing in the session enables the robot. A person enables it in the Driver Station, and a
  person holds the deadman. The robot refuses a test in the wrong place, and stops one the moment
  the deadman is let go.
- In the Driver Station, **Enter disables** the robot and the **space bar is the emergency stop**.
  Keep a hand near the keyboard whenever it is enabled.
- On blocks, check the wheels are clear of the blocks and of hands before enabling.
- On the floor: bumpers on, the clear floor measured and told to the robot, people out of the space.
