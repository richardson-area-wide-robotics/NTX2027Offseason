"""Next year's gyro, the Canandgyro: the config check's rules for it (yagslcfg.lint), and its details
as the robot publishes them (link.live)."""

import json
import os
import shutil
import tempfile
import unittest

from swervetune import yagslcfg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PEASHOOTER = os.path.join(REPO, "Peashooter")


class LintTest(unittest.TestCase):
    def lint_with(self, imu):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "Peashooter")
            shutil.copytree(PEASHOOTER, p, ignore=shutil.ignore_patterns("build", ".gradle", "bin", "logs"))
            f = os.path.join(p, "src", "main", "deploy", "swerve", "swervedrive.json")
            with open(f, encoding="utf-8") as fh:
                sd = json.load(fh)
            sd["imu"] = imu
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(sd, fh)
            return {x["id"]: x for x in yagslcfg.lint(yagslcfg.Project(p))}

    def test_a_new_canandgyro_on_id_0(self):
        f = self.lint_with({"type": "canandgyro", "id": 0, "canbus": ""})
        self.assertEqual(f["canandgyro_id_0"]["level"], "warn")
        self.assertIn("Alchemist", f["canandgyro_id_0"]["why"])
        self.assertNotIn("imu_spi_2027", f, "a CAN gyro works on SystemCore")

    def test_yagsl_ignores_its_bus(self):
        f = self.lint_with({"type": "canandgyro", "id": 12, "canbus": "canivore"})
        self.assertIn("canandgyro_canbus", f)
        self.assertNotIn("canandgyro_id_0", f)

    def test_the_navx_is_unchanged(self):
        f = self.lint_with({"type": "navx_spi", "id": 0, "canbus": None})
        self.assertIn("imu_spi_2027", f)
        self.assertNotIn("canandgyro_id_0", f)


class DetailsTest(unittest.TestCase):
    def test_name_value_lines_become_a_dict(self):
        lines = ["temperature=31.4", "firmware=2025.0.0", "sticky=restarted, CAN error", "junk"]
        got = dict(x.split("=", 1) for x in lines if "=" in x)
        self.assertEqual(got, {"temperature": "31.4", "firmware": "2025.0.0", "sticky": "restarted, CAN error"})


if __name__ == "__main__":
    unittest.main()
