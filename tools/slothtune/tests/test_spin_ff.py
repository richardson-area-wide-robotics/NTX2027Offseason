"""The robot's moment of inertia from spin_ff, against a model with a known one."""

import unittest

from slothtune import advisor, plant

FLOOR_FF = [{"modules": {m: {"ok": True, "kA": 0.45, "kV": 2.9} for m in ("fl", "fr", "bl", "br")}}]


def report(moi=6.0, history=FLOOR_FF, mass=55.0, source="slothtune.json", env="FIELD", **plant_kw):
    ch, meta = plant.spin_ff(moi=moi, **plant_kw)
    doc = {"test": "spin_ff", "env": env, "channels": ch, "meta": meta, "practice": True}
    return advisor.analyze(doc, history=history, mass_kg=mass, mass_source=source, moi_estimate=6.6)


class SpinFfTest(unittest.TestCase):
    def test_known_inertias_are_recovered(self):
        for moi in (3.0, 6.0, 10.0):
            r = report(moi)
            self.assertAlmostEqual(r["measured"]["moi_kg_m2"], moi, delta=0.06 * moi, msg=moi)
            self.assertEqual(r["score"], 100)

    def test_the_result_is_a_config_change_to_save(self):
        r = report(6.0)
        self.assertEqual(r["next"]["action"]["type"], "config")
        self.assertEqual(r["next"]["action"]["path"], ["robotMoiKgM2"])
        self.assertIn("PathPlanner", r["next"]["why"])

    def test_it_needs_a_floor_drive_ff_first(self):
        r = report(history=[])
        self.assertEqual(r["next"]["action"], {"type": "run", "test": "drive_ff", "env": "FIELD"})

    def test_it_needs_the_mass(self):
        r = report(mass=None)
        self.assertIn("Weigh the robot", r["findings"][0]["title"])
        self.assertNotIn("moi_kg_m2", r["measured"])

    def test_an_assumed_mass_is_called_out_and_never_saved(self):
        r = report(source="assumed (set robotMassKg in slothtune.json)")
        moi = next(f for f in r["findings"] if f["title"].startswith("Moment of inertia"))
        self.assertIn("from an assumed 121 lb", moi["title"])   # 55 kg
        self.assertNotIn("action", moi, "a guessed mass gives a guessed MOI: weigh first")
        self.assertFalse(any((f.get("action") or {}).get("path") == ["robotMoiKgM2"] for f in r["findings"]))

    def test_scrubbing_wheels_are_flagged(self):
        # Wheels that need 30% more voltage per speed turning than driving straight: they scrub.
        r = report(history=[{"modules": {"fl": {"ok": True, "kA": 0.45, "kV": 2.9 / 1.3}}}])
        self.assertTrue(any("more voltage per wheel speed" in f["title"] for f in r["findings"]))

    def test_on_blocks_it_refuses(self):
        r = report(env="BLOCKS")
        self.assertEqual(r["next"]["action"]["env"], "FIELD")




class HistoryTest(unittest.TestCase):
    def test_simulator_runs_never_stand_in_for_the_robots(self):
        import json
        import os
        import tempfile

        from slothtune import runs

        with tempfile.TemporaryDirectory() as d:
            old, runs.RUNS = runs.RUNS, d
            try:
                for i, env in enumerate(("SIM", "FIELD", "BLOCKS")):
                    doc = {"test": "drive_ff", "env": env, "robot": {"name": "Peashooter"},
                           "saved": f"2026-10-12T1{i}:00:00", "report": {"modules": {"fl": {"ok": True, "kA": i}}}}
                    with open(os.path.join(d, f"run{i}.json"), "w", encoding="utf-8") as fh:
                        json.dump(doc, fh)
                field = runs.ff_history("Peashooter", False, env="FIELD")
                self.assertEqual([h["modules"]["fl"]["kA"] for h in field], [1])
                self.assertEqual(len(runs.ff_history("Peashooter", False)), 2, "without env: floor and sim")
            finally:
                runs.RUNS = old


if __name__ == "__main__":
    unittest.main()
