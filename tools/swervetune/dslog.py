"""The Driver Station's own logs: what the link to the robot did, 50 times a second.

The Driver Station writes two files a session in ``C:\\Users\\Public\\Documents\\FRC\\Log Files``
(newer versions in its ``DSLogs`` folder), named by the local time the session began, e.g.
``2026_10_17 10_05_33 Sat.dslog`` and ``.dsevents``. Read here as AdvantageScope reads them (Littleton
Robotics, BSD license: github.com/Mechanical-Advantage/AdvantageScope, src/hub/dataSources/dslog),
version 4, big-endian:

* Both start with a 20-byte header: the version (int32), then a LabVIEW time (int64 seconds since
  1904 and a uint64 fraction).
* A ``.dslog`` record every 20 ms: trip time (uint8 x 0.5 ms), packet loss (int8 x 4 %), battery
  (uint16 / 256 V), roboRIO CPU (uint8 x 0.5 %), a status byte whose bits are set when *off* (7
  brownout, 6 watchdog, 5 DS teleop, 3 DS disabled, 2 robot teleop, 1 robot auto, 0 robot disabled),
  CAN use (uint8 x 0.5 %), Wi-Fi dB (uint8 x 0.5), Wi-Fi Mb (uint16 / 256); then a 4-byte
  power-distribution header whose last byte is the length of what follows (33 for a REV PDH, 25 for
  a CTRE PDP, else nothing).
* A ``.dsevents`` entry: a LabVIEW time, an int32 length, then that much text, tagged
  (``<message>``, ``<details>``, ``<Code>`` ...). Among them the Driver Station's own "Ping Results",
  which say which link (DS radio .4, robot radio .1, roboRIO .2) answered.

A dropped link is a run of records where the robot reports no mode at all (not disabled, teleop
or auto) between the first and last time it was heard: that is read from the records, not stated
by the format's sources, so a real dropped session is the check on it.
"""

from __future__ import annotations

import glob
import os
import re
import struct
from collections import Counter

LOG_DIRS = [os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "FRC", "Log Files"),
            os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "FRC", "Log Files", "DSLogs")]
LV_EPOCH = -2082844800          # 1904-01-01 00:00 UTC, in unix seconds
PERIOD = 0.02
GROUP = "Driver Station log"
MIN_DROP = 3                    # records (60 ms): shorter gaps are a lost packet or two, not a drop


def _lv_time(data, at):
    secs, frac = struct.unpack_from(">qQ", data, at)
    return LV_EPOCH + secs + frac / 2 ** 64


def read_dslog(data):
    """``{"version", "start", "trip_ms", "loss", "volts", "cpu", "can", "wifi_db", "wifi_mb",
    "brownout", "watchdog", "connected", "enabled"}``: one list each, a value per 20 ms."""
    version = struct.unpack_from(">i", data, 0)[0]
    if version != 4:
        raise ValueError(f"Driver Station log version {version}; this reads version 4")
    out = {k: [] for k in ("trip_ms", "loss", "volts", "cpu", "can", "wifi_db", "wifi_mb", "brownout", "watchdog",
                           "connected", "enabled")}
    out.update(version=version, start=_lv_time(data, 4))
    pos, last_v = 20, 0.0
    while pos + 14 <= len(data):
        trip, loss, volts, cpu, mask, can, db, mb = struct.unpack_from(">BbHBBBBH", data, pos)
        v = volts / 256
        if v > 20:              # a spike at the very end of some logs
            v = last_v
        last_v = v
        off = lambda bit: not (mask >> bit) & 1  # noqa: E731 - a bit set means the flag is off
        teleop, auto, disabled = off(2), off(1), off(0)
        out["trip_ms"].append(trip * 0.5)
        out["loss"].append(min(max(loss * 4 * 0.01, 0.0), 1.0))
        out["volts"].append(v)
        out["cpu"].append(cpu * 0.5 * 0.01)
        out["can"].append(can * 0.5 * 0.01)
        out["wifi_db"].append(db * 0.5)
        out["wifi_mb"].append(mb / 256)
        out["brownout"].append(off(7))
        out["watchdog"].append(off(6))
        out["connected"].append(teleop or auto or disabled)
        out["enabled"].append((teleop or auto) and not disabled)
        n = data[pos + 13]
        pos += 14 + (n if n in (25, 33) else 0)
    return out


