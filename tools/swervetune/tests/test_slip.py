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
        doc = run(ceiling_a=120.0)  # high enough for the tipped-on rear wheels to break loose too
        rep = advisor.analyze(doc)
        for i, n in enumerate(NAMES):
            self.assertAlmostEqual(rep["modules"][n]["slip_a"], doc["meta"][f"slip_a_m{i}"], delta=0.3, msg=n)
        self.assertEqual(rep["score"], 100)

    def test_the_wall_tips_weight_onto_the_rear_wheels(self):
        # Even weight: the fronts still slip first, by about the tipping the physics predicts.
        doc = run(ceiling_a=120.0)
        rep = advisor.analyze(doc)
        front = (rep["modules"]["frontleft"]["slip_a"] + rep["modules"]["frontright"]["slip_a"]) / 2
        rear = (rep["modules"]["backleft"]["slip_a"] + rep["modules"]["backright"]["slip_a"]) / 2
        self.assertGreater(rear / front, 1.4)
        info = [f for f in rep["findings"] if f["title"].startswith("The front wheels slipped first")]
        self.assertEqual(len(info), 1)
        self.assertIn("not the robot's balance", info[0]["why"])
        self.assertFalse(any("to one side" in f["why"] for f in rep["findings"]), "front/rear is the test, not the robot")

    def test_the_limit_is_90_percent_of_the_weakest_corner(self):
        rep = advisor.analyze(run())
        weakest = min(m["slip_a"] for m in rep["modules"].values())
        self.assertEqual(rep["recommended_a"], int(0.9 * weakest))
        rec = next(f for f in rep["findings"] if f["title"].startswith("Drive current limit"))
        self.assertEqual(rec["action"], {"type": "config", "file": "modules/physicalproperties.json",
                                         "path": ["currentLimit", "drive"], "value": rep["recommended_a"]})
        self.assertTrue("frontleft" in rec["why"] or "frontright" in rec["why"])  # the wall unloads the fronts

    def test_a_limit_above_slip_is_called_out(self):
        rep = advisor.analyze(run(limit_before_a=60.0))
        self.assertTrue(any(f["level"] == "warn" and "above where" in f["title"] for f in rep["findings"]))

    def test_grippy_carpet_keeps_the_policy(self):
        # No tipping (bumper_h=0): the path where no wheel slips below the ceiling.
        rep = advisor.analyze(run(mu_static=2.0, ceiling_a=60.0, limit_before_a=60.0, bumper_h=0.0))
        self.assertEqual(rep["recommended_a"], 60)
        self.assertTrue(any(f["title"].startswith("No wheel slipped") for f in rep["findings"]))

    def test_never_above_the_policy(self):
        doc = run(mu_static=2.0, ceiling_a=80.0)
        doc["meta"]["policy_a"] = 60.0
        self.assertLessEqual(advisor.analyze(doc)["recommended_a"], 60)

    def test_weight_to_one_side_is_explained(self):
        rep = advisor.analyze(run(left_share=0.35, ceiling_a=120.0))
        self.assertTrue(any("to one side" in f["why"] for f in rep["findings"]), [f["title"] for f in rep["findings"]])

    def test_front_heavy_is_never_blamed_on_the_robot(self):
        # In a wall push a front-heavy robot and the wall's tipping look alike: say nothing about balance.
        rep = advisor.analyze(run(front_share=0.60, ceiling_a=120.0))
        self.assertFalse(any("to one side" in f["why"] for f in rep["findings"]))

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
