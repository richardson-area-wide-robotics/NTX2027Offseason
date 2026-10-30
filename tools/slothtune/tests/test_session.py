"""The live-robot session: its record, its order, and how each check judges what the tool reports.

The checks run real commands against a real robot; here each one gets a stand-in that answers the
way the command line or the robot would, so every verdict is pinned without a robot.
"""

import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from slothtune import cli, contract as C, session as S


class FakeLink:
    def __init__(self, **kw):
        self.kw = kw

    def get(self, kind, name, default=None):
        return self.kw.get(name, default)

    def live(self):
        return self.kw.get("live", {})

    def status(self):
        return self.kw.get("status", {})

    def environment(self):
        return {"active": self.kw.get("env", "UNSET")}

    def robot_info(self):
        return {"modules": ["frontleft", "frontright", "backleft", "backright"]}

    def motors(self):
        return {"motors": self.kw.get("motors", [])}

    def systems(self):
        return self.kw.get("systems", [])

    def close(self):
        pass


class FakeCtx:
    """Answers each command with a scripted JSON object; never talks to a robot."""

    def __init__(self, answers=None, sim=False, link=None, opts=None, missing=()):
        self.answers, self.sim, self.opts = answers or {}, sim, opts or {}
        self.project, self.lk, self.missing = "Black team", link or FakeLink(), list(missing)
        self.calls = []

    def cli(self, *argv):
        self.calls.append(argv)
        return 0, self.answers.get(argv[0] if argv[0] != "run" else "run:" + argv[1], {"ok": True})

    def link(self):
        return S._Closing(self.lk)

    def missing_topics(self):
        return self.missing

    def project_name(self):
        return self.project

    def say(self, text):
        pass

    def beep(self, n=1):
        pass

    def countdown(self, seconds, what):
        pass

    def need_blocks(self):
        if not self.opts.get("blocks"):
            raise S.SessionError("needs --blocks")

    def need_field(self):
        pass


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_new_session_is_the_current_one_and_keeps_every_event(self):
        rec = S.Record.new("Black team", {"sim": False}, "Stuart", folder=self.dir)
        rec.add("check", "link", verdict="pass", summary="ok")
        again = S.Record.current(folder=self.dir)
        self.assertEqual(again.data["project"], "Black team")
        self.assertEqual(again.state("link"), "pass")
        self.assertIsNone(again.state("network"))

    def test_a_later_mark_overrides_a_check(self):
        rec = S.Record.new("Black team", {}, folder=self.dir)
        rec.add("check", "directions", verdict="person")
        rec.add("mark", "directions", verdict="pass", note="all four forward")
        self.assertEqual(rec.state("directions"), "pass")

    def test_no_session_says_how_to_start_one(self):
        with self.assertRaisesRegex(S.SessionError, "session start"):
            S.Record.current(folder=self.dir)

    def test_next_is_the_first_required_step_not_done(self):
        rec = S.Record.new("Black team", {}, folder=self.dir)
        self.assertEqual(S.next_step(rec).id, "network")
        for sid in ("network", "link", "config", "versions", "battery"):
            rec.add("check", sid, verdict="pass")
        rec.add("check", "deadman", verdict="fail")
        self.assertEqual(S.next_step(rec).id, "deadman", "a failed step stays next until it passes")
        rec.add("mark", "deadman", verdict="skip")
        self.assertEqual(S.next_step(rec).id, "controllers")

    def test_optional_steps_come_after_every_required_one(self):
        rec = S.Record.new("Black team", {}, folder=self.dir)
        for s in S.STEPS:
            if not s.optional:
                rec.add("mark", s.id, verdict="pass")
        self.assertTrue(S.next_step(rec).optional)


