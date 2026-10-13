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


class FlatOutTest(unittest.TestCase):
    def test_flat_out_is_the_same_on_a_fresh_battery(self):
        # YAGSL caps the SPARKs at 12 V, so a fresh 12.8 V battery must not hide saturation.
        sats = []
        for vb in (12.0, 12.8):
            ch = plant.steer_step(rehearse.STEER_PATTERN, kP=0.05, surface="floor")
            ch["vbus"] = [vb] * len(ch["vbus"])
            rep = advisor.analyze({"test": "steer_step", "channels": ch, "env": "FIELD", "practice": True,
                                   "robot": MODS}, {"Steer/kP": 0.05})
            sats.append(rep["worst"]["sat"])
        self.assertAlmostEqual(sats[0], sats[1], places=6)
        self.assertGreater(sats[1], 0.5)


class FeedforwardFitTest(unittest.TestCase):
    START = {"Drive/kP": 0.0005, "Drive/kI": 0.0, "Drive/kD": 0.0, "Drive/RampS": 0.0,
             "Drive/VelPeriodMs": 0, "Drive/VelDepth": 0}

    def gains(self, ks, kv, ka):
        g = dict(self.START)
        for m in rehearse.MODULES:
            g.update({f"FF/{m}/kS": ks, f"FF/{m}/kV": kv, f"FF/{m}/kA": ka})
        return g

    def test_a_feedforward_for_another_motor_is_measured_again(self):
        g = self.gains(0.168, 2.835, 0.505)  # a NEO's, on a Vortex robot
        rep = advisor.analyze(rehearse._drive_once(g, "floor", "vortex"), gains=g)
        self.assertIn("doesn't fit", rep["next"]["title"])

    def test_a_feedforward_that_fits_the_motor_leaves_the_rest_to_kp(self):
        g = self.gains(0.15, 2.40, 0.0)  # right for a Vortex, just no kA
        rep = advisor.analyze(rehearse._drive_once(g, "floor", "vortex"), gains=g)
        self.assertNotIn("doesn't fit", (rep["next"] or {}).get("title", ""),
                         "re-measuring would return the same numbers forever")


class AggressiveDriveTest(unittest.TestCase):
    """M13: the pod has no sensor noise, flex or lash, so it can't be what rejects these."""

    def test_peashooters_drive_gains_are_never_offered_save(self):
        g = {"Drive/kP": 1.0, "Drive/kD": 0.4, "Drive/RampS": 0.0, "Drive/VelPeriodMs": 0, "Drive/VelDepth": 0}
        rep = advisor.analyze(rehearse._drive_once(dict(g), "floor", "vortex"), gains=g)
        actions = [f.get("action") or {} for f in rep["findings"]]
        self.assertFalse(any(a.get("type") == "save" for a in actions), "never Save on a robot it would buzz")
        hot = next(f for f in rep["findings"] if "too aggressive" in f["title"])
        self.assertEqual(hot["action"]["values"], {"Drive/kP": 0.5, "Drive/kD": 0.2})

    def test_the_advice_walks_them_down(self):
        h = rehearse.rehearse("drive", {"Drive/kP": 1.0, "Drive/kD": 0.4, "Drive/RampS": 0.25,
                                        "Drive/VelPeriodMs": 0, "Drive/VelDepth": 0}, motor="vortex")
        self.assertEqual(h[-1]["score"], 100)
        self.assertLessEqual(h[-1]["gains"]["Drive/kD"], 0.05)
        self.assertLess(h[-1]["gains"]["Drive/kP"], 0.5)


class CarpetKvTest(unittest.TestCase):
    """M12: on carpet the chassis couples the wheels, so a module's kV can't name a weak motor."""

    def fits_doc(self, surface):
        return rehearse._ff_once({}, surface, "vortex")

    def history(self, rep):
        # Earlier runs where frontleft's kV sat 10% above its siblings: now it reads low against them.
        mods = {n: {"ok": True, "kV": f["kV"] * (1.1 if n == "frontleft" else 1.0), "kS": f["kS"]}
                for n, f in rep["modules"].items() if f.get("ok")}
        return [{"saved": "20260901-000000", "modules": mods}] * 3

    def test_a_motor_trend_is_judged_on_blocks_only(self):
        for surface, expect in (("floor", False), ("blocks", True)):
            doc = self.fits_doc(surface)
            first = advisor.analyze(doc, gains={}, history=[])
            rep = advisor.analyze(doc, gains={}, history=self.history(first))
            said = any("kV down" in f["title"] for f in rep["findings"])
            self.assertEqual(said, expect, surface)


if __name__ == "__main__":
    unittest.main()
