"""Finding PDH ports: by pulsing swerve motors on blocks, and from a practice log's currents."""

import os
import random
import tempfile
import unittest

from swervetune import pdhports as P, plant

try:
    import wpiutil  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

NAMES = ["frontleft drive", "frontleft steer", "frontright drive", "frontright steer",
         "backleft drive", "backleft steer", "backright drive", "backright steer"]
TRUE = [0, 1, 2, 3, 16, 17, 18, 19]


def pulse_doc(ports=TRUE, background=None, tweak=None):
    ch, notes, meta = plant.pdh_pulses(NAMES, ports, background=background)
    if tweak:
        tweak(ch)
    return {"test": "pdh_map", "channels": ch, "notes": notes, "meta": meta}


class PulseTest(unittest.TestCase):
    def test_every_motor_is_found_through_a_steady_background(self):
        r = P.from_pulses(pulse_doc(background={20: 3.0, 21: 1.2}))
        self.assertEqual(r["proposed"], dict(zip(NAMES, TRUE)))
        self.assertEqual(r["channels"], 24)
        self.assertTrue(all(x["verdict"] == "new" for x in r["rows"]))
        self.assertEqual(r["findings"], [])

    def test_a_swapped_port_and_a_motor_fed_elsewhere(self):
        ports = list(TRUE)
        ports[5] = None
        m = {"pdhPorts": {"frontleft drive": 0, "frontright drive": 9}}
        r = P.from_pulses(pulse_doc(ports), m)
        rows = {x["name"]: x for x in r["rows"]}
        self.assertEqual(rows["frontleft drive"]["verdict"], "same")
        self.assertEqual(rows["frontright drive"]["verdict"], "differs")
        self.assertEqual(rows["backleft steer"]["status"], "none")
        self.assertNotIn("backleft steer", r["proposed"])
        titles = " | ".join(f["title"] for f in r["findings"])
        self.assertIn("map says frontright drive is on PDH port 9, but it drew from port 2", titles)
        self.assertIn("Pulsing backleft steer moved no PDH port", titles)

    def test_two_motors_on_one_port_is_an_error(self):
        ports = list(TRUE)
        ports[3] = 2
        r = P.from_pulses(pulse_doc(ports))
        err = [f for f in r["findings"] if f["level"] == "error"]
        self.assertEqual(len(err), 1)
        self.assertIn("frontright drive and frontright steer all drew from PDH port 2", err[0]["title"])

    def test_something_else_switching_on_mid_pulse_is_unclear_not_wrong(self):
        def compressor(ch):
            for i, (s, o) in enumerate(zip(ch["slot"], ch["on"])):
                if s == 4 and o == 1:
                    ch["pdh21"][i] += 0.7
        r = P.from_pulses(pulse_doc(tweak=compressor))
        row = next(x for x in r["rows"] if x["name"] == "backleft drive")
        self.assertEqual(row["status"], "unclear")
        self.assertNotIn("backleft drive", r["proposed"])

    def test_a_simulator_run_has_no_pdh(self):
        r = P.from_pulses({"channels": {"t": [0, 1], "slot": [0, 0], "on": [0, 1]}, "notes": ["pulse 0: a drive"]})
        self.assertIn("no PDH currents", r["findings"][0]["title"])

    def test_a_pdh_that_reads_zero_is_one_finding_not_one_per_motor(self):
        def flat(ch):
            for p in range(24):
                ch[f"pdh{p}"] = [0.0] * len(ch["t"])
        doc = pulse_doc(tweak=flat)
        r = P.from_pulses(doc)
        self.assertEqual([f["level"] for f in r["findings"]], ["error"])
        doc["env"] = "SIM"
        r = P.from_pulses(doc)
        self.assertEqual(r["findings"][0]["level"], "info")
        self.assertIn("Expected in the simulator", r["findings"][0]["why"])

    def test_merge_writes_ports_into_a_copy(self):
        m = {"pdhPorts": {"Shooter": 7}}
        out = P.merge(m, {"frontleft drive": 0})
        self.assertEqual(out["pdhPorts"], {"Shooter": 7, "frontleft drive": 0})
        self.assertEqual(m["pdhPorts"], {"Shooter": 7})


