"""The Driver Station laptop, its firewall and the robot's radio (station.py), from the network
script's facts; the network check that carries them (netcheck.py); and Troubleshoot's use of them."""

import json
import unittest

from swervetune import diagnose, netcheck, station as ST

TEAM, YEAR = 1745, "2026"


def by_id(checks):
    return {c["id"]: c for c in checks}


def adapter(ip, prefix=24, dhcp=True, gateway="", name="Wi-Fi 2", ssid="", robot=False, radio_up=None):
    return {"name": name, "wifi": True, "ip": ip, "prefix": prefix, "dhcp": dhcp, "gateway": gateway, "ssid": ssid,
            "robot": robot, "radio_up": radio_up}


class DriverStationTest(unittest.TestCase):
    def test_the_right_year_and_team(self):
        c = by_id(ST.driver_station({"installed": True, "version": "26.0.0.49166", "ini": True, "team": 1745}, TEAM, YEAR))
        self.assertEqual((c["ds-version"]["level"], c["ds-team"]["level"]), ("ok", "ok"))

    def test_last_years_driver_station(self):
        c = by_id(ST.driver_station({"installed": True, "version": "25.0.1.1", "ini": True, "team": 1745}, TEAM, YEAR))
        self.assertEqual(c["ds-version"]["level"], "fail")
        self.assertIn("Driver Station 2025, but the robot code is 2026", c["ds-version"]["title"])

    def test_another_teams_number(self):
        c = by_id(ST.driver_station({"installed": True, "version": "26.0", "ini": True, "team": 9990}, TEAM, YEAR))
        self.assertEqual(c["ds-team"]["level"], "fail")
        self.assertIn("10.99.90.2", c["ds-team"]["why"])

    def test_never_set_up_or_not_installed(self):
        c = by_id(ST.driver_station({"installed": True, "version": "26.0", "ini": False}, TEAM, YEAR))
        self.assertEqual(c["ds-team"]["level"], "warn")
        self.assertEqual(list(by_id(ST.driver_station({"installed": False}, TEAM, YEAR))), ["ds-installed"])


class AddressTest(unittest.TestCase):
    def one(self, a, internet=""):
        found = ST.addresses([a], TEAM, internet)
        self.assertEqual(len(found), 1, found)
        return found[0]

    def test_automatic_from_the_radio(self):
        c = self.one(adapter("10.17.45.201", robot=True))
        self.assertEqual((c["id"], c["level"]), ("ip-config", "ok"))

    def test_the_fields_static_address(self):
        self.assertEqual(self.one(adapter("10.17.45.5", prefix=8, dhcp=False))["level"], "ok")
        self.assertEqual(self.one(adapter("10.17.45.5", dhcp=False, gateway="10.17.45.4"))["level"], "ok")
        self.assertEqual(self.one(adapter("10.17.45.5", dhcp=False))["level"], "warn", "a /24 with no gateway misses the field")

    def test_static_addresses_that_collide(self):
        self.assertEqual(self.one(adapter("10.17.45.2", dhcp=False))["level"], "fail", "the robot's own")
        self.assertIn("the access point radio", self.one(adapter("10.17.45.4", dhcp=False))["title"])
        self.assertEqual(self.one(adapter("10.17.45.30", dhcp=False))["level"], "warn", "inside a DHCP range")

    def test_no_address_and_the_radio_setup_address(self):
        self.assertEqual(self.one(adapter("169.254.10.3"))["id"], "ip-none")
        c = self.one(adapter("192.168.69.2", dhcp=False, radio_up=True))
        self.assertEqual(c["id"], "ip-setup")
        self.assertIn("http://192.168.69.1/", c["why"])

    def test_a_radio_on_its_factory_setting_or_another_teams(self):
        self.assertEqual(self.one(adapter("10.0.1.200"))["id"], "ip-factory")
        c = self.one(adapter("10.99.90.201", radio_up=True))
        self.assertEqual((c["id"], c["level"]), ("ip-other-team", "fail"))
        self.assertIn("team 9990", c["title"])
        self.assertIn("by hand", self.one(adapter("10.174.51.5", prefix=8, dhcp=False))["title"])

    def test_a_schools_10_network_is_not_a_robots(self):
        self.assertEqual(ST.addresses([adapter("10.20.30.40", prefix=16)], TEAM), [], "not a /24 radio network")
        self.assertEqual(ST.addresses([adapter("10.99.90.201", name="Wi-Fi")], TEAM, internet_adapter="Wi-Fi"), [],
                         "the adapter carrying the internet")

    def test_another_teams_radio_by_its_ssid(self):
        found = by_id(ST.addresses([adapter("10.17.45.201", ssid="FRC-9990", robot=True)], TEAM))
        self.assertEqual(found["wifi-other-team"]["level"], "fail")


