"""Model-based tuning (modeltune.py): the fit recovers a known mechanism, the gains match their
textbook forms, MAXMotion stays inside the voltage and the current, and the units a SPARK takes."""

import math
import random
import unittest

from slothtune import modeltune as M


def sim_id(plant, kind, dt=0.005, ramp=0.5, ramp_to=3.0, step=5.0, step_s=0.6, arpu=None, noise=0.0):
    """A quasistatic ramp then a dynamic step, each way, on a known plant: t, pos, volts."""
    rnd = random.Random(1)
    t, pos, volts = [], [], []
    x, v, tt = 0.0, 0.0, 0.0
    g0 = plant.get("kG", 0.0) if kind == "ELEVATOR" else 0.0

    def run(u_of_t, dur):
        nonlocal x, v, tt
        k = 0
        while k * dt < dur:
            u = u_of_t(k * dt)
            g = plant["kG"] * (math.cos(x * arpu) if kind == "PIVOT" else 1.0) if kind in ("ELEVATOR", "PIVOT") else 0.0
            fr = plant["kS"] * (1 if v > 1e-6 else -1 if v < -1e-6 else 0)
            a = (u - fr - plant["kV"] * v - g) / plant["kA"]
            if abs(v) < 1e-6 and abs(u - g) <= plant["kS"]:
                a = 0.0
            v += a * dt
            x += v * dt
            t.append(tt)
            pos.append(x + rnd.gauss(0, noise))
            volts.append(u)
            tt += dt
            k += 1
    for sgn in (1, -1):
        run(lambda s, sgn=sgn: g0 + sgn * min(ramp_to, ramp * s), ramp_to / ramp)
        run(lambda s: g0, 0.5)
    for sgn in (1, -1):
        run(lambda s, sgn=sgn: g0 + sgn * step, step_s)
        run(lambda s: g0, 0.5)
    return t, pos, volts


ELEVATOR = {"kS": 0.15, "kV": 9.0, "kA": 0.35, "kG": 0.45}
FLYWHEEL = {"kS": 0.2, "kV": 0.021, "kA": 0.004, "kG": 0.0}
ARM = {"kS": 0.1, "kV": 1.2, "kA": 0.08, "kG": 0.6}


class FitTest(unittest.TestCase):
    def fitted(self, plant, kind, **kw):
        t, pos, volts = sim_id(plant, kind, **kw)
        return M.fit(t, pos, M.velocity_from_position(t, pos), volts, kind, angle_rad_per_unit=kw.get("arpu"))

    def test_an_elevator(self):
        f = self.fitted(ELEVATOR, "ELEVATOR")
        self.assertTrue(f["ok"], f)
        self.assertAlmostEqual(f["kV"], 9.0, delta=0.5)
        self.assertAlmostEqual(f["kA"], 0.35, delta=0.05)
        self.assertAlmostEqual(f["kG"], 0.45, delta=0.03)
        self.assertGreater(f["r2"], 0.99)

    def test_a_flywheel(self):
        f = self.fitted(FLYWHEEL, "FLYWHEEL", ramp_to=6.0)
        self.assertTrue(f["ok"], f)
        self.assertAlmostEqual(f["kV"], 0.021, delta=0.001)
        self.assertAlmostEqual(f["kA"], 0.004, delta=0.0005)
        self.assertEqual(f["kG"], 0.0)

    def test_an_arm_and_where_its_gravity_pulls(self):
        f = self.fitted(ARM, "PIVOT", arpu=1.0, step=3.0, step_s=0.25)
        self.assertTrue(f["ok"], f)
        self.assertAlmostEqual(f["kG"], 0.6, delta=0.05)
        self.assertAlmostEqual(f["offset_rad"], 0.0, delta=0.05, msg="horizontal is zero here")

    def test_it_never_moved(self):
        f = M.fit([i * 0.01 for i in range(100)], [0.0] * 100, [0.0] * 100, [1.0] * 100)
        self.assertFalse(f["ok"])

    def test_a_reversed_motor_is_not_physical(self):
        t, pos, volts = sim_id(ELEVATOR, "ELEVATOR")
        f = M.fit(t, pos, M.velocity_from_position(t, pos), [-u for u in volts], "ELEVATOR")
        self.assertFalse(f["ok"])


class DelayTest(unittest.TestCase):
    def test_a_filtered_speed_reading_is_found_late(self):
        dt = 0.005
        t = [i * dt for i in range(800)]
        pos = [math.sin(2 * math.pi * 0.7 * x) for x in t]
        true_v = M.velocity_from_position(t, pos)
        lag = 6
        ctrl = [true_v[max(0, i - lag)] for i in range(len(t))]
        self.assertAlmostEqual(M.delay(t, pos, ctrl), lag * dt, delta=dt)


