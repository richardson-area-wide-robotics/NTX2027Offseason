"""Status lights (web/blinks.js): every device a check points at is described, from its maker's page,
and the fault words that mark a light "should show now" are the ones the robot code reports."""

import os
import re
import unittest

from swervetune import diagnose

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


SRC = read(os.path.join(WEB, "blinks.js"))
DEVICES = re.findall(r'^    "([^"]+)": \{ pic:', SRC, re.M)
ORDER = re.findall(r'"([^"]+)"', re.search(r"const ORDER = \[([^\]]+)\]", SRC).group(1))


class BlinksTest(unittest.TestCase):
    def test_the_devices_were_read(self):
        self.assertGreaterEqual(len(DEVICES), 9)
        for d in ("SPARK MAX", "SPARK Flex", "roboRIO", "SystemCore", "RSL", "VH-109 radio", "REV PDH", "navX", "Canandgyro"):
            self.assertIn(d, DEVICES)

    def test_the_picker_lists_every_device_once(self):
        self.assertEqual(sorted(ORDER), sorted(DEVICES))
        self.assertEqual(len(ORDER), len(set(ORDER)))

    def test_every_light_a_check_points_at_is_described(self):
        seen = 0
        for s in diagnose.SYMPTOMS:
            for c in s["checks"]:
                for d in c.get("lights", []):
                    self.assertIn(d, DEVICES, f"{s['id']}: {c['q']}")
                    seen += 1
        self.assertGreater(seen, 5, "the checks whose drawings show a light offer what it means")

    def test_a_check_offers_the_radio_lights(self):
        cs = diagnose.evaluate("no_comms")["checks"]
        self.assertTrue(any("VH-109 radio" in c.get("lights", []) for c in cs))

    def test_each_device_names_its_makers_page(self):
        for url in re.findall(r'url: "([^"]+)"', SRC):
            self.assertRegex(url, r"^https://(docs\.(revrobotics\.com|wpilib\.org|reduxrobotics\.com)|www\.kauailabs\.com|"
                                  r"downloads\.limelightvision\.io)/")

    def test_an_unsettled_source_says_so(self):
        # SystemCore's lights come from an alpha specification: its card must say so wherever it shows.
        sc = SRC[SRC.index('"SystemCore": {'):SRC.index('"RSL": {')]
        self.assertIn("caution:", sc)
        self.assertIn("subject to change", sc)

    def test_the_fault_words_are_the_robot_codes(self):
        # "Should show now" matches a controller's fault report by these words.
        java = read(os.path.join(REPO, "common", "swervetune", "java", "frc", "lib", "swervetune", "YagslDrivetrainIO.java"))
        words = re.findall(r'"([^"]+)"', re.search(r"\[(\"CAN fault\"[^\]]+)\]", SRC).group(1))
        self.assertIn("gate driver fault", words)
        for w in words:
            self.assertIn(f'"{w}"' if w in ("CAN ID conflict", "hardware fault") else f' {w}"', java, w)

    def test_spark_fault_rows_carry_those_words(self):
        for w in ("sensor fault", "gate driver fault", "CAN fault", "over temperature"):
            self.assertRegex(SRC, r'id: "' + w + '"', w)


if __name__ == "__main__":
    unittest.main()
