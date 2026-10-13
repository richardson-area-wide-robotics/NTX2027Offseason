"""The post-match summary on an AdvantageKit-shaped log with known faults planted in it.

Key names and types are the ones a real AdvantageKit log from these robots uses (checked against
a log the simulator wrote).
"""

import os
import tempfile
import unittest

try:
    import wpiutil  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

from swervetune import akit, logsummary as L

MAP = {"buses": [{"name": "roboRIO CAN", "chain": ["roboRIO", "A", "B", "C", "D", "PDH"],
                  "orderConfirmed": True, "segmentLengthsM": {}}],
       "pdhPorts": {"B": 3, "D": 9}}


def us(t):
    return int(t * 1e6)


def write_log(path):
    log = akit.LogWriter(path)

    def Entry(_log, name, kind):  # noqa: N802
        return log.entry(name, kind)

    en = Entry(log, "/DriverStation/Enabled", "boolean")
    au = Entry(log, "/DriverStation/Autonomous", "boolean")
    for t, e, a in ((0.5, False, False), (1.0, True, True), (16.0, True, False), (151.0, False, False)):
        en.append(e, us(t))
        au.append(a, us(t))
    batt = Entry(log, "/SystemStats/BatteryVoltage", "double")
    brown = Entry(log, "/SystemStats/BrownedOut", "boolean")
    off = Entry(log, "/SystemStats/CANBus/OffCount", "int64")
    faults = Entry(log, "/PowerDistribution/Faults", "int64")
    kp = Entry(log, "/RealOutputs/SwerveTune/Gains/Steer/kP", "double")
    kp.append(0.01, us(0.5))
    kp.append(0.02, us(30.0))
    # The reason the robot logs with every change: a string under the gains, which the summary must
    # read as a reason, not a gain (it crashed formatting it as a number).
    why = Entry(log, "/RealOutputs/SwerveTune/Gains/Reason", "string")
    why.append("the values in the files, at startup", us(0.5))
    why.append("Tune tab, advice: Steering overshoots 18%", us(30.0))
    motors = {}
    for m in "ABCD":
        b = f"/RealOutputs/Motors/{m}/"
        motors[m] = {k: Entry(log, b + k, kind) for k, kind in (
            ("Present", "boolean"), ("Dropouts", "int64"), ("Resets", "int64"),
            ("Brownouts", "int64"), ("Stage", "string"), ("Flags", "string"))}
    t = 0.5
    while t < 151:
        batt.append(6.4 if 60.0 <= t <= 60.3 else 12.4, us(t))
        brown.append(60.0 <= t <= 60.2, us(t))
        off.append(1 if t >= 40.05 else 0, us(t))
        faults.append((1 << 3) if 90 <= t <= 91 else 0, us(t))
        for m, e in motors.items():
            gone = m in "CD" and 40.0 <= t <= 40.4
            e["Present"].append(not gone, us(t))
            e["Dropouts"].append(1 if m in "CD" and t >= 40.0 else 0, us(t))
            e["Resets"].append(1 if m == "B" and t >= 75.0 else 0, us(t))
            e["Brownouts"].append(1 if m == "A" and t >= 80.0 else 0, us(t))
            e["Stage"].append("WARN" if m == "A" and t >= 120.0 else "OK", us(t))
            e["Flags"].append("", us(t))
        t += 0.02
    log.close()


@unittest.skipUnless(HAVE, "needs robotpy-wpiutil (pip install pyntcore)")
class LogSummaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "match.wpilog")
        write_log(path)
        cls.report = L.summarize_file(path, MAP)
        cls.text = "\n".join(f"{e['when']} | {e['text']}" for e in cls.report["events"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_phases_follow_the_driver_station(self):
        names = [p[2] for p in self.report["phases"]]
        self.assertEqual(names[:3], ["disabled", "auto", "teleop"])

    def test_each_planted_fault_is_found_at_its_time(self):
        for expected in ("teleop +24.0 s | Off the CAN bus for up to 0.4", "The CAN bus shut itself down",
                         "teleop +44.0 s | Brownout for 0.2", "teleop +59.0 s | B lost power and rebooted",
                         "A saw low supply voltage", "PDH port 3's breaker tripped (B)", "A: motor guard WARN",
                         "teleop +14.0 s | Gain Steer/kP changed from 0.01 to 0.02 (live, not saved): Tune tab, advice:"
                         " Steering overshoots 18%"):
            self.assertIn(expected, self.text)

    def test_a_dropout_run_points_at_the_cable_at_its_start(self):
        f = next(f for f in self.report["findings"] if f["title"].startswith("Everything from C"))
        self.assertEqual(f["where"]["segment"], ["B", "C"])
        self.assertIn("teleop", f["when"])

    def test_a_reboot_points_at_its_pdh_port(self):
        f = next(f for f in self.report["findings"] if "B lost power" in f["title"])
        self.assertIn("PDH port 3", f["why"])

    def test_the_battery_low_point_is_reported(self):
        self.assertAlmostEqual(self.report["battery_min"], 6.4, places=6)
        self.assertIn("battery low 6.4 V", self.report["summary"])

    def test_the_wiring_tab_can_replay_any_moment(self):
        snap = L.snapshot_at(L.read(os.path.join(self.tmp.name, "match.wpilog")), 40.2)
        rows = {r["name"]: r for r in snap["motors"]}
        self.assertEqual((rows["B"]["present"], rows["C"]["present"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
