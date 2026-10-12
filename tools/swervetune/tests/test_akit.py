"""AdvantageScope and SysId: exported runs read back in WPILib's own format, and the generated
layouts point at the keys the robot's AdvantageKit logging really records."""

import os
import re
import tempfile
import unittest

from swervetune import akit, plant, yagslcfg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
JAVA = os.path.join(REPO, "common", "swervetune", "java", "frc", "lib", "swervetune", "AkLogging.java")


def read_log(path):
    from wpiutil.log import DataLogReader
    starts, values = {}, {}
    for rec in DataLogReader(path):
        if rec.isStart():
            d = rec.getStartData()
            starts[d.entry] = (d.name, d.type, d.metadata)
        elif not rec.isControl():
            name, kind, _ = starts[rec.getEntry()]
            values.setdefault(name, []).append(rec.getString() if kind == "string" else rec.getDouble())
    return {n: (t, m) for n, t, m in starts.values()}, values


try:
    import wpiutil  # noqa: F401 - comes with pyntcore
    HAVE_WPIUTIL = True
except ImportError:  # pragma: no cover
    HAVE_WPIUTIL = False


@unittest.skipUnless(HAVE_WPIUTIL, "needs robotpy-wpiutil (pip install pyntcore)")
class ExportTest(unittest.TestCase):
    def test_a_feedforward_run_reads_back_as_sysid_data(self):
        ch = plant.drive_ff(surface="floor", quasi_s=3, max_v=4, modules=2)
        doc = {"test": "drive_ff", "channels": ch, "meta": {"kv_nominal": 2.9}, "notes": ["practice"],
               "robot": {"modules": ["frontleft", "frontright"]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ff.wpilog")
            akit.export_run(doc, path)
            entries, values = read_log(path)
        self.assertEqual(entries["voltage-frontleft-drive"], ("double", "Volt"))
        self.assertEqual(entries["position-frontright-drive"], ("double", "Meter"))
        self.assertEqual(entries["velocity-frontleft-drive"], ("double", "Meter per Second"))
        self.assertEqual(len(values["voltage-frontleft-drive"]), len(ch["t"]))
        self.assertEqual(values["sysid-test-state-drive"],
                         ["none", "quasistatic-forward", "none", "quasistatic-reverse", "none",
                          "dynamic-forward", "none", "dynamic-reverse", "none"])
        self.assertIn("/SwerveTune/drive_ff/m0.volts", entries)
        self.assertEqual(values["/SwerveTune/drive_ff/meta/kv_nominal"], [2.9])

    def test_other_runs_have_no_sysid_entries(self):
        ch = plant.steer_step([45, 0])
        doc = {"test": "steer_step", "channels": ch, "robot": {"modules": ["frontleft"]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.wpilog")
            akit.export_run(doc, path)
            entries, _ = read_log(path)
        self.assertFalse(any(n.startswith("sysid") or n.startswith("voltage-") for n in entries))


class LayoutTest(unittest.TestCase):
    def test_layouts_use_keys_the_robot_records(self):
        src = open(JAVA, encoding="utf-8").read()
        recorded = set(re.findall(r'Logger\.recordOutput\("([^"]+)"', src))
        recorded |= {"Motors/" + suffix for suffix in re.findall(r'b \+ "(\w+)"', src)}
        for d in yagslcfg.find_projects(REPO):
            lay = akit.layout(yagslcfg.Project(d))
            self.assertEqual(lay["version"], "26.0.0")
            tabs = lay["hubs"][0]["state"]["tabs"]["tabs"]
            self.assertEqual(tabs[1]["type"], 9, "the Swerve tab")
            keys = []
            for t in tabs:
                c = t.get("controller") or {}
                for group in ("sources", "leftSources", "rightSources", "discreteSources"):
                    keys += [s["logKey"] for s in c.get(group, [])]
            for k in keys:
                if k.startswith("/RealOutputs/"):
                    rest = k[len("/RealOutputs/"):]
                    if rest.startswith("Motors/"):
                        self.assertIn("Motors/" + rest.rsplit("/", 1)[1], recorded, k)
                    elif rest.endswith("/rotation"):
                        self.assertIn(rest[:-len("/rotation")], recorded, k)
                    else:
                        self.assertIn(rest, recorded, k)

    def test_mechanism_motors_are_found_in_robot_code(self):
        pea = yagslcfg.Project(os.path.join(REPO, "Peashooter"))
        self.assertIn("Spindexter", akit.mechanism_motors(pea))
        self.assertIn("Shooter leader", akit.mechanism_motors(pea))


if __name__ == "__main__":
    unittest.main()
