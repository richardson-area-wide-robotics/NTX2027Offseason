"""A controller's settings as the robot publishes them (link.motor_settings), and the endpoint
that clears every sticky fault."""

import unittest
from unittest import mock

from slothtune import link, server


class SettingsTest(unittest.TestCase):
    def test_numbers_and_words(self):
        s = link.motor_settings("idle=brake;stallA=40;kP=0.0123;mmCruise=2.5e+03;sensor=PrimaryEncoder")
        self.assertEqual(s, {"idle": "brake", "stallA": 40.0, "kP": 0.0123, "mmCruise": 2500.0, "sensor": "PrimaryEncoder"})

    def test_nothing_or_broken_parts_are_left_out(self):
        self.assertEqual(link.motor_settings(""), {})
        self.assertEqual(link.motor_settings(None), {})
        self.assertEqual(link.motor_settings("x;=3;y="), {})


class ClearStickyTest(unittest.TestCase):
    def test_needs_the_robot(self):
        with mock.patch.object(server.S, "link", None):
            self.assertFalse(server.api_motors_clear_sticky({})["ok"])

    def test_passes_on_the_robots_answer(self):
        lk = mock.Mock()
        lk.is_connected.return_value = True
        lk.clear_sticky.return_value = "Cleared the sticky faults on 12 controllers, and the counts."
        with mock.patch.object(server.S, "link", lk):
            r = server.api_motors_clear_sticky({})
        self.assertTrue(r["ok"])
        self.assertIn("12 controllers", r["message"])

    def test_no_answer_is_not_ok(self):
        lk = mock.Mock()
        lk.is_connected.return_value = True
        lk.clear_sticky.return_value = "No answer from the robot about clearing the sticky faults."
        with mock.patch.object(server.S, "link", lk):
            self.assertFalse(server.api_motors_clear_sticky({})["ok"])


if __name__ == "__main__":
    unittest.main()
