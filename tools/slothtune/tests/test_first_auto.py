"""The first auto after a boot fails and the second works: the code checks that name the causes."""

import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from slothtune import diagnose, yagslcfg as Y
from slothtune.robotrepo import ROBOTS, needs_robots

LATE = """public class Robot extends LoggedRobot {
  private Command autonomousCommand;
  public Robot() {
    drive.setupPathPlanner();
  }
  @Override
  public void autonomousInit() {
    autonomousCommand = AutoBuilder.buildAuto("W auto");
    if (autonomousCommand != null) { autonomousCommand.schedule(); }
  }
}
"""
EARLY = """public class Robot extends LoggedRobot {
  private Command autonomousCommand;
  public Robot() {
    drive.setupPathPlanner();
    autonomousCommand = AutoBuilder.buildAuto("W auto");
    CommandScheduler.getInstance().schedule(FollowPathCommand.warmupCommand());
  }
  @Override
  public void autonomousInit() {
    if (autonomousCommand != null) { CommandScheduler.getInstance().schedule(autonomousCommand); }
  }
}
"""


def project(java, autos=None):
    """Just what the checks read: the Java sources and the PathPlanner autos folder."""
    d = tempfile.mkdtemp()
    a = os.path.join(d, "src", "main", "deploy", "pathplanner", "autos")
    os.makedirs(a)
    for name, reset in (autos or {}).items():
        with open(os.path.join(a, name + ".auto"), "w", encoding="utf-8") as fh:
            json.dump({"version": "2025.0", "command": {"type": "sequential", "data": {"commands": []}},
                       "resetOdom": reset}, fh)
    return SimpleNamespace(path=d, java=java)


def ids(findings):
    return sorted(f["id"] for f in findings)


class FirstAutoTest(unittest.TestCase):
    def test_an_auto_built_when_auto_starts_and_no_warmup(self):
        f = Y.first_auto_findings(project({"src/main/java/frc/robot/Robot.java": LATE}, {"W auto": True}))
        self.assertEqual(ids(f), ["auto_built_late", "pathplanner_no_warmup"])
        late = next(x for x in f if x["id"] == "auto_built_late")
        self.assertIn("Robot.java", late["title"])
        self.assertEqual(late["fix"]["file"], "src/main/java/frc/robot/Robot.java")

    def test_built_at_startup_with_the_warmup_is_clean(self):
        self.assertEqual(Y.first_auto_findings(project({"Robot.java": EARLY}, {"W auto": True})), [])

    def test_an_auto_that_doesnt_reset_odometry_is_named(self):
        f = Y.first_auto_findings(project({"Robot.java": EARLY}, {"W auto": True, "Side auto": False}))
        self.assertEqual(ids(f), ["auto_no_reset_odom"])
        self.assertIn('"Side auto"', f[0]["title"])

    def test_code_without_pathplanner_says_nothing(self):
        self.assertEqual(Y.first_auto_findings(project({"Robot.java": "public class Robot {}"})), [])

    def test_the_symptom_reads_the_three_checks(self):
        sym = diagnose.BY_ID["auto_first_run"]
        lints = [lid for c in sym["checks"] for lid in (c.get("auto") or {}).get("lint", [])]
        self.assertEqual(lints, ["auto_built_late", "pathplanner_no_warmup", "auto_no_reset_odom"])
        self.assertIn("autos", diagnose.groups("auto_first_run")["devices"])

    @needs_robots
    def test_peashooter_builds_its_auto_at_boot_and_warms_up(self):
        f = Y.first_auto_findings(Y.Project(os.path.join(ROBOTS, "Peashooter")))
        self.assertEqual(f, [], [x["title"] for x in f])


if __name__ == "__main__":
    unittest.main()
