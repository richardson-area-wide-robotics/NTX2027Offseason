"""Every place one screen sends a student to another lands on something real."""

import os
import re
import unittest

from swervetune import diagnose

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")


def read(name):
    with open(os.path.join(WEB, name), encoding="utf-8") as fh:
        return fh.read()


GUIDE_STEPS = set(re.findall(r'^    \{ id: "([\w-]+)"', read("guide.js"), re.M))
TUNE_LOOPS = set(re.findall(r"^    (\w+): \{ label:", read("tune.js"), re.M))
TEST_LOOP = {"steer_step": "steer", "drive_step": "drive", "drive_ff": "ff", "slip": "slip",
             "spin": "spin", "straight": "straight"}


def actions():
    for s in diagnose.SYMPTOMS:
        for c in s["checks"]:
            if c.get("action"):
                yield s["id"], c["action"]


class LinksTest(unittest.TestCase):
    def test_the_screens_were_read(self):
        self.assertIn("hand", GUIDE_STEPS)
        self.assertGreater(len(GUIDE_STEPS), 12)
        self.assertIn("slip", TUNE_LOOPS)

    def test_every_troubleshoot_guide_link_is_a_real_step(self):
        for sid, a in actions():
            if a["type"] == "guide":
                self.assertIn(a["step"], GUIDE_STEPS, f"{sid} links to Guide step {a['step']}")

    def test_every_troubleshoot_test_opens_a_real_tuner(self):
        for sid, a in actions():
            if a["type"] == "run" and a["test"] != "capture":
                self.assertIn(TEST_LOOP.get(a["test"]), TUNE_LOOPS, f"{sid} runs {a['test']}")
            if a["type"] == "tune":
                self.assertIn("spin" if a["loop"] == "chassis" else a["loop"], TUNE_LOOPS, sid)

    def test_trouble_js_maps_every_test_the_same_way(self):
        src = read("trouble.js")
        for test, loop in TEST_LOOP.items():
            self.assertIn(f"{test}: \"{loop}\"", src, "trouble.js opens the wrong tuner for " + test)

    def test_every_troubleshoot_symptom_link_is_a_real_symptom(self):
        ids = {s["id"] for s in diagnose.SYMPTOMS}
        for sid, a in actions():
            if a["type"] == "troubleshoot":
                self.assertIn(a["symptom"], ids, sid)

    def test_yes_never_names_a_fault(self):
        # Yes means "that part is fine"; a question whose yes is the fault reads backwards.
        for s in diagnose.SYMPTOMS:
            for c in s["checks"]:
                self.assertNotRegex(c["q"], r"^(Is it only|Does it only)", f"{s['id']}: {c['q']}")
                self.assertNotIn("intended behavior", c["if_no"], f"{s['id']}: {c['q']}")


if __name__ == "__main__":
    unittest.main()
