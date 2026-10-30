"""A bring-up session on a live robot: every step in order, the tool's own checks for each, and a record.

Made for the first days with a real robot, with whoever helps from a distance (an AI agent over chat
included) running it on the laptop while a person stands at the robot:

    py -3.12 tools/slothtune session start --project "Black team"
    py -3.12 tools/slothtune session next             # what to do now, and where the robot must be
    py -3.12 tools/slothtune session check link       # the tool's checks for one step
    py -3.12 tools/slothtune session mark directions pass --note "all four rolled forward"
    py -3.12 tools/slothtune session issue "..."      # something wrong with Sloth Tune itself
    py -3.12 tools/slothtune session report           # everything, written up

The steps follow how a robot is brought up: connect; bring-up, robot disabled and then on blocks;
tuning; testing on the floor; set-up for a field or a competition; then troubleshooting, where a
person causes a known fault and the tool must spot it. A check runs the same commands as the rest of
the command line and the same analyses as the GUI, so what passes here passes there. Nothing here
moves the robot by itself: a test that moves it still needs the Driver Station to enable it and a
person holding the deadman, and the robot still refuses a test in the wrong place.

A step that needs a person to move something counts down out loud first (beeps on Windows), so
the person at the robot knows when the recording starts. Progress goes to stderr; with ``--json``
stdout is one JSON object, as for every other command.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout

from . import advisor, bringup, contract as C, maneuvers, runs

SESSIONS = os.path.join(runs.RUNS, "sessions")
CURRENT = os.path.join(SESSIONS, "current.txt")

PHASES = (
    ("connect", "1. Connect: laptop, network, robot code"),
    ("bringup", "2. Bring-up: robot disabled, then on blocks"),
    ("tuning", "3. Tuning"),
    ("testing", "4. Testing on the floor"),
    ("field", "5. A field or a competition"),
    ("trouble", "6. Troubleshooting: cause a fault, the tool must spot it"),
)
VERDICTS = ("pass", "warn", "fail", "person", "skip", "error")
DONE = ("pass", "warn", "skip")
# Topics the newest robot code publishes. Missing ones mean the robot runs code from before them.
NEWEST_TOPICS = ((C.STATUS_DEADMAN_CONTROLLER, "the deadman's controller check"),
                 (C.SYSTEMS_HOMED, "homing"), (C.WATCH_RULES, "the robot's own module checks"))


class SessionError(Exception):
    pass


def _r(verdict, summary, details=(), run_files=(), evidence=None, then=None):
    """One check's result. ``person``: the tool did its part; a person must look and mark it."""
    assert verdict in VERDICTS, verdict
    return {"verdict": verdict, "summary": summary, "details": list(details), "runs": list(run_files),
            "evidence": evidence or {}, "then": then}


# ---------------------------------------------------------------------------- the record


class Record:
    """A session's file: who, which robot, how to reach it, and every check, mark and note in order."""

    def __init__(self, path, data):
        self.path = path
        self.data = data

    @staticmethod
    def new(project, conn, who=None, folder=None, clock=time.time):
        folder = folder or SESSIONS
        os.makedirs(folder, exist_ok=True)
        t = clock()
        stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(t))
        path = os.path.join(folder, f"{stamp}_{project.replace(' ', '-')}.json")
        rec = Record(path, {"version": 1, "project": project, "conn": conn, "who": who or "",
                            "started": t, "events": []})
        rec.save()
        with open(os.path.join(folder, "current.txt"), "w", encoding="utf-8") as fh:
            fh.write(os.path.basename(path))
        return rec

    @staticmethod
    def current(folder=None):
        folder = folder or SESSIONS
        try:
            with open(os.path.join(folder, "current.txt"), encoding="utf-8") as fh:
                name = fh.read().strip()
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                return Record(os.path.join(folder, name), json.load(fh))
        except (OSError, ValueError):
            raise SessionError("No session yet: start one with  session start --project \"Black team\"") from None

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(self.data, fh, indent=1, default=str)
        os.replace(tmp, self.path)

    def add(self, kind, step=None, clock=time.time, **kw):
        ev = {"t": clock(), "kind": kind, "step": step, **kw}
        self.data["events"].append(ev)
        self.save()
        return ev

    def state(self, step_id):
        """The step's latest verdict: a check's, or a person's mark, whichever came last."""
        for ev in reversed(self.data["events"]):
            if ev.get("step") == step_id and ev["kind"] in ("check", "mark"):
                return ev["verdict"]
        return None


# ---------------------------------------------------------------------------- the steps


class Step:
    def __init__(self, sid, phase, title, where, do, passes, check=None, env=None, countdown=0, optional=False):
        self.id, self.phase, self.title, self.where = sid, phase, title, where
        self.do, self.passes, self.check, self.env = list(do), passes, check, env
        self.countdown, self.optional = countdown, optional

    def card(self):
        return {"id": self.id, "phase": self.phase, "title": self.title, "where": self.where, "do": self.do,
                "passes": self.passes, "env": self.env, "tool_checks": self.check is not None,
                "countdown_s": self.countdown, "optional": self.optional}


def _failed_findings(rep, levels=("error",)):
    return [f for f in (rep or {}).get("findings", []) if f.get("level") in levels]


def _run(ctx, test, args=None, module="ALL"):
    """Run a robot test through ``run``: (outcome document, report). Saved like any other run."""
    argv = ["run", test, "--module", module]
    for k, v in (args or {}).items():
        argv += ["--arg", f"{k}={v}"]
    _code, doc = ctx.cli(*argv)
    return doc


