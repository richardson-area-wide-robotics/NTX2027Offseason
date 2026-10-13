"""REV's published numbers, and every copy of them in the tools and the robot code, agree."""

import os
import re
import unittest

from swervetune import advisor, plant, ratios, revspecs as R, yagslcfg as Y

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
JAVA = os.path.join(REPO, "common", "swervetune", "java", "frc", "lib", "swervetune")


class MotorsTest(unittest.TestCase):
    def test_kv_is_free_speed_over_12_volts(self):
        for key, m in R.MOTORS.items():
            self.assertAlmostEqual(m["kv_rpm_per_v"], m["free_rpm"] / 12, delta=0.01 * m["kv_rpm_per_v"], msg=key)

    def test_the_practice_pod_uses_reves_numbers(self):
        for key in ("neo", "vortex", "neo550"):
            stall_nm, stall_a, free_a, free_rpm = plant.MOTORS[key]
            m = R.MOTORS[key]
            self.assertEqual((stall_nm, stall_a, free_a, free_rpm),
                             (m["stall_nm"], m["stall_a"], m["free_a"], m["free_rpm"]), key)
            self.assertEqual(Y.MOTORS[key], plant.MOTORS[key], f"{key}: yagslcfg and the pod agree")

    def test_the_advisor_and_the_robots_motor_table_agree(self):
        for key, rpm in advisor.MOTOR_FREE_RPM.items():
            self.assertEqual(rpm, R.MOTORS[key]["free_rpm"])
        src = open(os.path.join(JAVA, "MotorKind.java"), encoding="utf-8").read()
        rows = {label: float(rpm) for label, rpm in
                re.findall(r'\w+\("([^"]+)",\s*\d+,\s*([\d.]+),', src)}
        for label, key in R.LABEL_TO_KEY.items():
            self.assertEqual(rows[label], R.MOTORS[key]["free_rpm"], label)

    def test_the_team_policy_stays_inside_reves_advice_where_rev_gives_any(self):
        src = open(os.path.join(JAVA, "MotorKind.java"), encoding="utf-8").read()
        policy = {label: int(a) for label, a in re.findall(r'\w+\("([^"]+)",\s*(\d+),', src)}
        for label, key in R.LABEL_TO_KEY.items():
            advice = R.MOTORS[key]["current_limit_a"]
            if advice:
                self.assertLessEqual(policy[label], advice[1], label)


class SpeedSensorTest(unittest.TestCase):
    def test_a_vortex_on_a_flex_is_fine_grained_and_quick(self):
        self.assertEqual(R.drive_speed_sensor("vortex")[:3], (10, 2, 7168))
        self.assertEqual(R.drive_speed_sensor("neo")[:3], (32, 8, 42))

    def test_yagsl_really_sets_10_ms_x_2_on_a_spark_flex(self):
        # The number above is read off YAGSL's bytecode (SparkFlexSwerve.configureIntegratedEncoder);
        # this keeps the claim next to where the robots set it.
        src = open(os.path.join(JAVA, "YagslDrivetrainIO.java"), encoding="utf-8").read()
        self.assertIn("quadratureMeasurementPeriod", src, "the Flex's filter is the quadrature one")


