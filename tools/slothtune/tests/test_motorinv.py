"""What each motor and controller is: from the code, from the robot, by hand and by measurement."""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from slothtune import advisor, motorinv as M, plant, yagslcfg as Y
from slothtune.robotrepo import ROBOTS, needs_robots

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PEA = os.path.join(ROBOTS, "Peashooter")
BLACK = os.path.join(ROBOTS, "Black team")


def rows(r):
    return {x["name"]: x for x in r["rows"]}


def titles(r):
    return " | ".join(f["title"] for f in r["findings"])


class RealRobotsTest(unittest.TestCase):
    @needs_robots
    def test_peashooter_every_motor_is_named(self):
        r = M.table(Y.Project(PEA))
        x = rows(r)
        self.assertEqual(r["findings"], [])
        self.assertEqual(x["frontleft drive"]["code_controller"], "SPARK Flex")
        self.assertEqual(x["frontleft drive"]["motor"], "NEO Vortex")
        self.assertEqual(x["frontleft drive"]["key"], "drive")
        self.assertEqual(x["backright steer"]["code_controller"], "SPARK MAX")
        self.assertEqual(x["backright steer"]["motor"], "NEO 550")
        self.assertEqual(x["Spindexter"]["motor"], "NEO 2.0", "from Feeder.java's watch() call")
        self.assertEqual(x["Spindexter"]["motor_source"], "Feeder.java watch()")
        self.assertEqual(x["Shooter leader"]["motor"], "NEO Vortex")
        self.assertTrue(all(v["status"] == "ok" for v in x.values()))
        self.assertEqual(r["choices"], list(M.CHOICES))

    @needs_robots
    def test_black_team_every_motor_is_named(self):
        r = M.table(Y.Project(BLACK))
        x = rows(r)
        self.assertEqual(r["findings"], [])
        self.assertEqual(x["frontright drive"]["motor"], "NEO Vortex")
        self.assertEqual([v["motor"] for k, v in x.items() if k.startswith(("Intake", "Shooter"))],
                         ["NEO 2.0"] * sum(1 for k in x if k.startswith(("Intake", "Shooter"))))


class RobotReportsTest(unittest.TestCase):
    @needs_robots
    def test_a_controller_that_is_not_what_the_code_creates(self):
        live = [{"name": "frontleft drive", "controller": "SPARK MAX", "firmware": "25.1.0"},
                {"name": "frontright drive", "controller": "SPARK Flex", "firmware": "25.1.0"}]
        r = M.table(Y.Project(PEA), live)
        x = rows(r)
        self.assertEqual(x["frontleft drive"]["status"], "bad")
        self.assertEqual(x["frontleft drive"]["controller"], "SPARK MAX")
        self.assertEqual(x["frontright drive"]["status"], "ok")
        self.assertEqual(x["frontright drive"]["firmware"], "25.1.0")
        self.assertIn("frontleft drive (CAN 5) is a SPARK MAX, but the code creates a SPARK Flex", titles(r))
        self.assertIn("the YAGSL type starts sparkmax_", r["findings"][0]["why"])
        self.assertIn("Vortex on a SPARK MAX", titles(r), "fine only with a Solo Adapter")

    @needs_robots
    def test_a_controller_that_cannot_say_is_no_finding(self):
        r = M.table(Y.Project(PEA), [{"name": "frontleft drive", "controller": ""}])
        self.assertEqual(r["findings"], [])

    @needs_robots
    def test_a_subsystem_controller_names_the_class_to_create(self):
        r = M.table(Y.Project(PEA), [{"name": "Spindexter", "controller": "SPARK Flex"}])
        self.assertIn("Fix it in Feeder.java: new SparkMax(...) becomes new SparkFlex(...).", r["findings"][0]["why"])

    @needs_robots
    def test_the_motor_guard_names_a_motor_nothing_else_does(self):
        # When the code's watch() call can't be read, only the robot's guard knows the motor.
        with mock.patch.object(M, "code_kinds", return_value={}):
            r = M.table(Y.Project(PEA), [{"name": "Spindexter", "kind": "NEO V1.1"}])
        self.assertEqual(rows(r)["Spindexter"]["motor"], "NEO V1.1")
        self.assertEqual(rows(r)["Spindexter"]["motor_source"], "the robot's motor guard")


class PlantedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "robot")
        shutil.copytree(PEA, self.dir, ignore=shutil.ignore_patterns("build", ".gradle", "bin"))
        self.swerve = os.path.join(self.dir, "src", "main", "deploy", "swerve")

    def tearDown(self):
        self.tmp.cleanup()

    def edit_json(self, rel, fn):
        p = os.path.join(self.swerve, rel)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        fn(d)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)

    @needs_robots
    def test_the_inventory_disagrees_with_the_yagsl_type(self):
        self.edit_json("slothtune.json", lambda d: d["motors"].update(drive="NEO V1.1"))
        r = M.table(Y.Project(self.dir))
        x = rows(r)
        self.assertEqual(x["frontleft drive"]["motor"], "NEO V1.1", "a person's word comes first")
        self.assertEqual(x["frontleft drive"]["status"], "bad")
        self.assertIn("frontleft drive: YAGSL models a NEO Vortex, the motor inventory says NEO V1.1", titles(r))

    @needs_robots
    def test_one_motor_named_by_its_full_name_wins_over_its_group(self):
        self.edit_json("slothtune.json", lambda d: d["motors"].update({"backleft drive": "NEO 2.0"}))
        x = rows(M.table(Y.Project(self.dir)))
        self.assertEqual(x["backleft drive"]["motor"], "NEO 2.0")
        self.assertEqual(x["frontleft drive"]["motor"], "NEO Vortex")

    @needs_robots
    def test_a_motor_nobody_names(self):
        def plant_(d):
            d["angle"]["type"] = "sparkmax"
        for m in ("frontleft", "frontright", "backleft", "backright"):
            self.edit_json(f"modules/{m}.json", plant_)
        self.edit_json("slothtune.json", lambda d: d["motors"].pop("steer"))
        r = M.table(Y.Project(self.dir))
        x = rows(r)
        self.assertEqual(x["frontleft steer"]["status"], "unknown")
        self.assertEqual(x["frontleft steer"]["motor_source"], "not said anywhere")
        self.assertIn("Motor not named: frontleft steer, frontright steer", titles(r))

    @needs_robots
    def test_a_drive_ff_that_measures_another_motor(self):
        measured = {"label": "NEO", "kind": "neo", "rpm_per_volt": 446.0}
        r = M.table(Y.Project(self.dir), measured=measured)
        x = rows(r)
        self.assertEqual(x["frontleft drive"]["measured"], "NEO")
        self.assertEqual(x["frontleft drive"]["status"], "bad")
        self.assertEqual(x["frontleft steer"]["measured"], None, "drive_ff measures only the drive motors")
        self.assertIn("The drive motors measure as NEOs (446 rpm per volt)", titles(r))

    def fix(self, r, label):
        return next(f for f in r["findings"] if f["title"].startswith(f"Set the swerve {label} motors' YAGSL type"))

    @needs_robots
    def test_a_measured_motor_gets_a_one_click_fix_for_every_module_file(self):
        measured = {"label": "NEO", "kind": "neo", "rpm_per_volt": 446.0}
        f = self.fix(M.table(Y.Project(self.dir), measured=measured), "drive")
        self.assertEqual(f["title"], "Set the swerve drive motors' YAGSL type to sparkflex_neo")
        self.assertEqual([(e["file"], e["path"], e["value"]) for e in f["edits"]],
                         [(f"modules/{m}.json", ["drive", "type"], "sparkflex_neo")
                          for m in ("frontleft", "frontright", "backleft", "backright")])
        self.assertIn("run drive_ff on blocks again", f["why"])
        # The edits are ones a save can write.
        p = Y.Project(self.dir)
        self.assertTrue(all(p.writable(e["file"]) for e in f["edits"]))

    @needs_robots
    def test_the_controller_the_robot_reports_wins_over_the_code(self):
        live = [{"name": f"{m} drive", "controller": "SPARK MAX"} for m in ("frontleft", "frontright", "backleft", "backright")]
        f = self.fix(M.table(Y.Project(self.dir), live), "drive")
        self.assertEqual(f["edits"][0]["value"], "sparkmax_vortex", "a Vortex on a SPARK MAX, as the robot says")
        self.assertIn("the robot reports a SPARK MAX", f["why"])

    @needs_robots
    def test_the_inventory_names_the_motor_when_nothing_measured_it(self):
        self.edit_json("slothtune.json", lambda d: d["motors"].update(drive="NEO V1.1"))
        f = self.fix(M.table(Y.Project(self.dir)), "drive")
        self.assertEqual(f["edits"][0]["value"], "sparkflex_neo")
        self.assertIn("If the inventory is what's wrong", f["why"])

    @needs_robots
    def test_one_module_out_of_step_is_the_only_file_changed(self):
        self.edit_json("modules/backleft.json", lambda d: d["angle"].update(type="sparkmax_neo"))
        f = self.fix(M.table(Y.Project(self.dir)), "steering")
        self.assertEqual([e["file"] for e in f["edits"]], ["modules/backleft.json"])
        self.assertEqual(f["edits"][0]["value"], "sparkmax_neo550")

    @needs_robots
    def test_a_speed_only_a_neo550_reaches_sets_the_steering_type(self):
        for m in ("frontleft", "frontright", "backleft", "backright"):
            self.edit_json(f"modules/{m}.json", lambda d: d["angle"].update(type="sparkmax_neo"))
        self.edit_json("slothtune.json", lambda d: d["motors"].pop("steer"))
        live = [{"name": "frontleft steer", "rpm": 9000}]
        f = self.fix(M.table(Y.Project(self.dir), live), "steering")
        self.assertEqual({e["value"] for e in f["edits"]}, {"sparkmax_neo550"})
        self.assertEqual(len(f["edits"]), 4)

    @needs_robots
    def test_a_drive_ff_that_agrees(self):
        measured = {"label": "NEO Vortex", "kind": "vortex", "rpm_per_volt": 531.0}
        r = M.table(Y.Project(self.dir), measured=measured)
        self.assertEqual(r["findings"], [])
        self.assertEqual(rows(r)["frontleft drive"]["measured"], "NEO Vortex")


