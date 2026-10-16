"""The controller check, on made-up controllers with known faults, and against the robots' code."""

import math
import os
import random
import unittest

from slothtune import controllers as C, yagslcfg as Y
from slothtune.robotrepo import ROBOTS, needs_robots

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def rows(n, dt=8.0, axes=lambda k: (0, 0, 0, 0), buttons=lambda k: {}):
    out = []
    for k in range(n):
        b = buttons(k)
        out.append([k * dt, *axes(k), *[b.get(i, 0.0) for i in range(16)]])
    return out


def titles(r):
    return " | ".join(f["title"] for f in r["findings"])


class RestTest(unittest.TestCase):
    def test_a_drifting_stick_needs_a_bigger_deadband_than_the_code_has(self):
        rng = random.Random(1)
        r = C.rest(rows(500, axes=lambda k: (0.12 + rng.gauss(0, 0.004), rng.gauss(0, 0.004), 0.01, -0.02)))
        self.assertAlmostEqual(r["axes"][0]["offset"], 0.12, delta=0.002)
        self.assertEqual(r["axes"][2]["wpilib_axis"], 4, "right stick X is WPILib axis 4")
        self.assertGreater(r["recommended_deadband"], 0.13)
        rep = C.report({"rest": r}, [{"value": 0.1, "file": "Robot.java", "line": 55}])
        self.assertEqual(rep["verdict"], "error")
        self.assertIn("past the code's 0.1 deadband", titles(rep))
        self.assertIn("Robot.java", rep["findings"][0]["why"])

    def test_a_good_controller_is_well_inside(self):
        rng = random.Random(2)
        r = C.rest(rows(500, axes=lambda k: tuple(rng.gauss(0, 0.003) for _ in range(4))))
        rep = C.report({"rest": r}, [{"value": 0.08, "file": "Drive.java", "line": 42}])
        self.assertEqual(rep["verdict"], "ok")
        self.assertLessEqual(rep["recommended_deadband"], 0.04)
        self.assertIn("well inside the code's 0.08 deadband", titles(rep))

    def test_close_to_the_deadband_is_a_warning(self):
        r = C.rest(rows(200, axes=lambda k: (0.07, 0, 0, 0)))
        rep = C.report({"rest": r}, [{"value": 0.08, "file": "Drive.java", "line": 42}])
        self.assertEqual(rep["verdict"], "warn")

    def test_a_stuck_button(self):
        r = C.rest(rows(200, buttons=lambda k: {4: 1.0}))
        self.assertIn("Left bumper", titles(r))
        self.assertEqual(r["findings"][0]["level"], "error")

    def test_too_little_data(self):
        self.assertIn("Too little data", titles(C.rest(rows(3))))


def circle(n_turns, dent=None, radius=1.0, stick="left"):
    def axes(k):
        ang = 2 * math.pi * k / 120
        r = radius
        if dent is not None and abs(((math.degrees(ang) - dent[0] + 180) % 360) - 180) < 30:
            r = dent[1]
        x, y = r * math.cos(ang), -r * math.sin(ang)  # the browser's up is negative
        return (x, y, 0, 0) if stick == "left" else (0, 0, x, y)
    return rows(120 * n_turns, axes=axes)


class SticksTest(unittest.TestCase):
    def test_full_reach_all_round(self):
        r = C.sticks(circle(3) + circle(3, stick="right"))
        self.assertGreaterEqual(r["sticks"]["left"]["reach"], 0.99)
        self.assertIn("Left stick reaches full deflection all round", titles(r))

    def test_a_worn_stick_stops_short_one_way(self):
        r = C.sticks(circle(3, dent=(135, 0.85)) + circle(3, stick="right"))
        self.assertAlmostEqual(r["sticks"]["left"]["reach"], 0.85, places=2)
        self.assertIn("Left stick only reaches 0.85 toward up-left", titles(r))

    def test_not_circled(self):
        r = C.sticks(rows(100, axes=lambda k: (0.9, 0, 0, 0)))
        self.assertIn("not circled all the way round", titles(r))


