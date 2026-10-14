"""The robot's design file (design.py): what it catches in itself, where the code disagrees with
it, a draft from the code, and a spreadsheet import."""

import copy
import os
import unittest

from slothtune import design as D, yagslcfg as Y

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def motor(name, typ="sparkflex_vortex", cid=10, bus="rio", **kw):
    m = {"name": name, "subsystem": "Shooter", "motor": {"type": typ, "id": cid, "canbus": bus},
         "pdh": {"port": None, "breaker": None}}
    m.update(kw)
    return m


def design(motors, sensors=(), controller="roborio2", buses=({"name": "rio", "color": "yellow"},)):
    return {"version": 1, "robot": "Test", "controller": controller, "canBuses": list(buses),
            "motors": list(motors), "sensors": list(sensors)}


def titles(F, level=None):
    return [f["title"] for f in F if level is None or f["level"] == level]


class DesignCheckTest(unittest.TestCase):
    def test_a_good_file_has_nothing_to_say(self):
        d = design([motor("Shooter leader", cid=10, gearRatio=1.0, shaft="shooter"),
                    motor("Shooter follower", cid=11, gearRatio=1.0, shaft="shooter",
                          follows={"leader": "Shooter leader", "inverted": True})],
                   [{"name": "Beam break", "type": "digital", "port": 0}])
        self.assertEqual(D.check(d), [])

    def test_two_rev_controllers_on_one_id_and_bus(self):
        F = D.check(design([motor("A", "sparkmax_neo", 10), motor("B", "sparkflex_vortex", 10)]))
        self.assertTrue(any("both use CAN ID 10" in t for t in titles(F, "error")), "a MAX and a Flex share REV's ID space")
        F = D.check(design([motor("A", cid=10), motor("B", cid=10, bus="b2")], controller="systemcore",
                           buses=({"name": "rio", "color": "yellow"}, {"name": "b2", "color": "orange"})))
        self.assertFalse(any("both use" in t for t in titles(F)), "the same ID on another bus is fine")

    def test_bus_colors_are_ctre_cable_colors_one_each(self):
        F = D.check(design([motor("A")], controller="systemcore",
                           buses=({"name": "rio", "color": "yellow"}, {"name": "b2", "color": "yellow"}, {"name": "b3", "color": "red"})))
        self.assertTrue(any("both yellow" in t for t in titles(F, "error")))
        self.assertTrue(any("'red' is not a CAN cable color" in t for t in titles(F, "error")))
        F = D.check(design([motor("A")], buses=({"name": "rio", "color": "yellow"}, {"name": "b2", "color": "orange"})))
        self.assertTrue(any("2 CAN buses on a roboRIO" in t for t in titles(F, "warn")))

    def test_a_shared_shaft_needs_two_motors_and_their_ratios(self):
        F = D.check(design([motor("A", shaft="roller")]))
        self.assertTrue(any("has one motor" in t for t in titles(F, "warn")))
        self.assertTrue(any("no gear ratio" in t for t in titles(F, "error")), "the shaft test compares speeds by ratio")

    def test_pdh_ports_and_breakers(self):
        F = D.check(design([motor("A", cid=1, pdh={"port": 3, "breaker": 40}), motor("B", cid=2, pdh={"port": 3, "breaker": 40}),
                            motor("C", cid=3, pdh={"port": 21, "breaker": 20}), motor("D", cid=4, pdh={"port": 24, "breaker": 40})]))
        E = titles(F, "error")
        self.assertTrue(any("both on PDH port 3" in t for t in E))
        self.assertTrue(any("20 A breaker on PDH port 21" in t for t in E), "ports 20-23 take 15 A at most")
        self.assertTrue(any("PDH port 24 out of range" in t for t in E))

    def test_sensor_ports(self):
        F = D.check(design([], [{"name": "S1", "type": "digital", "port": 0}, {"name": "S2", "type": "dutycycle", "port": 0},
                                {"name": "S3", "type": "analog", "port": 9}, {"name": "S4", "type": "lidar", "port": 1}]))
        E = titles(F, "error")
        self.assertTrue(any("share DIO port 0" in t for t in E), "a digital input and a duty-cycle encoder both use DIO 0")
        self.assertTrue(any("analog port 9 doesn't exist on a roboRIO" in t for t in E))
        self.assertTrue(any("sensor type 'lidar'" in t for t in E))
        F = D.check(design([], [{"name": "S3", "type": "analog", "port": 9}], controller="systemcore"))
        self.assertEqual(F, [], "SystemCore's ports are its own: not checked against the roboRIO's")

    def test_types_are_written_as_yagsl_does(self):
        self.assertEqual(D.split_type("sparkflex_vortex"), ("sparkflex", "vortex"))
        self.assertEqual(D.split_type("sparkmax_neo2"), ("sparkmax", "neo2"))
        F = D.check(design([motor("A", "SparkFlex Vortex")]))
        self.assertTrue(any("not a controller_motor pair" in t for t in titles(F, "error")))


class DesignAgainstCodeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = Y.Project(os.path.join(REPO, "Peashooter"))
        cls.draft = D.from_code(cls.p)

    def test_a_draft_from_the_code_names_every_motor(self):
        names = {m["name"] for m in self.draft["motors"]}
        self.assertEqual(len(names), 15)
        self.assertIn("Spindexter", names)
        fl = next(m for m in self.draft["motors"] if m["name"] == "frontleft drive")
        self.assertEqual((fl["motor"]["type"], fl["motor"]["id"], fl["gearRatio"]), ("sparkflex_vortex", 5, 5.5), "from YAGSL's files")
        self.assertIsNone(fl["pdh"]["breaker"], "the breaker is the electrical team's to say, never guessed")

    def test_a_leader_and_its_follower_are_drafted_on_one_shaft(self):
        by = {m["name"]: m for m in self.draft["motors"]}
        self.assertEqual(by["Shooter leader"]["shaft"], by["Shooter follower"]["shaft"])
        self.assertEqual(by["Shooter follower"]["follows"], {"leader": "Shooter leader", "inverted": True})

    def test_the_code_matches_its_own_draft(self):
        self.assertEqual(D.compare(self.p, self.draft), [])

    def test_the_code_disagreeing_with_the_design(self):
        d = copy.deepcopy(self.draft)
        by = {m["name"]: m for m in d["motors"]}
        by["Tower"]["motor"]["id"] = 19
        by["Shooter follower"]["follows"]["inverted"] = False
        by["Spindexter"]["motor"]["type"] = "sparkflex_vortex"
        d["motors"] = [m for m in d["motors"] if m["name"] != "Intake pivot"]
        d["motors"].append(motor("Climber", cid=30))
        F = D.compare(self.p, d)
        E, W = titles(F, "error"), titles(F, "warn")
        self.assertTrue(any("Tower: CAN ID 19 in the design, 18 in the code" in t for t in E))
        self.assertTrue(any("Shooter follower: follows" in t for t in E), "a follower set the wrong way fights its leader")
        self.assertTrue(any("Spindexter: a SPARK Flex in the design, the code creates a SPARK MAX" in t for t in E))
        self.assertTrue(any("Intake pivot: in the code" in t for t in W))
        self.assertTrue(any("Climber: not in the code" in t for t in E))


class DesignImportTest(unittest.TestCase):
    CSV = ("name,subsystem,kind,type,id,canbus,pdh_port,breaker,inverted,idle,current_limit,gear_ratio,positive,shaft,follows,follows_inverted,port,means\n"
           "Shooter leader,Shooter,motor,sparkflex_vortex,10,rio,4,40,no,coast,80,1,throws out,shooter,,,,\n"
           "Shooter follower,Shooter,motor,sparkflex_vortex,11,rio,5,40,,coast,80,1,throws out,shooter,Shooter leader,yes,,\n"
           "Beam break,Intake,digital,,,,,,,,,,,,,,0,a game piece is in\n"
           "Arm encoder,Arm,encoder,,,,,,,,,,,,,,\"1, 2\",\n")

    def test_buses_have_their_own_names_and_colors(self):
        csv = self.CSV + "".join(r + chr(10) for r in ("rio,Drive train,bus,yellow,,,,,,,,,,,,,,",
                                                         "mech,Intake,bus,orange,,,,,,,,,,,,,,"))
        d = D.from_csv(csv, controller="systemcore")
        self.assertEqual(d["canBuses"], [{"name": "rio", "label": "Drive train", "color": "yellow"},
                                         {"name": "mech", "label": "Intake", "color": "orange"}])
        d["canBuses"][1]["label"] = "drive train"
        self.assertTrue(any("both called" in t for t in titles(D.check(d), "warn")))

    def test_a_spreadsheet_becomes_a_design_file(self):
        d = D.from_csv(self.CSV, robot="Test")
        self.assertEqual(len(d["motors"]), 2)
        f = d["motors"][1]
        self.assertEqual(f["follows"], {"leader": "Shooter leader", "inverted": True})
        self.assertEqual((f["pdh"], f["idleMode"], f["currentLimit"], f["gearRatio"]), ({"port": 5, "breaker": 40}, "coast", 80, 1.0))
        self.assertEqual([s["port"] for s in d["sensors"]], [0, [1, 2]])
        self.assertEqual(D.check(d), [])


class CodeParsingTest(unittest.TestCase):
    def test_config_chains_reach_their_motor(self):
        src = """
        SparkFlex a = new SparkFlex(10, MotorType.kBrushless);
        SparkFlex b = new SparkFlex(11, MotorType.kBrushless);
        SparkFlexConfig ca = new SparkFlexConfig();
        ca.idleMode(IdleMode.kBrake).smartCurrentLimit(60);
        ca.inverted(true);
        SparkFlexConfig cb = new SparkFlexConfig();
        cb.follow(a, true).idleMode(IdleMode.kCoast);
        a.configure(ca, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
        b.configure(cb, ResetMode.kResetSafeParameters, PersistMode.kPersistParameters);
        """
        c = D._configs(src)
        self.assertEqual(c["a"], {"follows": None, "inverted": True, "idle": "brake", "limit": 60})
        self.assertEqual(c["b"]["follows"], ("a", True))
        self.assertEqual(c["b"]["idle"], "coast")

    def test_roborio_ports_in_the_code(self):
        class P:
            java = {"src/main/java/frc/robot/Intake.java": "static final int BEAM = 3;\nDigitalInput beam = new DigitalInput(BEAM);\n"
                                                          "Encoder e = new Encoder(4, 5);\nDutyCycleEncoder arm = new DutyCycleEncoder(6);\n"}
        got = D.code_ports(P)
        self.assertEqual([(p["class"], p["kind"], p["ports"]) for p in got],
                         [("DigitalInput", "digital", [3]), ("Encoder", "encoder", [4, 5]), ("DutyCycleEncoder", "dutycycle", [6])])


if __name__ == "__main__":
    unittest.main()
