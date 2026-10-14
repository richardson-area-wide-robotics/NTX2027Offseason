# Tuning the swerve with an AI agent

This is the brief for an AI agent running the swerve tools (`tools/swervetune`). `py -3.12
tools/swervetune brief` prints it. Read all of it before your first command.

The tools do the measuring and the judging. Your job is to run the loop they define, one change at
a time, and to keep the people at the robot informed and in control.

## The hard rules

The robot enforces its own limits (see "What the robot stops by itself" below). These rules are
yours, and nothing in the tools will stop you from breaking them:

1. **A person holds the deadman for anything that moves.** Before any test that spins a wheel,
   confirm in this conversation that someone is at the robot, can see it, and is holding the
   deadman (the tester's joystick right bumper on Driver Station port 1, or the GUI's Hold to
   run button). On blocks too: "blocks" is only what someone told the tool. The CLI keeps the
   laptop's heartbeat alive; it never holds the deadman for anyone.
2. **Only set the environment you were told.** `env --mode BLOCKS` only when a person says every
   wheel is off the ground. `env --mode FIELD --space <m> --side <m> --bumpers` only with
   distances a person measured, and only once a person has said the bumpers are on. Never guess, and never change the mode to make a refused test run.
3. **Never write to the repository without a person's OK.** `save gains`, `config` and `offsets`
   show a diff without `--yes`. Show that diff to a person and wait for an explicit yes before adding
   `--yes`. Never commit or push.
4. **One change per run, never more than double or half.** Every gain change the advisor gives
   is already held to that (`"clamped": true` when it was held, and the finding says so); a gain at
   0 may be set to its first value. Never apply a bigger step yourself.
5. **Stay inside the current policy.** Drive and mechanism limits: NEO Vortex 80 A, NEO 2.0 80 A,
   NEO V1.1 60 A, NEO 550 20 A. The slip test may recommend a drive limit *below* 80 A for this
   carpet; nothing may go above policy.
6. **Never override thermal protection.** `motors --override` is for a person in a match-like
   emergency, not for finishing a test. A motor at DERATE or SHUTOFF means stop and let it cool.
7. **Never change the safety code.** Don't edit `SafetySupervisor`, `MotorGuard`, the deadman or
   the heartbeat to get a test to run. If a refusal looks wrong, report it to a person.
8. **An abort is information.** After an impact, stall, overspeed or driver-override abort, don't
   rerun until a person has looked at the robot and said it's clear.
9. **A motor test needs eyes on the mechanism.** `motor_test` runs a mechanism's motor with the
   robot's own code paused. Before each one, confirm a person sees the mechanism, it is clear of
   hands and hard stops, and they will say which way it turned: its encoder can't tell you that.

## What the robot stops by itself

The robot refuses to start, or aborts, when: the FMS is attached; it is in autonomous; the
environment is unset; the laptop heartbeat is lost (0.5 s); the gyro isn't reporting; a FIELD
test has no measured clear space; the deadman is released mid-test (on blocks or the floor); a driver
touches a stick; the chassis turns, or the lift check before a blocks drive test finds the wheels
carrying weight (a short pulse, NOT_ON_BLOCKS), while "on blocks"; the robot leaves its space (geofence), hits something (impact),
pushes against something (stall) or goes faster than asked; the battery starts below 11.8 V on
the floor (11.0 V on blocks) or sags below 7 V; a motor guard stage stops it. The refusal or
abort reason comes back in the command's output: read it, act on it, and tell the person.

## The commands

