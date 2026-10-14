"""The mechanism auto-tuner (autotune.SystemTune) on practice mechanisms, and the step report's one
next change (systems.tune_next): it converges, never more than doubles or halves a gain, keeps to
the robot's ranges, pauses on a let-go deadman and ends on its best round."""

import unittest

from slothtune import autotune as A, systems


def tune(kind, gains, **kw):
    r = A.PracticeSystemRunner("Mech", kind, gains, **kw)
    t = A.SystemTune(r, "Mech")
    t.start()
    return r, A.wait(t, 120)


def kp_steps(rounds):
    ks = [x["gains"]["Mech/kP"] for x in rounds]
    return [b / a for a, b in zip(ks, ks[1:]) if a]


class ConvergesTest(unittest.TestCase):
    def test_an_elevator_with_nothing_set_gets_kg_and_kv_from_its_own_runs(self):
        r, j = tune("ELEVATOR", {"kP": 4.0, "kD": 0.0, "kS": 0.0, "kV": 0.0, "kG": 0.0})
        self.assertEqual((j["state"], j["status"]), ("finished", "done"), j["reason"])
        self.assertLessEqual(len(j["rounds"]), 4)
        self.assertIn("kG", j["rounds"][0]["advice"])
        self.assertIn("from this run", j["rounds"][0]["advice"])
        self.assertAlmostEqual(r.gains()["Mech/kG"], 0.45, delta=0.05, msg="the model's own gravity volts")
        self.assertAlmostEqual(r.gains()["Mech/kV"], 9.0, delta=0.5)

    def test_too_much_kp_rings_and_comes_down(self):
        r, j = tune("ELEVATOR", {"kP": 400.0, "kD": 0.0, "kS": 0.15, "kV": 9.0, "kG": 0.45})
        self.assertEqual(j["status"], "done", j["reason"])
        self.assertLess(r.gains()["Mech/kP"], 400.0)
        self.assertTrue(any("ringing" in (x["advice"] or "").lower() or "overshoot" in (x["advice"] or "").lower()
                            for x in j["rounds"]))

    def test_a_flywheel_scales_kv_to_its_speed(self):
        r, j = tune("FLYWHEEL", {"kP": 0.01, "kS": 0.0, "kV": 0.015})
        self.assertEqual(j["status"], "done", j["reason"])
        self.assertAlmostEqual(r.gains()["Mech/kV"], 0.021, delta=0.0015)

    def test_never_more_than_double_or_half_a_round(self):
        _, j = tune("FLYWHEEL", {"kP": 0.4, "kS": 0.0, "kV": 0.021})
        for step in kp_steps(j["rounds"]):
            self.assertTrue(0.5 <= step <= 2.0, step)

    def test_ends_on_its_best_round(self):
        r, j = tune("FLYWHEEL", {"kP": 0.4, "kS": 0.0, "kV": 0.021})
        self.assertEqual(j["best"]["cost"], min(x["cost"] for x in j["rounds"]))
        for k, v in j["best_gains"].items():
            self.assertEqual(r.gains()[k], v)


class BackOutTest(unittest.TestCase):
    def test_a_change_that_makes_it_much_worse_is_backed_out_and_not_tried_again(self):
        # Code that gives its SPARK only a position: a kV there pushes it off instead of helping.
        r, j = tune("ELEVATOR", {"kP": 8.0, "kD": 0.0, "kS": 0.0, "kV": 0.0, "kG": 0.45}, position_only=True)
        tried = [x for x in j["rounds"] if x["gains"]["Mech/kV"]]
        self.assertEqual(len(tried), 1, "kV tried once")
        self.assertIn("Much worse", j["rounds"][tried[0]["round"] - 1]["advice"])
        self.assertTrue(all(not x["gains"]["Mech/kV"] for x in j["rounds"][tried[0]["round"]:]), "never again")
        self.assertEqual(r.gains()["Mech/kV"], 0.0)
        self.assertLess(j["best"]["cost"], j["rounds"][0]["cost"])


