---
name: swerve-tuning
description: Tune, check or troubleshoot the Peashooter or Black team YAGSL swerve drive with Sloth Tune (tools/slothtune) - running tests on the robot or simulator, reading reports, changing gains, motor health, wiring faults, match logs. Use whenever a request touches swerve tuning, drive or steering gains, offsets, the motor guard, CAN or PDH faults, or a .wpilog from these robots.
---

# Swerve tuning with tools/slothtune

1. **Read the brief first, every session:** `py -3.12 tools/slothtune brief`. It is
   `docs/AGENT_TUNING.md`: the hard rules, what the robot stops by itself, the commands, the
   report loop and the order. The rules are not optional. Above all: a person holds the deadman for
   anything that moves, you only set the environment you were told, and nothing is written to the
   repository without a person's OK.
2. Add `--json` to every command and parse the single object it prints. Act only on a report's
   `next`.
3. Start offline: `lint`, then `rehearse` a strategy on the practice pod before spending battery
   and floor time.
4. For people at the robot, the GUI (`py -3.12 tools/slothtune gui`) has the same tools with
   lessons; `docs/SWERVE_TUNING_GUIDE.md` is the student guide.
5. Connection trouble on a laptop with a VPN: `pwsh -File tools/robot_preflight.ps1 -Team 1745`.
6. **Units.** Run data, a report's numeric fields, NetworkTables values, `--arg` keys and config
   files are SI (meters, m/s, radians, kilograms, newton-meters): keep them that way in commands
   and files. Everything you say to a person is in the team's units: ft/s (never "fps"), inches,
   pounds, foot-pounds, degrees. Gains stay in the code's units.
   `env --space/--side` and `analyze --tape-forward` take inches. The brief's **Units** section has the conversion factors.

Other references: `docs/CONTROLS_REVIEW.md` (what is known to be wrong in both configs),
`docs/VISION_LUMA_PHOTONVISION.md`, `docs/MIGRATION_2027.md`.
