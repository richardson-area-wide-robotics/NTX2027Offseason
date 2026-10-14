"""What the robot keeps reporting: its errors and warnings, counted, not streamed.

Two sources:

* **The robot's console** (a real roboRIO only): the same stream VS Code's RioLog reads, TCP port
  1741. Each frame is a 2-byte big-endian length (counting the tag byte), a 1-byte tag, then the
  message. Tag 11 is an error or warning (``DriverStation.reportError`` and ``reportWarning``,
  vendor libraries, the HAL): timestamp (float), sequence (uint16), occurrence count (uint16),
  error code (int32), flags (bit 0 set for an error), then details, location and call stack, each
  a 2-byte length and UTF-8. Tag 12 is a printed line: timestamp, sequence, then the text. Printed
  lines count only when they read as an error or a warning. The format is WPILib's (vscode-wpilib's
  riolog and its test sender, resources/testing/riosender.py).
* **The robot's alerts** (any robot, the simulator too): WPILib Alerts published to NetworkTables,
  each group a table of ``errors`` and ``warnings``. An alert counts once each time it comes on.

The same message seen again adds to its count; the page shows each message once, with how often
and how recently, so a person sees what keeps coming back.
"""

from __future__ import annotations

import re
import socket
import struct
import threading
import time

CONSOLE_PORT = 1741
TAG_ERROR, TAG_PRINT = 11, 12
RECENT_S = 60.0          # seen within this: still happening
MAX_GROUPS = 300

_HEAD = struct.Struct("!HB")
_ERR = struct.Struct("!fHHiB")
_PRINT = struct.Struct("!fH")


def _string(buf, i):
    (n,) = struct.unpack_from("!H", buf, i)
    return buf[i + 2:i + 2 + n].decode("utf-8", "replace"), i + 2 + n


def parse_message(tag, body):
    """One frame's message: ``{"level", "text", "where", "occur"}``, or None for nothing to count."""
    try:
        if tag == TAG_ERROR:
            _, _, occur, code, flags = _ERR.unpack_from(body, 0)
            details, i = _string(body, _ERR.size)
            location, i = _string(body, i)
            return {"level": "error" if flags & 1 else "warning", "text": details.strip(),
                    "where": location.strip(), "occur": occur, "code": code}
        if tag == TAG_PRINT:
            line = body[_PRINT.size:].decode("utf-8", "replace").strip()
            level = classify_print(line)
            return {"level": level, "text": line, "where": "", "occur": 1, "code": 0} if level else None
    except (struct.error, UnicodeDecodeError):
        return None
    return None


def parse_frames(buf):
    """Every whole frame in ``buf``: ``([(tag, body), ...], what is left over)``."""
    out, i = [], 0
    while len(buf) - i >= 3:
        n, tag = _HEAD.unpack_from(buf, i)
        if n < 1:
            i += 2
            continue
        if len(buf) - (i + 2) < n:
            break
        out.append((tag, bytes(buf[i + 3:i + 2 + n])))
        i += 2 + n
    return out, bytes(buf[i:])


# "Exception" ends a Java class name (NullPointerException), so it needs no word start.
_ERRORISH = re.compile(r"\b(error|fatal|failed|failure)\b|exception\b", re.I)
_WARNISH = re.compile(r"\b(warning|warn)\b", re.I)


def classify_print(line):
    """A printed line as an error, a warning, or nothing to count. Java stack frames ("at ...")
    belong to the exception line above them and are not counted on their own."""
    s = line.strip()
    if not s or s.startswith("at ") or s.startswith("..."):
        return None
    if _ERRORISH.search(s):
        return "error"
    if _WARNISH.search(s):
        return "warning"
    return None


_DECIMAL = re.compile(r"-?\d+\.\d+")


def normalize(text):
    """The same message with different measurements is one message: "overrun by 0.0213 s" and
    "overrun by 0.0187 s" group together; a CAN ID or a port number (integers) keeps them apart."""
    return _DECIMAL.sub("#", " ".join(str(text).split()))[:400]


class Tally:
    """Every distinct message, counted."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self.groups = {}
        self.since = clock()
        self._alerts_on = set()
        self._lock = threading.Lock()

    def add(self, level, text, where="", source="console", now=None):
        if not text:
            return
        now = self.clock() if now is None else now
        key = (level, normalize(text), where)
        with self._lock:
            g = self.groups.get(key)
            if g is None:
                if len(self.groups) >= MAX_GROUPS:
                    # Make room: the one seen least, longest ago.
                    del self.groups[min(self.groups, key=lambda k: (self.groups[k]["count"], self.groups[k]["last"]))]
                g = self.groups[key] = {"level": level, "text": str(text).strip()[:600], "where": where,
                                        "source": source, "count": 0, "first": now, "last": now, "times": []}
            g["count"] += 1
            g["last"] = now
            g["times"] = (g["times"] + [now])[-50:]

    def alerts(self, active, now=None):
        """The robot's alerts showing now, ``[(level, text), ...]``: each counts once as it comes on."""
        now = self.clock() if now is None else now
        on = {(lvl, t) for lvl, t in active if t}
        for lvl, t in on - self._alerts_on:
            self.add(lvl, t, "", "alert", now)
        with self._lock:
            for key, g in self.groups.items():
                if g["source"] == "alert" and (g["level"], g["text"]) in on:
                    g["last"] = now   # still showing
        self._alerts_on = on

    def clear(self):
        with self._lock:
            self.groups.clear()
            self._alerts_on = set()
            self.since = self.clock()

    def summary(self, now=None):
        """Each message once: how often, first and last seen, and whether it is still happening.
        Errors first, then what keeps coming back."""
        now = self.clock() if now is None else now
        with self._lock:
            rows = []
            for g in self.groups.values():
                recent = sum(1 for t in g["times"] if now - t <= RECENT_S)
                ongoing = now - g["last"] <= RECENT_S
                rows.append({"level": g["level"], "text": g["text"], "where": g["where"], "source": g["source"],
                             "count": g["count"], "recent": recent, "first_ago_s": round(now - g["first"], 1),
                             "last_ago_s": round(now - g["last"], 1), "ongoing": ongoing,
                             "repeating": g["count"] >= 3})
        rows.sort(key=lambda r: (not r["ongoing"], r["level"] != "error", -r["count"], r["last_ago_s"]))
        return rows


class ConsoleWatch:
    """Reads the robot's console in the background and counts what it reports. Connects once, and
    after a drop waits before trying again: a robot rebooting is not to be knocked on."""

    RETRY_S = 5.0

    def __init__(self, host, tally, port=CONSOLE_PORT):
        self.host, self.port, self.tally = host, port, tally
        self.state = "connecting"
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="robotlog", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                with socket.create_connection((self.host, self.port), timeout=2.0) as s:
                    s.settimeout(1.0)
                    self.state = "connected"
                    buf = b""
                    while not self._stop.is_set():
                        try:
                            chunk = s.recv(65536)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        frames, buf = parse_frames(buf + chunk)
                        for tag, body in frames:
                            m = parse_message(tag, body)
                            if m:
                                self.tally.add(m["level"], m["text"], m["where"], "console")
            except OSError:
                pass
            self.state = "not connected"
            self._stop.wait(self.RETRY_S)
