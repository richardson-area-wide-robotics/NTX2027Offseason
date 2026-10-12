"""The robot (Java) and the laptop (Python) must agree on every topic name and every gain bound.

Reads the Java source rather than trusting a copy, so renaming a topic on one side fails here.
"""

import os
import re
import unittest

from swervetune import contract as C

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
JAVA = os.path.join(REPO, "common", "swervetune", "java", "frc", "lib", "swervetune")


def java_topics():
    src = open(os.path.join(JAVA, "SwerveTuneTopics.java"), encoding="utf-8").read()
    values = {}
    for name, expr in re.findall(r"public static final String (\w+)\s*=\s*([^;]+);", src):
        parts = [p.strip() for p in expr.split("+")]
        out = ""
        for p in parts:
            out += p[1:-1] if p.startswith('"') else values[p]
        values[name] = out
    version = int(re.search(r"PROTOCOL_VERSION\s*=\s*(\d+)", src).group(1))
    return values, version


class ContractTest(unittest.TestCase):
    def test_every_java_topic_matches_python(self):
        topics, _ = java_topics()
        self.assertGreater(len(topics), 60)
        for name, value in topics.items():
            self.assertTrue(hasattr(C, name), f"contract.py is missing {name}")
            self.assertEqual(getattr(C, name), value, f"{name} differs between Java and Python")

    def test_protocol_version_matches(self):
        _, version = java_topics()
        self.assertEqual(version, C.PROTOCOL_VERSION)

    def test_live_arrays_are_real_topics(self):
        topics, _ = java_topics()
        for topic in C.LIVE_MODULE_ARRAYS.values():
            self.assertIn(topic, topics.values())

    def test_gain_bounds_match_the_robot(self):
        src = open(os.path.join(JAVA, "LiveGains.java"), encoding="utf-8").read()
        specs = {k: (float(a), float(b)) for k, a, b in
                 re.findall(r'spec\("([^"]+)",\s*([-\d.]+),\s*([-\d.]+),', src)}
        self.assertEqual(set(specs), set(C.GAIN_SPECS))
        for k, (lo, hi) in specs.items():
            self.assertEqual((lo, hi), tuple(map(float, C.GAIN_SPECS[k])), k)
        ff = {k: (float(a), float(b)) for k, a, b in
              re.findall(r'FF_K(\w)\s*=\s*new Spec\("k\w",\s*([-\d.]+),\s*([-\d.]+),', src)}
        for letter, bounds in ff.items():
            self.assertEqual(bounds, tuple(map(float, C.FF_SPECS["k" + letter])), letter)

    def test_every_robot_test_is_known(self):
        src = open(os.path.join(JAVA, "SwerveTune.java"), encoding="utf-8").read()
        robot = set(re.findall(r'procedures\.put\("(\w+)"', src))
        self.assertEqual(robot, set(C.TESTS))


if __name__ == "__main__":
    unittest.main()
