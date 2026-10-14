"""Designs checked against Peashooter's real code, files and a made-up match log."""

import json
import os
import unittest
from urllib.parse import quote

from slothtune import designcheck as K, logsummary, motorinv, yagslcfg as Y

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PEA = Y.Project(os.path.join(REPO, "Peashooter"))
SHOOTER = ["Shooter leader", "Shooter follower"]


def recalc(page, **fields):
    q = "&".join(f"{k}={quote(json.dumps(v) if not isinstance(v, str) else v)}" for k, v in fields.items())
    return f"https://www.reca.lc/{page}?{q}"


def titles(F):
    return " | ".join(f["title"] for f in F)


class MechanismTest(unittest.TestCase):
    def test_the_shooter_asks_a_vortex_for_more_than_it_has(self):
        url = recalc("flywheel", motor={"name": "NEO Vortex", "quantity": 2},
                     ratio={"magnitude": 1, "ratioType": "Reduction"}, statorLimit={"s": 80, "u": "A"})
        out = K.evaluate(url, PEA, SHOOTER)
        F = out["findings"]
        self.assertIn("The code asks for 9999 rpm; a NEO Vortex turns at most 6784 rpm", titles(F))
        self.assertNotIn("isn't a REV motor", titles(F))
        self.assertNotIn("motors are attached", titles(F), "2 motors in the design, 2 attached")

    def test_a_design_for_another_motor_is_an_error(self):
        url = recalc("flywheel", motor={"name": "NEO 550", "quantity": 2}, ratio={"magnitude": 1, "ratioType": "Reduction"})
        F = K.evaluate(url, PEA, SHOOTER)["findings"]
        self.assertTrue(any(f["level"] == "error" and "The design is for a NEO 550" in f["title"] for f in F), titles(F))

    def test_a_design_over_the_teams_current_policy(self):
        url = recalc("arm", motor={"name": "NEO 550", "quantity": 1}, ratio={"magnitude": 100, "ratioType": "Reduction"},
                     statorLimit={"s": 80, "u": "A"}, armLength={"s": 10, "u": "in"}, load={"s": 2, "u": "lbs"})
        F = K.evaluate(url, PEA, ["Intake pivot"])["findings"]
        self.assertIn("The design assumes 80 A; the team limits a NEO 550 to 20 A", titles(F))

    def test_an_arm_that_cant_hold_its_load_level(self):
        url = recalc("arm", motor={"name": "NEO 550", "quantity": 1}, ratio={"magnitude": 5, "ratioType": "Reduction"},
                     statorLimit={"s": 20, "u": "A"}, armLength={"s": 24, "u": "in"}, load={"s": 10, "u": "lbs"})
        F = K.evaluate(url, PEA, ["Intake pivot"])["findings"]
        self.assertTrue(any(f["level"] == "error" and "holding the arm out level" in f["title"] for f in F), titles(F))

    def test_the_wrong_number_of_motors(self):
        url = recalc("flywheel", motor={"name": "NEO Vortex", "quantity": 1}, ratio={"magnitude": 1, "ratioType": "Reduction"})
        F = K.evaluate(url, PEA, SHOOTER)["findings"]
        self.assertIn("The design has 1 motor; 2 are attached", titles(F))

    def test_suggested_motors_follow_the_mechanisms_name(self):
        inv = motorinv.table(PEA)
        url = recalc("flywheel", motor={"name": "NEO Vortex", "quantity": 2})
        from slothtune import designlinks as D
        self.assertEqual(K.suggest_motors(D.parse(url), inv, "Shooter"), SHOOTER)
        self.assertEqual(K.default_name(D.parse(url)), "Shooter", "a flywheel is a shooter until named")
        self.assertEqual(K.suggest_motors(D.parse(url), inv, "Catapult"), [], "no guess by motor type alone")


class LogTest(unittest.TestCase):
    def series(self, rpm, volts, amps, n=200):
        b = "/RealOutputs/Motors/Shooter leader/"
        t = [i * 0.02 for i in range(n)]
        return {b + "Rpm": [(x, rpm) for x in t], b + "AppliedVolts": [(x, volts) for x in t],
                b + "Amps": [(x, amps) for x in t], b + "LimitA": [(x, 80) for x in t]}

    def test_speed_per_volt_tells_the_motors_apart(self):
        s = logsummary.motor_stats(self.series(5650, 10.0, 4.0))
        self.assertAlmostEqual(s["Shooter leader"]["rpm_per_volt"], 565)
        self.assertEqual(s["Shooter leader"]["peak_rpm"], 5650)

    def test_a_match_log_overrules_the_design(self):
        stats = logsummary.motor_stats(self.series(4730, 10.0, 4.0))  # 473 rpm/V: a NEO
        url = recalc("flywheel", motor={"name": "NEO Vortex", "quantity": 2})
        F = K.evaluate(url, PEA, SHOOTER, stats=stats)["findings"]
        self.assertIn("Shooter leader turns like a NEO V1.1 (473 rpm per volt)", titles(F))

    def test_time_at_the_current_limit(self):
        stats = logsummary.motor_stats(self.series(1000, 6.0, 79.0))
        self.assertEqual(stats["Shooter leader"]["at_limit_frac"], 1.0)
        self.assertIsNone(stats["Shooter leader"]["rpm_per_volt"], "never running free")


