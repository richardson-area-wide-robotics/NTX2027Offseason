"""Command line for the swerve tools - for people, and for AI agents (add ``--json``).

    py -3.12 tools/swervetune lint                      # check both robots' configs, no robot needed
    py -3.12 tools/swervetune gui                       # the student GUI in a browser
    py -3.12 tools/swervetune status --project Peashooter
    py -3.12 tools/swervetune env --mode BLOCKS
    py -3.12 tools/swervetune run steer_step --module FL
    py -3.12 tools/swervetune gains set Steer/kP=0.015
    py -3.12 tools/swervetune save gains --yes
    py -3.12 tools/swervetune practice steer --kp 0.02 --surface floor
    py -3.12 tools/swervetune brief                     # the rules an agent must follow

With ``--json`` every command prints exactly one JSON object, so an agent can parse it. The
safety rules an agent cannot get round live on the robot (bounds, deadman, interlocks); the ones
here keep it from wasting a run: a gain may change by at most 2x per step unless --force, and
nothing is written to the repository without --yes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time

from . import (advisor, akit, analysis, contract as C, diagnose, explain, logsummary, monitor, motorinv,
               pdhports, plant, ppcheck, predict, rehearse, runs, wiring, yagslcfg)

REPO = runs.REPO
MAX_STEP_RATIO = 2.0


# ---------------------------------------------------------------------------- output


class Out:
    def __init__(self, as_json):
        self.json = as_json
        self.data = {"ok": True}

    def say(self, text=""):
        if not self.json:
            print(text)

    def put(self, **kw):
        self.data.update(kw)

    def fail(self, message, **kw):
        self.data.update(ok=False, error=message, **kw)
        if not self.json:
            print(f"ERROR: {message}", file=sys.stderr)
        return 2

    def done(self, code=0):
        if self.json:
            # Strict JSON: NaN and infinity become null, anywhere in the output.
            print(json.dumps(_clean(self.data), default=_jsonable, indent=1, allow_nan=False))
        return code


def _jsonable(o):
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return str(o)


def _clean(o):
    """NaN and infinity are not JSON; agents get null instead."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def print_report(out, rep):
    if not rep:
        return
    out.say(f"\n{rep.get('summary', '')}")
    if rep.get("score") is not None:
        out.say(f"score {rep['score']}/100   cost {rep.get('cost')}")
    for t in rep.get("targets", []):
        v = t["value"]
        vs = f"{v:.3f}" if isinstance(v, float) and math.isfinite(v) else str(v)
        out.say(f"  [{'x' if t['met'] else ' '}] {t['name']}: {vs} (target {t['target']})")
    for f in rep.get("findings", []):
        out.say(f"\n  {f['level'].upper()}: {f['title']}")
        out.say("    " + f["why"])
        if f.get("action"):
            out.say("    -> " + json.dumps(f["action"]))


# ---------------------------------------------------------------------------- projects and links


def project_dirs():
    return yagslcfg.find_projects(REPO)


def resolve_project(name):
    if not name:
        return None
    for d in project_dirs():
        if os.path.basename(d).lower() == name.lower() or os.path.abspath(d) == os.path.abspath(name):
            return yagslcfg.Project(d)
    if os.path.isdir(name):
        return yagslcfg.Project(name)
    raise SystemExit(f"No robot project called {name!r}. Known: "
                     + ", ".join(os.path.basename(d) for d in project_dirs()))


def open_link(args, out):
    from . import link as L

    if L.ntcore is None:
        out.fail(L.INSTALL_HINT)
        return None
    team = args.team
    if not team and args.project:
        team = L.team_from_project(resolve_project(args.project).path)
    if not team:
        # No --project: every robot in this repo is the same team, so try its address first.
        for path in yagslcfg.find_projects(REPO):
            team = L.team_from_project(path)
            if team:
                break
    hosts = L.candidate_hosts(team=team, host=args.host, sim=args.sim)
    lk = L.RobotLink(hosts, client_name="swervetune-cli")
    if not lk.wait_connected(args.connect_timeout):
        lk.close()
        out.fail("Could not reach the robot at " + ", ".join(hosts) + ". Is robot code running? "
                 "On a laptop with a VPN, run tools/robot_preflight.ps1.", tried=hosts)
        return None
    if not lk.has_harness():
        lk.close()
        out.fail("Connected, but the robot code does not have SwerveTune installed.")
        return None
    proto = lk.get("int", C.PROTOCOL)
    if proto != C.PROTOCOL_VERSION:
        lk.close()
        out.fail(f"Robot speaks SwerveTune protocol {proto}, this tool speaks "
                 f"{C.PROTOCOL_VERSION}. Deploy matching code or update the tool.")
        return None
    lk.start_heartbeat()
    return lk


def project_for_robot(args, lk):
    if args.project:
        return resolve_project(args.project)
    name = lk.robot_info().get("name") if lk else None
    try:
        return resolve_project(name) if name else None
    except SystemExit:
        return None


def current_limits(project):
    if not project:
        return {}
    lim = project.phys.get("currentLimit", {})
    return {"steer": float(lim.get("angle", 20)), "drive": float(lim.get("drive", 40))}


# ---------------------------------------------------------------------------- commands


