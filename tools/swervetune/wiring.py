"""Where CAN and power faults come from: a map of the robot's wiring, and rules that read it.

**The map** (``<robot>/src/main/deploy/wiring.json``, versioned with the robot) says, for each CAN
bus, the order the devices sit in along the daisy chain, which device ends the chain with its
terminator, which PDH port feeds each controller, and how long the cable segments are. It starts
pre-filled from the code - YAGSL's module files, every ``new SparkMax(id)`` / ``new SparkFlex(id)``,
the PDH - with the chain in CAN-ID order and marked unconfirmed, because the real order cannot be
read electrically: CAN has no notion of position. A student confirms it by looking, once.

**The rules** turn what the robot reports into where to look:

* A controller passes CAN straight through, even unpowered. So **one device missing on its own,
  with its neighbors present, is that device**: its power (PDH port, breaker, leads) or the
  controller itself. **Everything from some point to the end of the chain missing together is the
  cable or plug at that point** - and that break also cuts the far terminator off, so the devices
  still connected see errors.
* A controller that **rebooted** lost power, however briefly: its power leads, its PDH port or
  breaker. Many rebooting at once with the battery dipping is the main power path instead.
* A controller warning of **low supply voltage** while the PDH holds steady has too much resistance
  in its own feed: a loose Wago, a bad crimp, a breaker not seated. With a PDH port mapped, the
  voltage drop over the current measures that resistance.
* **Bus errors**: the CAN controller's receive and transmit error counters climbing, or the bus
  shutting itself down (bus-off), mean termination is missing, doubled or shorted, or a connection is
  bad. A healthy bus reads about 60 ohms between CAN-H and CAN-L with the power off - two 120 ohm
  terminators, one at each end.
* **Length**: CAN at 1 Mbit/s is specified to 40 m; a robot never gets near that, so length is
  reported, and only flagged far beyond what a robot needs.
"""

from __future__ import annotations

import json
import math
import os
import re

DEFAULT_SEGMENT_M = 0.5
MAX_BUS_M = 40.0          # ISO 11898 high-speed CAN at 1 Mbit/s
LONG_BUS_M = 20.0         # unusual on a robot; worth a look
FEED_R_WARN = 0.035       # ohms, PDH to controller and back: 12 AWG and two good joints is ~0.015
FEED_R_BAD = 0.070


def _times(n):
    n = int(n)
    return "once" if n == 1 else f"{n} times"


def _level(lvl, title, why, where=None, fix=None):
    d = {"level": lvl, "title": title, "why": why}
    if where:
        d["where"] = where
    if fix:
        d["fix"] = fix
    return d


# ============================================================================ discovery


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def discover(project):
    """Every CAN device the robot code names, as dicts: name, kind, can_id, model, source."""
    out = []
    for n in project.module_names():
        mod = project.module(n)
        for part, label in (("drive", "drive"), ("angle", "steer")):
            m = mod.get(part) or {}
            out.append({"name": f"{n} {label}", "kind": "controller", "can_id": _int(m.get("id")),
                        "model": m.get("type", ""), "source": f"swerve/modules/{n}.json"})
        enc = mod.get("encoder") or {}
        if enc.get("type") not in (None, "attached", "none", "sparkmax_attached", "sparkflex_attached"):
            out.append({"name": f"{n} encoder", "kind": "encoder", "can_id": _int(enc.get("id")),
                        "model": enc.get("type", ""), "source": f"swerve/modules/{n}.json"})
    imu = (project.data.get("swervedrive.json") or {}).get("imu") or {}
    if imu.get("type") and "spi" not in imu["type"] and "usb" not in imu["type"] and "mxp" not in imu["type"]:
        out.append({"name": "gyro", "kind": "gyro", "can_id": _int(imu.get("id")), "model": imu["type"],
                    "source": "swerve/swervedrive.json"})
    for rel, src in project.java.items():
        if "Drive.java" in rel:
            continue
        consts = {k: int(v) for k, v in re.findall(r"\b([A-Z_][A-Z0-9_]*)\s*=\s*(\d+)\s*;", src)}
        names = dict((var, label) for label, var in re.findall(r'\.watch\(\s*"([^"]+)"\s*,\s*(\w+)', src))
        for var, cls, arg in re.findall(r"(\w+)\s*=\s*new\s+(Spark(?:Max|Flex))\(\s*(\w+)", src):
            cid = _int(arg) if arg.isdigit() else consts.get(arg)
            out.append({"name": names.get(var, f"{os.path.splitext(os.path.basename(rel))[0]} {var}"),
                        "kind": "controller", "can_id": cid, "model": cls,
                        "source": os.path.basename(rel)})
    return out


