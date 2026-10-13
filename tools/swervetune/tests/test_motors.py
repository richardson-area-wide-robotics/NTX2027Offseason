"""The laptop side of the motor guard: the contract mirror, the monitor's motor rules, the current
policy lint, and the kV/kS wear trend across saved runs."""

import glob
import json
import os
import re
import shutil
import tempfile
import unittest

from swervetune import advisor, contract as C, monitor, yagslcfg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
JAVA = os.path.join(REPO, "common", "swervetune", "java", "frc", "lib", "swervetune")
BLACK = os.path.join(REPO, "Black team")
PEA = os.path.join(REPO, "Peashooter")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class MotorContractTest(unittest.TestCase):
    def test_motor_kinds_match_the_robot(self):
        src = read(os.path.join(JAVA, "MotorKind.java"))
        java = {name: (label, int(amps), float(w), float(d), float(s)) for name, label, amps, _rpm, w, d, s in
                re.findall(r'(\w+)\("([^"]+)",\s*(\d+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),', src)}
        self.assertEqual(set(java), set(C.MOTOR_KINDS))
        for k, v in java.items():
            self.assertEqual(v, tuple(C.MOTOR_KINDS[k][:2]) + tuple(map(float, C.MOTOR_KINDS[k][2:])), k)

    def test_the_override_cap_matches(self):
        src = read(os.path.join(JAVA, "MotorGuard.java"))
        self.assertEqual(float(re.search(r"MAX_OVERRIDE_S\s*=\s*([\d.]+)", src).group(1)), C.MAX_OVERRIDE_S)

    def test_kinds_parse_the_same_way_on_both_sides(self):
        for text, kind in (("NEO 550", "NEO_550"), ("sparkmax_neo550", "NEO_550"),
                           ("sparkflex_vortex", "VORTEX"), ("NEO 2.0", "NEO_2_0"),
                           ("NEO V1.1", "NEO_V1_1"), ("sparkmax_neo", "NEO_UNKNOWN")):
            self.assertEqual(C.motor_kind_from_text(text), kind, text)

    def test_stages_match(self):
        src = read(os.path.join(JAVA, "MotorGuard.java"))
        body = re.search(r"enum Stage \{([^}]*)\}", src).group(1)
        self.assertEqual(tuple(re.findall(r"\w+", body)), C.STAGES)


def motor(name, stage="OK", temp=30.0, flags="", cause=""):
    return {"name": name, "kind": "NEO 550", "stage": stage, "cause": cause, "flags": flags,
            "heat_pct": 10.0, "temp": temp, "amps": 5.0, "limit": 20.0, "base_limit": 20.0,
            "stall_s": 0.0, "override_s": 0.0}


class MonitorMotorTest(unittest.TestCase):
    def snap(self, motors):
        return {"mode": "TELEOP", "steer": [0.0] * 4, "steer_sp": [0.0] * 4, "steer_motor": [0.0] * 4,
                "v": [0.0] * 4, "v_sp": [0.0] * 4, "drive_amps": [5] * 4, "abs_issue": [0] * 4,
                "drive_temp": [95] * 4, "steer_temp": [30] * 4, "faults": [""] * 4, "bus": 12.4,
                "motors": motors}

    def test_a_stepped_in_guard_and_a_failing_motor_are_flagged_by_name(self):
        m = monitor.Monitor(clock=lambda: 1.0)
        flags = m.update(self.snap([motor("Shooter leader", "DERATE", cause="heat estimate 72%"),
                                    motor("Feeder", flags="output but no current")]))
        got = {(f["rule"], f["module"]): f for f in flags}
        self.assertIn(("motor_hot", "Shooter leader"), got)
        self.assertEqual(got[("motor_hot", "Shooter leader")]["text"],
                         "Shooter leader motor is hot: the motor guard has stepped in.")
        self.assertIn(("motor_failing", "Feeder"), got)
        self.assertNotIn("hot", {f["rule"] for f in flags},
                         "with the guard running, the generic 70 C rule stands down")

    def test_one_swerve_motor_much_hotter_than_its_siblings(self):
        now = [0.0]
        m = monitor.Monitor(clock=lambda: now[0])
        group = [motor("frontleft drive", temp=62), motor("frontright drive", temp=44),
                 motor("backleft drive", temp=45), motor("backright drive", temp=43)]
        self.assertEqual([f for f in m.update(self.snap(group)) if f["rule"] == "motor_hotter_than_siblings"], [])
        now[0] = 5.1
        flags = [f for f in m.update(self.snap(group)) if f["rule"] == "motor_hotter_than_siblings"]
        self.assertEqual([f["module"] for f in flags], ["frontleft drive"])
        self.assertIn("62 °C vs 44 °C", flags[0]["detail"])

    def test_a_drivetrain_warm_all_over_is_not_a_sibling_problem(self):
        now = [0.0]
        m = monitor.Monitor(clock=lambda: now[0])
        group = [motor(f"{n} drive", temp=t) for n, t in
                 (("frontleft", 61), ("frontright", 58), ("backleft", 63), ("backright", 60))]
        m.update(self.snap(group))
        now[0] = 10
        self.assertFalse([f for f in m.update(self.snap(group)) if f["rule"] == "motor_hotter_than_siblings"])


