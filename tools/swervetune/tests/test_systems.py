"""The Systems tab's model (systems.py): groups, settings, the safe test, and what a test showed."""

import math
import os
import unittest

from swervetune import advisor, systems as SY, yagslcfg
from swervetune.tests.test_mechanics import ARM, recalc

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PEA = yagslcfg.Project(os.path.join(REPO, "Peashooter"))
EXA = yagslcfg.Project(os.path.join(REPO, "Examples"))

PIVOT = {"name": "Intake pivot", "kind": "PIVOT", "units": "motor rotations", "motors": ["Intake pivot"],
         "min": 0.0, "max": 17.8}
SHOOTER = {"name": "Shooter", "kind": "FLYWHEEL", "units": "RPM", "motors": ["Shooter leader", "Shooter follower"]}
FLY = recalc("flywheel", motor={"name": "NEO Vortex", "quantity": 2}, ratio={"magnitude": 1, "ratioType": "Reduction"},
             shooterDiameter={"s": 4, "u": "in"}, shooterWeight={"s": 3, "u": "lb"}, shooterTargetSpeed={"s": 4000, "u": "rpm"})


class GroupsTest(unittest.TestCase):
    def test_peashooters_subsystems_with_their_mechanisms(self):
        g = {x["name"]: x for x in SY.groups(PEA, None, [PIVOT, SHOOTER])}
        self.assertEqual(sorted(g), ["Drive train", "Feeder", "Intake", "Shooter"])
        self.assertEqual(g["Intake"]["systems"], ["Intake pivot"], "found by its motor")
        self.assertIn("Intake roller 1", g["Intake"]["motors"])
        self.assertEqual(len(g["Drive train"]["motors"]), 8)

    def test_the_design_files_subsystems_join_them(self):
        design = {"motors": [{"name": "Arm", "subsystem": "Arm"}], "sensors": [{"name": "Intake beam", "subsystem": "Intake"}]}
        g = {x["name"]: x for x in SY.groups(PEA, design, [])}
        self.assertEqual(g["Intake"]["from"], ["code", "design"])
        self.assertEqual(g["Intake"]["sensors"], ["Intake beam"])
        self.assertEqual(g["Arm"]["from"], ["design"])

    def test_a_design_drafted_from_the_code_adds_no_groups(self):
        from swervetune import design as D
        design = D.from_code(PEA)
        design["sensors"] = [{"name": "Tower beam", "subsystem": "Tower"}]
        g = {x["name"]: x for x in SY.groups(PEA, design, [])}
        self.assertEqual(sorted(g), ["Drive train", "Feeder", "Intake", "Shooter"])
        self.assertEqual(sorted(g["Feeder"]["aka"]), ["Spindexter", "Tower"])
        self.assertEqual(g["Feeder"]["sensors"], ["Tower beam"], "follows its design subsystem's motors")
        self.assertEqual(g["Drive train"]["aka"], ["Drive"])


class ExamplesTest(unittest.TestCase):
    """The Examples robot: past seasons' mechanisms, each with a complete plan from its settings."""
    UNITS = {"Elevator": "meters", "Shooter pivot": "degrees", "Arm shoulder": "degrees", "Arm elbow": "degrees",
             "Shooter left": "wheel RPM", "Shooter right": "wheel RPM", "Feeder": "RPM"}

    def test_every_mechanism_is_registered_and_has_a_complete_plan(self):
        kinds = SY.in_code(EXA)
        self.assertEqual(sorted(kinds), sorted(self.UNITS))
        cfg = SY.settings(EXA)
        self.assertEqual(sorted(cfg), sorted(self.UNITS))
        for name, entry in cfg.items():
            reg = {"name": name, "kind": kinds[name], "units": self.UNITS[name], "min": entry.get("min"), "max": entry.get("max")}
            plan = SY.plan(entry, reg)
            self.assertTrue(plan["ok"], (name, plan))
        # The physics the links give match the gains in the code: the elevator's kG, the pivot's kCos.
        lift = SY.plan(cfg["Elevator"], {"kind": "ELEVATOR", "units": "meters", "min": 0, "max": 1.18})
        self.assertAlmostEqual(lift["feedforward"]["kG"], 0.40, delta=0.01)
        pivot = SY.plan(cfg["Shooter pivot"], {"kind": "PIVOT", "units": "degrees", "min": 3.6, "max": 111.6})
        self.assertAlmostEqual(pivot["feedforward"]["kG"], 0.42, delta=0.01)

    def test_the_climber_is_a_subsystem_with_nothing_to_tune(self):
        g = {x["name"]: x for x in SY.groups(EXA, None, [{"name": n, "motors": [n]} for n in self.UNITS])}
        self.assertEqual(g["Climber"]["motors"], ["Climber", "Climber follower"])
        self.assertEqual(g["Climber"]["systems"], [])
        self.assertEqual(sorted(g["Shooter"]["systems"]), ["Shooter left", "Shooter right"])
        self.assertEqual(sorted(g["TwoJointArm"]["systems"]), ["Arm elbow", "Arm shoulder"])