class StepsTest(unittest.TestCase):
    def test_the_order_is_bring_up_then_tuning_testing_field_and_troubleshooting(self):
        phases = [s.phase for s in S.STEPS]
        order = [p for p, _ in S.PHASES]
        self.assertEqual(sorted(set(phases), key=order.index), order)
        self.assertEqual(phases, sorted(phases, key=order.index), "steps are grouped by phase, in phase order")

    def test_ids_are_unique_and_every_step_says_what_passing_is(self):
        self.assertEqual(len(S.BY_ID), len(S.STEPS))
        for s in S.STEPS:
            self.assertTrue(s.passes and s.where and s.do, s.id)

    def test_every_test_a_check_runs_is_one_the_robot_knows(self):
        with open(S.__file__, encoding="utf-8") as fh:
            src = fh.read()
        used = set(re.findall(r'_(?:run|field)\(ctx, "(\w+)"', src))
        self.assertTrue(used)
        self.assertEqual(used - set(C.TESTS), set())

    def test_a_step_on_blocks_or_the_floor_says_so(self):
        for s in S.STEPS:
            if s.env == "BLOCKS":
                self.assertIn("blocks", s.where.lower(), s.id)
            if s.env == "FIELD":
                self.assertIn("floor", s.where.lower(), s.id)


