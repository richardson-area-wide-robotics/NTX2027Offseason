"""Model-based tuning end to end (decision 75): a measuring run's report (systems.id_report) and
the gains for the mode the code runs its SPARK in (systems.model_gains), the speed filter's delay
and suggestion (decision 78), and the tuner (autotune.ModelTune) on practice SPARKs."""

import math
import unittest

from slothtune import autotune as A, modeltune as M, systems
from slothtune.tests.test_modeltune import ARM, ELEVATOR, sim_held


def practice(kind="ELEVATOR", control=None, gains=None):
    return A.PracticeSystemRunner("Lift" if kind == "ELEVATOR" else "Shooter", kind, gains=gains or {"kP": 2.0},
                                  spark=True, control=control)


def report(runner, control=None, ranges=None):
    reg = runner.registered()
    if control is not None:
        reg["control"] = control
    if ranges:
        for k, (lo, hi) in ranges.items():
            reg["gains"][k].update(min=lo, max=hi)
    return systems.id_report(runner._identify(), None, reg,
                             {"motor": "NEO V1.1", "limit_a": 40, "count": 1, "controller": "SPARK MAX"})


def tune(runner, **kw):
    t = A.ModelTune(runner, runner.name, **kw)
    t.start()
    return t, A.wait(t, 120)


class DelayTest(unittest.TestCase):
    def test_a_filter_shorter_than_a_row_is_still_found(self):
        # A 20 ms moving average (10 ms late), read once a 20 ms robot loop.
        dt, h = 0.02, 0.001
        x, xs, raw, t, pos, ctl = 0.0, [], [], [], [], []
        for k in range(int(6 / h)):
            v = math.sin(2 * math.pi * 0.8 * k * h)
            x += v * h
            raw.append(v)
            if k % int(dt / h) == 0:
                t.append(k * h)
                pos.append(x)
                ctl.append(60 * sum(raw[-20:]) / len(raw[-20:]))
        self.assertAlmostEqual(M.delay(t, pos, ctl), 0.010, delta=0.003)


class FitInSparkUnitsTest(unittest.TestCase):
    def test_an_arms_angle_apart_from_its_position_fits_the_same(self):
        t, pos, volts = sim_held(ARM, "PIVOT", arpu=1.0)
        a = M.fit_held(t, pos, volts, "PIVOT", angle_rad_per_unit=1.0)
        # The SPARK reads it in tenths of a radian; its angle still comes in radians.
        b = M.fit_held(t, [p * 10 for p in pos], volts, "PIVOT", angle=pos)
        self.assertAlmostEqual(b["kG"], a["kG"], places=6)
        self.assertAlmostEqual(b["kV"] * 10, a["kV"], places=6)

    def test_its_speed_units_against_its_position(self):
        t, pos, volts = sim_held(ELEVATOR, "ELEVATOR")
        rpm = [60 * v for v in M.velocity_from_position(t, pos)]
        self.assertAlmostEqual(M.speed_ratio(t, pos, rpm), 60.0, delta=0.01)


class FilterTest(unittest.TestCase):
    def test_the_filters_rules(self):
        # Chief Delphi's PSA (2026): quadrature windows overlap, a NEO's hall windows don't.
        self.assertAlmostEqual(M.filter_delay_s("SPARK Flex", 100, 64), 0.082)
        self.assertAlmostEqual(M.filter_delay_s("SPARK MAX", 32, 8), 0.128)
        self.assertAlmostEqual(M.filter_delay_s("SPARK Flex", 10, 2), 0.006)
        self.assertIsNone(M.filter_delay_s("SPARK MAX", None, 8))

    def test_a_long_delay_on_a_speed_loop_gets_a_setting_to_try(self):
        f = M.filter_suggestion(0.11, "SPARK MAX", 32, 8)
        self.assertEqual(f["suggest"], {"ms": 16, "depth": 1, "expected_ms": 8.0})
        self.assertEqual(f["expected_ms"], 128.0, "what its settings make it, beside what was measured")
        self.assertIn("measure again", f["why"])
        self.assertEqual(M.filter_suggestion(0.08, "SPARK Flex", 100, 64)["suggest"], {"ms": 10, "depth": 2, "expected_ms": 6.0})

    def test_short_enough_or_a_position_loop_gets_none(self):
        self.assertIsNone(M.filter_suggestion(0.012, "SPARK Flex", 10, 8)["suggest"])
        self.assertIsNone(M.filter_suggestion(0.11, "SPARK MAX", 32, 8, speed_loop=False)["suggest"])

    def test_already_short_says_the_delay_is_elsewhere(self):
        f = M.filter_suggestion(0.08, "SPARK Flex", 10, 2)
        self.assertIsNone(f["suggest"])
        self.assertIn("elsewhere", f["why"])


