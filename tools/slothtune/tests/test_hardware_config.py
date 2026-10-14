"""The hardware and config checks from the second gap check: a design's default mass, setpoints a
motor can't reach, the modules agreeing with each other, and names kept unregistered on purpose."""

import copy
import os
import unittest

from slothtune import designcheck as K, designlinks as D, ppcheck, yagslcfg as Y

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
AMB = ("https://ambcalc.com/drivetrain?=&motor=NEO+Vortex&ilim=60&g1a=14&g1b=50&g2a=27&g2b=17"
       "&g3a=15&g3b=45&wheel_diam=76.2&wheel_diam-u=0.001")


def pea():
    return Y.Project(os.path.join(REPO, "Peashooter"))


def ids(F):
    return [f["id"] for f in F]


class DesignMassTest(unittest.TestCase):
    def test_a_link_without_a_weight_marks_the_calculators_default_as_assumed(self):
        d = D.parse(AMB)
        self.assertIn("mass_kg", d["assumed"])
        self.assertIn("cof", d["assumed"])
        self.assertNotIn("wheel_diameter_m", d["assumed"])

    def test_a_design_never_writes_the_robots_mass(self):
        for url in (AMB, AMB + "&weight=120"):
            out = K.evaluate(url, pea())
            self.assertFalse(any(e["path"] == ["robotMassKg"] for e in out["edits"]), url)
        t = " | ".join(f["title"] for f in K.evaluate(AMB, pea())["findings"])
        self.assertIn("doesn't set the robot's weight", t)

    def test_a_saved_design_with_a_weight_stands_in_until_the_robot_is_weighed(self):
        p = pea()
        p.data["slothtune.json"] = dict(p.data["slothtune.json"], robotMassKg=None,
                                         designs={"Drivetrain": {"url": AMB + "&weight=120"}})
        p.pp = {}
        mass, src = p.mass()
        self.assertAlmostEqual(mass, round(120 * 0.453592, 1))
        self.assertIn("assumed", src)
        self.assertIn("design", src)
        p.data["slothtune.json"]["designs"] = {"Drivetrain": {"url": AMB}}  # the calculator's 154 lb: not used
        self.assertNotIn("design", p.mass()[1])


class LintTest(unittest.TestCase):
    def test_a_setpoint_past_free_speed_is_an_error(self):
        F = [f for f in Y.lint(pea()) if f["id"] == "setpoint_unreachable"]
        self.assertEqual(len(F), 1)
        self.assertIn("9999 rpm", F[0]["title"])
        self.assertIn("6784", F[0]["title"])

    def test_modules_with_different_motors_offsets_out_of_a_turn_and_a_ratio_rev_doesnt_sell(self):
        p = pea()
        names = p.module_names()
        bad = copy.deepcopy(p.data["modules/" + names[0] + ".json"] if not names[0].endswith(".json") else p.data["modules/" + names[0]])
        bad["drive"]["type"] = "sparkmax_neo"
        bad["absoluteEncoderOffset"] = -15.0
        key = "modules/" + (names[0] if names[0].endswith(".json") else names[0] + ".json")
        p.data[key] = bad
        p.phys["conversionFactors"]["drive"]["gearRatio"] = 5.9
        got = ids(Y.lint(p))
        self.assertIn("modules_mixed_drive_types", got)
        self.assertIn("offset_out_of_range", got)
        self.assertIn("drive_ratio_not_sold", got)

    def test_the_real_robots_pass_the_module_checks(self):
        for robot in ("Peashooter", "Black team"):
            got = ids(Y.lint(Y.Project(os.path.join(REPO, robot))))
            for x in ("modules_mixed_drive_types", "modules_mixed_angle_types", "offset_out_of_range", "drive_ratio_not_sold"):
                self.assertNotIn(x, got, robot)


class KnownUnregisteredTest(unittest.TestCase):
    def test_shoot_b_is_a_warning_not_an_error(self):
        F = [f for f in ppcheck.check(pea())["findings"] if f["kind"] == "names" and "never registers" in f["title"]]
        self.assertTrue(F)
        self.assertTrue(all(f["level"] == "warn" for f in F), F)
        self.assertIn("kept on purpose", F[0]["title"])

    def test_without_the_list_it_is_an_error(self):
        p = pea()
        p.data["slothtune.json"] = {k: v for k, v in p.data["slothtune.json"].items() if k != "pathplanner"}
        F = [f for f in ppcheck.check(p)["findings"] if f["kind"] == "names" and "never registers" in f["title"]]
        self.assertTrue(F and all(f["level"] == "error" for f in F))


class CanIdTest(unittest.TestCase):
    def test_a_constant_can_id_is_resolved(self):
        p = Y.Project(os.path.join(REPO, "Black team"))
        users = [u for us in p.can_ids().values() for u in us]
        self.assertTrue(any(u.startswith("Intake.java") for u in users), users)

    def test_a_duplicate_through_a_constant_is_an_error(self):
        p = pea()
        p.java = dict(p.java)
        p.java["src/main/java/frc/robot/Extra.java"] = (
            "class Extra { static final int ROLLER_ID = %d; SparkMax m = new SparkMax(ROLLER_ID, MotorType.kBrushless); }"
            % int(p.module(p.module_names()[0])["drive"]["id"]))
        self.assertIn("can_duplicate", ids(Y.lint(p)))



class GyroSignTest(unittest.TestCase):
    """The 2026 runbook's hand-turned gyro check: counter-clockwise by hand must read positive."""

    def _cap(self, heading):
        return {"channels": {"t": [i * 0.02 for i in range(len(heading))], "heading": heading}}

    def test_counter_clockwise_reads_positive(self):
        from slothtune import advisor
        up = [i * 1.0 for i in range(100)]
        self.assertEqual(advisor.hand_check(self._cap(up), "gyro")["gyro"]["heading"]["verdict"], "AGREES")
        down = [-i * 1.0 for i in range(100)]
        self.assertEqual(advisor.hand_check(self._cap(down), "gyro")["gyro"]["heading"]["verdict"], "INVERTED")
        self.assertEqual(advisor.hand_check(self._cap([0.0] * 100), "gyro")["gyro"]["heading"]["verdict"], "NO_MOTION")

    def test_an_inverted_gyro_gets_the_one_setting_that_flips_it(self):
        from unittest import mock
        from slothtune import server
        with mock.patch.object(server.S, "project", pea()), \
                mock.patch.object(server.runs, "load", return_value=self._cap([-i * 1.0 for i in range(100)])):
            out = server.api_handcheck({"file": "x", "kind": "gyro"})
        self.assertEqual(out["gyro"]["fix"], {"file": "swervedrive.json", "path": ["invertedIMU"], "value": True})


if __name__ == "__main__":
    unittest.main()