Add `--json` to every command: each one then prints exactly one JSON object, strict JSON (no NaN:
a number that couldn't be measured is `null`). In it, `ok` is true only when the command did what
was asked: a test that was refused **or stopped part-way** has `"ok": false`, a `message` for the
person and a `code` (below). Exit codes: 0 done, 1 a test stopped part-way, 2 refused or an error.

| Command | What it does |
|---|---|
| `lint --project Peashooter` | Checks the YAGSL config files; no robot needed. Start here. Each finding's `fix` says what carries it out: `edit` is one `config` change (a person's OK first), `tune` is the test for that loop (`steer` is `steer_step`, `drive` is `drive_step`, `slip` is `slip`), `pathplanner` is `ppcheck`, and `guide` (with a `symptom`, `diagnose <symptom>`) is a step a person does in the GUI's Guide tab: tell them which. |
| `setup --project P [--tab calibrate] [--part module:frontleft --start] [--live]` | Where to start and what to do next: each tool's jobs in order with their status (`done`, `attention`, `todo`, `later` with what it waits for, `optional`, `skip`), and `next`. `--part` is one part that changed (a replaced module, a moved camera, a new field): only work done since it was started counts. Tell the person the next job; the hands-on ones are theirs. |
| `ppcheck --project Peashooter` | Whether PathPlanner's settings describe the same robot as the code. Exits 1 on an error; report it, never edit PathPlanner's files. |
| `status` | Robot, environment, live modules, problems. |
| `netcheck` | Whether this laptop reaches the robot and the internet at the same time (two networks, a VPN). It also checks the Driver Station's year and team number, this laptop's address, the firewall, the radios, and, once connected, the roboRIO image. Run it when `status` can't reach the robot, and tell the person what it says. Never change a network, firewall or radio setting yourself. |
| `versions [--camera vX]` | Is each robot's software the newest for its year: every vendor library against the address it names for its newest, PhotonLib against PhotonVision's releases (never a next-year alpha), and the camera's PhotonVision against PhotonLib (they must match). Report; never update a library yourself. |
| `dslog [file]` | What a Driver Station log recorded of the link (default: this laptop's newest session with a robot): drops and whether the robot was enabled, brownouts, trip time, packet loss, CPU, and which links the Driver Station's pings found bad. |
| `env --mode BLOCKS` / `env --mode FIELD --space 3 --side 1.5 --bumpers` | Tells the robot where it is. |
| `run <test> [--module FL] [--arg key=value]` | Runs one test, saves it (`run_file`), prints the report. The `--arg` keys are below; leave them out unless a report or a person asks. |
| `gains show` / `gains set Steer/kP=0.015 --why "<finding title>" --from-run <run_file>` | Reads or changes live gains (lost at restart until saved). A pod's own PID is `Pod/<module>/Steer/kP` (and `kI`, `kD`, `IZone`; `Drive/...` likewise): it changes that pod only; the shared `Steer/kP` sets every pod. `analyze <run> --pod frontleft` reads a run for one pod with its own gains. Always give `--why`: it goes into the robot's match log with the change. Always give `--from-run` with the run whose report gave the values: it refuses another robot's run, the practice pod's, or one more than a day old. |
| `save gains [--keys Steer FF]` | Shows the diff of writing live gains to the files; `--yes` writes. |
| `config --file F --path a.b --value V` | Shows the diff of one config change (a report's `config` action); `--yes` writes. Only the robot's own config files. |
| `runs [--test steer_step] [--robot Peashooter] [--show robot\|sim\|practice\|all]` | Saved runs, newest first: file, test, outcome, score and cost, gains. Real robot runs only unless `--show` says otherwise; a run that stopped part-way has no score. |
| `analyze <run> [--tape-forward 2.52]` / `explain <run>` / `predict <run> Steer/kP=0.02` | Re-reads a saved run; what the controller saw; "what if" with other gains. For a `straight` run, `--tape-forward` is the distance a person measured with a tape, in meters: the ground truth the wheel size is graded on. |
| `offsets <run> --project P` | New absolute encoder offsets from a `capture` run with every wheel set straight (a person aligns them); `--yes` writes, with their OK. |
| `watch [--seconds 30]` | Prints problems as the robot's monitor spots them (a dropout, a hot motor, a brownout) while people drive. |
| `diagnose [symptom]` | The troubleshooter. |
| `motors` | Heat, stalls and failures for every watched motor. With `--project`, also what each motor and controller is, and any fix as an `edits` list: each edit is one `config --file --path --value`, shown to a person before `--yes`. |
| `practice steer|drive ...` / `rehearse steer|drive ...` | One run, or the whole advice loop, on the simulated practice pod. Its JSON carries `"practice": true`: never save gains from it. |
| `logsummary <file.wpilog> --project P` | What went wrong in a match log, and where to look. |
| `pdhports <run or .wpilog> --project P` | Which PDH port feeds each motor. |
| `design --project P [--draft \| --csv FILE] [--yes]` | The robot's design file (`src/main/deploy/design/devices.json`): what doesn't add up in it, and where the code disagrees with it (CAN IDs, MAX vs Flex, followers, inversion, ports). `--draft` drafts one from the code, `--csv` imports the design team's spreadsheet; `--yes` writes it only when none exists, with a person's OK. Exits 1 on an error. |

Tests for `run`: `capture` (sensors only, disabled), `steer_step`, `drive_step`, `drive_ff`,
`spin`, `spin_ff` (moment of inertia), `straight`, `slip`, `pdh_map`, `controller` (a Driver
Station joystick port as the robot sees it; disabled, moves nothing), `motor_test` (bring-up: runs chosen
motors briefly at low output, on blocks, with the robot's own code paused; rule 9), `sensors`
(bring-up: every sensor's value live while a person trips each by hand; moves nothing, runs
disabled; ends on `stop` or after `duration_s`), `can_load` (3 s quiet, 8 s with the swerve
controllers' status frames sped up, 2 s quiet: counts CAN errors and bus-offs; moves nothing; a clean
result does not prove the termination, the meter check does), `system_limits` (a person moves a
pivot or elevator by hand to both ends, robot disabled, its motors coasting: those are its limits),
`system_step` (a registered mechanism's own closed loop, its goal moved along a path no faster than
`vmax` nor `amax`; refuses a pivot or elevator without limits, stops it past them or too fast),
`system_piece` (calibrates a game-piece current sensor: `sensor` and `system` by number and
`pieces`; a roller runs while a person feeds that many pieces one at a time when the banner says,
stopping between them; an arm or elevator sweeps empty, then once with each piece; a person is
part of it, so never run it without one), `system_hold` (tunes a hold current like the slip test:
`hold` by number, a piece in; the limit steps down from `start_a` while a person pulls the piece the
same way each time, until it slips; then 1.5 times that is held for `heat_s` to see the motor warm).

Their `--arg` keys (the robot clamps each to a safe range and says so):

| Test | Keys |
|---|---|
| `capture` | `duration_s`, `rate_hz`, `coast=1` (wheels free to push by hand) |
| `steer_step` | `pattern` (0 standard, 1 small, 2 large), `hold_s`, `settle_s`, `rate_hz` |
| `drive_step` | `s0`, `s1`, ... (the speeds, m/s), `hold_s`, `align_s`, `angle_deg` |
| `drive_ff`, `spin_ff` | `max_v`, `ramp_vps`, `step_v`, `step_s`, `rest_s` |
| `spin` | `omega` (rad/s), `duration_s` |
| `straight` | `distance_m`, `speed`, `accel`, `return=1` (come back; leaves nothing to measure) |
| `slip` | `ceiling_a`, `ramp_vps`, `slip_mps`, `direction` (1 or -1) |
| `pdh_map` | `volts` |
| `controller` | `port`, `duration_s` |
| `sensors` | `duration_s` (5-300, default 120). Reads the sensors the code registers (`watchSensor`) and the deployed design file's others, opened from their ports for the readout only |
| `can_load` | none |
| `system_limits` | `system` (its index in the robot's Systems list), `duration_s` |
| `system_step` | `system`, `a`, `b` (goals, or speeds for a flywheel, in its units), `vmax`, `amax` (per second), `hold_s`, `moves` |
| `motor_test` | `drive`, `zero`, `watch` (bit masks over the robot's motor list, in the order `motors` lists them: run, hold at zero, only record; never drive or zero a follower, drive its leader), `duty` (0.02-0.15), `pulse` (0.2-1.0 s), `sign` (1 or -1), `stop_amps` |

## The loop

```
run <test>  ->  read the report  ->  apply report.next  ->  run <test> again
```

Every report has the same shape:

```
summary   one line for a person
score     0-100: the share of the targets met; null when the run stopped part-way
cost      lower is better: what you are minimizing
targets   [{name, value, target, met, lower_is_better}]
findings  [{level, title, why, action?}], most important first
next      the finding to act on: {level, title, why, action}, or null
```

People can also change gains from AdvantageScope's tuning mode while you work. Run `gains show`
before each test, and if a gain isn't what you last set, ask before going on.

Act on `next.action` and only on it. Every action is one the commands above carry out as written:

- `{"type": "gains", "values": {...}}`: `gains set` exactly those values with `--why` the finding's
  title and `--from-run` the run the report came from, then rerun the same test, or the test in `then` when the action has one (`{"test":
  "drive_step", "env": "FIELD"}` after a measured feedforward).
- `{"type": "run", "test": ..., "env": ...}`: run that test next (ask a person to change the
  environment if it differs).
- `{"type": "config", "file", "path", "value"}`: a file change that needs a redeploy. Run
  `config --file <file> --path <path joined by dots> --value <value as JSON>`, show the diff to a
  person, and add `--yes` only with their OK.
- `{"type": "save", "keys": [...]}`: `save gains --keys <keys>`; same rule, a person's OK first.
- `{"type": "troubleshoot", "symptom": ...}`: run `diagnose <symptom>` and relay what it says.
- `{"type": "stop", "reason": ...}`: the run stopped part-way. Tell the person the reason; don't
  rerun until they say the robot is clear and the cause is fixed.

## Why a test was refused or stopped

`code`, with the robot's own sentence in `message`:

| Code | What to do |
|---|---|
| `FMS_ATTACHED`, `AUTONOMOUS` | Nothing runs on a match field or in autonomous. Stop. |
| `ENV_UNSET`, `ENV_CHANGED` | Ask a person where the robot is; never set it to make a test run. |
| `NO_HEARTBEAT`, `NOT_CONNECTED` | The laptop lost the robot. Reconnect; tell the person. |
| `GYRO` | The gyro isn't reporting or is calibrating. Wait, then ask a person. |
| `NO_SPACE` | A person must measure the clear floor and put the bumpers on (`env --mode FIELD --space --side --bumpers`). |
| `DEADMAN`, `DRIVER_INPUT`, `ABORTED_BY_PERSON` | A person let go, drove, or aborted: ask why before anything else. |
| `DRIVETRAIN_TAKEN` | Another command (a drive button) took the drivetrain mid-test: ask the people to keep drive buttons alone, then rerun. |
| `NOT_ON_BLOCKS`, `IMPACT`, `GEOFENCE`, `NO_WALL`, `STALL`, `OVERSPEED` | Something physical: a person looks at the robot first. |
| `BATTERY` | Swap the battery (and pick its number). |
| `MOTOR_GUARD` | A motor is hot or stalled: let it cool; never override. |
| `DISABLED`, `NEEDS_DISABLED` | The Driver Station mode is wrong for this test: ask a person. |
| `NO_JOYSTICK`, `NO_PDH` | The robot can't read what the test needs; tell the person. |
| `BAD_ARGS` | Your command's arguments: fix the command. |
| `NO_SENSORS` | The sensor readout has nothing to read: the code registers no sensor and the deployed design file lists none. Deploy the design file, or register the code's sensors with `watchSensor`. |
| `NO_CAN_STATUS` | The robot code can't read the CAN bus's status, so the load test has nothing to count. |
| `NO_SYSTEM_HOOK` | The robot code registers that mechanism without a goal to set. A programmer adds `.goal(...)`. |
| `NO_LIMITS` | A pivot or elevator without limits: run `system_limits` with a person moving it by hand. Never invent them. |
| `PAST_LIMITS` | The mechanism left its limits and was stopped. A person looks at it before anything else runs. |
| `JAMMED` | A motor pulled hard without turning: jammed, or motors on one shaft pushing against each other. A person looks first; then run each motor on that shaft alone. |
| `NO_MOTORS`, `NOT_SUPPORTED` | The robot has no motors registered with its motor guard, or one the test can't run: tell the person. |
| `NO_PROJECT`, `NOT_FOUND` | A robot project or saved run that doesn't exist: `runs` lists runs; the projects are Peashooter and Black team. |
| `WRONG_PLACE` | The test can't run where the robot is (a floor test on blocks, the PDH map on the floor): ask a person to move it and set the environment. |
| `GAINS_REFUSED` | The robot refused a gain change (a test running, the FMS attached): nothing changed; wait, then `gains show`. |
| `WRONG_ROBOT` | `--from-run` names another robot's run, or the practice pod's: run the test on this robot. |
| `STALE_RUN` | `--from-run` names a run more than a day old: run the test again; `--force` only with a person's OK. |
| `TOOL_ERROR` | The tool itself failed: report the message to a person; don't retry blindly. |
| `TIMEOUT`, `WAITED_TOO_LONG`, `BUSY`, `ROBOT_ERROR`, `OTHER` | Read `message` to the person and wait. |

Stop when `next` is null or a save (show the save's diff to a person), or when the cost hasn't
improved over three runs that each changed something; a step held to 2x is still progress
(`runs --test <test>` lists them with their costs). Then summarize for the person: what was measured, what changed,
what is left.

Before spending battery and floor time on a strategy, `rehearse` it against the practice pod. The
same advisor drives it, so a strategy that doesn't converge there won't converge on carpet.

## The order

Follow the GUI's Guide tab order; each step depends on the ones before it:

1. `lint`, then `status`.
2. `run capture` with the robot disabled: sensor health.
3. Hand check (a person turns wheels; the GUI's Guide does this).
4. Absolute encoder offsets (`run capture`, then `offsets <run> --project P`; a person aligns
   the wheels first, and approves the diff before `--yes`).
5. On blocks: every wheel drives the right way.
6. Measure the robot: module positions (tape) and wheel sizes (a push in coast), in the GUI's
   Calibrate tab. People measure; you can walk them through it.
7. Steering on blocks, then on the floor (`steer_step`).
8. Slip current on the floor against a wall (`slip`).
9. Feedforward (`drive_ff`), then drive speed (`drive_step`).
10. Spin and straight-line checks.
11. Second-order motion profiles stay locked until steering and drive pass on a real robot.
12. A person saves, redeploys, checks the startup list, and commits.

## Telling the people what you are doing

Before each test, say which test, where (blocks or floor), what will move, roughly how far and for
how long. After each test, give the summary line, the score, and what you will change next. Keep
it short; they are watching a robot, not a screen.