class InCodeTest(unittest.TestCase):
    def test_what_peashooters_code_registers(self):
        self.assertEqual(SY.in_code(PEA), {"Intake pivot": "PIVOT", "Shooter": "FLYWHEEL"})

    def test_a_system_runs_summary_names_its_mechanism(self):
        import json
        import tempfile
        from swervetune import runs
        doc = {"test": "system_step", "module": "ALL", "env": "BLOCKS", "outcome": "DONE", "saved": "20261014-120000",
               "message": "Finished.", "notes": ["motor 0: Shooter leader", "system: Shooter (FLYWHEEL, RPM)"],
               "meta": {"vmax": 1975.0}}
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "run.json")
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            s = runs._summary(f)
        self.assertEqual((s["system"], s["vmax"], s["message"]), ("Shooter", 1975.0, "Finished."))


class PlanTest(unittest.TestCase):
    def test_a_pivot_needs_physics_and_limits_first(self):
        p = SY.plan({}, dict(PIVOT, min=float("nan"), max=float("nan")))
        self.assertFalse(p["ok"])
        self.assertEqual(len(p["missing"]), 2)
        ok = SY.plan({"link": ARM}, PIVOT)
        self.assertTrue(ok["ok"], ok)
        self.assertAlmostEqual(ok["scale"], 50 / (2 * math.pi), msg="motor rotations through the 50:1")
        self.assertTrue(PIVOT["min"] < ok["a"] < ok["b"] < PIVOT["max"])

    def test_the_teams_maximum_caps_it(self):
        p = SY.plan({"link": ARM, "maxVelocity": 0.5}, PIVOT)
        self.assertEqual(p["vmax"], 0.5)

    def test_typed_in_physics_from_the_amb_spreadsheet(self):
        typed = {"physics": {"kind": "pivot", "motor": "NEO Vortex", "count": 1, "ratio": 60, "arm_length_m": 0.4, "load_kg": 3}}
        self.assertTrue(SY.plan(typed, PIVOT)["ok"])

    def test_an_ambcalc_link_for_an_elevator(self):
        lift = {"name": "Elevator", "kind": "ELEVATOR", "units": "meters", "motors": ["Elevator"], "min": 0.0, "max": 1.2}
        amb = "https://ambcalc.com/mechanism?=Elevator&motor=Kraken+X60&mot_num=2&radius=0.75&load=15&rat-c=%5E&rat=9"
        p = SY.plan({"link": amb}, lift)
        self.assertTrue(p["ok"], p)
        self.assertEqual(p["scale"], 1.0, "meters are the elevator's own units")
        self.assertTrue(0.0 < p["a"] < p["b"] < 1.2)
        self.assertIn("register", SY.plan({"link": amb}, dict(lift, kind=""))["missing"][0])

    def test_units_it_cant_read_ask_for_the_scale(self):
        p = SY.plan({"link": ARM}, dict(PIVOT, units="ticks"))
        self.assertIn("how many ticks are one radian of it", p["missing"][0])
        self.assertTrue(SY.plan({"link": ARM, "unitsPerRadian": 4096 / (2 * math.pi)}, dict(PIVOT, units="ticks"))["ok"])


