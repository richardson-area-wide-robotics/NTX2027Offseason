"""Where the tool looks for a robot: 10.TE.AM.2 for any team number (link.candidate_hosts)."""

import unittest

from slothtune import link as L


class HostsTest(unittest.TestCase):
    def test_a_four_digit_team(self):
        self.assertEqual(L.candidate_hosts(1745)[:2], ["10.17.45.2", "roborio-1745-frc.local"])

    def test_a_five_digit_test_robot(self):
        # 17451 and 17452: TE is the leading digits, AM the last two, as WPILib does it.
        self.assertEqual(L.candidate_hosts(17451)[:2], ["10.174.51.2", "roborio-17451-frc.local"])
        self.assertEqual(L.candidate_hosts(17452)[0], "10.174.52.2")

    def test_a_short_team_number(self):
        self.assertEqual(L.candidate_hosts(254)[0], "10.2.54.2")

    def test_never_this_laptops_own_address(self):
        # Hyper-V's switch takes 172.26.0.1 on some laptops: with the simulator running, that would be it.
        self.assertNotIn("172.26.0.1", L.candidate_hosts(1745, own={"172.26.0.1"}))
        self.assertIn("172.26.0.1", L.candidate_hosts(1745, own=set()))

    def test_usb_and_systemcore_are_always_tried(self):
        self.assertIn("172.22.11.2", L.candidate_hosts(17451))
        self.assertIn("robot.local", L.candidate_hosts(None))


if __name__ == "__main__":
    unittest.main()
