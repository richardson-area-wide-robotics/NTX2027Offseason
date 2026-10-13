"""The advisor converges on the practice pod; the linter finds what is really wrong with both
robots; the troubleshooter, linter, monitor and advisor all point at things that exist."""

import os
import re
import shutil
import tempfile
import unittest

from swervetune import advisor, diagnose, monitor, rehearse, yagslcfg

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PKG))
BLACK = os.path.join(REPO, "Black team")
PEA = os.path.join(REPO, "Peashooter")


class AdvisorConvergesTest(unittest.TestCase):
    def test_steering_from_black_team_gains_on_carpet(self):
        h = rehearse.rehearse("steer", {"Steer/kP": 0.01, "Steer/kI": 0, "Steer/kD": 0.001,
                                        "Steer/IZone": 0, "Steer/RampS": 0.25}, surface="floor")
        self.assertEqual(h[-1]["score"], 100, h[-1])
        # Each step is held to double or half (the agent's rule), so a far-off start takes a few more rounds.
        self.assertLessEqual(len(h), 10, "took too many rounds")
        self.assertLess(h[-1]["cost"], h[0]["cost"])

    def test_steering_from_too_aggressive(self):
        h = rehearse.rehearse("steer", {"Steer/kP": 0.15, "Steer/kI": 0, "Steer/kD": 0.0,
                                        "Steer/IZone": 0, "Steer/RampS": 0.0}, surface="blocks")
        self.assertEqual(h[-1]["score"], 100, h[-1])

    def test_drive_from_black_team_gains_measures_feedforward_first(self):
        h = rehearse.rehearse("drive", {"Drive/kP": 0.0020645, "Drive/kD": 0, "Drive/RampS": 0.25,
                                        "Drive/VelPeriodMs": 0, "Drive/VelDepth": 0})
        self.assertEqual(h[-1]["score"], 100, h[-1])
        self.assertTrue(any("feedforward" in (e["advice"] or "") for e in h))
        self.assertGreater(h[-1]["ff"]["FF/frontleft/kA"], 0.2, "measured kA was applied")
        self.assertGreater(h[-1]["gains"]["Drive/kP"], 0.0020645, "kP was not walked to zero")

    def test_drive_from_peashooter_gains(self):
        h = rehearse.rehearse("drive", {"Drive/kP": 1.0, "Drive/kD": 0.4, "Drive/RampS": 0.25,
                                        "Drive/VelPeriodMs": 0, "Drive/VelDepth": 0})
        self.assertEqual(h[-1]["score"], 100, h[-1])

    def test_empty_runs_never_pass(self):
        for test in ("steer_step", "drive_step", "drive_ff", "spin", "straight", "capture"):
            r = advisor.analyze({"test": test, "channels": {}, "message": "aborted"})
            self.assertIsNone(r["score"], test)
            self.assertEqual(r["findings"][0]["level"], "error", test)

    def test_practice_runs_are_labeled(self):
        h = rehearse._steer_once({"Steer/kP": 0.02}, "floor")
        r = advisor.analyze(h, {"Steer/kP": 0.02})
        self.assertIn("Practice pod", r["findings"][0]["title"])


class LintRealRobotsTest(unittest.TestCase):
    def ids(self, path):
        return {f["id"] for f in yagslcfg.lint(yagslcfg.Project(path))}

    def test_black_team(self):
        ids = self.ids(BLACK)
        for expected in ("drive_inversion_mixed", "offsets_duplicate", "steer_ramp",
                         "drive_current_over_traction", "imu_spi_2027"):
            self.assertIn(expected, ids)
        self.assertNotIn("max_speed_unreal", ids)

    def test_peashooter(self):
        ids = self.ids(PEA)
        # PathPlanner's robot model was made to match on this branch; "Shoot B" stays unregistered.
        for expected in ("pathplanner_names", "pathplanner_defaults", "drive_p_hot", "steer_ramp"):
            self.assertIn(expected, ids)
        self.assertNotIn("drive_inversion_mixed", ids)
        self.assertNotIn("max_speed_unreal", ids, "fixed: createSwerveDrive(MAX_SPEED = 3.9)")

    def test_an_impossible_max_speed_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "robot")
            shutil.copytree(PEA, dst, ignore=shutil.ignore_patterns("build", ".gradle", "bin"))
            drive = os.path.join(dst, "src", "main", "java", "frc", "robot", "Drive.java")
            with open(drive, encoding="utf-8") as fh:
                src = fh.read()
            with open(drive, "w", encoding="utf-8") as fh:
                fh.write(src.replace("createSwerveDrive(MAX_SPEED,", "createSwerveDrive(40,"))
            self.assertIn("max_speed_unreal", self.ids(dst))

    def test_physics(self):
        p = yagslcfg.Project(PEA)
        self.assertAlmostEqual(p.max_module_speed(), 4.921, delta=0.01, msg="Vortex at 5.5:1, 3 in")
        self.assertAlmostEqual(yagslcfg.traction_current("neo", 5.5, 3.0, 55, 1.19), 47, delta=2)
        self.assertAlmostEqual(yagslcfg.traction_current("vortex", 5.5, 3.0, 55, 1.19), 69, delta=2)