class ReturnsTest(unittest.TestCase):
    def flicks(self, settle):
        out, t = [], 0.0
        for i in range(5):
            for k in range(20):   # pushed
                out.append([t, 0.95, 0, 0, 0] + [0] * 16)
                t += 8
            for k in range(60):   # let go: lands somewhere near center
                out.append([t, settle[i % len(settle)], 0, 0, 0] + [0] * 16)
                t += 8
        return out

    def test_a_lazy_spring(self):
        r = C.returns(self.flicks([0.02, 0.07, 0.03]))
        self.assertAlmostEqual(r["sticks"]["left"]["worst"], 0.07, places=3)
        self.assertIn("Left stick comes back up to 0.07 off center", titles(r))
        rep = C.report({"rest": C.rest(rows(100)), "returns": r}, [{"value": 0.08, "file": "Drive.java", "line": 1}])
        self.assertAlmostEqual(rep["worst_offset"], 0.07, places=3, msg="the worst return sets the deadband")

    def test_too_few_flicks(self):
        self.assertIn("fewer than 3 flicks", titles(C.returns(rows(50))))


class TriggersTest(unittest.TestCase):
    def test_a_short_trigger(self):
        r = C.triggers(rows(300, buttons=lambda k: {6: 0.9 * abs(math.sin(k / 30)), 7: abs(math.sin(k / 30))}))
        self.assertIn("Left trigger only reaches 0.90", titles(r))
        self.assertNotIn("Right trigger", titles(r))
        self.assertEqual(r["triggers"]["Right trigger"]["wpilib_axis"], 3)


class ButtonsTest(unittest.TestCase):
    def test_a_bouncing_button_and_ones_never_pressed(self):
        def b(k):
            t = k * 4.0
            out = {}
            # A: three clean 100 ms presses.
            if any(s <= t < s + 100 for s in (100, 400, 700)):
                out[0] = 1.0
            # B: one press that drops out for 8 ms in the middle (a bounce).
            if 1000 <= t < 1060 or 1068 <= t < 1150:
                out[1] = 1.0
            return out
        r = C.buttons(rows(400, dt=4.0, buttons=b))
        self.assertEqual(r["buttons"]["A"], {"presses": 3, "bounces": 0, "wpilib": 1})
        self.assertEqual(r["buttons"]["B"]["presses"], 2)
        self.assertEqual(r["buttons"]["B"]["bounces"], 1)
        self.assertIn("Bouncing: B (1x)", titles(r))
        self.assertIn("Never pressed: X, Y", titles(r))

    def test_update_interval(self):
        self.assertEqual(C.update_interval_ms(rows(50, dt=4.0)), 4.0)

    def test_a_quick_tap_through_the_robot_is_not_a_bounce(self):
        # The robot samples every 20 ms: a firm quick tap is one frame pressed. That is a person.
        def b(k):
            return {0: 1.0} if k in (10, 30, 50) else {}
        r = C.buttons(rows(80, dt=20.0, buttons=b))
        self.assertEqual(r["buttons"]["A"]["presses"], 3)
        self.assertEqual(r["buttons"]["A"]["bounces"], 0)

    def test_a_one_frame_release_between_presses_is_a_bounce(self):
        # Released for one 20 ms frame and pressed again: the robot sees two presses.
        def b(k):
            return {0: 1.0} if 10 <= k < 14 or 15 <= k < 20 else {}
        r = C.buttons(rows(40, dt=20.0, buttons=b))
        self.assertEqual(r["buttons"]["A"]["bounces"], 1)


