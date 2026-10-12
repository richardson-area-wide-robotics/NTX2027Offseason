"""Which PDH port feeds each motor controller, found from the robot instead of typed in.

Two ways, because they suit different motors:

* **Pulse on blocks** (the robot test ``pdh_map``): the swerve motors are pulsed one at a time
  while the robot records every PDH channel. Each pulse is compared with the quiet moment just
  before it; the channel that rose is that motor's port. Swerve motors only - they can spin freely
  on blocks, where a mechanism might hit a hard stop.
* **From a practice log**: AdvantageKit logs each watched motor's current and every PDH channel's
  current. A motor's port is the channel whose current goes up and down with it. This needs no
  special test, so it works for mechanisms - but motors that always run together (a leader and its
  follower, the four drive motors) cannot be told apart this way, and are reported as a group with
  the ports they share between them.

Either way the result is a proposal: a student looks at it and saves it to the wiring map.

Worth knowing when reading the numbers: the PDH measures current on the **battery side** of the
controller. A controller running a motor at a quarter of full voltage draws about a quarter of the
motor's current from the battery (the rest is the motor's current circulating through the
controller), so the PDH reads much less than the controller reports for its motor.
"""

from __future__ import annotations

import math
import re

MIN_RISE_A = 0.3        # a pulse that moves no channel by this much found nothing
CLEAR_RATIO = 2.0       # the winner must rise this many times more than the runner-up
MIN_ACTIVE_A = 3.0      # a motor that never drew this much in a log never really ran
MIN_CORR = 0.6          # a log match weaker than this is not a match
CORR_MARGIN = 0.15      # the best channel must beat the runner-up by this much
TOGETHER_CORR = 0.9     # motors whose currents track each other this closely ran together


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def _verdict(port, mapped):
    if port is None:
        return "not found"
    if mapped is None:
        return "new"
    return "same" if int(mapped) == int(port) else "differs"


def _findings(rows, source):
    out = []
    by_port = {}
    for r in rows:
        if r["status"] == "found":
            by_port.setdefault(r["port"], []).append(r["name"])
    for port, names in sorted(by_port.items()):
        if len(names) > 1:
            out.append({"level": "error", "title": f"{' and '.join(names)} all drew from PDH port {port}",
                        "why": "Every motor controller needs its own breaker. Either they really share "
                               "a port (rewire one of them), or one of them did not run - check it "
                               "turned during the test.",
                        "where": {"devices": names}})
    for r in rows:
        n = r["name"]
        if r["verdict"] == "differs":
            out.append({"level": "warn",
                        "title": f"The map says {n} is on PDH port {r['mapped']}, but it drew from port {r['port']}",
                        "why": "Save the found port if the map was wrong. If port "
                               f"{r['mapped']} was what the team intended, the power leads are on the "
                               "wrong breaker.",
                        "where": {"devices": [n]}})
        elif r["status"] == "none":
            out.append({"level": "warn", "title": f"{'Pulsing ' if source == 'pulse' else ''}{n} moved no PDH port",
                        "why": "It may be powered from somewhere other than this PDH (a second PDH, "
                               "a mini power module), or it did not turn - check it moved in the run, "
                               "and that its breaker is seated.",
                        "where": {"devices": [n]}})
        elif r["status"] == "unclear":
            out.append({"level": "info",
                        "title": f"{n}: ports {r['port_guess']} and {r['runner_up']} rose about equally",
                        "why": "Something else changed at the same moment. Run it again with nothing "
                               "else running (compressor off, mechanisms still).",
                        "where": {"devices": [n]}})
    return out


# ============================================================================ pulse on blocks