def flywheel_run(final_fraction=0.92, volts=4.0, env="BLOCKS"):
    """A Shooter step run: goals 2000 then 4000 RPM then 0; it settles at final_fraction of each."""
    t, vel, sp, goal, v0 = [], [], [], [], []
    for leg, g in enumerate((2000, 4000, 0)):
        for k in range(150):
            t.append(len(t) * 0.01)
            goal.append(g)
            sp.append(g)
            vel.append(g * final_fraction)
            v0.append(volts if g else 0.0)
    return {"test": "system_step", "env": env, "outcome": "DONE", "notes": ["system: Shooter (FLYWHEEL, RPM)"],
            "meta": {}, "channels": {"t": t, "vel": vel, "pos": [float("nan")] * len(t), "sp": sp, "goal": goal, "volts0": v0}}


class StepReportTest(unittest.TestCase):
    def test_a_flywheel_short_of_its_goal_gets_kv_from_the_physics(self):
        rep = advisor.analyze(flywheel_run(), systems={"Shooter": {"link": FLY}})
        self.assertEqual(rep["test"], "system_step")
        titles = [f["title"] for f in rep["findings"]]
        self.assertTrue(any("settles 8.0% short of its goals" in x for x in titles), titles)
        kv = rep["actions"][0]["values"]["Shooter/kV"]
        # Two NEO Vortexes direct: about 12 V at 6825 RPM free, so about 0.0018 V per RPM.
        self.assertAlmostEqual(kv, 12 / 6825, delta=0.0002)

    def test_on_target_says_so(self):
        rep = advisor.analyze(flywheel_run(final_fraction=1.0), systems={"Shooter": {"link": FLY}})
        self.assertEqual([f for f in rep["findings"] if f["level"] == "warn"], [])
        self.assertEqual(rep["score"], 100)

    def test_the_simulator_never_scores(self):
        rep = advisor.analyze(flywheel_run(env="SIM"))
        self.assertIsNone(rep["score"])
        self.assertIn("practice only", rep["summary"], "a modeled mechanism moved: worth reading")
        still = flywheel_run(env="SIM")
        still["channels"]["vel"] = [0.0] * len(still["channels"]["t"])
        rep = advisor.analyze(still)
        self.assertIn("aren't modeled", rep["summary"])
        self.assertEqual(rep["findings"], [])

    def test_wheel_rpm_is_the_wheels_own(self):
        belt = {"kind": "flywheel", "motor": "NEO Vortex", "count": 1, "ratio": 0.5}
        self.assertAlmostEqual(SY.scale({}, "wheel RPM", belt), 60 / (2 * math.pi))
        self.assertAlmostEqual(SY.scale({}, "RPM", belt), 0.5 * 60 / (2 * math.pi), msg="a motor's RPM, through the belt")

    def test_an_elevator_in_motor_rotations_scales_per_meter(self):
        mech = {"kind": "elevator", "motor": "NEO Vortex", "count": 1, "ratio": 5.0, "spool_diameter_m": 0.04}
        self.assertAlmostEqual(SY.scale({}, "motor rotations", mech), 5.0 / (math.pi * 0.04))
        self.assertAlmostEqual(SY.scale({}, "inches", mech), 39.37, places=2)
        self.assertEqual(SY.scale({}, "meters", mech), 1.0)


class LimitsReportTest(unittest.TestCase):
    def test_moved_and_not_moved(self):
        doc = {"test": "system_limits", "notes": ["system: Intake pivot (PIVOT, motor rotations)"],
               "meta": {"min": 0.1, "max": 17.7}, "channels": {"t": [0, 1, 2, 3, 4, 5]}}
        self.assertEqual(advisor.analyze(doc)["limits"]["max"], 17.7)
        still = dict(doc, meta={"min": 3.0, "max": 3.0})
        self.assertEqual(advisor.analyze(still)["findings"][0]["level"], "error")


if __name__ == "__main__":
    unittest.main()
