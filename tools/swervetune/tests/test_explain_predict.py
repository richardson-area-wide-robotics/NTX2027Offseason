"""The teaching tools: the controller replay explains what really happened, and the 'what if'
prediction is checked against the practice pod, whose true physics are known."""

import unittest

from swervetune import explain, plant, predict

STEER_TARGETS = [90, -45, 10, 30]
SPEEDS = [1.0, 2.5, 0.5, -1.5]


def steer_run(surface="floor", **gains):
    ch = plant.steer_step(STEER_TARGETS, surface=surface, **gains)
    return {"test": "steer_step", "channels": ch, "meta": {}, "robot": {"modules": ["frontleft"]}}


def drive_run(surface="floor", kP=0.002, ff=(0.0, 2.915, 0.0)):
    ch = plant.drive_step(SPEEDS, kP=kP, ff=ff, surface=surface, modules=1)
    return {"test": "drive_step", "channels": ch, "meta": {"drive_gear_ratio": 5.5},
            "robot": {"modules": ["frontleft"]}}


class ExplainTest(unittest.TestCase):
    def test_the_pid_terms_add_up_to_what_the_controller_asked_for(self):
        e = explain.explain(steer_run(kP=0.01, kD=0.2), {"Steer/kP": 0.01, "Steer/kD": 0.2})
        m = e["modules"][0]
        for k in range(0, len(m["t"]), 37):
            self.assertAlmostEqual(m["asked"][k], m["p"][k] + m["i"][k] + m["d"][k] + m["ff"][k], places=9)
        # P is kP x error x battery volts.
        k = next(i for i, e2 in enumerate(m["error"]) if abs(e2) > 20)
        self.assertAlmostEqual(m["p"][k], 0.01 * m["error"][k] * 12.0, places=6)

    def test_a_soft_loop_on_carpet_is_explained_as_stopping_short(self):
        m = explain.explain(steer_run(kP=0.01), {"Steer/kP": 0.01}, {"steer": 20})["modules"][0]
        learns = {s["learn"] for s in m["story"]}
        for expected in ("dead_time", "rise_time", "kP", "steady_state_error", "settling_time"):
            self.assertIn(expected, learns)
        short = next(s for s in m["story"] if s["learn"] == "steady_state_error")
        self.assertIn("carpet", short["text"])
        self.assertTrue(all(n["type"] in ("vspan", "rise", "point", "band", "bracket")
                            for n in m["response"] + m["controller"]))

    def test_a_big_step_says_the_motor_is_flat_out(self):
        m = explain.explain(steer_run(kP=0.03), {"Steer/kP": 0.03}, {"steer": 20})["modules"][0]
        texts = " ".join(s["text"] for s in m["story"] if s["learn"] in ("saturation", "kP"))
        self.assertIn("battery", texts)

    def test_kd_shows_up_as_braking(self):
        m = explain.explain(steer_run(surface="blocks", kP=0.03, kD=2.0),
                            {"Steer/kP": 0.03, "Steer/kD": 2.0})["modules"][0]
        self.assertIn("kD", {s["learn"] for s in m["story"]})

    def test_a_ramp_rate_is_shown_holding_the_output_back(self):
        run = steer_run(kP=0.01, ramp_s=0.25)
        with_ramp = explain.explain(run, {"Steer/kP": 0.01, "Steer/RampS": 0.25}, {"steer": 20})["modules"][0]
        self.assertIn("ramp_rate", {s["learn"] for s in with_ramp["story"]})
        no_ramp = explain.explain(run, {"Steer/kP": 0.01}, {"steer": 20})["modules"][0]
        self.assertNotIn("ramp_rate", {s["learn"] for s in no_ramp["story"]})

    def test_every_moment_says_which_step_it_belongs_to(self):
        m = explain.explain(steer_run(kP=0.02), {"Steer/kP": 0.02})["modules"][0]
        self.assertTrue(all(isinstance(n["step"], int) and n["step"] >= 1 for n in m["story"]))
        self.assertTrue(all(n["step"] >= 1 for n in m["response"] + m["controller"]))
        self.assertEqual({n["step"] for n in m["story"]}, set(range(1, len(STEER_TARGETS) + 1)))

    def test_drive_shows_how_much_the_feedforward_does(self):
        run = drive_run(ff=(0.15, 2.9, 0.0))
        g = {"Drive/kP": 0.002, "FF/frontleft/kS": 0.15, "FF/frontleft/kV": 2.9}
        m = explain.explain(run, g)["modules"][0]
        ff = [s for s in m["story"] if s["learn"] == "feedforward"]
        self.assertTrue(ff)
        self.assertRegex(ff[0]["text"], r"supplies about (9\d|10\d)%")

    def test_other_tests_have_nothing_to_explain(self):
        self.assertIsNone(explain.explain({"test": "spin", "channels": {}}))


