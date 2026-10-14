"""Wiring diagnosis: the map is found in the code, and each rule points at the right place."""

import os
import unittest

from slothtune import wiring as W, yagslcfg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PEA = yagslcfg.Project(os.path.join(REPO, "Peashooter"))
BLACK = yagslcfg.Project(os.path.join(REPO, "Black team"))

CHAIN = ["roboRIO", "FL drive", "FL steer", "FR drive", "FR steer", "Shooter", "PDH"]


def a_map(confirmed=True):
    return {"buses": [{"name": "roboRIO CAN", "chain": list(CHAIN), "orderConfirmed": confirmed,
                       "segmentLengthsM": {}}],
            "pdhPorts": {"FR drive": 3, "Shooter": 7}}


def rows(**kw):
    out = []
    for name in CHAIN[1:-1]:
        r = {"name": name, "present": 1, "dropouts": 0, "resets": 0, "brownouts": 0}
        r.update(kw.get(name.replace(" ", "_"), {}))
        out.append(r)
    return out


class DiscoveryTest(unittest.TestCase):
    def test_every_can_device_is_found_with_its_id(self):
        pea = {d["name"]: d["can_id"] for d in W.discover(PEA)}
        self.assertEqual(len(pea), 15)
        self.assertEqual(pea["Spindexter"], 14)
        self.assertEqual(pea["frontleft steer"], 6)
        black = {d["name"]: d["can_id"] for d in W.discover(BLACK)}
        self.assertEqual(black["Intake"], 9, "a CAN_ID constant is resolved")
        self.assertEqual(len(black), 10)

    def test_each_device_says_what_it_is(self):
        self.assertEqual(W.device_type("sparkflex_vortex"), "SPARK Flex · NEO Vortex")
        self.assertEqual(W.device_type("sparkmax_neo550"), "SPARK MAX · NEO 550")
        self.assertEqual(W.device_type("SparkMax"), "SPARK MAX", "a Java class name too")
        self.assertEqual(W.device_type("pigeon2"), "Pigeon 2")
        self.assertEqual(W.device_type("something else"), "something else")
        devs = W.devices_by_name(PEA, W.default_map(PEA))
        self.assertEqual((devs["Spindexter"]["type"], devs["Tower"]["type"]), ("SPARK MAX", "SPARK Flex"))
        self.assertEqual(devs["frontleft steer"]["type"], "SPARK MAX · NEO 550")
        self.assertEqual(devs["PDH"]["type"], "REV PDH")

    def test_a_fresh_map_is_unconfirmed_and_ends_at_the_terminators(self):
        m = W.default_map(PEA)
        chain = m["buses"][0]["chain"]
        self.assertEqual((chain[0], chain[-1]), ("roboRIO", "PDH"))
        self.assertFalse(m["buses"][0]["orderConfirmed"])
        self.assertEqual(W.bus_length(m["buses"][0]), (8.0, 0, 16))


class BusesTest(unittest.TestCase):
    """Several CAN buses (SystemCore): each its own chain, CAN-H in its cable color, CAN-L green."""

    TWO = {"canBuses": [{"name": "rio", "color": "yellow"}, {"name": "mech", "color": "white"}],
           "pdh": {"canbus": "rio"},
           "motors": [{"name": "Spindexter", "motor": {"type": "sparkflex_vortex", "id": 14, "canbus": "mech"}}]}

    def test_each_bus_keeps_its_own_color_and_two_never_share_one(self):
        m = {"buses": [{"name": "rio"}, {"name": "mech", "color": "purple"}, {"name": "extra", "color": "purple"}]}
        self.assertEqual(W.bus_colors(m, self.TWO), ["yellow", "purple", "white"],
                         "the design names the first; the map's own color wins; a clash takes the next free one")
        self.assertEqual(W.bus_colors({"buses": [{"name": "x", "color": "green"}]}), ["yellow"],
                         "green is CAN-L on every bus, never a bus's color")

    def test_a_new_map_has_one_chain_per_designed_bus(self):
        from unittest import mock
        with mock.patch.object(W, "_design", return_value=self.TWO):
            m = W.default_map(PEA)
        rio, mech = m["buses"]
        self.assertEqual((rio["name"], rio["color"], mech["name"], mech["color"]), ("rio", "yellow", "mech", "white"))
        self.assertEqual(mech["chain"], ["roboRIO", "Spindexter"], "a device on its designed bus, no PDH there")
        self.assertEqual((rio["chain"][0], rio["chain"][-1]), ("roboRIO", "PDH"))
        self.assertNotIn("Spindexter", rio["chain"])

    def test_each_bus_carries_what_people_call_it(self):
        from unittest import mock
        two = {**self.TWO, "canBuses": [{"name": "rio", "label": "Drive train", "color": "yellow"},
                                        {"name": "mech", "label": "Intake", "color": "white"}]}
        with mock.patch.object(W, "_design", return_value=two):
            m = W.default_map(PEA)
        self.assertEqual([b["label"] for b in m["buses"]], ["Drive train", "Intake"])
        self.assertEqual(W.bus_labels({"buses": [{"name": "mech"}, {"name": "rio", "label": "Swerve"}]}, two),
                         ["Intake", "Swerve"], "an older map takes the design's label; its own wins")
        self.assertEqual(W.bus_label({"name": "rio"}), "rio")

    def test_a_device_new_to_the_code_joins_its_designed_bus(self):
        from unittest import mock
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(W, "_design", return_value=self.TWO), \
                mock.patch.object(W, "map_path", return_value=os.path.join(tmp, "wiring.json")):
            m = W.default_map(PEA)
            m["buses"][1]["chain"] = ["roboRIO"]
            m["buses"][1]["orderConfirmed"] = True
            with open(os.path.join(tmp, "wiring.json"), "w", encoding="utf-8") as f:
                json.dump(m, f)
            back = W.load_map(PEA)
        self.assertEqual(back["buses"][1]["chain"], ["roboRIO", "Spindexter"])
        self.assertFalse(back["buses"][1]["orderConfirmed"], "its place on the bus needs checking")