def from_pulses(doc, wiring_map=None):
    """Ports from a ``pdh_map`` run: ``{"rows", "proposed", "findings", "channels"}``."""
    ch = doc.get("channels") or {}
    names = {}
    for note in doc.get("notes") or []:
        mm = re.match(r"pulse (\d+): (.+)$", note)
        if mm:
            names[int(mm.group(1))] = mm.group(2)
    ports = sorted(int(k[3:]) for k in ch if re.fullmatch(r"pdh\d+", k))
    mapped = (wiring_map or {}).get("pdhPorts") or {}
    if not ports:
        return {"rows": [], "proposed": {}, "channels": 0, "findings": [{
            "level": "error", "title": "This run has no PDH currents",
            "why": "The simulator has no PDH, and on a robot AdvantageKit must be running to read it. "
                   "Run it on the robot, on blocks."}]}
    slot = ch.get("slot") or []
    on = ch.get("on") or []
    n = min(len(slot), len(on), *(len(ch[f"pdh{p}"]) for p in ports))
    if all(max((abs(v) for v in ch[f"pdh{p}"][:n] if v == v), default=0.0) < 0.01 for p in ports):
        sim = doc.get("env") == "SIM"
        return {"rows": [], "proposed": {}, "channels": len(ports), "source": "pulse", "findings": [{
            "level": "info" if sim else "error", "title": "Every PDH channel read zero for the whole run",
            "why": "Expected in the simulator, which has no PDH currents: this run only checked the pulse "
                   "sequence. On a robot it means the PDH is not being read - check it is on the CAN bus "
                   "(its status light, REV Hardware Client)." if sim else
                   "The PDH is not being read: check it is on the CAN bus (its status light, REV Hardware "
                   "Client) and that its CAN ID is the one AdvantageKit expects."}]}
    rows = []
    for k in sorted(names):
        quiet = [i for i in range(n) if slot[i] == k and on[i] == 0]
        pulse = [i for i in range(n) if slot[i] == k and on[i] == 1]
        # The settled half of the quiet moment, and the pulse without its first readings: the PDH's
        # snapshot lags the command by a loop, and a channel still settling would blur the baseline.
        quiet = quiet[len(quiet) // 2:]
        pulse = pulse[max(2, len(pulse) // 10):]
        row = {"name": names[k], "port": None, "rise_a": None, "runner_up": None, "runner_up_a": None,
               "mapped": mapped.get(names[k])}
        if len(quiet) < 3 or len(pulse) < 3:
            row.update(status="none", why="the run ended before this motor's pulse")
        else:
            rises = sorted(((_mean([ch[f"pdh{p}"][i] for i in pulse])
                             - _mean([ch[f"pdh{p}"][i] for i in quiet]), p) for p in ports), reverse=True)
            (r1, p1), (r2, p2) = rises[0], rises[1] if len(rises) > 1 else (0.0, None)
            row.update(rise_a=r1, runner_up=p2, runner_up_a=r2)
            if r1 < MIN_RISE_A:
                row.update(status="none", port_guess=p1)
            elif r2 * CLEAR_RATIO > r1:
                row.update(status="unclear", port_guess=p1)
            else:
                row.update(status="found", port=p1)
        row["verdict"] = _verdict(row["port"], row["mapped"])
        rows.append(row)
    return {"rows": rows, "channels": len(ports), "source": "pulse",
            "proposed": {r["name"]: r["port"] for r in rows if r["status"] == "found"},
            "findings": _findings(rows, "pulse")}


# ============================================================================ from a practice log


def _resample(series, grid):
    """Step-hold a ``[(t, v), ...]`` series onto ``grid`` (AdvantageKit logs only changes)."""
    out, j, v = [], 0, None
    for t in grid:
        while j < len(series) and series[j][0] <= t:
            v = series[j][1]
            j += 1
        out.append(v)
    return out


def _ranks(xs):
    order = sorted(range(len(xs)), key=xs.__getitem__)
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def _pearson(a, b):
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    sab = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    saa = sum((x - ma) ** 2 for x in a)
    sbb = sum((y - mb) ** 2 for y in b)
    return sab / math.sqrt(saa * sbb) if saa > 0 and sbb > 0 else 0.0


def from_log(series, wiring_map=None):
    """Ports from a log's motor currents and PDH channels (``logsummary.read`` output)."""
    pdh = series.get("/PowerDistribution/ChannelCurrent") or []
    prefix, suffix = "/RealOutputs/Motors/", "/Amps"
    motors = {k[len(prefix):-len(suffix)]: v for k, v in series.items()
              if k.startswith(prefix) and k.endswith(suffix) and v}
    mapped = (wiring_map or {}).get("pdhPorts") or {}
    if not pdh or not motors:
        return {"rows": [], "proposed": {}, "channels": 0, "source": "log", "findings": [{
            "level": "error", "title": "This log has no PDH or motor currents",
            "why": "It needs AdvantageKit's PowerDistribution log and the motor guard's Motors/<name>/Amps "
                   "- a log from this branch's robot code."}]}
    enabled = series.get("/DriverStation/Enabled") or []
    t0 = max(pdh[0][0], min(v[0][0] for v in motors.values()))
    t1 = pdh[-1][0]
    step = max(0.05, (t1 - t0) / 6000)
    grid = [t0 + i * step for i in range(int((t1 - t0) / step) + 1)]
    on = _resample(enabled, grid) if enabled else [True] * len(grid)
    keep = [i for i, e in enumerate(on) if e]
    pdh_rows = [_resample(pdh, grid)[i] for i in keep]
    nch = max((len(r) for r in pdh_rows if r), default=0)
    channels = [[(r[c] if r and c < len(r) else 0.0) for r in pdh_rows] for c in range(nch)]
    ch_ranks = [_ranks(c) for c in channels]
    amps = {}
    for n, v in motors.items():
        full = _resample(v, grid)
        amps[n] = [abs(full[i] or 0.0) for i in keep]
    m_ranks = {n: _ranks(a) for n, a in amps.items()}
    rows, corr_of = [], {}
    for name in sorted(amps):
        a = amps[name]
        row = {"name": name, "port": None, "mapped": mapped.get(name), "peak_a": max(a, default=0.0),
               "corr": None, "runner_up": None, "runner_up_corr": None, "together": []}
        if row["peak_a"] < MIN_ACTIVE_A:
            row.update(status="idle")
        else:
            cs = sorted(((_pearson(m_ranks[name], ch_ranks[c]), c) for c in range(nch)), reverse=True)
            corr_of[name] = dict((c, r) for r, c in cs)
            (c1, p1), (c2, p2) = cs[0], cs[1] if len(cs) > 1 else (0.0, None)
            row.update(corr=c1, runner_up=p2, runner_up_corr=c2)
            row["together"] = [o for o in sorted(amps) if o != name and max(amps[o], default=0) >= MIN_ACTIVE_A
                               and _pearson(a, amps[o]) >= TOGETHER_CORR]
            if row["together"]:
                # A leader and follower track each other exactly; so do the four drive motors. Their
                # best channels say "one of these ports", never which.
                row.update(status="together", port_guess=p1)
            elif c1 < MIN_CORR:
                row.update(status="none", port_guess=p1)
            elif c1 - c2 < CORR_MARGIN:
                row.update(status="unclear", port_guess=p1)
            else:
                row.update(status="found", port=p1)
        row["verdict"] = _verdict(row["port"], row["mapped"])
        rows.append(row)
    findings = _findings([r for r in rows if r["status"] != "together"], "log")
    seen = set()
    for r in rows:
        if r["status"] != "together" or r["name"] in seen:
            continue
        group = [r["name"]] + [o for o in r["together"] if o not in seen]
        seen.update(group)
        # The group's ports: the channels that track the group best, one per motor in it.
        score = {c: sum(corr_of[g].get(c, 0.0) for g in group) / len(group) for c in range(nch)}
        guesses = sorted(sorted(score, key=score.get, reverse=True)[:len(group)])
        findings.append({"level": "info", "title": f"{', '.join(group)} always ran together",
                         "why": "Their currents rise and fall at the same moments, so this log cannot say "
                                "which is on which port" + (f" (between them: ports {', '.join(map(str, guesses))})"
                                                            if guesses else "")
                                + ". Swerve motors: use the pulse test on blocks. A leader and follower: "
                                  "unplug one at a time with the robot off, or read the labels.",
                         "where": {"devices": group}})
    idle = [r["name"] for r in rows if r["status"] == "idle"]
    if idle:
        findings.append({"level": "info", "title": f"Never ran in this log: {', '.join(idle)}",
                         "why": "A motor has to draw some current for its port to show. Use a log where "
                                "it ran, or type its port in."})
    return {"rows": rows, "channels": nch, "source": "log", "duration_s": len(keep) * step,
            "proposed": {r["name"]: r["port"] for r in rows if r["status"] == "found"},
            "findings": findings}


def merge(wiring_map, proposed):
    """A copy of the map with the proposed ports written in."""
    import copy

    m = copy.deepcopy(wiring_map)
    m.setdefault("pdhPorts", {}).update({k: int(v) for k, v in proposed.items()})
    return m
