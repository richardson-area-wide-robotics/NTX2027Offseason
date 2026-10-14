"""Where to start and what to do next (the tools' cards), and redoing one part (setup.py)."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from swervetune import cli, progress, server, setup as SP, yagslcfg as Y

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
EARLY, START, LATE = "20261013-080000", "20261013-100000", "20261013-110000"


class Robot:
    name = "Robot"

    def __init__(self, tune=None):
        self.data = {"swervetune.json": tune or {}}


def ctx(**kw):
    c = {"project": Robot(kw.pop("tune", None)), "robot": "Robot", "prog": {}, "runs": [], "connected": False,
         "live_motors": [], "lint": [], "pp": None, "inventory": {"rows": [], "findings": []}}
    c.update(kw)
    return c


def run(test, env, saved, module="ALL", score=100):
    return {"test": test, "env": env, "saved": saved, "module": module, "outcome": "DONE", "practice": False,
            "score": score, "robot": "Robot"}


def mark(result="pass", when=LATE, detail=""):
    return {"result": result, "when": when, "detail": detail}


def jobs(plan):
    return {j["id"]: j["status"] for j in plan["jobs"]}


class CalibrateTest(unittest.TestCase):
    def test_a_new_robot_starts_at_the_module_positions(self):
        p = SP.calibrate(ctx())
        self.assertEqual(p["next"]["id"], "positions")
        self.assertEqual(p["done"], 0)
        self.assertEqual(jobs(p)["camera"], "skip", "no camera listed")
        self.assertEqual(jobs(p)["field"], "optional")

    def test_each_camera_lens_is_calibrated_before_its_mount(self):
        self.assertEqual(jobs(SP.calibrate(ctx()))["lens"], "skip", "no camera listed")
        cams = {"vision": {"cameras": ["front", "back"]}}
        p = SP.calibrate(ctx(tune=cams, prog={"cal_lens_front": mark()}))
        lens = [j for j in p["jobs"] if j["id"] == "lens"][0]
        self.assertEqual((lens["title"], lens["status"], lens["detail"]), ("6. Camera lens", "todo", "Not calibrated yet: back"))
        self.assertEqual([j["title"] for j in p["jobs"]][-3:], ["6. Camera lens", "7. Camera positions", "8. Field tags"])
        st = jobs(SP.calibrate(ctx(tune=cams, prog={"cal_lens_front": mark(), "cal_lens_back": mark("fail")})))
        self.assertEqual(st["lens"], "attention", "a high mean error: recalibrate")

    def test_each_job_waits_for_what_it_needs(self):
        st = jobs(SP.calibrate(ctx()))
        self.assertEqual(st["wheels"], "later", "a crooked wheel measures short: offsets first")
        self.assertEqual(st["spin"], "later", "no floor spin yet")
        self.assertEqual(st["moi"], "todo", "weighing needs nothing")
        st = jobs(SP.calibrate(ctx(prog={"offsets": "verified"}, tune={"robotMassKg": 52.0})))
        self.assertEqual(st["wheels"], "todo")
        self.assertEqual(st["moi"], "later", "the spin compares against the floor feedforward")
        st = jobs(SP.calibrate(ctx(tune={"robotMassKg": 52.0}, runs=[run("drive_ff", "FIELD", LATE), run("spin", "FIELD", LATE)])))
        self.assertEqual((st["moi"], st["spin"]), ("todo", "todo"))

    def test_the_tools_results_tick_the_jobs(self):
        p = SP.calibrate(ctx(prog={"offsets": "verified", "cal_positions": mark(), "cal_wheels": mark("fail", detail="one wheel 6% off"),
                                   "cal_gyro_still": mark(), "cal_gyro_turns": mark("fail", detail="reads 2% short")},
                             tune={"robotMassKg": 52, "robotMoiKgM2": 5.1, "vision": {"cameras": ["front"]}}))
        st = jobs(p)
        self.assertEqual((st["positions"], st["wheels"], st["gyro"], st["moi"], st["camera"]),
                         ("done", "attention", "attention", "done", "todo"))
        self.assertEqual(p["next"]["id"], "wheels", "the first job needing work, in order")

    def test_everything_done_points_on_to_the_controllers(self):
        p = SP.calibrate(ctx(prog={"cal_positions": mark(), "cal_wheels": mark(), "cal_spin": mark(), "cal_gyro_still": mark(),
                                   "cal_gyro_turns": mark()}, tune={"robotMassKg": 52, "robotMoiKgM2": 5.1}))
        self.assertIsNone(p["next"])
        self.assertEqual(p["after"], {"tab": "controllers", "label": "Next: Controllers"}, "the tools run in order")
        self.assertEqual((p["done"], p["of"]), (5, 5), "the skipped camera and optional field don't count")

    def test_the_order_names_an_earlier_tool_with_jobs_left(self):
        c = ctx(tune={"robotMassKg": 52, "robotMoiKgM2": 5.1})
        o = SP.with_order("calibrate", c)["order"]
        self.assertEqual(o["chain"], SP.CHAIN)
        self.assertEqual(o["index"], SP.CHAIN.index("calibrate"))
        if o["earlier"]:
            self.assertIn(o["earlier"]["tab"], SP.CHAIN[:o["index"]])
            self.assertGreater(o["earlier"]["count"], 0)
        self.assertIsNone(SP.with_order("config", c)["order"]["earlier"],
                          "only Bring-up comes before Config, and only once a design file exists")


class OtherToolsTest(unittest.TestCase):
    def test_config_errors_then_pathplanner_then_batteries(self):
        c = ctx(lint=[{"id": "x", "level": "error"}, {"id": "y", "level": "warn"}, {"id": "pathplanner_names", "level": "error"}],
                pp={"used": True, "rows": [{"key": "robotMass", "status": "unknown"}], "findings": []})
        st = jobs(SP.config(c))
        self.assertEqual((st["errors"], st["warnings"], st["pathplanner"], st["batteries"]), ("attention", "optional", "later", "todo"))
        c = ctx(tune={"batteries": [1, 2]}, battery_grades_stale=True,
                pp={"used": True, "rows": [{"key": "maxDriveSpeed", "status": "differs"}], "findings": []})
        st = jobs(SP.config(c))
        self.assertEqual((st["errors"], st["pathplanner"], st["batteries"]), ("done", "attention", "attention"))

    def test_motors_needs_the_robot(self):
        st = jobs(SP.motors(ctx()))
        self.assertEqual((st["connect"], st["live"]), ("todo", "later"))
        st = jobs(SP.motors(ctx(connected=True, live_motors=[{"name": "Shooter leader", "present": 0}])))
        self.assertEqual((st["connect"], st["live"]), ("done", "attention"))

    def test_wiring_counts_the_ports_and_the_order(self):
        c = ctx(controllers=["a", "b"], wiring_map={"pdhPorts": {"a": 3}, "buses": [{"orderConfirmed": True}]},
                prog={"wire_ohms": mark()}, wiring_saved=True)
        p = SP.wiring(c)
        st = jobs(p)
        self.assertEqual((st["ohms"], st["pdh"], st["order"], st["saved"]), ("done", "todo", "done", "done"))
        self.assertIn("1 of 2", [j for j in p["jobs"] if j["id"] == "pdh"][0]["detail"])

    def test_termination_is_checked_on_every_bus(self):
        two = {"buses": [{"name": "rio", "chain": []}, {"name": "mech", "chain": []}], "pdhPorts": {}}
        def ohms(prog):
            j = [x for x in SP.wiring(ctx(controllers=[], wiring_map=two, prog=prog))["jobs"] if x["id"] == "ohms"][0]
            return j["status"], j["detail"]
        st, detail = ohms({"wire_ohms:rio": mark()})
        self.assertEqual(st, "todo")
        self.assertIn("1 of 2", detail)
        self.assertEqual(ohms({"wire_ohms:rio": mark(), "wire_ohms:mech": mark()})[0], "done")
        st, detail = ohms({"wire_ohms:rio": mark(), "wire_ohms:mech": mark("fail")})
        self.assertEqual(st, "attention")
        self.assertIn("mech", detail)
        self.assertEqual(ohms({"wire_ohms": mark()})[0], "todo", "an older single check can't say which bus")

    def test_controllers_by_their_names_and_the_deadband(self):
        hist = [{"label": "Driver", "when": LATE, "verdict": "good", "recommended_deadband": 0.12, "problems": []},
                {"label": "Operator", "when": LATE, "verdict": "error", "problems": ["button 3 bounces"]}]
        st = jobs(SP.controllers_plan(ctx(controller_history=hist, code_deadband=0.1)))
        self.assertEqual((st["driver"], st["tester"], st["deadband"]), ("done", "attention", "attention"))


class PartTest(unittest.TestCase):
    def test_only_work_since_the_start_counts(self):
        prog = {"parts": {"module:frontleft": {"started": START, "marks": {
            "hand_wheel": mark(when=EARLY), "offset": mark(when=LATE)}}}}
        c = ctx(prog=prog, runs=[run("capture", "DISABLED", EARLY), run("steer_step", "BLOCKS", LATE, module="FL", score=85)])
        st = jobs(SP.part_plan("module", "frontleft", c, START))
        self.assertEqual(st["health"], "todo", "the capture was before the module changed")
        self.assertEqual(st["hand_wheel"], "todo", "so was that hand check")
        self.assertEqual(st["offset"], "done")
        self.assertEqual(st["steer"], "done", "FL is frontleft's short name")

    def test_another_modules_run_does_not_count(self):
        c = ctx(runs=[run("steer_step", "BLOCKS", LATE, module="BR", score=100)])
        self.assertEqual(jobs(SP.part_plan("module", "frontleft", c, START))["steer"], "todo")
        c = ctx(runs=[run("steer_step", "BLOCKS", LATE, module="ALL", score=100)])
        self.assertEqual(jobs(SP.part_plan("module", "frontleft", c, START))["steer"], "done", "a run on all four counts")

    def test_a_new_field(self):
        prog = {"parts": {"field": {"started": START, "marks": {"field_type": mark(detail="AndyMark")}}}}
        c = ctx(prog=prog, layout_saved=True, layout_mtime=LATE)
        st = jobs(SP.part_plan("field", "", c, START))
        self.assertEqual((st["type"], st["survey"], st["upload"]), ("done", "done", "todo"))
        c["layout_mtime"] = EARLY
        self.assertEqual(jobs(SP.part_plan("field", "", c, START))["survey"], "todo", "last event's survey")

    def test_a_camera_and_a_motor(self):
        c = ctx(tune={"vision": {"cameras": ["front"]}}, prog={"cal_camera_front": mark()})
        self.assertEqual(jobs(SP.part_plan("camera", "front", c, START)), {"listed": "done", "position": "done", "field": "optional"})
        self.assertEqual(jobs(SP.part_plan("camera", "back", c, START))["listed"], "todo")
        c = ctx(inventory={"rows": [{"name": "frontleft drive", "motor": "NEO Vortex", "status": "ok", "can_id": 3}]})
        p = SP.part_plan("motor", "frontleft drive", c, START)
        self.assertEqual(jobs(p)["type"], "done")
        self.assertEqual([j["go"] for j in p["jobs"] if j["id"] == "module"], [{"part": "module", "which": "frontleft"}])

    def test_the_real_robots_have_every_plan(self):
        for robot in ("Peashooter", "Black team"):
            p = Y.Project(os.path.join(REPO, robot))
            c = SP.gather(p)
            for fn in SP.TOOLS.values():
                plan = fn(c)
                self.assertTrue(plan["jobs"], robot)
            for kind in SP.PARTS:
                which = {"module": p.module_names()[0], "motor": p.module_names()[0] + " drive", "camera": "front"}.get(kind, "")
                self.assertTrue(SP.part_plan(kind, which, c, START)["jobs"], (robot, kind))


def design(motors, sensors=()):
    return {"version": 1, "controller": "roborio2", "canBuses": [{"name": "rio", "color": "yellow"}],
            "motors": list(motors), "sensors": list(sensors)}


def dm(name, cid, **kw):
    m = {"name": name, "motor": {"type": "sparkflex_vortex", "id": cid, "canbus": "rio"}}
    m.update(kw)
    return m


def bctx(**kw):
    wm = {"buses": [{"name": "rio", "chain": ["roboRIO", "PDH"], "orderConfirmed": False}], "pdhPorts": {}}
    return ctx(wiring_map=wm, wiring_saved=False, controllers=[], **kw)


class BringupPlanTest(unittest.TestCase):
    def test_a_new_robot_starts_with_its_design_file(self):
        p = SP.bringup(bctx())
        st = jobs(p)
        self.assertEqual(p["next"]["id"], "design")
        self.assertEqual((st["code"], st["motors"], st["shafts"], st["sensors"]), ("later", "later", "later", "later"),
                         "nothing to check the robot against yet")
        self.assertEqual(p["after"], None)

    def test_each_mechanism_motor_and_each_shaft_is_checked(self):
        d = design([dm("frontleft drive", 5), dm("Shooter leader", 10, shaft="shooter", gearRatio=1),
                    dm("Shooter follower", 11, shaft="shooter", gearRatio=1, follows={"leader": "Shooter leader", "inverted": True}),
                    dm("Intake pivot", 12)])
        self.assertEqual([m["name"] for m in SP.mechanism_motors(d)], ["Shooter leader", "Intake pivot"],
                         "not the swerve's (the Guide does those), not a follower (its leader's run checks it)")
        c = bctx(design=d, design_check=[], design_compare=[], connected=True,
                 prog={"bu_motor:Shooter leader": mark(), "bu_motor:Intake pivot": mark("fail", detail="wrong way")})
        st = jobs(SP.bringup(c))
        self.assertEqual((st["design"], st["code"], st["motors"], st["shafts"], st["sensors"]),
                         ("done", "done", "attention", "todo", "skip"))
        c["prog"].update({"bu_motor:Intake pivot": mark(), "bu_shaft:shooter": mark()})
        st = jobs(SP.bringup(c))
        self.assertEqual((st["motors"], st["shafts"]), ("done", "done"))

    def test_the_code_disagreeing_needs_a_fix(self):
        c = bctx(design=design([dm("Tower", 18)]), design_check=[],
                 design_compare=[{"level": "error", "title": "Tower: CAN ID 18 in the design, 19 in the code", "why": ""}])
        self.assertEqual(jobs(SP.bringup(c))["code"], "attention")

    def test_bringup_comes_first_only_once_started(self):
        c = bctx()
        self.assertIsNone(SP.with_order("config", c)["order"]["earlier"], "no design file: not a nag on an old robot")
        c.update(design=design([dm("Tower", 18)]), design_check=[], design_compare=[])
        self.assertEqual(SP.with_order("config", c)["order"]["earlier"]["tab"], "bringup")
        self.assertEqual(SP.CHAIN[0], "bringup")


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.object(progress, "PATH", os.path.join(self.tmp, "progress.json"))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.proj = mock.patch.object(server.S, "project", Y.Project(os.path.join(REPO, "Peashooter")))
        self.proj.start()
        self.addCleanup(self.proj.stop)

    def test_start_mark_and_stop_a_part(self):
        self.assertIsNone(server.api_part_plan({"kind": "module", "which": "frontleft"})["started"])
        self.assertFalse(server.api_part_start({"kind": "module"})["ok"], "which module?")
        p = server.api_part_start({"kind": "module", "which": "frontleft"})
        self.assertTrue(p["started"])
        self.assertEqual(jobs(p)["offset"], "todo")
        p = server.api_part_mark({"kind": "module", "which": "frontleft", "step": "offset", "result": "pass", "detail": "Offset 12.3"})
        self.assertEqual(jobs(p)["offset"], "done")
        self.assertEqual(server.api_parts()["active"][0]["which"], "frontleft")
        server.api_part_stop({"kind": "module", "which": "frontleft"})
        self.assertEqual(server.api_parts()["active"], [])

    def test_an_unstarted_part_previews_its_jobs_with_nothing_counted(self):
        server.api_mark({"key": "cal_health", "result": "pass", "detail": "All green."})
        p = server.api_part_plan({"kind": "module", "which": "frontleft"})
        self.assertTrue(p["preview"])
        self.assertIsNone(p["started"])
        self.assertTrue(p["jobs"], "the jobs it would ask for")
        self.assertNotIn("done", jobs(p).values(), "a health check from before the part changed never counts")

    def test_the_simulator_never_counts(self):
        sim = mock.Mock()
        sim.is_connected.return_value = True
        sim.environment.return_value = {"active": "SIM"}
        server.api_part_start({"kind": "module", "which": "frontleft"})
        with mock.patch.object(server.S, "link", sim):
            self.assertFalse(server.api_mark({"key": "cal_positions", "result": "pass"})["ok"])
            self.assertFalse(server.api_part_mark({"kind": "module", "which": "frontleft", "step": "offset", "result": "pass"})["ok"])
        prog = progress.load("Peashooter")
        self.assertNotIn("cal_positions", prog)
        self.assertEqual(prog["parts"]["module:frontleft"]["marks"], {})

    def test_a_tools_mark_and_its_card(self):
        self.assertFalse(server.api_mark({"key": "geometry", "result": "pass"})["ok"], "only the tools' own keys")
        server.api_mark({"key": "cal_positions", "result": "pass", "detail": "Matches the files."})
        p = server.api_setup({"tab": "calibrate"})
        self.assertEqual(jobs(p)["positions"], "done")
        self.assertEqual(p["next"]["id"], "gyro", "wheels and spin wait; the gyro is next")

    def test_a_parts_offset_writes_only_its_module(self):
        res = {"frontleft": {"new": 12.0}, "frontright": {"new": 99.0}}
        with mock.patch.object(server.runs, "load", return_value={}), \
                mock.patch.object(server.advisor, "offsets_from_capture", return_value=res):
            every = server._edits_from({"kind": "offsets", "file": "x"})
            one = server._edits_from({"kind": "offsets", "file": "x", "module": "frontleft"})
        self.assertEqual(len(every), 2)
        self.assertEqual(one, [("modules/frontleft.json", ("absoluteEncoderOffset",), 12.0)])

    def test_bringup_drafts_a_design_file_and_saves_it_only_through_the_preview(self):
        from swervetune import design as D
        r = server.api_bringup()
        self.assertEqual((r["ok"], r["exists"]), (True, False))
        d = server.api_bringup_draft({"controller": "systemcore"})
        self.assertEqual(d["design"]["controller"], "systemcore")
        self.assertEqual(len(d["design"]["motors"]), 15)
        p = server.api_save_preview({"kind": "design", "design": d["design"]})
        self.assertTrue(p["ok"])
        self.assertEqual(p["files"], ["src/main/deploy/design/devices.json"])
        self.assertIn('+  "controller": "systemcore"', p["diff"])
        self.assertFalse(server.api_save_preview({"kind": "design", "design": {"robot": "x"}})["ok"], "not a design file")
        self.assertFalse(os.path.exists(D.path(server.S.project)), "a preview writes nothing")

    def test_bringup_marks_are_kept(self):
        self.assertTrue(server.api_mark({"key": "bu_motor:Tower", "result": "pass", "detail": "right way"})["ok"])
        self.assertEqual(progress.load("Peashooter")["bu_motor:Tower"]["result"], "pass")

    def test_the_cli_starts_a_part_and_says_whats_next(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["setup", "--project", "Peashooter", "--part", "gyro", "--start", "--json"])
        d = json.loads(buf.getvalue())
        self.assertEqual((d["ok"], d["part"]), (True, "gyro"))
        self.assertEqual(d["plan"]["next"]["id"], "health")

    def cli_json(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["setup", "--project", "Peashooter", *argv, "--json"])
        return json.loads(buf.getvalue())

    def test_the_cli_takes_the_robots_short_names(self):
        d = self.cli_json("--part", "module:FL")
        self.assertEqual(d["part"], "module:frontleft", "FL is frontleft, as the tuner and the robot accept")
        self.assertTrue(d["preview"], "not started: its jobs, and how to start it")
        self.assertIn("--start", d["hint"])

    def test_the_cli_names_the_robots_parts_when_one_is_wrong(self):
        d = self.cli_json("--part", "module:nope")
        self.assertEqual((d["ok"], d["code"]), (False, "BAD_ARGS"))
        self.assertIn("frontleft", d["error"])
        d = self.cli_json("--part", "module")
        self.assertEqual(d["code"], "BAD_ARGS", "which module?")
        d = self.cli_json("--part", "wheel")
        self.assertEqual(d["code"], "BAD_ARGS")


if __name__ == "__main__":
    unittest.main()
