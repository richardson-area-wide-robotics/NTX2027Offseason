"""After a match or a practice run: what went wrong, when, and where to look.

Reads an AdvantageKit log (a ``.wpilog`` from the robot's USB stick, or downloaded by
AdvantageScope) and lists every event worth a look - brownouts, CAN dropouts, controllers that
rebooted, the CAN bus shutting down, breakers tripping, motors the guard stepped in on, loop
overruns - each with its time in the match and, through the robot's wiring map, the cable, plug or
power feed to check. Devices that dropped out together are judged together, the way the Wiring tab
judges them live: a run of them to the end of the chain is the cable at its start.
"""

from __future__ import annotations

from . import wiring

PREFIXES = ("/DriverStation/", "/SystemStats/", "/PowerDistribution/", "/RealOutputs/Motors/",
            "/RealOutputs/LoggedRobot/FullCycleMS", "/RealOutputs/SwerveTune/Test", "/RealMetadata/")
PDH_FAULT_BITS = {24: "brownout", 25: "CAN warning", 26: "hardware fault"}
PDH_STICKY_BITS = {24: "brownout", 25: "CAN warning", 26: "CAN bus-off", 27: "hardware fault",
                   28: "firmware fault", 29: "reset"}
GROUP_S = 0.3          # dropouts this close together are one event
OVERRUN_MS = 25.0


def read(path):
    """``{key: [(seconds, value), ...]}`` for the keys the summary reads."""
    from wpiutil.log import DataLogReader

    reader = DataLogReader(path)
    if not reader.isValid():
        raise ValueError(f"{path} is not a WPILOG file")
    starts, out = {}, {}
    getters = {"boolean": "getBoolean", "int64": "getInteger", "double": "getDouble", "float": "getFloat",
               "string": "getString", "double[]": "getDoubleArray"}
    for rec in reader:
        if rec.isStart():
            d = rec.getStartData()
            if d.name.startswith(PREFIXES) and d.type in getters:
                starts[d.entry] = (d.name, getters[d.type])
            continue
        if rec.isControl():
            continue
        e = starts.get(rec.getEntry())
        if not e:
            continue
        try:
            v = getattr(rec, e[1])()
        except Exception:  # noqa: BLE001 - a malformed record is skipped, not fatal
            continue
        if isinstance(v, (list, tuple)) or e[1] == "getDoubleArray":
            v = list(v)
        out.setdefault(e[0], []).append((rec.getTimestamp() / 1e6, v))
    return out


def _value_at(series, t):
    v = None
    for ts, x in series or []:
        if ts > t:
            break
        v = x
    return v


def _rising(series, test=bool):
    """Times a condition becomes true, with how long it lasted."""
    out, start = [], None
    for ts, v in series or []:
        if test(v) and start is None:
            start = ts
        elif not test(v) and start is not None:
            out.append((start, ts - start))
            start = None
    if start is not None:
        out.append((start, (series[-1][0] - start) if series else 0.0))
    return out


def _increments(series):
    """Times an integer counter goes up, and by how much."""
    out, last = [], None
    for ts, v in series or []:
        if last is not None and v is not None and v > last:
            out.append((ts, v - last))
        last = v
    return out


def phases(series):
    """[(start, end, 'auto' | 'teleop' | 'disabled')] from the Driver Station."""
    enabled, auto = series.get("/DriverStation/Enabled", []), series.get("/DriverStation/Autonomous", [])
    times = sorted({t for t, _ in enabled} | {t for t, _ in auto})
    out = []
    for i, t in enumerate(times):
        e, a = _value_at(enabled, t), _value_at(auto, t)
        name = "disabled" if not e else "auto" if a else "teleop"
        if out and out[-1][2] == name:
            continue
        if out:
            out[-1] = (out[-1][0], t, out[-1][2])
        out.append((t, t, name))
    if out and times:
        out[-1] = (out[-1][0], max(t for s in series.values() for t, _ in s[-1:]), out[-1][2])
    return out


