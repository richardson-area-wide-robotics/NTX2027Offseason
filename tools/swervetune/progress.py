"""The Guide's progress, kept for each robot.

Each robot code project (Black team, Peashooter) has its own record:

* what a person marked done: the hand check, the offsets, the measurements, the commit;
* the newest real run of each Guide test with its score, recorded the moment the run is saved,
  so a step stays done however many runs come after it.

Only runs on the real robot count. The simulator's sensors are perfect and the practice pod is a
model, so neither may tick a step that is about the robot, and a run stopped part-way has no
score to count.
"""

from __future__ import annotations

import json
import os

from . import runs

PATH = os.path.join(runs.DATA, "guide_progress.json")

# Where each Guide test can count. A steering run on blocks and one on the floor are different
# steps; anything else (the simulator, an environment never set) is not a Guide result.
REAL_ENVS = ("BLOCKS", "FIELD")


def _read():
    try:
        with open(PATH, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _write(d):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1)
    os.replace(tmp, PATH)


def load(robot):
    """One robot's progress: the marks a person set, plus ``runs`` keyed ``"<test>/<env>"``."""
    if not robot:
        return {}
    p = _read().get(robot) or {}
    p.setdefault("runs", {})
    return p


def update(robot, changes):
    """Merges a person's marks into one robot's progress. Run results are never set this way."""
    if not robot:
        return {}
    d = _read()
    p = d.setdefault(robot, {})
    for k, v in (changes or {}).items():
        if k != "runs":
            p[k] = v
    _write(d)
    return load(robot)


def counts(doc):
    """Whether a saved run is a real-robot result the Guide may count, and under which key."""
    if doc.get("practice") or doc.get("outcome") != "DONE":
        return None
    env, test = doc.get("env"), doc.get("test")
    if env not in REAL_ENVS or not test or test == "capture":
        # Captures are the Guide's own (health, hand check, offsets) and it records those itself.
        return None
    return f"{test}/{env}"


def record_run(robot, doc, report, file):
    """Keeps the newest real result of a Guide test for this robot."""
    key = counts(doc)
    if not robot or not key:
        return False
    d = _read()
    p = d.setdefault(robot, {})
    p.setdefault("runs", {})[key] = {"score": (report or {}).get("score"), "file": file,
                                     "saved": doc.get("saved") or doc.get("started")}
    _write(d)
    return True