def cmd_lint(args, out):
    projects = [resolve_project(args.project)] if args.project else [yagslcfg.Project(d) for d in project_dirs()]
    result = {}
    for p in projects:
        findings = yagslcfg.lint(p)
        result[p.name] = {"summary": yagslcfg.summary(p), "findings": findings}
        s = result[p.name]["summary"]
        out.say(f"\n=== {p.name}  (team {p.team})")
        out.say(f"  drive {s['drive_motor']} {s['drive_gear']}:1 on {s['wheel_diameter_in']} in wheels,"
                f" free speed {s['max_module_speed_mps']:.2f} m/s; steering {s['steer_motor']}"
                f" {s['steer_gear']}:1")
        if s.get("traction_current_a"):
            out.say(f"  wheels slip at about {s['traction_current_a']:.0f} A per motor"
                    f" ({s['mass_kg']:.0f} kg, {s['mass_source']})")
        for f in findings:
            out.say(f"\n  [{f['level'].upper()}] {f['title']}")
            out.say("    " + f["why"])
            if f.get("fix"):
                out.say("    fix: " + json.dumps(f["fix"]))
    out.put(projects=_clean(result))
    return out.done()


def cmd_status(args, out):
    lk = open_link(args, out)
    if not lk:
        return out.done(2)
    try:
        info = lk.robot_info()
        env = lk.environment()
        live = lk.live()
        mon = monitor.Monitor(current_limits(project_for_robot(args, lk)).get("drive", 40))
        for _ in range(int(args.watch / 0.05) or 1):
            flags = mon.update(lk.live(), info["modules"], env["active"])
            time.sleep(0.05)
        out.put(robot=info, environment=env, live=_clean(live), status=lk.status(),
                gains=_clean(lk.gains()), flags=flags)
        out.say(f"{info['name']} at {info['address']}  mode {live['mode']}  battery {live['bus']:.1f} V")
        out.say(f"environment {env['active']}  apriltags {'on' if env['apriltags'] else 'off'}"
                f"  space {env['space_forward']:.1f} x {env['space_side']:.1f} m  cap {env['speed_cap']:.1f} m/s")
        for line in info["startup_report"]:
            out.say("  startup: " + line)
        for i, n in enumerate(info["modules"]):
            out.say(f"  {n:11s} steer {live['steer'][i]:7.1f}° (sp {live['steer_sp'][i]:7.1f})"
                    f"  speed {live['v'][i]:+5.2f} m/s  drive {live['drive_amps'][i]:4.1f} A"
                    f"  {live['faults'][i] if i < len(live['faults']) else ''}")
        for f in flags:
            out.say(f"  ! {f['text']} {f['detail']}  (troubleshoot: {f['symptom']})")
        return out.done()
    finally:
        lk.close()


def cmd_env(args, out):
    lk = open_link(args, out)
    if not lk:
        return out.done(2)
    try:
        if args.mode and args.mode.upper() == "FIELD" and not (args.space and args.side):
            return out.done(out.fail("FIELD needs --space and --side: meters of clear floor ahead "
                                     "and to each side. Measure them."))
        lk.set_environment(args.mode, None if args.tags is None else args.tags == "on",
                           args.space, args.side, args.cap)
        time.sleep(0.3)
        env = lk.environment()
        out.put(environment=env)
        out.say(f"robot now says: {env['active']}, apriltags {'on' if env['apriltags'] else 'off'},"
                f" space {env['space_forward']} x {env['space_side']} m, cap {env['speed_cap']} m/s")
        return out.done()
    finally:
        lk.close()


def _parse_kv(items):
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"expected key=value, got {it!r}")
        k, v = it.split("=", 1)
        out[k.strip()] = float(v)
    return out


def cmd_run(args, out):
    if args.test not in C.TESTS:
        return out.done(out.fail(f"unknown test {args.test!r}; known: {', '.join(C.TESTS)}"))
    lk = open_link(args, out)
    if not lk:
        return out.done(2)
    try:
        project = project_for_robot(args, lk)
        gains = lk.gains()
        last = {}

        def on_status(st):
            if st["message"] != last.get("m"):
                out.say(f"  [{st['state']}] {st['message']}")
                last["m"] = st["message"]

        res = lk.run_test(args.test, args.module, _parse_kv(args.arg), on_status=on_status)
        doc = res.to_json()
        if not res.accepted:
            out.put(accepted=False, message=res.message)
            return out.done(out.fail("Refused: " + res.message, code=C.stop_code(res.message)))
        lim = current_limits(project)
        rep = advisor.analyze(doc, gains,
                              current_limit=lim.get("steer" if args.test == "steer_step" else "drive", 40),
                              **advisor.robot_context(project))
        path = runs.save(doc, rep, gains)
        # ok means the test finished: a run stopped part-way is not ok, and says why in a code.
        out.put(ok=res.outcome == "DONE", outcome=res.outcome, message=res.message, notes=res.notes,
                run_file=os.path.basename(path), report=_clean(rep), samples=len(res.channels.get("t", [])),
                **({} if res.outcome == "DONE" else {"code": C.stop_code(res.message)}))
        out.say(f"{res.outcome}: {res.message}  ({len(res.channels.get('t', []))} samples, saved {os.path.basename(path)})")
        for n in res.notes:
            out.say("  note: " + n)
        print_report(out, rep)
        return out.done(0 if res.outcome == "DONE" else 1)
    finally:
        lk.close()