class IdReportTest(unittest.TestCase):
    def test_the_model_its_delay_and_units(self):
        r = practice()
        rep = report(r)
        P = r.p
        self.assertAlmostEqual(rep["model"]["kV"], P["kV"], delta=0.1 * P["kV"])
        self.assertAlmostEqual(rep["model"]["kG"], P["kG"], delta=0.03)
        self.assertAlmostEqual(rep["model"]["kA"], P["kA"], delta=0.1 * P["kA"])
        self.assertAlmostEqual(rep["delay_s"], r.FILTER_S / 2, delta=0.004, msg="a 20 ms average is 10 ms late")
        self.assertAlmostEqual(rep["ratio_v"], r.SPEED_UNITS, delta=0.5)
        self.assertLess(rep["volts_comp"], 12.4, "compensation below the battery it held")

    def test_plain_position_gets_no_speed_feedforward(self):
        apply = report(practice(), "Position")["computed"]["apply"]
        self.assertEqual({k.split("/")[1] for k in apply}, {"kP", "kD", "kG", "kI", "kS", "kCos", "vComp"})
        self.assertEqual(apply["Lift/kS"], 0.0, "decision 79: no error-signed kS at the target")
        self.assertEqual(apply["Lift/kI"], 0.0, "an old kI would wind up under the LQR's kP and kD")
        self.assertEqual(apply["Lift/kCos"], 0.0, "an elevator's gravity once: kG, never kCos on top")

    def test_maxmotion_gets_its_feedforward_and_profile(self):
        apply = report(practice(), "MAXMotionPosition")["computed"]["apply"]
        self.assertTrue({"kS", "kV", "kA", "kG", "mmCruise", "mmAccel"} <= {k.split("/")[1] for k in apply})

    def test_a_speed_loop_gets_pi_and_kv_in_its_speed_units(self):
        rep = report(practice("FLYWHEEL"), "Velocity")
        apply = {k.split("/")[1]: v for k, v in rep["computed"]["apply"].items()}
        self.assertEqual(set(apply), {"kP", "kI", "kS", "kV", "vComp", "kD", "iZone"})
        self.assertEqual(apply["kD"], 0.0, "no kD in a speed loop")
        self.assertGreater(apply["iZone"], 0, "the integral can't wind up over a spin-up")
        self.assertAlmostEqual(apply["kV"] * 60, rep["model"]["kV"], delta=0.01 * rep["model"]["kV"],
                               msg="volts per RPM-like unit, not per position unit a second")

    def test_open_loop_code_gets_nothing_applied(self):
        rep = report(practice(), "DutyCycle")
        self.assertEqual(rep["computed"]["apply"], {}, "not even compensation: it would change the code's duty cycle")
        self.assertIn("open loop", rep["computed"]["note_title"])
        self.assertIsNone(rep["next"])

    def test_a_gain_past_the_robots_range_is_held_and_said(self):
        rep = report(practice(), "Position", ranges={"kP": (0, 10)})
        self.assertEqual(rep["computed"]["apply"]["Lift/kP"], 10)
        self.assertIn("kP", rep["computed"]["clamped"])
        self.assertTrue(any("allowed range" in f["title"] for f in rep["findings"]))

    def test_one_gains_action_with_every_gain(self):
        rep = report(practice(), "Position")
        self.assertEqual(rep["next"]["action"]["type"], "gains")
        self.assertTrue(rep["next"]["action"]["model"])
        self.assertEqual(rep["next"]["action"]["values"], rep["computed"]["apply"])

    def test_a_speed_loop_survives_a_jump_to_its_speed(self):
        # Match code sets a shooter's speed at once: the gains are judged on that too.
        rep = report(practice("FLYWHEEL"), "Velocity")
        b = rep["basis"]
        c = M.compute(dict(b["model"]), b["kind"], b["volts"], b["delay_s"], b["move"], control="Velocity")
        jump = M.predict(dict(b["model"]), c["gains"], b["kind"], b["move"], c["maxmotion"]["cruise"],
                         c["maxmotion"]["accel"], volts=b["volts"], delay_s=max(b["delay_s"], M.SPEED_DELAY_MIN_S),
                         ff=M.MODE_FF["Velocity"], sp_period=M.MODE_SP_PERIOD["Velocity"], step=True)
        self.assertLessEqual(jump["overshoot_pct"], M.STEP_OVERSHOOT + 0.5, jump)

    def test_units_it_cant_vouch_for_apply_nothing(self):
        r = practice()
        doc = r._identify()
        doc["channels"]["spos"] = [float("nan")] * len(doc["channels"]["t"])
        rep = systems.id_report(doc, None, dict(r.registered(), control="Position"), {"controller": "SPARK MAX"})
        self.assertEqual(rep["computed"]["apply"], {})
        self.assertIn("Nothing applied", rep["computed"]["note_title"])
        sens = report(practice(), "Position")
        b = dict(sens["basis"], refuse="its loop reads an analog sensor", refuse_title="its loop reads an AnalogSensor")
        self.assertEqual(systems.model_gains(b)["apply"], {})

    def test_kcos_only_when_rev_sees_the_real_angle(self):
        rep = report(practice(), "Position")
        b = dict(rep["basis"], kind="PIVOT", angle_rad_per_unit=1.0)
        b["model"] = dict(b["model"], offset_rad=0.0)
        withheld = systems.model_gains(dict(b, kcos=None))
        self.assertNotIn("Lift/kCos", withheld["apply"])
        self.assertNotIn("Lift/kG", withheld["apply"], "the code's own gravity is left alone too")
        self.assertIn("kCos not applied", withheld["note_title"])
        ok = systems.model_gains(dict(b, kcos={"ok": True}))
        self.assertGreater(ok["apply"]["Lift/kCos"], 0)
        self.assertEqual(ok["apply"]["Lift/kG"], 0.0, "gravity once, not kG on top of kCos")

    def test_the_kcos_check(self):
        # The code reads degrees, level at 20; the SPARK reads arm rotations from level: they agree.
        deg = math.pi / 180
        pos = [20 + k for k in range(60)]
        spos = [(p - 20) / 360 for p in pos]
        good = systems.kcos_check(pos, spos, deg, 20 * deg, 1.0, 360.0)
        self.assertTrue(good["ok"], good)
        self.assertAlmostEqual(good["ratio"], 1.0, places=6)
        self.assertAlmostEqual(good["level"], 0.0, places=6)
        # Its SPARK reads motor rotations through a 50:1 gearbox, kCosRatio left at 1: far off, and what to set.
        motor = [50 * s for s in spos]
        bad = systems.kcos_check(pos, motor, deg, 20 * deg, 1.0, 360.0 / 50)
        self.assertFalse(bad["ok"])
        self.assertAlmostEqual(bad["ratio"], 1 / 50, places=6)
        self.assertFalse(systems.kcos_check(pos, spos, deg, 20 * deg, None, 360.0)["ok"], "unknown ratio: not applied")

    def test_a_coarse_sensor_holds_kd_to_a_small_kick_a_count(self):
        # A NEO's hall sensor on an elevator: half a millimeter a count. The model's kD would pulse the
        # motor at full output for a millisecond at every count; it is held to a quarter.
        r = practice()
        doc = r._identify()
        c = 0.0005
        doc["channels"]["spos"] = [round(x / c) * c if x == x else x for x in doc["channels"]["spos"]]
        rep = systems.id_report(doc, None, dict(r.registered(), control="Position"),
                                {"motor": "NEO V1.1", "limit_a": 40, "count": 1, "controller": "SPARK MAX"})
        self.assertAlmostEqual(rep["basis"]["count"], c, delta=1e-9, msg="one count, measured from the run")
        self.assertTrue(rep["computed"]["kd_capped"])
        self.assertLessEqual(rep["computed"]["apply"]["Lift/kD"] * c, M.COUNT_KICK * 1.000001)
        self.assertTrue(any("kD held" in f["title"] for f in rep["findings"]))
        self.assertFalse(report(practice(), "Position")["computed"]["kd_capped"], "a fine sensor keeps the model's kD")

    def test_a_buzz_is_heard_in_the_applied_volts(self):
        r = practice()
        doc = r.run("system_step")[0]
        clean = systems.step_report(doc, None, r.gains())
        self.assertFalse(any("buzzes" in f["title"] for f in clean["findings"]), "a smooth hold isn't a buzz")
        v = doc["channels"]["volts0"]
        doc["channels"]["volts0"] = [x + (3.0 if k % 3 == 0 else 0.0) for k, x in enumerate(v)]
        rep = systems.step_report(doc, None, r.gains())
        self.assertTrue(any("buzzes" in f["title"] for f in rep["findings"]), rep["findings"])
        self.assertGreater(max(m["buzz_v"] for m in rep["moves"]), systems.BUZZ_V)

    def test_maxmotion_current_limit_is_each_motors(self):
        m = {"kS": 0.1, "kV": 2.0, "kA": 0.3, "kG": 0.5}
        one = M.maxmotion(m, 12.0, 40, "NEO", 1)
        two = M.maxmotion(m, 12.0, 40, "NEO", 2)
        self.assertAlmostEqual(one["accel"], two["accel"], msg="the limit is per motor: the volts it allows don't halve")

    def test_the_prediction_follows_the_mode(self):
        rep = report(practice(), "Position")
        soft = systems.model_gains(rep["basis"], 0.5)
        hard = systems.model_gains(rep["basis"], 2.0)
        self.assertLess(soft["apply"]["Lift/kP"], hard["apply"]["Lift/kP"])