def _run_result(doc, what, passes_if_done=True):
    """A run's verdict: refused or stopped is a fail with the robot's own words; errors in its
    report are a fail; warnings a warn."""
    files = [doc["run_file"]] if doc.get("run_file") else []
    if doc.get("accepted") is False or (not doc.get("ok") and not doc.get("outcome")):
        return _r("fail", f"{what}: {doc.get('error') or doc.get('message')}", run_files=files,
                  evidence={"code": doc.get("code")})
    if doc.get("outcome") != "DONE":
        return _r("fail", f"{what} stopped: {doc.get('message')}", run_files=files,
                  evidence={"code": doc.get("code"), "outcome": doc.get("outcome")})
    rep = doc.get("report") or {}
    errs, warns = _failed_findings(rep), _failed_findings(rep, ("warn",))
    details = [f"{f['level'].upper()}: {f['title']}" for f in errs + warns]
    score = rep.get("score")
    summary = f"{what}: done" + (f", score {score}/100" if score is not None else "") + (
        f". {rep['summary']}" if rep.get("summary") else "")
    verdict = "fail" if errs else "warn" if warns else ("pass" if passes_if_done else "person")
    return _r(verdict, summary, details, files, {"score": score, "targets": rep.get("targets")})


# ---- 1. connect


def c_network(ctx):
    if ctx.sim:
        return _r("skip", "The simulator runs on this laptop: there is no robot network to check.")
    _code, d = ctx.cli("netcheck")
    if d.get("error"):
        return _r("error", d["error"])
    checks = d.get("checks") or []
    bad = [c for c in checks if c.get("level") in ("fail", "error")]
    warn = [c for c in checks if c.get("level") == "warn"]
    details = [f"{c['level'].upper()}: {c['title']} - {c.get('why', '')}" for c in bad + warn]
    if d.get("fix"):
        details.append("As Administrator: " + d["fix"])
    summary = (f"Robot adapter {d.get('robot_adapter') or 'not found'}; internet adapter "
               f"{d.get('internet_adapter') or 'not found'}" + ("; VPN up" if d.get("vpn") else ""))
    return _r("fail" if bad else "warn" if warn else "pass", summary, details,
              evidence={"robot_adapter": d.get("robot_adapter"), "internet_adapter": d.get("internet_adapter")})


def c_link(ctx):
    _code, d = ctx.cli("status")
    if not d.get("ok"):
        return _r("fail", d.get("error") or "Couldn't reach the robot.", evidence={"code": d.get("code")})
    info, live = d["robot"], d["live"]
    details = ["startup: " + s for s in info.get("startup_report", [])]
    verdict = "pass"
    if info.get("name", "").lower() != ctx.project.lower():
        verdict = "fail"
        details.insert(0, f"The robot runs {info.get('name')!r}'s code, and this session is for {ctx.project!r}.")
    missing = ctx.missing_topics()
    if missing:
        verdict = "fail"
        details.insert(0, "The robot's code is older than this tool: it has no " + ", ".join(missing)
                       + ". Deploy " + ctx.project + " from the team repo's StuartTesting branch, then check again.")
    if live.get("mode") in (None, "UNKNOWN"):
        verdict = "fail" if verdict == "fail" else "warn"
        details.append("The robot doesn't say its mode: is the Driver Station connected?")
    summary = (f"{info.get('name')} at {info.get('address')}, mode {live.get('mode')}, battery {live.get('bus', 0):.1f} V,"
               f" image {info.get('image') or '?'}, WPILib {info.get('wpilib') or '?'}")
    return _r(verdict, summary, details, evidence={"robot": info.get("name"), "mode": live.get("mode")})


def c_config(ctx):
    _code, d = ctx.cli("lint")
    res = (d.get("projects") or {}).get(ctx.project_name()) or {}
    findings = res.get("findings") or []
    errs = [f for f in findings if f["level"] == "error"]
    warns = [f for f in findings if f["level"] == "warn"]
    details = [f"{f['level'].upper()}: {f['title']}" for f in errs + warns]
    return _r("fail" if errs else "warn" if warns else "pass",
              f"{len(errs)} errors, {len(warns)} warnings in the robot's configuration files", details)


def c_versions(ctx):
    _code, d = ctx.cli("versions")
    checks = d.get("checks") or []
    bad = [c for c in checks if c.get("level") in ("fail", "error")]
    warn = [c for c in checks if c.get("level") == "warn"]
    return _r("fail" if bad else "warn" if warn else "pass", f"{len(checks)} software versions checked",
              [f"{c['level'].upper()}: {c['title']}" for c in bad + warn])


def c_battery(ctx):
    with ctx.link() as lk:
        live = lk.live()
    v, mode = live.get("bus") or 0.0, live.get("mode")
    if mode not in ("DISABLED", None, "UNKNOWN"):
        return _r("warn", f"{v:.2f} V, but the robot is {mode}: read it disabled, at rest.")
    if v >= 12.4:
        return _r("pass", f"{v:.2f} V at rest: charged enough to test.")
    if v >= 12.0:
        return _r("warn", f"{v:.2f} V at rest: usable, but swap in a charged battery before tuning.")
    return _r("fail", f"{v:.2f} V at rest: charge it or swap it. Tests on a flat battery measure the battery.")


def c_deadman(ctx):
    with ctx.link() as lk:
        if not lk.get("bool", C.STATUS_DEADMAN_CONTROLLER, True):
            return _r("fail", "No controller on Driver Station port 1: the deadman is on that controller. "
                              "Plug it in and check the Driver Station's USB tab puts it at 1.")
        ctx.countdown(3, "press and HOLD the deadman button for about two seconds, then let go")
        seen, t0 = [], time.monotonic()
        while time.monotonic() - t0 < 8:
            seen.append(bool(lk.status().get("deadman_held")))
            time.sleep(0.05)
        ctx.beep(2)
    held = any(seen)
    released = held and not seen[-1]
    if held and released:
        return _r("pass", "The robot saw the deadman held, then let go.")
    if held:
        return _r("warn", "The robot saw it held, but not let go by the end.")
    return _r("fail", "The robot never saw the deadman held. Check which button the code uses (deadmanButton"
                      " in slothtune.json) and that its controller is at port 1.")


