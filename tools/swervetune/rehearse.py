"""Rehearses the tuning loop against the practice pod: test, read the advice, apply it, repeat.

This is exactly the loop an AI agent (or a student) runs on the real robot, run offline against
the model in :mod:`plant`. Two uses:

* an agent can check its strategy converges before it spends battery and floor time;
* the tests use it to prove the advisor itself converges, rather than oscillating between two
  suggestions or walking a gain off to zero.

It follows only the advisor's single ``next`` action each round, applies gain changes, and runs
``drive_ff`` when told to - the same rules the agent brief in docs/AGENT_TUNING.md gives.
"""

from __future__ import annotations

from . import advisor, plant

STEER_PATTERN = [10, 0, -10, 0, 45, 0, -45, 0, 90, 0, -90, 0]
DRIVE_PATTERN = [0.5, 1.0, 0, -0.5, -1.0, 0]
MODULES = ["frontleft", "frontright", "backleft", "backright"]


def _steer_once(g, surface):
    ch = plant.steer_step(STEER_PATTERN, kP=g["Steer/kP"], kI=g.get("Steer/kI", 0),
                          kD=g.get("Steer/kD", 0), i_zone=g.get("Steer/IZone", 0),
                          ramp_s=g.get("Steer/RampS", 0), surface=surface)
    return {"test": "steer_step", "channels": ch, "practice": True,
            "env": "FIELD" if surface == "floor" else "BLOCKS",
            "robot": {"modules": MODULES[:1]}}


def _drive_once(g, surface):
    per = g.get("Drive/VelPeriodMs") or 32
    dep = g.get("Drive/VelDepth") or 8
    m0 = MODULES[0]
    ch = plant.drive_step(DRIVE_PATTERN, kP=g["Drive/kP"], kI=g.get("Drive/kI", 0),
                          kD=g.get("Drive/kD", 0), ramp_s=g.get("Drive/RampS", 0),
                          meas_period_ms=per, meas_depth=dep, surface=surface,
                          ff=(g.get(f"FF/{m0}/kS", 0.0), g.get(f"FF/{m0}/kV", 2.915),
                              g.get(f"FF/{m0}/kA", 0.0)))
    return {"test": "drive_step", "channels": ch, "practice": True,
            "env": "FIELD" if surface == "floor" else "BLOCKS", "robot": {"modules": MODULES}}


def _ff_once(g, surface):
    per = g.get("Drive/VelPeriodMs") or 32
    dep = g.get("Drive/VelDepth") or 8
    ch = plant.drive_ff(surface=surface, quasi_s=6, max_v=6, meas_period_ms=per, meas_depth=dep)
    return {"test": "drive_ff", "channels": ch, "practice": True,
            "env": "FIELD" if surface == "floor" else "BLOCKS",
            "meta": {"kv_nominal": 2.915}, "robot": {"modules": MODULES}}


def rehearse(loop, gains, surface="floor", rounds=12, log=None):
    """Runs the advice loop. Returns a list of rounds: gains, score, cost, advice title."""
    g = dict(gains)
    if loop == "drive":
        for m in MODULES:
            g.setdefault(f"FF/{m}/kS", 0.0)
            g.setdefault(f"FF/{m}/kV", 2.915)
            g.setdefault(f"FF/{m}/kA", 0.0)
    history = []
    seen = set()
    for i in range(rounds):
        run = _steer_once(g, surface) if loop == "steer" else _drive_once(g, surface)
        rep = advisor.analyze(run, gains=g)
        nxt = rep.get("next")
        entry = {"round": i, "gains": {k: v for k, v in g.items() if not k.startswith("FF/")},
                 "ff": {k: v for k, v in g.items() if k.startswith(f"FF/{MODULES[0]}/")},
                 "score": rep.get("score"), "cost": rep.get("cost"),
                 "worst": rep.get("worst"), "advice": nxt["title"] if nxt else None}
        history.append(entry)
        if log:
            log(entry)
        if not nxt:
            break
        action = nxt["action"]
        if action["type"] == "gains":
            key = tuple(sorted(action["values"].items()))
            if key in seen and all(g.get(k) == v for k, v in action["values"].items()):
                break  # advice repeated with nothing left to change
            seen.add(key)
            g.update(action["values"])
        elif action["type"] == "run" and action["test"] == "drive_ff":
            ff = advisor.analyze(_ff_once(g, surface))
            if ff.get("next") and ff["next"]["action"]["type"] == "gains":
                g.update(ff["next"]["action"]["values"])
            else:
                break
        else:
            break  # save, config, troubleshoot: a person's decision, not the loop's
    return history
