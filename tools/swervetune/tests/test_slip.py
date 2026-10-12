"""The slip test's analysis, checked against the practice pod's wall, whose true breakaway
current for each wheel is known."""

import unittest

from swervetune import advisor, plant

NAMES = ["frontleft", "frontright", "backleft", "backright"]


def run(**kw):
    ch, meta = plant.wall_push(**kw)
    return {"test": "slip", "channels": ch, "meta": meta, "env": "FIELD", "practice": True,
            "robot": {"modules": NAMES}}


class SlipTest(unittest.TestCase):
    def test_every_wheels_breakaway_is_found(self):
        rep = advisor.analyze(run())
        truth = plant.true_slip_currents()
        for i, n in enumerate(NAMES):
            self.assertAlmostEqual(rep["modules"][n]["slip_a"], truth[i], delta=0.3, msg=n)
        self.assertEqual(rep["score"], 100)

    def test_the_limit_is_90_percent_of_the_weakest_corner(self):
        rep = advisor.analyze(run())
        weakest = min(m["slip_a"] for m in rep["modules"].values())
        self.assertEqual(rep["recommended_a"], int(0.9 * weakest))
        rec = next(f for f in rep["findings"] if f["title"].startswith("Drive current limit"))
        self.assertEqual(rec["action"], {"type": "config", "file": "modules/physicalproperties.json",
                                         "path": ["currentLimit", "drive"], "value": rep["recommended_a"]})
        self.assertIn("frontleft", rec["why"])  # the lighter front corners slip first

    def test_a_limit_above_slip_is_called_out(self):
        rep = advisor.analyze(run(limit_before_a=60.0))
        self.assertTrue(any(f["level"] == "warn" and "above where" in f["title"] for f in rep["findings"]))

    def test_grippy_carpet_keeps_the_policy(self):
        rep = advisor.analyze(run(mu_static=2.0, ceiling_a=60.0, limit_before_a=60.0))
        self.assertEqual(rep["recommended_a"], 60)
        self.assertTrue(any(f["title"].startswith("No wheel slipped") for f in rep["findings"]))

    def test_never_above_the_policy(self):
        doc = run(mu_static=2.0, ceiling_a=80.0)
        doc["meta"]["policy_a"] = 60.0
        self.assertLessEqual(advisor.analyze(doc)["recommended_a"], 60)

    def test_uneven_weight_is_explained(self):
        rep = advisor.analyze(run(front_share=0.30))
        self.assertTrue(any("not shared evenly" in f["why"] for f in rep["findings"]))

    def test_not_against_a_wall_measures_nothing(self):
        doc = run()
        doc["meta"]["wall_lost"] = 1
        rep = advisor.analyze(doc)
        self.assertIn("not against a wall", rep["summary"])
        self.assertEqual(rep["findings"][0]["level"], "error")

    def test_the_graph_marks_each_slip(self):
        rep = advisor.analyze(run())
        points = [a for a in rep["annotations"] if a["type"] == "point"]
        self.assertEqual(len(points), 4)
        self.assertTrue(all(a["learn"] == "traction" for a in points))


if __name__ == "__main__":
    unittest.main()
