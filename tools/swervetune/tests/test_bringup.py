"""Bring-up's motor test report (bringup.py): read against the design file, what each motor did."""

import unittest

from swervetune import advisor, bringup


def run(motors, env="BLOCKS", outcome="DONE", message="", pdh=None, duty=0.08):
    """A motor_test run: ``motors`` is [(name, role, turns during the pulse, peak amps)]."""
    t = [round(0.02 * i, 2) for i in range(70)]          # 1.4 s: 0.3 quiet, 0.6 pulse, 0.5 after
    ch = {"t": t}
    notes = []
    for i, (name, role, turns, amps) in enumerate(motors):
        notes.append(f"motor {i}: {name} ({ {'run': 'run', 'held': 'held at zero', 'watched': 'watched'}[role] })")
        ch[f"m{i}.rot"] = [0.0 if x < 0.3 else turns * min(1.0, (x - 0.3) / 0.6) for x in t]
        ch[f"m{i}.amps"] = [amps if 0.3 <= x < 0.9 else 0.0 for x in t]
    for p, rise in (pdh or {}).items():
        ch[f"pdh{p}"] = [0.2 + (rise if 0.3 <= x < 0.9 else 0.0) for x in t]
    return {"test": "motor_test", "env": env, "outcome": outcome, "message": message, "notes": notes,
            "meta": {"quiet_s": 0.3, "pulse_s": 0.6, "duty": duty}, "channels": ch}


def motor(name, shaft=None, ratio=1.0, follows=None, port=None, positive=""):
    return {"name": name, "shaft": shaft, "gearRatio": ratio, "follows": follows, "pdh": {"port": port},
            "positive": positive, "motor": {"type": "sparkflex_vortex", "id": 1}}


SHOOTER = {"motors": [motor("Shooter leader", "shooter", positive="the wheels throw a game piece out"),
                      motor("Shooter follower", "shooter", follows={"leader": "Shooter leader", "inverted": True})]}


def titles(rep, level=None):
    return [f["title"] for f in rep["findings"] if level is None or f["level"] == level]


class MotorTestReportTest(unittest.TestCase):
    def test_a_follower_set_opposite_turns_opposite_and_that_is_right(self):
        rep = bringup.motor_test_report(run([("Shooter leader", "run", 3.0, 6), ("Shooter follower", "watched", -3.0, 6)]), SHOOTER)
        self.assertEqual(titles(rep, "error"), [])
        self.assertEqual(rep["score"], 100)
        self.assertEqual(rep["ask"][0]["question"], "Did Shooter leader turn so that the wheels throw a game piece out?")

    def test_a_follower_turning_with_the_leader_would_fight_it(self):
        rep = bringup.motor_test_report(run([("Shooter leader", "run", 3.0, 6), ("Shooter follower", "watched", 3.0, 6)]), SHOOTER)
        self.assertTrue(any("Shooter follower turns against Shooter leader" in t for t in titles(rep, "error")))

    def test_a_geared_partner_turns_by_the_ratio(self):
        d = {"motors": [motor("Roller A", "roller", ratio=1.0), motor("Roller B", "roller", ratio=2.0)]}
        ok = bringup.motor_test_report(run([("Roller A", "run", 2.0, 5), ("Roller B", "held", 4.0, 0)]), d)
        self.assertEqual(titles(ok), [])
        off = bringup.motor_test_report(run([("Roller A", "run", 2.0, 5), ("Roller B", "held", 2.0, 0)]), d)
        self.assertTrue(any("the ratios say 4.00" in t for t in titles(off, "warn")))

    def test_a_partner_that_doesnt_turn_isnt_on_the_shaft(self):
        d = {"motors": [motor("Roller A", "roller"), motor("Roller B", "roller")]}
        rep = bringup.motor_test_report(run([("Roller A", "run", 2.0, 5), ("Roller B", "held", 0.0, 0)]), d)
        self.assertTrue(any("Roller B didn't turn with Roller A" in t for t in titles(rep, "error")))

    def test_a_motor_that_didnt_turn(self):
        rep = bringup.motor_test_report(run([("Intake pivot", "run", 0.0, 0.2)]), {"motors": [motor("Intake pivot")]})
        self.assertTrue(any("Intake pivot didn't turn" in t for t in titles(rep, "error")))
        self.assertEqual(rep["score"], 0)

    def test_the_pdh_port_that_fed_it(self):
        d = {"motors": [motor("Tower", port=4)]}
        rep = bringup.motor_test_report(run([("Tower", "run", 2.0, 5)], pdh={4: 0.0, 5: 4.0}), d)
        self.assertEqual(rep["motors"][0]["pdh_port"], 5)
        self.assertTrue(any("fed from PDH port 5; the design says 4" in t for t in titles(rep, "error")))

    def test_a_fight_cut_short(self):
        rep = bringup.motor_test_report(run([("Roller A", "run", 0.0, 40)], outcome="ABORTED",
                                            message="Roller A drew 40 A without turning: jammed, or motors on one shaft "
                                                    "pushing against each other. Stopped."), None)
        self.assertTrue(any("pulled hard without turning" in t for t in titles(rep, "error")))
        self.assertFalse(any("didn't turn" in t for t in titles(rep)), "the stop says it already")

    def test_the_simulator_only_checks_the_sequence(self):
        rep = bringup.motor_test_report(run([("Tower", "run", 0.0, 0)], env="SIM"), None)
        self.assertIsNone(rep["score"])
        self.assertEqual(titles(rep, "error"), [])

    def test_the_advisor_hands_it_the_design(self):
        rep = advisor.analyze(run([("Shooter leader", "run", 3.0, 6), ("Shooter follower", "watched", 3.0, 6)]), design=SHOOTER)
        self.assertEqual(rep["test"], "motor_test")
        self.assertTrue(any("turns against" in t for t in titles(rep)))


class ReportTest(unittest.TestCase):
    def test_the_report_is_written_from_the_evidence(self):
        import os
        from swervetune import design as D, setup as SP, yagslcfg as Y
        here = os.path.dirname(os.path.abspath(__file__))
        p = Y.Project(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(here))), "Peashooter"))
        d = D.from_code(p)
        c = {"project": p, "robot": p.name, "connected": False, "live_motors": [], "runs": [], "lint": [], "pp": None,
             "inventory": {"rows": [], "findings": []}, "controllers": [], "wiring_saved": False,
             "wiring_map": {"buses": [{"name": "rio", "chain": [], "orderConfirmed": False}], "pdhPorts": {}},
             "design": d, "design_check": D.check(d), "design_compare": [],
             "prog": {"bu_motor:Tower": {"result": "pass", "when": "20261013-143100", "detail": "right way"}}}
        path, text = bringup.report(p, c, {"programming": "A. Student", "mechanical": ""})
        self.assertEqual(os.path.basename(os.path.dirname(path)), "bringup")
        self.assertIn("# Bring-up: Peashooter", text)
        self.assertIn("Signed off by programming: A. Student.", text)
        self.assertIn("| Tower | pass |", text)
        self.assertIn("UTC)", text, "the laptop's time, with UTC beside it")
        self.assertIn("rio (yellow/green)", text)
        self.assertIn("no gear ratio", text, "what still disagrees is in it")
        for j in SP.bringup(c)["jobs"]:
            self.assertIn(f"| {j['title']} | {j['status']} |", text, "every job of the checklist, with its status")


if __name__ == "__main__":
    unittest.main()
