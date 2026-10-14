"""AdvantageScope and SysId, so every run and every match looks the same in WPILib's own tools.

* :func:`export_run` writes a saved test run as a WPILOG file that AdvantageScope opens like a
  match log. A ``drive_ff`` run is also written the way WPILib's SysId expects - voltage, position
  and velocity per module, plus the test-state entry - so SysId's own analysis can check ours.
* :func:`layout` builds an AdvantageScope layout for a robot project: the swerve view, the field,
  motor heat, drive current, and battery and CAN health, all keyed the way the robot's
  AdvantageKit logging (``AkLogging.java``) records them. File > Import Layout in AdvantageScope.

Colors are AdvantageScope's own graph palette, so a module is the same color here, in the GUI and
in AdvantageScope.
"""

from __future__ import annotations

import json
import os
import random
import re
import string

# AdvantageScope's GraphColors, in its order.
GRAPH_COLORS = ["#2b66a2", "#e5b31b", "#af2437", "#80588e", "#e48b32", "#c0b487", "#858584",
                "#3b875a", "#d993aa", "#5f4528"]

SYSID_STATES = {1: "quasistatic-forward", 2: "quasistatic-reverse", 3: "dynamic-forward",
                4: "dynamic-reverse"}


def _writer(path):
    from wpiutil import DataLogWriter  # robotpy-wpiutil comes with pyntcore
    return DataLogWriter(path)


class LogWriter:
    """A WPILOG writer that flushes every 2,000 records.

    robotpy's DataLogWriter fails with "resource deadlock would occur" once its buffer fills, at
    roughly 75,000 records; flushing often keeps it from filling.
    """

    FLUSH_EVERY = 2000
    APPEND = {"double": "appendDouble", "string": "appendString", "int64": "appendInteger",
              "boolean": "appendBoolean", "double[]": "appendDoubleArray"}

    def __init__(self, path):
        self.log = _writer(path)
        self.count = 0

    def entry(self, name, kind, metadata="", ts=0):
        log, fn = self.log, getattr(self.log, self.APPEND[kind])
        eid = log.start(name, kind, metadata, ts)
        writer = self

        class _E:
            def append(self, value, stamp):
                fn(eid, value, stamp)
                writer.count += 1
                if writer.count % writer.FLUSH_EVERY == 0:
                    log.flush()
        return _E()

    def close(self):
        self.log.flush()
        self.log.stop()


def export_run(doc, path):
    """Writes one saved run as a WPILOG. Returns the entry names written."""
    ch = doc.get("channels") or {}
    t = ch.get("t") or []
    if not t:
        raise ValueError("this run has no samples")
    test = doc.get("test", "run")
    base = f"/SlothTune/{test}/"
    ts = [1_000_000 + int(round((x - t[0]) * 1e6)) for x in t]  # start one second in
    log = LogWriter(path)
    names = []
    for key, values in ch.items():
        if key == "t" or not isinstance(values, list) or len(values) != len(t):
            continue
        e = log.entry(base + key, "double", "", ts[0])
        for v, stamp in zip(values, ts):
            if v is not None:
                e.append(float(v), stamp)
        names.append(base + key)
    for key, value in (doc.get("meta") or {}).items():
        if isinstance(value, (int, float)):
            log.entry(base + "meta/" + key, "double", "", ts[0]).append(float(value), ts[0])
    notes = log.entry(base + "notes", "string", "", ts[0])
    for line in doc.get("notes") or []:
        notes.append(str(line), ts[0])
    if test == "drive_ff" and ch.get("phase"):
        names += _sysid_entries(log, doc, ch, ts)
    log.close()
    return names


def _sysid_entries(log, doc, ch, ts):
    """The drive_ff run in SysIdRoutineLog's own names and units."""
    mech = "drive"
    modules = (doc.get("robot") or {}).get("modules") or []
    out = []
    state = log.entry("sysid-test-state-" + mech, "string", "", ts[0])
    last = None
    for phase, stamp in zip(ch["phase"], ts):
        s = SYSID_STATES.get(int(phase), "none") if phase is not None else "none"
        if s != last:
            state.append(s, stamp)
            last = s
    if last != "none":
        state.append("none", ts[-1] + 1)
    out.append("sysid-test-state-" + mech)
    i = 0
    while f"m{i}.volts" in ch:
        name = modules[i] if i < len(modules) else f"module{i}"
        for field, key, unit in (("voltage", "volts", "Volt"), ("position", "pos", "Meter"),
                                 ("velocity", "v", "Meter per Second")):
            series = ch.get(f"m{i}.{key}")
            if not series:
                continue
            entry_name = f"{field}-{name}-{mech}"
            e = log.entry(entry_name, "double", unit, ts[0])
            for v, stamp in zip(series, ts):
                if v is not None:
                    e.append(float(v), stamp)
            out.append(entry_name)
        i += 1
    return out


# ---------------------------------------------------------------------------- layout


def _uuid():
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(32))


