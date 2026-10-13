"""The practice pod drives with the robots' real motor (a Vortex), and the advice works for it."""

import tempfile
import unittest
from unittest import mock

from swervetune import advisor, plant, rehearse, runs


START = {"Drive/kP": 0.0005, "Drive/kI": 0.0, "Drive/kD": 0.0, "Drive/RampS": 0.0,
         "Drive/VelPeriodMs": 0, "Drive/VelDepth": 0}


class PodMotorTest(unittest.TestCase):
    def test_a_vortex_pod_reads_speed_like_a_vortex_on_a_flex(self):
        v, n = plant.DriveModule(motor="vortex"), plant.DriveModule()
        self.assertEqual((v.COUNTS_PER_REV, v.meas_period_ms, v.meas_depth), (7168, 10, 2))
        self.assertEqual((n.COUNTS_PER_REV, n.meas_period_ms, n.meas_depth), (42, 32, 8))

    def test_yagsls_default_kv_per_motor(self):
        self.assertAlmostEqual(plant.nominal_kv("neo"), 2.915, places=2)
        self.assertAlmostEqual(plant.nominal_kv("vortex"), 12 / 4.92, delta=0.01)

    def test_a_vortex_pods_feedforward_names_a_vortex(self):
        ch = plant.drive_ff(surface="floor", motor="vortex")
        doc = {"test": "drive_ff", "env": "FIELD", "channels": ch, "practice": True, "meta": {"pod_motor": "vortex"},
               "robot": {"modules": ["frontleft", "frontright", "backleft", "backright"]}}
        rep = advisor.analyze(doc, {}, history=[], drive_gear=5.5, wheel_d_in=3.0, drive_kind="vortex")
        self.assertEqual(rep["motor"]["kind"], "vortex")

    def test_a_vortex_slips_at_more_amps_than_a_neo(self):
        # Corner by corner: the wall tips weight onto the rear wheels, so fronts and rears differ.
        for v, n in zip(plant.true_slip_currents(motor="vortex"), plant.true_slip_currents(motor="neo")):
            self.assertGreater(v, n * 1.2)


class AdviceOnAVortexTest(unittest.TestCase):
    def test_the_advice_loop_converges_on_a_vortex(self):
        h = rehearse.rehearse("drive", START, rounds=8, motor="vortex")
        self.assertEqual(h[-1]["score"], 100, [(r["score"], r["advice"]) for r in h])
        self.assertAlmostEqual(h[-1]["ff"]["FF/frontleft/kV"], plant.true_drive_feedforward(motor="vortex")["kV"],
                               delta=0.06)

    def test_a_feedforward_that_doesnt_fit_is_measured_again_not_covered_with_kp(self):
        g = dict(START)
        for m in rehearse.MODULES:  # measured on a NEO, run on a Vortex
            g.update({f"FF/{m}/kS": 0.168, f"FF/{m}/kV": 2.835, f"FF/{m}/kA": 0.505})
        rep = advisor.analyze(rehearse._drive_once(g, "floor", "vortex"), gains=g)
        self.assertIn("the feedforward doesn't fit this robot", rep["next"]["title"])
        self.assertEqual(rep["next"]["action"]["test"], "drive_ff")

    def test_vortex_delay_advice_does_not_ask_for_a_slower_window(self):
        g = dict(START, **{"Drive/kP": 0.05})
        rep = advisor.analyze(rehearse._drive_once(g, "floor", "vortex"), gains=g)
        actions = [f.get("action") or {} for f in rep["findings"]]
        self.assertFalse(any((a.get("gains") or {}).get("Drive/VelPeriodMs") == 16 for a in actions),
                         "10 ms x 2 is already shorter than 16 ms x 2")


class PracticeApiTest(unittest.TestCase):
    def test_the_apps_practice_runs_use_the_robots_drive_motor(self):
        from swervetune import server
        with tempfile.TemporaryDirectory() as d, mock.patch.object(runs, "RUNS", d):
            self.assertTrue(server.S.set_project("Peashooter"))
            doc = server.api_practice({"loop": "drive_ff", "surface": "floor", "gains": {}})
        self.assertEqual(doc["meta"]["pod_motor"], "vortex")
        self.assertIn("NEO Vortex", doc["robot"]["name"])
        self.assertEqual(doc["report"]["motor"]["kind"], "vortex")


if __name__ == "__main__":
    unittest.main()
