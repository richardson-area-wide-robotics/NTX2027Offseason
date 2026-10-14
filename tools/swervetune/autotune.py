"""The auto-tuner: each pod's own steering or drive gains, tuned by running the test, reading the
advice for that pod, applying it to that pod alone, and running again.

The loop :mod:`rehearse` proves against the model, on the real robot. On blocks every wheel turns
freely, and on the floor the robot rolls on all four, so the pods always run together: each round
is one test of every pod, and each pod is judged on its own (:func:`advisor.pod_doc`) and changed
on its own (its ``Pod/<module>/...`` gains; a shared gain would overwrite every pod's). A pod that
is finished keeps its gains while the rest go on.

It never runs unattended. Every round is a test, and a test waits for the deadman, so a person
holds it for the whole tune. Letting go stops that round and pauses the tuner; it carries on from
the same round when the person presses Continue. It stops for good on ABORT, a refused or failed
run, Stop, or when every pod is finished. Each pod finishes on its own when:

* it meets every target (score 100, or the advice is to save);
* the advice isn't a change to its own gains (a limit, a configuration fix, a test other than the
  drive feedforward): a person's call, said in its reason. A setting every pod shares (a ramp
  rate, the velocity filter) is changed only when every pod still tuning asks for the same change,
  once, for all of them; the drive feedforward is measured (on the floor) for every pod at once;
* the same advice comes back with nothing left to change;
* two rounds in a row don't beat its best cost, or it has had ``max_rounds`` rounds.

Every change is the advisor's, which never more than doubles or halves a gain in one step. At the
end each pod is put back on the gains it ran its best round with (lowest cost). Nothing is written
to a file: the result is offered for Save gains, which previews the change as usual.
"""

from __future__ import annotations

import threading
import time

from . import advisor, plant, rehearse

MAX_ROUNDS = 8
STALL = 2
TESTS = {"steer": "steer_step", "drive": "drive_step"}
PID = ("kP", "kI", "kD", "IZone")
LOOP_KEY = {"steer": "Steer", "drive": "Drive"}


def pod_gains(gains, pod):
    """The gains as one pod runs them: its own PID in place of the shared names."""
    g = dict(gains)
    for loop in ("Steer", "Drive"):
        for k in PID:
            v = gains.get(f"Pod/{pod}/{loop}/{k}")
            if v is not None:
                g[f"{loop}/{k}"] = v
    return g


def own_change(values, pod):
    """The advice as this pod's own gains, or None when it changes a gain every pod shares."""
    out = {}
    for k, v in values.items():
        loop, _, name = k.partition("/")
        if loop in ("Steer", "Drive") and name in PID:
            out[f"Pod/{pod}/{k}"] = v
        elif k.startswith(f"FF/{pod}/"):
            out[k] = v
        else:
            return None
    return out


class Pod:
    def __init__(self, name):
        self.name = name
        self.rounds = []          # {round, gains, score, cost, advice, run}
        self.status = "tuning"    # tuning, done, stopped
        self.reason = ""
        self.best = None          # the round with the lowest cost
        self.stalls = 0
        self.seen = set()
        self.want_ff = False
        self.shared = None

    def to_json(self):
        return {"pod": self.name, "status": self.status, "reason": self.reason, "rounds": self.rounds,
                "best": self.best}