def run_kind(r):
    """Where a saved run came from. Only "robot" runs are evidence about a robot."""
    return "practice" if r.get("practice") else "sim" if r.get("env") == "SIM" else "robot"


def cmd_runs(args, out):
    rows = []
    for r in runs.list_runs(1000):
        kind = run_kind(r)
        if args.show != "all" and kind != args.show:
            continue
        if args.test and r["test"] != args.test:
            continue
        if args.robot and (r["robot"] or "").lower() != args.robot.lower():
            continue
        done = r["outcome"] == "DONE"
        # As in the Runs tab: a run that stopped part-way has no score and no cost.
        rows.append({"file": r["file"], "kind": kind, "robot": r["robot"], "test": r["test"],
                     "module": r["module"], "env": r["env"], "outcome": r["outcome"],
                     "score": r["score"] if done else None, "cost": r["cost"] if done else None,
                     "summary": r["summary"], "gains": r["gains"]})
        if len(rows) >= args.limit:
            break
    out.put(runs=_clean(rows))
    if not rows:
        out.say(f"No {'' if args.show == 'all' else args.show + ' '}runs saved yet.")
    for x in rows:
        score = "-" if x["score"] is None else x["score"]
        out.say(f"{x['file']}  {x['kind']:8} {x['test'] or '?':11} {(x['outcome'] or '?').lower():9} "
                f"score {score}")
    return out.done()


def cmd_analyze(args, out):
    doc = runs.load(args.run)
    project = resolve_project(args.project) if args.project else None
    rep = advisor.analyze(doc, doc.get("gains"), measured_forward_m=args.tape_forward,
                          measured_lateral_m=args.tape_lateral, **advisor.robot_context(project))
    out.put(report=_clean(rep), run_file=doc["_file"])
    print_report(out, rep)
    return out.done()


def _run_limits(args, doc):
    if doc.get("practice"):
        return {"steer": 20.0, "drive": 40.0}
    try:
        return current_limits(resolve_project(args.project) if args.project else None) or {"steer": 20.0, "drive": 40.0}
    except Exception:  # noqa: BLE001 - limits only sharpen the explanation
        return {"steer": 20.0, "drive": 40.0}


def _pod_motor(args):
    """The practice pod's drive motor: --motor, else the --project robot's, else a NEO."""
    if getattr(args, "motor", None):
        return args.motor
    try:
        kind = resolve_project(args.project).drive_kind() if getattr(args, "project", None) else None
    except Exception:  # noqa: BLE001 - the pod still runs, as a NEO
        kind = None
    return kind if kind in plant.MOTORS and kind != "neo550" else "neo"


def _drive_kind(args, doc):
    """The drive motor of the robot a run came from: its project, or the one named on the command line."""
    if doc.get("practice"):
        return None
    try:
        name = args.project or (doc.get("robot") or {}).get("name")
        return resolve_project(name).drive_kind() if name else None
    except Exception:  # noqa: BLE001 - without it the prediction assumes a NEO
        return None


def cmd_explain(args, out):
    doc = runs.load(args.run)
    e = explain.explain(doc, doc.get("gains"), _run_limits(args, doc))
    if not e or not e["modules"]:
        out.say("Only steer_step and drive_step runs can be explained.")
        return out.done(1)
    mods = e["modules"] if args.module is None else [m for m in e["modules"] if m["index"] == args.module]
    slim = [{k: m[k] for k in ("module", "index", "loop", "units", "sensor", "gains", "story")} for m in mods]
    out.put(explain=_clean(slim), run_file=doc["_file"])
    for m in mods:
        out.say(f"{m['module']} ({m['loop']}, the loop sees {m['sensor']}):")
        for n in m["story"]:
            if args.step is None or n["step"] == args.step:
                out.say(f"  {n['t']:6.2f} s  [{n['learn']}] {n['text']}")
    return out.done()


def cmd_predict(args, out):
    doc = runs.load(args.run)
    new = dict(doc.get("gains") or {})
    for kv in args.gains:
        k, _, v = kv.partition("=")
        new[k.strip()] = float(v)
    loop = "steer" if doc.get("test") == "steer_step" else "drive"
    kind = _drive_kind(args, doc) if loop == "drive" else None
    p = predict.predict(doc, doc.get("gains") or {}, new, args.module,
                        current_limit=_run_limits(args, doc).get(loop), motor_kind=kind)
    if not p.get("ok"):
        out.put(prediction=_clean(p))
        out.say(p.get("reason", "No prediction."))
        return out.done(1)
    out.put(prediction=_clean({k: v for k, v in p.items() if k not in ("t", "sp", "measured", "replay", "predicted")}))
    out.say(f"{p['module']}: model {p['quality']} ({p['relative_error'] * 100:.1f}% replay error, recording "
            f"{p['delay_ms']} ms late). {p['note']}")
    rows = (("rise_time", "rise", 1000, "ms"), ("overshoot_pct", "overshoot", 1, "%"),
            ("settling_time", "settle", 1000, "ms"), ("steady_state_error", "left over", 1, p["units"]),
            ("oscillations", "swings", 1, ""))
    out.say(f"  {'':10s} {'this run':>10s} {'replay':>10s} {'predicted':>10s}")
    for key, label, scale, unit in rows:
        cells = []
        for col in ("measured", "replay", "predicted"):
            v = p["summary"][col].get(key)
            cells.append("never" if key == "settling_time" and p["summary"][col].get("settled") is False
                         else "-" if v is None else f"{v * scale:.3g}{unit}")
        out.say(f"  {label:10s} " + " ".join(f"{c:>10s}" for c in cells))
    return out.done()


