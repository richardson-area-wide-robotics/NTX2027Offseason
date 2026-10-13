"""Where to start and what to do next: in each calibration and configuration tool, and for one part.

Two kinds of checklist, both worked out from evidence, never from a click alone: the robot's
files, the runs saved on this laptop, the progress marks the tools record when a measurement
checks out, and the live robot.

* A **tool plan** (Calibrate, Config, Motors, Wiring, Controllers) lists that tool's jobs in the
  order they depend on each other.
* A **part plan** redoes one part without the whole path: a module that was replaced or acts
  up, a motor, the gyro, a camera, a new field, new wheels. It counts only what was done to that
  part since the person started it, and its steps link into the same tools, set to that part.

Every job has a status:

    done       measured or set, and it checked out
    attention  measured, and something needs fixing
    todo       not done yet
    later      waits for something else first (``unblock`` says what)
    optional   worth doing, not needed
    skip       doesn't apply to this robot (no camera listed)

``next`` is the first todo or attention job. With none left, ``after`` says where to go next.
"""

import os
import time

STAMP = "%Y%m%d-%H%M%S"
# The short names the tuner and the robot also take (web/app.js ABBR).
ABBR = {"frontleft": "FL", "frontright": "FR", "backleft": "BL", "backright": "BR"}
WORK = ("attention", "todo")


def stamp(t=None):
    return time.strftime(STAMP, time.localtime(t))


def _job(jid, title, status, detail="", go=None, how=None, unblock=None, optional=False):
    j = {"id": jid, "title": title, "status": status, "detail": detail}
    if go:
        j["go"] = go
    if how:
        j["how"] = how
    if unblock:
        j["unblock"] = unblock
    if optional:
        j["optional"] = True
    return j


def _plan(title, what, bring, jobs, after):
    nxt = next((j for j in jobs if j["status"] in WORK), None)
    # Counted: every job that applies, an optional one only once it is done.
    counted = [j for j in jobs if j["status"] != "skip" and not (j.get("optional") and j["status"] != "done")]
    done = sum(1 for j in counted if j["status"] == "done")
    return {"title": title, "what": what, "bring": bring, "jobs": jobs, "next": nxt,
            "after": None if nxt else after, "done": done, "of": len(counted)}


def _mark(prog, key, since=None):
    """A tool's progress mark ``{"result", "when", ...}``, or None (or older than ``since``)."""
    m = (prog or {}).get(key)
    if not isinstance(m, dict) or not m.get("when"):
        return None
    if since and str(m["when"]) < str(since):
        return None
    return m


def _mark_status(m, fail_detail="measured: it needs a fix"):
    if not m:
        return None
    return ("done", m.get("detail") or f"Done {_when(m['when'])}") if m.get("result") == "pass" \
        else ("attention", m.get("detail") or fail_detail)


def _when(s):
    s = str(s or "")
    return f"{s[4:6]}/{s[6:8]} {s[9:11]}:{s[11:13]}" if len(s) >= 13 else s


def _runs(ctx, test=None, env=None, module=None, since=None):
    """This robot's real runs, newest first, that finished."""
    out = []
    for r in ctx.get("runs") or []:
        if r.get("practice") or r.get("outcome") != "DONE":
            continue
        if ctx.get("robot") and r.get("robot") not in (None, ctx["robot"]):
            continue
        if test and r.get("test") != test:
            continue
        if env and r.get("env") != env:
            continue
        if module is not None and (r.get("module") or "ALL") not in (module, ABBR.get(module, module), "ALL"):
            continue
        if since and str(r.get("saved") or "") < str(since):
            continue
        out.append(r)
    return out


def _tune(ctx):
    p = ctx.get("project")
    return ((p.data.get("swervetune.json") or {}) if p else {}) or {}


def _guide_done(prog, key, ok=("pass", "verified", "done")):
    return (prog or {}).get(key) in ok


# ---------------------------------------------------------------------------- tools


