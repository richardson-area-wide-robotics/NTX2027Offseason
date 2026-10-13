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


class NextBatteryTest(unittest.TestCase):
    NOW = 1_800_000_000  # a fixed clock
    import time as _t
    STAMP = _t.strftime("%Y%m%d-%H%M%S", _t.localtime(1_800_000_000 - 3 * 3600))   # 3 h earlier
    RECENT = _t.strftime("%Y%m%d-%H%M%S", _t.localtime(1_800_000_000 - 20 * 60))   # 20 min earlier
    OLDER = _t.strftime("%Y%m%d-%H%M%S", _t.localtime(1_800_000_000 - 26 * 3600))  # a day earlier

    def row(self, bid, status, when, mohm=15.0, listed=True):
        return {"id": bid, "status": status, "when": when, "mohm": mohm, "listed": listed}

    def test_the_healthy_battery_off_the_robot_longest(self):
        rows = [self.row("1", "good", self.STAMP), self.row("2", "good", self.OLDER),
                self.row("3", "practice", self.OLDER, 24), self.row("4", "retire", self.OLDER, 35),
                self.row(battery.BORROWED, None, self.OLDER, listed=True)]
        n = battery.suggest_next(rows, current="1", now=self.NOW)
        self.assertEqual(n["id"], "2")
        self.assertIn("graded good (15 mΩ), last on the robot 26 h ago", n["why"])

    def test_one_on_the_robot_in_the_last_hour_is_a_last_resort(self):
        rows = [self.row("1", "good", self.RECENT), self.row("2", "practice", self.STAMP, 24)]
        self.assertEqual(battery.suggest_next(rows, now=self.NOW)["id"], "2", "rested beats a better grade")
        n = battery.suggest_next([self.row("1", "good", self.RECENT)], now=self.NOW)
        self.assertEqual(n["id"], "1")
        self.assertIn("check this one's charge", n["why"])

    def test_never_the_one_in_now_or_a_retired_one(self):
        rows = [self.row("1", "good", self.OLDER), self.row("2", "retire", self.OLDER, 40)]
        self.assertIsNone(battery.suggest_next(rows, current="1", now=self.NOW))

    def test_an_unmeasured_battery_comes_after_measured_healthy_ones(self):
        rows = [self.row("5", None, None), self.row("2", "good", self.STAMP)]
        self.assertEqual(battery.suggest_next(rows, now=self.NOW)["id"], "2")
        n = battery.suggest_next([self.row("5", None, None)], now=self.NOW)
        self.assertIn("not measured yet, no record of its last use", n["why"])


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
