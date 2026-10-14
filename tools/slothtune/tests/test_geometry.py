"""Module positions from a tape measure, wheel sizes from a push in coast, and the spin check."""

import os
import unittest

from slothtune import geometry as G, plant, yagslcfg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PEA = yagslcfg.Project(os.path.join(REPO, "Peashooter"))
NAMES = ["frontleft", "frontright", "backleft", "backright"]


class TapeTest(unittest.TestCase):
    def test_a_rectangular_frame_moves_every_module_into_its_quadrant(self):
        r = G.tape_locations(PEA, 22.5, 24.5)
        rows = {x["name"]: x for x in r["rows"]}
        self.assertEqual((rows["frontleft"]["new_front"], rows["frontleft"]["new_left"]), (11.25, 12.25))
        self.assertEqual((rows["backright"]["new_front"], rows["backright"]["new_left"]), (-11.25, -12.25))
        self.assertEqual(len(r["edits"]), 8)
        self.assertIn(("modules/frontright.json", ("location", "left"), -12.25), r["edits"])
        self.assertIn("up to 0.79 in", r["findings"][0]["title"])

    def test_a_matching_tape_changes_nothing(self):
        r = G.tape_locations(PEA, 24.1, 24)
        self.assertEqual(r["edits"], [])
        self.assertEqual(r["findings"][0]["level"], "ok")

    def test_centimetres_or_the_frame_size_by_mistake_are_refused(self):
        r = G.tape_locations(PEA, 61, 61)
        self.assertEqual(r["edits"], [])
        self.assertIn("don't look like a robot", r["findings"][0]["title"])


def push(**kw):
    return {"channels": plant.coast_push(**kw)}


class WheelTest(unittest.TestCase):
    def test_one_worn_wheel_and_the_average_are_found(self):
        r = G.wheel_sizes(push(real_in=(3.92, 4.0, 4.0, 4.0)), 3.0, 4.0, NAMES)
        rows = {x["name"]: x for x in r["rows"]}
        self.assertAlmostEqual(rows["frontleft"]["diameter_in"], 3.92, delta=0.003)
        self.assertAlmostEqual(rows["frontright"]["diameter_in"], 4.0, delta=0.003)
        self.assertAlmostEqual(r["average_in"], 3.98, delta=0.003)
        titles = " | ".join(f["title"] for f in r["findings"])
        self.assertIn("frontleft's wheel is 1.5% smaller than the average", titles)
        self.assertIn("0.5% smaller than configured", titles)
        self.assertEqual(r["edits"][0][:2], ("modules/physicalproperties.json", ("conversionFactors", "drive", "diameter")))
        self.assertAlmostEqual(r["edits"][0][2], 3.98, delta=0.003)

    def test_a_wheel_at_an_angle_is_corrected_and_named(self):
        r = G.wheel_sizes(push(angles_deg=(12, 0, 0, 0)), 3.0, 4.0, NAMES)
        rows = {x["name"]: x for x in r["rows"]}
        self.assertAlmostEqual(rows["frontleft"]["diameter_in"], 4.0, delta=0.004, msg="cosine corrected")
        self.assertTrue(any("frontleft pointed 12 degrees off straight" in f["title"] for f in r["findings"]))
        self.assertEqual(r["edits"], [])

    def test_a_wheel_pointing_backwards_is_straight(self):
        r = G.wheel_sizes(push(angles_deg=(180, 0, 0, 0)), 3.0, 4.0, NAMES)
        self.assertLess(r["rows"][0]["angle_deg"], 1)
        self.assertTrue(any("counted backwards" in f["title"] for f in r["findings"]))

    def test_a_curved_or_short_push_is_flagged(self):
        titles = " | ".join(f["title"] for f in G.wheel_sizes(push(curve_deg=6, tape_m=1.0), 1.0, 4.0, NAMES)["findings"])
        self.assertIn("curved by 6", titles)
        self.assertIn("short push", titles)

    def test_good_wheels_need_nothing(self):
        r = G.wheel_sizes(push(), 3.0, 4.0, NAMES)
        self.assertEqual(r["edits"], [])
        self.assertEqual([f["level"] for f in r["findings"]], ["ok"])

    def test_a_distance_typed_wrong_is_never_saved_as_a_wheel_size(self):
        # Pushed 6 m, the box said 3 m: the wheels "measure" half size. Before, that was a one-click save.
        r = G.wheel_sizes(push(tape_m=6.0), 3.0, 4.0, NAMES)
        self.assertEqual(r["edits"], [])
        self.assertEqual(r["findings"][-1]["level"], "error")
        self.assertIn("measuring mistake", r["findings"][-1]["title"])

    def test_no_push_recorded(self):
        r = G.wheel_sizes(push(tape_m=0.0), 3.0, 4.0, NAMES)
        self.assertIn("No wheel turned", r["findings"][0]["title"])


class SpinTest(unittest.TestCase):
    def test_agreement_and_disagreement(self):
        self.assertEqual(G.spin_check({"gyro_over_wheels": 1.01})["findings"][0]["level"], "ok")
        r = G.spin_check({"gyro_over_wheels": 1 / 1.06})
        self.assertAlmostEqual(r["radius_ratio"], 1.06, places=6)
        self.assertIn("1.060x as far", r["findings"][0]["title"])

    def test_worn_wheels_are_taken_out_before_judging_positions(self):
        # 2% worn tread reads 2% long, so the wheels alone make the spin look 2% off.
        self.assertAlmostEqual(G.spin_check({"gyro_over_wheels": 1 / 1.02}, configured_over_real=1.02)["radius_ratio"], 1.0)

    def test_no_spin(self):
        self.assertIn("No spin", G.spin_check({})["findings"][0]["title"])


if __name__ == "__main__":
    unittest.main()
