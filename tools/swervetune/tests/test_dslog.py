"""The Driver Station's logs (dslog.py): files built byte by byte in the documented layout, read back."""

import os
import struct
import tempfile
import unittest

from swervetune import diagnose, dslog as D

MODES = {"teleop": 2, "auto": 1, "disabled": 0}


def record(mode=None, trip=4.0, loss=0.0, volts=12.5, cpu=0.3, brownout=False, pd=33):
    mask = 0xFF                      # a set bit means "off"
    if brownout:
        mask &= ~(1 << 7)
    if mode:
        mask &= ~(1 << MODES[mode])
    data = struct.pack(">BbHBBBBH", int(trip / 0.5), int(round(loss / 0.04)), int(volts * 256), int(round(cpu / 0.005)),
                       mask, 20, 80, 256)
    return data + bytes([0, 0, 0, pd]) + bytes(pd if pd in (25, 33) else 0)


def dslog_bytes(records):
    return struct.pack(">iqQ", 4, 3_870_000_000, 0) + b"".join(records)


def dsevents_bytes(entries):
    out = struct.pack(">iqQ", 4, 3_870_000_000, 0)
    for t, text in entries:
        raw = text.encode("utf-8")
        out += struct.pack(">qQi", 3_870_000_000 + int(t), 0, len(raw)) + raw
    return out


def session():
    """Off, then 100 records driving, a 10-record gap, driving with a 5-record brownout, then off."""
    recs = [record() for _ in range(20)]
    recs += [record("teleop", trip=3.0) for _ in range(100)]
    recs += [record() for _ in range(10)]
    recs += [record("teleop", trip=3.0, brownout=20 <= i < 25, volts=6.5 if 20 <= i < 25 else 12.4) for i in range(50)]
    recs += [record() for _ in range(20)]
    return recs


class ReadTest(unittest.TestCase):
    def test_records_and_their_flags(self):
        log = D.read_dslog(dslog_bytes(session()))
        self.assertEqual(len(log["trip_ms"]), 200)
        self.assertEqual(log["trip_ms"][25], 3.0)
        self.assertAlmostEqual(log["volts"][25], 12.5, places=2)
        self.assertTrue(log["enabled"][25])
        self.assertFalse(log["connected"][5])
        self.assertEqual(sum(log["brownout"]), 5)

    def test_every_power_distribution_size(self):
        for pd in (33, 25, 0):
            log = D.read_dslog(dslog_bytes([record("disabled", pd=pd), record("teleop", pd=pd)]))
            self.assertEqual(log["enabled"], [False, True], pd)

    def test_events_lose_their_tags(self):
        ev = D.read_dsevents(dsevents_bytes([(3, "<TagVersion>1 <time> 00:03 <message> Ping Results: link-GOOD, "
                                                  "DS radio(.4)-GOOD, robot radio(.1)-bad, cRIO(.2)-bad, FMS-bad")]))
        self.assertEqual(ev[0][0], 3)
        self.assertTrue(ev[0][1].startswith("Ping Results"))

    def test_another_version_is_refused(self):
        with self.assertRaises(ValueError):
            D.read_dslog(struct.pack(">iqQ", 3, 0, 0))


class SummaryTest(unittest.TestCase):
    def summary(self):
        events = [(2, "<message> Ping Results: link-GOOD, DS radio(.4)-GOOD, robot radio(.1)-bad, cRIO(.2)-bad, FMS-bad"),
                  (2, "<message> Warning: loop overrun 0.021 s"), (3, "<message> Warning: loop overrun 0.034 s")]
        return D.summary(D.read_dslog(dslog_bytes(session())), D.read_dsevents(dsevents_bytes(events)), "2026_10_17 10_05_33 Sat")

    def test_a_drop_while_driving_and_a_brownout(self):
        s = self.summary()
        self.assertEqual(s["drops"], [{"at_s": 2.4, "length_s": 0.2, "while_enabled": True}], "not the off time at either end")
        self.assertEqual(s["brownouts"], 1)
        self.assertEqual(s["min_volts"], 6.5)
        self.assertEqual(s["ping_bad"], {"robot radio (.1)": 1, "cRIO (.2)": 1, "FMS": 1})
        self.assertEqual(s["messages"][0], ("Warning: loop overrun # s", 2), "numbers folded, so repeats count")

    def test_its_checks(self):
        c = {x["id"]: x for x in D.checks(self.summary())}
        self.assertEqual(c["dslog-drops"]["level"], "fail")
        self.assertIn("while enabled", c["dslog-drops"]["title"])
        self.assertEqual(c["dslog-brownout"]["level"], "fail")
        self.assertEqual(c["dslog-trip"]["level"], "ok")
        self.assertIn("robot radio (.1)", c["dslog-ping"]["title"])

    def test_a_clean_session(self):
        recs = [record("teleop", trip=3.0) for _ in range(100)]
        c = {x["id"]: x["level"] for x in D.checks(D.summary(D.read_dslog(dslog_bytes(recs))))}
        self.assertEqual((c["dslog-drops"], c["dslog-brownout"], c["dslog-loss"]), ("ok", "ok", "ok"))

    def test_a_busy_link(self):
        recs = [record("teleop", trip=30.0, loss=0.12) for _ in range(100)]
        c = {x["id"]: x["level"] for x in D.checks(D.summary(D.read_dslog(dslog_bytes(recs))))}
        self.assertEqual((c["dslog-trip"], c["dslog-loss"]), ("warn", "warn"))


class FilesTest(unittest.TestCase):
    def test_the_newest_session_that_reached_a_robot(self):
        with tempfile.TemporaryDirectory() as d:
            for name, recs in (("2026_10_16 09_00_00 Fri", session()), ("2026_10_17 10_05_33 Sat", [record() for _ in range(50)])):
                with open(os.path.join(d, name + ".dslog"), "wb") as fh:
                    fh.write(dslog_bytes(recs))
            s = D.latest_summary([d])
        self.assertEqual(s["name"], "2026_10_16 09_00_00 Fri", "Saturday's never heard the robot")

    def test_no_logs(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(D.latest_summary([d]))


class TroubleshootTest(unittest.TestCase):
    def test_the_log_answers_losing_communication(self):
        from swervetune import station
        net = {"checks": station.checks({"checks": []}, 1745, ds_log=SummaryTest().summary())}
        r = diagnose.evaluate("comms_drops", [], [], net)
        first = r["checks"][r["first_failing"]]
        self.assertTrue(first["q"].startswith("Are the radio's power"), first["q"])
        battery = [c for c in r["checks"] if c["q"].startswith("Does the battery")][0]
        self.assertEqual(battery.get("auto_answer"), "no")


if __name__ == "__main__":
    unittest.main()
