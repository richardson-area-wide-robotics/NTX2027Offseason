"""The Guide's ticks are each robot's own, and only real runs earn them."""

import glob
import os
import tempfile
import threading
import unittest
from unittest import mock

from slothtune import progress


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
        self.assertEqual(progress.load("Peashooter")["runs"]["steer_step/FIELD"],
                         {"score": 60, "file": "b.json", "saved": "x", "limited": False, "needs_truth": False})

    def test_a_run_on_one_module_never_counts(self):
        # The troubleshooter's "pick FL only" must not tick a step for all four modules.
        self.assertFalse(progress.record_run("Peashooter", dict(self.run_doc(), module="FL"), {"score": 100}, "a"))

    def test_hardware_limited_steering_is_recorded(self):
        progress.record_run("Peashooter", self.run_doc(), {"score": 80, "limited": True}, "a.json")
        self.assertTrue(progress.load("Peashooter")["runs"]["steer_step/FIELD"]["limited"])

    def test_a_straight_line_needs_a_ground_truth(self):
        doc = dict(self.run_doc(), test="straight")
        progress.record_run("Peashooter", doc, {"score": 100, "measured": {}}, "a.json")
        self.assertTrue(progress.load("Peashooter")["runs"]["straight/FIELD"]["needs_truth"])
        progress.record_run("Peashooter", doc, {"score": 100, "measured": {"tape_forward_m": 2.0}}, "b.json")
        self.assertFalse(progress.load("Peashooter")["runs"]["straight/FIELD"]["needs_truth"])

    def test_a_person_cannot_write_run_results(self):
        progress.update("Peashooter", {"runs": {"steer_step/FIELD": {"score": 100}}})
        self.assertEqual(progress.load("Peashooter")["runs"], {})

    def test_changes_from_many_threads_all_land(self):
        # The GUI answers on many threads; a read-change-write that isn't locked loses some.
        def bump(p):
            p["n"] = p.get("n", 0) + 1

        def work():
            for _ in range(25):
                progress.change("Peashooter", bump)
        ts = [threading.Thread(target=work) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(progress.load("Peashooter")["n"], 200)
        self.assertEqual(glob.glob(progress.PATH + ".*.tmp"), [], "no temp file left behind")

    def test_reads_and_writes_together_lose_nothing(self):
        # On Windows a file one thread is reading can't be replaced by another: a read outside the
        # lock made a write fail and lost the change (190 of 200 landed).
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                progress.load("Peashooter")

        rs = [threading.Thread(target=reader) for _ in range(3)]
        [t.start() for t in rs]
        try:
            ws = [threading.Thread(target=lambda: [progress.change("Peashooter", lambda p: p.__setitem__("n", p.get("n", 0) + 1))
                                                   for _ in range(25)]) for _ in range(4)]
            [t.start() for t in ws]
            [t.join() for t in ws]
        finally:
            stop.set()
            [t.join() for t in rs]
        self.assertEqual(progress.load("Peashooter")["n"], 100)

    def test_a_file_held_for_a_moment_is_waited_for_never_read_as_empty(self):
        # Another process (the command line, a virus scanner) holding the file must not make a
        # read look empty: the next write would erase every robot's progress.
        progress.update("Black team", {"hand": "pass"})
        real = progress._open_read
        calls = []

        def held_twice():
            calls.append(1)
            if len(calls) <= 2:
                raise PermissionError("held by another process")
            return real()
        with mock.patch.object(progress, "_open_read", held_twice), mock.patch.object(progress, "BUSY_WAIT_S", 0):
            progress.update("Peashooter", {"hand": "pass"})
        self.assertEqual(progress.load("Black team")["hand"], "pass", "the other robot's progress survives")
        self.assertEqual(progress.load("Peashooter")["hand"], "pass")

    def test_a_file_held_too_long_fails_loudly_and_writes_nothing(self):
        progress.update("Black team", {"hand": "pass"})
        with mock.patch.object(progress, "_open_read", side_effect=PermissionError("held")), \
                mock.patch.object(progress, "BUSY_WAIT_S", 0):
            with self.assertRaises(PermissionError):
                progress.update("Peashooter", {"hand": "pass"})
        self.assertEqual(progress.load("Black team")["hand"], "pass")
        self.assertNotIn("hand", progress.load("Peashooter"))

    def test_a_damaged_file_is_set_aside_not_erased(self):
        os.makedirs(os.path.dirname(progress.PATH), exist_ok=True)
        with open(progress.PATH, "w", encoding="utf-8") as fh:
            fh.write('{"Peashooter": {"hand": "pass"')
        progress.update("Black team", {"hand": "pass"})
        kept = glob.glob(progress.PATH + ".unreadable-*")
        self.assertEqual(len(kept), 1, "the damaged file is kept for a person to rescue")
        with open(kept[0], encoding="utf-8") as fh:
            self.assertIn("Peashooter", fh.read())
        self.assertEqual(progress.load("Black team")["hand"], "pass")


if __name__ == "__main__":
    unittest.main()