def cmd_export(args, out):
    doc = runs.load(args.run)
    path = args.out or os.path.join(runs.RUNS, os.path.splitext(doc["_file"])[0] + ".wpilog")
    names = akit.export_run(doc, path)
    out.put(path=path, entries=names)
    out.say(f"Wrote {path}: {len(names)} entries. Open it in AdvantageScope"
            + (", or in SysId (mechanism 'drive', one motor per module)." if doc.get("test") == "drive_ff" else "."))
    return out.done()


def cmd_ppcheck(args, out):
    """Does PathPlanner describe the same robot as the code? Exit 1 on any error, for CI."""
    projects = [resolve_project(args.project)] if args.project else [yagslcfg.Project(d) for d in project_dirs()]
    errors = 0
    results = {}
    for p in projects:
        r = ppcheck.check(p)
        results[p.name] = _clean({k: v for k, v in r.items() if k != "fixes"})
        if not r["used"]:
            out.say(f"=== {p.name}: doesn't use PathPlanner")
            continue
        out.say(f"=== {p.name}")
        for row in r["rows"]:
            if row["status"] != "ok":
                out.say(f"  {row['status']:8s} {row['key']:18s} PathPlanner {row['pathplanner']!s:10s} code "
                        f"{row['code']!s:10s} ({row['source']})")
        for f in r["findings"]:
            out.say(f"  [{f['level'].upper()}] {f['title']}")
        errors += sum(1 for f in r["findings"] if f["level"] == "error")
        if args.fix and r["fixes"]:
            path, new = ppcheck.fixed_text(p, r["fixes"])
            old = open(path, encoding="utf-8").read()
            out.say(yagslcfg.diff(old, new, os.path.relpath(path, p.path).replace(os.sep, "/")))
            if args.yes:
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(new)
                out.say(f"  wrote {path}: reopen the PathPlanner app so it doesn't write its old values back")
            else:
                out.say("  (add --yes to write it)")
    out.put(pathplanner=results, errors=errors)
    return out.done(1 if errors else 0)


def cmd_pdhports(args, out):
    """Which PDH port feeds each motor, from a pdh_map run or a practice log."""
    project = resolve_project(args.project) if args.project else None
    m = wiring.load_map(project) if project else None
    src = args.source
    if src.lower().endswith(".wpilog"):
        rep = pdhports.from_log(logsummary.read(src), m)
    else:
        rep = pdhports.from_pulses(runs.load(src), m)
    out.put(pdh=_clean(rep))
    for r in rep["rows"]:
        port = r["port"] if r["port"] is not None else "-"
        extra = (f"rise {r['rise_a']:.2f} A" if r.get("rise_a") is not None
                 else f"match {r['corr']:.2f}" if r.get("corr") is not None else "")
        out.say(f"  {r['name']:24s} port {port!s:>3}  {r['status']:9s} {extra:14s} map: "
                f"{r['mapped'] if r['mapped'] is not None else '-'} ({r['verdict']})")
    for f in rep["findings"]:
        out.say(f"  {f['level']}: {f['title']}. {f['why']}")
    if not project:
        out.say("  (add --project Peashooter to compare with that robot's wiring map)")
    return out.done()


def cmd_logsummary(args, out):
    project = resolve_project(args.project) if args.project else None
    m = wiring.load_map(project) if project else None
    rep = logsummary.summarize_file(args.log, m)
    out.put(summary=_clean(rep))
    info = rep["info"]
    out.say(f"{os.path.basename(args.log)}: {rep['summary']}"
            + (f"  ({info.get('EventName', '')} {info.get('MatchType', '')} {info.get('MatchNumber', '')})"
               if info.get("FMSAttached") else ""))
    for e in rep["events"]:
        out.say(f"  {e['when']:>18s}  {e['level']:5s}  {e['text']}")
    for f in rep["findings"]:
        out.say(f"  where to look: {f['title']}. {f['why']}")
    if not project:
        out.say("  (add --project Peashooter to judge dropouts with that robot's wiring map)")
    return out.done()


def cmd_layout(args, out):
    projects = [resolve_project(args.project)] if args.project else [yagslcfg.Project(d) for d in project_dirs()]
    paths = [akit.write_layout(p, args.out_dir) for p in projects]
    out.put(layouts=paths)
    for p in paths:
        out.say(f"Wrote {p}. In AdvantageScope: File > Import Layout.")
    return out.done()


