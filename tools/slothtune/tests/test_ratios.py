"""Gear ratio detection: a module geared unlike the others, the whole robot geared unlike the
config, and a wrong steering ratio - each told apart from the things that look similar."""

import unittest

from slothtune import advisor, monitor, ratios


def floor_ff_run(scale_by_module, env="FIELD", steps=600, dt=0.01):
    """A drive_ff-shaped run where module i reports scale[i] times the true travel."""
    ch = {"t": [k * dt for k in range(steps)], "phase": [1] * steps}
    for i, s in enumerate(scale_by_module):
        ch[f"m{i}.v"] = [1.0 * s] * steps
        ch[f"m{i}.pos"] = [k * dt * s for k in range(steps)]
        ch[f"m{i}.volts"] = [3.0] * steps
    return {"test": "drive_ff", "env": env, "channels": ch,
            "meta": {"drive_gear_ratio": 5.5, "steer_gear_ratio": 46.42},
            "robot": {"modules": ["frontleft", "frontright", "backleft", "backright"]}}


class RatioMathTest(unittest.TestCase):
    def test_maxswerve_family_names_a_13_tooth_pinion(self):
        c = ratios.candidates(5.5 * 0.923, "maxswerve")
        self.assertEqual(c[0]["name"], "MAXSwerve Medium: 13T pinion, 22T spur")

    def test_module_unlike_the_others(self):
        out = ratios.module_ratio_findings({"fl": 3.0, "fr": 3.0 * 0.923, "bl": 3.0, "br": 3.0}, 5.5, "maxswerve")
        self.assertEqual([f["module"] for f in out], ["fr"])
        self.assertAlmostEqual(out[0]["estimated_ratio"], 5.077, delta=0.01)
        self.assertIn("13T", ratios.describe(out[0]))

    def test_matching_modules_raise_nothing(self):
        self.assertEqual(ratios.module_ratio_findings({"a": 3.0, "b": 3.01, "c": 2.99, "d": 3.0}, 5.5), [])

    def test_family_from_steering_ratio(self):
        self.assertEqual(ratios.family(46.42), "maxswerve")
        self.assertEqual(ratios.family(150 / 7), "sds")


class AdvisorRatioTest(unittest.TestCase):
    def ratio_findings(self, rep):
        return [f for f in rep["findings"] if "gear ratio" in f["title"]]

    def test_floor_feedforward_names_the_odd_module(self):
        rep = advisor.analyze(floor_ff_run([1, 0.923, 1, 1]))
        found = self.ratio_findings(rep)
        self.assertEqual(len(found), 1, rep["findings"])
        self.assertTrue(found[0]["title"].startswith("frontright"))
        self.assertIn("13T", found[0]["why"])

    def test_blocks_cannot_see_it_and_does_not_pretend(self):
        rep = advisor.analyze(floor_ff_run([1, 0.923, 1, 1], env="BLOCKS"))
        self.assertEqual(self.ratio_findings(rep), [])

    def test_kv_advice_no_longer_blames_the_gear_ratio(self):
        doc = floor_ff_run([1, 1, 1, 1])
        rep = advisor.feedforward_report(doc)
        for f in rep["findings"]:
            if "motor physics predicts" in f["title"]:
                self.assertIn("cancels", f["why"])

    def test_steering_ratio_from_motor_versus_absolute(self):
        n = 400
        absolute = [k * 0.45 for k in range(n)]
        ch = {"t": [k * 0.005 for k in range(n)], "m0.sp": [0] * 100 + [90] * 300,
              "m0.steer": [a % 360 for a in absolute], "m0.motor": [a * 1.08 for a in absolute]}
        doc = {"test": "steer_step", "env": "BLOCKS", "channels": ch,
               "meta": {"steer_gear_ratio": 46.42, "steer_feedback_absolute": 0}}
        found = advisor.steer_ratio_findings(doc)
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0]["ratio"], 1.08, delta=0.01)
        doc["meta"]["steer_feedback_absolute"] = 1
        self.assertEqual(advisor.steer_ratio_findings(doc), [], "one sensor: nothing to compare")

    def test_tape_measure_tells_gearing_from_tread(self):
        def run(scale):
            n = 300
            x = [k * 0.01 for k in range(n)]
            ch = {"t": [k * 0.01 for k in range(n)], "cmd_vx": [1.0] * 280 + [0.0] * 20,
                  "x": x, "y": [0.0] * n, "heading": [0.0] * n}
            doc = {"test": "straight", "env": "FIELD", "channels": ch,
                   "meta": {"distance_m": x[-1], "drive_gear_ratio": 5.5, "steer_gear_ratio": 46.42}}
            return advisor.straight_report(doc, measured_forward_m=x[-1] * scale)
        gearing = [f for f in run(1.083)["findings"] if "tread wear" in f["title"]]
        self.assertEqual(len(gearing), 1)
        self.assertIn("13T", gearing[0]["why"])
        self.assertEqual([f for f in run(1.02)["findings"] if "tread wear" in f["title"]], [])


class PassiveMonitorTest(unittest.TestCase):
    def drive(self, env, scales, meters=4.0):
        now = [0.0]
        m = monitor.Monitor(clock=lambda: now[0])
        names = ["fl", "fr", "bl", "br"]
        pos = [0.0] * 4
        flags = []
        for _ in range(int(meters / 0.02)):
            now[0] += 0.02
            pos = [p + 0.02 * s for p, s in zip(pos, scales)]
            live = {"mode": "TELEOP", "steer": [0.0] * 4, "steer_sp": [0.0] * 4, "steer_motor": [0.0] * 4,
                    "v": [1.0] * 4, "v_sp": [1.0] * 4, "pos": list(pos), "heading": 0.0,
                    "drive_amps": [5] * 4, "abs_issue": [0] * 4, "drive_temp": [30] * 4,
                    "steer_temp": [30] * 4, "faults": [""] * 4, "bus": 12.4}
            flags = m.update(live, names, env)
        return [f for f in flags if f["rule"] == "drive_ratio_mismatch"]

    def test_flags_the_odd_module_on_the_floor(self):
        flags = self.drive("FIELD", [1, 1, 0.92, 1])
        self.assertEqual([f["module"] for f in flags], ["bl"])

    def test_silent_on_blocks(self):
        self.assertEqual(self.drive("BLOCKS", [1, 1, 0.92, 1]), [])

    def test_silent_until_enough_travel(self):
        self.assertEqual(self.drive("FIELD", [1, 1, 0.92, 1], meters=2.0), [])


if __name__ == "__main__":
    unittest.main()
