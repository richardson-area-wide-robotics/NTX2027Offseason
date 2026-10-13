"""The preview (preview/make.py) builds from a recording without a robot: the tool's real page with
the mock ahead of it, a stylesheet that follows the viewer's theme switch, and the dashboard's
moments from the robot code's own text."""

import json
import os
import re
import tempfile
import unittest

from swervetune.preview import make

LIVE = {"connected": True, "live": {"steer": [0, 0, 0, 0], "mode": "TELEOP"}}


class PreviewBuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        rec = os.path.join(self.tmp.name, "rec")
        os.makedirs(os.path.join(rec, "runs"))
        with open(os.path.join(rec, "runs", "a_steer_step_all.json"), "w", encoding="utf-8") as fh:
            json.dump({"test": "steer_step"}, fh)
        moving = [dict(LIVE, live=dict(LIVE["live"], steer=[i, 0, 0, 0])) for i in range(5)]
        with open(os.path.join(rec, "rec.json"), "w", encoding="utf-8") as fh:
            json.dump({"get": {"/api/projects": {"projects": ["Peashooter"], "current": "Peashooter"}},
                       "post": [{"path": "/api/project", "body": {"name": "Peashooter"}, "resp": {"ok": True}}],
                       "live": [dict(LIVE, live=dict(LIVE["live"], mode="DISABLED"))] + moving + [LIVE] * 40,
                       "state": [{"connected": True}], "started": {},
                       "recorded": "2026-10-13T18:49:00+00:00"}, fh)
        self.site = os.path.join(self.tmp.name, "site")
        self.files = make.build(rec_dir=rec, site=self.site)

    def read(self, name):
        with open(os.path.join(self.site, name), encoding="utf-8") as fh:
            return fh.read()

    def test_the_page_is_the_tools_own_with_the_mock_first(self):
        page = self.read("index.html")
        with open(os.path.join(make.WEB, "index.html"), encoding="utf-8") as fh:
            scripts = re.findall(r'<script src="([^"]+)"></script>', fh.read())
        order = re.findall(r'<script src="([^"]+)"></script>', page)
        self.assertEqual(order, ["mock.js"] + scripts + ["preview.js"], "the mock answers before the page asks")
        for f in scripts + ["style.css", "img/frc-control-system-layout-rev.svg", "rec/rec.json", "rec/elastic.json"]:
            self.assertIn(f, self.files)
        self.assertNotIn("<html", page.lower(), "the publisher adds the document around it")
        self.assertIn("Peashooter's robot code", page)
        self.assertIn("(18:49 UTC)", page, "the local time first, UTC beside it")

    def test_the_stylesheet_follows_the_viewers_theme_switch(self):
        css = self.read("style.css")
        self.assertNotRegex(css, r"prefers-color-scheme: dark\) \{\n  :root \{", "an explicit light choice must win")
        self.assertIn(':root:not([data-theme="light"]) {', css)
        self.assertIn(':root[data-theme="dark"] {', css)
        self.assertIn(':root[data-theme="dark"] .frcmap', css, "the drawing's dark rule too")
        self.assertEqual(css.count("{"), css.count("}"))

    def test_the_live_view_replays_the_motion_only(self):
        rec = json.loads(self.read("rec/rec.json"))
        self.assertTrue(all(x["live"]["mode"] != "DISABLED" for x in rec["live"]))
        self.assertLess(len(rec["live"]), 46, "not the idle time after the test")

    def test_every_moment_the_dashboard_offers_is_the_robots_text(self):
        el = json.loads(self.read("rec/elastic.json"))
        types = {c["type"] for c in el["layout"]["tabs"][0]["grid_layout"]["containers"]}
        self.assertEqual(types, {"ComboBox Chooser", "Text Display", "Alerts"}, "the widgets preview.js draws")
        with open(os.path.join(make.HERE, "preview.js"), encoding="utf-8") as fh:
            js = fh.read()
        for name, m in el["moments"].items():
            self.assertIn(f"{name}:", js, f"{name} has a label and a pick")
            for a in m["alerts"]:
                self.assertRegex(a, r"^k(Error|Warning|Info): ")
        self.assertIn("CHARGE IT", el["moments"]["charge_it"]["check"])


if __name__ == "__main__":
    unittest.main()
