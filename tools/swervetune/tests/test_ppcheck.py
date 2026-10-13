"""PathPlanner against the code, on the real robots and on copies with problems planted."""

import json
import os
import shutil
import tempfile
import unittest

from swervetune import ppcheck as P, yagslcfg as Y

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PEA = os.path.join(REPO, "Peashooter")
BLACK = os.path.join(REPO, "Black team")


def titles(r):
    return " | ".join(f["title"] for f in r["findings"])


class RealRobotsTest(unittest.TestCase):
    def test_peashooter_today(self):
        # Made to match on this branch (decision 15); mass and MOI wait for measurement.
        r = P.check(Y.Project(PEA))
        rows = {x["key"]: x for x in r["rows"]}
        self.assertEqual({k for k, x in rows.items() if x["status"] != "ok"}, {"robotMass", "robotMOI"})
        self.assertEqual(rows["driveMotorType"]["code"], "vortex", "Vortex on SPARK Flex")
        self.assertEqual(rows["maxDriveSpeed"]["code"], 3.9, "the code's MAX_SPEED")
        self.assertEqual(rows["wheelCOF"]["status"], "ok", "1.2 against 1.19 is within tolerance")
        self.assertEqual(r["fixes"], [])
        self.assertIn("Named command 'Shoot B' is used by auto 'Kishores Auto' but the code never registers it",
                      titles(r))
        self.assertNotIn("loads auto 'W auto'", titles(r), "Robot.java's auto exists")

    def test_black_team_has_no_pathplanner(self):
        r = P.check(Y.Project(BLACK))
        self.assertFalse(r["used"])
        self.assertEqual(r["findings"], [])


class PlantedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "robot")
        shutil.copytree(PEA, self.dir, ignore=shutil.ignore_patterns("build", ".gradle", "bin"))
        self.pp = os.path.join(self.dir, "src", "main", "deploy", "pathplanner")

    def tearDown(self):
        self.tmp.cleanup()

    def edit_json(self, rel, fn):
        p = os.path.join(self.pp, rel)
        d = json.load(open(p, encoding="utf-8"))
        fn(d)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=2)

    def test_the_fix_makes_the_model_match_and_touches_nothing_else(self):
        p = Y.Project(self.dir)
        before = open(P.settings_path(p), encoding="utf-8").read()
        path, text = P.fixed_text(p, P.check(p)["fixes"])
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        r = P.check(Y.Project(self.dir))
        self.assertEqual([x["key"] for x in r["rows"] if x["status"] in ("differs", "missing")], [])
        new = json.loads(text)
        old = json.loads(before)
        for k in ("defaultMaxVel", "robotWidth", "robotFeatures", "robotMass"):
            self.assertEqual(new[k], old[k], f"{k} is not the fix's business")
        self.assertEqual(new["flModuleX"], 0.3048)

    def test_a_weighed_and_measured_robot_is_compared_and_fixed(self):
        tune = os.path.join(self.dir, "src", "main", "deploy", "swerve", "swervetune.json")
        text = open(tune, encoding="utf-8").read()
        text = Y.json_set(Y.json_set(text, ("robotMassKg",), 52.5), ("robotMoiKgM2",), 5.1)
        open(tune, "w", encoding="utf-8").write(text)
        p = Y.Project(self.dir)
        rows = {x["key"]: x for x in P.check(p)["rows"]}
        self.assertEqual((rows["robotMass"]["status"], rows["robotMass"]["code"]), ("differs", 52.5))
        self.assertIn(("robotMOI", 5.1), P.check(p)["fixes"])

    def test_names_that_dont_line_up(self):
        def missing_path(d):
            d["command"]["data"]["commands"].append({"type": "path", "data": {"pathName": "gone path"}})
        self.edit_json("autos/Hub unload.auto", missing_path)
        robot = os.path.join(self.dir, "src", "main", "java", "frc", "robot", "Robot.java")
        src = open(robot, encoding="utf-8").read()
        src = src.replace('NamedCommands.registerCommand("Shoot Hub"', 'NamedCommands.registerCommand("Shoot B", shooter.shootA());\n    NamedCommands.registerCommand("Shoot Hub"')
        src = src.replace('AutoBuilder.buildAuto("W auto")', 'AutoBuilder.buildAuto("W Auto")')
        open(robot, "w", encoding="utf-8").write(src)
        t = titles(P.check(Y.Project(self.dir)))
        self.assertIn("Auto 'Hub unload' uses path 'gone path', which doesn't exist", t)
        self.assertNotIn("'Shoot B'", t.replace("Named command 'Shoot B' is registered", ""), "registered now")
        self.assertIn("The code loads auto 'W Auto', which doesn't exist", t, "names are case-sensitive")

    def test_path_limits_beyond_the_robot(self):
        def fast(d):
            d["useDefaultConstraints"] = False
            d["globalConstraints"].update(maxVelocity=6.0, maxAcceleration=20.0)
        self.edit_json("paths/hub shoot.path", fast)
        r = P.check(Y.Project(self.dir))
        lim = [f["title"] for f in r["findings"] if f["kind"] == "limits"]
        self.assertTrue(any("Path 'hub shoot': speed limit 6" in x for x in lim), lim)
        self.assertTrue(any("Path 'hub shoot': acceleration limit 20" in x for x in lim), lim)

    def test_no_settings_file(self):
        os.remove(os.path.join(self.pp, "settings.json"))
        r = P.check(Y.Project(self.dir))
        self.assertIn("no settings.json", titles(r))


if __name__ == "__main__":
    unittest.main()