def load_run(quiet_err=0, loaded_err=0, busoff=0, util=(0.3, 0.7), env="BLOCKS"):
    """A can_load run: 3 s quiet, 8 s loaded, 2 s quiet, at 50 Hz; errors in the first n samples of a phase."""
    phase = [0] * 150 + [1] * 400 + [2] * 100
    ch = {"t": [i / 50 for i in range(len(phase))], "phase": phase,
          "util": [util[0] if p != 1 else util[1] for p in phase],
          "busoff": [0] * 300 + [busoff] * (len(phase) - 300), "txfull": [0] * len(phase),
          "rxerr": [0] * len(phase), "txerr": [0] * len(phase)}
    for i in range(quiet_err):
        ch["rxerr"][i] = 2
    for i in range(loaded_err):
        ch["rxerr"][150 + i] = 5
    return {"test": "can_load", "env": env, "outcome": "DONE", "channels": ch, "meta": {}, "notes": []}


class CanLoadTest(unittest.TestCase):
    def kinds(self, **kw):
        rep = W.can_load_report(load_run(**kw))
        return rep, [(f["level"], f["title"]) for f in rep["findings"]]

    def test_clean_says_what_it_cannot_prove(self):
        rep, f = self.kinds()
        self.assertEqual(f[0], ("ok", "No errors at 70% busy"))
        self.assertIn("does not prove", rep["findings"][0]["why"])
        self.assertIsNone(rep["score"])

    def test_errors_only_under_load(self):
        rep, f = self.kinds(loaded_err=12)
        self.assertEqual(f[0][0], "warn")
        self.assertIn("only when the bus got busy (12 of 400 samples at 70%)", f[0][1])

    def test_errors_when_quiet_and_bus_off(self):
        self.assertEqual(self.kinds(quiet_err=3, loaded_err=3)[1][0][0], "error")
        self.assertIn("shut itself down 2 times", self.kinds(busoff=2)[1][0][1])

    def test_too_little_load_and_the_simulator(self):
        self.assertEqual(self.kinds(util=(0.1, 0.2))[1][0][0], "info")
        rep, f = self.kinds(env="SIM", loaded_err=50)
        self.assertEqual(f, [], "the simulator has no real bus")

    def test_the_advisor_routes_it(self):
        from slothtune import advisor
        self.assertEqual(advisor.analyze(load_run())["test"], "can_load")


class TerminationTest(unittest.TestCase):
    """Two readings at a bus's far end, robot off: terminator in, then out."""

    PDH_END = {"chain": ["roboRIO", "FL drive", "PDH"]}
    PLUG_END = {"chain": ["roboRIO", "Intake", "Tower"]}

    def kind(self, a, b=None, bus=None):
        return W.termination_pair(W.parse_ohms(a), W.parse_ohms(b), bus or self.PDH_END)

    def test_both_terminators_work(self):
        v = self.kind("60.2", "119")
        self.assertEqual((v["level"], v["kind"]), ("ok", "ok"))

    def test_a_far_terminator_fitted_but_not_working(self):
        v = self.kind("121", "120")
        self.assertEqual((v["level"], v["kind"]), ("error", "far_dead"))
        self.assertIn("isn't working", v["title"])
        self.assertIn("TERM switch", v["why"], "it names the PDH's switch at a PDH end")
        self.assertIn("after Tower", self.kind("121", "120", self.PLUG_END)["why"], "and a plug-in one after the last device")

    def test_a_broken_cable_is_not_a_missing_terminator(self):
        v = self.kind("120", "OL")
        self.assertEqual((v["level"], v["kind"]), ("error", "broken"))
        self.assertIn("broken", v["title"])

    def test_other_pairs(self):
        self.assertEqual(self.kind("OL", "ol")["kind"], "open")
        self.assertEqual(self.kind("60", "60")["kind"], "far_dead", "another terminator stands in for the dead one")
        self.assertEqual(self.kind("40", "60")["kind"], "extra")
        self.assertEqual(self.kind("2", "OL")["kind"], "short")
        self.assertEqual(self.kind("120", "60")["kind"], "odd", "taking a terminator out never lowers it")

    def test_one_reading_says_how_to_tell_missing_from_broken(self):
        v = self.kind("119 Ω")
        self.assertEqual((v["level"], v["kind"]), ("error", "one"))
        self.assertIn("second reading", v["why"])
        self.assertEqual(self.kind("")["kind"], "none")

    def test_a_reading_as_typed(self):
        self.assertEqual(W.parse_ohms("OL"), float("inf"))
        self.assertEqual(W.parse_ohms(" 59.9 ohms"), 59.9)
        self.assertIsNone(W.parse_ohms("abc"))
        self.assertIsNone(W.parse_ohms(None))