class AutoTune:
    """One tune of one loop. ``runner`` runs a test and applies gains (:class:`RobotRunner`, or
    :class:`PracticeRunner` for practice and the tests)."""

    def __init__(self, runner, loop, max_rounds=MAX_ROUNDS, log=None):
        if loop not in TESTS:
            raise ValueError("The auto-tuner tunes steer or drive.")
        self.runner, self.loop, self.max_rounds, self.log = runner, loop, max_rounds, log
        self.pods = [Pod(m) for m in runner.modules()]
        self.round = 0
        self.notes = []           # what it did beyond each pod's own changes
        self.shared_seen = set()
        self.state = "ready"      # ready, running, paused, finished, stopped
        self.message = ""
        self._go = threading.Event()
        self._stop = False
        self.thread = None

    # ------------------------------------------------------------------ control
    def start(self):
        self.state = "running"
        self.thread = threading.Thread(target=self._safe_run, name="swervetune-autotune", daemon=True)
        self.thread.start()

    def resume(self):
        """Continue after the deadman was let go: the same round again."""
        if self.state == "paused":
            self.state = "running"
            self._go.set()

    def stop(self, why="Stopped."):
        self._stop = True
        self.message = why
        self._go.set()

    def to_json(self):
        return {"loop": self.loop, "state": self.state, "message": self.message, "round": self.round, "notes": self.notes,
                "max_rounds": self.max_rounds, "pods": [p.to_json() for p in self.pods],
                "best_gains": self.best_gains()}

    def mine(self, pod):
        """The gain names this tune changes for a pod: its own PID for this loop (and, for drive, its
        feedforward). Only these are recorded, put back and saved."""
        return (f"Pod/{pod}/{LOOP_KEY[self.loop]}/",) + ((f"FF/{pod}/",) if self.loop == "drive" else ())

    def best_gains(self):
        """Each pod's own gains from its best round: what Save gains would write."""
        out = {}
        for p in self.pods:
            if p.best:
                out.update(p.best["gains"])
        return out

    # ------------------------------------------------------------------ the loop
    def _safe_run(self):
        try:
            self.run()
        except Exception as e:  # noqa: BLE001 - the page must hear about any failure
            self.state, self.message = "stopped", f"The tuner stopped on an error: {e}"

    def _test(self, test, what):
        """Runs one test, waiting out a let-go deadman: the run's document, or None to stop."""
        while not self._stop:
            self.message = f"Round {self.round + 1}: {what}. Keep holding the deadman."
            doc, outcome, why = self.runner.run(test)
            if self._stop:
                return None
            if outcome == "DONE":
                return doc
            if "deadman" not in (why or "").lower():
                self.state, self.message = "stopped", f"Stopped: the run ended {outcome.lower()}: {why}"
                return None
            # Let go: wait for the person, then the same round again.
            self.state, self.message = "paused", (f"Paused: the deadman was let go. Hold it again and press "
                                                  f"Continue to run round {self.round + 1} again.")
            self._go.clear()
            self._go.wait()
        return None

    def run(self):
        test = TESTS[self.loop]
        ff_done = False
        while not self._stop and any(p.status == "tuning" for p in self.pods):
            if self.round >= self.max_rounds:
                for p in self.pods:
                    if p.status == "tuning":
                        p.status, p.reason = "stopped", f"{self.max_rounds} rounds without meeting every target."
                break
            gains = self.runner.gains()
            want_ff = [p for p in self.pods if p.status == "tuning" and p.want_ff]
            if want_ff:
                changes = self._feedforward(want_ff, gains, ff_done)
                ff_done = True
            else:
                doc = self._test(test, f"{test} on every pod")
                if doc is None:
                    break
                doc = dict(doc, gains=gains)
                changes = {}
                for p in self.pods:
                    if p.status == "tuning":
                        p.shared = None
                        changes.update(self._judge(p, doc, gains) or {})
                changes.update(self._shared(gains))
            if self._stop or self.state == "stopped":
                break
            self.round += 1
            if changes:
                self.runner.apply(changes, f"Auto-tune {self.loop}, round {self.round}")
        self._put_back_best()
        if self.state != "stopped":
            done = sum(p.status == "done" for p in self.pods)
            self.state = "stopped" if self._stop else "finished"
            self.message = self.message if self._stop else (
                f"Finished: {done} of {len(self.pods)} pods meet every target. Each pod is back on its best "
                "gains; Save gains writes them to the robot's files.")

    def _judge(self, p, doc, gains):
        """One pod's report, recorded; returns the change to make for it, or None."""
        mine = advisor.pod_doc(doc, p.name)
        g = pod_gains(gains, p.name)
        rep = advisor.analyze(mine, g, **self.runner.context(self.loop))
        nxt = rep.get("next")
        entry = {"round": self.round + 1, "gains": {k: v for k, v in gains.items() if k.startswith(self.mine(p.name))},
                 "score": rep.get("score"), "cost": rep.get("cost"), "advice": nxt["title"] if nxt else None,
                 "run": doc.get("_run")}
        p.rounds.append(entry)
        if self.log:
            self.log(p.name, entry)
        cost = rep.get("cost")
        if cost is not None and (p.best is None or cost < p.best["cost"]):
            p.best, p.stalls = entry, 0
        elif cost is not None:
            p.stalls += 1
        if (rep.get("score") or 0) >= 100 or (nxt and nxt["action"]["type"] == "save") or rep.get("limited"):
            p.status, p.reason = "done", "Meets every target."
            return None
        if p.stalls >= STALL:
            p.status, p.reason = "stopped", f"{STALL} rounds without beating its best: it goes back to round {p.best['round']}'s gains."
            return None
        if nxt and self.loop == "drive" and nxt["action"]["type"] == "run" and nxt["action"].get("test") == "drive_ff":
            if doc.get("env") == "BLOCKS":
                p.status, p.reason = "stopped", (f"Needs a person: {nxt['title']}. The feedforward is measured on the floor "
                                                 "(Field), where the wheels carry the robot: run the drive auto-tune there.")
            else:
                p.want_ff = True   # the next round measures every pod's feedforward
            return None
        if not nxt or nxt["action"]["type"] != "gains":
            p.status, p.reason = "stopped", ("Needs a person: " + nxt["title"]) if nxt else "No more advice."
            return None
        values = nxt["action"]["values"]
        change = own_change(values, p.name)
        if change is not None and not all(k.startswith(self.mine(p.name)) for k in change):
            change = None   # e.g. drive advice on a steer gain: not this tune's to change
        if change is None:
            if values and all(k.startswith(LOOP_KEY[self.loop] + "/") and k.split("/", 1)[1] not in PID for k in values):
                p.shared = (dict(values), nxt["title"])   # this loop's shared setting: decided once every pod is judged
            else:
                p.status, p.reason = "stopped", "Needs a person: the advice changes a gain every pod shares (" + nxt["title"] + ")."
            return None
        key = tuple(sorted(change.items()))
        if key in p.seen and all(gains.get(k) == v for k, v in change.items()):
            p.status, p.reason = "stopped", "The same advice again, with nothing left to change."
            return None
        p.seen.add(key)
        return change

    def _shared(self, gains):
        """A setting every pod shares (a ramp rate, the velocity filter): changed only when every pod
        still tuning asks for the same change, and only once. Otherwise each pod that asked stops."""
        asking = [p for p in self.pods if p.status == "tuning" and p.shared]
        if not asking:
            return {}
        tuning = [p for p in self.pods if p.status == "tuning"]
        first = asking[0].shared[0]
        key = tuple(sorted(first.items()))
        if len(asking) == len(tuning) and all(p.shared[0] == first for p in asking) and key not in self.shared_seen                 and not all(gains.get(k) == v for k, v in first.items()):
            self.shared_seen.add(key)
            self.notes.append(f"Round {self.round + 1}: every pod asked for the same shared change ({asking[0].shared[1]}), "
                              "so it was made once, for all of them.")
            for p in asking:
                p.rounds[-1]["advice"] = "Shared, every pod: " + p.shared[1]
            return dict(first)
        for p in asking:
            p.status, p.reason = "stopped", "Needs a person: the advice changes a gain every pod shares (" + p.shared[1] + ")."
        return {}

    def _feedforward(self, pods, gains, already):
        """Drive advice to measure the feedforward: one drive_ff run for every pod, each pod given its
        own measured kS/kV/kA. Measured only on the floor (on blocks a wheel spins with no load, and
        the report gives none), and only once a tune."""
        if already:
            for p in pods:
                p.status, p.reason = "stopped", "Needs a person: it asked for the feedforward again after it was measured."
            return {}
        doc = self._test("drive_ff", "measuring every pod's feedforward (drive_ff)")
        if doc is None:
            return {}
        rep = advisor.analyze(dict(doc, gains=gains), gains, **self.runner.context(self.loop))
        nxt = rep.get("next")
        values = nxt["action"].get("values") or {} if nxt and nxt["action"]["type"] == "gains" else {}
        changes = {}
        for p in pods:
            p.want_ff = False
            own = {k: v for k, v in values.items() if k.startswith(f"FF/{p.name}/")}
            if own:
                changes.update(own)
                p.rounds.append({"round": self.round + 1, "gains": {k: v for k, v in gains.items() if k.startswith(self.mine(p.name))},
                                 "score": None, "cost": None, "advice": "Feedforward measured: " + ", ".join(
                                     f"{k.split('/')[-1]} {v:.3g}" for k, v in own.items()), "run": doc.get("_run")})
            else:
                p.status, p.reason = "stopped", ("Needs a person: the feedforward is measured on the floor (Field), "
                                                 "where the wheels carry the robot." if rep.get("env") == "BLOCKS" or doc.get("env") == "BLOCKS"
                                                 else "Needs a person: the feedforward test gave nothing for this pod"
                                                 + (f" ({nxt['title']})." if nxt else "."))
        return changes

    def _put_back_best(self):
        """Every pod back on its best round's gains, where it isn't on them already."""
        now = self.runner.gains()
        back = {}
        for p in self.pods:
            if p.best:
                back.update({k: v for k, v in p.best["gains"].items() if now.get(k) != v})
        if back:
            self.runner.apply(back, f"Auto-tune {self.loop}: each pod back on its best gains")