def default_map(project):
    devices = [d for d in discover(project) if d["can_id"] is not None]
    devices.sort(key=lambda d: d["can_id"])
    return {
        "_readme": "The robot's wiring for the swerve tools' Wiring tab. 'chain' is the order devices "
                   "sit along the CAN cable from the roboRIO to the far end; check it on the robot and "
                   "set orderConfirmed. pdhPorts: which PDH port feeds each controller.",
        "pdh": {"model": "REV PDH", "canId": 1, "terminationOn": True},
        "buses": [{
            "name": "roboRIO CAN",
            "chain": ["roboRIO"] + [d["name"] for d in devices] + ["PDH"],
            "orderConfirmed": False,
            "segmentLengthsM": {},
        }],
        "pdhPorts": {},
        "extraDevices": [],
    }


def map_path(project):
    return os.path.join(project.path, "src", "main", "deploy", "wiring.json")


def load_map(project):
    """The robot's map, or a fresh one from the code. New devices in the code are added unconfirmed."""
    path = map_path(project)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            m = json.load(fh)
    else:
        m = default_map(project)
    known = {name for bus in m["buses"] for name in bus["chain"]}
    for d in discover(project):
        if d["can_id"] is not None and d["name"] not in known:
            chain = m["buses"][0]["chain"]
            chain.insert(len(chain) - 1 if chain and chain[-1] == "PDH" else len(chain), d["name"])
            m["buses"][0]["orderConfirmed"] = False
    return m


def map_text(m):
    return json.dumps(m, indent=2) + "\n"


def devices_by_name(project, m):
    found = {d["name"]: d for d in discover(project)}
    for d in m.get("extraDevices", []):
        found[d["name"]] = d
    found["roboRIO"] = {"name": "roboRIO", "kind": "roborio", "can_id": None, "model": "roboRIO",
                        "source": "built in: 120 ohm terminator"}
    pdh = m.get("pdh", {})
    found["PDH"] = {"name": "PDH", "kind": "pdh", "can_id": pdh.get("canId", 1),
                    "model": pdh.get("model", "REV PDH"), "source": "power distribution"}
    return found


def bus_length(bus):
    lengths = bus.get("segmentLengthsM", {})
    total = 0.0
    measured = 0
    for a, b in zip(bus["chain"], bus["chain"][1:]):
        v = lengths.get(f"{a}|{b}")
        if v is not None:
            measured += 1
            total += float(v)
        else:
            total += DEFAULT_SEGMENT_M
    return total, measured, max(0, len(bus["chain"]) - 1)


# ============================================================================ checks


def termination_verdict(ohms):
    """What a multimeter reading across CAN-H and CAN-L, robot powered off, means."""
    if ohms is None or not math.isfinite(ohms):
        return _level("info", "No reading", "Measure between CAN-H (yellow) and CAN-L (green) with every "
                      "device unpowered: powered devices make the reading meaningless.")
    if ohms < 30:
        return _level("error", f"{ohms:.0f} ohms: too low",
                      "A short between CAN-H and CAN-L (a pinched or stray strand) or three or more "
                      "terminators. Look for crushed wire and for a device with termination switched on "
                      "in the middle of the chain.")
    if ohms < 50:
        return _level("warn", f"{ohms:.0f} ohms: one terminator too many",
                      "About 40 ohms is three 120 ohm terminators. Only the two ends of the chain may "
                      "terminate: the roboRIO (always on) and the far end, usually the PDH's switch.")
    if ohms <= 70:
        return _level("ok", f"{ohms:.0f} ohms: correctly terminated",
                      "Two 120 ohm terminators, one at each end. Termination is not the problem.")
    if ohms <= 150:
        return _level("error", f"{ohms:.0f} ohms: one terminator missing",
                      "About 120 ohms is one terminator. Either the far end is not terminated (the PDH's "
                      "termination switch is off, or the chain does not end at the PDH) or the cable is "
                      "broken between where you measured and one end.")
    return _level("error", f"{ohms:.0f} ohms: open",
                  "No terminator reached: a broken CAN wire right where you measured, or both ends "
                  "unterminated.")