class PredictTest(unittest.TestCase):
    """Predictions against the practice pod's real response to the same gains."""

    def check_steer(self, surface, new):
        run = steer_run(surface, kP=0.01)
        p = predict.predict(run, {"Steer/kP": 0.01}, new, 0, current_limit=20)
        self.assertTrue(p["ok"], p.get("reason"))
        self.assertEqual(p["quality"], "good")
        truth = plant.steer_step(STEER_TARGETS, surface=surface, kP=new.get("Steer/kP", 0),
                                 kD=new.get("Steer/kD", 0))
        self.assertLess(predict._rms(p["predicted"], truth["m0.steer"], wrap=True), 2.0)
        real = predict._summary(truth["t"], truth["m0.sp"], truth["m0.steer"], "steer")
        return p["summary"]["predicted"], real

    def test_doubling_steering_kp_on_carpet(self):
        pred, real = self.check_steer("floor", {"Steer/kP": 0.02})
        self.assertAlmostEqual(pred["rise_time"], real["rise_time"], delta=0.15 * real["rise_time"])
        self.assertAlmostEqual(pred["steady_state_error"], real["steady_state_error"], delta=0.5)

    def test_adding_kd_on_blocks(self):
        pred, real = self.check_steer("blocks", {"Steer/kP": 0.04, "Steer/kD": 0.5})
        self.assertAlmostEqual(pred["rise_time"], real["rise_time"], delta=0.15 * real["rise_time"])

    def test_drive_feedforward_and_kp_changes(self):
        run = drive_run()
        g0 = {"Drive/kP": 0.002, "FF/frontleft/kS": 0.0, "FF/frontleft/kV": 2.915}
        for kp, ks, kv in ((0.05, 0.0, 2.915), (0.002, 0.15, 2.36)):
            g1 = dict(g0, **{"Drive/kP": kp, "FF/frontleft/kS": ks, "FF/frontleft/kV": kv})
            p = predict.predict(run, g0, g1, 0, current_limit=40)
            self.assertEqual(p["quality"], "good")
            truth = plant.drive_step(SPEEDS, kP=kp, ff=(ks, kv, 0.0), surface="floor", modules=1)
            self.assertLess(predict._rms(p["predicted"], truth["m0.v"]), 0.05)

    def test_too_much_drive_kp_is_predicted_to_ring(self):
        run = drive_run(surface="blocks")
        g0 = {"Drive/kP": 0.002, "FF/frontleft/kV": 2.915}
        p = predict.predict(run, g0, dict(g0, **{"Drive/kP": 0.2}), 0, current_limit=40)
        self.assertGreaterEqual(p["summary"]["predicted"]["oscillations"], 1)
        self.assertEqual(p["summary"]["replay"]["oscillations"], 0)

    def test_a_run_with_no_motion_refuses_honestly(self):
        run = steer_run(kP=0.0)
        p = predict.predict(run, {"Steer/kP": 0.0}, {"Steer/kP": 0.01}, 0)
        self.assertFalse(p["ok"])
        self.assertIn("too little motion", p["reason"])


if __name__ == "__main__":
    unittest.main()
