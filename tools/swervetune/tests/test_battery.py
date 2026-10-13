"""The battery: sag measured from runs and match logs, graded, and remembered per battery."""

import os
import random
import tempfile
import unittest
from unittest import mock

from swervetune import advisor, battery as B, explain, logsummary, plant, runs


def noisy_pairs(r=0.018, v0=12.7, n=600, seed=3):
    rng = random.Random(seed)
    out = []
    for k in range(n):
        i = 5 + 140 * (0.5 + 0.5 * __import__("math").sin(k / 17.0)) * rng.random()
        v = v0 - r * i + rng.gauss(0, 0.02)
        out.append((i + rng.gauss(0, 1.0), v))
    # A few readings taken mid-change, far off the line.
    out += [(120.0, 12.6), (3.0, 10.9), (80.0, 12.9)]
    return out


class FitTest(unittest.TestCase):
    def test_recovers_the_sag_through_noise_and_stray_readings(self):
        f = B.fit(noisy_pairs())
        self.assertAlmostEqual(f["r_ohm"], 0.018, delta=0.0015)
        self.assertAlmostEqual(f["v_rest"], 12.7, delta=0.05)
        self.assertLess(f["n"], 603, "the stray readings were set aside")

    def test_no_answer_when_the_current_barely_moved(self):
        self.assertIsNone(B.fit([(5 + k % 10, 12.6) for k in range(100)]))
        self.assertIsNone(B.fit([(5.0, 12.6)] * 5))

    def test_no_answer_for_a_line_no_battery_makes(self):
        rising = [(i, 12.0 + 0.01 * i) for i in range(0, 60)]
        self.assertIsNone(B.fit(rising), "voltage rising with current is a wiring or timing problem, not a battery")

    def test_grades_and_what_it_means(self):
        self.assertEqual(B.grade(0.016)[0], "good")
        self.assertEqual(B.grade(0.024)[0], "practice")
        self.assertEqual(B.grade(0.035)[0], "retire")
        self.assertIn("Anderson connector", B.grade(0.035)[1], "a loose connection looks like a worn battery")
        f = {"r_ohm": 0.02, "v_rest": 12.8}
        self.assertAlmostEqual(B.volts_at(f, 150), 9.8)
        self.assertAlmostEqual(B.brownout_amps(f), (12.8 - 6.8) / 0.02)

    def test_charge_words(self):
        self.assertIn("charged", B.charge_words(12.85))
        self.assertIn("partly", B.charge_words(12.5))
        self.assertIn("charge it", B.charge_words(12.1))


class FromRunsTest(unittest.TestCase):
    def test_pdh_readings_are_preferred(self):
        ch = plant.drive_ff(battery_r=0.018, bus=12.6)
        pairs, source = B.pairs_from_run({"channels": ch})
        self.assertIn("PDH", source)
        self.assertAlmostEqual(B.fit(pairs)["r_ohm"], 0.018, places=4)

    def test_without_a_pdh_the_current_is_estimated_from_the_motors(self):
        ch = plant.drive_ff(battery_r=0.018, bus=12.6)
        ch.pop("pdh_v")
        ch.pop("ibatt")
        pairs, source = B.pairs_from_run({"channels": ch})
        self.assertIn("estimated", source)
        self.assertAlmostEqual(B.fit(pairs)["r_ohm"], 0.018, delta=0.001)

    def test_a_drive_ff_report_measures_the_battery_and_what_full_stick_needs(self):
        ch = plant.drive_ff(battery_r=0.024, bus=12.6)
        doc = {"test": "drive_ff", "env": "FIELD", "channels": ch, "battery": "7",
               "robot": {"modules": ["frontleft", "frontright", "backleft", "backright"]}}
        rep = advisor.analyze(doc, {}, history=[], max_speed=3.9, drive_gear=5.5, wheel_d_in=3.0,
                              drive_kind="neo")
        b = rep["battery"]
        self.assertEqual(b["id"], "7")
        self.assertAlmostEqual(b["fit"]["r_ohm"], 0.024, delta=0.001)
        self.assertEqual(b["status"], "practice")
        titles = " | ".join(f["title"] for f in rep["findings"])
        self.assertIn("Battery 7 sags 24 mV for every amp drawn (24 mΩ)", titles)
        self.assertIn("Full stick (3.9 m/s) needs", titles)
        self.assertGreater(b["full_stick_v"], 9.0, "a NEO at 3.9 m/s needs most of the battery")

    def test_a_steady_battery_says_nothing(self):
        doc = {"test": "drive_ff", "env": "FIELD", "channels": plant.drive_ff(),
               "robot": {"modules": ["a", "b", "c", "d"]}}
        rep = advisor.analyze(doc, {}, history=[])
        self.assertIsNone(rep["battery"]["fit"])
        self.assertNotIn("sags", " | ".join(f["title"] for f in rep["findings"]))

    def test_a_flat_battery_at_the_start_is_called_out(self):
        ch = plant.drive_ff(battery_r=0.018, bus=12.1)
        rep = B.report({"channels": ch})
        self.assertIn("started at", " | ".join(f["title"] for f in rep["findings"]))