_TAGS = re.compile(r"<(TagVersion|time|count|flags|Code|location|stack)>[^<]*")


def read_dsevents(data):
    """``[(seconds into the session, text)]``, the tags the Driver Station wraps them in removed."""
    version = struct.unpack_from(">i", data, 0)[0]
    if version != 4:
        raise ValueError(f"Driver Station events version {version}; this reads version 4")
    start = _lv_time(data, 4)
    pos, out = 20, []
    while pos + 20 <= len(data):
        t = _lv_time(data, pos)
        (length,) = struct.unpack_from(">i", data, pos + 16)
        pos += 20
        text = data[pos:pos + length].decode("utf-8", errors="replace")
        pos += length
        text = _TAGS.sub("", text).replace("<message> ", "").replace("<details> ", "").strip()
        out.append((t - start, text))
    return out


def find_logs(dirs=None):
    """This laptop's Driver Station sessions, newest first: ``[(dslog path, dsevents path or None)]``."""
    found = []
    for d in dirs or LOG_DIRS:
        found += glob.glob(os.path.join(d, "*.dslog"))
    found = sorted(set(found), key=os.path.basename, reverse=True)
    return [(f, f[:-6] + ".dsevents" if os.path.exists(f[:-6] + ".dsevents") else None) for f in found]


def _pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def _runs(flags, min_len=1):
    """``[(start, length)]`` of each run of True."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_len:
                out.append((start, i - start))
            start = None
    return out


_PING = re.compile(r"([A-Za-z][\w ]*?)(?:\((\.\d+)\))?-(GOOD|bad)", re.I)


def summary(log, events=(), name=""):
    """What one session's link did: drops, trip time, packet loss, brownouts, CPU, and which links
    the Driver Station's own ping found bad."""
    conn = log["connected"]
    heard = [i for i, c in enumerate(conn) if c]
    first, last = (heard[0], heard[-1]) if heard else (0, -1)
    drops = []
    for s, n in _runs([not c for c in conn[first:last + 1]], MIN_DROP):
        i = first + s
        drops.append({"at_s": round(i * PERIOD, 2), "length_s": round(n * PERIOD, 2),
                      "while_enabled": bool(i > 0 and log["enabled"][i - 1])})
    on = [i for i in range(first, last + 1) if conn[i]]
    trip = [log["trip_ms"][i] for i in on]
    loss = [log["loss"][i] for i in on]
    volts = [log["volts"][i] for i in on if log["volts"][i] > 0]
    brown = _runs(log["brownout"], 1)
    bad = Counter()
    for _, text in events:
        if "ping results" in text.lower():
            for part, addr, state in _PING.findall(text.split(":", 1)[-1]):
                if state.lower() == "bad":
                    bad[(part.strip() + (f" ({addr})" if addr else "")).strip()] += 1
    msgs = Counter(re.sub(r"\d+(\.\d+)?", "#", t)[:160] for _, t in events if t and "ping results" not in t.lower())
    return {"name": name, "duration_s": round(len(conn) * PERIOD, 1), "heard_s": round(len(on) * PERIOD, 1),
            "enabled_s": round(sum(log["enabled"]) * PERIOD, 1), "drops": drops,
            "trip_ms": {"median": _pct(trip, 0.5), "p95": _pct(trip, 0.95), "max": max(trip) if trip else None},
            "loss_pct": {"mean": round(100 * sum(loss) / len(loss), 1) if loss else None,
                         "p95": round(100 * _pct(loss, 0.95), 1) if loss else None},
            "brownouts": len(brown), "min_volts": round(min(volts), 2) if volts else None,
            "cpu_p95_pct": round(100 * _pct([log["cpu"][i] for i in on], 0.95), 1) if on else None,
            "ping_bad": dict(bad.most_common()), "messages": msgs.most_common(8)}