# ---- 2. bring-up


def c_controllers(ctx):
    from . import motorinv

    with ctx.link() as lk:
        live = lk.motors()["motors"]
    findings = motorinv.table(ctx.project_obj(), live)["findings"]
    missing = [m["name"] for m in live if m.get("present") != 1]
    flaky = [f"{m['name']} ({m.get('dropouts') or 0:.0f} dropouts, {m.get('resets') or 0:.0f} resets)" for m in live
             if (m.get("dropouts") or 0) > 0 or (m.get("resets") or 0) > 0]
    errs = [f for f in findings if f["level"] == "error"]
    warns = [f for f in findings if f["level"] == "warn"]
    details = [f"{f['level'].upper()}: {f['title']}" for f in errs + warns]
    if flaky:
        details.insert(0, "Dropped off CAN or reset since boot: " + ", ".join(flaky) + ". Wiggle-test their CAN and power.")
    if missing:
        details.insert(0, "Not answering on CAN: " + ", ".join(missing))
    firmware = sorted({m.get("firmware") for m in live if m.get("firmware")})
    summary = f"{len(live) - len(missing)} of {len(live)} controllers answer" + (
        f"; firmware {', '.join(firmware)}" if firmware else "; no firmware reported (the simulator has none)" if ctx.sim else "")
    verdict = "fail" if (errs or missing) else "warn" if (warns or flaky) else "pass"
    return _r(verdict, summary, details,
              evidence={"rows": [{k: m.get(k) for k in ("name", "can_id", "controller", "firmware", "present")} for m in live]})


def c_can(ctx):
    return _run_result(_run(ctx, "can_load"), "CAN bus load")


def c_health(ctx):
    return _run_result(_run(ctx, "capture", {"duration_s": 3}), "Three seconds standing still")


def _hand(ctx, kind, what):
    ctx.countdown(5, what)
    doc = _run(ctx, "capture", {"duration_s": 20, "coast": 1})
    ctx.beep(2)
    if doc.get("outcome") != "DONE":
        return _run_result(doc, "The recording")
    v = advisor.hand_check(runs.load(doc["run_file"]), kind, 1)
    files = [doc["run_file"]]
    if kind == "gyro":
        h = (v.get("gyro") or {}).get("heading") or {}
        ok = h.get("verdict") == "AGREES"
        why = {"INVERTED": "Counter-clockwise reads negative: field-relative driving would turn the wrong way."
                           " Flip invertedIMU (the Guide's hand check offers the edit).",
               "NO_MOTION": "It didn't turn far enough, or the gyro isn't reporting.",
               "AMBIGUOUS": "It was turned both ways: turn it one way only."}.get(h.get("verdict"), "")
        return _r("pass" if ok else "fail", f"Gyro {h.get('verdict', 'NO_DATA')}: turned {h.get('net', 0):.1f} deg",
                  [why] if why else [], files, {"gyro": h})
    rows, details = {}, []
    for name, r in v.items():
        if kind == "wheel":
            word = r["drive"]["verdict"]
        else:
            word = (r["absolute"]["verdict"] if r["absolute"]["verdict"] != "AGREES" else
                    "MOTOR " + r["motor"]["verdict"] if r["motor"]["verdict"] != "AGREES" else
                    "RATIO" if abs(r["motor_per_module_deg"] - 1) >= 0.03 else "AGREES")
        rows[name] = word
        if word != "AGREES":
            details.append(f"{name}: {word}")
    if details:
        details.append("INVERTED: flip that setting for that module. NO_MOTION: it didn't move far enough, or the"
                       " sensor isn't reporting. AMBIGUOUS: it was rocked; one way only. RATIO: the steering motor"
                       " turned a different amount than the module: check the gear ratio.")
    ok = bool(rows) and not [w for w in rows.values() if w != "AGREES"]
    return _r("pass" if ok else "fail", ", ".join(f"{n} {w}" for n, w in rows.items()) or "No modules in the recording",
              details, files, {"verdicts": rows})


def c_hand_wheels(ctx):
    return _hand(ctx, "wheel", "roll each wheel so its TOP moves toward the robot's front, about one turn, all four")


def c_hand_steer(ctx):
    return _hand(ctx, "steer", "turn each module counter-clockwise (seen from above) about a quarter turn, all four")


def c_hand_gyro(ctx):
    return _hand(ctx, "gyro", "turn the whole robot counter-clockwise (seen from above) about a quarter turn, by hand")


def c_offsets(ctx):
    ctx.countdown(3, "hold still: every wheel straight ahead, bevel gears facing the robot's left")
    doc = _run(ctx, "capture", {"duration_s": 4, "coast": 1})
    if doc.get("outcome") != "DONE":
        return _run_result(doc, "The capture")
    _code, d = ctx.cli("offsets", doc["run_file"])
    files = [doc["run_file"]]
    if not d.get("ok"):
        return _r("fail", d.get("error") or "No offsets.", run_files=files)
    offs = d.get("offsets") or {}
    moved = {n: r["new"] - r["old"] for n, r in offs.items()}
    big = {n: m for n, m in moved.items() if abs(((m + 180) % 360) - 180) > 1.0}
    details = [f"{n}: {offs[n]['old']:.2f} -> {offs[n]['new']:.2f} deg" for n in offs]
    if not big:
        return _r("pass", "Every module reads straight within 1 deg: the offsets are right.", details, files)
    return _r("person", f"{len(big)} offset(s) would change by more than 1 deg", details, files,
              then=f"If the wheels really were straight: slothtune offsets {doc['run_file']} --yes, then redeploy,"
                   " and run this step again.")


def c_directions(ctx):
    ctx.need_blocks()
    doc = _run(ctx, "drive_step", {"s0": 0.4, "s1": 0, "s2": -0.4, "s3": 0, "hold_s": 1.5})
    res = _run_result(doc, "Directions on blocks", passes_if_done=False)
    if res["verdict"] == "person":
        res["then"] = ("Watch: each wheel first rolls with its TOP toward the robot's front, then back. "
                       "Mark it: session mark directions pass (or fail, saying which wheel).")
    return res