def calibrate(ctx):
    prog, tune = ctx.get("prog") or {}, _tune(ctx)
    jobs = []
    offsets_ok = _guide_done(prog, "offsets", ("verified", "written"))

    st = _mark_status(_mark(prog, "cal_positions"), "the tape differs from the files: save the new positions")
    jobs.append(_job("positions", "1. Module positions", *(st or ("todo", "A tape measure; the robot anywhere.")),
                     go={"tab": "calibrate", "panel": "cal-positions"}))

    st = _mark_status(_mark(prog, "cal_wheels"), "measured: save the wheel size")
    if st:
        jobs.append(_job("wheels", "2. Wheel sizes", *st, go={"tab": "calibrate", "panel": "cal-wheels"}))
    elif not offsets_ok:
        jobs.append(_job("wheels", "2. Wheel sizes", "later", "A crooked wheel measures short: set the offsets first.",
                         go={"tab": "calibrate", "panel": "cal-wheels"},
                         unblock={"guide": "offsets", "label": "Guide step 4: Set the wheel offsets"}))
    else:
        jobs.append(_job("wheels", "2. Wheel sizes", "todo", "3 m of floor, a tape measure; robot disabled.",
                         go={"tab": "calibrate", "panel": "cal-wheels"}))

    st = _mark_status(_mark(prog, "cal_spin"), "the gyro and the wheels disagree: recheck 1 and 2")
    if st:
        jobs.append(_job("spin", "3. Check with a spin", *st, go={"tab": "calibrate", "panel": "cal-spin"}))
    elif _runs(ctx, "spin", "FIELD"):
        jobs.append(_job("spin", "3. Check with a spin", "todo", "A floor spin is saved: check it.",
                         go={"tab": "calibrate", "panel": "cal-spin"}))
    else:
        jobs.append(_job("spin", "3. Check with a spin", "later", "Needs a Spin run on the floor first.",
                         go={"tab": "calibrate", "panel": "cal-spin"},
                         unblock={"guide": "spin", "label": "Guide step 12: Spin check"}))

    still, turns = _mark(prog, "cal_gyro_still"), _mark(prog, "cal_gyro_turns")
    if still and turns:
        bad = [m for m in (still, turns) if m.get("result") != "pass"]
        jobs.append(_job("gyro", "4. Gyro", "attention" if bad else "done",
                         "; ".join(m.get("detail", "") for m in bad) or "Drift and full turns check out.",
                         go={"tab": "calibrate", "panel": "cal-gyro"}))
    else:
        left = [w for w, m in (("a minute standing still", still), ("full turns", turns)) if not m]
        jobs.append(_job("gyro", "4. Gyro", "attention" if (still or turns) and (still or turns).get("result") != "pass" else "todo",
                         "Still to do: " + " and ".join(left) + ".", go={"tab": "calibrate", "panel": "cal-gyro"}))

    mass, moi = tune.get("robotMassKg"), tune.get("robotMoiKgM2")
    if mass and moi:
        jobs.append(_job("moi", "5. Mass and moment of inertia", "done", f"{mass} kg, {moi} kg·m².",
                         go={"tab": "calibrate", "panel": "cal-moi"}))
    elif not mass:
        jobs.append(_job("moi", "5. Mass and moment of inertia", "todo", "Weigh the robot with bumpers and battery.",
                         go={"tab": "calibrate", "panel": "cal-moi"}))
    elif _runs(ctx, "drive_ff", "FIELD"):
        jobs.append(_job("moi", "5. Mass and moment of inertia", "todo", f"Weighed ({mass} kg); now spin and measure.",
                         go={"tab": "calibrate", "panel": "cal-moi"}))
    else:
        jobs.append(_job("moi", "5. Mass and moment of inertia", "later",
                         f"Weighed ({mass} kg). The spin compares against the floor feedforward, so that first.",
                         go={"tab": "calibrate", "panel": "cal-moi"},
                         unblock={"guide": "ff", "label": "Guide step 10: Measure the feedforward"}))

    cams = [str(c) for c in ((tune.get("vision") or {}).get("cameras") or [])]
    if not cams:
        jobs.append(_job("camera", "6. Camera positions", "skip",
                         "No camera listed in swervetune.json (\"vision\": {\"cameras\": [...]}).",
                         go={"tab": "calibrate", "panel": "cal-camera"}))
    else:
        left = [c for c in cams if not _mark(prog, f"cal_camera_{c}")]
        jobs.append(_job("camera", "6. Camera positions", "todo" if left else "done",
                         ("Not measured yet: " + ", ".join(left)) if left else "Every camera measured.",
                         go={"tab": "calibrate", "panel": "cal-camera"}))

    if ctx.get("layout_saved"):
        jobs.append(_job("field", "7. Field tags", "done",
                         "A surveyed layout is saved. Upload it to each camera too (vision doc).",
                         go={"tab": "calibrate", "panel": "cal-field"}))
    else:
        jobs.append(_job("field", "7. Field tags", "optional",
                         "On a field with tags, at an event or a practice field: needs a camera.",
                         go={"tab": "calibrate", "panel": "cal-field"}, optional=True))

    return _plan("Calibrate: measure the robot itself",
                 "Where the modules sit, how big the wheels are, how well the gyro reads, the robot's mass "
                 "and inertia, and where each camera looks: odometry, PathPlanner and vision all start from these. "
                 "Measure in this order: each uses the ones before it. Every panel's Practice runs it on made-up "
                 "data with a known answer, to see what a good result looks like first.",
                 ["A tape measure", "3 m of straight floor", "A scale", "A tag on a wall (for a camera)"],
                 jobs, {"guide": "", "label": "Back to the Guide"})


