"""The agent's loop does what its brief says (review item M19), and the app is fenced in (M20)."""

import glob
import http.client
import io
import json
import os
import re
import threading
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer

from swervetune import advisor, cli, contract as C, server, yagslcfg as Y

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
JAVA = os.path.join(REPO, "common", "swervetune", "java", "frc", "lib", "swervetune")


def robot_messages():
    """Every refusal and abort sentence the robot code can send, from its source."""
    out = []
    for path in glob.glob(os.path.join(JAVA, "*.java")):
        src = open(path, encoding="utf-8").read()
        for m in re.finditer(r'(?:Verdict\.abort|finish\(State\.ABORTED,)\s*\(?\s*(?:String\.format\()?\s*"([^"]+)"', src):
            out.append(m.group(1))
        if path.endswith(("SafetySupervisor.java", "Procedure.java")) or "Procedure" in path:
            for m in re.finditer(r'return\s+"([A-Z][^"]{12,})"', src):
                if not m.group(1).startswith("Pressed now"):
                    out.append(m.group(1))
    return out


class StopCodeTest(unittest.TestCase):
    def test_every_robot_sentence_has_a_code(self):
        msgs = robot_messages()
        self.assertGreater(len(msgs), 25)
        unknown = [m for m in msgs if C.stop_code(m) == "OTHER"]
        self.assertEqual(unknown, [], "add a STOP_CODES entry for these")

    def test_the_specific_code_wins(self):
        self.assertEqual(C.stop_code("Impact: 14.2 m/s^2. Check the robot and what it hit."), "IMPACT")
        self.assertEqual(C.stop_code("Gave up after a minute waiting: Deadman released."), "DEADMAN")
        self.assertEqual(C.stop_code("Battery sagged to 6.9 V. Brownout risk."), "BATTERY")
        self.assertEqual(C.stop_code(""), "OTHER")


class BriefTest(unittest.TestCase):
    BRIEF = open(os.path.join(REPO, "docs", "AGENT_TUNING.md"), encoding="utf-8").read()

    def test_the_brief_explains_every_code(self):
        for _, code in C.STOP_CODES:
            self.assertIn(f"`{code}`", self.BRIEF, code)
        self.assertIn("`OTHER`", self.BRIEF)

    def test_the_brief_lists_every_test(self):
        tests = self.BRIEF.split("Tests for `run`:")[1].split("\n\n")[0]
        for t in C.TESTS:
            self.assertIn(f"`{t}`", tests, t)

    def test_the_brief_names_every_action(self):
        for t in ("gains", "run", "config", "save", "troubleshoot", "stop"):
            self.assertIn(f'{{"type": "{t}"', self.BRIEF, t)


class ActionsTest(unittest.TestCase):
    def rep(self, action):
        return {"findings": [{"level": "warn", "title": "t", "why": "w.", "action": action}], "next": None}

    def test_a_gain_step_is_never_more_than_double(self):
        r = advisor._concrete(self.rep({"type": "gains", "values": {"Steer/kD": 0.36}}), {"Steer/kD": 0.001}, {})
        a = r["findings"][0]["action"]
        self.assertEqual(a["values"]["Steer/kD"], 0.002)
        self.assertTrue(a["clamped"])
        self.assertIn("held to 2×", r["findings"][0]["why"])

    def test_a_gain_at_zero_takes_its_first_value(self):
        r = advisor._concrete(self.rep({"type": "gains", "values": {"Steer/kD": 0.2}}), {"Steer/kD": 0.0}, {})
        self.assertEqual(r["findings"][0]["action"]["values"]["Steer/kD"], 0.2)

    def test_a_file_change_carries_the_real_value(self):
        r = advisor._concrete(self.rep({"type": "config", "file": "swervedrive.json", "path": ["invertedIMU"], "value": "toggle"}),
                              {}, {"inverted_imu": False})
        self.assertIs(r["findings"][0]["action"]["value"], True)
        r = advisor._concrete(self.rep({"type": "config", "file": "modules/physicalproperties.json",
                                        "path": ["conversionFactors", "drive", "diameter"], "value": "x0.9800"}),
                              {}, {"wheel_d_in": 3.0})
        self.assertEqual(r["findings"][0]["action"]["value"], 2.94)

    def test_a_save_names_what_save_gains_takes(self):
        r = advisor._concrete(self.rep({"type": "save", "what": "steer_pid"}), {}, {})
        self.assertEqual(r["findings"][0]["action"]["keys"], ["Steer"])

    def test_rehearse_output_says_it_is_the_practice_pod(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["rehearse", "steer", "--rounds", "1", "--json"])
        doc = json.loads(buf.getvalue())
        self.assertIs(doc["practice"], True)
        self.assertIn("not your robot", doc["note"])

    def test_json_output_is_strict(self):
        out = cli.Out(True)
        out.put(x=float("nan"), y=[float("inf")])
        buf = io.StringIO()
        with redirect_stdout(buf):
            out.done()
        self.assertEqual(json.loads(buf.getvalue()), {"ok": True, "x": None, "y": [None]})


class SavesTest(unittest.TestCase):
    def test_a_save_only_writes_the_robots_config_files(self):
        p = Y.Project(os.path.join(REPO, "Peashooter"))
        for ok in ("swervedrive.json", "modules/frontleft.json", "modules/physicalproperties.json", "swervetune.json"):
            self.assertTrue(p.writable(ok), ok)
        for bad in ("../src/main/java/frc/robot/Robot.java", "../../build.gradle.json", "/etc/x.json",
                    "C:/Windows/x.json", "modules/../../x.json", "Robot.java", "new.json"):
            self.assertFalse(p.writable(bad), bad)
        with self.assertRaises(ValueError):
            p.preview([("../src/main/java/frc/robot/Robot.java", ("x",), 1)])


class ServerFenceTest(unittest.TestCase):
    def setUp(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def req(self, method, path, headers=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        h.update(headers or {})
        c.request(method, path, body=json.dumps(body or {}) if method == "POST" else None, headers=h)
        r = c.getresponse()
        return r.status, r.read()

    def test_the_page_carries_the_token(self):
        status, page = self.req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(f'name="swervetune-token" content="{server.TOKEN}"'.encode(), page)

    def test_a_change_without_the_token_is_refused(self):
        status, _ = self.req("POST", "/api/deadman", body={"held": True})
        self.assertEqual(status, 403)
        status, _ = self.req("POST", "/api/deadman", {"X-SwerveTune-Token": "guess"}, {"held": True})
        self.assertEqual(status, 403)

    def test_another_host_name_is_refused(self):
        status, _ = self.req("GET", "/api/state", {"Host": f"evil.example:{self.port}"})
        self.assertEqual(status, 403)
        status, _ = self.req("POST", "/api/abort", {"Host": f"evil.example:{self.port}", "X-SwerveTune-Token": server.TOKEN})
        self.assertEqual(status, 403)

    def test_the_tools_own_page_gets_through(self):
        status, body = self.req("POST", "/api/abort", {"X-SwerveTune-Token": server.TOKEN})
        self.assertEqual(status, 200, body)


if __name__ == "__main__":
    unittest.main()