def c_joysticks(ctx):
    ctx.countdown(3, "driver's controller (port 0): move both sticks around their full circle, both triggers, every button")
    doc = _run(ctx, "controller", {"port": 0, "duration_s": 12})
    ctx.beep(2)
    return _run_result(doc, "The driver's controller")


def c_pdh(ctx):
    ctx.need_blocks()
    return _run_result(_run(ctx, "pdh_map"), "Which PDH channel feeds each motor")


# ---- 3. tuning


def c_steer_blocks(ctx):
    ctx.need_blocks()
    return _run_result(_run(ctx, "steer_step"), "Steering steps on blocks")


def _field(ctx, test, what, args=None):
    ctx.need_field()
    return _run_result(_run(ctx, test, args), what)


def c_steer_floor(ctx):
    return _field(ctx, "steer_step", "Steering steps on the floor")


def c_slip(ctx):
    return _field(ctx, "slip", "Where the wheels slip (bumper against the wall)")


def c_ff(ctx):
    return _field(ctx, "drive_ff", "Drive feedforward")


def c_drive(ctx):
    return _field(ctx, "drive_step", "Drive speed steps")


def c_systems(ctx):
    import math

    with ctx.link() as lk:
        rows = lk.systems()
    if not rows:
        return _r("skip", "This robot's code registers no mechanisms (tune.system(...)).")
    details = []
    for s in rows:
        kind = s.get("kind") or "?"
        if kind in ("PIVOT", "ELEVATOR"):
            limits = all(isinstance(s.get(k), float) and math.isfinite(s[k]) for k in ("min", "max"))
            state = ("limits set" if limits else "NO limits yet") + ("" if s.get("homed", True) else ", NOT homed this boot")
        else:
            state = "no limits needed"
        details.append(f"{s.get('name')} ({kind}): {state}")
    return _r("person", f"{len(rows)} mechanism(s): tune each in the Systems tab", details,
              then="Systems tab, one mechanism at a time: limits (by hand) and homing for a pivot or elevator,"
                   " then its measuring run, then steps. Mark it when done: session mark systems pass.")


# ---- 4. testing


def c_spin(ctx):
    return _field(ctx, "spin", "Spin check")


def c_straight(ctx):
    res = _field(ctx, "straight", "Straight line, 10 ft", {"distance_m": 3.048})
    if res["runs"] and res["verdict"] in ("pass", "warn"):
        res["verdict"] = "person"
        res["then"] = (f"Tape where it stopped, then: slothtune analyze {res['runs'][0]} --tape-forward <in> "
                       "--tape-lateral <in, left +>. Mark it with what that says.")
    return res


def c_maneuver(ctx):
    name = ctx.opts.get("maneuver") or "OB_same_straight10ft"
    m = maneuvers.by_name(name)
    if not m:
        return _r("error", f"No maneuver called {name!r}.")
    res = _field(ctx, "maneuver", f"Maneuver {name}", {"id": maneuvers.ident(name)})
    if res["runs"] and res["verdict"] in ("pass", "warn"):
        res["verdict"] = "person"
        res["then"] = (f"Tape the end pose, then: slothtune analyze {res['runs'][0]} --tape-forward <in> "
                       "--tape-lateral <in> --tape-heading <deg>. Or score it in Calibrate, 10. Accuracy.")
    return res


# ---- 5. a field or competition


def c_pathplanner(ctx):
    _code, d = ctx.cli("ppcheck")
    if not d.get("pathplanner") and d.get("error"):
        return _r("error", d["error"])
    r = (d.get("pathplanner") or {}).get(ctx.project_name()) or {}
    if not r.get("used", True):
        return _r("skip", "This robot doesn't use PathPlanner.")
    findings = (r or {}).get("findings") or []
    errs = [f for f in findings if f["level"] == "error"]
    warns = [f for f in findings if f["level"] == "warn"]
    return _r("fail" if errs else "warn" if warns else "pass",
              f"PathPlanner against the code: {len(errs)} errors, {len(warns)} warnings",
              [f"{f['level'].upper()}: {f['title']}" for f in errs + warns])


def c_vision(ctx):
    with ctx.link() as lk:
        live = lk.live()
    counts = live.get("vision_counts") or []
    if not counts:
        return _r("skip", "This robot reports no cameras.")
    return _r("person", f"Cameras report {counts} (tags seen / accepted)",
              then="Calibrate tab, cameras and the field survey, at this venue: check each camera sees the tags"
                   " it should, then mark it.")


# ---- 6. troubleshooting


def c_watch(ctx):
    with ctx.link() as lk:
        live = lk.live()
    checks = live.get("watch") or []
    if not checks:
        return _r("fail", "The robot publishes none of its own module checks: its code is older than this tool."
                          " Deploy from StuartTesting.")
    active = [c for c in checks if c["active"]]
    details = [f"{c['rule']} {c['who'] or 'robot'}" for c in active]
    return _r("warn" if active else "pass",
              f"The robot runs {len({c['rule'] for c in checks})} checks of its own; {len(active)} raised now", details)


def _wait_for(lk, test, seconds, poll=0.1):
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        hit = test(lk)
        if hit:
            return hit, time.monotonic() - t0
        time.sleep(poll)
    return None, seconds