class GainsTest(unittest.TestCase):
    def test_the_regulator_matches_the_continuous_textbook_form(self):
        # x'' = u / m (no friction, kV ~ 0): continuous LQR gives Kp = sqrt(q1/rho) exactly.
        m, qp, qv, r = 0.5, 0.01, 0.5, 7.0
        kp, kd = M.lqr_pd(1e-9, m, qp, qv, r=r, dt=0.0005)
        q1, q2, rho = 1 / qp ** 2, 1 / qv ** 2, 1 / r ** 2
        self.assertAlmostEqual(kp, math.sqrt(q1 / rho), delta=0.02 * math.sqrt(q1 / rho))
        kd_true = math.sqrt((q2 + 2 * m * math.sqrt(q1 * rho)) / rho)
        self.assertAlmostEqual(kd, kd_true, delta=0.05 * kd_true)

    def test_a_delay_softens_the_regulator(self):
        kp0, kd0 = M.lqr_pd(9.0, 0.35, 0.012, 0.2)
        kp1, kd1 = M.lqr_pd(9.0, 0.35, 0.012, 0.2, delay_s=0.01)
        self.assertLess(kp1, kp0)
        self.assertGreater(kp1, 0)

    def test_simc(self):
        kp, ki = M.simc_pi(0.021, 0.004, 0.02)
        self.assertAlmostEqual(kp, 0.004 / 0.04)
        self.assertAlmostEqual(ki, kp / min(0.004 / 0.021, 4 * 0.04))

    def test_position_gains_ignore_the_speed_filter(self):
        a = M.compute(dict(ELEVATOR, r2=1), "ELEVATOR", 11.0, 0.0, 0.6)
        b = M.compute(dict(ELEVATOR, r2=1), "ELEVATOR", 11.0, 0.1, 0.6)
        self.assertEqual(a["gains"]["kP"], b["gains"]["kP"])

    def test_the_prediction_settles_with_the_computed_gains(self):
        for plant, kind, move in ((ELEVATOR, "ELEVATOR", 0.6), (FLYWHEEL, "FLYWHEEL", 300.0)):
            c = M.compute(dict(plant), kind, 11.0, 0.02, move, current_limit_a=40)
            p = c["predicted"]
            self.assertLess(p["overshoot_pct"], 10, (kind, p))
            self.assertLess(abs(p["error_pct"]), 2, (kind, p))
            self.assertIsNotNone(p["settle_s"], (kind, p))


class MaxMotionTest(unittest.TestCase):
    def test_inside_the_voltage_and_the_current(self):
        mm = M.maxmotion(ELEVATOR, 11.0, current_limit_a=40, motor="NEO")
        self.assertLess(ELEVATOR["kS"] + ELEVATOR["kG"] + ELEVATOR["kV"] * mm["cruise"], 0.8 * 11.0)
        self.assertAlmostEqual(mm["cruise"], 0.8 * (0.8 * 11.0 - 0.15 - 0.45) / 9.0, places=6)
        a_i = (40 * 12 / 105 - 0.15 - 0.45) / 0.35
        self.assertLessEqual(mm["accel"], 0.8 * a_i + 1e-9, "never more than the current limit allows")

    def test_a_short_move_caps_the_cruise(self):
        long = M.maxmotion(ELEVATOR, 11.0, move=2.0)
        short = M.maxmotion(ELEVATOR, 11.0, move=0.01)
        self.assertLess(short["cruise"], long["cruise"])

    def test_less_battery_less_speed(self):
        self.assertLess(M.maxmotion(ELEVATOR, 10.0)["cruise"], M.maxmotion(ELEVATOR, 12.0)["cruise"])


class SparkUnitsTest(unittest.TestCase):
    def test_reves_units(self):
        g = {"kP": 200.0, "kD": 5.0, "kI": 0.0, "kS": 0.1, "kV": 0.12, "kA": 0.01, "kG": 0.3}
        s = M.spark_gains(g, {"cruise": 2.0, "accel": 8.0}, 12.0, ratio_p=1.0, ratio_v=60.0)
        self.assertAlmostEqual(s["kP"], 200 / 12)
        self.assertAlmostEqual(s["kD"], 5 / (12 * 0.001))
        self.assertAlmostEqual(s["kV"], 0.12 / 60, msg="volts per rpm when the SPARK reads rpm")
        self.assertEqual((s["kS"], s["kG"]), (0.1, 0.3), "volts stay volts")
        self.assertAlmostEqual(s["mmCruise"], 120.0)

    def test_compensation_from_the_measured_battery(self):
        self.assertEqual(M.compensation_volts(11.62), 11.0)
        self.assertEqual(M.compensation_volts(12.9), 12.0)
        self.assertEqual(M.compensation_volts(8.0), 9.0)
        self.assertEqual(M.compensation_volts(None), 11.0)


if __name__ == "__main__":
    unittest.main()
