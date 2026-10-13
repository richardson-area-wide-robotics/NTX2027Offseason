"""The network check: the script's JSON, read the same way however PowerShell writes it."""

import json
import subprocess
import unittest

from swervetune import netcheck as N


def runner(payload, code=0, stderr=""):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, code, stdout=payload if isinstance(payload, str) else json.dumps(payload),
                                           stderr=stderr)
    run.calls = calls
    return run


class NetcheckTest(unittest.TestCase):
    def test_the_scripts_findings_come_through(self):
        r = runner({"ok": True, "team": 1745, "robot_adapter": "Wi-Fi 2", "internet_adapter": "Wi-Fi",
                    "vpn": "UID-VPN-71", "checks": [{"id": "claude", "level": "ok", "title": "Claude reachable", "why": "x"}]})
        out = N.run(1745, runner=r)
        self.assertTrue(out["ok"])
        self.assertEqual(out["checks"][0]["id"], "claude")
        self.assertIsNone(out["fix"])
        self.assertEqual(r.calls[0][-3:], ["-Team", "1745", "-Json"])

    def test_one_check_written_as_an_object_is_still_a_list(self):
        out = N.run(9990, runner=runner({"ok": False, "checks": {"id": "internet", "level": "fail", "title": "t", "why": "w"}}))
        self.assertEqual([c["id"] for c in out["checks"]], ["internet"])

    def test_a_robot_adapter_that_could_take_the_internet_gets_the_admin_command(self):
        out = N.run(9990, "Wi-Fi 2", runner=runner({"ok": False, "checks": [
            {"id": "robot-metric", "level": "fail", "title": "The internet can go to the robot's radio", "why": "w"}]}))
        self.assertIn("-Team 9990 -Fix", out["fix"])

    def test_no_json_is_an_error_not_a_crash(self):
        out = N.run(1745, runner=runner("Set-NetIPInterface : Access denied", stderr="boom"))
        self.assertFalse(out["ok"])
        self.assertIn("printed no result", out["error"])

    def test_the_command_line_has_it(self):
        from swervetune import cli
        a = cli.build_parser().parse_args(["netcheck", "--team", "9990", "--adapter", "Wi-Fi 2"])
        self.assertEqual((a.team, a.adapter), (9990, "Wi-Fi 2"))

    def test_the_script_stays_ascii_for_windows_powershell(self):
        # Windows PowerShell 5.1 reads a UTF-8 file without a byte-order mark as the local code page:
        # one em dash and the script no longer parses (the version before this one didn't).
        with open(N.SCRIPT, "rb") as fh:
            data = fh.read()
        bad = [i for i, b in enumerate(data) if b > 127]
        self.assertEqual(bad[:5], [], "non-ASCII bytes in robot_preflight.ps1")
