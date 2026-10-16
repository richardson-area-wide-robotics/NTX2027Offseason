"""The agent's loop, second gap check: what it saves, what it does next, what it writes, its codes."""

import io
import json
import os
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from slothtune import advisor, cli, contract as C, plant
from slothtune.robotrepo import ROBOTS, needs_robots

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

    @needs_robots
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


class TeamUnitsOnTheCommandLineTest(unittest.TestCase):
    """A person types inches and ft/s; the robot and the report get meters and m/s."""

    def test_env_sends_the_robot_meters(self):
        sent = []

        class Link:
            def set_environment(self, *a):
                sent.append(a)

            def environment(self):
                return {"active": "FIELD", "apriltags": False, "space_forward": 3.048, "space_side": 1.524,
                        "speed_cap": 1.524}

            def close(self):
                pass
        with mock.patch.object(cli, "open_link", return_value=Link()), mock.patch.object(cli.time, "sleep"):
            code, doc = run_cli("env", "--mode", "FIELD", "--space", "120", "--side", "60", "--cap", "5", "--bumpers")
        self.assertEqual(code, 0, doc)
        mode, tags, space, side, cap = sent[0]
        self.assertEqual((mode, tags), ("FIELD", None))
        self.assertAlmostEqual(space, 3.048)
        self.assertAlmostEqual(side, 1.524)
        self.assertAlmostEqual(cap, 1.524)

    def test_env_refuses_meters_typed_out_of_habit(self):
        sent = []

        class Link:
            def set_environment(self, *a):
                sent.append(a)

            def close(self):
                pass
        with mock.patch.object(cli, "open_link", return_value=Link()):
            code, doc = run_cli("env", "--mode", "FIELD", "--space", "3", "--side", "1.5", "--bumpers")
        self.assertEqual((doc["ok"], doc["code"]), (False, "BAD_ARGS"))
        self.assertIn("takes inches", doc["error"])
        self.assertEqual(sent, [], "nothing sent to the robot")

    def test_analyze_takes_the_tape_in_inches(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "straight.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(GradingTest().straight_doc(odo_m=2.0), fh)
        code, doc = run_cli("analyze", path, "--tape-forward", "80")
        self.assertAlmostEqual(doc["report"]["measured"]["tape_forward_m"], 2.032)
        code, doc = run_cli("analyze", path, "--tape-forward", "2.03")
        self.assertEqual((doc["ok"], doc["code"]), (False, "BAD_ARGS"))


class StopCodeTest(unittest.TestCase):
    def test_the_sentences_the_review_found_mismapped(self):
        for text, code in (("Speed 1.50 m/s is over the 1.00 m/s cap.", "BAD_ARGS"),
                           ("Wheel speed 1.50 m/s is over the 1.00 m/s cap. Something", "OVERSPEED"),
                           ("Unknown module 'XX'", "BAD_ARGS"),
                           ("2.0 m of floor only allows a 1.5 s ramp, too short", "NO_SPACE"),
                           # The same sentences in the team's units.
                           ("Speed 4.92 ft/s is over the 3.28 ft/s cap.", "BAD_ARGS"),
                           ("Wheel speed 4.92 ft/s is over the 3.28 ft/s cap. Something", "OVERSPEED"),
                           ("79 in of floor only allows a 1.5 s ramp, too short", "NO_SPACE"),
                           ("Spinning needs 1.0 m clear on every side.", "NO_SPACE"),
                           ("'pdh_map' cannot run with the robot declared FIELD", "WRONG_PLACE"),
                           ("Busy: 'drive_step' is already running", "BUSY"),
                           ("The frontleft steer motor is at DERATE (stalled 3 s). Waiting for it to cool.", "MOTOR_GUARD"),
                           ("REFUSED: not applied while a test is running.", "GAINS_REFUSED")):
            self.assertEqual(C.stop_code(text), code, text)


class DeadmanTopicTest(unittest.TestCase):
    def test_only_the_gui_publishes_the_deadman(self):
        from slothtune import link as L
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


class GradingTest(unittest.TestCase):
    def straight_doc(self, odo_m=2.0, vision_m=None):
        n, dt = 300, 0.02
        t = [k * dt for k in range(n)]
        cmd = [0.0] * 30 + [1.0] * 100 + [0.0] * 170
        x = [0.0] * 30 + [odo_m * (k / 100) for k in range(100)] + [odo_m] * 170
        ch = {"t": t, "cmd_vx": cmd, "x": x, "y": [0.0] * n, "heading": [0.0] * n}
        if vision_m is not None:
            ch["vx_vision"] = [3.0] * 30 + [float("nan")] * 100 + [3.0 + vision_m] * 170
            ch["vy_vision"] = [1.0] * n
        return {"test": "straight", "env": "FIELD", "outcome": "DONE", "channels": ch, "meta": {"distance_m": 2.0}}

    def test_apriltags_at_both_ends_grade_the_straight_line(self):
        rep = advisor.analyze(self.straight_doc(odo_m=2.0, vision_m=2.1), {})
        self.assertAlmostEqual(rep["measured"]["vision_forward_m"], 2.1, places=6)
        # 2.1 m, worded in inches.
        self.assertTrue(any("AprilTags say 82.7 in" in f["title"] for f in rep["findings"]), [f["title"] for f in rep["findings"]])

    def test_without_tape_or_tags_nothing_measured_the_distance(self):
        rep = advisor.analyze(self.straight_doc(), {})
        self.assertNotIn("vision_forward_m", rep["measured"])
        self.assertNotIn("tape_forward_m", rep["measured"])

    def test_a_carpet_that_grips_past_the_ceiling_passes_the_slip_test(self):
        n = 200
        ch = {"t": [k * 0.02 for k in range(n)]}
        for m in range(4):
            ch[f"m{m}.amps"] = [min(80.0, k * 0.6) for k in range(n)]
            ch[f"m{m}.v"] = [0.0] * n
        rep = advisor.analyze({"test": "slip", "env": "FIELD", "outcome": "DONE", "channels": ch,
                               "meta": {"ceiling_a": 80, "policy_a": 80, "limit_before_a": 80}}, {})
        self.assertEqual(rep["score"], 100, [f["title"] for f in rep["findings"]])
        self.assertEqual(rep["wheels_slipped"], 0)


class FromRunTest(unittest.TestCase):
    """m8: a measured result goes only onto the robot it was measured on, while it is fresh."""

    def _save(self, robot, practice=False, hours_ago=1):
        import tempfile, time as _t
        from slothtune import runs as R
        d = tempfile.mkdtemp()
        stamp = _t.strftime("%Y%m%d-%H%M%S", _t.localtime(_t.time() - hours_ago * 3600))
        path = os.path.join(d, f"{stamp}_x_drive_ff_all.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"test": "drive_ff", "env": "FIELD", "robot": {"name": robot}, "saved": stamp,
                       "practice": practice}, fh)
        return path

    def test_another_robots_run_is_refused(self):
        bad = cli._from_run_problem(self._save("Black team"), {"name": "Peashooter"}, False)
        self.assertEqual(bad[0], "WRONG_ROBOT")
        self.assertIn("Black team", bad[1])

    def test_the_practice_pod_is_no_robot(self):
        self.assertEqual(cli._from_run_problem(self._save("practice", practice=True), {"name": "Peashooter"}, True)[0],
                         "WRONG_ROBOT")

    def test_a_day_old_run_is_stale_unless_forced(self):
        old = self._save("Peashooter", hours_ago=30)
        self.assertEqual(cli._from_run_problem(old, {"name": "Peashooter"}, False)[0], "STALE_RUN")
        self.assertIsNone(cli._from_run_problem(old, {"name": "Peashooter"}, True))

    def test_a_fresh_run_on_this_robot_goes_through(self):
        self.assertIsNone(cli._from_run_problem(self._save("Peashooter"), {"name": "Peashooter"}, False))

    def test_a_missing_run_says_so(self):
        self.assertEqual(cli._from_run_problem("no-such-run.json", {"name": "Peashooter"}, False)[0], "NOT_FOUND")

    def test_gains_set_refuses_before_touching_the_robot(self):
        from unittest import mock

        class FakeLink:
            calls = []

            def gains(self):
                return {"FF/drive/kV": 2.0}

            def robot_info(self):
                return {"name": "Peashooter"}

            def set_gains(self, values, timeout=3.0, reason=""):
                self.calls.append(values)
                return "Applied.", values

            def close(self):
                pass

        lk = FakeLink()
        buf = io.StringIO()
        with mock.patch.object(cli, "open_link", return_value=lk), redirect_stdout(buf):
            rc = cli.main(["gains", "set", "FF/drive/kV=2.1", "--from-run", self._save("Black team"), "--json"])
        self.assertEqual(lk.calls, [], "nothing sent to the robot")
        self.assertNotEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["code"], "WRONG_ROBOT")
