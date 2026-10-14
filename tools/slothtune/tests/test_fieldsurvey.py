"""The field tag survey on synthetic fields: moved tags found, noise never moves a tag, wild ones
refused, and the layout variant told apart when the views allow it."""

import json
import unittest

from slothtune import fieldsurvey as FS, plant

MOVED = {5: (0.04, 0.0, 0.0, 0, 0, 0),        # 4 cm along x
         26: (0.0, 0.0, 0.0, 0, 0, 3.0),      # turned 3 degrees
         21: (0.0, -0.025, 0.01, 0, 0, 0)}


def official_x(tag):
    return FS.official("welded")["tags"][tag][1][0]


class SurveyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = FS.survey(plant.field_frames(moved=MOVED))
        cls.rows = {x["id"]: x for x in cls.r["rows"]}
        cls.layout = {t["ID"]: t["pose"] for t in json.loads(cls.r["layout_text"])["tags"]}

    def test_moved_and_turned_tags_are_found(self):
        self.assertAlmostEqual(self.rows[5]["dx_cm"], 4.0, delta=0.6)
        self.assertAlmostEqual(self.rows[26]["turned_deg"], 3.0, delta=0.5)
        self.assertAlmostEqual(self.rows[21]["dy_cm"], -2.5, delta=1.0)   # 13 views: about ±0.7 cm
        for t in MOVED:
            self.assertTrue(self.rows[t]["significant"], t)

    def test_noise_never_moves_a_tag(self):
        flagged = sorted(i for i, x in self.rows.items() if x["significant"] and i not in MOVED)
        self.assertEqual(flagged, [])
        self.assertTrue(any("are where they should be" in f["title"] for f in self.r["findings"]))
        self.assertEqual(self.layout[9]["translation"]["x"], round(official_x(9), 6), "kept official exactly")

    def test_the_saved_layout_carries_the_measured_poses(self):
        self.assertEqual(len(self.layout), 32)
        self.assertAlmostEqual(self.layout[5]["translation"]["x"], official_x(5) + 0.04, delta=0.006)

    def test_rarely_seen_tags_are_not_judged(self):
        lone = [i for i, x in self.rows.items() if not x["measured"]]
        self.assertIn(12, lone)
        self.assertTrue(any(f["title"].startswith("Not measured: tags") for f in self.r["findings"]))


class EdgeTest(unittest.TestCase):
    def test_a_tag_on_the_wrong_bracket_is_refused(self):
        r = FS.survey(plant.field_frames(moved={9: (0.45, 0.0, 0.0, 0, 0, 0)}))
        row = next(x for x in r["rows"] if x["id"] == 9)
        self.assertFalse(row["trusted"])
        self.assertTrue(any(f["level"] == "error" and "Tag 9" in f["title"] for f in r["findings"]))
        x9 = next(t for t in json.loads(r["layout_text"])["tags"] if t["ID"] == 9)["pose"]["translation"]["x"]
        self.assertAlmostEqual(x9, official_x(9), places=5, msg="keeps the official pose")

    def test_a_wrong_bracket_does_not_drag_its_neighbors(self):
        # Moved tags and one 45 cm off together: only the moved ones may be flagged.
        moved = {**MOVED, 9: (0.45, 0.0, 0.0, 0, 0, 0)}
        r = FS.survey(plant.field_frames(moved=moved))
        flagged = sorted(x["id"] for x in r["rows"] if x["significant"] or (x["measured"] and not x["trusted"]))
        self.assertEqual(flagged, sorted(moved))
        rows = {x["id"]: x for x in r["rows"]}
        self.assertAlmostEqual(rows[9]["moved_cm"], 45, delta=1.0)
        self.assertAlmostEqual(rows[5]["dx_cm"], 4.0, delta=0.6)

    def test_close_up_views_cant_tell_the_layouts_apart(self):
        r = FS.survey(plant.field_frames(noise_m=0, noise_deg=0))
        self.assertTrue(any("Can't tell the welded and AndyMark" in f["title"] for f in r["findings"]))

    def test_a_whole_field_shape_tells_the_layouts_apart(self):
        # When views tie every tag together, the shape alone says which layout the field is.
        am = FS.official("andymark")
        shape = {"poses": dict(am["tags"]), "groups": [sorted(am["tags"])], "counts": {},
                 "sigma": {i: (0.001, 0.1, 20) for i in am["tags"]}}
        fit_am = FS.compare(shape, am)["rms_cm"]
        fit_w = FS.compare(shape, FS.official("welded"))["rms_cm"]
        self.assertLess(fit_am, 1e-6)
        self.assertGreater(fit_w, FS.MIN_FIT_GAP_CM)

    def test_a_whole_structure_moved_as_one_is_not_visible(self):
        # Documented limit: every tag in a group moved together reads as unmoved.
        everything = {i: (0.03, 0.0, 0.0, 0, 0, 0) for i in range(1, 33)}
        r = FS.survey(plant.field_frames(moved=everything, noise_m=0, noise_deg=0))
        self.assertLess(max(x["moved_cm"] for x in r["rows"]), 0.01)

    def test_nothing_seen_together(self):
        r = FS.survey([{"camera": "front", "tag": 1, "x": 2, "y": 0, "z": 0, "qw": 0, "qx": 0, "qy": 0,
                        "qz": 1, "ambiguity": 0.05, "t": 1.0}])
        self.assertIn("No frame had two tags", r["findings"][0]["title"])

    def test_ambiguous_sightings_are_left_out_and_still_frames_merge(self):
        s = plant.field_frames()
        self.assertEqual(FS.frames([dict(x, ambiguity=0.5) for x in s]), [])
        # The same view ten times over (a robot standing still) is one view that counts ten times.
        one = [x for x in s if x["t"] == s[0]["t"]]
        many = [dict(x, t=x["t"] + k * 0.02) for k in range(10) for x in one]
        views = FS.frames(many)
        if len(one) >= 2:
            self.assertEqual(len(views), 1)
            self.assertEqual(next(iter(views[0].values()))[2], 10.0)


if __name__ == "__main__":
    unittest.main()
