"""FIRST's control-system drawing: shipped unchanged with its credit, and every part a check or
a view names is one the drawing's map knows (web/frcmap.js)."""

import os
import re
import unittest

from slothtune import diagnose

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")


def read(name):
    with open(os.path.join(WEB, name), encoding="utf-8") as fh:
        return fh.read()


JS = read("frcmap.js")
PARTS = set(re.findall(r"\b(\w+): \[\d", JS.split("const P = {")[1].split("};")[0])) \
    | {f"pdh_{i}" for i in range(24)}
VIEWS = set(re.findall(r"\b(\w+): \[\d", JS.split("const VIEWS = {")[1].split("};")[0]))


class FrcMapTest(unittest.TestCase):
    def test_the_drawing_ships_unchanged_with_its_credit(self):
        svg = read(os.path.join("img", "frc-control-system-layout-rev.svg"))
        self.assertIn('viewBox="0 0 2592 1728"', svg, "the parts' positions are in these units")
        credit = read(os.path.join("img", "ATTRIBUTION.md"))
        for must in ("Team 3161", "Creative Commons Attribution 4.0", "docs.wpilib.org"):
            self.assertIn(must, credit)
        self.assertIn("CC BY 4.0", JS, "every view says so under it")

    def test_every_check_names_parts_the_drawing_knows(self):
        seen = 0
        for s in diagnose.SYMPTOMS:
            for c in s["checks"]:
                d = c.get("diagram")
                if not d:
                    continue
                seen += 1
                self.assertIn(d["view"], VIEWS, (s["id"], c["q"]))
                for f in d["focus"]:
                    self.assertIn(f["part"], PARTS, (s["id"], c["q"]))
        self.assertGreaterEqual(seen, 6)

    def test_the_tools_name_parts_the_drawing_knows(self):
        for name in ("wiring.js", "motors.js"):
            # A name built at runtime ("pdh_" + port) is checked by the PDH ports existing at all.
            for part in re.findall(r'part: "(\w+)"(?!\s*\+)', read(name)):
                self.assertIn(part, PARTS, (name, part))
            for view in re.findall(r'view: "(\w+)"', read(name)):
                self.assertIn(view, VIEWS, (name, view))

    def test_the_parts_these_robots_dont_use_are_faded(self):
        faded = JS.split("const NOT_OURS = [")[1].split("];")[0]
        for word in ("Pneumatics", "Talon SRX", "Koors", "Kraken"):
            self.assertIn(word, faded)


if __name__ == "__main__":
    unittest.main()
