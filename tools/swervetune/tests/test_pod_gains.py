"""Each pod's own gains: their names and ranges, how they are saved beside the shared ones, and a run
read for one pod alone."""

import unittest

from swervetune import advisor, contract as C, yagslcfg as Y


class Project:
    def __init__(self, pidf=None, tune=None):
        self.data = {"modules/pidfproperties.json": pidf or {"angle": {"p": 0.01, "i": 0, "d": 0, "iz": 0},
                                                              "drive": {"p": 1, "i": 0, "d": 0.4, "iz": 0}},
                     "swervetune.json": tune or {}}


def edits(project, gains):
    return {(f, p): v for f, p, v in Y.edits_for_gains(project, gains)}


class NamesTest(unittest.TestCase):
    def test_a_pods_gain_has_the_shared_ones_range(self):
        self.assertEqual(C.pod_key("frontleft", "Steer", "kP"), "Pod/frontleft/Steer/kP")
        self.assertEqual(C.gain_spec("Pod/frontleft/Steer/kP"), C.GAIN_SPECS["Steer/kP"])
        self.assertEqual(C.gain_spec("FF/backright/kV"), C.FF_SPECS["kV"])
        self.assertIsNone(C.gain_spec("Pod/frontleft/Steer/kQ"))


class SaveTest(unittest.TestCase):
    def test_only_a_pod_that_differs_gets_its_own_entry(self):
        e = edits(Project(), {"Steer/kP": 0.01, "Pod/frontleft/Steer/kP": 0.03, "Pod/frontright/Steer/kP": 0.01})
        self.assertEqual(e[("swervetune.json", ("podGains", "frontleft", "steer", "p"))], 0.03)
        self.assertNotIn(("swervetune.json", ("podGains", "frontright", "steer", "p")), e,
                         "a pod running the shared gains needs no entry")
        self.assertEqual(e[("modules/pidfproperties.json", ("angle", "p"))], 0.01)

    def test_an_old_entry_is_set_back_to_the_shared_value(self):
        p = Project(tune={"podGains": {"backleft": {"drive": {"p": 2.0}}}})
        e = edits(p, {"Drive/kP": 1.5, "Pod/backleft/Drive/kP": 1.5})
        self.assertEqual(e[("swervetune.json", ("podGains", "backleft", "drive", "p"))], 1.5,
                         "or the file would put back an override nobody is running")

    def test_without_the_shared_value_in_hand_the_file_says_it(self):
        e = edits(Project(), {"Pod/frontleft/Drive/kD": 0.4})
        self.assertEqual(e, {}, "equal to pidfproperties.json's drive d")


class PodViewTest(unittest.TestCase):
    RUN = {"test": "steer_step", "robot": {"modules": ["frontleft", "frontright", "backleft", "backright"]},
           "channels": {"t": [0, 1], "m0.sp": [0, 1], "m0.pos": [0, 1], "m1.sp": [0, 2], "m1.pos": [0, 2], "bus": [12, 12]},
           "gains": {"Steer/kP": 0.01, "Pod/frontright/Steer/kP": 0.03, "Pod/frontright/Steer/kD": 0.5}}

    def test_one_pod_with_its_own_gains(self):
        d = advisor.pod_doc(self.RUN, "frontright")
        self.assertEqual(sorted(d["channels"]), ["bus", "m1.pos", "m1.sp", "t"], "its channels and the whole robot's")
        self.assertEqual((d["gains"]["Steer/kP"], d["gains"]["Steer/kD"]), (0.03, 0.5), "the advice starts from its own")
        self.assertEqual(d["pod"], "frontright")
        self.assertEqual(self.RUN["gains"]["Steer/kP"], 0.01, "the run itself is untouched")

    def test_an_unknown_pod_is_the_whole_run(self):
        self.assertIs(advisor.pod_doc(self.RUN, "middle"), self.RUN)


if __name__ == "__main__":
    unittest.main()
