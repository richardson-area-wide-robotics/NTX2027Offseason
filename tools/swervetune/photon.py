"""Talking to a camera's PhotonVision (a Luma P1) straight from the laptop, as its own web page does.

PhotonVision's page talks to it over a websocket (``ws://<camera>:5800/websocket_data``) in
MessagePack, plus a little HTTP. Through the same messages this module can:

* read what the camera is (PhotonVision's version, the hardware, each camera's settings and its
  lens calibrations);
* run a lens calibration: start it with the ChArUco board's sizes, take snapshots, finish it
  (PhotonVision does the solving, as its page does);
* change a pipeline's camera settings (exposure, gain, brightness);
* listen to each frame's result (how many tags it sees, how sure it is), to tune those settings.

The robot code can't do any of this: PhotonLib only switches pipelines and driver mode.

Message names and shapes are PhotonVision v2026.3.4's (DataSocketHandler, UIDataPublisher,
Calibrate3dPipeline, RequestHandler). Only the standard library: the websocket and MessagePack
here are the small parts of each that PhotonVision uses.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import queue
import socket
import struct
import threading
import time
import urllib.error
import urllib.request

PORT = 5800
WS_PATH = "/websocket_data"
# The team's ChArUco board (docs/VISION_LUMA_PHOTONVISION.md): 8 x 8 squares of 1 in, 0.75 in
# markers, 4x4 ArUco markers, the current OpenCV pattern.
BOARD = {"squareSizeIn": 1.0, "markerSizeIn": 0.75, "patternWidth": 8, "patternHeight": 8,
         "boardType": 1, "tagFamily": 0, "useOldPattern": False}


# ---------------------------------------------------------------------------- MessagePack


def mp_pack(v) -> bytes:
    if v is None:
        return b"\xc0"
    if v is True:
        return b"\xc3"
    if v is False:
        return b"\xc2"
    if isinstance(v, int):
        if 0 <= v < 128:
            return struct.pack("B", v)
        if -32 <= v < 0:
            return struct.pack("b", v)
        if -2 ** 31 <= v < 2 ** 31:
            return b"\xd2" + struct.pack(">i", v)
        return b"\xd3" + struct.pack(">q", v)
    if isinstance(v, float):
        return b"\xcb" + struct.pack(">d", v)
    if isinstance(v, str):
        b = v.encode("utf-8")
        n = len(b)
        if n < 32:
            return struct.pack("B", 0xa0 | n) + b
        if n < 256:
            return b"\xd9" + struct.pack("B", n) + b
        if n < 65536:
            return b"\xda" + struct.pack(">H", n) + b
        return b"\xdb" + struct.pack(">I", n) + b
    if isinstance(v, (bytes, bytearray)):
        n = len(v)
        return (b"\xc4" + struct.pack("B", n) if n < 256 else b"\xc6" + struct.pack(">I", n)) + bytes(v)
    if isinstance(v, (list, tuple)):
        n = len(v)
        head = struct.pack("B", 0x90 | n) if n < 16 else (b"\xdc" + struct.pack(">H", n) if n < 65536 else b"\xdd" + struct.pack(">I", n))
        return head + b"".join(mp_pack(x) for x in v)
    if isinstance(v, dict):
        n = len(v)
        head = struct.pack("B", 0x80 | n) if n < 16 else (b"\xde" + struct.pack(">H", n) if n < 65536 else b"\xdf" + struct.pack(">I", n))
        return head + b"".join(mp_pack(k) + mp_pack(x) for k, x in v.items())
    raise TypeError(f"Can't pack {type(v).__name__}")


def mp_unpack(data: bytes):
    v, end = _mp(data, 0)
    return v


def _mp(d, i):
    b = d[i]
    i += 1
    if b < 0x80:
        return b, i
    if b >= 0xe0:
        return b - 0x100, i
    if 0x80 <= b <= 0x8f:
        return _mp_map(d, i, b & 0x0f)
    if 0x90 <= b <= 0x9f:
        return _mp_arr(d, i, b & 0x0f)
    if 0xa0 <= b <= 0xbf:
        n = b & 0x1f
        return d[i:i + n].decode("utf-8", "replace"), i + n
    if b == 0xc0:
        return None, i
    if b == 0xc2:
        return False, i
    if b == 0xc3:
        return True, i
    fixed = {0xcc: ">B", 0xcd: ">H", 0xce: ">I", 0xcf: ">Q", 0xd0: ">b", 0xd1: ">h", 0xd2: ">i", 0xd3: ">q",
             0xca: ">f", 0xcb: ">d"}
    if b in fixed:
        fmt = fixed[b]
        n = struct.calcsize(fmt)
        return struct.unpack(fmt, d[i:i + n])[0], i + n
    if b in (0xc4, 0xc5, 0xc6, 0xd9, 0xda, 0xdb):
        fmt = {0xc4: ">B", 0xc5: ">H", 0xc6: ">I", 0xd9: ">B", 0xda: ">H", 0xdb: ">I"}[b]
        k = struct.calcsize(fmt)
        n = struct.unpack(fmt, d[i:i + k])[0]
        i += k
        raw = d[i:i + n]
        return (raw.decode("utf-8", "replace") if b >= 0xd9 else bytes(raw)), i + n
    if b in (0xdc, 0xdd):
        k = 2 if b == 0xdc else 4
        return _mp_arr(d, i + k, struct.unpack(">H" if k == 2 else ">I", d[i:i + k])[0])
    if b in (0xde, 0xdf):
        k = 2 if b == 0xde else 4
        return _mp_map(d, i + k, struct.unpack(">H" if k == 2 else ">I", d[i:i + k])[0])
    if b in (0xd4, 0xd5, 0xd6, 0xd7, 0xd8):        # fixext: skipped as raw bytes
        n = {0xd4: 1, 0xd5: 2, 0xd6: 4, 0xd7: 8, 0xd8: 16}[b]
        return bytes(d[i + 1:i + 1 + n]), i + 1 + n
    if b in (0xc7, 0xc8, 0xc9):                     # ext
        k = {0xc7: 1, 0xc8: 2, 0xc9: 4}[b]
        n = int.from_bytes(d[i:i + k], "big")
        return bytes(d[i + k + 1:i + k + 1 + n]), i + k + 1 + n
    raise ValueError(f"Unknown MessagePack byte 0x{b:02x}")


def _mp_arr(d, i, n):
    out = []
    for _ in range(n):
        v, i = _mp(d, i)
        out.append(v)
    return out, i


def _mp_map(d, i, n):
    out = {}
    for _ in range(n):
        k, i = _mp(d, i)
        v, i = _mp(d, i)
        out[k if not isinstance(k, (list, dict)) else str(k)] = v
    return out, i


# ---------------------------------------------------------------------------- websocket


class WebSocket:
    """A client websocket: binary messages each way, pings answered, nothing else."""

    def __init__(self, host, port, path, timeout=5.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("The camera closed the connection during the handshake.")
            head += chunk
        head, self._buf = head.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ":
            raise ConnectionError(f"The camera refused the websocket: {lines[0]}")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        if not any(ln.lower().startswith("sec-websocket-accept:") and ln.split(":", 1)[1].strip() == accept for ln in lines):
            raise ConnectionError("The camera's websocket handshake didn't check out.")
        self.sock.settimeout(None)
        self._send_lock = threading.Lock()
        self.closed = False

    def send(self, payload: bytes, opcode=0x2):
        n = len(payload)
        head = struct.pack("B", 0x80 | opcode)
        if n < 126:
            head += struct.pack("B", 0x80 | n)
        elif n < 65536:
            head += struct.pack(">BH", 0x80 | 126, n)
        else:
            head += struct.pack(">BQ", 0x80 | 127, n)
        mask = os.urandom(4)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self._send_lock:
            self.sock.sendall(head + mask + body)

    def _read(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("The camera closed the connection.")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv(self):
        """The next whole message's payload (bytes), or None when the camera closed it."""
        parts = []
        while True:
            b0, b1 = self._read(2)
            fin, op = b0 & 0x80, b0 & 0x0f
            n = b1 & 0x7f
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b1 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 0x8:
                self.closed = True
                return None
            if op == 0x9:
                self.send(data, 0xA)
                continue
            if op == 0xA:
                continue
            parts.append(data)
            if fin:
                return b"".join(parts)

    def close(self):
        self.closed = True
        try:
            self.send(b"", 0x8)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------- the camera


