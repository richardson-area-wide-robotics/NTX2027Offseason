"""Every control's tip exists, is used, links a real lesson, and reads like the rest of the tool.

A tip is the sentence a student reads when they hover, focus or tap a control (or every one of
them, in Explain mode). A key with no tip is a control that explains nothing; a tip nothing uses
is text nobody can reach. Both are checked here rather than in a browser.
"""

import glob
import os
import re
import unittest

from swervetune import diagnose

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


JS_STR = r'"((?:[^"\\]|\\.)*)"'
TIPS = {m.group(1): (m.group(2), m.group(3), m.group(5))
        for m in re.finditer(r'^\s+"([\w.-]+)": \[' + JS_STR + r',\s*' + JS_STR + r',\s*(null|"(\w+)")\]',
                             read(os.path.join(WEB, "tips.js")), re.M)}
LESSONS = set(re.findall(r"^\s{4}(\w+): \{ title:", read(os.path.join(WEB, "learn.js")), re.M))
SOURCES = {os.path.basename(p): read(p) for p in glob.glob(os.path.join(WEB, "*.js")) + [os.path.join(WEB, "index.html")]
           if not p.endswith("tips.js")}

# Keys written out in full, and keys built from a template such as "guide.step.${s.id}".
USED, PATTERNS = {}, []
for name, src in SOURCES.items():
    for m in re.finditer(r'data-tip(?:="|": ")([^"]+)"', src):
        key = m.group(1)
        if "${" in key:
            PATTERNS.append((re.compile("^" + re.sub(r"\\\$\\\{[^}]*\\}", r"[\\w-]+", re.escape(key)) + "$"), name))
        else:
            USED.setdefault(key, name)

# Files whose hover-only title="" attributes haven't been replaced by tips yet. It only shrinks.
TITLES_PENDING = {"calibrate.js", "config.js", "controllers.js", "motors.js", "runs.js", "tune.js", "wiring.js"}


class TipsTest(unittest.TestCase):
    def test_the_tips_were_read(self):
        self.assertGreater(len(TIPS), 90)
        self.assertGreater(len(USED), 40)

    def test_every_key_the_page_uses_has_a_tip(self):
        for key, where in USED.items():
            self.assertIn(key, TIPS, f"{where} uses data-tip=\"{key}\"")
        for pat, where in PATTERNS:
            self.assertTrue(any(pat.match(k) for k in TIPS), f"{where}: no tip matches {pat.pattern}")

    def test_every_tip_is_used(self):
        for key in TIPS:
            self.assertTrue(key in USED or any(p.match(key) for p, _ in PATTERNS), f"tip {key} is never used")

    def test_every_tip_links_a_real_lesson(self):
        for key, (_, _, lesson) in TIPS.items():
            if lesson:
                self.assertIn(lesson, LESSONS, f"tip {key}")

    def test_every_guide_step_and_symptom_has_a_tip(self):
        steps = re.findall(r'^    \{ id: "([\w-]+)"', SOURCES["guide.js"], re.M)
        self.assertGreater(len(steps), 12)
        for s in steps:
            self.assertIn(f"guide.step.{s}", TIPS)
        for s in diagnose.SYMPTOMS:
            self.assertIn(f"trouble.sym.{s['id']}", TIPS)

    def test_tips_are_short_sentences(self):
        for key, (what, how, _) in TIPS.items():
            self.assertTrue(what.strip(), key)
            self.assertLessEqual(len(what), 160, f"{key}: the first sentence is what Explain mode prints; keep it short")
            self.assertLessEqual(len(how), 260, key)
            for s in (what, how):
                if s:
                    self.assertRegex(s.rstrip('"'), r"[.!?)]$", f"{key}: {s}")

    def test_us_spelling(self):
        uk = re.compile(r"\b(colour\w*|behaviour\w*|tyres?|centre\w*|metres?|optimis\w*|analys(?:e|ed|ing)|travelled|grey)\b", re.I)
        for key, (what, how, _) in TIPS.items():
            for s in (what, how):
                self.assertEqual(uk.findall(s), [], f"{key}: {s}")

    def test_no_hover_only_titles(self):
        # A title="" never shows on a tap or a keyboard focus, and is unreadable past a phrase.
        for name, src in SOURCES.items():
            if name in TITLES_PENDING:
                continue
            self.assertNotRegex(src, r'\btitle="', f"{name} still has a title=\"\" attribute; use data-tip")
            self.assertNotRegex(src, r"\.title = ", f"{name} still sets .title; use data-tip-now")


if __name__ == "__main__":
    unittest.main()
