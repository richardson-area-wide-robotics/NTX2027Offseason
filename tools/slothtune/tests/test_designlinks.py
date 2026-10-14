"""Design links from ReCalc and AMBcalc, read back to the numbers each site's own code shows.

The example links were produced by each site's own code (ReCalc's Copy Link on its 2026 app, the
old app's encoder for legacy links, AMBcalc's pages run in a browser emulator) and decoded there,
so the expected values below are what the sites themselves display.
"""

import math
import unittest

from slothtune import designlinks as D

LINEAR = ("https://www.reca.lc/linear?motor=%7B%22name%22%3A%22NEO+Vortex%22%2C%22quantity%22%3A2%7D"
          "&travelDistance=%7B%22s%22%3A48%2C%22u%22%3A%22in%22%7D&spoolDiameter=%7B%22s%22%3A1.75%2C%22u%22%3A%22in%22%7D"
          "&load=%7B%22s%22%3A15%2C%22u%22%3A%22lbs%22%7D&ratio=%7B%22magnitude%22%3A9%2C%22ratioType%22%3A%22Reduction%22%7D"
          "&efficiency=90&statorLimit=%7B%22s%22%3A40%2C%22u%22%3A%22A%22%7D&supplyLimit=%7B%22s%22%3A60%2C%22u%22%3A%22A%22%7D"
          "&supplyVoltage=%7B%22s%22%3A12%2C%22u%22%3A%22V%22%7D&angle=%7B%22s%22%3A90%2C%22u%22%3A%22deg%22%7D"
          "&batteryResistance=%7B%22s%22%3A0.015%2C%22u%22%3A%22Ohm%22%7D&cascade=true&enableCustomMaxVelocity=false"
          "&maxVelocity=%7B%22s%22%3A2%2C%22u%22%3A%22m%2Fs%22%7D")
ARM = ('https://www.reca.lc/arm?motor={"name":"Kraken+X60+(FOC)","quantity":1}&ratio={"magnitude":100,"ratioType":"Reduction"}'
       '&statorLimit={"s":80,"u":"A"}&supplyLimit={"s":60,"u":"A"}&supplyVoltage={"s":12,"u":"V"}&statorVoltage={"s":12,"u":"V"}'
       '&batteryResistance={"s":0.015,"u":"Ohm"}&armLength={"s":24,"u":"in"}&minAngle={"s":0,"u":"deg"}&maxAngle={"s":90,"u":"deg"}'
       '&efficiency=100&load={"s":5,"u":"lbs"}')
OLD_LINEAR = ("https://www.reca.lc/linear?angle=%7B%22s%22%3A90%2C%22u%22%3A%22deg%22%7D&currentLimit=%7B%22s%22%3A40%2C%22u%22%3A%22A%22%7D"
              "&efficiency=100&limitAcceleration=0&motor=%7B%22quantity%22%3A2%2C%22name%22%3A%22NEO%20550*%22%7D"
              "&ratio=%7B%22magnitude%22%3A2%2C%22ratioType%22%3A%22Reduction%22%7D")


class ReCalcTest(unittest.TestCase):
    def test_a_cascade_elevator_from_copy_link(self):
        d = D.parse(LINEAR)
        self.assertEqual((d["source"], d["kind"]), ("ReCalc", "elevator"))
        self.assertEqual(d["motor"], {"name": "NEO Vortex", "key": "vortex", "label": "NEO Vortex", "count": 2})
        self.assertEqual(d["ratio"], 9)
        self.assertAlmostEqual(d["spool_diameter_m"], 1.75 * 0.0254)
        self.assertAlmostEqual(d["travel_m"], 48 * 0.0254)
        self.assertAlmostEqual(d["mass_kg"], 15 * 0.45359237)
        self.assertEqual((d["efficiency"], d["current_limit_a"], d["supply_limit_a"]), (0.9, 40, 60))
        self.assertTrue(d["cascade"])
        self.assertFalse(d["legacy"])

    def test_a_cascade_doubles_the_carriage_speed(self):
        p = D.predicts(D.parse(LINEAR))
        one_stage = 6784 / 60 / 9 * math.pi * 1.75 * 0.0254
        self.assertAlmostEqual(p["free_speed_mps"], 2 * one_stage)

    def test_an_arm_with_raw_json_and_a_motor_that_isnt_revs(self):
        d = D.parse(ARM)
        self.assertEqual(d["kind"], "arm")
        self.assertEqual(d["motor"]["name"], "Kraken X60 (FOC)")
        self.assertIsNone(d["motor"]["key"])
        self.assertEqual((d["ratio"], d["angles_deg"]), (100, [0, 90]))
        self.assertAlmostEqual(d["arm_length_m"], 0.6096)
        self.assertEqual(D.predicts(d), {}, "no REV specs, so nothing is predicted")

    def test_an_old_link_with_old_names_and_a_starred_motor(self):
        d = D.parse(OLD_LINEAR)
        self.assertTrue(d["legacy"])
        self.assertEqual(d["current_limit_a"], 40)
        self.assertEqual((d["motor"]["key"], d["motor"]["count"]), ("neo550", 2))

    def test_a_step_up_and_a_bad_ratio(self):
        d = D.parse('https://reca.lc/flywheel?motor={"name":"NEO","quantity":1}&ratio={"magnitude":2,"ratioType":"Step-up"}'
                    '&shooterDiameter={"s":4,"u":"in"}&shooterTargetSpeed={"s":3000,"u":"rpm"}')
        self.assertEqual((d["kind"], d["ratio"], d["target_rpm"]), ("flywheel", 0.5, 3000))
        self.assertEqual(d["motor"]["key"], "neo")
        d = D.parse('https://www.reca.lc/flywheel?ratio={"magnitude":0,"ratioType":"Reduction"}')
        self.assertIsNone(d["ratio"])

    def test_gearing_pages(self):
        self.assertEqual(D.parse("https://www.reca.lc/ratio?ratioPairs=%5B%5B18%2C72%5D%2C%5B24%2C48%5D%5D")["ratio"], 8)
        self.assertEqual(D.parse('https://www.reca.lc/ratio?ratioPairs={"pairs":[[18,72],[24,48]]}')["ratio"], 8)
        self.assertAlmostEqual(D.parse("https://www.reca.lc/gears?gear1Teeth=16&gear2Teeth=36&gearDP=20")["ratio"], 2.25)

    def test_pages_with_nothing_to_configure(self):
        for url in ("https://www.reca.lc/about", "https://example.com/arm?x=1"):
            with self.assertRaises(ValueError):
                D.parse(url)