class VerdictTest(unittest.TestCase):
    def test_a_refused_or_stopped_run_fails_with_the_robots_words(self):
        r = S._run_result({"ok": False, "accepted": False, "error": "Refused: Disable the robot first"}, "X")
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("Disable the robot first", r["summary"])
        r = S._run_result({"ok": False, "outcome": "ABORTED", "message": "Deadman released.", "code": "DEADMAN",
                           "run_file": "a.json"}, "X")
        self.assertEqual((r["verdict"], r["evidence"]["code"], r["runs"]), ("fail", "DEADMAN", ["a.json"]))

    def test_a_finished_run_is_judged_by_its_report(self):
        done = {"ok": True, "outcome": "DONE", "run_file": "r.json"}
        self.assertEqual(S._run_result({**done, "report": {"findings": []}}, "X")["verdict"], "pass")
        self.assertEqual(S._run_result({**done, "report": {"findings": [{"level": "warn", "title": "t"}]}}, "X")["verdict"], "warn")
        self.assertEqual(S._run_result({**done, "report": {"findings": [{"level": "error", "title": "t"}]}}, "X")["verdict"], "fail")
        self.assertEqual(S._run_result({**done, "report": {}}, "X", passes_if_done=False)["verdict"], "person")

    def test_the_network_check_is_skipped_in_the_simulator_and_fails_on_a_failed_check(self):
        self.assertEqual(S.c_network(FakeCtx(sim=True))["verdict"], "skip")
        net = {"ok": False, "robot_adapter": "Ethernet 2", "internet_adapter": "Wi-Fi",
               "checks": [{"level": "fail", "title": "Robot traffic leaves by the VPN", "why": "w"},
                          {"level": "ok", "title": "fine", "why": ""}], "fix": "powershell ... -Fix"}
        r = S.c_network(FakeCtx({"netcheck": net}))
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("Ethernet 2", r["summary"])
        self.assertTrue(any("-Fix" in d for d in r["details"]))

    def test_old_robot_code_fails_the_link_and_says_to_deploy(self):
        status = {"ok": True, "robot": {"name": "Black team", "address": "10.17.45.2", "startup_report": []},
                  "live": {"mode": "DISABLED", "bus": 12.8}}
        ok = S.c_link(FakeCtx({"status": status}))
        self.assertEqual(ok["verdict"], "pass")
        old = S.c_link(FakeCtx({"status": status}, missing=["homing"]))
        self.assertEqual(old["verdict"], "fail")
        self.assertIn("StuartTesting", old["details"][0])
        wrong = S.c_link(FakeCtx({"status": {**status, "robot": {**status["robot"], "name": "Peashooter"}}}))
        self.assertEqual(wrong["verdict"], "fail")

    def test_the_battery_needs_twelve_point_four_at_rest(self):
        judge = lambda v, mode="DISABLED": S.c_battery(FakeCtx(link=FakeLink(live={"bus": v, "mode": mode})))["verdict"]
        self.assertEqual([judge(12.7), judge(12.2), judge(11.8), judge(12.7, "TELEOP")], ["pass", "warn", "fail", "warn"])

    def test_a_controller_not_answering_fails_and_dropouts_warn(self):
        rows = [{"name": "frontleft drive", "present": 1.0, "firmware": "26.1.6", "dropouts": 0, "resets": 0},
                {"name": "frontleft steer", "present": 1.0, "firmware": "26.1.5", "dropouts": 2, "resets": 0}]
        with mock.patch("slothtune.motorinv.table", return_value={"findings": []}), \
                mock.patch.object(FakeCtx, "project_obj", lambda self: None, create=True):
            r = S.c_controllers(FakeCtx(link=FakeLink(motors=rows)))
            self.assertEqual(r["verdict"], "warn")
            self.assertIn("2 dropouts", r["details"][0])
            r = S.c_controllers(FakeCtx(link=FakeLink(motors=rows + [{"name": "Shooter", "present": 0.0}])))
            self.assertEqual(r["verdict"], "fail")
            self.assertIn("Shooter", r["details"][0])

    def test_firmware_for_2027_fails_the_controllers_step(self):
        rows = [{"name": "frontleft drive", "present": 1.0, "firmware": "27.0.0"}]
        with mock.patch("slothtune.motorinv.table", return_value={"findings": [
                {"level": "error", "title": "frontleft drive: SPARK Flex firmware 27.0.0 is for 2027 code"}]}), \
                mock.patch.object(FakeCtx, "project_obj", lambda self: None, create=True):
            r = S.c_controllers(FakeCtx(link=FakeLink(motors=rows)))
        self.assertEqual(r["verdict"], "fail")

    def test_the_hand_check_passes_only_when_every_module_agrees(self):
        run = {"run:capture": {"ok": True, "outcome": "DONE", "run_file": "cap.json"}}
        agree = {"verdict": "AGREES"}
        rows = {n: {"drive": agree} for n in ("frontleft", "frontright", "backleft", "backright")}
        with mock.patch("slothtune.runs.load", return_value={}), \
                mock.patch("slothtune.advisor.hand_check", return_value=rows):
            self.assertEqual(S.c_hand_wheels(FakeCtx(run))["verdict"], "pass")
        rows["backleft"] = {"drive": {"verdict": "INVERTED"}}
        with mock.patch("slothtune.runs.load", return_value={}), \
                mock.patch("slothtune.advisor.hand_check", return_value=rows):
            r = S.c_hand_wheels(FakeCtx(run))
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("backleft: INVERTED", r["details"])

    def test_the_steering_hand_check_catches_a_wrong_ratio(self):
        run = {"run:capture": {"ok": True, "outcome": "DONE", "run_file": "cap.json"}}
        good = {"absolute": {"verdict": "AGREES"}, "motor": {"verdict": "AGREES"}, "motor_per_module_deg": 1.0}
        rows = {"frontleft": good, "frontright": {**good, "motor_per_module_deg": 1.08}}
        with mock.patch("slothtune.runs.load", return_value={}), \
                mock.patch("slothtune.advisor.hand_check", return_value=rows):
            r = S.c_hand_steer(FakeCtx(run))
        self.assertEqual(r["verdict"], "fail")
        self.assertEqual(r["evidence"]["verdicts"]["frontright"], "RATIO")

    def test_an_inverted_gyro_fails_and_says_why(self):
        run = {"run:capture": {"ok": True, "outcome": "DONE", "run_file": "cap.json"}}
        with mock.patch("slothtune.runs.load", return_value={}), \
                mock.patch("slothtune.advisor.hand_check", return_value={"gyro": {"heading": {"verdict": "INVERTED", "net": -88}}}):
            r = S.c_hand_gyro(FakeCtx(run))
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("invertedIMU", r["details"][0])

    def test_offsets_within_a_degree_pass_and_bigger_ones_wait_for_a_person(self):
        run = {"run:capture": {"ok": True, "outcome": "DONE", "run_file": "cap.json"}}
        small = {"offsets": {"frontleft": {"old": 10.0, "new": 10.4}, "frontright": {"old": 359.8, "new": 0.3}}, "ok": True}
        self.assertEqual(S.c_offsets(FakeCtx({**run, "offsets": small}))["verdict"], "pass")
        big = {"offsets": {"frontleft": {"old": 10.0, "new": 190.0}}, "ok": True}
        r = S.c_offsets(FakeCtx({**run, "offsets": big}))
        self.assertEqual(r["verdict"], "person")
        self.assertIn("--yes", r["then"])

    def test_tests_on_blocks_need_a_persons_word(self):
        with self.assertRaises(S.SessionError):
            S.c_directions(FakeCtx())
        r = S.c_directions(FakeCtx({"run:drive_step": {"ok": True, "outcome": "DONE", "report": {}}}, opts={"blocks": True}))
        self.assertEqual(r["verdict"], "person", "the tool can't see which way a wheel turned on blocks: a person marks it")

    def test_letting_go_of_the_deadman_must_stop_the_test(self):
        stopped = {"run:drive_step": {"ok": False, "outcome": "ABORTED", "message": "Deadman released.", "code": "DEADMAN"}}
        self.assertEqual(S.c_fault_deadman(FakeCtx(stopped, opts={"blocks": True}))["verdict"], "pass")
        ran = {"run:drive_step": {"ok": True, "outcome": "DONE"}}
        self.assertEqual(S.c_fault_deadman(FakeCtx(ran, opts={"blocks": True}))["verdict"], "fail")

    def test_an_unplugged_encoder_must_be_named(self):
        lk = FakeLink(live={"abs_issue": [0, 0, 1, 0], "watch": []})
        r = S.c_fault_encoder(FakeCtx(link=lk))
        self.assertEqual(r["verdict"], "pass")
        self.assertIn("backleft", r["summary"])

    def test_an_unplugged_deadman_controller_must_be_noticed(self):
        lk = FakeLink(**{C.STATUS_DEADMAN_CONTROLLER: False})
        self.assertEqual(S.c_fault_controller(FakeCtx(link=lk))["verdict"], "pass")

    def test_a_crash_in_a_check_is_recorded_as_a_tool_defect(self):
        with tempfile.TemporaryDirectory() as d:
            rec = S.Record.new("Black team", {"sim": True}, folder=d)
            step = S.Step("boom", "connect", "t", "w", ["x"], "p", check=lambda ctx: int("not a number"))
            with mock.patch.object(S, "Ctx", lambda *a, **k: FakeCtx()):
                res = S.run_check(rec, step, None)
            self.assertEqual(res["verdict"], "error")
            self.assertIn("ValueError", res["summary"])
            self.assertEqual(rec.state("boom"), "error")


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(S, "SESSIONS", self.tmp.name)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main([*argv, "--json"])
        return code, json.loads(buf.getvalue())

    def test_marks_notes_issues_and_the_report(self):
        S.Record.new("Black team", {"sim": False}, "Stuart")
        self.assertEqual(self.cli("session", "mark", "directions", "pass", "--note", "all four forward")[0], 0)
        self.cli("session", "note", "battery 3 in")
        self.cli("session", "issue", "deadman", "the chip said held when it wasn't")
        code, d = self.cli("session", "report")
        self.assertEqual(code, 0)
        with open(d["report"], encoding="utf-8") as fh:
            text = fh.read()
        for want in ("# Sloth Tune session: Black team", "## 2. Bring-up", "| Every wheel drives the right way | pass |",
                     "## Sloth Tune issues found", "the chip said held when it wasn't (step deadman)", "UTC"):
            self.assertIn(want, text)

    def test_a_bad_mark_says_how(self):
        S.Record.new("Black team", {})
        code, d = self.cli("session", "mark", "directions", "great")
        self.assertNotEqual(code, 0)
        self.assertIn("pass|fail", d["error"])

    def test_a_person_only_step_cant_be_checked(self):
        S.Record.new("Black team", {})
        code, d = self.cli("session", "check", "sticks")
        self.assertNotEqual(code, 0)
        self.assertIn("session mark sticks", d["error"])


if __name__ == "__main__":
    unittest.main()