def cmd_gains(args, out):
    lk = open_link(args, out)
    if not lk:
        return out.done(2)
    try:
        now = lk.gains()
        if args.action == "show" or not args.values:
            out.put(gains=_clean(now))
            for k, v in now.items():
                out.say(f"  {k:28s} {v}")
            return out.done()
        want = _parse_kv(args.values)
        problems = []
        for k, v in want.items():
            if k not in now:
                problems.append(f"{k} is not a live gain")
                continue
            spec = C.GAIN_SPECS.get(k) or C.FF_SPECS.get(k.split("/")[-1])
            if spec and not (spec[0] <= v <= spec[1]):
                problems.append(f"{k}={v} is outside the robot's range {spec}")
            old = now[k]
            if (not args.force and isinstance(old, float) and math.isfinite(old) and old > 0 and v > 0
                    and (v / old > MAX_STEP_RATIO or old / v > MAX_STEP_RATIO)):
                problems.append(f"{k}: {old} -> {v} is more than a {MAX_STEP_RATIO:g}x step; change"
                                " one thing a little at a time (or --force)")
        if problems:
            return out.done(out.fail("; ".join(problems)))
        status, after = lk.set_gains(want)
        out.put(status=status, gains=_clean(after))
        out.say(status)
        return out.done(0 if "REFUSED" not in status else 1)
    finally:
        lk.close()


def cmd_save(args, out):
    lk = open_link(args, out)
    if not lk:
        return out.done(2)
    try:
        project = project_for_robot(args, lk)
        if not project:
            return out.done(out.fail("Which project? Pass --project."))
        live = lk.gains()
        edits = yagslcfg.edits_for_gains(project, {k: v for k, v in live.items()
                                                   if isinstance(v, float) and math.isfinite(v)
                                                   and (not args.keys or any(k.startswith(p) for p in args.keys))})
        changes = project.preview(edits)
        text = "".join(yagslcfg.diff(o, n, f) for f, (o, n) in changes.items())
        out.put(diff=text, files=list(changes))
        if not changes:
            out.say("The files already hold these gains. Nothing to save.")
            return out.done()
        out.say(text)
        if not args.yes:
            out.say("Not written. Rerun with --yes to write these changes, then redeploy.")
            out.put(written=False)
            return out.done()
        project.apply(edits)
        out.put(written=True)
        out.say("Written. Redeploy for them to load at boot; review with git diff and commit.")
        return out.done()
    finally:
        lk.close()


def cmd_config(args, out):
    """A report's ``config`` action: shows the file change; ``--yes`` writes it."""
    if not args.project:
        return out.done(out.fail("Which robot? Pass --project.", code="NO_PROJECT"))
    project = resolve_project(args.project)
    try:
        value = json.loads(args.value)
    except ValueError:
        value = args.value
    path = [p for p in (json.loads(args.path) if args.path.startswith("[") else args.path.split("."))]
    try:
        changes = project.preview([(args.file, tuple(path), value)])
    except ValueError as e:
        return out.done(out.fail(str(e), code="NOT_A_CONFIG_FILE"))
    text = "".join(yagslcfg.diff(o, n, f) for f, (o, n) in changes.items())
    out.put(diff=text, files=list(changes))
    if not changes:
        out.say("The file already says that. Nothing to change.")
        return out.done()
    out.say(text)
    if not args.yes:
        out.say("Not written. Show this to a person; with their yes, rerun with --yes, then redeploy.")
        out.put(written=False)
        return out.done()
    project.apply([(args.file, tuple(path), value)])
    out.put(written=True)
    out.say("Written. Redeploy for it to load at boot; review with git diff and commit.")
    return out.done()


def cmd_offsets(args, out):
    doc = runs.load(args.run)
    if doc.get("test") != "capture":
        return out.done(out.fail("Offsets come from a capture run with every wheel set straight ahead."))
    project = resolve_project(args.project or (doc.get("robot") or {}).get("name"))
    res = advisor.offsets_from_capture(doc, project.offsets())
    out.put(offsets=res)
    unsteady = [n for n, r in res.items() if not r["steady"]]
    for n, r in res.items():
        out.say(f"  {n:11s} read {r['reading_deg']:+7.2f}°  offset {r['old']:7.2f} -> {r['new']:7.2f}"
                + ("   (moved during capture!)" if not r["steady"] else ""))
    if unsteady:
        return out.done(out.fail("A module moved during the capture: " + ", ".join(unsteady)
                                 + ". Hold them still and capture again."))
    edits = [(f"modules/{n}.json", ("absoluteEncoderOffset",), r["new"]) for n, r in res.items()]
    changes = project.preview(edits)
    out.say("".join(yagslcfg.diff(o, n, f) for f, (o, n) in changes.items()))
    if args.yes:
        project.apply(edits)
        out.say("Written. Redeploy, then check every wheel reads 0° when straight.")
    else:
        out.say("Not written. Rerun with --yes to write, then redeploy.")
    out.put(written=bool(args.yes))
    return out.done()


def cmd_diagnose(args, out):
    if not args.symptom:
        out.put(symptoms=[{"id": s["id"], "title": s["title"], "looks_like": s["looks_like"]}
                          for s in diagnose.SYMPTOMS])
        for s in diagnose.SYMPTOMS:
            out.say(f"  {s['id']:22s} {s['title']}")
        return out.done()
    if args.symptom not in diagnose.BY_ID:
        return out.done(out.fail(f"unknown symptom; run 'diagnose' to list them"))
    lint = []
    if args.project:
        lint = yagslcfg.lint(resolve_project(args.project))
    ev = diagnose.evaluate(args.symptom, lint, [])
    out.put(symptom=ev)
    out.say(f"{ev['title']}: {ev['looks_like']}")
    for i, c in enumerate(ev["checks"]):
        mark = {"no": "PROBLEM", "yes": "ok"}.get(c.get("auto_answer"), "check")
        out.say(f"\n {i + 1}. [{mark}] {c['q']}")
        out.say(f"    how ({c['where']}): {c['how']}")
        if c.get("auto_answer") == "no":
            out.say(f"    found: {', '.join(c['evidence'])}")
        out.say(f"    if not: {c['if_no']}  ->  {c['fix']}")
    return out.done()


