"""The robot runs the monitor's rules itself (ModuleWatch.java), so they watch matches with no laptop
connected. Its rules must be the laptop's (names, hold times, words, thresholds); the laptop shows the
robot's flags for those rules instead of judging them again, keeps the rest, and the post-match
summary words every check the robot logs.
"""

import os
import re
import unittest

from slothtune import contract as C
from slothtune import link as L
from slothtune import logsummary, monitor

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
WATCH_JAVA = os.path.join(REPO, "common", "slothtune", "java", "frc", "lib", "slothtune", "ModuleWatch.java")
NAMES = ["fl", "fr", "bl", "br"]


def java_source():
    with open(WATCH_JAVA, encoding="utf-8") as fh:
        src = fh.read()
    # Adjacent literals joined, escapes read: the text a person sees.
    return re.sub(r'"\s*\+\s*"', "", src).replace("\\u00b0", "°").replace('\\"', '"')


def java_rules():
    """{laptop rule: (log name, hold s)} from ModuleWatch.Rule."""
    return {laptop: (key, float(hold)) for key, laptop, hold in re.findall(
        r'^\s+[A-Z_]+\("(\w+)", "(\w+)", Scope\.\w+, ([\d.]+), (?:true|false), Show\.\w+,', java_source(), re.M)}


class TheRobotsRulesAreTheLaptopsTest(unittest.TestCase):
    def test_every_rule_is_judged_somewhere_and_the_split_is_the_documented_one(self):
        rules = java_rules()
        self.assertEqual(set(rules), set(monitor.ON_ROBOT))
        self.assertEqual(monitor.ON_ROBOT | monitor.LAPTOP_ONLY, set(monitor.RULES))
        self.assertEqual(monitor.LAPTOP_ONLY, {"motor_hot", "motor_failing"})
        self.assertRegex(java_source(), r"motor_hot\s*\*?\s*and motor_failing, only put words",
                         "the robot's code says why they stay on the laptop")

    def test_hold_times_and_log_names_match(self):
        for rule, (key, hold) in java_rules().items():
            self.assertEqual(hold, monitor.HOLD_S[rule], rule)
            self.assertEqual(monitor.ROBOT_LOG_NAMES[key], rule)
        self.assertEqual(set(monitor.HOLD_S), set(monitor.RULES))

    def test_the_robot_uses_the_laptops_words(self):
        src = java_source()
        own = {"steer_not_reaching", "motor_vs_absolute", "drive_backwards"}  # worded on the robot first
        for rule in monitor.ON_ROBOT - own:
            text = monitor.RULES[rule][1]
            self.assertIn(f'"{text[3:] if text.startswith("is ") else text}"', src, rule)

    def test_thresholds_match(self):
        src = java_source()
        for name in ("SIBLING_HOT_C", "RATIO_MIN_TRAVEL_M", "RATIO_FLAG"):
            m = re.search(rf"static final double {name} = ([\d.]+);", src)
            self.assertEqual(float(m.group(1)), getattr(monitor, name), name)
        self.assertEqual(int(re.search(r"static final int STRIDE = (\d+);", src).group(1)), monitor.STRIDE)


def snap(**kw):
    """A four-module robot driving forward at 1 m/s, nothing wrong."""
    s = {"mode": "TELEOP", "steer": [0.0] * 4, "steer_sp": [0.0] * 4, "steer_motor": [0.0] * 4,
         "v": [1.0] * 4, "v_sp": [1.0] * 4, "drive_amps": [5] * 4, "abs_issue": [0] * 4,
         "drive_temp": [30] * 4, "steer_temp": [30] * 4, "faults": [""] * 4, "bus": 12.4,
         "gyro": ["navX", "connected", "ready", ""], "t": 50.0}
    s.update(kw)
    return s