def log_series(seed=5):
    """Intake on 5, shooter leader 7 and follower 8 (always together), climber never runs.

    Like a real match log, the robot sits disabled for a long time first: that time must not count.
    """
    rng = random.Random(seed)
    s = {"/DriverStation/Enabled": [(0.0, False), (240.0, True), (360.0, False)],
         "/PowerDistribution/ChannelCurrent": []}
    motors = {"Intake": [], "Shooter leader": [], "Shooter follower": [], "Climber": []}
    intake = shooter = 0.0
    t = 0.0
    while t < 364:
        if rng.random() < 0.02:
            intake = rng.choice([0.0, 0.0, 18.0, 30.0])
        if rng.random() < 0.01:
            shooter = rng.choice([0.0, 25.0, 40.0])
        on = 240.0 <= t <= 360.0
        i_a, s_a = (intake, shooter) if on else (0.0, 0.0)
        motors["Intake"].append((t, i_a + rng.gauss(0, 0.3)))
        motors["Shooter leader"].append((t, s_a + rng.gauss(0, 0.3)))
        motors["Shooter follower"].append((t, s_a * 0.97 + rng.gauss(0, 0.3)))
        motors["Climber"].append((t, rng.gauss(0, 0.05)))
        pdh = [0.05 + abs(rng.gauss(0, 0.06)) for _ in range(24)]
        pdh[5] += 0.02 * i_a ** 1.3       # battery side: grows faster than linearly with load
        pdh[7] += 0.02 * s_a ** 1.3
        pdh[8] += 0.02 * (s_a * 0.97) ** 1.3
        pdh[22] += 2.5                    # the radio's steady draw
        s["/PowerDistribution/ChannelCurrent"].append((t, pdh))
        t += 0.02
    for n, v in motors.items():
        s[f"/RealOutputs/Motors/{n}/Amps"] = v
    return s


class LogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = P.from_log(log_series(), {"pdhPorts": {"Intake": 4}})
        cls.rows = {x["name"]: x for x in cls.r["rows"]}

    def test_a_motor_running_on_its_own_is_matched(self):
        self.assertEqual(self.rows["Intake"]["port"], 5)
        self.assertEqual(self.rows["Intake"]["verdict"], "differs")
        self.assertGreater(self.rows["Intake"]["corr"], 0.8)

    def test_a_leader_and_follower_are_a_group_with_their_two_ports(self):
        for n in ("Shooter leader", "Shooter follower"):
            self.assertEqual(self.rows[n]["status"], "together")
            self.assertNotIn(n, self.r["proposed"])
        f = next(f for f in self.r["findings"] if "always ran together" in f["title"])
        self.assertIn("ports 7, 8", f["why"])
        self.assertFalse(any(f["level"] == "error" for f in self.r["findings"]), "no false shared-breaker error")

    def test_a_motor_that_never_ran_is_named(self):
        self.assertEqual(self.rows["Climber"]["status"], "idle")
        self.assertTrue(any("Never ran in this log: Climber" in f["title"] for f in self.r["findings"]))

    def test_a_log_without_the_motor_guard_says_so(self):
        r = P.from_log({"/PowerDistribution/ChannelCurrent": [(0, [0.0] * 24)]})
        self.assertIn("no PDH or motor currents", r["findings"][0]["title"])

    @unittest.skipUnless(HAVE, "needs robotpy-wpiutil")
    def test_the_same_through_a_real_wpilog(self):
        from swervetune import akit, logsummary
        series = log_series()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "practice.wpilog")
            log = akit.LogWriter(path)
            for key, pts in series.items():
                kind = "double[]" if key.endswith("ChannelCurrent") else "boolean" if key.endswith("Enabled") else "double"
                e = log.entry(key, kind)
                for t, v in pts:
                    e.append(v, int(t * 1e6) + 1)
            log.close()
            r = P.from_log(logsummary.read(path))
        self.assertEqual(r["proposed"].get("Intake"), 5)


if __name__ == "__main__":
    unittest.main()