class ModelTuneTest(unittest.TestCase):
    def test_each_mode_tunes_from_one_measuring_run(self):
        for kind, control in (("ELEVATOR", "Position"), ("ELEVATOR", "MAXMotionPosition"), ("FLYWHEEL", "Velocity")):
            r = practice(kind, control, {"kP": 2.0} if kind == "ELEVATOR" else {"kP": 0.0001})
            start = r.report(dict(r.run("system_step")[0], gains=r.gains()))["cost"]
            t, j = tune(r)
            self.assertEqual((j["state"], j["status"]), ("finished", "done"), (kind, control, j["reason"]))
            self.assertLess(j["best"]["cost"], 0.5 * start, (kind, control))
            self.assertEqual(j["best_gains"], {k: v for k, v in r.gains().items() if k in j["best_gains"]},
                             "it ends on its best check's gains")
            self.assertEqual(r.runs, 1 + 1 + 1 + len(j["checks"]),
                             "this test's own run, one measuring run, the baseline, the checks")
            self.assertLess(j["best"]["cost"], j["baseline"]["cost"], "the model's beat the gains it had")

    def test_a_check_unlike_the_model_puts_the_start_back(self):
        # Its speed filter is made ten times longer after it was measured (someone changed the config):
        # the speed loop the model worked out rings, softer too, and nothing it may try is acceptable.
        r = practice("FLYWHEEL", "Velocity", {"kP": 0.0001})
        before = r.gains()
        orig = r.run

        def run(test):
            if test == "system_step":
                r.FILTER_S = 0.2
            return orig(test)
        r.run = run
        t, j = tune(r)
        # Either the gains it had beat every ringing check, or nothing it tried was acceptable: both
        # put back what it started on.
        self.assertTrue("already as good" in j["reason"] or "doesn't match" in j["reason"], j["reason"])
        self.assertIsNone(j["best"])
        self.assertEqual({k: v for k, v in r.gains().items() if k in before}, before, "back on what it started with")

    def test_the_gains_it_had_are_kept_when_the_model_cant_beat_them(self):
        # Start on the gains the model would give: its checks can't beat them by much, and a tie keeps them.
        r = practice()
        rep = r.id_report(r._identify())
        r.apply(rep["computed"]["apply"], "already tuned")
        before = r.gains()
        t, j = tune(r)
        if j["best"] is None:
            self.assertIn("already as good", j["reason"])
            self.assertEqual(r.gains(), before)

    def test_a_refused_apply_stops_it_and_puts_the_start_back(self):
        r = practice()
        before = r.gains()
        orig = r.apply

        def apply(values, reason):
            if "model's gains" in reason:
                return "Refused: a test is running it by voltage."
            return orig(values, reason)
        r.apply = apply
        t, j = tune(r)
        self.assertEqual(j["status"], "stopped")
        self.assertIn("didn't take the gains", j["reason"])
        self.assertEqual(j["checks"], [], "no check judged on gains it never had")
        self.assertEqual(r.gains(), before)

    def test_an_error_mid_check_puts_the_start_back(self):
        r = practice()
        before = r.gains()
        orig = r.report

        def report_(doc):
            if any(k.endswith("/kD") and v != before.get(k) for k, v in (doc.get("gains") or {}).items()):
                raise RuntimeError("the link dropped")
            return orig(doc)
        r.report = report_
        t, j = tune(r)
        self.assertEqual(j["state"], "stopped")
        self.assertIn("the link dropped", t.message)
        self.assertEqual(r.gains(), before, "never left on a check's untested gains")

    def test_no_kd_in_the_simulator(self):
        r = practice()
        doc = dict(r._identify(), env="SIM")
        doc["channels"]["loop"] = list(range(len(doc["channels"]["t"])))
        rep = systems.id_report(doc, None, r.registered(), {"controller": "SPARK MAX"})
        self.assertEqual(rep["computed"]["apply"].get("Lift/kD", 0.0), 0.0)
        self.assertGreater(rep["computed"]["apply"]["Lift/kP"], 0)
        self.assertTrue(any("No kD" in f["title"] for f in rep["findings"]))

    def test_the_report_reaches_the_page(self):
        t, j = tune(practice())
        self.assertEqual(j["mode"], "model")
        self.assertIsNotNone(j["baseline"]["cost"])
        self.assertIn("kG", j["model"]["summary"])
        self.assertTrue(j["checks"][0]["predicted"])
        self.assertIsNotNone(j["checks"][0]["measured"]["overshoot_pct"])


if __name__ == "__main__":
    unittest.main()
