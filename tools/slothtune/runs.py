"""Saved test runs: one JSON file per run, so any result can be re-analyzed or compared later.

Runs live in ``tools/slothtune/runs/`` (git-ignored: they are data, not code). A run file holds
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
# Where the robot projects are: this repo, unless SLOTHTUNE_ROBOT_REPO says otherwise.
from .robotrepo import ROBOTS  # noqa: E402


# Ledgers that aren't runs live apart, so nothing reading runs/*.json mistakes one for a run.
DATA = os.path.join(RUNS, "data")


def _is_run(d):
    return isinstance(d, dict) and bool(d.get("test"))


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


# A run's summary, by file and its modification time: a run's file carries every sample, and the
# checklists and the Runs tab list hundreds of them on every request.
_SUMMARIES = {}


def _summary(f):
    try:
        st = os.stat(f)
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    hit = _SUMMARIES.get(f)
    if hit and hit[0] == key:
        return hit[1]
    try:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    s = None
    if _is_run(d):
        rep = d.get("report") or {}
        s = {"file": os.path.basename(f), "test": d.get("test"), "module": d.get("module"),
             "env": d.get("env"), "outcome": d.get("outcome"), "saved": d.get("saved"),
             "practice": d.get("practice", False), "score": rep.get("score"),
             "cost": rep.get("cost"), "summary": rep.get("summary"),
             "robot": (d.get("robot") or {}).get("name"), "gains": d.get("gains") or {}}
        if str(d.get("test") or "").startswith("system_"):
            # Which mechanism, and how fast or how far it went: the Systems walkthrough reads these.
            m = next((re.match(r"system: (.+) \((\w*)", n) for n in d.get("notes") or [] if str(n).startswith("system: ")), None)
            meta = d.get("meta") or {}
            s.update(system=m.group(1) if m else None, message=d.get("message"),
                     vmax=meta.get("vmax"), min=meta.get("min"), max=meta.get("max"))
    _SUMMARIES[f] = (key, s)
    return s


def list_runs(limit=50):
    files = sorted(glob.glob(os.path.join(RUNS, "*.json")), reverse=True)[:limit]
    return [dict(s) for s in map(_summary, files) if s]


LEDGER = os.path.join(DATA, "batteries.json")


def battery_ledger():
    """Battery measurements from match logs: ``{key: {"when", "id", "fit", "source"}}``."""
    try:
        with open(LEDGER, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def battery_ledger_add(key, when, battery_id, fit, source):
    """Keeps one match log's battery measurement, once per log (``key`` names the log)."""
    if not battery_id or not fit:
        return False
    led = battery_ledger()
    led[key] = {"when": when, "id": battery_id, "fit": fit, "source": source}
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(led, fh, indent=1)
    os.replace(tmp, LEDGER)
    return True


CONTROLLER_LOG = os.path.join(DATA, "controllers.json")


def controller_log():
    """Every joystick check saved, oldest first."""
    try:
        with open(CONTROLLER_LOG, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def controller_log_add(entry):
    log = controller_log()
    log.append(entry)
    os.makedirs(os.path.dirname(CONTROLLER_LOG), exist_ok=True)
    tmp = CONTROLLER_LOG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(log[-1000:], fh, indent=1)
    os.replace(tmp, CONTROLLER_LOG)


def ff_history(robot, blocks, before=None, exclude=None, limit=200, env=None):
    """Earlier drive_ff fits for one robot, oldest first: ``[{"saved", "modules"}]``.

    Only runs in the same place (blocks or floor: a free wheel's kV is not a loaded one's; and with
    ``env``, exactly that environment, so the simulator's runs never stand in for the robot's), not
    practice runs, and only those saved before ``before`` so re-analyzing an old run never compares
    it with its own future.
    """
    out = []
    # The newest `limit` matching runs, not the newest `limit` files of any kind: practice runs and
    # other tests used to push a robot's baseline out of the window.
    named = re.compile(r"^\d{8}-\d{6}_")  # how save() names a run: the test is in the name
    files = [f for f in sorted(glob.glob(os.path.join(RUNS, "*.json")))
             if "_drive_ff_" in os.path.basename(f) or not named.match(os.path.basename(f))]
    for f in reversed(files):
        if len(out) >= limit:
            break
        if exclude and os.path.basename(f) == exclude:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if not _is_run(d):
            continue
        rep = d.get("report") or {}
        if (d.get("test") != "drive_ff" or d.get("practice") or not rep.get("modules")
                or (d.get("robot") or {}).get("name") != robot
                or (d.get("env") == "BLOCKS") != bool(blocks)
                or (env and d.get("env") != env)
                or (before and str(d.get("saved", "")) >= str(before))):
            continue
        out.append({"saved": d.get("saved"), "modules": rep["modules"]})
    return out[::-1]
