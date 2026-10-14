"""The Live tab's field view (server.field_view, seen_tags, robot_outline, api_field): the surveyed
tags as the page draws them, which tags count as in view, and the robot's bumpers from PathPlanner."""

import json
import math
import os
import struct
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from slothtune import fieldsurvey, server


def _layout(tags, length=16.541, width=8.069):
    return {"field": {"length": length, "width": width}, "tags": [
        {"ID": i, "pose": {"translation": {"x": x, "y": y, "z": 0.5},
                           "rotation": {"quaternion": {"W": math.cos(math.radians(yaw) / 2), "X": 0.0, "Y": 0.0,
                                                       "Z": math.sin(math.radians(yaw) / 2)}}}}
        for i, x, y, yaw in tags]}


class FieldViewTest(unittest.TestCase):
    def test_each_tag_where_it_stands_and_which_way_it_faces(self):
        v = server.field_view(_layout([(1, 2.0, 3.0, 0.0), (2, 14.0, 1.0, 180.0), (3, 8.0, 4.0, 90.0)]))
        self.assertEqual((v["length"], v["width"]), (16.541, 8.069))
        by = {t["id"]: t for t in v["tags"]}
        self.assertEqual((by[1]["x"], by[1]["y"], by[1]["z"]), (2.0, 3.0, 0.5))
        self.assertAlmostEqual(by[1]["yaw_deg"], 0.0, places=6)
        self.assertAlmostEqual(abs(by[2]["yaw_deg"]), 180.0, places=6)
        self.assertAlmostEqual(by[3]["yaw_deg"], 90.0, places=6)

    def test_the_official_layout_reads(self):
        with open(os.path.join(fieldsurvey.FIELDS, "2026-rebuilt-welded.json"), encoding="utf-8") as fh:
            v = server.field_view(json.load(fh))
        self.assertGreater(len(v["tags"]), 20)
        self.assertTrue(all(0 <= t["x"] <= v["length"] and 0 <= t["y"] <= v["width"] for t in v["tags"]))


class SeenTagsTest(unittest.TestCase):
    def test_only_fresh_sightings_count(self):
        s = [{"tag": 4, "t": 99.9}, {"tag": 7, "t": 98.0}, {"tag": 4, "t": 99.95}]
        self.assertEqual(server.seen_tags(s, 100.0), [4], "tag 7's frame is 2 s old: the camera lost it")

    def test_without_a_clock_every_sighting_counts(self):
        self.assertEqual(server.seen_tags([{"tag": 3, "t": 0.0}, {"tag": 1, "t": 5.0}], 0.0), [1, 3])
        self.assertEqual(server.seen_tags([{"tag": 2, "t": float("nan")}], 10.0), [2])

    def test_no_sightings(self):
        self.assertEqual(server.seen_tags([], 10.0), [])


class RobotOutlineTest(unittest.TestCase):
    def test_pathplanners_bumpers(self):
        r = server.robot_outline({"robotWidth": 0.9, "robotLength": 0.8, "bumperOffsetX": 0.05, "bumperOffsetY": 0.0})
        self.assertEqual(r, {"length": 0.8, "width": 0.9, "offset": [0.05, 0.0]})

    def test_missing_or_silly_sizes_give_none(self):
        self.assertIsNone(server.robot_outline({}))
        self.assertIsNone(server.robot_outline({"robotWidth": 0.0, "robotLength": 0.9}))
        self.assertIsNone(server.robot_outline({"robotWidth": "wide", "robotLength": 0.9}))


class ApiFieldTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="slothtune-field-")
        self.project = SimpleNamespace(path=self.dir, name="Test")

    def _write(self, rel, data):
        path = os.path.join(self.dir, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh) if not isinstance(data, str) else fh.write(data)

    def _call(self):
        with mock.patch.object(server.S, "project", self.project), \
                mock.patch.object(server.ppcheck, "settings_path",
                                  lambda p: os.path.join(p.path, "src", "main", "deploy", "pathplanner", "settings.json")):
            return server.api_field()

    def test_not_surveyed_yet(self):
        r = self._call()
        self.assertEqual((r["ok"], r["surveyed"], r["robot"]), (True, False, None))

    def test_surveyed_with_pathplanners_robot(self):
        self._write("src/main/deploy/apriltags/surveyed.json", _layout([(1, 2.0, 3.0, 0.0)]))
        self._write("src/main/deploy/pathplanner/settings.json", {"robotWidth": 0.9, "robotLength": 0.9})
        r = self._call()
        self.assertTrue(r["surveyed"])
        self.assertEqual(r["file"], "src/main/deploy/apriltags/surveyed.json")
        self.assertEqual([t["id"] for t in r["tags"]], [1])
        self.assertEqual(r["robot"]["width"], 0.9)

    def test_a_broken_layout_says_so(self):
        self._write("src/main/deploy/apriltags/surveyed.json", "{not json")
        r = self._call()
        self.assertFalse(r["surveyed"])
        self.assertIn("surveyed.json", r["error"])


class FieldPictureTest(unittest.TestCase):
    """The page places the robot on PathPlanner's picture by its pixels a meter and margin: those
    must match the picture shipped."""

    def test_the_2026_picture_matches_its_entry(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "web", "img", "fields", "field26.png"), "rb") as fh:
            head = fh.read(24)          # a PNG's IHDR: width and height, big-endian, at bytes 16-24
        self.assertEqual(head[:8], bytes.fromhex("89504e470d0a1a0a"), "a PNG")
        size = struct.unpack(">II", head[16:24])
        with open(os.path.join(here, "web", "live.js"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn(f'src: "img/fields/field26.png", w: {size[0]}, h: {size[1]}, ppm: 100, margin: 0.5', src)
        self.assertAlmostEqual(size[0] / 100 - 1.0, 16.541, delta=0.01, msg="the picture's field is the layout's length")
        self.assertAlmostEqual(size[1] / 100 - 1.0, 8.069, delta=0.01)


if __name__ == "__main__":
    unittest.main()