def _when(t, ph):
    """'teleop +12.3 s' - time into the phase it happened in."""
    for i, (a, b, name) in enumerate(ph):
        if a <= t < b or (i == len(ph) - 1 and t >= a):
            return f"{name} +{t - a:.1f} s" if name != "disabled" else f"disabled, {t:.1f} s"
    return f"{t:.1f} s"


def motors_in(series):
    names = set()
    for k in series:
        if k.startswith("/RealOutputs/Motors/"):
            names.add(k[len("/RealOutputs/Motors/"):].rsplit("/", 1)[0])
    return sorted(names)


def snapshot_at(series, t):
    """The robot's motor rows as the Wiring tab would have seen them at time ``t``."""
    rows = []
    for m in motors_in(series):
        b = f"/RealOutputs/Motors/{m}/"
        present = _value_at(series.get(b + "Present"), t)
        rows.append({"name": m, "present": None if present is None else int(bool(present)),
                     "dropouts": _value_at(series.get(b + "Dropouts"), t) or 0,
                     "resets": _value_at(series.get(b + "Resets"), t) or 0,
                     "brownouts": _value_at(series.get(b + "Brownouts"), t) or 0,
                     "bus_volts": _value_at(series.get(b + "BusVolts"), t)})
    can = [_value_at(series.get("/SystemStats/CANBus/" + k), t) or 0
           for k in ("Utilization", "OffCount", "TxFullCount", "ReceiveErrorCount", "TransmitErrorCount")]
    return {"motors": rows, "can": can}