def config(ctx):
    p = ctx.get("project")
    if not p:
        return _plan("Config", "What the robot's files say.", [],
                     [_job("project", "Pick the robot", "todo", "Pick the robot project at the top of the page.")], None)
    lint = ctx.get("lint") or []
    own = [f for f in lint if not str(f.get("id", "")).startswith("pathplanner")]
    errors = [f for f in own if f.get("level") == "error"]
    warns = [f for f in own if f.get("level") == "warn"]
    jobs = [_job("errors", "Fix what doesn't add up", "attention" if errors else "done",
                 f"{len(errors)} error{'s' if len(errors) != 1 else ''} in the files: each says how to fix it."
                 if errors else "No errors in the swerve files.", go={"tab": "config", "panel": "cfg-findings"}),
            _job("warnings", "Read the warnings", "optional",
                 f"{len(warns)} to read. Most are settled by the Guide's tests; none stop a test." if warns
                 else "None.", go={"tab": "config", "panel": "cfg-findings"}, optional=True)]

    pp = ctx.get("pp")
    if not pp or not pp.get("used"):
        jobs.append(_job("pathplanner", "PathPlanner matches the code", "skip", "This robot doesn't use PathPlanner.",
                         go={"tab": "config", "panel": "pp-panel"}))
    else:
        rows = pp.get("rows") or []
        differs = [r for r in rows if r.get("status") in ("differs", "missing")]
        unknown = [r for r in rows if r.get("status") == "unknown"]
        pp_err = [f for f in pp.get("findings") or [] if f.get("level") == "error"]
        if differs or pp_err:
            jobs.append(_job("pathplanner", "PathPlanner matches the code", "attention",
                             f"{len(differs)} setting{'s' if len(differs) != 1 else ''} differ"
                             + (f", {len(pp_err)} error{'s' if len(pp_err) != 1 else ''}" if pp_err else "")
                             + ": Make PathPlanner match the code.", go={"tab": "config", "panel": "pp-panel"}))
        elif unknown:
            jobs.append(_job("pathplanner", "PathPlanner matches the code", "later",
                             "Matches, except " + ", ".join(r.get("key", "") for r in unknown)
                             + ": measured in Calibrate, then sent here.", go={"tab": "config", "panel": "pp-panel"},
                             unblock={"tab": "calibrate", "panel": "cal-moi", "label": "Calibrate 5: Mass and moment of inertia"}))
        else:
            jobs.append(_job("pathplanner", "PathPlanner matches the code", "done", "Every setting matches.",
                             go={"tab": "config", "panel": "pp-panel"}))

    tune = _tune(ctx)
    batteries = tune.get("batteries") or []
    if not batteries:
        jobs.append(_job("batteries", "Number the batteries", "todo",
                         "Write a number on each battery (a paint marker), then list them: Edit the battery list.",
                         go={"battery": 1}))
    elif ctx.get("battery_grades_stale"):
        jobs.append(_job("batteries", "Number the batteries", "attention",
                         f"{len(batteries)} listed. Newer grades to send to the robot, so Elastic shows them.",
                         go={"battery": 1}))
    else:
        jobs.append(_job("batteries", "Number the batteries", "done", f"{len(batteries)} listed.", go={"battery": 1}))

    designs = [k for k, v in (tune.get("designs") or {}).items() if v]
    jobs.append(_job("designs", "Mechanism designs", "optional",
                     (f"{len(designs)} saved: " + ", ".join(designs)) if designs
                     else "Paste a ReCalc or AMBcalc link for each mechanism you designed.",
                     go={"tab": "config", "panel": "dl-panel"}, optional=True))
    return _plan("Config: what the files say",
                 "The robot's swerve files checked against physics and each other, PathPlanner checked against "
                 "the code, the battery list, and mechanism designs.",
                 ["Nothing: no robot needed"], jobs, {"tab": "motors", "label": "Next: Motors"})


