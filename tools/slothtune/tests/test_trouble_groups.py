"""Troubleshoot's groups (diagnose.ISSUES, DEVICES, GROUPS): every problem is in at least one group
each way, every group has a problem, and the page gets both."""

import unittest

from slothtune import diagnose as D, server


class GroupsTest(unittest.TestCase):
    def test_every_problem_is_grouped_both_ways(self):
        issues, devices = {g[0] for g in D.ISSUES}, {g[0] for g in D.DEVICES}
        self.assertEqual(set(D.GROUPS), set(D.BY_ID), "a problem with no groups, or groups for no problem")
        for sid, (i, d) in D.GROUPS.items():
            self.assertTrue(i and d, f"{sid} needs a kind and a device")
            self.assertLessEqual(set(i), issues, sid)
            self.assertLessEqual(set(d), devices, sid)
            self.assertEqual(len(i), len(set(i)), sid)
            self.assertEqual(len(d), len(set(d)), sid)

    def test_every_group_has_a_problem(self):
        used_i = {k for i, _ in D.GROUPS.values() for k in i}
        used_d = {k for _, d in D.GROUPS.values() for k in d}
        self.assertEqual(used_i, {g[0] for g in D.ISSUES})
        self.assertEqual(used_d, {g[0] for g in D.DEVICES})

    def test_groups_have_names_and_short_names(self):
        for k, name, short in D.ISSUES + D.DEVICES:
            self.assertTrue(name and short and len(short) <= 20, k)

    def test_a_problem_can_sit_in_several_groups(self):
        self.assertGreater(len(D.groups("motor_dead")["devices"]), 1)
        self.assertGreater(len(D.groups("comms_drops")["issues"]), 1)


class ApiTest(unittest.TestCase):
    def test_the_page_gets_each_problems_groups_and_the_group_names(self):
        r = server.api_symptoms(None)
        self.assertEqual(len(r["symptoms"]), len(D.SYMPTOMS))
        s = next(x for x in r["symptoms"] if x["id"] == "no_comms")
        self.assertEqual((s["issues"], s["devices"]), (["connect"], ["network", "controller"]))
        self.assertEqual([g[0] for g in r["groups"]["issues"]], [g[0] for g in D.ISSUES])
        self.assertEqual(len(r["groups"]["devices"][0]), 3, "key, name, short name")


if __name__ == "__main__":
    unittest.main()