class AMBcalcTest(unittest.TestCase):
    def test_a_mechanism_driven_by_its_ratio(self):
        d = D.parse("https://ambcalc.com/mechanism?=&motor=NEO+Vortex&mot_num=2&radius=1.5&load=20&gbx_eff=85&rat-c=%5E&rat=25")
        self.assertEqual((d["source"], d["kind"], d["ratio"], d["efficiency"]), ("AMBcalc", "mechanism", 25, 0.85))
        self.assertEqual((d["motor"]["key"], d["motor"]["count"]), ("vortex", 2))
        self.assertAlmostEqual(d["radius_m"], 1.5 * 0.0254)
        self.assertAlmostEqual(d["load_n"], 20 * 4.448)

    def test_a_mechanism_driven_by_its_loaded_speed_gets_ambcalcs_own_ratio(self):
        # rat=25 is left over in the link; the page solves the ratio from 1.2 m/s loaded and shows 21.99.
        d = D.parse("https://ambcalc.com/mechanism?=&motor=NEO+Vortex&mot_num=2&radius=1.5&load=20&gbx_eff=85"
                    "&rat=25&lin_l-u=1&lin_l-c=%5E&lin_l=1.2")
        self.assertAlmostEqual(d["ratio"], 21.99, places=2)

    def test_a_target_on_a_motor_it_has_no_specs_for_says_so(self):
        d = D.parse("https://ambcalc.com/mechanism?=&rat=25&lin_l-u=1&lin_l-c=%5E&lin_l=1.2")
        self.assertIsNone(d["ratio"])
        self.assertTrue(any("no specs" in n for n in d["notes"]), d["notes"])

    def test_a_drivetrain(self):
        d = D.parse("https://ambcalc.com/drivetrain?=&motor=Kraken+X60+FOC&ilim=60&weight=135&g1a=14&g1b=50&g2a=27&g2b=17"
                    "&g3a=15&g3b=45&dist=20&wheel_diam=101.6&wheel_diam-u=0.001")
        self.assertEqual(d["kind"], "drivetrain")
        self.assertAlmostEqual(d["ratio"], 50 / 14 * 17 / 27 * 45 / 15)
        self.assertAlmostEqual(d["ratio"], 6.75, places=2)  # the page shows 6.75
        self.assertAlmostEqual(d["wheel_diameter_m"], 0.1016)
        self.assertAlmostEqual(d["mass_kg"], 135 * 0.453592)
        self.assertEqual((d["current_limit_a"], d["motor"]["count"]), (60, 4))

    def test_a_titled_startup_page_and_the_old_neo_name(self):
        d = D.parse("https://ambcalc.com/startup?=Wrist&motor=NEO+2.0&mot_num=2&maxI=40&radius=20&mass=8&load=0&sim-ratio=60")
        self.assertEqual((d["title"], d["ratio"], d["current_limit_a"]), ("Wrist", 60, 40))
        self.assertEqual(d["motor"]["key"], "neo2")
        self.assertEqual(D.parse("https://ambcalc.com/mechanism.html?motor=NEO&rat=10")["motor"]["key"], "neo")

    def test_motor_curves_reads_the_first_row(self):
        d = D.parse("https://ambcalc.com/motor_curves?=&num-motors=%5B0%2C1%2C2%5D&motor-type2=NEO+550&mot_maxi1=40&mot_rat2=4")
        self.assertEqual(d["current_limit_a"], 40)
        self.assertIn("compares 2 motors", d["notes"][0])

    def test_describe_says_it_in_words(self):
        rows = dict(D.describe(D.parse(LINEAR)))
        self.assertEqual(rows["Motor"], "2 × NEO Vortex")
        self.assertIn("9:1", rows["Gear ratio"])
        self.assertIn("ft/s", rows["Free speed"])


if __name__ == "__main__":
    unittest.main()