class CodeTest(unittest.TestCase):
    @needs_robots
    def test_both_robots_deadbands(self):
        pea = C.code_deadbands(Y.Project(os.path.join(ROBOTS, "Peashooter")))
        black = C.code_deadbands(Y.Project(os.path.join(ROBOTS, "Black team")))
        self.assertEqual({d["value"] for d in pea}, {0.1})
        self.assertEqual({d["file"] for d in pea}, {"Robot.java"})
        self.assertEqual({d["value"] for d in black}, {0.08})

    @needs_robots
    def test_the_axes_each_robot_reads(self):
        pea = Y.Project(os.path.join(ROBOTS, "Peashooter"))
        # Peashooter names its axes: a round deadband on the left stick, right X on its own.
        db = C.code_deadbands(pea)
        self.assertEqual([d["axes"] for d in db if d.get("round")], [[0, 1]])
        self.assertEqual([d["axis"] for d in db if not d.get("round")], [2])
        self.assertEqual(C.axes_read(pea), [0, 1, 2], "left X, left Y, right X; never right Y")
        black = Y.Project(os.path.join(ROBOTS, "Black team"))
        self.assertEqual({d["axis"] for d in C.code_deadbands(black)}, {None}, "suppliers passed in from Robot.java")
        self.assertEqual(C.axes_read(black), [0, 1, 2])

    @needs_robots
    def test_both_robots_deadband_the_left_stick_round(self):
        for robot, value in (("Peashooter", 0.1), ("Black team", 0.08)):
            p = Y.Project(os.path.join(ROBOTS, robot))
            self.assertEqual(C.round_sticks(C.code_deadbands(p), C.axes_read(p)), {"left": value}, robot)
            self.assertEqual(C.stick_deadbands(p), {"left": {"value": value, "round": True},
                                                    "right": {"value": value, "round": False}}, robot)

    def test_a_round_deadband_judges_the_distance_from_center(self):
        # 0.07 on both left axes is 0.099 from center: inside a round 0.1, outside a round 0.08.
        r = C.rest(rows(200, axes=lambda k: (0.07, 0.07, 0, 0)))
        round01 = [{"value": 0.1, "file": "Robot.java", "line": 60, "axis": None, "round": True, "axes": [0, 1]},
                   {"value": 0.1, "file": "Robot.java", "line": 62, "axis": 2}]
        rep = C.report({"rest": r}, round01, read=[0, 1, 2])
        self.assertEqual(rep["verdict"], "warn")
        self.assertIn("Left stick (distance from center) drifts 0.10, close to the code's 0.1 deadband", titles(rep))
        self.assertAlmostEqual(rep["stick_drift"]["left"], 0.099, places=3)
        round008 = [{"value": 0.08, "file": "Drive.java", "line": 45, "axis": None, "round": True, "axes": None},
                    {"value": 0.08, "file": "Drive.java", "line": 50, "axis": None}]
        rep = C.report({"rest": r}, round008, read=[0, 1, 2])
        self.assertEqual(rep["verdict"], "error")
        self.assertIn("Left stick (distance from center) drifts 0.10, past the code's 0.08 deadband", titles(rep))
        self.assertEqual(rep["recommended_deadband"], 0.12)

    def test_drift_on_an_axis_nothing_reads_never_fails_a_controller(self):
        r = C.rest(rows(200, axes=lambda k: (0.01, 0.0, 0.0, 0.2)))
        rep = C.report({"rest": r}, [{"value": 0.1, "file": "Robot.java", "line": 59, "axis": 1}], read=[0, 1, 2])
        self.assertNotEqual(rep["verdict"], "error")
        self.assertIn("axes the robot code doesn't read: Right stick Y 0.20", titles(rep))

    def test_each_axis_is_judged_on_its_own(self):
        # 0.07 on both left axes is 0.099 from center, but the code deadbands each axis: no creep.
        r = C.rest(rows(200, axes=lambda k: (0.07, 0.07, 0, 0)))
        rep = C.report({"rest": r}, [{"value": 0.08, "file": "Drive.java", "line": 42, "axis": None}], read=[0, 1, 2])
        self.assertNotEqual(rep["verdict"], "error")
        self.assertIn("close to the code's 0.08 deadband", titles(rep))

    def test_no_deadband_in_the_code_means_no_comparison(self):
        rep = C.report({"rest": C.rest(rows(100, axes=lambda k: (0.2, 0, 0, 0)))}, [])
        self.assertNotIn("deadband", titles(rep).lower().replace("deadband of", ""))
        self.assertEqual(rep["recommended_deadband"], 0.22)