def c_fault_encoder(ctx):
    with ctx.link() as lk:
        ctx.countdown(3, "robot disabled: unplug ONE module's absolute encoder cable from its SPARK MAX")

        def flagged(lk):
            live = lk.live()
            names = lk.robot_info().get("modules") or []
            issue = [names[i] if i < len(names) else str(i) for i, x in enumerate(live.get("abs_issue") or []) if x]
            watch = [c["who"] for c in (live.get("watch") or []) if c["rule"] == "absolute_read_issue" and c["active"]]
            return sorted(set(issue) | set(watch))

        hit, after = _wait_for(lk, flagged, 15)
        ctx.beep(2)
    if hit:
        return _r("pass", f"Spotted after {after:.1f} s: {', '.join(hit)}. Plug it back in.",
                  then="Plug it back in, then check the flag clears: session check watch.")
    return _r("fail", "Nothing flagged within 15 s of an unplugged absolute encoder: a Sloth Tune defect, or"
                      " the cable wasn't the encoder's. Log it: session issue \"...\".")


def c_fault_controller(ctx):
    with ctx.link() as lk:
        ctx.countdown(3, "unplug the deadman's controller (port 1) from the Driver Station laptop")
        hit, after = _wait_for(lk, lambda lk: lk.get("bool", C.STATUS_DEADMAN_CONTROLLER, True) is False, 15)
        ctx.beep(2)
    if hit:
        return _r("pass", f"The robot said the deadman's controller is gone after {after:.1f} s; the top bar says"
                          " 'Deadman: no port 1 controller'.", then="Plug it back in at port 1.")
    return _r("fail", "The robot never said the port 1 controller was gone.")


def c_fault_deadman(ctx):
    ctx.need_blocks()
    ctx.say("Hold the deadman: the wheels will spin slowly on blocks. Let go after about two seconds of motion.")
    doc = _run(ctx, "drive_step", {"s0": 0.3, "hold_s": 8})
    if doc.get("code") == "DEADMAN" or "eadman released" in str(doc.get("message")):
        return _r("pass", "The test stopped the moment the deadman was let go.", run_files=[doc.get("run_file")] if doc.get("run_file") else [])
    if doc.get("outcome") == "DONE":
        return _r("fail", "The test ran to the end: the deadman was never let go, or letting go didn't stop it.")
    return _r("fail", f"It stopped for another reason: {doc.get('message') or doc.get('error')}")


def c_fault_link(ctx):
    with ctx.link() as lk:
        before = lk.environment().get("active")
        ctx.countdown(3, "unplug the laptop's robot network cable (or turn off its robot Wi-Fi) for five seconds, then reconnect")
        gone, t_gone = _wait_for(lk, lambda lk: not lk.is_connected(), 30)
        if not gone:
            return _r("fail", "The link never dropped: was it the robot network's cable?")
        back, t_back = _wait_for(lk, lambda lk: lk.is_connected(), 60)
        if not back:
            return _r("fail", "The link didn't come back within a minute.")
        time.sleep(1.0)
        after = lk.environment().get("active")
        ctx.beep(2)
    detail = [f"Dropped after {t_gone:.1f} s, back {t_back:.1f} s later; environment {before} before, {after} after."]
    if before not in (None, "UNSET", "SIM") and after != "UNSET":
        return _r("fail", "After the link came back the robot still believed its old environment.", detail)
    return _r("pass", "The tool reconnected by itself" + (", and the robot forgot where it was, as it must"
                                                          if before not in (None, "UNSET", "SIM") else ""), detail)


def c_diagnose(ctx):
    from . import diagnose, monitor, yagslcfg

    lint = yagslcfg.lint(ctx.project_obj())
    with ctx.link() as lk:
        info = lk.robot_info()
        mon = monitor.Monitor()
        flags = []
        for _ in range(40):
            flags = mon.update(lk.live(), info["modules"], lk.environment()["active"])
            time.sleep(0.05)
    hits = []
    for s in diagnose.SYMPTOMS:
        ev = diagnose.evaluate(s["id"], lint, flags)
        if ev.get("first_failing") is not None:
            c = ev["checks"][ev["first_failing"]]
            hits.append(f"{s['title']}: {c['q']} -> {c['fix']}")
    return _r("warn" if hits else "pass",
              f"The troubleshooter, on this robot as it is now: {len(hits)} of {len(diagnose.SYMPTOMS)} symptoms"
              " have evidence", hits)