def motors(ctx):
    connected = bool(ctx.get("connected"))
    inv = ctx.get("inventory") or {"rows": [], "findings": []}
    rows = inv.get("rows") or []
    bad = [f for f in inv.get("findings") or [] if f.get("level") in ("error", "warn")]
    unnamed = [r["name"] for r in rows if not r.get("motor")]
    jobs = [_job("connect", "Connect to the robot", "done" if connected else "todo",
                 "Connected." if connected else "Connect at the top of the page (robot on, laptop on its network).")]
    if bad:
        jobs.append(_job("inventory", "Every motor named, with its type", "attention",
                         f"{len(bad)} to fix: the code, the files and the controllers disagree.", go={"tab": "motors", "panel": "motor-inventory"}))
    elif unnamed:
        jobs.append(_job("inventory", "Every motor named, with its type", "todo",
                         "Not named: " + ", ".join(unnamed[:6]) + ("…" if len(unnamed) > 6 else ""),
                         go={"tab": "motors", "panel": "motor-inventory"}))
    else:
        jobs.append(_job("inventory", "Every motor named, with its type", "done", f"{len(rows)} controllers.",
                         go={"tab": "motors", "panel": "motor-inventory"}))
    if not connected:
        jobs.append(_job("live", "Every controller heard, firmware current", "later",
                         "Needs the robot: the controllers say what they are and which firmware they run.",
                         unblock={"connect": 1, "label": "Connect to the robot"}))
    else:
        # Only motors the robot watches report in; one it doesn't watch is never "missing".
        missing = [r.get("name") for r in ctx.get("live_motors") or [] if not r.get("present", 1)]
        old = [f for f in inv.get("findings") or [] if "firmware" in f.get("title", "").lower()]
        jobs.append(_job("live", "Every controller heard, firmware current", "attention" if (missing or old) else "done",
                         ("Not heard: " + ", ".join(missing[:6]) + ". " if missing else "")
                         + (f"{len(old)} on old firmware: update with REV Hardware Client." if old else "")
                         or "All heard, firmware current.", go={"tab": "motors", "panel": "motor-inventory"}))
    return _plan("Motors: what each motor is",
                 "Every motor the code creates, with its controller, its type and its firmware, and the guard "
                 "that protects them from heat and stalls.",
                 ["The robot, powered and connected", "REV Hardware Client 2, for firmware"],
                 jobs, {"tab": "wiring", "label": "Next: Wiring"})


def wiring(ctx):
    prog, m = ctx.get("prog") or {}, ctx.get("wiring_map") or {}
    controllers = ctx.get("controllers") or []
    jobs = []
    st = _mark_status(_mark(prog, "wire_ohms"), "the reading is wrong: see the check's advice")
    jobs.append(_job("ohms", "Termination check", *(st or ("todo", "Robot off; a multimeter across CAN-H and CAN-L.")),
                     go={"tab": "wiring", "panel": "w-ohms-panel"}))
    ports = m.get("pdhPorts") or {}
    mapped = [c for c in controllers if c in ports]
    jobs.append(_job("pdh", "Find the PDH ports", "done" if controllers and len(mapped) == len(controllers) else "todo",
                     f"{len(mapped)} of {len(controllers)} motors mapped.", go={"tab": "wiring", "panel": "w-find"}))
    buses = m.get("buses") or []
    confirmed = bool(buses) and all(b.get("orderConfirmed") for b in buses)
    jobs.append(_job("order", "Confirm the CAN cable order", "done" if confirmed else "todo",
                     "Checked on the robot." if confirmed else "Follow the yellow-green cable from the roboRIO; Edit the map.",
                     go={"tab": "wiring", "panel": "w-edit"}))
    st = _mark_status(_mark(prog, "wire_wiggle"), "something dropped when a plug moved: see the result")
    jobs.append(_job("wiggle", "Wiggle test", *(st or ("todo", "Robot on and disabled; about five minutes.")),
                     go={"tab": "wiring", "panel": "w-wiggle"}))
    jobs.append(_job("saved", "Save the map and redeploy", "done" if ctx.get("wiring_saved") else "todo",
                     "Saved in the robot project; redeploy after each change so alerts name ports."
                     if ctx.get("wiring_saved") else "Edit the map, then Save; redeploy so Robot Health names ports.",
                     go={"tab": "wiring", "panel": "w-edit"}))
    return _plan("Wiring: the CAN chain and the power feeds",
                 "Which PDH port feeds each motor and the order of the CAN cable, so a fault names the plug to check.",
                 ["A multimeter", "The robot on blocks (for the PDH ports)"], jobs,
                 {"tab": "calibrate", "label": "Next: Calibrate"})