class FirmwareTest(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(R.firmware_tuple("v26.1.5"), (26, 1, 5))
        self.assertIsNone(R.firmware_tuple("unknown"))

    def test_findings(self):
        self.assertIsNone(R.firmware_finding("SPARK MAX", "26.1.5"))
        self.assertIsNone(R.firmware_finding("SPARK MAX", ""))
        self.assertEqual(R.firmware_finding("SPARK Flex", "v26.1.0")[0], "info")
        level, title, why = R.firmware_finding("SPARK MAX", "v25.0.4")
        self.assertEqual(level, "warn")
        self.assertIn("Hardware Client 2", why)


class MaxSwerveTest(unittest.TestCase):
    def test_every_ratio_is_three_times_spur_over_pinion(self):
        for name, ratio, p, s in R.MAXSWERVE["drive_ratios"]:
            self.assertAlmostEqual(3 * int(s[:-1]) / int(p[:-1]), ratio, delta=0.006, msg=name)

    def test_reves_free_speeds_match_ours(self):
        for ratio, speeds in R.MAXSWERVE["free_speed_mps"].items():
            for kind, mps in speeds.items():
                exact = next(3 * int(s[:-1]) / int(p[:-1]) for _, r, p, s in R.MAXSWERVE["drive_ratios"] if r == ratio)
                self.assertAlmostEqual(Y.free_speed_mps(kind, exact, 3.0), mps, delta=0.015, msg=(ratio, kind))

    def test_the_ratio_finder_offers_only_gears_rev_sells(self):
        self.assertEqual(len(ratios.MAXSWERVE_DRIVE), 8)
        self.assertIn("MAXSwerve Low: 12T pinion, 22T spur", [n for n, _ in ratios.MAXSWERVE_DRIVE])
        self.assertAlmostEqual(R.MAXSWERVE["steer_ratio"], 46.42, places=2)


class DocsTest(unittest.TestCase):
    def test_the_student_reference_names_every_part(self):
        text = open(os.path.join(REPO, "docs", "REV_HARDWARE.md"), encoding="utf-8").read()
        for m in R.MOTORS.values():
            self.assertIn(m["part"], text)
        for c in R.CONTROLLERS.values():
            self.assertIn(c["part"], text)
            self.assertIn(c["latest_firmware"], text)
        self.assertIn(R.MAXSWERVE["part"], text)

    @staticmethod
    def _table(text, first_header):
        """A markdown table's rows as {first cell: [the other cells]}, from the one whose header row
        starts with ``first_header``."""
        lines = text.splitlines()
        start = next(i for i, ln in enumerate(lines) if ln.startswith("|") and ln.split("|")[1].strip() == first_header)
        rows = {}
        for ln in lines[start + 2:]:
            if not ln.startswith("|"):
                break
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows[cells[0]] = cells[1:]
        return rows

    def test_the_motor_table_matches_the_numbers_the_tools_use(self):
        text = open(os.path.join(REPO, "docs", "REV_HARDWARE.md"), encoding="utf-8").read()
        rows = self._table(text, "")
        order = ["neo", "neo2", "vortex", "neo550"]
        first = lambda cell: float(re.match(r"[\d.]+", cell.replace(",", "")).group())  # noqa: E731
        for field, key, scale in (("Kv (rpm per volt)", "kv_rpm_per_v", 1), ("Free speed", "free_rpm", 1),
                                  ("Free current", "free_a", 1), ("Stall current", "stall_a", 1),
                                  ("Stall torque", "stall_nm", 1), ("Peak power", "peak_w", 1),
                                  ("Weight", "mass_kg", 1000)):
            for cell, k in zip(rows[field], order):
                self.assertAlmostEqual(first(cell), R.MOTORS[k][key] * scale, places=3, msg=(field, k, cell))
        self.assertEqual(rows["Part"], [R.MOTORS[k]["part"] for k in order])

    def test_the_maxswerve_table_matches_the_ratios_and_free_speeds(self):
        text = open(os.path.join(REPO, "docs", "REV_HARDWARE.md"), encoding="utf-8").read()
        rows = self._table(text, "REV's name")
        self.assertEqual(len(rows), len(ratios.MAXSWERVE_DRIVE))
        for name, ratio in ratios.MAXSWERVE_DRIVE:
            short = name.split(":")[0].replace("MAXSwerve ", "")
            ratio_cell, _, _, neo, vortex = rows[short]
            self.assertAlmostEqual(float(ratio_cell.split(":")[0]), ratio, delta=0.005, msg=short)
            self.assertAlmostEqual(float(neo.split()[0]), Y.free_speed_mps("neo", ratio, 3.0), delta=0.015, msg=short)
            self.assertAlmostEqual(float(vortex.split()[0]), Y.free_speed_mps("vortex", ratio, 3.0), delta=0.015, msg=short)


if __name__ == "__main__":
    unittest.main()