STEPS = (
    Step("network", "connect", "Two networks at once", "Laptop: robot adapter and internet adapter",
         ["Laptop on the robot's network (Ethernet to the radio for the first session) and on the internet."],
         "A robot adapter on 10.TE.AM.x, the internet on the other, routes kept apart.", c_network),
    Step("link", "connect", "The robot answers, with this robot's newest code", "Robot on, Driver Station connected",
         ["Robot on; Driver Station open and connected.", f"Robot code deployed from the team repo's StuartTesting branch."],
         "Connected; the robot's name matches; nothing missing that the newest code publishes.", c_link),
    Step("config", "connect", "The configuration files", "Laptop", ["Nothing: the tool reads the robot's files."],
         "No errors in the YAGSL files or slothtune.json.", c_config),
    Step("versions", "connect", "Software versions", "Laptop", ["Nothing."], "Every library is this season's.", c_versions),
    Step("battery", "connect", "The battery", "Robot disabled, at rest", ["A charged battery in."],
         "12.4 V or more at rest.", c_battery),
    Step("deadman", "connect", "The deadman", "Robot disabled",
         ["The deadman's controller on Driver Station port 1.", "When it beeps: hold the deadman button two seconds, let go."],
         "The robot sees it held, then let go.", c_deadman, countdown=3),

    Step("controllers", "bringup", "Every controller heard, firmware right", "Robot disabled",
         ["Nothing: every SPARK reports itself."], "Every controller the code creates answers, none on 27.x firmware.", c_controllers),
    Step("can", "bringup", "CAN bus load", "Robot disabled", ["Nothing."], "Load well under the bus's limit.", c_can),
    Step("health", "bringup", "Sensor health", "Robot disabled, not moving", ["Don't touch the robot for 3 s."],
         "No noisy or slipping encoder.", c_health, env="DISABLED"),
    Step("hand-wheels", "bringup", "Hand check: wheels", "Robot disabled, motors coasting",
         ["Point every wheel straight ahead, bevel gears to the robot's LEFT.", "When it beeps: roll each wheel so its TOP moves toward the front, one turn, all four."],
         "Every drive encoder AGREES.", c_hand_wheels, env="DISABLED", countdown=5),
    Step("hand-steer", "bringup", "Hand check: steering", "Robot disabled, motors coasting",
         ["When it beeps: turn each module counter-clockwise (from above) a quarter turn, all four."],
         "Every absolute encoder and steering motor AGREES, ratio right.", c_hand_steer, env="DISABLED", countdown=5),
    Step("hand-gyro", "bringup", "Hand check: gyro", "Robot disabled, on the floor",
         ["When it beeps: turn the whole robot counter-clockwise (from above) a quarter turn."],
         "The heading goes up (counter-clockwise positive).", c_hand_gyro, env="DISABLED", countdown=5),
    Step("offsets", "bringup", "Wheel offsets", "Robot disabled, motors coasting",
         ["Every wheel straight ahead with a straight-edge, bevel gears to the LEFT; hold still."],
         "Every module already reads straight within 1 deg, or new offsets written and redeployed.", c_offsets, env="DISABLED", countdown=3),
    Step("directions", "bringup", "Every wheel drives the right way", "On blocks, deadman held",
         ["Robot on blocks, wheels free.", "Enable in the Driver Station; hold the deadman.", "Watch each wheel."],
         "Each wheel's top rolls toward the front, then back.", c_directions, env="BLOCKS"),
    Step("joysticks", "bringup", "The driver's controller", "Robot disabled",
         ["When it beeps: both sticks full circle, both triggers, every button."], "Every axis and button reads, no drift.", c_joysticks, countdown=3),
    Step("pdh", "bringup", "PDH channels", "On blocks, deadman held",
         ["On blocks, enabled, deadman held: each motor turns briefly."], "Each motor's PDH channel found.", c_pdh, env="BLOCKS", optional=True),

    Step("steer-blocks", "tuning", "Steering, on blocks", "On blocks, deadman held", ["On blocks, enabled, deadman held."],
         "Steering steps meet their targets.", c_steer_blocks, env="BLOCKS"),
    Step("steer-floor", "tuning", "Steering, on the floor", "On the floor, the robot doesn't drive",
         ["Robot on the floor, bumpers on; environment FIELD with the clear floor measured."], "Steps meet their targets on carpet.", c_steer_floor, env="FIELD"),
    Step("slip", "tuning", "Where the wheels slip", "On the floor, front bumper against a solid wall",
         ["Front bumper flat against a wall."], "A slip current found; a limit just under it suggested.", c_slip, env="FIELD"),
    Step("ff", "tuning", "Drive feedforward", "On the floor, about 10 ft clear", ["10 ft clear ahead."],
         "kS, kV, kA measured with a good fit.", c_ff, env="FIELD"),
    Step("drive", "tuning", "Drive speed", "On the floor", ["Clear floor ahead."], "Speed steps meet their targets.", c_drive, env="FIELD"),
    Step("systems", "tuning", "Mechanisms", "Depends on the mechanism", ["Systems tab, each mechanism in turn."],
         "Each mechanism's limits, homing (pivots, elevators), measuring run and steps done.", c_systems),

    Step("spin", "testing", "Spin check", "On the floor, clear all round", ["Clear all round."], "Every module agrees while spinning.", c_spin, env="FIELD"),
    Step("straight", "testing", "Straight line, 10 ft", "On the floor, 10 ft clear", ["Mark the start; tape where it stops."],
         "Within 1 in per 10 ft of the tape.", c_straight, env="FIELD"),
    Step("maneuver", "testing", "A maneuver, scored", "On the floor, room for the maneuver", ["Tape the end pose."],
         "Within 1 in per 10 ft driven and 0.5 deg of heading.", c_maneuver, env="FIELD"),
    Step("sticks", "testing", "Drive it with the sticks", "On the floor, clear all round",
         ["Field-relative: stick forward drives away from the driver, right goes right, right stick right turns clockwise."],
         "A person drives it and every direction is right.", None, env="FIELD"),

    Step("pathplanner", "field", "PathPlanner describes this robot", "Laptop", ["Nothing."],
         "PathPlanner's robot matches the code; the first auto after a boot will run.", c_pathplanner),
    Step("vision", "field", "Cameras at this venue", "On the field", ["Robot where it can see tags."],
         "Each camera sees the tags it should.", c_vision, optional=True),
    Step("venue", "field", "This venue's floor", "On the field",
         ["Measure the clear floor; set the environment: slothtune env --mode FIELD --space <in> --side <in> --bumpers."],
         "Slip and feedforward re-measured on this carpet if it differs from the shop's.", None, optional=True),

    Step("watch", "trouble", "The robot's own checks", "Any", ["Nothing."], "The robot runs its checks; none raised at rest.", c_watch),
    Step("fault-encoder", "trouble", "Unplug an absolute encoder", "Robot disabled",
         ["When it beeps: unplug one module's absolute encoder cable. Plug it back after."], "The tool names that module within 15 s.",
         c_fault_encoder, env="DISABLED", countdown=3),
    Step("fault-controller", "trouble", "Unplug the deadman's controller", "Robot disabled",
         ["When it beeps: unplug the port 1 controller. Plug it back after."], "The robot says it's gone.", c_fault_controller, countdown=3),
    Step("fault-deadman", "trouble", "Let go of the deadman mid-test", "On blocks, deadman held",
         ["On blocks, enabled; hold the deadman, then let go once the wheels turn."], "The test stops at once.", c_fault_deadman, env="BLOCKS"),
    Step("fault-link", "trouble", "Drop the robot link", "Robot disabled",
         ["When it beeps: unplug the laptop's robot network for 5 s, then reconnect."],
         "The tool reconnects; the robot forgets its environment.", c_fault_link, countdown=3),
    Step("diagnose", "trouble", "The troubleshooter on this robot", "Any", ["Nothing."],
         "Nothing it can see is wrong, or it says exactly what.", c_diagnose),
)
BY_ID = {s.id: s for s in STEPS}


