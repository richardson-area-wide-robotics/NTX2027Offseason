"""The Guide's ticks are each robot's own, and only real runs earn them."""

import os
import tempfile
import unittest
from unittest import mock

from swervetune import progress


class ProgressTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        p = mock.patch.object(progress, "PATH", os.path.join(self.dir.name, "data", "guide_progress.json"))
        p.start()
        self.addCleanup(p.stop)

    def run_doc(self, **kw):
        d = {"test": "steer_step", "env": "FIELD", "outcome": "DONE", "practice": False, "saved": "x"}
        d.update(kw)
        return d

    def test_each_robot_keeps_its_own_marks(self):
        progress.update("Black team", {"hand": "pass"})
        self.assertEqual(progress.load("Black team")["hand"], "pass")
        self.assertNotIn("hand", progress.load("Peashooter"))

    def test_a_real_run_is_recorded_under_its_test_and_place(self):
        self.assertTrue(progress.record_run("Peashooter", self.run_doc(), {"score": 100}, "a.json"))
        self.assertEqual(progress.load("Peashooter")["runs"]["steer_step/FIELD"]["score"], 100)
        self.assertEqual(progress.load("Black team")["runs"], {})

    def test_the_simulator_and_the_practice_pod_never_count(self):
        for doc in (self.run_doc(env="SIM"), self.run_doc(practice=True), self.run_doc(env="UNSET")):
            self.assertFalse(progress.record_run("Peashooter", doc, {"score": 100}, "a.json"), doc)
        self.assertEqual(progress.load("Peashooter")["runs"], {})

    def test_a_stopped_run_never_counts(self):
        self.assertFalse(progress.record_run("Peashooter", self.run_doc(outcome="ABORTED"), {"score": None}, "a"))

    def test_the_newest_result_replaces_the_last(self):
        progress.record_run("Peashooter", self.run_doc(), {"score": 100}, "a.json")
        progress.record_run("Peashooter", self.run_doc(), {"score": 60}, "b.json")
        self.assertEqual(progress.load("Peashooter")["runs"]["steer_step/FIELD"], {"score": 60, "file": "b.json", "saved": "x"})

    def test_a_person_cannot_write_run_results(self):
        progress.update("Peashooter", {"runs": {"steer_step/FIELD": {"score": 100}}})
        self.assertEqual(progress.load("Peashooter")["runs"], {})


if __name__ == "__main__":
    unittest.main()