def cmd_watch(args, out):
    lk = open_link(args, out)
    if not lk:
        return out.done(2)
    try:
        names = lk.robot_info()["modules"]
        env = lk.environment()["active"]
        mon = monitor.Monitor(current_limits(project_for_robot(args, lk)).get("drive", 40))
        end = time.time() + args.seconds
        seen = set()
        while time.time() < end:
            for f in mon.update(lk.live(), names, env):
                key = (f["rule"], f["module"])
                if key not in seen:
                    seen.add(key)
                    out.say(f"{time.strftime('%H:%M:%S')}  {f['text']} {f['detail']}  -> {f['symptom']}")
            time.sleep(0.02)
        out.put(flags=mon.flags())
        return out.done()
    finally:
        lk.close()


def _fmt(x, spec):
    if isinstance(x, (int, float)) and x == x:
        return format(x, spec)
    width = re.match(r"\d*", spec).group(0)
    return format("-", ">" + width) if width else "-"


def cmd_motors(args, out):
    lk = open_link(args, out)
    if not lk:
        return out.done(2)
    try:
        if args.override is not None:
            reply = lk.override_motors(args.override, args.seconds)
            out.put(override=reply)
            out.say(reply)
        m = lk.motors()
        out.put(motors=_clean(m))
        if not m["guard_on"]:
            out.say("Motor guard is switched OFF in swervetune.json: no heat, stall or failure protection.")
        for line in m["report"]:
            out.say("  startup: " + line)
        if not m["motors"]:
            out.say("No motors are being watched.")
        out.say(f"  {'motor':22s} {'kind':18s} {'stage':8s} {'heat':>5s} {'temp':>5s} {'amps':>5s}"
                f" {'limit':>7s} {'stall':>5s}  why")
        for r in m["motors"]:
            limit = f"{_fmt(r['limit'], '.0f')}/{_fmt(r['base_limit'], '.0f')}"
            out.say(f"  {r['name']:22s} {r['kind']:18s} {r['stage']:8s} {_fmt(r['heat_pct'], '4.0f')}%"
                    f" {_fmt(r['temp'], '5.0f')} {_fmt(r['amps'], '5.1f')} {limit:>7s}"
                    f" {_fmt(r['stall_s'], '5.1f')}  {r['cause'] or ''}"
                    + (f"  override {r['override_s']:.0f} s" if (r['override_s'] or 0) > 0 else ""))
            if r["flags"]:
                out.say(f"  {'':22s} ! {r['flags']}")
        for line in m["events"][-args.events:]:
            out.say("  event: " + line)
        if args.project:
            # What each motor and controller is, and any fix: an "edits" list, one config change each.
            inv = motorinv.table(resolve_project(args.project), m["motors"])
            out.put(inventory=_clean(inv["findings"]))
            for f in inv["findings"]:
                out.say(f"  {f['level']}: {f['title']}")
        return out.done()
    finally:
        lk.close()


PRACTICE_NOTE = "PRACTICE POD - a model, not your robot. Its numbers never set a robot's gains."


def cmd_practice(args, out):
    surface = args.surface
    if args.loop == "steer":
        ch = plant.steer_step(rehearse.STEER_PATTERN, kP=args.kp, kI=args.ki, kD=args.kd,
                              i_zone=args.izone, ramp_s=args.ramp, surface=surface)
        doc = {"test": "steer_step", "channels": ch}
        gains = {"Steer/kP": args.kp, "Steer/kI": args.ki, "Steer/kD": args.kd,
                 "Steer/IZone": args.izone, "Steer/RampS": args.ramp}
    else:
        motor = _pod_motor(args)
        kv = args.kv if args.kv is not None else plant.nominal_kv(motor)
        ch = plant.drive_step(rehearse.DRIVE_PATTERN, kP=args.kp, kI=args.ki, kD=args.kd,
                              ramp_s=args.ramp, surface=surface, ff=(args.ks, kv, args.ka), motor=motor,
                              meas_period_ms=args.vel_period or None, meas_depth=args.vel_depth or None)
        doc = {"test": "drive_step", "channels": ch, "meta": {"pod_motor": motor}}
        gains = {"Drive/kP": args.kp, "Drive/kI": args.ki, "Drive/kD": args.kd,
                 "Drive/RampS": args.ramp, "Drive/VelPeriodMs": args.vel_period,
                 "Drive/VelDepth": args.vel_depth}
        gains.update({f"FF/frontleft/{k}": v for k, v in (("kS", args.ks), ("kV", kv), ("kA", args.ka))})
    doc.update(practice=True, env="FIELD" if surface == "floor" else "BLOCKS",
               robot={"name": "practice pod", "modules": rehearse.MODULES})
    rep = advisor.analyze(doc, gains)
    path = runs.save(doc, rep, gains, practice=True)
    out.put(practice=True, note=PRACTICE_NOTE, report=_clean(rep), run_file=os.path.basename(path))
    out.say(PRACTICE_NOTE)
    print_report(out, rep)
    return out.done()