class FromMatchLogsTest(unittest.TestCase):
    def series(self, picked="3", r=0.025):
        rng = random.Random(5)
        amps, volts = [], []
        for k in range(3000):
            t = k * 0.02
            i = max(0.0, 60 + 70 * __import__("math").sin(t / 3) + rng.gauss(0, 10))
            amps.append((t, i))
            volts.append((t, 12.75 - r * i + rng.gauss(0, 0.015)))
        s = {"/PowerDistribution/TotalCurrent": amps, "/PowerDistribution/Voltage": volts,
             "/SystemStats/BatteryVoltage": [(t, v - 0.05) for t, v in volts]}
        if picked is not None:
            s["/RealOutputs/SwerveTune/Battery"] = [(0.0, ""), (4.0, picked)]
        return s

    def test_a_match_measures_the_battery_that_was_picked(self):
        rep = logsummary.summarize(self.series())
        self.assertEqual(rep["battery"]["id"], "3")
        self.assertAlmostEqual(rep["battery"]["fit"]["r_ohm"], 0.025, delta=0.001)
        f = [x for x in rep["findings"] if "sags" in x["title"]]
        self.assertEqual(f[0]["title"], "Battery 3 sags 25 mV for every amp drawn (25 mΩ)")
        self.assertEqual(f[0]["level"], "warn")

    def test_a_match_with_no_battery_picked_says_so(self):
        rep = logsummary.summarize(self.series(picked=""))
        self.assertIn("Nobody picked which battery was in", " | ".join(x["title"] for x in rep["findings"]))

    def test_an_older_log_without_the_picker_is_not_nagged(self):
        rep = logsummary.summarize(self.series(picked=None))
        self.assertNotIn("Nobody picked", " | ".join(x["title"] for x in rep["findings"]))


class LedgerAndHistoryTest(unittest.TestCase):
    def test_each_log_counts_once_and_history_is_per_battery(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(runs, "RUNS", d), \
                mock.patch.object(runs, "LEDGER", os.path.join(d, "batteries.json")):
            f1 = {"r_ohm": 0.016, "v_rest": 12.8}
            self.assertTrue(runs.battery_ledger_add("m1.wpilog:1", "20261010-100000", "3", f1, "match log m1"))
            runs.battery_ledger_add("m1.wpilog:1", "20261010-100000", "3", f1, "match log m1")
            self.assertFalse(runs.battery_ledger_add("m2.wpilog:2", "20261010-110000", "", f1, "match log m2"))
            runs.battery_ledger_add("m3.wpilog:3", "20261011-100000", "3", {"r_ohm": 0.031, "v_rest": 12.6}, "m3")
            led = runs.battery_ledger()
            self.assertEqual(len(led), 2)
            h = B.history([(e["when"], e["id"], e["fit"], e["source"]) for e in led.values()]
                          + [("20261009-090000", "5", {"r_ohm": 0.019, "v_rest": 12.7}, "drive_ff run"),
                             ("20261009-090000", "", {"r_ohm": 0.019, "v_rest": 12.7}, "drive_ff run")])
            self.assertEqual([x["mohm"] for x in h["3"]], [16.0, 31.0], "oldest first")
            self.assertEqual(h["3"][-1]["status"], "retire")
            self.assertEqual(set(h), {"3", "5"}, "a run with no battery picked counts for none")


class CompensationTest(unittest.TestCase):
    def test_runs_without_the_meta_assume_yagsls_12_volts(self):
        self.assertEqual(explain.compensation_volts({}), 12.0)
        self.assertEqual(explain.compensation_volts({"comp_volts": 11.0}), 11.0)
        self.assertEqual(explain.compensation_volts({"comp_volts": float("nan")}), 12.0)

    def test_the_p_term_is_a_fraction_of_12_volts_whatever_the_battery_reads(self):
        n = 40
        ch = {"t": [k * 0.01 for k in range(n)], "vbus": [10.5] * n, "m0.sp": [90.0] * n,
              "m0.steer": [80.0] * n, "m0.motor": [80.0] * n, "m0.volts": [1.2] * n, "m0.amps": [3.0] * n}
        out = explain.explain_module({"channels": ch, "meta": {"steer_feedback_absolute": 1}},
                                     {"Steer/kP": 0.01}, 0, "steer")
        self.assertAlmostEqual(out["p"][5], 0.01 * 10 * 12.0)
        self.assertEqual(out["battery"][5], 10.5, "the battery line is what it had")


class GradesForTheRobotTest(unittest.TestCase):
    def test_listed_graded_batteries_only_and_never_borrowed(self):
        rows = [{"id": "1", "listed": True, "status": "good"}, {"id": "2", "listed": True, "status": None},
                {"id": "3", "listed": False, "status": "retire"}, {"id": B.BORROWED, "listed": True, "status": "good"},
                {"id": "4", "listed": True, "status": "practice"}]
        self.assertEqual(B.grades_for_robot(rows), {"1": "good", "4": "practice"})


if __name__ == "__main__":
    unittest.main()