class RulesTest(unittest.TestCase):
    def find(self, snapshot, m=None):
        return W.diagnose(m or a_map(), snapshot)

    def test_a_tail_going_silent_is_the_cable_at_its_start(self):
        f = self.find({"motors": rows(FR_drive={"present": 0}, FR_steer={"present": 0}, Shooter={"present": 0})})
        self.assertEqual(len(f), 1)
        self.assertIn("Everything from FR drive", f[0]["title"])
        self.assertEqual(f[0]["where"]["segment"], ["FL steer", "FR drive"])

    def test_one_device_alone_is_its_power(self):
        f = self.find({"motors": rows(FR_drive={"present": 0})})
        self.assertIn("on its own", f[0]["title"])
        self.assertIn("PDH port 3", f[0]["why"])

    def test_the_last_device_alone_is_also_treated_as_alone(self):
        f = self.find({"motors": rows(Shooter={"present": 0})})
        self.assertIn("Shooter is off the CAN bus on its own", f[0]["title"])

    def test_an_intermittent_run_points_at_its_first_link(self):
        f = self.find({"motors": rows(FR_steer={"dropouts": 2}, Shooter={"dropouts": 2})})
        self.assertIn("from FR steer onward", f[0]["title"])
        self.assertEqual(f[0]["where"]["segment"], ["FR drive", "FR steer"])

    def test_reboots_point_at_power_and_many_point_upstream(self):
        one = self.find({"motors": rows(Shooter={"resets": 1})})
        self.assertIn("PDH port 7", one[0]["why"])
        many = self.find({"motors": rows(FL_drive={"resets": 1}, FR_drive={"resets": 1}, Shooter={"resets": 1})})
        self.assertTrue(any("3 controllers have rebooted" in x["title"] for x in many))

    def test_bus_errors(self):
        f = self.find({"motors": rows(), "can": [0.4, 2, 0, 12, 0]})
        titles = " | ".join(x["title"] for x in f)
        self.assertIn("shut itself down 2 times", titles)
        self.assertIn("CAN errors happening now", titles)

    def test_each_controllers_own_faults_now_and_earlier(self):
        f = self.find({"motors": rows(FR_steer={"flags": "faults: CAN"},
                                      Shooter={"history": "faults since last cleared: sensor (encoder or hall cable)"})})
        now = [x for x in f if x["title"] == "FR steer: faults: CAN"][0]
        self.assertEqual((now["level"], now["where"]["devices"]), ("error", ["FR steer"]))
        self.assertIn("CAN plugs", now["why"])
        earlier = [x for x in f if x["title"].startswith("Shooter: faults since last cleared")][0]
        self.assertEqual(earlier["level"], "warn")
        gone = self.find({"motors": rows(FR_steer={"flags": "faults: CAN", "present": 0})})
        self.assertFalse(any(x["title"] == "FR steer: faults: CAN" for x in gone), "off the bus says it already")

    def test_a_healthy_robot_has_nothing_to_say(self):
        self.assertEqual(self.find({"motors": rows(), "can": [0.3, 0, 0, 0, 0]}), [])

    def test_feed_resistance(self):
        samples = [(12.2, 12.2 - 0.05 * i - 0.08, i) for i in range(0, 40, 2)]
        self.assertAlmostEqual(W.feed_resistance(samples), 0.05, places=6)
        self.assertIsNone(W.feed_resistance([(12.2, 12.1, 2.0)] * 20), "needs a spread of current")
        f = self.find({"motors": rows(), "feed_r": {"Shooter": 0.08}})
        self.assertEqual(f[0]["level"], "error")
        self.assertIn("80 milliohms", f[0]["title"])

    def test_termination_readings(self):
        self.assertEqual(W.termination_verdict(61)["level"], "ok")
        self.assertIn("one terminator missing", W.termination_verdict(121)["title"])
        self.assertIn("too many", W.termination_verdict(40)["title"])
        self.assertIn("too low", W.termination_verdict(10)["title"])
        self.assertIn("open", W.termination_verdict(5000)["title"])


if __name__ == "__main__":
    unittest.main()