class Photon:
    """One camera computer's PhotonVision. ``connect`` first; ``close`` when done."""

    def __init__(self, host, port=PORT, timeout=5.0):
        self.host, self.port, self.timeout = host, port, timeout
        self.ws = None
        self.settings = None          # the "settings" part of the message sent on connect
        self.cameras = []             # its "cameraSettings": one per camera
        self.calibration = {}         # the last "calibrationData" (snapshot count)
        self.results = {}             # uniqueName -> deque-like list of recent frame results
        self._listeners = []
        self._got_settings = threading.Event()
        self._cal_seq = 0
        self._cal_event = threading.Condition()
        self.error = ""

    # ------------------------------------------------------------------ connection
    def connect(self):
        self.ws = WebSocket(self.host, self.port, WS_PATH, timeout=self.timeout)
        threading.Thread(target=self._reader, name="photon-ws", daemon=True).start()
        if not self._got_settings.wait(self.timeout):
            self.close()
            raise ConnectionError("Connected, but the camera sent no settings.")
        return self

    def close(self):
        if self.ws:
            self.ws.close()

    @property
    def alive(self):
        return bool(self.ws and not self.ws.closed)

    def _reader(self):
        try:
            while True:
                raw = self.ws.recv()
                if raw is None:
                    break
                try:
                    msg = mp_unpack(raw) if raw[:1] != b"{" else json.loads(raw)
                except (ValueError, IndexError, struct.error):
                    continue
                if isinstance(msg, dict):
                    self._handle(msg)
        except (OSError, ConnectionError) as e:
            self.error = str(e)
        finally:
            if self.ws:
                self.ws.closed = True

    def _handle(self, msg):
        if "settings" in msg or "cameraSettings" in msg:
            if isinstance(msg.get("settings"), dict):
                self.settings = msg["settings"]
            if isinstance(msg.get("cameraSettings"), list):
                self.cameras = msg["cameraSettings"]
            self._got_settings.set()
        if isinstance(msg.get("calibrationData"), dict):
            with self._cal_event:
                self.calibration = msg["calibrationData"]
                self._cal_seq += 1
                self._cal_event.notify_all()
        res = msg.get("updatePipelineResult")
        if isinstance(res, dict):
            now = time.time()
            for name, r in res.items():
                if isinstance(r, dict):
                    lst = self.results.setdefault(name, [])
                    lst.append((now, r))
                    del lst[:-600]
        for fn in list(self._listeners):
            fn(msg)

    def send(self, msg: dict):
        self.ws.send(mp_pack(msg))

    def _http(self, path, body=None, timeout=10.0):
        req = urllib.request.Request(f"http://{self.host}:{self.port}{path}", method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    # ------------------------------------------------------------------ what it is
    def version(self):
        return ((self.settings or {}).get("general") or {}).get("version") or ""

    def hardware(self):
        g = (self.settings or {}).get("general") or {}
        return {"version": g.get("version") or "", "hardware": g.get("hardwareModel") or "",
                "image": g.get("imageVersion") or "", "arch": g.get("wpilibArch") or "",
                "mrcal": g.get("mrCalWorking")}

    def camera(self, name=None):
        """A camera by its unique name or nickname, or the only one."""
        cams = self.cameras or []
        if name:
            for c in cams:
                if name in (c.get("uniqueName"), c.get("nickname")):
                    return c
            return None
        return cams[0] if len(cams) == 1 else None

    @staticmethod
    def modes(cam):
        """Its video modes: [{index, width, height, fps}], biggest first."""
        out = []
        for k, v in (cam.get("videoFormatList") or {}).items():
            try:
                out.append({"index": int(k), "width": int(v.get("width")), "height": int(v.get("height")), "fps": v.get("fps")})
            except (TypeError, ValueError):
                continue
        return sorted(out, key=lambda m: -m["width"] * m["height"])

    # ------------------------------------------------------------------ calibration
    def start_calibration(self, unique, video_mode, square_in=1.0, marker_in=0.75, width=8, height=8):
        data = dict(BOARD, videoModeIndex=int(video_mode), squareSizeIn=float(square_in), markerSizeIn=float(marker_in),
                    patternWidth=int(width), patternHeight=int(height))
        self.send({"startPnpCalibration": data, "cameraUniqueName": unique})

    def snapshot(self, unique, wait=2.5):
        """Takes one calibration snapshot: the count afterwards, and whether this one counted (a
        snapshot without the board found is dropped)."""
        with self._cal_event:
            before, seq = int(self.calibration.get("count") or 0), self._cal_seq
        self.send({"takeCalibrationSnapshot": True, "cameraUniqueName": unique})
        end = time.time() + wait
        with self._cal_event:
            while self._cal_seq == seq and time.time() < end:
                self._cal_event.wait(max(0.0, end - time.time()))
            now = int(self.calibration.get("count") or 0)
        return {"count": now, "counted": now > before, "min": int(self.calibration.get("minCount") or 12),
                "enough": bool(self.calibration.get("hasEnough"))}

    def finish_calibration(self, unique, timeout=180.0):
        """Has PhotonVision solve it (it can take a minute): (ok, its message). It leaves calibration
        mode either way, which is also how a calibration is cancelled."""
        code, text = self._http("/api/calibration/end", {"cameraUniqueName": unique}, timeout=timeout)
        return code == 200, text.strip()

    # ------------------------------------------------------------------ settings and results
    def set_pipeline(self, unique, index):
        self.send({"currentPipeline": int(index), "cameraUniqueName": unique})

    def change_settings(self, unique, values: dict):
        """Changes the camera's current pipeline's settings: integers stay integers (PhotonVision casts
        them strictly)."""
        self.send({"changePipelineSetting": dict(values, cameraUniqueName=unique)})

    def collect(self, unique, seconds):
        """Every frame result for ``seconds`` from now."""
        start = time.time()
        time.sleep(seconds)
        return [r for t, r in self.results.get(unique, []) if t >= start]


# ---------------------------------------------------------------------------- what it means


def summarize_calibration(cal):
    """A calibration as PhotonVision reports it: its resolution, mean error (px), and the fields of
    view its lens model gives."""
    res = cal.get("resolution") or {}
    w, h = res.get("width"), res.get("height")
    data = (cal.get("cameraIntrinsics") or {}).get("data") or []
    errs = [e for e in (cal.get("meanErrors") or []) if isinstance(e, (int, float))]
    out = {"width": w, "height": h, "snapshots": cal.get("numSnapshots") or len(errs),
           "mean_error_px": round(sum(errs) / len(errs), 3) if errs else None}
    if len(data) >= 6 and w and h and data[0] and data[4]:
        fx, fy = data[0], data[4]
        out["hfov_deg"] = round(math.degrees(2 * math.atan(w / 2 / fx)), 1)
        out["vfov_deg"] = round(math.degrees(2 * math.atan(h / 2 / fy)), 1)
        out["fx"], out["fy"] = round(fx, 1), round(fy, 1)
    return out


def frame_stats(frames):
    """How well it saw tags over some frames: share of frames with a tag, tags per frame, mean
    single-tag ambiguity, share with a multi-tag solve, and the frame rate."""
    if not frames:
        return {"frames": 0, "seen": 0.0, "tags": 0.0, "ambiguity": None, "multitag": 0.0, "fps": None}
    seen = tags = multi = 0
    amb = []
    fps = []
    for r in frames:
        ts = [t for t in (r.get("targets") or []) if isinstance(t, dict) and (t.get("fiducialId", -1) or 0) >= 0]
        seen += bool(ts)
        tags += len(ts)
        amb += [t["ambiguity"] for t in ts if isinstance(t.get("ambiguity"), (int, float)) and t["ambiguity"] >= 0]
        multi += bool(r.get("multitagResult"))
        if isinstance(r.get("fps"), (int, float)):
            fps.append(r["fps"])
    n = len(frames)
    return {"frames": n, "seen": seen / n, "tags": tags / n, "ambiguity": sum(amb) / len(amb) if amb else None,
            "multitag": multi / n, "fps": sum(fps) / len(fps) if fps else None}