class FirewallTest(unittest.TestCase):
    RULE = {"name": "Driver Station", "enabled": True, "direction": "Inbound", "action": "Allow", "profile": "Any"}

    def fw(self, rules=(), robot="Public", public=True, others=()):
        return {"profiles": {"Domain": True, "Private": True, "Public": public}, "robot_profile": robot,
                "ds_rules": list(rules), "others": list(others)}

    def test_allowed_blocked_or_missing(self):
        self.assertEqual(by_id(ST.firewall(self.fw([self.RULE]), True))["fw-ds"]["level"], "ok")
        self.assertEqual(by_id(ST.firewall(self.fw([dict(self.RULE, action="Block")]), True))["fw-ds"]["level"], "fail")
        missing = by_id(ST.firewall(self.fw([dict(self.RULE, profile="Private")]), True))["fw-ds"]
        self.assertEqual(missing["level"], "fail", "only allowed on Private; the robot's network is Public")
        self.assertIn("Allow an app through firewall", missing["why"])

    def test_off_for_the_robots_kind_of_network(self):
        self.assertEqual(by_id(ST.firewall(self.fw(public=False), True))["fw-ds"]["level"], "ok")

    def test_another_firewall(self):
        c = by_id(ST.firewall(self.fw([self.RULE], others=["Norton Firewall", "Windows Defender"]), True))
        self.assertIn("Norton Firewall", c["fw-other"]["title"])
        self.assertNotIn("Defender", c["fw-other"]["title"])

    def test_off_the_robots_network_it_only_warns(self):
        c = by_id(ST.firewall(self.fw(robot=""), True))["fw-ds"]
        self.assertEqual(c["level"], "warn")


class RadioTest(unittest.TestCase):
    def test_the_access_point_answers_but_the_robot_radio_doesnt(self):
        c = by_id(ST.radio({"robot_radio": False, "ap_radio": True, "roborio": False}, "", TEAM))["radio-link"]
        self.assertEqual(c["level"], "fail")
        self.assertIn("kiosk", c["why"])
        self.assertIn("SYS light blinking once a second", c["why"])

    def test_firmware_from_its_page(self):
        reach = {"robot_radio": True, "ap_radio": True}
        self.assertEqual(ST.firmware("VH-109 Configuration ... Firmware Version: 1.3.2"), (1, 3, 2))
        self.assertEqual(by_id(ST.radio(reach, "Version v1.2.4", TEAM))["radio-firmware"]["level"], "warn")
        self.assertEqual(by_id(ST.radio(reach, "Firmware 1.3.0", TEAM))["radio-firmware"]["level"], "ok")
        none = by_id(ST.radio(reach, "Robot Radio Mode Team Number", TEAM))["radio-firmware"]
        self.assertIn("before 1.2.0", none["why"])


class RobotSoftwareTest(unittest.TestCase):
    def test_the_image_year(self):
        self.assertEqual(ST.robot_software("FRC_roboRIO2_2026_v2.0", "2026.2.1", YEAR)[0]["level"], "ok")
        bad = ST.robot_software("FRC_roboRIO2_2025_v2.0", "2026.2.1", YEAR)[0]
        self.assertEqual(bad["level"], "fail")
        self.assertIn("roboRIO Imaging Tool", bad["why"])

    def test_an_image_gradlerio_refuses(self):
        c = ST.robot_software("FRC_roboRIO2_2026_v1.0", "", YEAR, accepted=["2026_v1.2", "2026_v2"])[0]
        self.assertEqual(c["level"], "warn")
        self.assertEqual(ST.robot_software("FRC_roboRIO2_2026_v2.1", "", YEAR, accepted=["2026_v1.2", "2026_v2"])[0]["level"], "ok")

    def test_the_simulator_has_no_image(self):
        self.assertEqual([c["id"] for c in ST.robot_software("", "2026.2.1", YEAR)], ["robot-wpilib"])