def next_step(rec):
    """The first step in order that isn't done (passed, warned or skipped), optional ones last."""
    todo = [s for s in STEPS if rec.state(s.id) not in DONE]
    required = [s for s in todo if not s.optional]
    return (required or todo or [None])[0]


# ---------------------------------------------------------------------------- running a check


class Ctx:
    """What a check needs: the command line, a link to the robot, and a way to talk to the person."""

    def __init__(self, rec, args, opts=None, err=sys.stderr):
        self.rec, self.args, self.opts, self.err = rec, args, opts or {}, err
        conn = rec.data.get("conn") or {}
        self.project = rec.data["project"]
        self.sim = bool(conn.get("sim"))
        self.conn_argv = ["--project", self.project] + (["--sim"] if self.sim else []) + (
            ["--host", conn["host"]] if conn.get("host") else []) + (["--team", str(conn["team"])] if conn.get("team") else [])

    def say(self, text):
        print(text, file=self.err, flush=True)

    def beep(self, n=1):
        try:
            import winsound
            for _ in range(n):
                winsound.Beep(1000, 180)
                time.sleep(0.08)
        except Exception:  # noqa: BLE001 - no speaker, or not Windows: the printed line is enough
            print("\a" * n, end="", file=self.err, flush=True)

    def countdown(self, seconds, what):
        self.say(f"\n>>> {what}")
        for s in range(int(seconds), 0, -1):
            self.say(f"    starting in {s}...")
            self.beep(1) if s <= 3 else None
            time.sleep(1)
        self.beep(1)
        self.say(">>> GO")

    def cli(self, *argv):
        from . import cli

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main([*argv, *self.conn_argv, "--json"])
        text = buf.getvalue().strip()
        try:
            return code, json.loads(text[text.index("{"):]) if text else {}
        except ValueError:
            return code, {"ok": False, "error": f"The command printed something that isn't JSON: {text[:200]}"}

    def project_name(self):
        return self.project_obj().name

    def project_obj(self):
        from . import cli

        return cli.resolve_project(self.project)

    def link(self):
        from . import cli

        ns = argparse.Namespace(project=self.project, team=(self.rec.data.get("conn") or {}).get("team"),
                                host=(self.rec.data.get("conn") or {}).get("host"), sim=self.sim, connect_timeout=8.0)
        sink = cli.Out(True)
        with redirect_stdout(io.StringIO()):
            lk = cli.open_link(ns, sink)
        if not lk:
            raise SessionError(sink.data.get("error") or "Couldn't reach the robot.")
        return _Closing(lk)

    def missing_topics(self):
        with self.link() as lk:
            return [what for topic, what in NEWEST_TOPICS if not lk.inst.getTopic(topic).exists()]

    def need_blocks(self):
        if not self.opts.get("blocks"):
            raise SessionError("This step drives the wheels on blocks. Put the robot on blocks with the wheels free,"
                               " then run it again with --blocks (a person checked).")
        _code, d = self.cli("env", "--mode", "BLOCKS")
        if not d.get("ok"):
            raise SessionError(d.get("error") or "The robot didn't take BLOCKS.")

    def need_field(self):
        with self.link() as lk:
            env = lk.environment()
        if env.get("active") not in ("FIELD", "SIM"):
            raise SessionError("This step runs on the floor. Measure the clear floor, then: slothtune env --mode FIELD "
                               f"--space <inches ahead> --side <inches each side> --bumpers --project \"{self.project}\"."
                               f" The robot says it is {env.get('active')}.")


class _Closing:
    def __init__(self, lk):
        self.lk = lk

    def __enter__(self):
        return self.lk

    def __exit__(self, *exc):
        self.lk.close()
        return False


def run_check(rec, step, args, opts=None, err=sys.stderr):
    if step.check is None:
        raise SessionError(f"{step.id} is a person's call: watch, then  session mark {step.id} pass|fail --note \"...\"")
    ctx = Ctx(rec, args, opts, err)
    started = time.time()
    try:
        res = step.check(ctx)
    except SessionError as e:
        res = _r("error", str(e))
    except Exception as e:  # noqa: BLE001 - a crash in a check is a Sloth Tune defect: record it, keep the session
        res = _r("error", f"{type(e).__name__}: {e}", then="This is a Sloth Tune defect: log it with  session issue.")
    res["seconds"] = round(time.time() - started, 1)
    rec.add("check", step.id, **res)
    return res


# ---------------------------------------------------------------------------- the report


def _when(t):
    return bringup._local_and_utc(t)


