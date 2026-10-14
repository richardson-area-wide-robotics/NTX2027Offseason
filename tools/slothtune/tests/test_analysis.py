"""Analysis against signals whose answer is known in closed form."""

import math
import random
import unittest

from slothtune import analysis as A


def first_order_step(tau, size=90.0, dt=0.005, hold=1.0, delay=0.0):
    t, sp, y = [], [], []
    for k in range(int(0.2 / dt)):
        t.append(k * dt); sp.append(0.0); y.append(0.0)
    t0 = t[-1] + dt
    for k in range(int(hold / dt)):
        tt = k * dt
        t.append(t0 + tt); sp.append(size)
        y.append(0.0 if tt < delay else size * (1 - math.exp(-(tt - delay) / tau)))
    return t, sp, y


class StepMetricsTest(unittest.TestCase):
    def test_first_order_rise_time_is_2_2_tau(self):
        t, sp, y = first_order_step(0.05)
        s = A.analyze_steps(t, sp, y)[0]
        self.assertAlmostEqual(s["rise_time"], 2.197 * 0.05, delta=0.006)
        self.assertEqual(s["overshoot_pct"], 0.0)
        self.assertEqual(s["oscillations"], 0)
        self.assertTrue(s["settled"])

    def test_dead_time_is_measured(self):
        t, sp, y = first_order_step(0.03, delay=0.04)
        s = A.analyze_steps(t, sp, y)[0]
        self.assertAlmostEqual(s["dead_time"], 0.04 + 0.03 * -math.log(0.95), delta=0.007)

    def test_underdamped_overshoot_matches_theory(self):
        zeta, wn, dt = 0.3, 30.0, 0.002
        t, sp, y = [0.0], [0.0], [0.0]
        x, v = 0.0, 0.0
        for k in range(1, 1500):
            r = 0.0 if k < 50 else 45.0
            a = wn * wn * (r - x) - 2 * zeta * wn * v
            v += a * dt
            x += v * dt
            t.append(k * dt); sp.append(r); y.append(x)
        s = A.analyze_steps(t, sp, y)[0]
        expected = 100 * math.exp(-zeta * math.pi / math.sqrt(1 - zeta ** 2))
        self.assertAlmostEqual(s["overshoot_pct"], expected, delta=2.0)
        self.assertGreaterEqual(s["oscillations"], 2)

    def test_sensor_noise_inside_the_band_is_not_ringing(self):
        rnd = random.Random(3)
        t, sp, y = first_order_step(0.05, size=1.0, dt=0.01)
        y = [v + (rnd.random() - 0.5) * 0.06 if tt > 0.2 else v for tt, v in zip(t, y)]
        s = A.analyze_steps(t, sp, y, tol_abs=0.05, window=5)[0]
        self.assertEqual(s["oscillations"], 0)

    def test_saturation_counts_current_limiting(self):
        t, sp, y = first_order_step(0.05)
        volts = [12.0] * len(t)
        amps = [20.0 if v < 80 else 2.0 for v in y]
        s = A.analyze_steps(t, sp, y, [3.0] * len(t), u_max=12, amps=amps, amp_limit=20)[0]
        self.assertGreater(s["saturation"], 0.9)
        s2 = A.analyze_steps(t, sp, y, volts, u_max=12)[0]
        self.assertGreater(s2["saturation"], 0.9)

    def test_never_reaching_target_is_unsettled(self):
        t, sp, y = first_order_step(0.05)
        y = [min(v, 80.0) for v in y]
        s = A.analyze_steps(t, sp, y, tol_abs=1.0)[0]
        self.assertFalse(s["settled"])
        self.assertAlmostEqual(s["steady_state_error"], 10.0, delta=0.5)


class FeedforwardFitTest(unittest.TestCase):
    def simulate(self, kS, kV, kA, noise=0.0, dt=0.01, seed=1):
        rnd = random.Random(seed)
        t, V, v = [], [], []
        x = 0.0
        tt = 0.0
        plan = [("ramp", 1, 6), ("rest", 0, 1), ("ramp", -1, 6), ("rest", 0, 1),
                ("step", 4, 1), ("rest", 0, 1), ("step", -4, 1), ("rest", 0, 1)]
        for kind, a, dur in plan:
            for k in range(int(dur / dt)):
                volts = a * k * dt if kind == "ramp" else a
                accel = 0.0
                if abs(x) > 1e-6 or abs(volts) > kS:
                    s = math.copysign(1, x) if abs(x) > 1e-6 else math.copysign(1, volts)
                    accel = (volts - kS * s - kV * x) / kA
                nx = x + accel * dt
                if x != 0 and nx * x < 0 and abs(volts) <= kS:
                    nx = 0.0
                x = nx
                t.append(tt); V.append(volts); v.append(x + rnd.gauss(0, noise))
                tt += dt
        return t, V, v

    def test_recovers_known_gains(self):
        t, V, v = self.simulate(0.15, 2.8, 0.45)
        f = A.fit_feedforward(t, V, v)
        self.assertTrue(f["ok"], f)
        self.assertAlmostEqual(f["kS"], 0.15, delta=0.03)
        self.assertAlmostEqual(f["kV"], 2.8, delta=0.05)
        self.assertAlmostEqual(f["kA"], 0.45, delta=0.05)

    def test_noise_does_not_collapse_kA(self):
        t, V, v = self.simulate(0.15, 2.8, 0.45, noise=0.01)
        f = A.fit_feedforward(t, V, v)
        self.assertTrue(f["ok"])
        self.assertAlmostEqual(f["kA"], 0.45, delta=0.1)

    def test_backwards_wiring_is_refused_not_fitted(self):
        t, V, v = self.simulate(0.15, 2.8, 0.45)
        f = A.fit_feedforward(t, [-x for x in V], v)
        self.assertFalse(f["ok"])

    def test_no_motion_is_refused(self):
        f = A.fit_feedforward([i * 0.01 for i in range(200)], [1.0] * 200, [0.0] * 200)
        self.assertFalse(f["ok"])


class HandMotionTest(unittest.TestCase):
    def test_verdicts(self):
        self.assertEqual(A.hand_motion([0, 10, 40, 90], 1, 20)["verdict"], "AGREES")
        self.assertEqual(A.hand_motion([0, -10, -40, -90], 1, 20)["verdict"], "INVERTED")
        self.assertEqual(A.hand_motion([0, 1, 2], 1, 20)["verdict"], "NO_MOTION")
        self.assertEqual(A.hand_motion([0, 60, -5, 55, 2], 1, 20)["verdict"], "AMBIGUOUS")

    def test_ratio_finds_a_wrong_gear_ratio(self):
        module = [i * 2.0 for i in range(50)]
        self.assertAlmostEqual(A.ratio(module, module), 1.0)
        self.assertAlmostEqual(A.ratio([m * 1.08 for m in module], module), 1.08)
        self.assertAlmostEqual(A.ratio([-m for m in module], module), -1.0)

    def test_unwrap(self):
        self.assertEqual(A.unwrap_deg([350, 359, 3, 10, 355]), [350, 359, 363, 370, 355])


if __name__ == "__main__":
    unittest.main()
