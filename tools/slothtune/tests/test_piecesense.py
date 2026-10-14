"""Game pieces by current (piecesense.py): made-up runs shaped like the robot's system_piece and
system_hold, and the threshold, hold time, spin-up allowance and hold current they give."""

import math
import unittest

from slothtune import advisor, piecesense as P

DT = 0.01


def roller_run(pieces=(22.0, 20.0, 24.0), empty=6.0, spike=40.0, settle=2.0, feed=4.0, clear=3.0, piece_at=2.0):
    t, amps, phase = [], [], []

    def add(n, ph, f):
        for i in range(n):
            t.append(len(t) * DT)
            amps.append(f(i * DT))
            phase.append(ph)

    spin = lambda x: empty + (spike - empty) * math.exp(-x / 0.08)      # a spin-up spike, gone in ~0.3 s
    add(int(settle / DT), 0, spin)
    for k, peak in enumerate(pieces, 1):
        add(int(feed / DT), k, lambda x, p=peak: spin(x) if x < piece_at else (p if x < piece_at + 1.2 else empty))
        add(int(clear / DT), -k, lambda x: 0.0)
    return {"test": "system_piece", "outcome": "DONE", "channels": {"t": t, "amps": amps, "phase": phase},
            "meta": {"pieces": len(pieces), "settle_s": settle, "feed_s": feed, "clear_s": clear, "spin_up_s": 1.0, "positional": 0},
            "notes": ["sensor: Intake has piece (Intake roller, rise)", "system: Intake (ROLLER, RPM)"]}


def arm_run(pieces=2, add_a=3.0):
    t, amps, phase, pos = [], [], [], []

    def sweep(ph, extra):
        for i in range(200):
            p = 90.0 * (i / 199 if i < 100 else (199 - i) / 99)
            t.append(len(t) * DT)
            pos.append(p)
            amps.append(2 + (6 + extra) * math.cos(math.radians(p)))   # gravity pulls most at horizontal (0)
            phase.append(ph)

    sweep(100, 0)
    for k in range(1, pieces + 1):
        sweep(k, add_a)
    return {"test": "system_piece", "outcome": "DONE", "channels": {"t": t, "amps": amps, "phase": phase, "pos": pos},
            "meta": {"pieces": pieces, "positional": 1, "min": 0.0, "max": 90.0}, "notes": ["sensor: Arm has piece (Arm, aboveBaseline)"]}


def hold_run(slip=6.0, hold=9.0, rise_c=1.0):
    t, temp, phase = [], [], []
    for i in range(1000):
        t.append(i * 0.02)
        phase.append(0 if i < 200 else 1 if i < 500 else 2)
        temp.append(30 + (rise_c * (i - 500) * 0.02 / 10 if i >= 500 else 0))
    return {"test": "system_hold", "outcome": "DONE", "channels": {"t": t, "temp": temp, "phase": phase},
            "meta": {"start_a": 20, "min_a": 2, "slip_a": slip, "hold_a": hold, "duty": 0.3, "warn_c": 45},
            "notes": ["hold: Intake roller"]}


class RollerTest(unittest.TestCase):
    def test_the_threshold_sits_between_empty_and_the_weakest_piece(self):
        r = P.calibration_report(roller_run())
        v = r["suggest"]["values"]
        self.assertEqual(v["mode"], "rise")
        self.assertGreater(v["thresholdA"], 6.0)
        self.assertLess(v["thresholdA"], 20.0, "below the weakest piece")
        self.assertAlmostEqual(v["thresholdA"], 13.0, delta=1.0, msg="halfway")
        self.assertGreaterEqual(v["ignoreS"], 0.2, "the spin-up spike passes the threshold: it must be ignored")
        self.assertLessEqual(v["holdS"], 0.25)
        self.assertEqual([p["piece"] for p in r["pieces"]], [1, 2, 3])
        self.assertEqual(r["score"], 100)

    def test_a_piece_fed_too_late_is_said(self):
        r = P.calibration_report(roller_run(pieces=(22.0, 6.0, 24.0)))
        self.assertTrue(any("Piece 2" in f["title"] for f in r["findings"]), r["findings"])

    def test_too_close_to_tell(self):
        r = P.calibration_report(roller_run(pieces=(8.5, 8.6)))
        self.assertEqual(r["findings"][0]["level"], "warn")
        self.assertIn("close", r["findings"][0]["why"])

    def test_the_save_is_to_slothtune_json(self):
        rep = advisor.analyze(roller_run())
        self.assertTrue(rep["save"])
        self.assertTrue(all(e["file"] == "slothtune.json" and e["path"][:2] == ["currentSensors", "Intake has piece"]
                            for e in rep["save"]))


class NoCurrentTest(unittest.TestCase):
    def test_the_simulator_reports_none(self):
        run = roller_run()
        run["channels"]["amps"] = [float("nan")] * len(run["channels"]["amps"])
        r = P.calibration_report(run)
        self.assertIn("no current", r["findings"][0]["title"])


class ArmTest(unittest.TestCase):
    def test_a_baseline_and_where_it_can_tell(self):
        r = P.calibration_report(arm_run())
        v = r["suggest"]["values"]
        self.assertEqual(v["mode"], "aboveBaseline")
        self.assertEqual(len(v["baseline"]), 8)
        self.assertGreater(v["baseline"][0][1], v["baseline"][-1][1], "more current near horizontal")
        self.assertGreater(v["thresholdA"], 0.3)
        self.assertIn("small", r["findings"][0]["why"], "near vertical a piece adds little")


class HoldTest(unittest.TestCase):
    def test_slipped_then_held_with_a_margin(self):
        r = P.hold_report(hold_run())
        self.assertEqual(r["hold_a"], 9.0)
        self.assertIn("slipped at 6 A", r["findings"][0]["title"])
        self.assertEqual(r["suggest"]["values"]["currentA"], 9.0)

    def test_warming_past_its_warning_over_a_match(self):
        r = P.hold_report(hold_run(rise_c=5.0))
        self.assertEqual(r["findings"][-1]["level"], "warn")
        self.assertIn("warning", r["findings"][-1]["why"])

    def test_no_grip_at_all(self):
        r = P.hold_report(hold_run(slip=20.0, hold=20.0))
        self.assertIn("even at the start", r["findings"][0]["title"])

    def test_the_hold_saves_to_holds(self):
        rep = advisor.analyze(hold_run())
        self.assertEqual(rep["save"][0]["path"][:2], ["holds", "Intake roller"])


if __name__ == "__main__":
    unittest.main()
