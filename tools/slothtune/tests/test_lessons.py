"""Every lesson the tool points at exists, and every lesson points at real reading.

The GUI links words to lessons in many places - the controller replay, the guide, every tab. A
typo there is a broken tooltip a student hovers over, so it is checked here, not in a browser.
"""

import glob
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
WEB = os.path.join(PKG, "web")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


LEARN = read(os.path.join(WEB, "learn.js"))
LESSONS = set(re.findall(r"^\s{4}(\w+): \{ title:", LEARN, re.M))
LINKS = set(re.findall(r'^\s{4}(\w+): \[(?:W \+|"https)', LEARN, re.M))


class LessonsTest(unittest.TestCase):
    def test_there_is_a_full_course(self):
        self.assertGreater(len(LESSONS), 45)

    def test_lesson_links_and_units_resolve(self):
        for m in re.finditer(r"links: \[([^\]]*)\]", LEARN):
            for k in re.findall(r'"(\w+)"', m.group(1)):
                self.assertIn(k, LINKS, f"lesson link {k}")
        for unit in re.findall(r"lessons: \[([^\]]*)\]", LEARN):
            for k in re.findall(r'"(\w+)"', unit):
                self.assertIn(k, LESSONS, f"course unit lists {k}")
        terms = LEARN.split("const TERMS")[1].split("];")[0]
        for _, k in re.findall(r'\["([^"]+)", "(\w+)"\]', terms):
            self.assertIn(k, LESSONS, f"term links to {k}")

    def test_every_lesson_is_in_the_course(self):
        listed = {k for unit in re.findall(r"lessons: \[([^\]]*)\]", LEARN) for k in re.findall(r'"(\w+)"', unit)}
        self.assertEqual(LESSONS - listed, set(), "lessons no unit lists")

    def test_every_pointer_in_the_gui_and_the_replay_lands(self):
        used = {}
        for path in glob.glob(os.path.join(WEB, "*.js")) + [os.path.join(WEB, "index.html")]:
            src = read(path)
            for k in re.findall(r'data-learn="(\w+)"', src):
                used.setdefault(k, os.path.basename(path))
            for arr in re.findall(r"learn: \[([^\]]*)\]", src):
                for k in re.findall(r'"(\w+)"', arr):
                    used.setdefault(k, os.path.basename(path))
            for k in re.findall(r'\["[^"]+", "(\w+)", [\d.]+\]', src):  # what-if sliders
                used.setdefault(k, os.path.basename(path))
        explain = read(os.path.join(PKG, "explain.py"))
        for k in re.findall(r'_note\(out, "\w+", "\w+", "(\w+)"', explain):
            used.setdefault(k, "explain.py")
        self.assertGreater(len(used), 30)
        for k, where in used.items():
            self.assertIn(k, LESSONS, f"{where} points at lesson {k}")


if __name__ == "__main__":
    unittest.main()
