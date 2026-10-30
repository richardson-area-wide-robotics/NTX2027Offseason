"""The accuracy maneuvers: the laptop's catalog against the robot's, the plan's geometry, and the
report that judges a run against 1 in for every 10 ft driven."""

import io
import json
import math
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout

from slothtune import advisor, cli, contract as C, maneuvers as MV, server

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
LIB = os.path.join(REPO, "common", "slothtune")
IN = 0.0254


def read(*parts):
    with open(os.path.join(LIB, *parts), encoding="utf-8") as fh:
        return fh.read()


def run_doc(name, end_in=(0.0, 0.0), end_deg=None, settled=True, vision=None, outcome="DONE"):
    """A finished maneuver as the robot sends it: its legs, the plan, odometry's end (inches from
    the plan), and optionally AprilTag poses at the start and the end."""
    i = next(k for k, m in enumerate(MV.CATALOG) if m["name"] == name)
    m = MV.CATALOG[i]
    ex, ey, edeg = MV.expected_pose(m["legs"])
    n = len(m["legs"])
    meta = {"maneuver_index": i, "maneuver_id": MV.ident(name), "family": m["family"],
            "returns": int(m["family"] != MV.PERMUTATION), "legs": n,
            "expected_x": ex, "expected_y": ey, "expected_deg": edeg, "vision_in_use": 0,
            "end_x": ex + end_in[0] * IN, "end_y": ey + end_in[1] * IN,
            "end_deg": edeg if end_deg is None else end_deg, "complete": 1, "legs_done": n}
    for k, (kind, v) in enumerate(m["legs"]):
        meta[f"leg{k}_turn"] = int(kind == "turn")
        meta[f"leg{k}_value"] = v
        meta[f"leg{k}_settled"] = 1 if settled else 0
        meta[f"leg{k}_residual"] = 0.001 if settled else 0.05
    rows = 40
    leg = [-1] * 10 + [0] * 20 + [n] * 10
    ch = {"t": [k * 0.02 for k in range(rows)], "leg": leg, "x": [0.0] * rows, "y": [0.0] * rows,
          "heading": [0.0] * rows, "vbus": [12.5] * rows}
    if vision:
        (x0, y0, d0), (x1, y1, d1) = vision
        ch["vx_vision"] = [x0] * 10 + [float("nan")] * 20 + [x1] * 10
        ch["vy_vision"] = [y0] * 10 + [float("nan")] * 20 + [y1] * 10
        ch["vdeg_vision"] = [d0] * 10 + [float("nan")] * 20 + [d1] * 10
    return {"test": "maneuver", "env": "FIELD", "outcome": outcome, "channels": ch, "meta": meta,
            "notes": [f"Maneuver {name} ({i} of {len(MV.CATALOG)}): {m['description']}."]}


class CatalogTest(unittest.TestCase):
    def test_twenty_five_in_the_robots_order(self):
        self.assertEqual(len(MV.CATALOG), 25)
        self.assertEqual([m["family"] for m in MV.CATALOG], [0] * 16 + [1] * 4 + [2] * 5)
        # Pinned in ManeuverCatalogTest.java too.
        for i, name in ((0, "P_10ft_L90_fwd10ft"), (2, "P_10ft_R90_fwd10ft"), (16, "OB_same_straight10ft"),
                        (20, "OB_diff_square5ft"), (24, "OB_diff_triangle")):
            self.assertEqual(MV.CATALOG[i]["name"], name)

    def test_the_loop_names_match_the_java_in_order(self):
        src = read("java", "frc", "lib", "slothtune", "ManeuverCatalog.java")
        java = re.findall(r'new Maneuver\("(OB_\w+)"', src)
        self.assertEqual(java, [m["name"] for m in MV.CATALOG if m["name"].startswith("OB_")])
        for piece in ('{"10ft", "5ft"}', "{90, 270}", '{"L", "R"}', '{"fwd10ft", "rev10ft"}'):
            self.assertIn(piece, src, "the permutations are built from these")

    def test_ids_are_the_robots(self):
        test = read("test", "frc", "lib", "slothtune", "ManeuverCatalogTest.java")
        for name, want in (("OB_diff_square5ft", 131818226), ("P_10ft_L90_fwd10ft", 443694424)):
            self.assertEqual(MV.ident(name), want)
            self.assertIn(f"{want}L", test, "the Java test pins the same number")
        ids = [MV.ident(m["name"]) for m in MV.CATALOG]
        self.assertEqual(len(set(ids)), 25)
        self.assertTrue(all(0 <= i < 2 ** 31 for i in ids))

    def test_every_loop_closes_and_nothing_goes_behind_the_start(self):
        for m in MV.CATALOG:
            x, y, d = MV.expected_pose(m["legs"])
            e = MV.extent(m["legs"])
            self.assertAlmostEqual(e["behind"], 0.0, places=9, msg=m["name"])
            if m["family"] != MV.PERMUTATION:
                self.assertAlmostEqual(math.hypot(x, y), 0.0, places=6, msg=m["name"])
                self.assertAlmostEqual(d, 0.0, places=6, msg=m["name"])

    def test_a_permutations_end(self):
        x, y, d = MV.expected_pose(MV.by_name("P_5ft_R270_rev10ft")["legs"])
        self.assertAlmostEqual(x, MV.FIVE_FT)
        self.assertAlmostEqual(y, -MV.TEN_FT, msg="270 right faces left; reversing from there goes right")
        self.assertAlmostEqual(d, 90.0)

    def test_mirrors(self):
        self.assertEqual(MV.mirror("P_10ft_L90_fwd10ft"), "P_10ft_R90_fwd10ft")
        self.assertEqual(MV.mirror("P_5ft_R270_rev10ft"), "P_5ft_L270_rev10ft")
        self.assertEqual(MV.mirror("OB_diff_square5ft"), "OB_diff_square5ft_right")
        self.assertEqual(MV.mirror("OB_diff_mixed_turns"), "OB_diff_rectangle")
        self.assertIsNone(MV.mirror("OB_diff_triangle"))

    def test_the_server_lists_them_for_the_picker(self):
        r = server.api_maneuvers(None)
        self.assertEqual(len(r["maneuvers"]), 25)
        sq = r["maneuvers"][20]
        self.assertEqual((sq["name"], sq["id"], sq["family"]), ("OB_diff_square5ft", 131818226, "different_path"))
        self.assertAlmostEqual(sq["budget_m"], 2 * IN, msg="20 ft driven: 2 in")
        self.assertAlmostEqual(r["maneuvers"][17]["budget_m"], 1 * IN, msg="10 ft driven: 1 in")


