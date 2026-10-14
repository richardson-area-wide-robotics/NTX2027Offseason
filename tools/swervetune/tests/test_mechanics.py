"""A mechanism's physics from a ReCalc link, and the safe test that follows (mechanics.py)."""

import json
import math
import unittest
from urllib.parse import urlencode

from swervetune import mechanics as M


def recalc(page, **params):
    """A ReCalc share link as reca.lc writes one: every value JSON in the query."""
    return f"https://www.reca.lc/{page}?" + urlencode({k: json.dumps(v) if not isinstance(v, str) else v for k, v in params.items()})


ARM = recalc("arm", motor={"name": "NEO Vortex", "quantity": 1}, ratio={"magnitude": 50, "ratioType": "Reduction"},
             armLength={"s": 0.5, "u": "m"}, load={"s": 5, "u": "kg"}, minAngle={"s": 0, "u": "deg"},
             maxAngle={"s": 90, "u": "deg"})


class RecalcTest(unittest.TestCase):
    def test_an_arm_link_reads_in_si(self):
        a = M.from_recalc(ARM)
        self.assertEqual((a["kind"], a["motor"], a["count"], a["ratio"]), ("pivot", "NEO Vortex", 1, 50.0))
        self.assertAlmostEqual(a["arm_length_m"], 0.5)
        self.assertAlmostEqual(a["max_angle_rad"], math.pi / 2)

    def test_units_and_a_step_up_ratio(self):
        f = M.from_recalc(recalc("flywheel", motor={"name": "Kraken X60", "quantity": 2},
                                 ratio={"magnitude": 2, "ratioType": "Step-up"},
                                 shooterDiameter={"s": 4, "u": "in"}, shooterWeight={"s": 1, "u": "lb"},
                                 shooterTargetSpeed={"s": 3000, "u": "rpm"}))
        self.assertEqual((f["kind"], f["count"], f["ratio"]), ("flywheel", 2, 0.5))
        self.assertAlmostEqual(f["moi_kgm2"], 0.45359237 * (2 * 0.0254) ** 2 / 2, "ReCalc's m r^2 / 2")
        self.assertAlmostEqual(f["target_rad_s"], 3000 * 2 * math.pi / 60)

    def test_what_it_refuses(self):
        with self.assertRaises(ValueError):
            M.from_recalc("https://example.com/arm?x=1")
        with self.assertRaises(ValueError):
            M.from_recalc(recalc("arm", motor={"name": "Mystery motor", "quantity": 1}, ratio={"magnitude": 5, "ratioType": "Reduction"}))


class PhysicsTest(unittest.TestCase):
    def test_an_arm_as_wpilib_models_it(self):
        a = M.from_recalc(ARM)
        ff = M.feedforward(a)
        # WPILib's SingleJointedArmFromPhysicalConstants: A11 = -G^2 Kt / (Kv R J), B10 = G Kt / (R J).
        r, kv, kt, free = M.dc_motor("NEO Vortex", 1)
        j = 5 * 0.5 ** 2
        a11, b10 = -50 ** 2 * kt / (kv * r * j), 50 * kt / (r * j)
        self.assertAlmostEqual(ff["kV"], -a11 / b10)
        self.assertAlmostEqual(ff["kA"], 1 / b10)
        # kG: the volts that hold it level, from torque: m g L = Kt I G, V = I R.
        self.assertAlmostEqual(ff["kG"], 5 * 9.80665 * 0.5 / (kt * 50) * r)
        self.assertAlmostEqual(ff["free_speed"], free / 50)

    def test_a_direct_drive_flywheel_needs_about_its_motor_voltage_per_free_speed(self):
        f = {"kind": "flywheel", "motor": "NEO Vortex", "count": 1, "ratio": 1.0, "moi_kgm2": 0.001}
        ff = M.feedforward(f)
        self.assertAlmostEqual(ff["kV"], 12 / (6825 * 2 * math.pi / 60), delta=0.001)
        self.assertEqual(ff["kG"], 0.0)

    def test_more_motors_less_volts_to_accelerate(self):
        one = M.feedforward({"kind": "flywheel", "motor": "NEO", "count": 1, "ratio": 1.0, "moi_kgm2": 0.002})
        two = M.feedforward({"kind": "flywheel", "motor": "NEO", "count": 2, "ratio": 1.0, "moi_kgm2": 0.002})
        self.assertAlmostEqual(two["kA"], one["kA"] / 2)


class PlanTest(unittest.TestCase):
    def test_a_pivot_test_stays_slow_and_inside(self):
        a = M.from_recalc(ARM)
        # Its position in motor rotations: 50 per mechanism turn, so 50 / 2 pi per radian.
        k = 50 / (2 * math.pi)
        p = M.test_plan(a, (0.0, 12.5), k)
        free = M.feedforward(a)["free_speed"] * k
        self.assertAlmostEqual(p["vmax"], 0.25 * free)
        self.assertAlmostEqual((p["a"], p["b"]), (3.75, 8.75))
        self.assertLess(p["amax"], (12 / M.feedforward(a)["kA"]) * k)
        capped = M.test_plan(a, (0.0, 12.5), k, team_max_velocity=1.0)
        self.assertEqual(capped["vmax"], 1.0, "never above the team's maximum")

    def test_a_flywheel_test_tops_out_at_its_target(self):
        f = {"kind": "flywheel", "motor": "NEO Vortex", "count": 2, "ratio": 1.0, "moi_kgm2": 0.002,
             "target_rad_s": 3000 * 2 * math.pi / 60}
        rpm_per_rad_s = 60 / (2 * math.pi)
        p = M.test_plan(f, None, rpm_per_rad_s)
        self.assertAlmostEqual(p["b"], 3000, msg="a flywheel at its shooting speed is just working")
        self.assertAlmostEqual(p["a"], 1500)
        self.assertEqual(M.test_plan(f, None, rpm_per_rad_s, team_max_velocity=2500)["b"], 2500)


if __name__ == "__main__":
    unittest.main()