class JsonEditTest(unittest.TestCase):
    def test_only_the_value_changes(self):
        text = '{\n  "a": 1,\n  "b": { "c": 263, "d": [1, 2] },\n  "e": "x"\n}\n'
        out = yagslcfg.json_set(text, ("b", "c"), 263.25)
        self.assertEqual(out, text.replace("263", "263.25"))
        self.assertEqual(yagslcfg.json_set(text, ("e",), "y"), text.replace('"x"', '"y"'))

    def test_a_new_key_is_added(self):
        out = yagslcfg.json_set('{"a": 1}', ("b", "c"), True)
        self.assertIn('"c": true', out)

    def test_editing_a_copy_of_a_real_project(self):
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "Peashooter")
            shutil.copytree(os.path.join(PEA, "src", "main", "deploy"), os.path.join(dst, "src", "main", "deploy"))
            p = yagslcfg.Project(dst)
            edits = yagslcfg.edits_for_gains(p, {"Steer/kP": 0.02, "Steer/RampS": 0.0,
                                                 "FF/frontleft/kS": 0.12, "Drive/VelPeriodMs": 16})
            text = p.apply(edits)
            self.assertIn('"p": 0.02', text)
            p2 = yagslcfg.Project(dst)
            self.assertEqual(p2.pidf["angle"]["p"], 0.02)
            self.assertEqual(p2.phys["rampRate"]["angle"], 0)
            self.assertEqual(p2.tune["driveFeedforward"]["frontleft"]["kS"], 0.12)
            self.assertEqual(p2.tune["driveVelocityFilter"]["periodMs"], 16)
            changed = [l for l in text.splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
            self.assertLessEqual(len(changed), 10, "an edit must not reformat whole files")
        finally:
            shutil.rmtree(tmp)


class CrossReferenceTest(unittest.TestCase):
    """Every pointer between modules must land on something real."""

    def test_symptom_links(self):
        known = set(diagnose.BY_ID)
        for name in ("advisor.py", "monitor.py", "diagnose.py", "yagslcfg.py"):
            src = open(os.path.join(PKG, name), encoding="utf-8").read()
            for sym in re.findall(r'"symptom":\s*"(\w+)"', src):
                self.assertIn(sym, known, f"{name} points at missing symptom {sym}")
        for rule, (sym, _) in monitor.RULES.items():
            self.assertIn(sym, known, f"monitor rule {rule}")

    def test_lint_and_monitor_evidence_exist(self):
        src = open(os.path.join(PKG, "yagslcfg.py"), encoding="utf-8").read()
        lint_ids = set(re.findall(r'_f\(\s*[^,]+,\s*f?"([\w{}]+)"', src))
        lint_ids |= {"drive_f_ignored", "angle_f_ignored"}
        lint_ids |= {i.replace("{part}", p) for i in lint_ids if "{part}" in i for p in ("drive", "steer")}
        for s in diagnose.SYMPTOMS:
            for c in s["checks"]:
                for lid in (c.get("auto") or {}).get("lint", []):
                    self.assertIn(lid, lint_ids, f"{s['id']} expects lint id {lid}")
                for rule in (c.get("auto") or {}).get("monitor", []):
                    self.assertIn(rule, monitor.RULES, f"{s['id']} expects monitor rule {rule}")


class MonitorTest(unittest.TestCase):
    def live(self, v, v_sp, steer=0.0):
        return {"mode": "TELEOP", "steer": [steer] * 4, "steer_sp": [0.0] * 4, "steer_motor": [steer] * 4,
                "v": v, "v_sp": v_sp, "drive_amps": [5] * 4, "abs_issue": [0] * 4,
                "drive_temp": [30] * 4, "steer_temp": [30] * 4, "faults": [""] * 4, "bus": 12.4}

    def test_backwards_wheel_needs_to_persist_then_clears(self):
        now = [0.0]
        m = monitor.Monitor(clock=lambda: now[0])
        names = ["fl", "fr", "bl", "br"]
        snap = self.live([1.0, 1.0, -1.0, 1.0], [1.0] * 4)
        self.assertEqual(m.update(snap, names), [])
        now[0] = 0.4
        flags = m.update(snap, names)
        self.assertEqual([(f["rule"], f["module"]) for f in flags], [("drive_backwards", "bl")])
        now[0] = 0.5
        m.update(self.live([1.0] * 4, [1.0] * 4), names)
        now[0] = 1.6
        self.assertEqual(m.update(self.live([1.0] * 4, [1.0] * 4), names), [])

    def test_disabled_robot_raises_nothing_about_motion(self):
        m = monitor.Monitor(clock=lambda: 10.0)
        snap = self.live([0.0] * 4, [2.0] * 4)
        snap["mode"] = "DISABLED"
        self.assertEqual(m.update(snap), [])


if __name__ == "__main__":
    unittest.main()