def report_markdown(rec):
    d = rec.data
    lines = [f"# Sloth Tune session: {d['project']}", "",
             f"Started {_when(d['started'])}" + (f" by {d['who']}" if d.get("who") else "")
             + (" (simulator)" if (d.get("conn") or {}).get("sim") else "") + ".", ""]
    counts = {}
    for s in STEPS:
        counts[rec.state(s.id) or "not run"] = counts.get(rec.state(s.id) or "not run", 0) + 1
    lines += ["**" + ", ".join(f"{n} {k}" for k, n in counts.items()) + "**", ""]
    for key, title in PHASES:
        lines += [f"## {title}", "", "| Step | Result | What it found |", "|---|---|---|"]
        for s in [s for s in STEPS if s.phase == key]:
            last = next((e for e in reversed(d["events"]) if e.get("step") == s.id and e["kind"] in ("check", "mark")), None)
            found = (last.get("summary") or last.get("note") or "").replace("|", "/") if last else ""
            lines.append(f"| {s.title} | {last['verdict'] if last else 'not run'} | {found} |")
        lines.append("")
    issues = [e for e in d["events"] if e["kind"] == "issue"]
    lines += ["## Sloth Tune issues found", ""] + ([f"- {_when(e['t'])}: {e['text']}" + (f" (step {e['step']})" if e.get("step") else "")
                                                     for e in issues] or ["None."]) + [""]
    lines += ["## Everything, in order", ""]
    for e in d["events"]:
        what = e.get("summary") or e.get("note") or e.get("text") or ""
        lines.append(f"- {_when(e['t'])} **{e['kind']}** {e.get('step') or ''} {e.get('verdict') or ''}: {what}")
        for x in e.get("details") or []:
            lines.append(f"  - {x}")
        if e.get("then"):
            lines.append(f"  - next: {e['then']}")
        for f in e.get("runs") or []:
            lines.append(f"  - run: {f}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------- the command


def add_parser(sub):
    s = sub.add_parser("session", help="a bring-up session on a live robot: steps in order, checks, a record")
    s.add_argument("action", choices=["start", "plan", "next", "show", "check", "mark", "note", "issue", "report"])
    s.add_argument("what", nargs="*", help="a step id; for mark: step and pass|fail|skip; for note/issue: the text")
    s.add_argument("--who", help="start: who is at the robot")
    s.add_argument("--note", help="mark: what the person saw")
    s.add_argument("--blocks", action="store_true", help="check: a person checked the robot is on blocks, wheels free")
    s.add_argument("--maneuver", help="check maneuver: which one (default OB_same_straight10ft)")
    s.add_argument("--out", help="report: where to write it (default: beside the session's record)")
    return s


def _print_card(out, step, state):
    out.say(f"\n[{state or 'not run'}] {step.id}: {step.title}   ({dict(PHASES)[step.phase]})")
    out.say(f"  where: {step.where}")
    for x in step.do:
        out.say(f"  do:    {x}")
    out.say(f"  pass:  {step.passes}")
    out.say(f"  run:   session check {step.id}" + (" --blocks" if step.env == "BLOCKS" else "")
            if step.check else f"  mark:  session mark {step.id} pass|fail --note \"...\"")


def cmd_session(args, out):
    try:
        return _session(args, out)
    except SessionError as e:
        return out.done(out.fail(str(e), code="SESSION"))


def _session(args, out):
    action, what = args.action, list(args.what or [])
    if action == "start":
        if not args.project:
            return out.done(out.fail("start needs --project, e.g. --project \"Black team\"."))
        from . import cli

        proj = cli.resolve_project(args.project)
        rec = Record.new(proj.name, {"sim": bool(args.sim), "host": args.host, "team": args.team}, args.who)
        rec.add("start", note=f"Session for {proj.name}" + (" in the simulator" if args.sim else ""))
        out.put(session=os.path.basename(rec.path), path=rec.path, steps=[s.card() for s in STEPS])
        out.say(f"Session started: {rec.path}")
        step = next_step(rec)
        _print_card(out, step, None)
        return out.done()
    rec = Record.current()
    if action == "plan":
        rows = [{**s.card(), "state": rec.state(s.id)} for s in STEPS]
        out.put(project=rec.data["project"], steps=rows, next=(next_step(rec) or Step("", "", "", "", [], "")).id or None)
        for key, title in PHASES:
            out.say(f"\n{title}")
            for s in [s for s in STEPS if s.phase == key]:
                out.say(f"  [{(rec.state(s.id) or ' ')[:6]:6s}] {s.id:17s} {s.title}" + ("  (optional)" if s.optional else ""))
        return out.done()
    if action in ("next", "show"):
        step = next_step(rec) if action == "next" else BY_ID.get(what[0] if what else "")
        if not step:
            return out.done(out.fail("Every step is done: session report." if action == "next" else
                                     "Which step? " + ", ".join(BY_ID)))
        out.put(step={**step.card(), "state": rec.state(step.id)})
        _print_card(out, step, rec.state(step.id))
        return out.done()
    if action == "check":
        if not what or what[0] not in BY_ID:
            return out.done(out.fail("Which step? " + ", ".join(BY_ID)))
        step = BY_ID[what[0]]
        res = run_check(rec, step, args, {"blocks": args.blocks, "maneuver": args.maneuver})
        out.put(step=step.id, **res)
        out.say(f"\n{step.id}: {res['verdict'].upper()}  {res['summary']}")
        for x in res["details"]:
            out.say(f"  - {x}")
        if res.get("then"):
            out.say(f"  next: {res['then']}")
        nxt = next_step(rec)
        out.say(f"\nnext step: {nxt.id}" if nxt else "\nEvery step is done: session report")
        return out.done(0 if res["verdict"] in ("pass", "warn", "skip", "person") else 1)
    if action == "mark":
        if len(what) < 2 or what[0] not in BY_ID or what[1] not in ("pass", "fail", "skip", "warn"):
            return out.done(out.fail("mark STEP pass|fail|skip|warn --note \"what you saw\""))
        ev = rec.add("mark", what[0], verdict=what[1], note=args.note or "")
        out.put(event=ev)
        out.say(f"{what[0]}: {what[1]}" + (f" ({args.note})" if args.note else ""))
        return out.done()
    if action in ("note", "issue"):
        step = what[0] if what and what[0] in BY_ID and len(what) > 1 else None
        text = " ".join(what[1:] if step else what).strip()
        if not text:
            return out.done(out.fail(f"{action} needs some text."))
        ev = rec.add(action, step, text=text)
        out.put(event=ev)
        out.say(f"{'Issue' if action == 'issue' else 'Note'} recorded.")
        return out.done()
    if action == "report":
        text = report_markdown(rec)
        path = args.out or os.path.splitext(rec.path)[0] + ".md"
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        out.put(report=path)
        out.say(text)
        out.say(f"Written to {path}")
        return out.done()
    return out.done(out.fail(f"unknown action {action}"))