class NetcheckTest(unittest.TestCase):
    """The script's JSON, with facts, through netcheck.run, as the page gets it."""

    def run_with(self, script_out, **kw):
        class P:
            stdout = json.dumps(script_out)
            stderr = ""
        return netcheck.run(TEAM, runner=lambda *a, **k: P(), **kw)

    def test_facts_become_grouped_checks_in_order(self):
        out = {"ok": True, "checks": [{"id": "internet", "level": "ok", "title": "Internet", "why": ""},
                                      {"id": "firewall", "level": "info", "title": "Public", "why": ""},
                                      {"id": "robot-ping", "level": "ok", "title": "Robot answers", "why": ""}],
               "internet_adapter": "Wi-Fi",
               "facts": {"ds": {"installed": True, "version": "26.0.0.1", "ini": True, "team": 9990},
                         "adapters": [adapter("10.17.45.201", robot=True)],
                         "firewall": {"profiles": {"Public": True, "Private": True}, "robot_profile": "Public", "ds_rules": [], "others": []},
                         "reach": {"robot_radio": True, "ap_radio": True, "roborio": True}, "radio_page": "Firmware 1.3.1"}}
        r = self.run_with(out, year=YEAR, robot={"image": "FRC_roboRIO2_2026_v2.0", "wpilib": "2026.2.1"})
        ids = [c["id"] for c in r["checks"]]
        self.assertNotIn("firewall", ids, "the firewall checks replace the script's hint")
        self.assertFalse(r["ok"], "the Driver Station's team and the firewall fail")
        groups = [c["group"] for c in r["checks"]]
        self.assertEqual(groups[0], ST.DS)
        self.assertEqual(groups[-1], ST.INTERNET)
        self.assertLess(ids.index("radio-link"), ids.index("robot-image"))


class SaveTest(unittest.TestCase):
    def test_a_saved_check_carries_no_passwords(self):
        import os
        import tempfile
        result = {"ok": False, "checks": [{"id": "radio-link", "level": "fail", "title": "x", "why": "y"}],
                  "facts": {"radio_page": "Firmware Version 1.3.2 WPA Key: hunter22 Password=abc123"}}
        with tempfile.TemporaryDirectory() as d:
            path = netcheck.save(result, "Black team", 9990, folder=d)
            self.assertTrue(os.path.basename(path).startswith("netcheck-black-team-"))
            doc = json.load(open(path, encoding="utf-8"))
        self.assertEqual((doc["robot"], doc["team"], doc["checks"][0]["id"]), ("Black team", 9990, "radio-link"))
        self.assertNotIn("hunter22", doc["facts"]["radio_page"])
        self.assertNotIn("abc123", doc["facts"]["radio_page"])
        self.assertIn("1.3.2", doc["facts"]["radio_page"])
        self.assertIn("UTC)", doc["saved"], "local time first, UTC after it")

    def test_an_unread_team_number_names_the_settings_entries(self):
        c = by_id(ST.driver_station({"installed": True, "version": "26.0", "ini": True, "team": None,
                                     "ini_keys": ["Team Num", "DashboardCmdLine"]}, TEAM, YEAR))["ds-team"]
        self.assertIn("Team Num", c["why"])


class TroubleshootTest(unittest.TestCase):
    def test_the_network_check_answers_communications_symptoms(self):
        net = {"checks": [{"id": "radio-link", "level": "fail", "title": "The access point radio answers; the robot radio doesn't"},
                          {"id": "ds-team", "level": "ok", "title": "fine"}]}
        r = diagnose.evaluate("after_event", [], [], net)
        first = r["checks"][r["first_failing"]]
        self.assertEqual(first["evidence"], ["The access point radio answers; the robot radio doesn't"])
        team = [c for c in r["checks"] if c["q"].startswith("Is the Driver Station still")][0]
        self.assertEqual((team.get("suggest"), team.get("suggest_by")), ("yes", "net"))

    def test_every_communications_check_can_run_the_network_check(self):
        for sid in ("no_comms", "no_robot_code", "after_event"):
            for c in diagnose.BY_ID[sid]["checks"]:
                if "net" in (c.get("auto") or {}):
                    self.assertEqual(c.get("action"), {"type": "netcheck"}, (sid, c["q"]))


if __name__ == "__main__":
    unittest.main()
