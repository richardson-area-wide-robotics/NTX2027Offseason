"""The team's units (units.py): ft/s, inches, pounds, foot-pounds and degrees for what a person
reads, converted from the robot's SI at the last step and back for what a person types."""

import math
import unittest

from slothtune import units as U


class NumbersTest(unittest.TestCase):
    def test_known_conversions(self):
        self.assertAlmostEqual(U.fps(1.0), 3.28084, places=5)
        self.assertAlmostEqual(U.inches(1.0), 39.3701, places=4)
        self.assertAlmostEqual(U.lb(1.0), 2.20462, places=5)
        self.assertAlmostEqual(U.ftlb(1.0), 0.737562, places=6)
        self.assertAlmostEqual(U.deg(math.pi), 180.0)
        self.assertAlmostEqual(U.inches(0.0254), 1.0)
        self.assertAlmostEqual(U.fps(0.3048), 1.0)
        self.assertAlmostEqual(U.lb(0.45359237), 1.0)

    def test_round_trips(self):
        for v in (0.0, 0.37, 1.0, 4.5, -2.25, 123.456):
            self.assertAlmostEqual(U.mps_from_fps(U.fps(v)), v)
            self.assertAlmostEqual(U.m_from_in(U.inches(v)), v)
            self.assertAlmostEqual(U.kg_from_lb(U.lb(v)), v)
            self.assertAlmostEqual(U.nm_from_ftlb(U.ftlb(v)), v)
            self.assertAlmostEqual(U.rad_from_deg(U.deg(v)), v)

    def test_typed_team_units_back_to_the_robots(self):
        self.assertAlmostEqual(U.m_from_in(120), 3.048)
        self.assertAlmostEqual(U.mps_from_fps(10), 3.048)
        self.assertAlmostEqual(U.kg_from_lb(125), 56.699, places=3)
        self.assertAlmostEqual(U.rad_from_deg(90), math.pi / 2)


class WordsTest(unittest.TestCase):
    def test_each_unit_is_named(self):
        self.assertEqual(U.speed(1.5), "4.92 ft/s")
        self.assertEqual(U.speed(1.5, 1), "4.9 ft/s")
        self.assertEqual(U.speed(-1.5, sign=True), "-4.92 ft/s")
        self.assertEqual(U.speed(1.5, sign=True), "+4.92 ft/s")
        self.assertEqual(U.accel(3.0), "9.8 ft/s²")
        self.assertEqual(U.length(0.05), "2.0 in")
        self.assertEqual(U.length(0.0254, 2), "1.00 in")
        self.assertEqual(U.mass(50.0), "110 lb")
        self.assertEqual(U.torque(2.6), "1.9 ft·lb")
        self.assertEqual(U.inertia(6.0), "20503 lb·in²")
        self.assertEqual(U.angle(math.pi), "180.0°")
        self.assertEqual(U.angvel(math.pi), "180°/s")
        self.assertEqual(U.angaccel(2 * math.pi), "360°/s²")

    def test_speed_is_never_fps(self):
        # The camera's frames per second share the pages: a speed always says ft/s.
        self.assertNotIn("fps", U.speed(2.0))
        self.assertTrue(U.speed(2.0).endswith(" ft/s"))

    def test_missing_numbers_read_as_a_question_mark(self):
        for f in (U.speed, U.accel, U.length, U.mass, U.torque, U.inertia, U.angle, U.angvel, U.angaccel):
            for v in (None, float("nan"), float("inf")):
                self.assertTrue(f(v).startswith("?"), (f.__name__, v, f(v)))


class SystemUnitTest(unittest.TestCase):
    def test_metric_and_radians_show_in_the_teams(self):
        label, k = U.system_unit("meters")
        self.assertEqual(label, "in")
        self.assertAlmostEqual(k, 39.3701, places=4)
        self.assertEqual(U.system_unit("Meters")[0], "in", "case doesn't matter")
        self.assertEqual(U.system_unit(" m ")[0], "in")
        self.assertEqual(U.system_unit("m/s")[0], "ft/s")
        self.assertAlmostEqual(U.system_unit("m/s")[1], 3.28084, places=5)
        self.assertEqual(U.system_unit("radians")[0], "deg")
        self.assertAlmostEqual(U.system_unit("radians")[1], 180 / math.pi)
        self.assertAlmostEqual(U.system_unit("cm")[1], 1 / 2.54)
        self.assertAlmostEqual(U.system_unit("mm")[1], 1 / 25.4)
        self.assertEqual(U.system_unit("kg")[0], "lb")

    def test_anything_else_stays_as_it_is(self):
        self.assertEqual(U.system_unit("RPM"), ("RPM", 1.0))
        self.assertEqual(U.system_unit("motor rotations"), ("motor rotations", 1.0))
        self.assertEqual(U.system_unit("degrees"), ("degrees", 1.0))
        self.assertEqual(U.system_unit(None), ("", 1.0))
        self.assertEqual(U.system_unit(""), ("", 1.0))


if __name__ == "__main__":
    unittest.main()