class MotorFromKvTest(unittest.TestCase):
    # kV from drive_ff, volts per m/s, for each motor at 94% of its datasheet speed per volt, on
    # 5.50:1 and 3 inch wheels: 60 * 5.5 / (rpm_per_volt * pi * 0.0762).
    def kv(self, rpm_per_volt):
        import math
        return 60 * 5.5 / (rpm_per_volt * math.pi * 3 * 0.0254)

    def test_each_rev_motor_is_told_apart(self):
        for rpm, kind in ((5676, "neo"), (6784, "vortex"), (11000, "neo550")):
            rpv, best, _ = advisor.motor_from_kv(self.kv(rpm / 12 * 0.94), 5.5, 3.0)
            self.assertEqual(best, kind)
            self.assertAlmostEqual(rpv, rpm / 12 * 0.94, places=6)

    def test_the_practice_pods_neo_reads_as_a_neo(self):
        truth = plant.true_drive_feedforward()
        _, best, _ = advisor.motor_from_kv(truth["kV"], 5.5, 3.0)
        self.assertEqual(best, "neo")

    def test_the_config_named_the_wrong_motor(self):
        ctx = {"drive_gear": 5.5, "wheel_d_in": 3.0, "drive_kind": "neo"}
        f, ident = advisor.motor_identity_findings([self.kv(531)] * 4, ctx)
        self.assertEqual(ident["kind"], "vortex")
        self.assertEqual(f[0]["level"], "error")
        self.assertIn("The config says NEO, but the drive motors spin like NEO Vortexs", f[0]["title"])

    def test_as_configured(self):
        ctx = {"drive_gear": 5.5, "wheel_d_in": 3.0, "drive_kind": "vortex"}
        f, ident = advisor.motor_identity_findings([self.kv(531)] * 4, ctx)
        self.assertEqual(f[0]["level"], "info")
        self.assertEqual(ident["label"], "NEO Vortex")

    def test_like_no_rev_motor(self):
        ctx = {"drive_gear": 5.5, "wheel_d_in": 3.0, "drive_kind": "vortex"}
        f, _ = advisor.motor_identity_findings([self.kv(300)] * 4, ctx)
        self.assertEqual(f[0]["level"], "warn")
        self.assertIn("like no REV motor", f[0]["title"])

    def test_nothing_without_the_gearing(self):
        self.assertEqual(advisor.motor_identity_findings([2.6], {"drive_kind": "vortex"}), ([], None))


if __name__ == "__main__":
    unittest.main()