def _line_tab(title, left, right=(), discrete=()):
    def src(key, i, kind="stepped"):
        return {"type": kind, "logKey": key, "logType": "Number", "visible": True,
                "options": {"color": GRAPH_COLORS[i % len(GRAPH_COLORS)], "size": "normal"}}
    return {
        "type": 1, "title": title,
        "controller": {
            "leftSources": [src(k, i) for i, k in enumerate(left)],
            "rightSources": [src(k, i + len(left)) for i, k in enumerate(right)],
            "discreteSources": [{"type": "stripes", "logKey": k, "logType": "Boolean", "visible": True,
                                 "options": {"color": GRAPH_COLORS[(i + 4) % len(GRAPH_COLORS)]}}
                                for i, k in enumerate(discrete)],
            "leftLockedRange": None, "rightLockedRange": None,
            "leftUnitConversion": {"autoTarget": None, "preset": None},
            "rightUnitConversion": {"autoTarget": None, "preset": None},
            "leftFilter": 0, "rightFilter": 0,
        },
        "controllerUUID": _uuid(), "renderer": None, "controlsHeight": 200,
    }


def mechanism_motors(project):
    """Names robot code gives the motor guard: every ``w.watch("Name", ...)``."""
    names = []
    for src in project.java.values():
        names += re.findall(r'\.watch\(\s*"([^"]+)"', src)
    return list(dict.fromkeys(names))


def layout(project):
    """An AdvantageScope v26 layout for one robot project, as a dict."""
    modules = project.module_names()
    locs = [project.module(n)["location"] for n in modules]
    size_x = 2 * max(abs(l["front"]) for l in locs) * 0.0254 + 0.2
    size_y = 2 * max(abs(l["left"]) for l in locs) * 0.0254 + 0.2
    rr = "/RealOutputs/"
    swerve = {
        "type": 9, "title": "Swerve",
        "controller": {
            "sources": [
                {"type": "states", "logKey": rr + "SwerveStates/Measured", "logType": "SwerveModuleState[]",
                 "visible": True, "options": {"color": "#ff0000", "arrangement": "0,1,2,3"}},
                {"type": "states", "logKey": rr + "SwerveStates/Setpoints", "logType": "SwerveModuleState[]",
                 "visible": True, "options": {"color": "#00ffff", "arrangement": "0,1,2,3"}},
                {"type": "rotation", "logKey": rr + "Odometry/Robot/rotation", "logType": "Rotation2d",
                 "visible": True, "options": {}},
            ],
            "maxSpeed": round(project.max_module_speed(), 2), "sizeX": round(size_x, 2),
            "sizeY": round(size_y, 2), "orientation": 1,
        },
        "controllerUUID": _uuid(), "renderer": None, "controlsHeight": 200,
    }
    field = {
        "type": 3, "title": "Field",
        "controller": {"sources": [{"type": "robot", "logKey": rr + "Odometry/Robot", "logType": "Pose2d",
                                    "visible": True, "options": {"model": "Crab Bot"}}], "game": ""},
        "controllerUUID": _uuid(), "renderer": "", "controlsHeight": 200,
    }
    motors = [f"{m} drive" for m in modules] + [f"{m} steer" for m in modules] + mechanism_motors(project)
    tabs = [
        {"type": 0, "title": "", "controller": None, "controllerUUID": _uuid(), "renderer": "",
         "controlsHeight": 0},
        swerve, field,
        _line_tab("Motor heat (%)", [rr + f"Motors/{m}/HeatPct" for m in motors]),
        _line_tab("Drive current", [rr + f"Motors/{m} drive/Amps" for m in modules],
                  [rr + f"Motors/{m} drive/LimitA" for m in modules]),
        _line_tab("Steering current", [rr + f"Motors/{m} steer/Amps" for m in modules]),
        _line_tab("Battery and CAN", ["/SystemStats/BatteryVoltage"],
                  ["/SystemStats/CANBus/Utilization", "/SystemStats/CANBus/ReceiveErrorCount",
                   "/SystemStats/CANBus/TransmitErrorCount", "/SystemStats/CANBus/TxFullCount",
                   "/SystemStats/CANBus/OffCount"],
                  ["/SystemStats/BrownedOut"]),
        _line_tab("Controller supply voltage", [rr + f"Motors/{m}/BusVolts" for m in motors],
                  [], ["/SystemStats/BrownedOut"]),
        _line_tab("Robot heading", [rr + "Drive/GyroYawDeg"]),
    ]
    return {
        "hubs": [{"x": 120, "y": 80, "width": 1200, "height": 760, "state": {
            "sidebar": {"width": 300, "expanded": ["/RealOutputs", "/RealOutputs/Motors", "/SystemStats",
                                                   "/PowerDistribution"]},
            "tabs": {"selected": 1, "tabs": tabs}}}],
        "satellites": [], "version": "26.0.0",
    }


def write_layout(project, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{re.sub(r'[^A-Za-z0-9]+', '-', project.name).strip('-').lower()}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(layout(project), fh, indent=2)
        fh.write("\n")
    return path