def controllers_plan(ctx):
    hist = ctx.get("controller_history") or []
    latest = {}
    for e in hist:
        latest[str(e.get("label", "")).strip().lower()] = e
    code_db = ctx.get("code_deadband")

    def find(*words):
        hits = [e for k, e in latest.items() if any(w in k for w in words)]
        return max(hits, key=lambda e: str(e.get("when", ""))) if hits else None

    jobs = []
    for jid, title, words, detail in (
            ("driver", "Check the driver's controller", ("driv",), "Port 0: the sticks that drive."),
            ("tester", "Check the tester's controller", ("test", "dead", "operat"),
             "Port 1: its right bumper is the deadman for every test.")):
        e = find(*words)
        if not e:
            jobs.append(_job(jid, title, "todo", detail + " Name it so when you save the check.",
                             go={"tab": "controllers", "panel": "ct-steps"}))
        else:
            verdict = e.get("verdict")
            jobs.append(_job(jid, title, "attention" if verdict == "error" else "done",
                             f"{e.get('label')}, {_when(e.get('when'))}: " + ("; ".join(e.get("problems") or []) or "good"),
                             go={"tab": "controllers", "panel": "ct-steps"}))
    needs = [e for e in latest.values() if e.get("recommended_deadband") and code_db
             and e["recommended_deadband"] > code_db + 1e-9]
    jobs.append(_job("deadband", "The code's deadband covers every controller", "attention" if needs else
                     ("done" if latest else "later"),
                     ("Needs more than the code's " + str(code_db) + ": "
                      + ", ".join(f"{e.get('label')} {e['recommended_deadband']}" for e in needs)) if needs
                     else ("Every checked controller rests inside it." if latest else "Check a controller first."),
                     go={"tab": "controllers", "panel": "ct-history"}))
    jobs.append(_job("spares", "Check the spares", "optional", "Before an event, so a swap mid-event is safe.",
                     go={"tab": "controllers", "panel": "ct-steps"}, optional=True))
    return _plan("Controllers: the drivers' sticks and buttons",
                 "Drift, dead zones, reach and buttons, for each Xbox controller, against the deadband the code uses.",
                 ["Each controller, with a USB cable"], jobs, {"guide": "", "label": "Back to the Guide"})


TOOLS = {"calibrate": calibrate, "config": config, "motors": motors, "wiring": wiring,
         "controllers": controllers_plan}


# ---------------------------------------------------------------------------- one part

PARTS = {
    "module": {"title": "A swerve module", "when": "Replaced, rebuilt, or acting up",
               "pick": "module"},
    "motor": {"title": "A motor or controller", "when": "Replaced, or its CAN ID or firmware changed",
              "pick": "motor"},
    "gyro": {"title": "The gyro", "when": "Moved, replaced, or reading oddly", "pick": None},
    "camera": {"title": "A camera", "when": "Moved, bumped, replaced, or added", "pick": "camera"},
    "field": {"title": "A new field or event", "when": "Setting up on a field you haven't surveyed", "pick": None},
    "wheels": {"title": "Wheels or tread", "when": "New wheels or tread on any module", "pick": None},
}


def part_key(kind, which=""):
    return f"{kind}:{which}" if which else kind


def _module_motors(module):
    return [f"{module} drive", f"{module} steer"]