class RangesTest(unittest.TestCase):
    def test_a_change_past_the_robots_range_is_held_at_its_end(self):
        r, j = tune("FLYWHEEL", {"kP": 0.01, "kS": 0.0, "kV": 0.0}, ranges=(0.0, 0.018))
        self.assertLessEqual(r.gains()["Mech/kV"], 0.018)
        self.assertEqual(j["status"], "stopped")
        self.assertIn("end of its range", j["reason"])


class DeadmanTest(unittest.TestCase):
    def test_letting_go_pauses_and_continue_runs_the_round_again(self):
        r = A.PracticeSystemRunner("Mech", "FLYWHEEL", {"kP": 0.01, "kS": 0.0, "kV": 0.0})
        real = r.run
        calls = []

        def run(test):
            calls.append(test)
            if len(calls) == 1:
                return None, "ABORTED", "The deadman was released."
            return real(test)
        r.run = run
        t = A.SystemTune(r, "Mech")
        t.start()
        for _ in range(200):
            if t.state == "paused":
                break
            import time
            time.sleep(0.01)
        self.assertEqual(t.state, "paused")
        self.assertEqual(t.round, 0, "the round isn't counted")
        t.resume()
        j = A.wait(t, 60)
        self.assertEqual(j["status"], "done")


class NextTest(unittest.TestCase):
    MOVE = {"goal": 1.0, "step": 0.5, "track_pct": 0.0, "overshoot_pct": 0.0, "error_pct": 0.0, "final": 1.0, "settle_s": 0.2}

    def mv(self, **kw):
        return [dict(self.MOVE, **kw)]

    def test_the_physics_come_before_this_runs_fit(self):
        nxt = systems.tune_next("E", True, self.mv(track_pct=40), {"E/kP": 5.0, "E/kV": 0.0}, {"kV": 20.0, "kG": None}, 2.0,
                                "ELEVATOR", {"kV": 9.0, "kG": 0.0})
        self.assertEqual(nxt["action"]["values"], {"E/kV": 10.0})
        self.assertIn("physics", nxt["title"])

    def test_a_kp_of_zero_is_a_persons_call(self):
        nxt = systems.tune_next("E", True, self.mv(error_pct=10), {"E/kP": 0.0}, kind="PIVOT")
        self.assertEqual(nxt["action"]["type"], "person")

    def test_no_kp_registered_is_a_persons_call(self):
        nxt = systems.tune_next("E", True, self.mv(overshoot_pct=40), {"E/kV": 1.0}, kind="PIVOT")
        self.assertEqual(nxt["action"]["type"], "person")

    def test_meeting_every_target_is_save(self):
        nxt = systems.tune_next("E", True, self.mv(), {"E/kP": 5.0}, kind="PIVOT")
        self.assertEqual(nxt["action"]["type"], "save")

    def test_a_kv_scale_stays_within_half_and_double(self):
        nxt = systems.tune_next("F", False, [dict(self.MOVE, goal=400.0, final=100.0, error_pct=-75.0)], {"F/kP": 0.1, "F/kV": 0.01})
        self.assertEqual(nxt["action"]["values"], {"F/kV": 0.02})


class ReportTest(unittest.TestCase):
    def test_the_report_carries_a_cost_and_next(self):
        r = A.PracticeSystemRunner("Mech", "ELEVATOR", {"kP": 4.0, "kV": 0.0, "kG": 0.0})
        doc, _, _ = r.run("system_step")
        rep = systems.step_report(doc, None, r.gains())
        self.assertGreater(rep["cost"], 0)
        self.assertEqual(rep["next"]["action"]["type"], "gains")

    def test_a_simulator_without_physics_gives_no_advice(self):
        doc = {"test": "system_step", "env": "SIM", "channels": {"t": [i * 0.01 for i in range(300)], "pos": [0.0] * 300,
                                                                "sp": [0.0] * 300, "goal": [0.0] * 150 + [1.0] * 150},
               "notes": ["system: E (ELEVATOR, meters)"]}
        rep = systems.step_report(doc, None, {"E/kP": 1.0})
        self.assertIsNone(rep["next"])


if __name__ == "__main__":
    unittest.main()