def summarize(series, wiring_map=None):
    """The report: match info, phases, a timeline of events, and where to look."""
    ph = phases(series)
    end = max((s[-1][0] for s in series.values() if s), default=0.0)
    events = []

    def ev(t, level, text, learn=None, where=None):
        events.append({"t": t, "when": _when(t, ph), "level": level, "text": text,
                       "learn": learn, "where": where or {}})

    for t, dur in _rising(series.get("/SystemStats/BrownedOut")):
        vmin = min((v for ts, v in series.get("/SystemStats/BatteryVoltage", []) if t - 1 <= ts <= t + dur + 1),
                   default=float("nan"))
        ev(t, "error", f"Brownout for {dur:.2f} s (battery down to {vmin:.1f} V): the roboRIO cut motor output.",
           "voltage_sag")
    batt = [v for _, v in series.get("/SystemStats/BatteryVoltage", []) if v and v > 1]
    for t, n in _increments(series.get("/SystemStats/CANBus/OffCount")):
        ev(t, "error", f"The CAN bus shut itself down{'' if n == 1 else f' {n} times'} (bus-off).",
           "can_termination", {"bus": True})
    for t, dur in _rising(series.get("/SystemStats/CANBus/ReceiveErrorCount"), lambda v: (v or 0) > 0):
        ev(t, "warn", f"CAN receive errors for {dur:.1f} s.", "can_termination", {"bus": True})
    for t, dur in _rising(series.get("/SystemStats/CANBus/TransmitErrorCount"), lambda v: (v or 0) > 0):
        ev(t, "warn", f"CAN transmit errors for {dur:.1f} s.", "can_termination", {"bus": True})

    ports = (wiring_map or {}).get("pdhPorts", {})
    by_port = {}
    for name, p in ports.items():
        by_port.setdefault(p, []).append(name)
    for key, bits, label in (("/PowerDistribution/Faults", PDH_FAULT_BITS, "PDH"),):
        last = 0
        for ts, v in series.get(key, []):
            v = int(v or 0)
            new = v & ~last
            for bit in range(24):
                if new & (1 << bit):
                    who = ", ".join(by_port.get(bit, [])) or "nothing mapped"
                    ev(ts, "error", f"PDH port {bit}'s breaker tripped ({who}).", "power_path",
                       {"pdh_port": bit, "devices": by_port.get(bit, [])})
            for bit, what in bits.items():
                if new & (1 << bit):
                    ev(ts, "warn", f"{label} reported a {what}.", "power_path")
            last = v

    drops = []
    for m in motors_in(series):
        b = f"/RealOutputs/Motors/{m}/"
        for t, dur in _rising(series.get(b + "Present"), lambda v: v is False or v == 0):
            drops.append((t, dur, m))
        for t, n in _increments(series.get(b + "Resets")):
            ev(t, "warn", f"{m} lost power and rebooted.", "power_path",
               {"devices": [m], "pdh_port": ports.get(m)})
        for t, n in _increments(series.get(b + "Brownouts")):
            ev(t, "info", f"{m} saw low supply voltage.", "power_path", {"devices": [m]})
        last = "OK"
        for ts, stage in series.get(b + "Stage", []):
            if stage != last and stage in ("WARN", "DERATE", "SHUTOFF"):
                ev(ts, "error" if stage == "SHUTOFF" else "warn", f"{m}: motor guard {stage}.",
                   "heat_estimate", {"devices": [m]})
            last = stage
        seen = set()
        for ts, flags in series.get(b + "Flags", []):
            for f in (flags or "").split("; "):
                if f and f not in seen and "not heard" not in f:
                    seen.add(f)
                    ev(ts, "warn", f"{m}: {f}.", None, {"devices": [m]})

    # Group dropouts that happened together, and judge each group with the wiring rules.
    drops.sort()
    groups, cur = [], []
    for d in drops:
        if cur and d[0] - cur[0][0] > GROUP_S:
            groups.append(cur)
            cur = []
        cur.append(d)
    if cur:
        groups.append(cur)
    where_to_look = []
    for g in groups:
        t0 = g[0][0]
        names = sorted({m for _, _, m in g})
        longest = max(d for _, d, _ in g)
        ev(t0, "error", f"Off the CAN bus for up to {longest:.2f} s: {', '.join(names)}.", "can_bus",
           {"devices": names})
        if wiring_map:
            snap = {"motors": [{"name": n, "present": 0 if n in names else 1} for n in motors_in(series)]}
            for f in wiring.diagnose(wiring_map, snap):
                f = dict(f)
                f["when"] = _when(t0, ph)
                where_to_look.append(f)

    cycles = [v for _, v in series.get("/RealOutputs/LoggedRobot/FullCycleMS", []) if v is not None]
    over = [v for v in cycles if v > OVERRUN_MS]
    events.sort(key=lambda e: e["t"])

    findings = []
    seen_titles = set()
    for f in where_to_look:
        if f["title"] not in seen_titles:
            seen_titles.add(f["title"])
            findings.append(f)
    resets = {}
    for e in events:
        if "rebooted" in e["text"]:
            m = e["where"]["devices"][0]
            resets[m] = resets.get(m, 0) + 1
    if wiring_map or resets:
        snap = {"motors": [{"name": m, "present": 1, "resets": n} for m, n in resets.items()]}
        for f in wiring.diagnose(wiring_map or {"buses": [], "pdhPorts": {}}, snap):
            if f["title"] not in seen_titles:
                seen_titles.add(f["title"])
                findings.append(f)
    if over and len(over) > 0.01 * max(1, len(cycles)):
        findings.append({"level": "warn", "title": f"{len(over)} robot loops ran long (worst {max(over):.0f} ms)",
                         "why": "Each loop should take 20 ms. Long loops make the robot stutter and every "
                                "control loop run late. AdvantageScope shows which part of the code took the "
                                "time (LoggedRobot/UserCodeMS, GCTimeMS)."})
    info = {k.split("/")[-1]: v[-1][1] for k, v in series.items()
            if k in ("/DriverStation/EventName", "/DriverStation/MatchNumber", "/DriverStation/MatchType",
                     "/DriverStation/FMSAttached") and v}
    errors = sum(1 for e in events if e["level"] == "error")
    warns = sum(1 for e in events if e["level"] == "warn")
    summary = ("Clean: nothing went wrong." if not events else
               f"{errors} errors and {warns} warnings in {end:.0f} s"
               + (f"; battery low {min(batt):.1f} V" if batt else ""))
    return {"info": info, "duration_s": end, "phases": ph, "battery_min": min(batt) if batt else None,
            "loop_overruns": len(over), "events": events, "findings": findings, "summary": summary}


def summarize_file(path, wiring_map=None):
    return summarize(read(path), wiring_map)