# ---------------------------------------------------------------------------- runners


class RobotRunner:
    """The connected robot, through the tool's session: each run saved like any other."""

    def __init__(self, session):
        self.s = session

    def modules(self):
        return list(self.s.link.robot_info().get("modules") or [])

    def gains(self):
        return self.s.link.gains()

    def run(self, test):
        res, doc, path = self.s.run_test_sync(test, "ALL", {})
        if doc is not None and path:
            doc = dict(doc, _run=path)
        return doc, res.outcome if res.accepted else "REFUSED", res.message

    def apply(self, values, reason):
        status, _ = self.s.link.set_gains(values, reason=reason)
        return status

    def context(self, loop):
        lim = self.s.limits()
        return dict(current_limit=lim["steer" if loop == "steer" else "drive"], **advisor.robot_context(self.s.project))


class PracticeRunner:
    """Four practice pods (the model in :mod:`plant`), each on its own gains and its own small
    differences: for the Tune tab's practice target and for the tests."""

    def __init__(self, gains, surface="blocks", motor="vortex", modules=None):
        self.mods = list(modules or rehearse.MODULES)
        self.g = dict(gains)
        for m in self.mods:
            for loop in ("Steer", "Drive"):
                for k in PID:
                    self.g.setdefault(f"Pod/{m}/{loop}/{k}", self.g.get(f"{loop}/{k}", 0.0))
            self.g.setdefault(f"FF/{m}/kS", 0.0)
            self.g.setdefault(f"FF/{m}/kV", plant.nominal_kv(motor))
            self.g.setdefault(f"FF/{m}/kA", 0.0)
        self.surface, self.motor, self.runs = surface, motor, 0

    def modules(self):
        return list(self.mods)

    def gains(self):
        return dict(self.g)

    def run(self, test):
        self.runs += 1
        channels = {}
        for i, m in enumerate(self.mods):
            g = pod_gains(self.g, m)
            if test == "steer_step":
                ch = plant.steer_step(rehearse.STEER_PATTERN, kP=g["Steer/kP"], kI=g.get("Steer/kI", 0), kD=g.get("Steer/kD", 0),
                                      i_zone=g.get("Steer/IZone", 0), ramp_s=g.get("Steer/RampS", 0),
                                      surface=self.surface, seed=1 + i)
            elif test == "drive_ff":
                ch = plant.drive_ff(surface=self.surface, quasi_s=6, max_v=6, meas_period_ms=g.get("Drive/VelPeriodMs") or 32,
                                    meas_depth=g.get("Drive/VelDepth") or 8, motor=self.motor)
            else:
                ch = plant.drive_step(rehearse.DRIVE_PATTERN, kP=g["Drive/kP"], kI=g.get("Drive/kI", 0), kD=g.get("Drive/kD", 0),
                                      ramp_s=g.get("Drive/RampS", 0), meas_period_ms=g.get("Drive/VelPeriodMs") or None,
                                      meas_depth=g.get("Drive/VelDepth") or None, surface=self.surface, motor=self.motor,
                                      ff=(g[f"FF/{m}/kS"], g[f"FF/{m}/kV"], g[f"FF/{m}/kA"]))
            for k, v in ch.items():
                if k.startswith("m0."):
                    channels[f"m{i}." + k[3:]] = v
                elif i == 0:
                    channels[k] = v
        env = "FIELD" if self.surface == "floor" else "BLOCKS"
        doc = {"test": test, "channels": channels, "practice": True, "env": env, "outcome": "DONE",
               "robot": {"modules": self.mods}, "meta": {"pod_motor": self.motor, "kv_nominal": plant.nominal_kv(self.motor)}}
        return doc, "DONE", ""

    def apply(self, values, reason):
        self.g.update(values)
        return "Applied."

    def context(self, loop):
        return {}


def wait(tune, timeout=600.0):
    """Waits for a tune to stop (the tests and the command line)."""
    end = time.time() + timeout
    while tune.thread and tune.thread.is_alive() and time.time() < end:
        time.sleep(0.05)
    return tune.to_json()
