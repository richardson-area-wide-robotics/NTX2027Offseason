"""Can this laptop reach the robot and the internet (Claude, over a VPN) at the same time?

The shop setup: the laptop's own Wi-Fi on the school network with the VPN on it for Claude, and a
second (USB) Wi-Fi adapter on the robot's radio. The checks live in ``tools/robot_preflight.ps1``
(Windows' routing table, interface metrics and adapters are only reachable from PowerShell); this
runs it with ``-Json`` and hands its findings to the GUI and the command line. Nothing here changes
a setting: the one fix (the robot adapter's metric) needs the script run as Administrator with -Fix.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "robot_preflight.ps1")


def fix_command(team):
    """What to run, as Administrator, to keep the robot adapter off the internet."""
    return f'powershell -ExecutionPolicy Bypass -File "{SCRIPT}" -Team {int(team)} -Fix'


def _shell():
    # Windows PowerShell 5.1 is on every Windows laptop; PowerShell 7 only if someone installed it.
    return shutil.which("powershell") or shutil.which("pwsh")


def run(team, robot_adapter=None, timeout=60, runner=subprocess.run, year=None, robot=None, accepted=()):
    """``{"ok", "checks": [{"id", "group", "level", "title", "why"}], "robot_adapter", "internet_adapter",
    "vpn", "fix"}``, or ``{"ok": False, "error"}`` when it can't run (not Windows, no PowerShell).

    The script's routing checks, then :mod:`station`'s from the facts it read: the Driver Station
    (against the robot code's ``year``), this laptop's addresses, the firewall and the radios. With
    ``robot`` (``{"image", "wpilib"}`` from the connected robot) and the images GradleRIO
    ``accepted``, the robot's own versions too."""
    if sys.platform != "win32" and runner is subprocess.run:
        return {"ok": False, "error": "The network check runs on Windows, where the Driver Station runs."}
    shell = _shell() if runner is subprocess.run else "powershell"
    if not shell:
        return {"ok": False, "error": "PowerShell isn't on this laptop's PATH."}
    cmd = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT, "-Team", str(int(team)), "-Json"]
    if robot_adapter:
        cmd += ["-RobotAdapter", robot_adapter]
    try:
        p = runner(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": f"Couldn't run the network check: {e}"}
    try:
        out = json.loads(p.stdout)
    except ValueError:
        return {"ok": False, "error": "The network check printed no result: " + (p.stderr or p.stdout or "").strip()[:300]}
    checks = out.get("checks") or []
    if isinstance(checks, dict):  # PowerShell writes a one-item list as the item
        checks = [checks]
    out["checks"] = checks
    from . import station
    out["checks"] = station.checks(out, team, year, robot, accepted)
    out["ok"] = not any(c.get("level") == "fail" for c in out["checks"])
    out["fix"] = fix_command(team) if any(c.get("id") == "robot-metric" and c.get("level") in ("fail", "warn")
                                          for c in checks) else None
    return out