class PolicyLintTest(unittest.TestCase):
    def black_team_with(self, motors, drive_type=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dst = os.path.join(tmp.name, "robot")
        shutil.copytree(BLACK, dst, ignore=shutil.ignore_patterns("build", ".gradle", "bin"))
        if drive_type:
            for f in glob.glob(os.path.join(dst, "src", "main", "deploy", "swerve", "modules", "*.json")):
                d = json.loads(read(f))
                if "drive" in d:
                    d["drive"]["type"] = drive_type
                    with open(f, "w", encoding="utf-8") as fh:
                        json.dump(d, fh)
        tune = os.path.join(dst, "src", "main", "deploy", "swerve", "swervetune.json")
        data = json.loads(read(tune))
        data["motors"] = motors
        with open(tune, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return {f["id"]: f for f in yagslcfg.lint(yagslcfg.Project(dst))}

    def test_black_team_as_built_is_within_policy(self):
        ids = {f["id"] for f in yagslcfg.lint(yagslcfg.Project(BLACK))}
        self.assertFalse({"drive_current_over_policy", "steer_current_over_policy"} & ids,
                         "Vortex drives allow 80 A")

    def test_black_team_drive_limit_is_over_the_unknown_neo_policy(self):
        # As a NEO on a SPARK MAX that the inventory doesn't name, 80 A is over the 60 A policy.
        found = self.black_team_with({"guard": True}, drive_type="sparkmax_neo")
        f = found["drive_current_over_policy"]
        self.assertIn("80 A is over the 60 A policy", f["title"])
        self.assertEqual(f["fix"]["value"], 60)
        self.assertNotIn("steer_current_over_policy", found)

    def test_saying_the_neos_are_1_1s_lowers_the_policy_to_60(self):
        self.assertIn("drive_current_over_policy", self.black_team_with({"drive": "NEO V1.1"}))

    def test_peashooter_is_within_policy(self):
        ids = {f["id"] for f in yagslcfg.lint(yagslcfg.Project(PEA))}
        self.assertFalse({"drive_current_over_policy", "steer_current_over_policy"} & ids)


def fits(kv, ks):
    names = ("frontleft", "frontright", "backleft", "backright")
    return {n: {"ok": True, "kV": v, "kS": s, "kA": 0.3, "r2": 0.99} for n, v, s in zip(names, kv, ks)}


class WearTrendTest(unittest.TestCase):
    HISTORY = [{"saved": "20260901-180000", "modules": fits([2.40, 2.44, 2.38, 2.42], [0.12, 0.11, 0.13, 0.12])},
               {"saved": "20260915-180000", "modules": fits([2.41, 2.43, 2.40, 2.41], [0.12, 0.12, 0.12, 0.12])}]

    def titles(self, now):
        return [f["title"] for f in advisor.motor_trend_findings(now, self.HISTORY)]

    def test_a_motor_whose_kv_fell_against_its_siblings_is_named(self):
        t = self.titles(fits([2.18, 2.44, 2.39, 2.42], [0.12, 0.12, 0.12, 0.12]))
        self.assertEqual(len(t), 1, t)
        self.assertTrue(t[0].startswith("frontleft: kV down 9% against the other modules since 2026-09-01"), t)

    def test_growing_drag_shows_as_ks_climbing(self):
        t = self.titles(fits([2.41, 2.43, 2.40, 2.41], [0.12, 0.12, 0.25, 0.12]))
        self.assertEqual(len(t), 1, t)
        self.assertTrue(t[0].startswith("backleft: needs"), t)

    def test_every_module_moving_together_is_not_one_bad_motor(self):
        self.assertEqual(self.titles(fits([2.20, 2.23, 2.19, 2.21], [0.15, 0.15, 0.15, 0.15])), [])

    def test_one_earlier_run_is_not_a_baseline(self):
        self.assertEqual(advisor.motor_trend_findings(fits([2.0, 2.44, 2.39, 2.42], [0.12] * 4),
                                                      self.HISTORY[:1]), [])


if __name__ == "__main__":
    unittest.main()
