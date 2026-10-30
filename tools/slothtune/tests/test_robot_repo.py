"""Setting the tool up: where the robots come from, what to say when there are none, what to install.

Sloth Tune lives in its own repo and is synced into the team repo (NTX2027Offseason, StuartTesting
branch), where the robots are. Run from either, nothing it tells a person may be wrong: an empty
robot list says why and how to fix it, and the setup steps name the repo that has the robots.
"""

import ast
import glob
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from slothtune import cli, robotrepo, runs, server

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
TOOLS = os.path.dirname(PKG)
REPO = os.path.dirname(TOOLS)
# The copy synced into the team repo sits beside the robots; Sloth Tune's own repo has none.
IN_TEAM_REPO = os.path.isdir(os.path.join(REPO, "Peashooter"))
# The docs Sloth Tune ships, and copies into the team repo. The team repo has its own docs beside them
# (the controls review), and its own README, which are not Sloth Tune's to check.
SHIPPED_DOCS = ("AGENT_TUNING.md", "GYRO_CANANDGYRO.md", "MIGRATION_2027.md", "NETWORK_CHECK.md",
                "REV_HARDWARE.md", "ROBOT_DAY.md", "SWERVE_TUNING_GUIDE.md", "VISION_LUMA_PHOTONVISION.md")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv) + ["--json"])
    return code, json.loads(buf.getvalue())


class NoRobotsTest(unittest.TestCase):
    """Run from a folder with no robot projects: every place that lists them says so, and how to fix it."""

    def setUp(self):
        self.empty = tempfile.mkdtemp(prefix="slothtune-norobots-")
        p = mock.patch.object(runs, "ROBOTS", self.empty)
        p.start()
        self.addCleanup(p.stop)

    def says_how_to_fix_it(self, text):
        self.assertIn(self.empty, text, "where it looked")
        self.assertIn("NTX2027Offseason", text)
        self.assertIn("StuartTesting", text)
        self.assertIn('setx SLOTHTUNE_ROBOT_REPO "C:\\path\\to\\NTX2027Offseason"', text)

    def test_the_command_line_names_none_rather_than_an_empty_list(self):
        code, d = run_cli("lint", "--project", "Peashooter")
        self.assertEqual((d["ok"], d["code"]), (False, "NO_PROJECT"))
        self.assertNotIn("Known: ", d["error"], "an empty 'Known:' list helps nobody")
        self.says_how_to_fix_it(d["error"])

    def test_a_command_over_every_robot_says_there_are_none(self):
        code, d = run_cli("lint")
        self.assertEqual((d["ok"], d["code"]), (False, "NO_PROJECT"), "not a lint of nothing that passes")
        self.says_how_to_fix_it(d["error"])

    def test_the_gui_says_so_instead_of_pick_a_robot(self):
        p = server.api_projects(None)
        self.assertEqual(p["projects"], [])
        self.says_how_to_fix_it(p["none_found"])
        with mock.patch.object(server.S, "project", None):
            lint = server.api_lint(None)
        self.assertFalse(lint["ok"])
        self.says_how_to_fix_it(lint["error"])

    def test_a_setting_that_points_nowhere_says_so(self):
        with mock.patch.dict(os.environ, {"SLOTHTUNE_ROBOT_REPO": self.empty}):
            self.assertTrue(robotrepo.none_found(self.empty).startswith(f"SLOTHTUNE_ROBOT_REPO is {self.empty}"))
        with mock.patch.dict(os.environ, {"SLOTHTUNE_ROBOT_REPO": ""}):
            self.assertTrue(robotrepo.none_found(self.empty).startswith("No robot projects found in"))


class RobotsHereTest(unittest.TestCase):
    @robotrepo.needs_robots
    def test_with_robots_the_list_and_the_known_names_are_there(self):
        p = server.api_projects(None)
        self.assertIn("Peashooter", p["projects"])
        self.assertEqual(p["none_found"], "")
        code, d = run_cli("lint", "--project", "Nope")
        self.assertEqual(d["code"], "NO_PROJECT")
        self.assertIn("Known: ", d["error"])
        self.assertIn("Peashooter", d["error"])


