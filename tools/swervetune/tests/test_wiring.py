"""Wiring diagnosis: the map is found in the code, and each rule points at the right place."""

import os
import unittest

from swervetune import wiring as W, yagslcfg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PEA = yagslcfg.Project(os.path.join(REPO, "Peashooter"))
BLACK = yagslcfg.Project(os.path.join(REPO, "Black team"))

CHAIN = ["roboRIO", "FL drive", "FL steer", "FR drive", "FR steer", "Shooter", "PDH"]


def a_map(confirmed=True):
    return {"buses": [{"name": "roboRIO CAN", "chain": list(CHAIN), "orderConfirmed": confirmed,
                       "segmentLengthsM": {}}],
            "pdhPorts": {"FR drive": 3, "Shooter": 7}}


def rows(**kw):
    out = []
    for name in CHAIN[1:-1]:
        r = {"name": name, "present": 1, "dropouts": 0, "resets": 0, "brownouts": 0}
        r.update(kw.get(name.replace(" ", "_"), {}))
        out.append(r)
    return out


class DiscoveryTest(unittest.TestCase):
    def test_every_can_device_is_found_with_its_id(self):
        pea = {d["name"]: d["can_id"] for d in W.discover(PEA)}
        self.assertEqual(len(pea), 15)
        self.assertEqual(pea["Spindexter"], 14)
        self.assertEqual(pea["frontleft steer"], 6)
        black = {d["name"]: d["can_id"] for d in W.discover(BLACK)}
        self.assertEqual(black["Intake"], 9, "a CAN_ID constant is resolved")
        self.assertEqual(len(black), 10)

    def test_a_fresh_map_is_unconfirmed_and_ends_at_the_terminators(self):
        m = W.default_map(PEA)
        chain = m["buses"][0]["chain"]
        self.assertEqual((chain[0], chain[-1]), ("roboRIO", "PDH"))
        self.assertFalse(m["buses"][0]["orderConfirmed"])
        self.assertEqual(W.bus_length(m["buses"][0]), (8.0, 0, 16))


class RulesTest(unittest.TestCase):
    def find(self, snapshot, m=None):
        return W.diagnose(m or a_map(), snapshot)

    def test_a_tail_going_silent_is_the_cable_at_its_start(self):
        f = self.find({"motors": rows(FR_drive={"present": 0}, FR_steer={"present": 0}, Shooter={"present": 0})})
        self.assertEqual(len(f), 1)
        self.assertIn("Everything from FR drive", f[0]["title"])
        self.assertEqual(f[0]["where"]["segment"], ["FL steer", "FR drive"])

    def test_one_device_alone_is_its_power(self):
        f = self.find({"motors": rows(FR_drive={"present": 0})})
        self.assertIn("on its own", f[0]["title"])
        self.assertIn("PDH port 3", f[0]["why"])

    def test_the_last_device_alone_is_also_treated_as_alone(self):
        f = self.find({"motors": rows(Shooter={"present": 0})})
        self.assertIn("Shooter is off the CAN bus on its own", f[0]["title"])

    def test_an_intermittent_run_points_at_its_first_link(self):
        f = self.find({"motors": rows(FR_steer={"dropouts": 2}, Shooter={"dropouts": 2})})
        self.assertIn("from FR steer onward", f[0]["title"])
        self.assertEqual(f[0]["where"]["segment"], ["FR drive", "FR steer"])

    def test_reboots_point_at_power_and_many_point_upstream(self):
        one = self.find({"motors": rows(Shooter={"resets": 1})})
        self.assertIn("PDH port 7", one[0]["why"])
        many = self.find({"motors": rows(FL_drive={"resets": 1}, FR_drive={"resets": 1}, Shooter={"resets": 1})})
        self.assertTrue(any("3 controllers have rebooted" in x["title"] for x in many))

    def test_bus_errors(self):
        f = self.find({"motors": rows(), "can": [0.4, 2, 0, 12, 0]})
        titles = " | ".join(x["title"] for x in f)
        self.assertIn("shut itself down 2 times", titles)
        self.assertIn("CAN errors happening now", titles)

    def test_a_healthy_robot_has_nothing_to_say(self):
        self.assertEqual(self.find({"motors": rows(), "can": [0.3, 0, 0, 0, 0]}), [])

    def test_feed_resistance(self):
        samples = [(12.2, 12.2 - 0.05 * i - 0.08, i) for i in range(0, 40, 2)]
        self.assertAlmostEqual(W.feed_resistance(samples), 0.05, places=6)
        self.assertIsNone(W.feed_resistance([(12.2, 12.1, 2.0)] * 20), "needs a spread of current")
        f = self.find({"motors": rows(), "feed_r": {"Shooter": 0.08}})
        self.assertEqual(f[0]["level"], "error")
        self.assertIn("80 milliohms", f[0]["title"])

    def test_termination_readings(self):
        self.assertEqual(W.termination_verdict(61)["level"], "ok")
        self.assertIn("one terminator missing", W.termination_verdict(121)["title"])
        self.assertIn("too many", W.termination_verdict(40)["title"])
        self.assertIn("too low", W.termination_verdict(10)["title"])
        self.assertIn("open", W.termination_verdict(5000)["title"])


if __name__ == "__main__":
    unittest.main()
