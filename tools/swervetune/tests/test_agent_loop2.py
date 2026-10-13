"""The agent's loop, second gap check: what it saves, what it does next, what it writes, its codes."""

import io
import json
import os
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from swervetune import advisor, cli, contract as C, plant

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv) + ["--json"])
    return code, json.loads(buf.getvalue())


class AdviceTest(unittest.TestCase):
    def test_a_drive_save_keeps_the_feedforward(self):
        rep = {"findings": [{"level": "ok", "title": "t", "why": "w", "action": {"type": "save", "what": "drive_pid"}}]}
        self.assertEqual(advisor._concrete(rep, {}, {})["findings"][0]["action"]["keys"], ["Drive", "FF"])

    def test_a_mild_kv_spread_is_a_note_and_the_feedforward_comes_next(self):
        ch = plant.drive_ff(surface="floor", motor="vortex", rate_hz=100)
        ch["m1.v"] = [v * 0.9 for v in ch["m1.v"]]  # one module reads 10% slow: about 11% more kV
        ch["m1.pos"] = [x * 0.9 for x in ch["m1.pos"]]
        doc = {"test": "drive_ff", "env": "FIELD", "outcome": "DONE", "channels": ch, "meta": {"pod_motor": "vortex"}}
        rep = advisor.analyze(doc, {})
        spread = [f for f in rep["findings"] if "kV differs" in f["title"]]
        self.assertEqual(len(spread), 1, [f["title"] for f in rep["findings"]])
        self.assertEqual(spread[0]["level"], "info")
        self.assertNotIn("action", spread[0], "no detour to blocks, where no gains come out")
        self.assertEqual(rep["next"]["title"], "Per-module feedforward measured", [f["title"] for f in rep["findings"]])
        self.assertEqual(rep["next"]["action"]["then"], {"test": "drive_step", "env": "FIELD"})

    def test_a_value_the_tool_cant_work_out_is_never_offered(self):
        rep = {"findings": [{"level": "warn", "title": "t", "why": "Wheels read 1.6% long.",
                             "action": {"type": "config", "file": "modules/physicalproperties.json",
                                        "path": ["conversionFactors", "drive", "diameter"], "value": "x1.0163"}}]}
        f = advisor._concrete(rep, {}, {})["findings"][0]
        self.assertNotIn("action", f)
        self.assertIn("--project", f["why"])


class CommandLineTest(unittest.TestCase):
    def test_an_unknown_project_is_one_json_object_with_a_code(self):
        code, doc = run_cli("lint", "--project", "Nope")
        self.assertEqual((code, doc["ok"], doc["code"]), (2, False, "NO_PROJECT"))

    def test_an_unknown_run_is_not_found(self):
        code, doc = run_cli("analyze", "no-such-run.json")
        self.assertEqual(doc["code"], "NOT_FOUND")

    def test_config_refuses_text_where_the_file_has_a_number(self):
        code, doc = run_cli("config", "--project", "Peashooter", "--file", "modules/physicalproperties.json",
                            "--path", "conversionFactors.drive.diameter", "--value", "x1.0163")
        self.assertEqual((doc["ok"], doc["code"]), (False, "BAD_ARGS"))

    def test_a_refused_gain_change_is_not_ok(self):
        class Link:
            def gains(self):
                return {"Steer/kP": 0.01}

            def set_gains(self, values, timeout=3.0, reason=""):
                return "REFUSED: not applied while a test is running.", {"Steer/kP": 0.01}

            def close(self):
                pass
        with mock.patch.object(cli, "open_link", return_value=Link()):
            code, doc = run_cli("gains", "set", "Steer/kP=0.012", "--why", "x")
        self.assertEqual((doc["ok"], doc["code"]), (False, "GAINS_REFUSED"))


class StopCodeTest(unittest.TestCase):
    def test_the_sentences_the_review_found_mismapped(self):
        for text, code in (("Speed 1.50 m/s is over the 1.00 m/s cap.", "BAD_ARGS"),
                           ("Wheel speed 1.50 m/s is over the 1.00 m/s cap. Something", "OVERSPEED"),
                           ("Unknown module 'XX'", "BAD_ARGS"),
                           ("2.0 m of floor only allows a 1.5 s ramp, too short", "NO_SPACE"),
                           ("Spinning needs 1.0 m clear on every side.", "NO_SPACE"),
                           ("'pdh_map' cannot run with the robot declared FIELD", "WRONG_PLACE"),
                           ("Busy: 'drive_step' is already running", "BUSY"),
                           ("The frontleft steer motor is at DERATE (stalled 3 s). Waiting for it to cool.", "MOTOR_GUARD"),
                           ("REFUSED: not applied while a test is running.", "GAINS_REFUSED")):
            self.assertEqual(C.stop_code(text), code, text)


class DeadmanTopicTest(unittest.TestCase):
    def test_only_the_gui_publishes_the_deadman(self):
        from swervetune import link as L
        lk = L.RobotLink(["127.0.0.2"], client_name="test")
        names = []
        lk.put = lambda kind, name, value: names.append(name)
        lk.flush = lambda: None
        try:
            lk.start_heartbeat()
            time.sleep(0.2)
            self.assertIn(C.CLIENT_HEARTBEAT, names)
            self.assertNotIn(C.CLIENT_DEADMAN, names, "a command line never says 'not held'")
            lk.set_gui_deadman(False)
            time.sleep(0.15)
            self.assertIn(C.CLIENT_DEADMAN, names)
        finally:
            lk.close()
