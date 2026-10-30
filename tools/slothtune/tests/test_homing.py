"""Homing a pivot or elevator on a relative encoder (decision 85): the report a system_home run gets."""

import unittest

from slothtune import advisor, contract as C, systems


def run(meta=None, end="lower end", message=""):
    return {"test": "system_home", "env": "BLOCKS", "meta": meta or {}, "message": message,
            "notes": [f"system: Intake pivot (PIVOT, rot), held at its {end}"]}


class HomeReportTest(unittest.TestCase):
    def test_a_homed_pivot_says_where_its_limits_are_now(self):
        r = systems.home_report(run({"shift": 5.0, "min": 5.0, "max": 23.0}))
        self.assertEqual(r["test"], "system_home")
        self.assertIn("Intake pivot homed at its lower end", r["summary"])
        self.assertIn("5 to 23 rot", r["summary"])
        self.assertEqual([f["level"] for f in r["findings"]], ["ok"])
        self.assertEqual(r["limits"], {"min": 5.0, "max": 23.0, "units": "rot", "name": "Intake pivot"})

    def test_a_shift_bigger_than_its_range_says_to_check_the_end(self):
        r = systems.home_report(run({"shift": 40.0, "min": 40.0, "max": 58.0}, end="upper end"))
        self.assertEqual([f["level"] for f in r["findings"]], ["ok", "warn"])
        self.assertIn("upper end", r["findings"][1]["why"])

    def test_a_run_that_was_stopped_isnt_homed(self):
        r = systems.home_report(run(message="Intake pivot moved 0.5 rot while it was read"))
        self.assertEqual(r["summary"], "It wasn't homed.")
        self.assertEqual(r["findings"][0]["level"], "error")
        self.assertIn("moved", r["findings"][0]["why"])

    def test_the_advisor_hands_a_home_run_to_its_report(self):
        r = advisor.analyze(run({"shift": 0.0, "min": 0.0, "max": 18.0}))
        self.assertEqual(r["test"], "system_home")

    def test_the_contract_knows_the_test_and_its_topics(self):
        self.assertIn("system_home", C.TESTS)
        self.assertTrue(C.SYSTEMS_HOMED.endswith("Homed"))
        self.assertTrue(C.STATUS_DEADMAN_CONTROLLER.endswith("/Status/DeadmanController"))


class LimitsAgreementTest(unittest.TestCase):
    """Limits by hand also compare the code's reading with its motor's own encoder."""

    def doc(self, r):
        return {"test": "system_limits", "meta": {"min": 0.0, "max": 18.0, "sensor_r": r},
                "notes": ["system: Intake pivot (PIVOT, rot)"]}

    def test_readings_that_move_together_agree(self):
        f = systems.limits_report(self.doc(-0.999))["findings"]
        self.assertEqual([x["level"] for x in f], ["ok", "ok"])
        self.assertIn("agree", f[1]["title"])

    def test_a_slipping_belt_is_a_warning(self):
        f = systems.limits_report(self.doc(0.81))["findings"]
        self.assertEqual(f[1]["level"], "warn")
        self.assertIn("slipping", f[1]["why"])

    def test_no_second_reading_says_nothing_about_it(self):
        doc = self.doc(0.9)
        del doc["meta"]["sensor_r"]
        self.assertEqual(len(systems.limits_report(doc)["findings"]), 1)


if __name__ == "__main__":
    unittest.main()