def feed_resistance(samples):
    """Ohms of one controller's power path from (pdh_volts, controller_volts, amps) samples.

    Fits drop = R * I + offset by least squares, so a constant meter offset between the PDH and the
    controller cancels. Needs a spread of currents; returns None without one.
    """
    pts = [(i, p - c) for p, c, i in samples
           if all(x is not None and math.isfinite(x) for x in (p, c, i))]
    if len(pts) < 10:
        return None
    xs = [i for i, _ in pts]
    if max(xs) - min(xs) < 8.0:
        return None
    n = len(pts)
    mx = sum(xs) / n
    my = sum(d for _, d in pts) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (d - my) for x, d in pts)
    return sxy / sxx if sxx > 0 else None


def diagnose(m, snapshot, devices=None):
    """Findings for one moment: which device, link or feed to look at, and why.

    ``snapshot``: ``motors`` (the robot's motor rows), ``can`` (utilization, bus-off, TX-full,
    receive errors, transmit errors), optionally ``pdh`` ({voltage}) and ``feed_r`` ({name: ohms}).
    """
    F = []
    rows = {r["name"]: r for r in snapshot.get("motors") or [] if r.get("name")}
    ports = m.get("pdhPorts", {})

    def port(name):
        p = ports.get(name)
        return f"PDH port {p}" if p is not None else "its PDH port"

    for bus in m.get("buses", []):
        chain = bus["chain"]
        confirmed = bus.get("orderConfirmed", False)
        tracked = [i for i, n in enumerate(chain) if n in rows]
        absent = [i for i in tracked if rows[chain[i]].get("present") == 0]
        if absent:
            first = absent[0]
            tail = [i for i in tracked if i >= first]
            if len(absent) >= 2 and absent == tail:
                before = chain[first - 1]
                where = {"devices": [chain[i] for i in absent], "segment": [before, chain[first]]}
                F.append(_level(
                    "error", f"Everything from {chain[first]} to the end of the chain is off the CAN bus",
                    f"{len(absent)} devices in a row, from {chain[first]} onward, went silent together. "
                    f"Controllers pass CAN through even when unpowered, so this is the CAN cable between "
                    f"{before} and {chain[first]}, or the CAN connectors at either end of it. The break also "
                    "cuts off the far terminator, so the devices still connected will see errors."
                    + ("" if confirmed else " (The chain order in the map is not confirmed yet, so check "
                       "the order first.)"),
                    where, "Reseat and inspect that cable and both plugs; look for a crushed or pulled wire."))
            else:
                for i in absent:
                    name = chain[i]
                    nb = [chain[j] for j in (i - 1, i + 1) if 0 <= j < len(chain)]
                    F.append(_level(
                        "error", f"{name} is off the CAN bus on its own",
                        f"Its neighbors ({', '.join(nb)}) are still heard, and CAN passes through a "
                        f"controller even unpowered, so the cable is fine. Most likely {name} has no "
                        f"power: {port(name)}, its breaker, or its power leads. Otherwise the controller "
                        "itself (a blink code on its LED says which).",
                        {"devices": [name], "pdh_port": ports.get(name)},
                        "Check its LED: dark means no power; blinking a fault code means the controller."))
        # Past drops: a run of devices that each dropped out, starting at the same point.
        dropped = [i for i in tracked if (rows[chain[i]].get("dropouts") or 0) > 0]
        if dropped and not absent:
            first = dropped[0]
            run = [i for i in tracked if i >= first]
            if len(dropped) >= 2 and dropped == run:
                before = chain[first - 1]
                F.append(_level(
                    "warn", f"Devices from {chain[first]} onward have dropped off the CAN bus",
                    f"Each device from {chain[first]} to the end of the chain has dropped out at least "
                    f"once. An intermittent connection at that point: the cable between {before} and "
                    f"{chain[first]}, or a plug that only loses contact when the robot is hit or turns.",
                    {"devices": [chain[i] for i in dropped], "segment": [before, chain[first]]},
                    "Wiggle test: watch the Wiring tab live while wiggling that cable and its plugs."))
            else:
                for i in dropped:
                    name = chain[i]
                    F.append(_level(
                        "warn", f"{name} has dropped off the CAN bus {_times(rows[name]['dropouts'])}",
                        "Only it dropped, so its own power is the likeliest cause (a brief loss of power "
                        "makes a controller vanish from the bus while it restarts), then its CAN plugs.",
                        {"devices": [name], "pdh_port": ports.get(name)}))

    for name, r in rows.items():
        if (r.get("resets") or 0) > 0:
            F.append(_level(
                "warn", f"{name} lost power and rebooted {_times(r['resets'])}",
                f"A controller only reboots when its supply drops out. Check its power leads, {port(name)} "
                "and the breaker in it (fully seated?), and the Wago or crimp joints in between.",
                {"devices": [name], "pdh_port": ports.get(name)}))
        if (r.get("brownouts") or 0) > 0:
            F.append(_level(
                "warn", f"{name} saw low supply voltage {_times(r['brownouts'])}",
                "If the battery and PDH held up at the same time, the voltage was lost in this "
                "controller's own feed: a loose joint or a thin wire.",
                {"devices": [name], "pdh_port": ports.get(name)}))
    resets = [n for n, r in rows.items() if (r.get("resets") or 0) > 0]
    if len(resets) >= 3:
        F.append(_level(
            "warn", f"{len(resets)} controllers have rebooted",
            "Several at once points upstream of them all: the battery connection, the main breaker, "
            "the Anderson connector, or the PDH's own input lugs - or a battery that sags badly.",
            {"devices": resets}, "Check the main power path from the battery to the PDH, tight and clean."))

    for name, ohms in (snapshot.get("feed_r") or {}).items():
        if ohms is None:
            continue
        if ohms >= FEED_R_WARN:
            F.append(_level(
                "error" if ohms >= FEED_R_BAD else "warn",
                f"{name}'s power wiring measures {ohms * 1000:.0f} milliohms",
                f"Normal is about 15 milliohms there and back. Every amp loses voltage across it and heats "
                f"the joint. Look at {port(name)}, its breaker, and each joint to the controller.",
                {"devices": [name], "pdh_port": ports.get(name)}))

    can = snapshot.get("can") or []
    if len(can) >= 5:
        util, bus_off, tx_full, rx_err, tx_err = can[:5]
        if bus_off > 0:
            F.append(_level(
                "error", f"The CAN bus shut itself down {_times(bus_off)}",
                "Bus-off happens when transmissions keep failing: missing or doubled termination, CAN-H and "
                "CAN-L swapped somewhere, a short, or a break. Check termination with a multimeter "
                "(about 60 ohms, powered off).", {"bus": True}))
        if rx_err > 0 or tx_err > 0:
            F.append(_level(
                "warn", f"CAN errors happening now ({rx_err:.0f} receive, {tx_err:.0f} transmit)",
                "The error counters climb with every bad frame and fall with good ones, so above zero means "
                "it is happening now: a bad connection or termination. Wiggle-test while watching this.",
                {"bus": True}))
        if tx_full > 0:
            F.append(_level(
                "info", f"The roboRIO's transmit queue filled {_times(tx_full)}",
                "Frames waited to be sent: a busy bus, or nobody acknowledging (a disconnected bus).",
                {"bus": True}))
        u = util if util <= 1 else util / 100
        if u > 0.8:
            F.append(_level("warn", f"The CAN bus is {u * 100:.0f}% busy",
                            "Above about 80% frames start to wait. Slow down status frames you do not use.",
                            {"bus": True}))

    for bus in m.get("buses", []):
        total, measured, segs = bus_length(bus)
        if total > MAX_BUS_M:
            F.append(_level("error", f"{bus['name']} is about {total:.0f} m long",
                            f"Over the {MAX_BUS_M:.0f} m CAN allows at 1 Mbit/s.", {"bus": True}))
        elif total > LONG_BUS_M:
            F.append(_level("warn", f"{bus['name']} is about {total:.0f} m long",
                            "Within CAN's 40 m, but long for a robot: check for coiled spare cable.",
                            {"bus": True}))
    return F
