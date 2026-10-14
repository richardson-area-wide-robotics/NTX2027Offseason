"""Camera mount from a wall tag: the rotation math, then recovery of known mounts from sightings."""

import math
import unittest

from slothtune import camcal as K, plant

FRONT = (0.28, -0.12, 0.52, 0.0, -18.0, 8.0)
SPOTS = [{"side": "front", "distance_m": 2.0, "lateral_m": 0.0, "height_m": 0.6, "tag_id": 7},
         {"side": "front", "distance_m": 1.5, "lateral_m": 0.5, "height_m": 0.6, "tag_id": 7},
         {"side": "front", "distance_m": 2.6, "lateral_m": -0.4, "height_m": 0.6, "tag_id": 7}]


def close(test, result, mount, cm=0.05, deg=0.05):
    test.assertLess(math.dist([result[k] for k in "xyz"], mount[:3]) * 100, cm)
    got = K.euler_to_mat(result["roll"], result["pitch"], result["yaw"])
    test.assertLess(K.angle_between(got, K.euler_to_mat(*mount[3:])), deg)


class MathTest(unittest.TestCase):
    def test_euler_quaternion_and_inverse_round_trips(self):
        for rpy in [(0, 0, 0), (5, -18, 8), (-30, 20, 170), (0, -10, -90)]:
            m = K.euler_to_mat(*rpy)
            back = K.mat_to_euler(m)
            self.assertLess(K.angle_between(m, K.euler_to_mat(*back)), 1e-9)
            self.assertLess(K.angle_between(m, K.quat_to_mat(*K.mat_to_quat(m))), 1e-6)
            t = (m, [0.3, -0.2, 0.5])
            r, v = K.compose(t, K.inverse(t))
            self.assertLess(K.angle_between(r, K.euler_to_mat(0, 0, 0)), 1e-9)
            self.assertLess(max(abs(x) for x in v), 1e-12)

    def test_wpilib_conventions(self):
        # Positive pitch tips +x toward -z (a camera looking down); positive yaw turns +x toward +y.
        down = K._vec(K.euler_to_mat(0, 30, 0), [1, 0, 0])
        self.assertLess(down[2], 0)
        left = K._vec(K.euler_to_mat(0, 0, 90), [1, 0, 0])
        self.assertAlmostEqual(left[1], 1, places=12)

    def test_a_wall_tag_faces_the_robot(self):
        r, t = K.tag_in_robot("front", 2.0, 0.5, 0.6)
        self.assertEqual([round(x, 9) for x in t], [2.0, 0.5, 0.6])
        normal = K._vec(r, [1, 0, 0])
        self.assertAlmostEqual(normal[0], -1, places=12, msg="the tag's face points back at the robot")
        r, t = K.tag_in_robot("back", 2.0, 0.5, 0.6)
        self.assertEqual([round(x, 9) for x in t], [-2.0, -0.5, 0.6], "left, looking from the robot's back")


class SolveTest(unittest.TestCase):
    def test_a_front_camera_is_recovered_exactly_without_noise(self):
        r = K.solve("front", plant.camera_sightings(FRONT, SPOTS, noise_m=0, noise_deg=0))
        close(self, r["result"], FRONT, cm=1e-4, deg=1e-4)
        self.assertLess(r["spread"]["cm"], 1e-4)

    def test_with_camera_noise_it_lands_within_a_centimeter(self):
        r = K.solve("front", plant.camera_sightings(FRONT, SPOTS))
        close(self, r["result"], FRONT, cm=1.0, deg=0.5)
        self.assertFalse(any("disagree" in f["title"] for f in r["findings"]))
        self.assertEqual(r["edit"][:2], ("slothtune.json", ("cameras", "front")))
        self.assertEqual(set(r["edit"][2]), {"x", "y", "z", "roll", "pitch", "yaw"})

    def test_cameras_on_the_back_and_side(self):
        back = (-0.30, 0.05, 0.45, 0.0, -10.0, 180.0)
        spots = [dict(s, side="back") for s in SPOTS]
        close(self, K.solve("rear", plant.camera_sightings(back, spots, noise_m=0, noise_deg=0))["result"], back, 1e-4, 1e-4)
        side = (0.0, 0.33, 0.40, 2.0, -5.0, 92.0)
        spots = [dict(s, side="left") for s in SPOTS]
        close(self, K.solve("left", plant.camera_sightings(side, spots, noise_m=0, noise_deg=0))["result"], side, 1e-4, 1e-4)

    def test_a_tape_mistake_at_one_spot_shows_as_disagreement(self):
        placements = plant.camera_sightings(FRONT, SPOTS)
        placements[1]["distance_m"] += 0.10   # measured 10 cm wrong
        r = K.solve("front", placements)
        self.assertTrue(any("disagree by up to" in f["title"] for f in r["findings"]))

    def test_few_sightings_or_the_wrong_tag_leave_a_spot_out(self):
        placements = plant.camera_sightings(FRONT, SPOTS, n=3)
        r = K.solve("front", placements)
        self.assertIsNone(r["result"])
        placements = plant.camera_sightings(FRONT, SPOTS)
        placements[0]["tag_id"] = 8
        r = K.solve("front", placements)
        self.assertEqual(r["spread"]["spots"], 2)
        self.assertIn("Only 0 sightings of tag 8", r["per_placement"][0]["error"])

    def test_ambiguous_sightings_are_flagged(self):
        r = K.solve("front", plant.camera_sightings(FRONT, SPOTS, ambiguity=0.35))
        self.assertTrue(any("wasn't sure which way" in f["title"] for f in r["findings"]))

    def test_the_wrong_side_gives_an_impossible_height_and_no_edit(self):
        placements = plant.camera_sightings(FRONT, SPOTS)
        for p in placements:
            p["height_m"] = -0.6   # typed as a negative
        r = K.solve("front", placements)
        self.assertIsNone(r["edit"])
        self.assertTrue(any(f["level"] == "error" for f in r["findings"]))

    def test_the_change_from_the_current_mount_is_reported(self):
        cur = {"x": 0.30, "y": -0.12, "z": 0.52, "roll": 0, "pitch": -15, "yaw": 8}
        r = K.solve("front", plant.camera_sightings(FRONT, SPOTS, noise_m=0, noise_deg=0), cur)
        f = next(f for f in r["findings"] if "from what slothtune.json says" in f["title"])
        self.assertIn("2.0 cm and 3.0 degrees", f["title"])


class LinkTest(unittest.TestCase):
    def test_the_robots_flat_array_reads_back_as_sightings(self):
        # The layout SlothTune publishes (checked on the robot side by SlothTuneHarnessTest).
        from slothtune import contract as C, link

        topics = {C.LIVE_VISION_SIGHTINGS: [7, 1.5, 0.1, 0.2, 1, 0, 0, 0, 0.05, 12.5,
                                            3, 2.0, -0.4, 0.1, 0, 0, 0, 1, -1, 12.6],
                  C.LIVE_VISION_SIGHTING_CAMERAS: ["front", "rear"]}

        class Fake:
            def get(self, kind, name, default=None):
                return topics[name]

        got = link.RobotLink.sightings(Fake())
        self.assertEqual([(g["camera"], g["tag"]) for g in got], [("front", 7), ("rear", 3)])
        self.assertEqual((got[0]["x"], got[0]["qw"], got[0]["ambiguity"], got[0]["t"]), (1.5, 1, 0.05, 12.5))
        self.assertEqual(got[1]["qz"], 1)


if __name__ == "__main__":
    unittest.main()