def part_plan(kind, which, ctx, started):
    """The checklist for redoing one part. ``started`` is when the person began: only evidence
    from then on counts, since the part changed."""
    prog = ctx.get("prog") or {}
    pm = ((prog.get("parts") or {}).get(part_key(kind, which)) or {}).get("marks") or {}
    since = started

    def pmark(key):
        m = pm.get(key)
        return m if isinstance(m, dict) and str(m.get("when", "")) >= str(since) else None

    if kind == "module":
        return _module_plan(which, ctx, since, pmark)
    if kind == "motor":
        return _motor_plan(which, ctx, since, pmark)
    if kind == "gyro":
        jobs = [_health_job(ctx, since, "gyro"),
                _from_mark(_mark(prog, "cal_gyro_still", since), "still", "The gyro standing still",
                           "Record a minute with nobody touching the robot.", {"tab": "calibrate", "panel": "cal-gyro"}),
                _from_mark(_mark(prog, "cal_gyro_turns", since), "turns", "Full turns read 360° each",
                           "Turn the robot five times by hand or with the sticks.", {"tab": "calibrate", "panel": "cal-gyro"}),
                _spin_job(ctx, since, optional=True)]
        return _plan("The gyro", "A moved or new gyro: is it calibrated, does it drift, does a full turn read 360°.",
                     ["The robot on the floor", "A tape line on the floor"], jobs, {"guide": "", "label": "Back to the Guide"})
    if kind == "camera":
        cams = [str(c) for c in ((_tune(ctx).get("vision") or {}).get("cameras") or [])]
        listed = which in cams
        jobs = [_job("listed", f"{which or 'The camera'} is listed for the robot", "done" if listed else "todo",
                     "In swervetune.json." if listed else
                     f"Add \"{which}\" (its PhotonVision name) to \"vision\": {{\"cameras\": [...]}} in swervetune.json, then redeploy.",
                     go={"tab": "config", "panel": "cfg-findings"}),
                _from_mark(_mark(prog, f"cal_camera_{which}", since), "position", "Measure where it sits",
                           "One tag on a wall; three spots or more.", {"tab": "calibrate", "panel": "cal-camera", "camera": which}),
                _job("field", "On a new field too? Survey it", "optional", "Pick \"A new field or event\" after this.",
                     go={"part": "field"}, optional=True)]
        return _plan(f"Camera: {which}", "Every vision pose passes through where the code thinks this camera is.",
                     ["A tag on a wall", "A tape measure"], jobs, {"guide": "", "label": "Back to the Guide"})
    if kind == "field":
        vf = (_tune(ctx).get("vision") or {}).get("field")
        fm = pmark("field_type")
        jobs = [_job("type", "Say which field it is: welded or AndyMark",
                     "done" if fm else "todo",
                     f"{(fm or {}).get('detail') or vf or 'welded'}." if fm else
                     f"Now {vf or 'welded (the default)'}. The event's documents say which; the survey can tell too.",
                     how=["Read the event's field documents (welded or AndyMark).", "Pick it here and save."]),
                _job("survey", "Survey the tags", "done" if ctx.get("layout_mtime", "") >= since and ctx.get("layout_saved") else "todo",
                     "Drive past every group of tags, then Work it out and save.",
                     go={"tab": "calibrate", "panel": "cal-field"}),
                _job("upload", "Upload surveyed.json to each camera", "done" if pmark("upload") else "todo",
                     "PhotonVision's page, Settings, AprilTag field layout: the camera solves its multi-tag poses itself.",
                     how=["Open each camera's PhotonVision page.", "Settings, AprilTag field layout: upload "
                          "src/main/deploy/apriltags/surveyed.json.", "Then press Done here."]),
                _job("cameras", "A camera knocked in transit? Measure it again", "optional",
                     "Pick \"A camera\" for it.", go={"part": "camera"}, optional=True)]
        return _plan("A new field or event", "Tags on a real field sit where people hung them: measure where.",
                     ["The robot on the field, a camera fitted", "The event's field documents"], jobs,
                     {"guide": "", "label": "Back to the Guide"})
    if kind == "wheels":
        jobs = [_from_mark(_mark(prog, "cal_wheels", since), "wheels", "Measure the wheel sizes",
                           "A 3 m push in coast: new tread is bigger than worn.", {"tab": "calibrate", "panel": "cal-wheels"}),
                _straight_job(ctx, since)]
        return _plan("Wheels or tread", "Every distance odometry reports is wheel turns times the wheel size.",
                     ["3 m of straight floor", "A tape measure"], jobs, {"guide": "", "label": "Back to the Guide"})
    raise ValueError(f"no such part: {kind}")