def latest_summary(dirs=None):
    """The newest session's summary on this laptop, or None (no Driver Station logs here)."""
    for dslog, dsevents in find_logs(dirs):
        try:
            with open(dslog, "rb") as fh:
                log = read_dslog(fh.read())
            events = []
            if dsevents:
                with open(dsevents, "rb") as fh:
                    events = read_dsevents(fh.read())
        except (OSError, ValueError, struct.error):
            continue
        if not any(log["connected"]):
            continue    # a session that never reached a robot says nothing about the link
        return summary(log, events, os.path.basename(dslog)[:-6])
    return None


def _check(cid, level, title, why):
    return {"id": cid, "group": GROUP, "level": level, "title": title, "why": why}


def checks(s):
    """Checks from one session's summary, the network check's shape."""
    if not s:
        return []
    out = []
    where = f"In the session {s['name']}" if s.get("name") else "In the last session"
    drops = s.get("drops") or []
    if drops:
        mid = [d for d in drops if d["while_enabled"]]
        longest = max(d["length_s"] for d in drops)
        out.append(_check("dslog-drops", "fail" if mid else "warn",
                          f"The link to the robot dropped {len(drops)} time{'s' if len(drops) != 1 else ''} (longest {longest:g} s)"
                          + (f", {len(mid)} while enabled" if mid else ""),
                          f"{where}, the robot went quiet "
                          + ", ".join(f"at {d['at_s']:g} s" for d in drops[:5]) + ("..." if len(drops) > 5 else "")
                          + ". With no brownout at the same time, look for a loose radio power or Ethernet connection, "
                          "or the radio rebooting."))
    else:
        out.append(_check("dslog-drops", "ok", "No dropped link in the Driver Station's log",
                          f"{where}: {s['heard_s']:g} s with the robot, none of it lost."))
    if s.get("brownouts"):
        out.append(_check("dslog-brownout", "fail", f"Browned out {s['brownouts']} time{'s' if s['brownouts'] != 1 else ''}"
                          + (f" (lowest {s['min_volts']:g} V)" if s.get("min_volts") else ""),
                          "The battery sagged far enough that the roboRIO cut the motors: a tired battery, a loose "
                          "battery lead, or too much current at once."))
    elif s.get("min_volts") is not None:
        out.append(_check("dslog-brownout", "ok", f"No brownout (lowest {s['min_volts']:g} V)", "The battery held up."))
    trip, loss = s.get("trip_ms") or {}, s.get("loss_pct") or {}
    if trip.get("median") is not None:
        slow = trip["median"] > 20 or (trip.get("p95") or 0) > 50
        out.append(_check("dslog-trip", "warn" if slow else "ok",
                          f"Trip time {trip['median']:g} ms typically, {trip.get('p95'):g} ms at worst (95%)",
                          "Long trip times mean a slow or busy link: 2.4 GHz Wi-Fi in a busy building, or a weak "
                          "signal. Use a cable to the access point radio." if slow else "A quick link."))
    if loss.get("mean") is not None:
        lossy = loss["mean"] > 5 or (loss.get("p95") or 0) > 20
        out.append(_check("dslog-loss", "warn" if lossy else "ok",
                          f"Packet loss {loss['mean']:g}% on average, {loss.get('p95'):g}% at worst (95%)",
                          "Lost packets make the robot stutter and can drop the link: a busy or weak wireless link. "
                          "Use a cable to the access point radio." if lossy else "Few packets lost."))
    if (s.get("cpu_p95_pct") or 0) > 95:
        out.append(_check("dslog-cpu", "warn", f"The roboRIO's CPU ran at {s['cpu_p95_pct']:g}%",
                          "Robot code using all of the CPU misses its loops; the Driver Station can then report "
                          "lost communication even with a good link. Look for loops doing too much work."))
    bad = s.get("ping_bad") or {}
    if bad:
        parts = ", ".join(f"{k} {v}x" for k, v in list(bad.items())[:4])
        out.append(_check("dslog-ping", "info", f"The Driver Station's own pings found bad links: {parts}",
                          "Which link failed: the DS radio (.4) is the access point side, the robot radio (.1) the "
                          "robot's radio, the roboRIO (.2) the robot itself. FMS and field radio lines are bad off the field."))
    return out
