"""Saved test runs: one JSON file per run, so any result can be re-analyzed or compared later.

Runs live in ``tools/swervetune/runs/`` (git-ignored: they are data, not code). A run file holds
the raw channels, the gains in effect when it ran, and the analysis report at the time - re-running
the analysis later with a newer advisor is always possible from the channels.
"""

from __future__ import annotations

import glob
import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
REPO = os.path.dirname(os.path.dirname(HERE))


def _slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", str(s)).strip("-").lower() or "x"


def save(result_json, report=None, gains=None, practice=False):
    os.makedirs(RUNS, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    robot = (result_json.get("robot") or {}).get("name") or ("practice" if practice else "robot")
    name = f"{stamp}_{_slug(robot)}_{result_json.get('test')}_{_slug(result_json.get('module', 'all'))}.json"
    doc = dict(result_json)
    doc["gains"] = gains or doc.get("gains") or {}
    doc["report"] = report
    doc["practice"] = practice or doc.get("practice", False)
    doc["saved"] = stamp
    path = os.path.join(RUNS, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    return path


def load(path_or_name):
    path = path_or_name if os.path.exists(path_or_name) else os.path.join(RUNS, path_or_name)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["_file"] = os.path.basename(path)
    return doc


def list_runs(limit=50):
    files = sorted(glob.glob(os.path.join(RUNS, "*.json")), reverse=True)[:limit]
    out = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        rep = d.get("report") or {}
        out.append({"file": os.path.basename(f), "test": d.get("test"), "module": d.get("module"),
                    "env": d.get("env"), "outcome": d.get("outcome"), "saved": d.get("saved"),
                    "practice": d.get("practice", False), "score": rep.get("score"),
                    "cost": rep.get("cost"), "summary": rep.get("summary"),
                    "robot": (d.get("robot") or {}).get("name")})
    return out


def ff_history(robot, blocks, before=None, exclude=None, limit=200, env=None):
    """Earlier drive_ff fits for one robot, oldest first: ``[{"saved", "modules"}]``.

    Only runs in the same place (blocks or floor: a free wheel's kV is not a loaded one's; and with
    ``env``, exactly that environment, so the simulator's runs never stand in for the robot's), not
    practice runs, and only those saved before ``before`` so re-analyzing an old run never compares
    it with its own future.
    """
    out = []
    for f in sorted(glob.glob(os.path.join(RUNS, "*.json")))[-limit:]:
        if exclude and os.path.basename(f) == exclude:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        rep = d.get("report") or {}
        if (d.get("test") != "drive_ff" or d.get("practice") or not rep.get("modules")
                or (d.get("robot") or {}).get("name") != robot
                or (d.get("env") == "BLOCKS") != bool(blocks)
                or (env and d.get("env") != env)
                or (before and str(d.get("saved", "")) >= str(before))):
            continue
        out.append({"saved": d.get("saved"), "modules": rep["modules"]})
    return out