def watch(active=None, since=48.0):
    """The robot's checks, every rule on every module as ModuleWatch publishes them; ``active`` maps
    (rule, who) to its two readings."""
    active = active or {}
    rules, who, values = [], [], []
    for rule in sorted(monitor.ON_ROBOT):
        for w in ([""] if rule in ("low_battery", "gyro_problem") else
                  [n + " drive" for n in NAMES] if rule == "motor_hotter_than_siblings" else NAMES):
            a, b = active.get((rule, w), (float("nan"), float("nan")))
            on = (rule, w) in active
            rules.append(rule)
            who.append(w)
            values += [1 if on else 0, 1 if on else 0, since if on else float("nan"), a, b]
    return monitor.robot_checks(rules, who, values)


class TheLaptopShowsTheRobotsFlagsTest(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.m = monitor.Monitor(clock=lambda: self.now[0])

    def run_for(self, seconds, live):
        flags = []
        for _ in range(int(seconds / 0.1) + 1):
            flags = self.m.update(live, NAMES, "BLOCKS")
            self.now[0] += 0.1
        return flags

    def test_a_rule_the_robot_runs_is_shown_from_the_robot_once(self):
        # The laptop's own data says bl turns backwards; the robot judged fr. The robot's word stands.
        live = snap(v=[1.0, -1.0, -1.0, 1.0], watch=watch({("drive_backwards", "fr"): (-1.0, 1.0)}))
        flags = self.run_for(1.0, live)
        self.assertEqual([(f["rule"], f["module"], f["source"]) for f in flags], [("drive_backwards", "fr", "robot")])
        f = flags[0]
        self.assertEqual(f["text"], "Module fr: wheel is turning opposite to its command.")
        self.assertEqual(f["detail"], "-3.28 vs +3.28 ft/s")
        self.assertEqual(f["symptom"], "wheel_backwards")
        self.assertAlmostEqual(f["since"], self.now[0] - 0.1 - 2.0, places=6,
                               msg="placed by how long ago it started on the robot's clock")

    def test_a_quiet_robot_rule_is_not_raised_by_the_laptop_either(self):
        self.assertEqual(self.run_for(2.0, snap(v=[1.0, 1.0, -1.0, 1.0], bus=7.0, watch=watch())), [])

    def test_older_robot_code_is_watched_as_before(self):
        flags = self.run_for(1.0, snap(v=[1.0, 1.0, -1.0, 1.0]))
        self.assertEqual([(f["rule"], f["module"]) for f in flags], [("drive_backwards", "bl")])
        self.assertNotIn("source", flags[0])

    def test_the_laptop_keeps_the_rules_only_it_words(self):
        motors = [{"name": "Shooter leader", "stage": "DERATE", "cause": "heat estimate 72%", "flags": ""}]
        flags = self.run_for(0.2, snap(motors=motors, watch=watch()))
        self.assertEqual([(f["rule"], f["module"]) for f in flags], [("motor_hot", "Shooter leader")])

    def test_a_laptop_flag_gives_way_when_the_robot_starts_sending(self):
        self.assertTrue(self.run_for(1.0, snap(v=[1.0, 1.0, -1.0, 1.0])))
        self.assertEqual(self.m.update(snap(v=[1.0, 1.0, -1.0, 1.0], watch=watch()), NAMES), [],
                         "not held for a second as its own: the robot says it is fine")

    def test_words_the_robot_does_not_send_come_from_the_snapshot(self):
        live = snap(faults=["", "", "", "drive CAN fault"], gyro=["navX", "NOT CONNECTED", "ready", ""],
                    bus=7.4, watch=watch({("faults", "br"): (0, 0), ("gyro_problem", ""): (0, 0),
                                          ("low_battery", ""): (7.4, 0)}))
        got = {f["rule"]: f for f in self.run_for(0.2, live)}
        self.assertEqual(got["faults"]["detail"], "drive CAN fault")
        self.assertEqual(got["gyro_problem"]["detail"], "navX, NOT CONNECTED, ready")
        self.assertEqual(got["gyro_problem"]["text"], "The robot: gyro is not connected, still calibrating, or faulted.")
        self.assertEqual(got["low_battery"]["detail"], "7.4 V")

    def test_a_sibling_flag_reads_like_the_laptops(self):
        live = snap(watch=watch({("motor_hotter_than_siblings", "fl drive"): (62.0, 44.0)}))
        f = self.run_for(0.2, live)[0]
        self.assertEqual(f["text"], "fl drive motor runs much hotter than the matching motors on the other modules:"
                                    " binding, a dragging bearing or a failing motor.")
        self.assertEqual(f["detail"], "62 °C vs 44 °C")


class ReadingTheRobotsTopicsTest(unittest.TestCase):
    def test_three_topics_to_one_entry_per_check(self):
        got = monitor.robot_checks(["low_battery", "stall"], ["", "fl"], [1, 2, 40.5, 7.4, float("nan"), 0, 0, 0, 0, 0])
        self.assertEqual(got[0], {"rule": "low_battery", "who": "", "active": True, "count": 2, "since": 40.5,
                                  "a": 7.4, "b": got[0]["b"]})
        self.assertFalse(got[1]["active"])

    def test_read_mid_republish_every_check_is_quiet_but_still_the_robots(self):
        got = monitor.robot_checks(["low_battery", "stall"], ["", "fl"], [1, 2, 40.5, 7.4, 0])
        self.assertEqual([(w["rule"], w["active"]) for w in got], [("low_battery", False), ("stall", False)])

    def test_the_link_reads_the_contracts_topics(self):
        topics = {C.WATCH_RULES: ["low_battery"], C.WATCH_WHO: [""], C.WATCH_VALUES: [1, 1, 3.0, 7.2, 0]}

        class Stub:
            def get(self, kind, name):
                return topics.get(name, [])

        self.assertTrue(L.RobotLink.watch(Stub())[0]["active"])
        self.assertTrue(C.WATCH_VALUES.startswith(C.ROOT + "/Watch/"))


class TheMatchLogWordsEveryCheckTest(unittest.TestCase):
    W = "/RealOutputs/SlothTune/Watch/"

    def test_a_robot_wide_check_names_the_robot(self):
        rep = logsummary.summarize({self.W + "Robot/LowBattery": [(1.0, 0), (20.0, 1)]})
        texts = [e["text"] for e in rep["events"] if "battery" in e["text"]]
        self.assertEqual(texts, ["The robot: battery voltage is sagging below 8 V. Troubleshoot: \"Stutters or browns out\"."])

    def test_most_modules_starting_together_is_one_event(self):
        series = {self.W + f"{m}/DriveLagging": [(1.0, 0), (10.0 + 0.2 * i, 1)] for i, m in enumerate(NAMES)}
        series[self.W + "fl/DriveLagging"].append((30.0, 2))
        rep = logsummary.summarize(series)
        texts = [e["text"] for e in rep["events"] if "commanded speed" in e["text"]]
        self.assertEqual(len(texts), 2, texts)
        self.assertTrue(texts[0].startswith("4 modules at once (bl, br, fl, fr): wheel is well short"), texts[0])
        self.assertTrue(texts[1].startswith("fl: wheel is well short"), "one module alone is its own event")

    def test_the_first_three_keep_their_words(self):
        rep = logsummary.summarize({self.W + "fl/SteerOscillation": [(1.0, 0), (5.0, 1)],
                                    self.W + "fl/SteerOff": [(1.0, 0), (9.0, 1)]})
        texts = [e["text"] for e in rep["events"] if e["text"].startswith("fl:")]
        self.assertEqual(texts[0], "fl: swinging back and forth around its angle. Troubleshoot: \"A module shakes,"
                                   " buzzes or oscillates\".")
        self.assertIn("steering more than 10", texts[1])


if __name__ == "__main__":
    unittest.main()
