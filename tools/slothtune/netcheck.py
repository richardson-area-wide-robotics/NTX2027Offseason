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
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "robot_preflight.ps1")
# Saved checks, to send to whoever is helping: this laptop's network details, so never committed.
REPORTS = os.path.join(HERE, "reports")
_SECRET = re.compile(r"(?i)(key|pass\w*|psk|sae)\s*[:=]?\s*\S+")


def fix_command(team):
    """What to run, as Administrator, to keep the robot adapter off the internet."""
    return f'powershell -ExecutionPolicy Bypass -File "{SCRIPT}" -Team {int(team)} -Fix'


def _shell():
    # Windows PowerShell 5.1 is on every Windows laptop; PowerShell 7 only if someone installed it.
    return shutil.which("powershell") or shutil.which("pwsh")


def run(team, robot_adapter=None, timeout=60, runner=subprocess.run, year=None, robot=None, accepted=(), ds_log=None,
        versions=None):
    """``{"ok", "checks": [{"id", "group", "level", "title", "why"}], "robot_adapter", "internet_adapter",
    "vpn", "fix"}``, or ``{"ok": False, "error"}`` when it can't run (not Windows, no PowerShell).

    The script's routing checks, then :mod:`station`'s from the facts it read: the Driver Station
    (against the robot code's ``year``), this laptop's addresses, the firewall and the radios. With
    ``robot`` (``{"image", "wpilib"}`` from the connected robot) and the images GradleRIO
    ``accepted``, the robot's own versions too; with ``ds_log``, what the Driver Station's newest
    session recorded of the link (:mod:`dslog`)."""
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
    out["checks"] = station.checks(out, team, year, robot, accepted, ds_log, versions)
    out["ds_log"] = ds_log
    out["ok"] = not any(c.get("level") == "fail" for c in out["checks"])
    out["fix"] = fix_command(team) if any(c.get("id") == "robot-metric" and c.get("level") in ("fail", "warn")
                                          for c in checks) else None
    return out


def save(result, robot, team, folder=None):
    """Writes a network check to ``reports/netcheck-<robot>-<time>.json`` and returns its path:
    every check, and the facts it read (no passwords: the radio's page is cut to its firmware line,
    and anything there that looks like a key is hidden again here)."""
    folder = folder or REPORTS
    os.makedirs(folder, exist_ok=True)
    now = time.time()
    local = time.strftime("%Y-%m-%d %I:%M %p", time.localtime(now)).replace(" 0", " ")
    zone = time.strftime("%Z", time.localtime(now))
    utc = time.strftime("%H:%M", time.gmtime(now))
    facts = json.loads(json.dumps((result or {}).get("facts") or {}))
    if facts.get("radio_page"):
        facts["radio_page"] = _SECRET.sub(lambda m: m.group(1) + " [hidden]", facts["radio_page"])
    doc = {"robot": robot, "team": team, "saved": f"{local} {zone} ({utc} UTC)", "ok": (result or {}).get("ok"),
           "checks": (result or {}).get("checks") or [], "facts": facts}
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(robot or "robot")).strip("-").lower() or "robot"
    path = os.path.join(folder, f"netcheck-{slug}-{time.strftime('%Y%m%d-%H%M%S', time.localtime(now))}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    return path