def _from_mark(m, jid, title, todo, go):
    st = _mark_status(m)
    return _job(jid, title, *(st or ("todo", todo)), go=go)


def _health_job(ctx, since, part):
    caps = _runs(ctx, "capture", since=since)
    return _job("health", "Sensor health capture", "done" if caps else "todo",
                f"Captured {_when(caps[0]['saved'])}." if caps else "Robot disabled, three seconds still.",
                go={"guide": "health"})


def _spin_job(ctx, since, optional=False):
    spins = _runs(ctx, "spin", "FIELD", since=since)
    status = "done" if spins and (spins[0].get("score") or 0) >= 100 else ("attention" if spins else
                                                                          ("optional" if optional else "todo"))
    return _job("spin", "Spin check on the floor", status, "Gyro, wheels and command agree on the turn rate.",
                go={"tune": "spin"}, optional=optional)


def _straight_job(ctx, since):
    runs = _runs(ctx, "straight", "FIELD", since=since)
    return _job("straight", "Straight line, measured with a tape", "done" if runs and (runs[0].get("score") or 0) >= 100
                else ("attention" if runs else "optional"),
                "Confirms the new size on the floor.", go={"tune": "straight"}, optional=not runs)


def _module_plan(module, ctx, since, pmark):
    live = {r.get("name"): r for r in ctx.get("live_motors") or []}
    names = _module_motors(module)
    jobs = []
    if not ctx.get("connected"):
        jobs.append(_job("heard", "Both its controllers heard on the CAN bus", "todo",
                         "Connect to the robot. A new module's SPARKs need their CAN IDs set first (REV Hardware Client).",
                         how=["Set each new SPARK's CAN ID to the old one's (Config shows them), with REV Hardware Client.",
                              "Update its firmware there too.", "Connect at the top of the page."]))
    else:
        gone = [n for n in names if n not in live or not live[n].get("present", 1)]
        jobs.append(_job("heard", "Both its controllers heard on the CAN bus", "attention" if gone else "done",
                         ("Not heard: " + ", ".join(gone) + ". Check the CAN ID, the plugs and its breaker.") if gone
                         else "Both heard.", go={"tab": "motors", "panel": "motor-inventory"}))
    jobs.append(_health_job(ctx, since, module))
    for jid, title, todo in (("hand_wheel", "Hand check: roll its wheel", "Robot disabled. Roll the wheel so its top moves forward."),
                             ("hand_steer", "Hand check: turn it", "Turn the module counter-clockwise, seen from above.")):
        st = _mark_status(pmark(jid), "the sensors disagree: see the result")
        jobs.append(_job(jid, title, *(st or ("todo", todo)), go={"part_action": jid}))
    st = _mark_status(pmark("offset"), "the offset wasn't saved")
    jobs.append(_job("offset", "Its offset", *(st or ("todo", "Wheel straight ahead, bevel gear to the left; capture, save, redeploy.")),
                     go={"part_action": "offset"}))
    st = _mark_status(pmark("direction"), "it rolled backwards: see Troubleshoot, wheel backwards")
    jobs.append(_job("direction", "On blocks: it drives the right way", *(st or ("todo", "On blocks, deadman held; watch its tire.")),
                     go={"part_action": "direction"}))
    steer = _runs(ctx, "steer_step", "BLOCKS", module=module, since=since)
    jobs.append(_job("steer", "Steering on blocks", "done" if steer and (steer[0].get("score") or 0) >= 80
                     else ("attention" if steer else "todo"),
                     (f"Scored {steer[0].get('score')}." if steer else "Same gains as the others: it should score as they do."),
                     go={"tune": "steer", "module": module}))
    ff = _runs(ctx, "drive_ff", since=since)
    jobs.append(_job("ff", "Feedforward against the other three", "done" if ff else "todo",
                     "Its kV within a few percent of the others: a big gap is friction or a wrong ratio."
                     if not ff else f"Measured {_when(ff[0]['saved'])}: compare its row in the result.",
                     go={"tune": "ff"}))
    jobs.append(_job("floor", "Steering on the floor", "done" if _runs(ctx, "steer_step", "FIELD", module=module, since=since)
                     else "optional", "If it still acts up on carpet.", go={"tune": "steer", "module": module}, optional=True))
    return _plan(f"Module: {module}", "A replaced or misbehaving module, checked on its own: the rest keep their settings.",
                 ["Blocks", "The robot connected", "REV Hardware Client (a new module)"], jobs,
                 {"guide": "", "label": "Back to the Guide"})


