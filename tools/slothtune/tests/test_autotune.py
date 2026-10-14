"""The auto-tuner (autotune.py): each pod tuned on its own gains, against four practice pods that
start differently, and its rules for a person: pausing when the deadman is let go, stopping on
anything else, never touching a gain every pod shares, and ending on each pod's best gains."""

import threading
import unittest

from slothtune import autotune as A

MODS = ["frontleft", "frontright", "backleft", "backright"]
STEER = {"Steer/kP": 0.01, "Steer/kI": 0, "Steer/kD": 0.0, "Steer/IZone": 0, "Steer/RampS": 0}
DRIVE = {"Drive/kP": 0.0020645, "Drive/kD": 0, "Drive/RampS": 0.25, "Drive/kI": 0, "Drive/IZone": 0}


def spread(base, loop, values):
    g = dict(base)
    for m, v in zip(MODS, values):
        g[f"Pod/{m}/{loop}/kP"] = v
    return g


def tune(runner, loop, **kw):
    t = A.AutoTune(runner, loop, **kw)
    t.start()
    return t, A.wait(t, 300)


class SteerTest(unittest.TestCase):
    def test_four_pods_from_four_starts(self):
        r = A.PracticeRunner(spread(STEER, "Steer", [0.004, 0.01, 0.03, 0.15]), surface="blocks")
        t, res = tune(r, "steer")
        self.assertEqual(res["state"], "finished")
        self.assertEqual([p["status"] for p in res["pods"]], ["done"] * 4)
        # Each pod changed on its own: they ended on different gains.
        kps = {round(res["best_gains"][f"Pod/{m}/Steer/kP"], 4) for m in MODS}
        self.assertGreater(len(kps), 2)
        # Only this pod's steering gains, so Save never writes another loop's.
        self.assertTrue(all(k.startswith(tuple(f"Pod/{m}/Steer/" for m in MODS)) for k in res["best_gains"]))

    def test_no_step_more_than_doubles_or_halves(self):
        r = A.PracticeRunner(spread(STEER, "Steer", [0.004, 0.01, 0.03, 0.15]), surface="floor")
        _, res = tune(r, "steer")
        for p in res["pods"]:
            kp = [x["gains"][f"Pod/{p['pod']}/Steer/kP"] for x in p["rounds"]]
            for a, b in zip(kp, kp[1:]):
                self.assertLessEqual(max(a, b) / min(a, b), 2.0 + 1e-9, (p["pod"], kp))

    def test_ends_on_each_pods_best_gains(self):
        r = A.PracticeRunner(spread(STEER, "Steer", [0.004, 0.01, 0.03, 0.15]), surface="blocks")
        _, res = tune(r, "steer")
        now = r.gains()
        for k, v in res["best_gains"].items():
            self.assertEqual(now[k], v, k)

    def test_a_round_limit(self):
        r = A.PracticeRunner(spread(STEER, "Steer", [0.002] * 4), surface="floor")
        _, res = tune(r, "steer", max_rounds=2)
        self.assertEqual(res["round"], 2)
        self.assertTrue(all(p["status"] == "stopped" and "2 rounds" in p["reason"] for p in res["pods"]))


class SharedTest(unittest.TestCase):
    def test_a_shared_setting_every_pod_asks_for_is_changed_once(self):
        g = spread(dict(STEER, **{"Steer/RampS": 0.25}), "Steer", [0.01] * 4)
        r = A.PracticeRunner(g, surface="blocks")
        _, res = tune(r, "steer")
        # Made for every pod at once, a halving at a time like any other change.
        self.assertLess(r.gains()["Steer/RampS"], 0.25)
        self.assertGreaterEqual(r.gains()["Steer/RampS"], 0.25 / 2 ** len(res["notes"]) - 1e-12)
        self.assertTrue(res["notes"])
        self.assertTrue(all("every pod asked for the same shared change" in n for n in res["notes"]))
        self.assertTrue(all(p["status"] in ("done", "stopped") for p in res["pods"]))


