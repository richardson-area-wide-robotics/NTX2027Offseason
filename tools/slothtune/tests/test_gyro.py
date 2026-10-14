"""The gyro: drift standing still, scale over full turns, direction, and how level it's mounted."""

import unittest

from slothtune import geometry as G, plant


def still(**kw):
    return G.gyro_still({"channels": plant.gyro_capture("still", **kw)})


def turns(said=5, **kw):
    return G.gyro_turns({"channels": plant.gyro_capture("turns", seconds=40, **kw)}, said)


def titles(r):
    return " | ".join(f["title"] for f in r["findings"])


class GyroTest(unittest.TestCase):
    def test_drift(self):
        self.assertAlmostEqual(still(drift_dpm=0.2)["drift_deg_per_min"], 0.2, delta=0.02)
        self.assertIn("drifts 1.50 degrees a minute", titles(still(drift_dpm=1.5)))

    def test_a_good_gyro(self):
        r = turns(scale=1.001)
        self.assertAlmostEqual(r["scale_error"], 0.001, delta=0.0005)
        self.assertEqual([f["level"] for f in r["findings"]], ["ok"])

    def test_a_gyro_that_reads_short(self):
        r = turns(scale=0.98)
        self.assertAlmostEqual(r["scale_error"], -0.02, delta=0.0005)
        self.assertIn("% short (1764", titles(r))
        self.assertEqual(r["findings"][-1]["level"], "error")

    def test_backwards(self):
        self.assertIn("Counter-clockwise turns read as clockwise", titles(turns(scale=-1.0)))

    def test_the_wrong_count(self):
        self.assertIn("It read 4.00 turns, not 5", titles(turns(said=5, turns=4)))

    def test_a_tilted_mount(self):
        r = still(tilt=(4.0, 3.0))
        self.assertAlmostEqual(r["tilt_deg"], 5.0, delta=0.05)
        self.assertIn("mounted 5.0 degrees off level", titles(r))
        self.assertNotIn("off level", titles(still(tilt=(1.0, -0.5))))


if __name__ == "__main__":
    unittest.main()
