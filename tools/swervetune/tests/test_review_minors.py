"""Small fixes from the review, each pinned so it stays fixed."""

import math
import os
import unittest

from swervetune import advisor, battery, ppcheck, yagslcfg as Y

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def capture(seconds, drift_deg_per_min):
    n = int(seconds * 50)
    t = [i * 0.02 for i in range(n)]
    ch = {"t": t, "heading": [drift_deg_per_min / 60 * x for x in t], "vbus": [12.6] * n}
    for i in range(4):
        ch[f"m{i}.steer"] = [10.0] * n
        ch[f"m{i}.steer_motor"] = [10.0] * n
    return {"test": "capture", "env": "BLOCKS", "outcome": "DONE", "channels": ch,
            "robot": {"modules": ["frontleft", "frontright", "backleft", "backright"]}}


class GyroDriftTest(unittest.TestCase):
    def test_three_seconds_never_judges_drift(self):
        rep = advisor.analyze(capture(3, 2.0))
        self.assertFalse(any("drift" in t["name"] for t in rep["targets"]), rep["targets"])
        self.assertTrue(any("not judged from a short capture" in f["title"] for f in rep["findings"]))

    def test_a_minute_still_does(self):
        rep = advisor.analyze(capture(60, 2.0))
        drift = next(t for t in rep["targets"] if "drift" in t["name"])
        self.assertFalse(drift["met"])
        self.assertTrue(any("Gyro drifts 2.0" in f["title"] for f in rep["findings"]))
        self.assertIn("gyro drift 2.00", rep["summary"])

    def test_a_short_capture_claims_nothing_about_the_gyro(self):
        rep = advisor.analyze(capture(3, 0.0))
        self.assertIn("gyro drift not judged", rep["summary"])
        self.assertNotIn("gyro drift 0.00", rep["summary"])


class BatteryPathTest(unittest.TestCase):
    def hist(self, statuses, when="20261010"):
        return {str(i): [{"when": when + "-120000", "status": s, "mohm": 30}] for i, s in enumerate(statuses, 1)}

    def test_every_battery_tired_at_once_points_at_the_robot(self):
        r = battery.robot_path_suspect(self.hist(["retire", "practice", "retire", "practice"]), today="20261013")
        self.assertIn("4 of 4 batteries", r["title"])
        self.assertIn("main breaker", r["why"])

    def test_one_tired_battery_is_just_a_battery(self):
        self.assertIsNone(battery.robot_path_suspect(self.hist(["good", "good", "retire", "good"]), today="20261013"))

    def test_old_measurements_and_borrowed_ones_dont_count(self):
        h = self.hist(["retire", "retire", "retire"], when="20260901")
        self.assertIsNone(battery.robot_path_suspect(h, today="20261013"))
        h = {battery.BORROWED: [{"when": "20261012", "status": "retire"}]} | self.hist(["good", "good"])
        self.assertIsNone(battery.robot_path_suspect(h, today="20261013"))

    def test_borrowed_is_never_graded(self):
        fit = {"r_ohm": 0.040, "v_rest": 12.5}
        h = battery.history([("20261012", battery.BORROWED, fit, "run"), ("20261012", "3", fit, "run")])
        self.assertIsNone(h[battery.BORROWED][0]["status"])
        self.assertEqual(h["3"][0]["status"], "retire")


class TurnAccelTest(unittest.TestCase):
    def test_turning_uses_the_moment_of_inertia(self):
        p = Y.Project(os.path.join(REPO, "Peashooter"))
        c = ppcheck.capabilities(p)
        mass, _ = p.mass()
        moi, _ = p.moi()
        self.assertAlmostEqual(math.radians(c["max_ang_accel_deg"]), mass * c["max_accel"] * c["radius_m"] / moi)
        self.assertGreater(math.radians(c["max_ang_accel_deg"]), c["max_accel"] / c["radius_m"] * 1.2,
                           "a ring of point masses at the wheels understated it")


if __name__ == "__main__":
    unittest.main()
