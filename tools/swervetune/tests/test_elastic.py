"""The drive team's Elastic layout points at the topics the robot really publishes."""

import json
import os
import re
import unittest

from swervetune import contract as C, elastic

HERE = os.path.dirname(os.path.abspath(__file__))
JAVA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "common", "swervetune", "java",
                    "frc", "lib", "swervetune")


class ElasticLayoutTest(unittest.TestCase):
    def test_the_committed_file_is_what_the_generator_makes(self):
        with open(elastic.LAYOUT_FILE, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), elastic.text(), "run: py -3.12 -c \"from swervetune import elastic; elastic.write()\"")

    def test_widgets_read_the_robots_topics(self):
        ws = elastic.layout()["tabs"][0]["grid_layout"]["containers"]
        by_type = {w["type"]: w for w in ws}
        self.assertEqual(by_type["ComboBox Chooser"]["properties"]["topic"] + "/selected", C.BATTERY_SELECTED)
        self.assertEqual(by_type["Text Display"]["properties"]["topic"], C.BATTERY_CHECK)
        src = open(os.path.join(JAVA, "DashboardAlerts.java"), encoding="utf-8").read()
        group = re.search(r'GROUP\s*=\s*"([^"]+)"', src).group(1)
        self.assertEqual(by_type["Alerts"]["properties"]["topic"], "/SmartDashboard/" + group)

    def test_no_bare_numbers_for_the_drive_team(self):
        # A verdict in words beats a voltage to interpret, and NaN at boot reads as broken.
        topics = {w["properties"]["topic"] for w in elastic.layout()["tabs"][0]["grid_layout"]["containers"]}
        self.assertNotIn(C.BATTERY_REST_VOLTS, topics)
        self.assertNotIn(C.LIVE_BUS_VOLTS, topics)

    def test_widgets_fit_the_grid(self):
        d = elastic.layout()
        for w in d["tabs"][0]["grid_layout"]["containers"]:
            for k in ("x", "y", "width", "height"):
                self.assertEqual(w[k] % d["grid_size"], 0, (w["title"], k))
        json.dumps(d)


if __name__ == "__main__":
    unittest.main()