def cmd_rehearse(args, out):
    out.say(PRACTICE_NOTE)
    if args.loop == "steer":
        start = {"Steer/kP": args.kp, "Steer/kI": 0.0, "Steer/kD": args.kd, "Steer/IZone": 0.0,
                 "Steer/RampS": args.ramp}
    else:
        start = {"Drive/kP": args.kp, "Drive/kI": 0.0, "Drive/kD": args.kd, "Drive/RampS": args.ramp,
                 "Drive/VelPeriodMs": 0, "Drive/VelDepth": 0}
    hist = rehearse.rehearse(args.loop, start, surface=args.surface, rounds=args.rounds, motor=_pod_motor(args),
                             log=lambda e: out.say(f"  round {e['round']}: score {e['score']} cost"
                                                   f" {e['cost']} -> {e['advice']}"))
    out.put(practice=True, note=PRACTICE_NOTE, history=_clean(hist), final=_clean(hist[-1] if hist else None))
    return out.done()


def cmd_sim(args, out):
    args.sim = True
    lk = open_link(args, out)
    if not lk:
        return out.done(2)
    try:
        lk.sim_enable(args.state == "on")
        time.sleep(0.4)
        out.put(mode=lk.live()["mode"])
        out.say("simulated robot mode: " + lk.live()["mode"])
        return out.done()
    finally:
        lk.close()


def cmd_brief(args, out):
    path = os.path.join(REPO, "docs", "AGENT_TUNING.md")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else "docs/AGENT_TUNING.md is missing."
    out.put(brief=text)
    out.say(text)
    return out.done()


def cmd_gui(args, out):
    from . import server

    return server.main(args)


# ---------------------------------------------------------------------------- parser


def _common(parser, suppress):
    """Options that work before or after the command: ``lint --project X`` and ``--project X lint``."""
    d = (lambda v: argparse.SUPPRESS) if suppress else (lambda v: v)
    parser.add_argument("--json", action="store_true", default=d(False),
                        help="print one JSON object (for agents)")
    parser.add_argument("--project", default=d(None), help="robot project folder, e.g. Peashooter")
    parser.add_argument("--host", default=d(None),
                        help="robot address (default: from the project's team number)")
    parser.add_argument("--team", type=int, default=d(None), help="team number, if not in the project")
    parser.add_argument("--sim", action="store_true", default=d(False),
                        help="talk to the simulator on this laptop")
    parser.add_argument("--connect-timeout", type=float, default=d(6.0))


class _Sub(argparse.ArgumentParser):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        _common(self, suppress=True)