class RequirementsTest(unittest.TestCase):
    """tools/requirements.txt names every package the tool imports, pinned to WPILib's year."""

    PIP = {"ntcore": "pyntcore", "wpiutil": "robotpy-wpiutil"}

    def requirements(self):
        out = {}
        for line in read(os.path.join(TOOLS, "requirements.txt")).splitlines():
            line = line.split("#")[0].strip()
            if line:
                m = re.fullmatch(r"([A-Za-z0-9_.-]+)(.*)", line)
                out[m.group(1).lower()] = m.group(2)
        return out

    def test_each_is_the_2026_release(self):
        req = self.requirements()
        self.assertEqual(set(req), {"pyntcore", "robotpy-wpiutil"})
        for name, spec in req.items():
            self.assertEqual(spec, ">=2026,<2027", name)

    def test_every_package_the_tool_imports_is_listed(self):
        req = self.requirements()
        for path in glob.glob(os.path.join(PKG, "*.py")) + glob.glob(os.path.join(PKG, "preview", "*.py")):
            for node in ast.walk(ast.parse(read(path))):
                names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                         [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
                for name in names:
                    top = name.split(".")[0]
                    if top in sys.stdlib_module_names or top == "slothtune":
                        continue
                    self.assertIn(self.PIP.get(top, top), req, f"{os.path.basename(path)} imports {top}")

    def test_the_install_hint_and_the_docs_use_it(self):
        from slothtune import link
        self.assertIn("-r tools/requirements.txt", link.INSTALL_HINT)
        for doc in ("README.md", os.path.join("docs", "SWERVE_TUNING_GUIDE.md")):
            self.assertIn("py -3.12 -m pip install -r tools/requirements.txt", read(os.path.join(REPO, doc)), doc)


class SetupDocsTest(unittest.TestCase):
    """Since the split, "this branch" is wrong from Sloth Tune's own repo: say which repo and branch."""

    @unittest.skipIf(IN_TEAM_REPO, "the team repo's README is the team's: its Sloth Tune section is checked below")
    def test_the_readme_says_where_the_robots_are_and_how_to_point_at_them(self):
        text = read(os.path.join(REPO, "README.md"))
        setup = text.split("## Setting up")[1].split("\n## ")[0]
        for want in ("NTX2027Offseason", "StuartTesting", 'setx SLOTHTUNE_ROBOT_REPO "C:\\path\\to\\NTX2027Offseason"',
                     "set SLOTHTUNE_ROBOT_REPO=", "$env:SLOTHTUNE_ROBOT_REPO", "py -3.12 -m slothtune gui --project Peashooter"):
            self.assertIn(want, setup)

    @unittest.skipUnless(IN_TEAM_REPO, "only the team repo's README has a Sloth Tune section")
    def test_the_team_readme_says_how_to_install_and_where_sloth_tune_is_made(self):
        text = read(os.path.join(REPO, "README.md"))
        for want in ("py -3.12 -m pip install -r tools/requirements.txt", "py -3.12 tools/slothtune gui",
                     "developed in its own repository"):
            self.assertIn(want, text)

    @unittest.skipIf(IN_TEAM_REPO, "checks Sloth Tune's own docs folder")
    def test_the_shipped_docs_list_is_the_docs_folder(self):
        # SHIPPED_DOCS is also the list copied into the team repo: a new doc must be added to it.
        found = sorted(os.path.basename(p) for p in glob.glob(os.path.join(REPO, "docs", "*.md")))
        self.assertEqual(sorted(SHIPPED_DOCS), found)

    def test_nothing_a_person_reads_says_this_branch(self):
        files = ([os.path.join(REPO, "docs", d) for d in SHIPPED_DOCS]
                 + ([] if IN_TEAM_REPO else [os.path.join(REPO, "README.md")])
                 + glob.glob(os.path.join(PKG, "*.py")) + glob.glob(os.path.join(PKG, "web", "*.js")))
        for path in files:
            text = read(path)
            for bad in ("this branch", "this repository on the `StuartTesting` branch"):
                self.assertNotIn(bad, text, os.path.relpath(path, REPO))

    def test_the_connect_errors_name_the_team_repo(self):
        self.assertIn("team repo's StuartTesting branch", read(os.path.join(PKG, "server.py")))
        self.assertIn("team repo's StuartTesting", read(os.path.join(PKG, "web", "app.js")))


if __name__ == "__main__":
    unittest.main()