def _motor_plan(name, ctx, since, pmark):
    inv = {r["name"]: r for r in (ctx.get("inventory") or {}).get("rows") or []}
    row = inv.get(name) or {}
    live = {r.get("name"): r for r in ctx.get("live_motors") or []}
    jobs = []
    if not ctx.get("connected"):
        jobs.append(_job("heard", "Heard on the CAN bus, with its CAN ID", "todo",
                         f"Set the new controller's CAN ID to {row.get('can_id', '?')} with REV Hardware Client, then connect."))
    else:
        r = live.get(name)
        ok = r and r.get("present", 1)
        jobs.append(_job("heard", "Heard on the CAN bus, with its CAN ID", "done" if ok else "attention",
                         "Heard." if ok else f"Not heard: check CAN ID {row.get('can_id', '?')}, its plugs and breaker.",
                         go={"tab": "motors", "panel": "motor-inventory"}))
    jobs.append(_job("type", "Its type matches the code", "attention" if row.get("status") == "bad" else
                     ("done" if row.get("motor") else "todo"),
                     f"{row.get('motor') or 'Not named'} on a {row.get('code_controller') or '?'}.",
                     go={"tab": "motors", "panel": "motor-inventory"}))
    ports = ((ctx.get("wiring_map") or {}).get("pdhPorts") or {})
    jobs.append(_job("pdh", "Its PDH port", "done" if name in ports else "optional",
                     f"Port {ports[name]}." if name in ports else "If it moved to another port: Find the PDH ports.",
                     go={"tab": "wiring", "panel": "w-find"}, optional=name not in ports))
    module = name.rsplit(" ", 1)[0] if name.endswith((" drive", " steer")) else ""
    if module:
        jobs.append(_job("module", f"Then check {module} as a module", "todo",
                         "Direction, offset (steering) and feedforward all depend on it.", go={"part": "module", "which": module}))
    return _plan(f"Motor: {name}", "A replaced motor or controller: heard, named, powered.",
                 ["The robot connected", "REV Hardware Client"], jobs, {"guide": "", "label": "Back to the Guide"})


# ---------------------------------------------------------------------------- the server's evidence


def gather(project, *, link=None, battery_grades_stale=False):
    """Everything the plans read, from the project, this laptop and the robot. Whether the battery
    grades the robot has are older than the laptop's comes from the server, which keeps them."""
    from . import motorinv, ppcheck, progress, runs, wiring, yagslcfg
    ctx = {"project": project, "robot": project.name if project else None,
           "prog": progress.load(project.name) if project else {},
           "runs": runs.list_runs(400)}
    connected = bool(link and link.is_connected())
    ctx["connected"] = connected
    live = []
    if connected:
        try:
            live = link.motors().get("motors") or []
        except Exception:  # noqa: BLE001 - a robot without the motor guard has no rows
            live = []
    ctx["live_motors"] = live
    if not project:
        return ctx
    ctx["lint"] = yagslcfg.lint(project)
    try:
        ctx["pp"] = ppcheck.check(project)
    except Exception:  # noqa: BLE001 - no PathPlanner folder
        ctx["pp"] = None
    ctx["inventory"] = motorinv.table(project, live)
    m = wiring.load_map(project)
    ctx["wiring_map"] = m
    ctx["wiring_saved"] = os.path.exists(wiring.map_path(project))
    ctx["controllers"] = [d["name"] for d in wiring.discover(project) if d["kind"] == "controller"]
    lay = os.path.join(project.path, "src", "main", "deploy", "apriltags", "surveyed.json")
    ctx["layout_saved"] = os.path.exists(lay)
    ctx["layout_mtime"] = stamp(os.path.getmtime(lay)) if os.path.exists(lay) else ""
    ctx["controller_history"] = runs.controller_log()[-200:]
    from . import controllers
    dbs = [d["value"] for d in controllers.code_deadbands(project) if d.get("value")]
    ctx["code_deadband"] = min(dbs) if dbs else None
    ctx["battery_grades_stale"] = bool(battery_grades_stale)
    return ctx
