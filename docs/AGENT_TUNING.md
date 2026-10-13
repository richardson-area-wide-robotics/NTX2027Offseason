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
   deadman (the tester's controller right bumper, or SPACE in the GUI; never SPACE on the Driver
   Station laptop, where it is the E-STOP). The CLI keeps the laptop's heartbeat alive; it never
   holds the deadman for anyone.
2. **Only set the environment you were told.** `env --mode BLOCKS` only when a person says every
   wheel is off the ground. `env --mode FIELD --space <m> --side <m>` only with distances a
   person measured. Never guess, and never change the mode to make a refused test run.
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

## What the robot stops by itself

The robot refuses to start, or aborts, when: the FMS is attached; it is in autonomous; the
environment is unset; the laptop heartbeat is lost (0.5 s); the gyro isn't reporting; a FIELD
test has no measured clear space; the deadman is released mid-test; a driver touches a stick; the
chassis turns while "on blocks"; the robot leaves its space (geofence), hits something (impact),
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
| `lint --project Peashooter` | Checks the YAGSL config files; no robot needed. Start here. |
| `status` | Robot, environment, live modules, problems. |
| `env --mode BLOCKS` / `env --mode FIELD --space 3 --side 1.5` | Tells the robot where it is. |
| `run <test> [--module FL] [--arg key=value]` | Runs one test, saves it, prints the report. |
| `gains show` / `gains set Steer/kP=0.015` | Reads or changes live gains (lost at restart until saved). |
| `save gains [--keys Steer FF]` | Shows the diff of writing live gains to the files; `--yes` writes. |
| `config --file F --path a.b --value V` | Shows the diff of one config change (a report's `config` action); `--yes` writes. Only the robot's own config files. |
| `runs [--test steer_step] [--robot Peashooter] [--show robot\|sim\|practice\|all]` | Saved runs, newest first: file, test, outcome, score and cost, gains. Real robot runs only unless `--show` says otherwise; a run that stopped part-way has no score. |
| `analyze <run>` / `explain <run>` / `predict <run> Steer/kP=0.02` | Re-reads a saved run; what the controller saw; "what if" with other gains. |
| `diagnose [symptom]` | The troubleshooter. |
| `motors` | Heat, stalls and failures for every watched motor. |
| `practice steer|drive ...` / `rehearse steer|drive ...` | One run, or the whole advice loop, on the simulated practice pod. Its JSON carries `"practice": true`: never save gains from it. |
| `logsummary <file.wpilog> --project P` | What went wrong in a match log, and where to look. |
| `pdhports <run or .wpilog> --project P` | Which PDH port feeds each motor. |

Tests for `run`: `capture` (sensors only, disabled), `steer_step`, `drive_step`, `drive_ff`,
`spin`, `spin_ff` (moment of inertia), `straight`, `slip`, `pdh_map`, `controller` (a Driver
Station port as the robot sees it; disabled, moves nothing).

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

- `{"type": "gains", "values": {...}}`: `gains set` exactly those values, then rerun the same test.
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
| `NO_SPACE` | A person must measure the clear floor (`env --mode FIELD --space --side`). |
| `DEADMAN`, `DRIVER_INPUT`, `ABORTED_BY_PERSON` | A person let go, drove, or aborted: ask why before anything else. |
| `DRIVETRAIN_TAKEN` | Another command (a drive button) took the drivetrain mid-test: ask the people to keep drive buttons alone, then rerun. |
| `NOT_ON_BLOCKS`, `IMPACT`, `GEOFENCE`, `NO_WALL`, `STALL`, `OVERSPEED` | Something physical: a person looks at the robot first. |
| `BATTERY` | Swap the battery (and pick its number). |
| `MOTOR_GUARD` | A motor is hot or stalled: let it cool; never override. |
| `DISABLED`, `NEEDS_DISABLED` | The Driver Station mode is wrong for this test: ask a person. |
| `NO_CONTROLLER`, `NO_PDH` | The robot can't read what the test needs; tell the person. |
| `BAD_ARGS` | Your command's arguments: fix the command. |
| `TIMEOUT`, `WAITED_TOO_LONG`, `BUSY`, `ROBOT_ERROR`, `OTHER` | Read `message` to the person and wait. |

Stop when the score reaches 100, or the cost hasn't improved over three runs (`runs --test <test>`
lists them with their costs). Then summarize for the person: what was measured, what changed,
what is left.

Before spending battery and floor time on a strategy, `rehearse` it against the practice pod. The
same advisor drives it, so a strategy that doesn't converge there won't converge on carpet.

## The order

Follow the GUI's Guide tab order; each step depends on the ones before it:

1. `lint`, then `status`.
2. `run capture` with the robot disabled: sensor health.
3. Hand check (a person turns wheels; the GUI's Guide does this).
4. Absolute encoder offsets (`run capture`, then `offsets <run>`; a person aligns the wheels).
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