class DrivetrainTest(unittest.TestCase):
    def test_a_design_for_another_module_and_wheel(self):
        url = ("https://ambcalc.com/drivetrain?=&motor=Kraken+X60+FOC&ilim=60&weight=135&g1a=14&g1b=50&g2a=27&g2b=17"
               "&g3a=15&g3b=45&wheel_diam=101.6&wheel_diam-u=0.001")
        out = K.evaluate(url, PEA)
        t = titles(out["findings"])
        self.assertIn("aren't REV's", t)
        self.assertIn("isn't a MAXSwerve ratio", t)
        self.assertIn("The design's wheel is 4 in; YAGSL has 3 in", t)
        self.assertFalse(any(e["path"][-1] == "gearRatio" for e in out["edits"]), "never copies a ratio REV doesn't sell")

    def test_a_maxswerve_design_fills_in_the_gearing_but_never_the_current_limit(self):
        url = recalc("drive", motor={"name": "NEO Vortex", "quantity": 4}, ratio={"magnitude": 5.08, "ratioType": "Reduction"},
                     wheelDiameter={"s": 3, "u": "in"}, motorCurrentLimit={"s": 60, "u": "A"})
        out = K.evaluate(url, PEA)
        self.assertIn({"file": "modules/physicalproperties.json", "path": ["conversionFactors", "drive", "gearRatio"],
                       "value": 5.08, "label": "Drive gear ratio 5.5 → 5.08"}, out["edits"])
        self.assertFalse(any("currentLimit" in e["path"] for e in out["edits"]), "the slip test owns the drive limit")
        self.assertIn("the files have 40 A", titles(out["findings"]))


class AgainstTheCodeTest(unittest.TestCase):
    """R39: the design against what the subsystem's code does (Peashooter's Intake.java, Shooter.java)."""

    def test_the_pivots_targets_against_the_arms_range(self):
        arm = dict(motor={"name": "NEO Vortex", "quantity": 1}, statorLimit={"s": 40, "u": "A"},
                   minAngle={"s": 0, "u": "deg"}, maxAngle={"s": 110, "u": "deg"},
                   armLength={"s": 10, "u": "in"}, load={"s": 2, "u": "lbs"})
        F = K.evaluate(recalc("arm", ratio={"magnitude": 60, "ratioType": "Reduction"}, **arm), PEA, ["Intake pivot"])["findings"]
        self.assertIn("The code's targets fit the design's range: 107° of 110°", titles(F), "0 to 17.8 motor turns at 60:1")
        self.assertIn("The code sets no current limit for Intake pivot; the design assumes 40 A", titles(F))
        F = K.evaluate(recalc("arm", ratio={"magnitude": 45, "ratioType": "Reduction"}, **arm), PEA, ["Intake pivot"])["findings"]
        self.assertIn("The code moves it 142°; the design covers 110°", titles(F))

    def test_the_shooters_speeds_against_the_designs_target(self):
        url = recalc("flywheel", motor={"name": "NEO Vortex", "quantity": 2}, ratio={"magnitude": 1, "ratioType": "Reduction"},
                     statorLimit={"s": 80, "u": "A"}, shooterTargetSpeed={"s": 2000, "u": "rpm"})
        self.assertIn("None of the code's speeds is the design's 2000 rpm", titles(K.evaluate(url, PEA, SHOOTER)["findings"]))
        url = url.replace("2000", "4000")
        self.assertNotIn("None of the code's speeds", titles(K.evaluate(url, PEA, SHOOTER)["findings"]), "3950 is within 15%")

    def test_what_counts_as_a_position(self):
        src = """ControlType.kPosition; static final double ARM_STOW_POSITION = -2.5; static final double POSITION_TOLERANCE = 0.5;
                 pid.setSetpoint(12.0, ControlType.kPosition);"""
        self.assertEqual(K.position_setpoints(src), [-2.5, 12.0], "the tolerance isn't a place to go")
        self.assertEqual(K.position_setpoints("ARM_POSITION = 3.0;"), [], "no position control: not a target")
        self.assertEqual(K.code_current_limits("cfg.smartCurrentLimit(40); other.smartCurrentLimit( 60 )"), [40, 60])


if __name__ == "__main__":
    unittest.main()