class ReportTest(unittest.TestCase):
    def test_without_a_tape_it_is_not_scored(self):
        rep = advisor.analyze(run_doc("OB_diff_square5ft", end_in=(0.2, -0.1)), {})
        self.assertTrue(rep["needs_truth"])
        self.assertIsNone(rep["score"])
        self.assertIn("not measured", rep["summary"])
        self.assertTrue(rep["findings"][0]["title"].startswith("Not measured yet"), rep["findings"][0])
        self.assertAlmostEqual(rep["measured"]["odometry_residual_m"], math.hypot(0.2, 0.1) * IN)

    def test_a_tape_inside_the_budget_passes(self):
        doc = run_doc("OB_diff_square5ft")
        rep = advisor.analyze(doc, {}, measured_forward_m=1.2 * IN, measured_lateral_m=-0.9 * IN)
        self.assertEqual(rep["score"], 100)
        self.assertAlmostEqual(rep["measured"]["error_m"], 1.5 * IN)
        self.assertAlmostEqual(rep["measured"]["closure_m"], 1.5 * IN)
        self.assertTrue(any(f["level"] == "ok" and "Within the budget" in f["title"] for f in rep["findings"]))
        self.assertLess(rep["cost"], 1.0)

    def test_a_tape_over_the_budget_fails_and_says_what_the_family_isolates(self):
        rep = advisor.analyze(run_doc("OB_same_straight10ft"), {}, measured_forward_m=-2.5 * IN, measured_lateral_m=0.0)
        self.assertLess(rep["score"], 100)
        bad = next(f for f in rep["findings"] if f["title"].startswith("Over the accuracy budget"))
        self.assertIn("2.5 in off, budget 2.0 in", bad["title"], "20 ft driven, out and back")
        self.assertIn("wheel size cancels", bad["why"])
        fam = next(f for f in rep["findings"] if f.get("kind") == "family")
        self.assertEqual(fam["action"], {"type": "run", "test": "maneuver", "env": "FIELD",
                                         "args": {"id": MV.ident("OB_same_turnaround10ft")}})

    def test_the_budget_scales_with_the_travel(self):
        # 20 ft driven: 2 in allowed; 1.8 in passes here and would fail a 10 ft maneuver.
        perm = advisor.analyze(run_doc("P_10ft_L90_fwd10ft"), {}, measured_forward_m=MV.TEN_FT + 1.8 * IN,
                               measured_lateral_m=MV.TEN_FT)
        self.assertEqual(perm["score"], 100)
        self.assertAlmostEqual(perm["measured"]["budget_m"], 2 * IN)
        short = advisor.analyze(run_doc("OB_same_straight5ft"), {}, measured_forward_m=1.8 * IN, measured_lateral_m=0.0)
        self.assertLess(short["score"], 100)

    def test_along_and_across_the_last_heading(self):
        # P_10ft_L90: it ends facing left (+y). 1 in further along +y is along-track; +x is to its right.
        rep = advisor.analyze(run_doc("P_10ft_L90_fwd10ft"), {}, measured_forward_m=MV.TEN_FT + 1.0 * IN,
                              measured_lateral_m=MV.TEN_FT + 1.0 * IN)
        self.assertAlmostEqual(rep["measured"]["along_m"], 1.0 * IN)
        self.assertAlmostEqual(rep["measured"]["cross_m"], -1.0 * IN)

    def test_a_heading_off_by_more_than_half_a_degree_fails(self):
        rep = advisor.analyze(run_doc("OB_diff_square5ft"), {}, measured_forward_m=0.5 * IN, measured_lateral_m=0.0,
                              measured_heading_deg=1.2)
        self.assertEqual(rep["measured"]["heading_error_deg"], 1.2)
        heading = next(t for t in rep["targets"] if t["name"].startswith("heading"))
        self.assertFalse(heading["met"])
        self.assertTrue(any("facing +1.2° off" in f["title"] for f in rep["findings"]))

    def test_a_tape_far_off_is_a_measuring_mistake(self):
        rep = advisor.analyze(run_doc("OB_diff_square5ft"), {}, measured_forward_m=60 * IN, measured_lateral_m=0.0)
        self.assertEqual(rep["measured"]["truth_rejected"], "the tape")
        self.assertTrue(rep["needs_truth"])
        self.assertTrue(any("too far to be the drivetrain" in f["why"] for f in rep["findings"]))

    def test_apriltags_standing_still_at_both_ends_score_it(self):
        # Facing +x on the field at the start, so 1 in further along the field's +y is 1 in left.
        doc = run_doc("OB_same_straight5ft", vision=((2.0, 1.0, 0.0), (2.0, 1.0 + 1.0 * IN, 0.1)))
        rep = advisor.analyze(doc, {})
        self.assertEqual(rep["measured"]["truth"], "AprilTags")
        self.assertAlmostEqual(rep["measured"]["truth_y_m"], 1.0 * IN)
        self.assertAlmostEqual(rep["measured"]["heading_error_deg"], 0.1)
        self.assertNotIn("needs_truth", rep)

    def test_odometry_far_from_the_tape_points_at_wheel_size(self):
        rep = advisor.analyze(run_doc("OB_same_straight10ft", end_in=(0.0, 0.0)), {},
                              measured_forward_m=1.0 * IN, measured_lateral_m=0.0)
        self.assertEqual(rep["score"], 100)
        doc = run_doc("P_10ft_L90_fwd10ft")
        rep = advisor.analyze(doc, {}, measured_forward_m=MV.TEN_FT, measured_lateral_m=MV.TEN_FT + 3 * IN)
        odo = next(f for f in rep["findings"] if f["title"].startswith("The odometry thought"))
        self.assertEqual(odo["level"], "warn")
        self.assertIn("wheel size", odo["why"])
        self.assertEqual(odo["action"]["test"], "straight")

    def test_a_leg_that_never_settled_points_at_the_feedforward(self):
        rep = advisor.analyze(run_doc("OB_diff_square5ft", settled=False), {})
        loose = next(f for f in rep["findings"] if f["title"].startswith("The closed loop didn't settle"))
        self.assertEqual(loose["action"]["test"], "drive_ff")

    def test_a_robot_with_another_list_is_called_out(self):
        doc = run_doc("OB_diff_square5ft")
        doc["meta"]["maneuver_index"] = 0
        rep = advisor.analyze(doc, {})
        self.assertTrue(any("maneuver list and the robot's differ" in f["title"] for f in rep["findings"]))

    def test_a_stopped_run_is_not_scored(self):
        doc = run_doc("OB_diff_square5ft", outcome="ABORTED")
        doc["message"] = "Deadman released."
        rep = advisor.analyze(doc, {}, measured_forward_m=0.5 * IN, measured_lateral_m=0.0)
        self.assertIsNone(rep["score"])

    def test_cli_analyze_takes_small_tape_numbers_for_a_maneuver(self):
        path = os.path.join(tempfile.mkdtemp(), "maneuver.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(run_doc("OB_diff_square5ft"), fh)
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["analyze", path, "--tape-forward", "1.5", "--tape-lateral", "-0.5", "--tape-heading", "0.2", "--json"])
        doc = json.loads(buf.getvalue())
        self.assertAlmostEqual(doc["report"]["measured"]["tape_forward_m"], 1.5 * IN)
        self.assertAlmostEqual(doc["report"]["measured"]["heading_error_deg"], 0.2)


class StopCodeTest(unittest.TestCase):
    def test_the_procedures_sentences_have_their_codes(self):
        src = read("java", "frc", "lib", "slothtune", "ManeuverProcedure.java")
        found = {}
        for m in re.finditer(r'(?:return|frozen =)\s+(?:String\.format\()?\s*"([^"]+)"', src):
            found[m.group(1)] = C.stop_code(m.group(1))
        want = {"Pick a maneuver": "BAD_ARGS", "No maneuver at index": "BAD_ARGS",
                "No maneuver has that id": "CATALOG_MISMATCH", "clear floor ahead": "NO_SPACE",
                "pose stopped changing while": "ODOMETRY_FROZEN"}
        for key, code in want.items():
            hits = [s for s in found if key in s]
            self.assertTrue(hits, f"no sentence with {key!r}: {list(found)}")
            self.assertEqual(found[hits[0]], code, hits[0])
        self.assertIn("maneuver", C.TESTS)


if __name__ == "__main__":
    unittest.main()