def build_parser():
    p = argparse.ArgumentParser(prog="swervetune", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(p, suppress=False)
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=_Sub)

    sub.add_parser("lint", help="check YAGSL configs (no robot needed)").set_defaults(fn=cmd_lint)

    s = sub.add_parser("status", help="robot, environment, live modules, problems")
    s.add_argument("--watch", type=float, default=1.0, help="seconds of live data to judge")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("env", help="tell the robot where it is")
    s.add_argument("--mode", choices=["BLOCKS", "FIELD", "UNSET", "blocks", "field", "unset"])
    s.add_argument("--tags", choices=["on", "off"], help="AprilTags present")
    s.add_argument("--space", type=float, help="clear floor ahead, m")
    s.add_argument("--side", type=float, help="clear floor to each side, m")
    s.add_argument("--cap", type=float, help="speed cap for tests, m/s")
    s.set_defaults(fn=cmd_env)

    s = sub.add_parser("run", help="run a test on the robot and analyze it")
    s.add_argument("test", help=", ".join(C.TESTS))
    s.add_argument("--module", default="ALL", help="ALL, FL, FR, BL, BR or a module name")
    s.add_argument("--arg", action="append", help="test argument key=value, repeatable")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("runs", help="saved runs, newest first, with score and cost")
    s.add_argument("--show", choices=["robot", "sim", "practice", "all"], default="robot",
                   help="robot (default): the real robot only; sim; practice (the practice pod); all")
    s.add_argument("--test", help="only this test, e.g. steer_step")
    s.add_argument("--robot", help="only this robot, e.g. Peashooter")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_runs)

    s = sub.add_parser("analyze", help="re-analyze a saved run")
    s.add_argument("run")
    s.add_argument("--tape-forward", type=float, help="straight test: tape-measured forward m")
    s.add_argument("--tape-lateral", type=float, help="straight test: tape-measured sideways m")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("explain", help="what the controller saw and did in a saved step run")
    s.add_argument("run")
    s.add_argument("--module", type=int, help="channel index, e.g. 0")
    s.add_argument("--step", type=int, help="only this step")
    s.set_defaults(fn=cmd_explain)

    s = sub.add_parser("predict", help="'what if': a saved step run predicted with changed gains")
    s.add_argument("run")
    s.add_argument("gains", nargs="+", help="Name=value, e.g. Steer/kP=0.02 FF/frontleft/kS=0.15")
    s.add_argument("--module", type=int, default=0, help="channel index, e.g. 0")
    s.set_defaults(fn=cmd_predict)

    s = sub.add_parser("export", help="a saved run as a WPILOG for AdvantageScope (and SysId for drive_ff)")
    s.add_argument("run")
    s.add_argument("--out", help="output .wpilog path (default: next to the run)")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("logsummary", help="what went wrong in a match log (.wpilog), and where to look")
    s.add_argument("log")
    s.set_defaults(fn=cmd_logsummary)

    s = sub.add_parser("ppcheck", help="does PathPlanner describe the same robot as the code? (exit 1 if not)")
    s.add_argument("--fix", action="store_true", help="show the settings.json change that makes it match")
    s.add_argument("--yes", action="store_true", help="with --fix: write it")
    s.set_defaults(fn=cmd_ppcheck)

    s = sub.add_parser("pdhports", help="which PDH port feeds each motor: from a pdh_map run or a .wpilog")
    s.add_argument("source", help="a saved pdh_map run (file name) or a practice log (.wpilog)")
    s.set_defaults(fn=cmd_pdhports)

    s = sub.add_parser("layout", help="write the AdvantageScope layout for each robot")
    s.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "advantagescope"))
    s.set_defaults(fn=cmd_layout)

    s = sub.add_parser("gains", help="show or change live gains")
    s.add_argument("action", nargs="?", default="show", choices=["show", "set"])
    s.add_argument("values", nargs="*", help="Name=value, e.g. Steer/kP=0.015")
    s.add_argument("--force", action="store_true", help="allow more than a 2x step")
    s.set_defaults(fn=cmd_gains)

    s = sub.add_parser("save", help="write the robot's live gains into the JSON files")
    s.add_argument("what", choices=["gains"])
    s.add_argument("--keys", nargs="*", help="only gains starting with these, e.g. Steer FF")
    s.add_argument("--yes", action="store_true", help="actually write")
    s.set_defaults(fn=cmd_save)

    s = sub.add_parser("config", help="a report's config action: show the file change (--yes writes it)")
    s.add_argument("--file", required=True, help="e.g. swervedrive.json or modules/physicalproperties.json")
    s.add_argument("--path", required=True, help="dot-separated, e.g. conversionFactors.drive.diameter, or a JSON list")
    s.add_argument("--value", required=True, help="JSON (2.95, true, \"text\") or plain text")
    s.add_argument("--yes", action="store_true", help="write it (only with a person's OK)")
    s.set_defaults(fn=cmd_config)
    s = sub.add_parser("offsets", help="new absolute offsets from a straight-wheels capture")
    s.add_argument("run")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(fn=cmd_offsets)

    s = sub.add_parser("diagnose", help="the troubleshooter")
    s.add_argument("symptom", nargs="?")
    s.set_defaults(fn=cmd_diagnose)

    s = sub.add_parser("watch", help="print problems as the monitor spots them")
    s.add_argument("--seconds", type=float, default=30)
    s.set_defaults(fn=cmd_watch)

    s = sub.add_parser("motors", help="heat, stalls and failures for every watched motor")
    s.add_argument("--override", metavar="NAME", help="hold heat shutoffs at half current: a motor"
                   " name or ALL (stalls still cut out)")
    s.add_argument("--seconds", type=float, default=C.MAX_OVERRIDE_S,
                   help=f"override length, at most {C.MAX_OVERRIDE_S} s; 0 cancels")
    s.add_argument("--events", type=int, default=10, help="recent stage changes to show")
    s.set_defaults(fn=cmd_motors)

    for name, fn, help_ in (("practice", cmd_practice, "one run on the practice pod"),
                            ("rehearse", cmd_rehearse, "the full advice loop on the practice pod")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("loop", choices=["steer", "drive"])
        s.add_argument("--surface", choices=["floor", "blocks"], default="floor")
        s.add_argument("--kp", type=float, default=0.01)
        s.add_argument("--ki", type=float, default=0.0)
        s.add_argument("--kd", type=float, default=0.0)
        s.add_argument("--izone", type=float, default=0.0)
        s.add_argument("--ramp", type=float, default=0.0)
        s.add_argument("--ks", type=float, default=0.0)
        s.add_argument("--kv", type=float, default=None, help="default: YAGSL's, 12 V over the free speed")
        s.add_argument("--motor", choices=["neo", "vortex"], default=None,
                       help="the pod's drive motor; default: the --project robot's, else neo")
        s.add_argument("--ka", type=float, default=0.0)
        s.add_argument("--vel-period", type=int, default=0)
        s.add_argument("--vel-depth", type=int, default=0)
        s.add_argument("--rounds", type=int, default=12)
        s.set_defaults(fn=fn)

    s = sub.add_parser("sim", help="enable or disable the simulated robot")
    s.add_argument("state", choices=["on", "off"])
    s.set_defaults(fn=cmd_sim)

    sub.add_parser("brief", help="the rules an AI agent follows").set_defaults(fn=cmd_brief)

    s = sub.add_parser("gui", help="open the GUI in a browser")
    s.add_argument("--port", type=int, default=5806)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_gui)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if "--json" in raw:
        # Bad input still answers with one JSON object, as --json promises.
        def json_error(message):
            print(json.dumps({"ok": False, "error": message, "code": "BAD_ARGS"}))
            raise SystemExit(2)
        parser.error = json_error
        for action in parser._actions:
            sub = getattr(action, "choices", None)
            if isinstance(sub, dict):
                for p in sub.values():
                    p.error = json_error
    args = parser.parse_args(argv)
    out = Out(args.json)
    try:
        return args.fn(args, out)
    except KeyboardInterrupt:
        return out.done(130)
