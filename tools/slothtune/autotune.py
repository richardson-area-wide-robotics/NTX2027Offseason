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

:class:`SystemTune` does the same for one mechanism on the Systems tab: its step test, the one
change its report asks for (:func:`systems.tune_next`) to its own gains, a round at a time, ending
on its best round. Its Save writes the gains to slothtune.json, which the robot applies at startup.

:class:`ModelTune` is the model-based way (decision 75): one measuring run (``system_id``), the
gains worked out from the fitted model applied together, then the step test as a check, trimming the
one setting the model leaves open (how hard the loop pushes) by the checks' cost, at most four times.
"""

from __future__ import annotations

import math
import threading
import time

from . import advisor, plant, rehearse, systems

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


class _Loop:
    """Starting, pausing on a let-go deadman, continuing and stopping: what every tuner shares.
    ``runner.run(test)`` gives ``(document, outcome, why)``."""

    def _init_loop(self, runner, max_rounds):
        self.runner, self.max_rounds = runner, max_rounds
        self.round = 0
        self.state = "ready"      # ready, running, paused, finished, stopped
        self.message = ""
        self._go = threading.Event()
        self._stop = False
        self.thread = None

    def start(self):
        self.state = "running"
        self.thread = threading.Thread(target=self._safe_run, name="slothtune-autotune", daemon=True)
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


class AutoTune(_Loop):
    """One tune of one loop. ``runner`` runs a test and applies gains (:class:`RobotRunner`, or
    :class:`PracticeRunner` for practice and the tests)."""

    def __init__(self, runner, loop, max_rounds=MAX_ROUNDS, log=None):
        if loop not in TESTS:
            raise ValueError("The auto-tuner tunes steer or drive.")
        self._init_loop(runner, max_rounds)
        self.loop, self.log = loop, log
        self.pods = [Pod(m) for m in runner.modules()]
        self.notes = []           # what it did beyond each pod's own changes
        self.shared_seen = set()

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


# ---------------------------------------------------------------------------- one mechanism


class SystemTune(_Loop):
    """The auto-tuner for one mechanism: its step test each round, the first change its report
    offers (to its own ``Name/k`` gains, kept inside the robot's allowed range), and at the end the
    gains of its best round (lowest cost). A change that makes a round much worse than the best
    (``WORSE`` times its cost) is backed out at once, and that change, that way, isn't tried again:
    the next one the best round's report offered is. (A code that holds a position in the SPARK's
    own loop gives it no speed, so a kV there only pushes it off: the physics are right, the code
    can't use them.) It finishes when it meets every target; it stops for a person when nothing it
    may try is left, the advice isn't a gain change, two rounds don't beat its best, or after
    ``max_rounds``. ``runner`` is a :class:`RobotSystemRunner` or a :class:`PracticeSystemRunner`."""

    WORSE = 2.0       # a step on the way (kG before kV) can cost more for a round; a wrong one costs far more

    def __init__(self, runner, name, max_rounds=MAX_ROUNDS):
        self._init_loop(runner, max_rounds)
        self.name = name
        self.rounds = []          # {round, gains, cost, score, advice, why, run}
        self.best = None
        self.status, self.reason = "tuning", ""
        self.stalls = 0
        self.seen = set()
        self.banned = set()       # (gain, "set"/"up"/"down") that made it much worse
        self.last = None          # the change made after the last round

    def to_json(self):
        return {"system": self.name, "state": self.state, "message": self.message, "round": self.round,
                "max_rounds": self.max_rounds, "status": self.status, "reason": self.reason,
                "rounds": self.rounds, "best": self.best, "best_gains": self.best_gains()}

    def best_gains(self):
        return dict(self.best["gains"]) if self.best else {}

    def _clamp(self, values):
        """The change kept inside the gains' allowed ranges, and to this mechanism's own gains."""
        ranges = self.runner.ranges()
        out = {}
        for k, v in values.items():
            if not k.startswith(self.name + "/"):
                continue
            lo, hi = ranges.get(k, (float("nan"), float("nan")))
            if lo == lo and v < lo:
                v = lo
            if hi == hi and v > hi:
                v = hi
            out[k] = v
        return out

    def _finish(self, status, reason):
        self.status, self.reason = status, reason

    def run(self):
        while not self._stop:
            if self.round >= self.max_rounds:
                self._finish("stopped", f"{self.max_rounds} rounds without meeting every target.")
                break
            gains = self.runner.gains()
            doc = self._test("system_step", f"{self.name}'s step test")
            if doc is None:
                break
            rep = self.runner.report(dict(doc, gains=gains))
            cost = rep.get("cost")
            options = rep.get("options") or ([rep["next"]] if rep.get("next") else [])
            entry = {"round": self.round + 1, "gains": {k: v for k, v in gains.items() if k.startswith(self.name + "/")},
                     "cost": cost, "score": rep.get("score"), "advice": None, "why": None,
                     "summary": rep.get("summary"), "run": doc.get("_run"), "options": options}
            self.rounds.append(entry)
            self.round += 1
            if cost is None:
                self._finish("stopped", "Needs a person: " + (rep.get("summary") or "this run can't be judged."))
                break
            worse = self.best is not None and self.last and cost > self.WORSE * self.best["cost"] + 1
            if worse:
                # Back out at once, and don't try that change that way again: the best round's next offer.
                self.banned.add(self.last)
                gains = dict(self.runner.gains(), **self.best["gains"])
                self.runner.apply({k: v for k, v in self.best["gains"].items() if self.runner.gains().get(k) != v},
                                  f"Auto-tune {self.name}: round {self.round} was worse, back to round {self.best['round']}'s gains")
                options = self.best["options"]
                entry["advice"] = f"Much worse: back to round {self.best['round']}'s gains, and {self.last[0].split('/')[-1]} that way is off the list."
            elif self.best is None or cost < self.best["cost"]:
                self.best, self.stalls = entry, 0
            else:
                self.stalls += 1
            if not worse and options and options[0]["action"]["type"] == "save":
                entry["advice"] = options[0]["title"]
                self._finish("done", "Meets every target.")
                break
            if self.stalls >= STALL:
                self._finish("stopped", f"{STALL} rounds without beating its best: it goes back to round {self.best['round']}'s gains.")
                break
            nxt = next((o for o in options if o["action"]["type"] != "gains"
                        or systems.change_key(o["action"]["values"], gains) not in self.banned), None)
            if not worse:
                entry["advice"], entry["why"] = (nxt["title"], nxt.get("why")) if nxt else (None, None)
            if not nxt or nxt["action"]["type"] != "gains":
                self._finish("stopped", "Needs a person: " + (nxt["title"] if nxt else "every change it could try made it worse."))
                break
            if worse:
                entry["advice"] += f" Next: {nxt['title']}."
            change = self._clamp(nxt["action"]["values"])
            if not change or all(gains.get(k) == v for k, v in change.items()):
                self._finish("stopped", f"Needs a person: {nxt['title']}, but the gain is already at the end of its range.")
                break
            key = tuple(sorted(change.items()))
            if key in self.seen:
                self._finish("stopped", "The same advice again, with nothing left to change.")
                break
            self.seen.add(key)
            self.last = systems.change_key(change, gains)
            self.runner.apply(change, f"Auto-tune {self.name}, round {self.round}")
        if self.best:
            now = self.runner.gains()
            back = {k: v for k, v in self.best["gains"].items() if now.get(k) != v}
            if back:
                self.runner.apply(back, f"Auto-tune {self.name}: back on its best gains")
        if self.state != "stopped":
            self.state = "stopped" if self._stop else "finished"
            if not self._stop:
                self.message = (f"Finished: {self.reason} " if self.reason else "Finished. ") + (
                    f"It is on round {self.best['round']}'s gains, its best; Save writes them to slothtune.json."
                    if self.best else "")
        if self._stop and self.status == "tuning":
            self.status, self.reason = "stopped", self.message or "Stopped."


class ModelTune(_Loop):
    """Model-based auto-tune (decision 75) for one mechanism.

    1. Measure it: ``system_id`` on blocks, the robot's code paused, its SPARK run by voltage.
    2. Fit its physics and work every gain out from them at once (:func:`systems.id_report`): LQR
       for a position loop, SIMC for a speed loop, MAXMotion's limits, voltage compensation from the
       battery it held, only the gains the mode its code runs the SPARK in uses.
    3. Check: the step test with those gains, judged as every step test is (its cost).
    4. Trim the one setting the model leaves open, how hard the loop pushes (``aggressiveness``,
       half to double): a check that overshoots or rings more than the model said goes softer,
       one that is clean goes harder, then one between the two best. At most ``max_checks``.
    5. End on the best check's gains. A first check that meets every target ends it at once.

    Nothing is written to a file: Save writes the gains to slothtune.json as usual."""

    MAX_CHECKS = 4
    SOFT, HARD = 0.5, 2.0
    ACCEPT_OVERSHOOT = 15.0   # the best check must settle and overshoot no more than this (percent)

    def __init__(self, runner, name, max_checks=MAX_CHECKS):
        self._init_loop(runner, max_checks + 1)
        self.name = name
        self.max_checks = max_checks
        self.report = None
        self.checks = []
        self.best = None
        self.before = None
        self.status, self.reason = "tuning", ""

    def to_json(self):
        r = self.report or {}
        return {"system": self.name, "mode": "model", "state": self.state, "message": self.message,
                "round": self.round, "max_rounds": self.max_rounds, "status": self.status, "reason": self.reason,
                "model": {k: r.get(k) for k in ("summary", "model", "shown", "fit", "delay_s", "filter", "volts_comp",
                                                 "findings", "current", "ratio_v", "applied_volts")} if r else None,
                "run": r.get("_run"), "checks": self.checks, "best": self.best,
                "best_gains": self.best_gains(), "before": self.before}

    def best_gains(self):
        return dict(self.best["gains"]) if self.best else {}

    def _finish(self, status, reason):
        self.status, self.reason = status, reason

    def _check(self, agg):
        comp = systems.model_gains(self.report["basis"], agg)
        self.runner.apply(comp["apply"], f"Model-based tune {self.name}: the model's gains at {agg:g}x")
        doc = self._test("system_step", f"check {len(self.checks) + 1}, the model's gains at {agg:g}x")
        if doc is None:
            return None
        rep = self.runner.report(dict(doc, gains=self.runner.gains()))
        moves = rep.get("moves") or []
        measured = {"overshoot_pct": max((m["overshoot_pct"] for m in moves), default=None),
                    "error_pct": max((abs(m["error_pct"]) for m in moves), default=None),
                    "settled": all(m["settle_s"] is not None for m in moves) if moves else None,
                    "settle_s": max((m["settle_s"] for m in moves if m["settle_s"] is not None), default=None)}
        entry = {"check": len(self.checks) + 1, "aggressiveness": agg, "gains": comp["apply"],
                 "cost": rep.get("cost"), "score": rep.get("score"), "summary": rep.get("summary"),
                 "measured": measured, "predicted": comp["predicted"], "run": doc.get("_run"),
                 "meets": bool((rep.get("options") or [{}])[0].get("action", {}).get("type") == "save")}
        self.checks.append(entry)
        self.round += 1
        if entry["cost"] is not None and (self.best is None or entry["cost"] < self.best["cost"]):
            self.best = entry
        return entry

    def _next_trim(self):
        """The next aggressiveness: away from the first check toward what it lacked, then between."""
        tried = sorted(c["aggressiveness"] for c in self.checks)
        judged = [c for c in self.checks if c["cost"] is not None]
        if len(judged) == 1:
            c = judged[0]
            m, p = c["measured"], c["predicted"]
            rough = (m["settled"] is False or (m["overshoot_pct"] or 0) > (p.get("overshoot_pct") or 0) + 5)
            return 0.6 if rough else 1.6
        by = sorted(judged, key=lambda c: c["cost"])
        a, b = by[0]["aggressiveness"], by[1]["aggressiveness"]
        if by[0]["aggressiveness"] in (min(tried), max(tried)):
            # The best is at an end: one more step past it, inside half to double.
            nxt = a * (a / b) if a != b else a * 1.25
            nxt = min(self.HARD, max(self.SOFT, nxt))
        else:
            nxt = math.sqrt(a * b)
        return None if any(abs(nxt - x) < 0.05 for x in tried) else round(nxt, 3)

    def run(self):
        self.before = {k: v for k, v in self.runner.gains().items() if k.startswith(self.name + "/")}
        doc = self._test("system_id", f"measuring {self.name}")
        if doc is None:
            if self.status == "tuning":
                self._finish("stopped", self.message or "Stopped.")
        else:
            rep = self.runner.id_report(doc)
            self.report = dict(rep, _run=doc.get("_run"))
            self.round += 1
            if not rep.get("basis"):
                self._finish("stopped", "Needs a person: " + (rep.get("summary") or "the run couldn't be fitted."))
            elif not rep["computed"]["apply"]:
                self._finish("stopped", "Needs a person: nothing to apply. " + (rep["computed"].get("note") or ""))
            else:
                agg = 1.0
                while not self._stop and len(self.checks) < self.max_checks and agg is not None:
                    entry = self._check(agg)
                    if entry is None:
                        break
                    if entry["cost"] is None:
                        self._finish("stopped", "Needs a person: " + (entry["summary"] or "the check run can't be judged."))
                        break
                    if entry["meets"] and len(self.checks) == 1:
                        self._finish("done", "The model's gains meet every target on the first check.")
                        break
                    agg = self._next_trim()
                if self.status == "tuning" and self.best:
                    m = self.best["measured"]
                    if m["settled"] is False or (m["overshoot_pct"] or 0) > self.ACCEPT_OVERSHOOT:
                        # Even the best check doesn't behave: the model is off for this mechanism. Put
                        # back what it started on rather than leave it on gains that ring.
                        p = self.best["predicted"]
                        self._finish("stopped", (
                            f"Needs a person: the best check still {'never settled' if m['settled'] is False else 'overshot'}"
                            f" ({m['overshoot_pct'] or 0:.0f}% against the model's {p.get('overshoot_pct') or 0:.0f}%), so "
                            "the model doesn't match it: something loose, a delay it didn't measure, or a filter. It is "
                            "back on the gains it started with."))
                        self.best = None
                    else:
                        self._finish("done", f"{len(self.checks)} checks: the best was {self.best['aggressiveness']:g}x "
                                             f"(cost {self.best['cost']:.3g}).")
        if self.best:
            now = self.runner.gains()
            back = {k: v for k, v in self.best["gains"].items() if now.get(k) != v}
            if back:
                self.runner.apply(back, f"Model-based tune {self.name}: back on its best check's gains")
        elif self.before and self.checks:
            self.runner.apply(self.before, f"Model-based tune {self.name}: no check could be judged, back to where it started")
        if self.state != "stopped":
            self.state = "stopped" if self._stop else "finished"
            if not self._stop:
                self.message = (f"Finished: {self.reason} " if self.reason else "Finished. ") + (
                    f"It is on check {self.best['check']}'s gains; Save writes them to slothtune.json." if self.best else "")
        if self._stop and self.status == "tuning":
            self.status, self.reason = "stopped", self.message or "Stopped."


class RobotSystemRunner:
    """One mechanism on the connected robot, through the tool's session: its live gains (and their
    allowed ranges) as the robot reports them, its step test with the Systems tab's arguments, and
    for the model-based tune its measuring run with ``id_args``."""

    def __init__(self, session, name, args, id_args=None):
        self.s, self.name, self.args, self.id_args = session, name, dict(args), dict(id_args or {})

    def _system(self):
        return next((x for x in self.s.link.systems() if x["name"] == self.name), None) or {}

    def gains(self):
        return {f"{self.name}/{k}": g["value"] for k, g in (self._system().get("gains") or {}).items()}

    def ranges(self):
        return {f"{self.name}/{k}": (g.get("min", float("nan")), g.get("max", float("nan")))
                for k, g in (self._system().get("gains") or {}).items()}

    def run(self, test):
        res, doc, path = self.s.run_test_sync(test, "ALL", self.id_args if test == "system_id" else self.args)
        if doc is not None and path:
            doc = dict(doc, _run=path)
        return doc, res.outcome if res.accepted else "REFUSED", res.message

    def report(self, doc):
        return advisor.analyze(doc, doc.get("gains"), **advisor.robot_context(self.s.project))

    def id_report(self, doc):
        return systems.id_report(doc, systems.settings(self.s.project).get(self.name), self._system(),
                                 systems.system_motor(self.s.link.motors().get("motors") or [], self._system()))

    def apply(self, values, reason):
        return self.s.link.set_system_gains(values)


class PracticeSystemRunner:
    """A made-up mechanism on its own gains, for the tests and practice: an elevator (meters, with
    gravity) or a flywheel (rad/s) as a DC motor with friction and inertia, run through the same
    step test the robot runs (a trapezoid move, then a hold, ``moves`` times). The controller sees
    the mechanism ``delay_s`` late, as a real one's sensor and loop do, so too much kP rings.
    ``position_only`` models code that gives its controller only a position (a SPARK in plain
    position mode): its kV multiplies the position, not a speed."""

    PLANTS = {"ELEVATOR": {"kS": 0.15, "kG": 0.45, "kV": 9.0, "kA": 0.35},
              "FLYWHEEL": {"kS": 0.2, "kG": 0.0, "kV": 0.021, "kA": 0.004}}
    ARGS = {"ELEVATOR": {"a": 0.2, "b": 0.8, "vmax": 0.6, "amax": 3.0, "hold_s": 1.0, "moves": 2},
            "FLYWHEEL": {"a": 200.0, "b": 400.0, "vmax": 400.0, "amax": 800.0, "hold_s": 1.5, "moves": 2}}

    # A SPARK in practice (``spark=True``): its gains in REV's units, run at 1 kHz in ``control`` mode;
    # its speed reading in RPM-like units (SPEED_UNITS per position unit a second) through a filter.
    SPEED_UNITS = 60.0
    FILTER_S = 0.02
    SPARK_GAINS = {"kP": (0, 1000), "kI": (0, 100), "kD": (0, 1e5), "kS": (0, 4), "kV": (0, 20), "kA": (0, 20),
                   "kG": (-12, 12), "kCos": (-12, 12), "mmCruise": (0, 1e6), "mmAccel": (0, 1e7), "vComp": (0, 13)}

    def __init__(self, name="Elevator", kind="ELEVATOR", gains=None, args=None, ranges=(0.0, 1000.0), delay_s=0.03,
                 position_only=False, spark=False, control=None):
        self.name, self.kind = name, kind
        self.g = {f"{name}/{k}": float(v) for k, v in (gains or {"kP": 4.0, "kD": 0.0, "kS": 0.0, "kV": 0.0, "kG": 0.0}).items()}
        self.args = dict(self.ARGS[kind], **(args or {}))
        self.p = dict(self.PLANTS[kind])
        self.lo, self.hi = ranges
        self.delay = max(0, round(delay_s / 0.01))
        self.position_only = position_only
        self.spark = spark
        self.control = control or ("Position" if kind == "ELEVATOR" else "Velocity")
        if spark:
            self.g = {f"{name}/{k}": 0.0 for k in self.SPARK_GAINS}
            self.g.update({f"{name}/{k}": float(v) for k, v in (gains or {"kP": 1.0}).items()})
        self.runs = 0

    def gains(self):
        return dict(self.g)

    def ranges(self):
        if self.spark:
            return {f"{self.name}/{k}": r for k, r in self.SPARK_GAINS.items()}
        return {k: (self.lo, self.hi) for k in self.g}

    def registered(self):
        """The robot's view of it, as :meth:`link.systems` gives it."""
        return {"name": self.name, "kind": self.kind, "units": "meters" if self.kind == "ELEVATOR" else "rad/s",
                "control": self.control, "min": 0.0, "max": 1.0,
                "gains": {k.split("/", 1)[1]: {"value": v, "min": self.ranges()[k][0], "max": self.ranges()[k][1]}
                          for k, v in self.g.items()}}

    def id_report(self, doc):
        return systems.id_report(doc, None, self.registered(),
                                 {"motor": "NEO V1.1", "limit_a": 40, "count": 1, "controller": "SPARK MAX"})

    def apply(self, values, reason):
        self.g.update(values)
        return "Applied."

    def report(self, doc):
        return systems.step_report(doc, None, doc.get("gains"))

    def _profile(self, x0, x1, vmax, amax, dt):
        """A trapezoid move from x0 to x1: [(position, speed)] each dt."""
        d, s = abs(x1 - x0), 1 if x1 >= x0 else -1
        ta = vmax / amax
        if amax * ta * ta > d:
            ta = (d / amax) ** 0.5
            vmax = amax * ta
        tc = (d - amax * ta * ta) / vmax if vmax else 0.0
        out, t, total = [], 0.0, 2 * ta + tc
        while t < total:
            if t < ta:
                p, v = 0.5 * amax * t * t, amax * t
            elif t < ta + tc:
                p, v = 0.5 * amax * ta * ta + vmax * (t - ta), vmax
            else:
                r = total - t
                p, v = d - 0.5 * amax * r * r, amax * r
            out.append((x0 + s * p, s * v))
            t += dt
        out.append((x1, 0.0))
        return out

    def _filtered(self, speeds):
        """A SPARK's speed reading: a moving average FILTER_S long, in its speed units."""
        n = max(1, int(round(self.FILTER_S / 0.001)))
        out, acc = [], []
        for v in speeds:
            acc.append(v)
            if len(acc) > n:
                acc.pop(0)
            out.append(sum(acc) / len(acc) * self.SPEED_UNITS)
        return out

    def _step_plant(self, x, v, u, h):
        P = self.p
        positional = self.kind == "ELEVATOR"
        grav = P["kG"] if positional else 0.0
        if v == 0 and abs(u - grav) <= P["kS"]:
            return x, 0.0
        acc = (u - grav - P["kS"] * (1 if (v or (u - grav)) > 0 else -1) - P["kV"] * v) / P["kA"]
        nv = v + acc * h
        if v and nv * v < 0:
            nv = 0.0
        return x + nv * h, nv

    def _identify(self):
        """system_id on the practice mechanism: its hold, slow ramps and quick steps each way, the
        volts held each 20 ms loop, a row a loop, as the robot records it."""
        P, h, loop = self.p, 0.001, 0.02
        positional = self.kind == "ELEVATOR"
        g0 = P["kG"] if positional else 0.0
        plan = []
        if positional:
            for sgn in (1, -1):
                plan += [(lambda s, sgn=sgn: g0 + sgn * (P["kS"] + 0.3 + 0.4 * s), 3.0, 2), (lambda s: g0, 0.6, 1)]
            for sgn in (1, -1):
                plan += [(lambda s, sgn=sgn: g0 + sgn * 3.0, 0.35, 3), (lambda s: g0, 0.6, 1)]
        else:
            plan += [(lambda s: min(8.0, 1.0 * s), 8.0, 2), (lambda s: max(0.0, 8.0 - 1.0 * s), 8.0, 2),
                     (lambda s: 4.0, 1.5, 3), (lambda s: 4.0 / 3, 1.5, 3), (lambda s: 0.0, 0.5, 1)]
        x, v, loops = (0.3 if positional else 0.0), 0.0, 0
        rows = {k: [] for k in ("t", "pos", "vel", "cmd", "volts0", "stage", "loop", "batt", "spos", "svel")}
        speeds = []
        for f, dur, stage in plan:
            k = 0
            while k * loop < dur - 1e-9:
                u = max(-12.0, min(12.0, f(k * loop)))
                for _ in range(int(round(loop / h))):
                    x, v = self._step_plant(x, v, u, h)
                    speeds.append(v)
                sv = self._filtered(speeds[-int(round(self.FILTER_S / h)):])[-1]
                for key, val in (("t", loops * loop), ("pos", x if positional else float("nan")), ("vel", v),
                                 ("cmd", u), ("volts0", u), ("stage", stage), ("loop", loops),
                                 ("batt", 12.4 - 0.08 * abs(u)), ("spos", x), ("svel", sv)):
                    rows[key].append(val)
                loops += 1
                k += 1
        units = "meters" if positional else "rad/s"
        return {"test": "system_id", "outcome": "DONE", "env": "PRACTICE", "practice": True, "channels": rows,
                "notes": [f"system: {self.name} ({self.kind}, {units})", "motor 0: practice (driven)"],
                "meta": {"min": 0.0, "max": 1.0, "lo": 0.05, "hi": 0.95, "vmax": self.args["vmax"]} if positional
                else {"vmax": self.args["vmax"]}}

    def _spark_step(self):
        """The step test with a SPARK's own loop: REV's units, 1 kHz, in ``control`` mode."""
        name, a, h = self.name, self.args, 0.001
        g = lambda k: self.g.get(f"{name}/{k}", 0.0)   # noqa: E731
        positional = self.kind == "ELEVATOR"
        vcomp = g("vComp") or 12.0
        x, v = (a["a"] if positional else 0.0), 0.0
        rows = {k: [] for k in ("t", "pos", "vel", "sp", "goal", "volts0")}
        start = x if positional else 0.0
        targets = [a["b"] if i % 2 == 0 else a["a"] for i in range(int(a["moves"]))]
        t, e_prev, integ = 0.0, None, 0.0
        speeds, held = [], None
        mm = self.control.startswith("MAXMotion")
        cruise = (g("mmCruise") / self.SPEED_UNITS) if g("mmCruise") else a["vmax"]
        accel = (g("mmAccel") / self.SPEED_UNITS) if g("mmAccel") else a["amax"]
        mp, mv = x, 0.0   # MAXMotion's own profile state, chasing the goal the code gives it
        for target in targets:
            prof = self._profile(start, target, a["vmax"], a["amax"], h)
            prof += [(target, 0.0)] * int(a["hold_s"] / h)
            prev_v = 0.0
            for i, (p_sp, v_sp) in enumerate(prof):
                acc_sp = (v_sp - prev_v) / h
                prev_v = v_sp
                if held is None or i % 20 == 0:
                    held = (p_sp, v_sp, acc_sp)   # the code's goal reaches the SPARK each 20 ms loop
                hp, hv, ha = held
                if mm and positional:
                    # MAXMotion: its own trapezoid toward that goal, never past cruise or acceleration.
                    gap = hp - mp
                    stop = mv * mv / (2 * accel) if accel > 0 else 0.0
                    want = (cruise if gap > 0 else -cruise) if abs(gap) > stop else 0.0
                    dv_ = max(-accel * h, min(accel * h, want - mv))
                    if abs(gap) < 1e-6 and abs(mv) < accel * h:
                        mp, mv, dv_ = hp, 0.0, 0.0
                    mv += dv_
                    mp += mv * h
                    hp, hv, ha = mp, mv, dv_ / h
                if positional:
                    e = hp - x
                    ff = g("kG")
                    if mm:
                        ff += g("kS") * (1 if hv > 0 else -1 if hv < 0 else 0) + g("kV") * hv + g("kA") * ha
                else:
                    # A flywheel's profile is of its speed: hp is the speed asked, hv how fast it ramps.
                    sv = self._filtered(speeds[-int(round(self.FILTER_S / h)):] or [0.0])[-1]
                    e = hp * self.SPEED_UNITS - sv
                    ff = g("kS") * (1 if hp > 0 else 0) + g("kV") * hp * self.SPEED_UNITS
                d = 0.0 if e_prev is None else e - e_prev
                e_prev = e
                integ += e
                u = ff + vcomp * (g("kP") * e + g("kD") * d + g("kI") * integ)
                u = max(-12.0, min(12.0, u))
                x, v = self._step_plant(x, v, u, h)
                speeds.append(v)
                if i % 10 == 0:
                    for key, val in (("t", round(t, 4)), ("pos", x if positional else v), ("vel", v),
                                     ("sp", p_sp), ("goal", target), ("volts0", u)):
                        rows[key].append(val)
                t += h
            start = target
        units = "meters" if positional else "rad/s"
        return {"test": "system_step", "outcome": "DONE", "env": "PRACTICE", "practice": True, "channels": rows,
                "notes": [f"system: {name} ({self.kind}, {units})"], "meta": {"min": 0.0, "max": 1.0} if positional else {}}

    def run(self, test):
        self.runs += 1
        if test == "system_id":
            return self._identify(), "DONE", ""
        if self.spark:
            return self._spark_step(), "DONE", ""
        name, a = self.name, self.args
        g = lambda k: self.g.get(f"{name}/{k}", 0.0)   # noqa: E731
        P, dt = self.p, 0.01
        positional = self.kind == "ELEVATOR"
        x = a["a"] if positional else 0.0
        v = 0.0
        t_ch, pos, vel, sp, goal, volts = [], [], [], [], [], []
        targets = [a["b"] if i % 2 == 0 else a["a"] for i in range(int(a["moves"]))]
        start = x if positional else 0.0
        t = 0.0
        seen = [(x, v)] * (self.delay + 1)    # what the controller sees: the mechanism, delay_s ago
        ff_speed = (lambda p_, v_: p_) if self.position_only else (lambda p_, v_: v_)   # noqa: E731
        for target in targets:
            for p_sp, v_sp in self._profile(start, target, a["vmax"], a["amax"], dt) + [(target, 0.0)] * int(a["hold_s"] / dt):
                xs, vs = seen[0]
                if positional:
                    u = g("kS") * (1 if v_sp > 0 else -1 if v_sp < 0 else 0) + g("kG") + g("kV") * ff_speed(p_sp, v_sp) \
                        + g("kP") * (p_sp - xs) + g("kD") * (v_sp - vs)
                else:
                    u = g("kS") * (1 if p_sp > 0 else 0) + g("kV") * p_sp + g("kP") * (p_sp - vs)
                u = max(-12.0, min(12.0, u))
                fr = P["kS"] * (1 if v > 1e-6 else -1 if v < -1e-6 else 0)
                acc = (u - P["kG"] - fr - P["kV"] * v) / P["kA"]
                if abs(v) < 1e-6 and abs(u - P["kG"]) <= P["kS"]:
                    acc = 0.0
                v += acc * dt
                x += v * dt
                seen = seen[1:] + [(x, v)]
                t_ch.append(round(t, 4))
                pos.append(x)
                vel.append(v)
                sp.append(p_sp)
                goal.append(target)
                volts.append(u)
                t += dt
            start = target
        units = "meters" if positional else "rad/s"
        doc = {"test": "system_step", "outcome": "DONE", "env": "PRACTICE", "practice": True,
               "channels": {"t": t_ch, "pos": pos if positional else vel, "vel": vel, "sp": sp, "goal": goal, "volts0": volts},
               "notes": [f"system: {name} ({self.kind}, {units})"],
               "meta": {"min": 0.0, "max": 1.0} if positional else {}}
        return doc, "DONE", ""


def wait(tune, timeout=600.0):
    """Waits for a tune to stop (the tests and the command line)."""
    end = time.time() + timeout
    while tune.thread and tune.thread.is_alive() and time.time() < end:
        time.sleep(0.05)
    return tune.to_json()