class DriveTest(unittest.TestCase):
    def test_the_floor_measures_each_pods_feedforward_then_tunes(self):
        r = A.PracticeRunner(DRIVE, surface="floor")
        _, res = tune(r, "drive")
        self.assertEqual([p["status"] for p in res["pods"]], ["done"] * 4)
        self.assertTrue(any("Feedforward measured" in (x["advice"] or "") for x in res["pods"][0]["rounds"]))
        self.assertGreater(res["best_gains"]["FF/frontleft/kS"], 0)

    def test_blocks_leave_the_feedforward_to_the_floor_without_a_wasted_run(self):
        r = A.PracticeRunner(DRIVE, surface="blocks")
        _, res = tune(r, "drive")
        self.assertEqual(r.runs, 1)
        self.assertTrue(all(p["status"] == "stopped" and "floor" in p["reason"] for p in res["pods"]))


class Scripted:
    """A runner whose runs end as told: DONE, or ABORTED with a message."""

    def __init__(self, outcomes, gains=None):
        self.inner = A.PracticeRunner(gains or spread(STEER, "Steer", [0.004] * 4), surface="floor")
        self.outcomes, self.calls, self.applied = list(outcomes), 0, []
        self.ran = threading.Event()

    def modules(self):
        return self.inner.modules()

    def gains(self):
        return self.inner.gains()

    def context(self, loop):
        return {}

    def apply(self, values, reason):
        self.applied.append(dict(values))
        return self.inner.apply(values, reason)

    def run(self, test):
        self.calls += 1
        how = self.outcomes.pop(0) if self.outcomes else "DONE"
        self.ran.set()
        if how == "DONE":
            return self.inner.run(test)
        return None, "ABORTED", how


class PersonTest(unittest.TestCase):
    def test_letting_go_pauses_and_continue_runs_the_same_round(self):
        s = Scripted(["DONE", "Deadman released."])
        t = A.AutoTune(s, "steer")
        t.start()
        for _ in range(200):
            if t.state == "paused":
                break
            threading.Event().wait(0.02)
        self.assertEqual(t.state, "paused")
        self.assertIn("deadman", t.message)
        paused_round = t.round
        t.resume()
        res = A.wait(t, 300)
        self.assertEqual(res["state"], "finished")
        self.assertEqual(paused_round, 1, "the let-go round is not counted")

    def test_abort_stops_for_good_on_the_best_gains(self):
        s = Scripted(["DONE", "Stopped by the safety supervisor: impact."])
        t, res = tune(s, "steer")
        self.assertEqual(res["state"], "stopped")
        self.assertIn("impact", res["message"])
        self.assertEqual(s.calls, 2)

    def test_stop_while_paused(self):
        s = Scripted(["Deadman released."])
        t = A.AutoTune(s, "steer")
        t.start()
        for _ in range(200):
            if t.state == "paused":
                break
            threading.Event().wait(0.02)
        t.stop("Stopped.")
        res = A.wait(t, 60)
        self.assertEqual(res["state"], "stopped")
        self.assertEqual(s.calls, 1)


class RulesTest(unittest.TestCase):
    def test_only_its_own_gains(self):
        self.assertEqual(A.own_change({"Steer/kP": 0.02, "Steer/kD": 0.1}, "frontleft"),
                         {"Pod/frontleft/Steer/kP": 0.02, "Pod/frontleft/Steer/kD": 0.1})
        self.assertIsNone(A.own_change({"Steer/RampS": 0}, "frontleft"), "a ramp rate is shared by every pod")
        self.assertEqual(A.own_change({"FF/frontleft/kV": 2.4}, "frontleft"), {"FF/frontleft/kV": 2.4})
        self.assertIsNone(A.own_change({"FF/backleft/kV": 2.4}, "frontleft"))

    def test_a_pods_gains_read_as_the_shared_names(self):
        g = A.pod_gains({"Steer/kP": 0.01, "Pod/frontleft/Steer/kP": 0.03}, "frontleft")
        self.assertEqual(g["Steer/kP"], 0.03)

    def test_it_tunes_steer_or_drive(self):
        with self.assertRaises(ValueError):
            A.AutoTune(A.PracticeRunner(STEER), "spin")


if __name__ == "__main__":
    unittest.main()