class FromTheRobotTest(unittest.TestCase):
    def test_a_robot_recording_becomes_the_same_rows(self):
        ch = {"t": [0.0, 0.02, 0.04], "a0": [0.1, 0.1, 0.1], "a1": [-0.2, -0.2, -0.2], "a2": [0.0, 0.5, 1.0],
              "a3": [0.0, 0.0, 0.25], "a4": [0.3, 0.3, 0.3], "a5": [0.4, 0.4, 0.4],
              "buttons": [0, 2, 2 | 64], "pov": [-1, 90, 45]}
        rows = C.rows_from_robot(ch)
        self.assertEqual(rows[0][:5], [0.0, 0.1, -0.2, 0.3, 0.4], "WPILib axes 0, 1, 4, 5 are the sticks")
        b = lambda r, i: rows[r][5 + i]
        self.assertEqual((b(1, 1), b(1, 0)), (1.0, 0.0), "button 2 is B")
        self.assertEqual(b(2, 5), 0.0)
        self.assertEqual((b(2, 8), b(2, 9)), (1.0, 0.0), "bit 6 is WPILib button 7, Back")
        self.assertEqual((b(2, 6), b(2, 7)), (1.0, 0.25), "WPILib axes 2 and 3 are the triggers")
        self.assertEqual([b(1, i) for i in (12, 13, 14, 15)], [0, 0, 0, 1.0], "POV 90 is D-pad right")
        self.assertEqual([b(2, i) for i in (12, 13, 14, 15)], [1.0, 0, 0, 1.0], "POV 45 is up and right")
        self.assertEqual(rows[1][0], 20.0, "milliseconds")

    def test_the_robots_rows_go_through_the_same_checks(self):
        ch = {"t": [k * 0.02 for k in range(200)], **{f"a{i}": [0.12 if i == 0 else 0.0] * 200 for i in range(6)},
              "buttons": [0] * 200, "pov": [-1] * 200}
        r = C.rest(C.rows_from_robot(ch))
        self.assertAlmostEqual(r["axes"][0]["offset"], 0.12)
        self.assertEqual(C.update_interval_ms(C.rows_from_robot(ch)), 20.0)


class SavedChecksTest(unittest.TestCase):
    def test_saved_checks_never_look_like_runs(self):
        import json
        import tempfile
        from unittest import mock
        from slothtune import runs
        with tempfile.TemporaryDirectory() as d, mock.patch.object(runs, "RUNS", d),                 mock.patch.object(runs, "CONTROLLER_LOG", os.path.join(d, "data", "controllers.json")):
            with open(os.path.join(d, "20261012-100000_x_drive_ff_all.json"), "w") as f:
                json.dump({"test": "drive_ff", "robot": {"name": "x"}, "report": {"modules": {"a": {}}}}, f)
            with open(os.path.join(d, "stray-list.json"), "w") as f:
                json.dump([{"label": "old"}], f)
            with open(os.path.join(d, "setup_progress.json"), "w") as f:
                json.dump({"step": 3}, f)
            runs.controller_log_add({"label": "Driver"})
            self.assertEqual([r["file"] for r in runs.list_runs()], ["20261012-100000_x_drive_ff_all.json"])
            self.assertEqual(len(runs.ff_history("x", False)), 1)
            self.assertEqual(runs.controller_log(), [{"label": "Driver"}])


if __name__ == "__main__":
    unittest.main()
