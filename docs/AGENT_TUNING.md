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
   deadman (SPACE in the GUI, or the tester's controller bumper). The CLI keeps the laptop's
   heartbeat alive; it never holds the deadman for anyone.
2. **Only set the environment you were told.** `env --mode BLOCKS` only when a person says every
   wheel is off the ground. `env --mode FIELD --space <m> --side <m>` only with distances a
   person measured. Never guess, and never change the mode to make a refused test run.
3. **Never write to the repository without a person's OK.** `save gains` and `offsets` show a
   diff without `--yes`. Show that diff to a person and wait for an explicit yes before adding
   `--yes`. Never commit or push.
4. **One change per run, never more than double or half.** The advisor's `next` action already
   follows this. `--force` (a bigger step) needs a person's OK and a reason.
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

Add `--json` to every command: each one then prints exactly one JSON object.

| Command | What it does |
|---|---|
| `lint --project Peashooter` | Checks the YAGSL config files; no robot needed. Start here. |
| `status` | Robot, environment, live modules, problems. |
| `env --mode BLOCKS` / `env --mode FIELD --space 3 --side 1.5` | Tells the robot where it is. |
| `run <test> [--module FL] [--arg key=value]` | Runs one test, saves it, prints the report. |
| `gains show` / `gains set Steer/kP=0.015` | Reads or changes live gains (lost at restart until saved). |
| `save gains [--keys Steer FF]` | Shows the diff of writing live gains to the files; `--yes` writes. |
| `analyze <run>` / `explain <run>` / `predict <run> Steer/kP=0.02` | Re-reads a saved run; what the controller saw; "what if" with other gains. |
| `diagnose [symptom]` | The troubleshooter. |
| `motors` | Heat, stalls and failures for every watched motor. |
| `practice steer|drive ...` / `rehearse steer|drive ...` | One run, or the whole advice loop, on the simulated practice pod. |
| `logsummary <file.wpilog> --project P` | What went wrong in a match log, and where to look. |
| `pdhports <run or .wpilog> --project P` | Which PDH port feeds each motor. |

Tests for `run`: `capture` (sensors only, disabled), `steer_step`, `drive_step`, `drive_ff`,
`spin`, `straight`, `slip`, `pdh_map`.

## The loop

```
run <test>  ->  read the report  ->  apply report.next  ->  run <test> again
```

Every report has the same shape:

```
summary   one line for a person
score     0-100: the share of the targets met
cost      lower is better: what you are minimizing
targets   [{name, value, target, met}]
findings  [{level, title, why, action?}], most important first
next      the first finding's action, or null
```

People can also change gains from AdvantageScope's tuning mode while you work. Run `gains show`
before each test, and if a gain isn't what you last set, ask before going on.

Act on `next` and only on `next`:

- `{"type": "gains", "values": {...}}`: `gains set` exactly those values, then rerun the same test.
- `{"type": "run", "test": ..., "env": ...}`: run that test next (ask a person to change the
  environment if it differs).
- `{"type": "config", "file", "path", "value"}`: a file change that needs a redeploy. Show it to a
  person; don't apply it yourself.
- `{"type": "troubleshoot", "symptom": ...}`: run `diagnose <symptom>` and relay what it says.

Stop when the score reaches 100, or the cost hasn't improved over three runs. Then summarize for
the person: what was measured, what changed, what is left.

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
