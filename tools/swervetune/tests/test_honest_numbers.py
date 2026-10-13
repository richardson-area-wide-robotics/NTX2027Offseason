"""Numbers a student or agent would act on must never flatter a bad run (review findings B4, B5, B8)."""

import unittest

from swervetune import advisor, plant, rehearse

MODS = {"modules": ["frontleft"]}


class StoppedRunTest(unittest.TestCase):
    def test_a_stopped_run_gets_no_score_and_no_gain_advice(self):
        ch = plant.steer_step(rehearse.STEER_PATTERN, kP=0.01)
        rep = advisor.analyze({"test": "steer_step", "channels": ch, "env": "FIELD", "outcome": "ABORTED",
                               "message": "Impact: 14.2 m/s^2", "robot": MODS}, {"Steer/kP": 0.01})
        self.assertIsNone(rep["score"])
        self.assertEqual(rep["targets"], [])
        self.assertEqual(rep["next"]["action"], {"type": "stop", "reason": "Impact: 14.2 m/s^2"})
        self.assertEqual([f for f in rep["findings"] if f.get("action")], [rep["next"]], "nothing to change")

    def test_a_finished_run_is_judged_as_before(self):
        ch = plant.steer_step(rehearse.STEER_PATTERN, kP=0.01)
        rep = advisor.analyze({"test": "steer_step", "channels": ch, "env": "FIELD", "outcome": "DONE",
                               "robot": MODS}, {"Steer/kP": 0.01})
        self.assertIsNotNone(rep["score"])


class NeverFinishedTest(unittest.TestCase):
    def test_a_move_that_never_finishes_is_a_miss_not_zero_ms(self):
        ch = plant.steer_step(rehearse.STEER_PATTERN, kP=0.002, surface="floor")
        rep = advisor.analyze({"test": "steer_step", "channels": ch, "env": "FIELD", "practice": True,
                               "robot": MODS}, {"Steer/kP": 0.002})
        t = {x["name"].split(",")[0].split(" (")[0]: x for x in rep["targets"]}
        self.assertFalse(t["large-step rise time"]["met"])
        self.assertFalse(t["settling time"]["met"])
        self.assertIn("never finished", rep["summary"])

    def test_raising_kp_from_too_weak_raises_the_score(self):
        scores = []
        for kp in (0.002, 0.0067, 0.0152, 0.0513):
            ch = plant.steer_step(rehearse.STEER_PATTERN, kP=kp, surface="floor")
            rep = advisor.analyze({"test": "steer_step", "channels": ch, "env": "FIELD", "practice": True,
                                   "robot": MODS}, {"Steer/kP": kp})
            scores.append(rep["score"])
        self.assertEqual(scores, sorted(scores), scores)
        self.assertGreater(scores[-1], scores[0])


class TapeTest(unittest.TestCase):
    def straight(self):
        n = 300
        t = [k * 0.02 for k in range(n)]
        cmd = [1.0 if 30 <= k < 180 else 0.0 for k in range(n)]
        x, pos = [], 0.0
        for k in range(n):
            pos += cmd[k] * 0.02
            x.append(pos)
        return {"test": "straight", "env": "FIELD", "outcome": "DONE",
                "channels": {"t": t, "cmd_vx": cmd, "heading": [0.0] * n, "x": x, "y": [0.0] * n},
                "meta": {"distance_m": 3.0, "drive_gear_ratio": 5.5, "steer_gear_ratio": 46.42}}

    def test_a_tape_reading_far_from_odometry_is_refused_not_written(self):
        rep = advisor.straight_report(self.straight(), measured_forward_m=0.04)
        self.assertNotIn("wheel_scale", rep["measured"])
        self.assertFalse(any((f.get("action") or {}).get("type") == "config" for f in rep["findings"]),
                         "never a one-click wheel size from a measuring mistake")
        self.assertIn("too far apart to be the wheels", " ".join(f["why"] for f in rep["findings"]))

    def test_a_believable_tape_reading_still_gives_the_wheel_scale(self):
        rep = advisor.straight_report(self.straight(), measured_forward_m=2.94)
        self.assertAlmostEqual(rep["measured"]["wheel_scale"], 2.94 / rep["measured"]["odometry_forward_m"])
        self.assertTrue(any((f.get("action") or {}).get("type") == "config" for f in rep["findings"]))


if __name__ == "__main__":
    unittest.main()
