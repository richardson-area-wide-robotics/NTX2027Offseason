"""A stand-in for a camera's PhotonVision, for the tests and for trying the camera pages without a
camera: the same websocket messages and HTTP calls as PhotonVision v2026.3.4, on a port of its own.

It sends its settings on connect; counts a calibration snapshot only while ``board_visible``;
solves a calibration from 12 snapshots or more; keeps each pipeline setting it is sent; and sends a
frame result ten times a second, seeing the tags better or worse with the exposure and gain the way
a real camera under a venue's lights would (too dark: none; too much exposure: blurred, fewer).
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import socket
import struct
import threading
import time

from .photon import mp_pack, mp_unpack


class FakePhoton:
    def __init__(self, port=0, version="v2026.3.4", light=1.0):
        self.version, self.light = version, light
        self.board_visible = True
        self.moving = False                 # the robot spinning: motion blur grows with exposure
        self.count = 0
        self.calibrating = False
        self.settings = {"cameraExposureRaw": 20.0, "cameraGain": 75, "cameraBrightness": 50, "cameraAutoExposure": False,
                         "cameraVideoModeIndex": 1}
        self.calibrations = []
        self.sent = []                      # every message it was sent, decoded
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", port))
        self.srv.listen(8)
        self.port = self.srv.getsockname()[1]
        self.clients = []
        self._stop = False
        threading.Thread(target=self._accept, daemon=True).start()
        threading.Thread(target=self._frames, daemon=True).start()

    def close(self):
        self._stop = True
        try:
            self.srv.close()
        except OSError:
            pass

    # ------------------------------------------------------------------ what it says it is
    def camera(self):
        return {"uniqueName": "luma-p1-cam0", "nickname": "front", "inputStreamPort": 1181, "outputStreamPort": 1182,
                "currentPipelineIndex": 0, "currentPipelineSettings": dict(self.settings),
                "videoFormatList": {"0": {"width": 640, "height": 400, "fps": 120}, "1": {"width": 1280, "height": 800, "fps": 60}},
                "calibrations": self.calibrations, "isConnected": True, "isCSICamera": True,
                "minExposureRaw": 7.0, "maxExposureRaw": 80000.0}

    def settings_msg(self):
        return {"settings": {"general": {"version": self.version, "hardwareModel": "Luma P1", "imageVersion": "v2026.1.3",
                                         "wpilibArch": "linuxarm64", "mrCalWorking": True}},
                "cameraSettings": [self.camera()]}

    # ------------------------------------------------------------------ connections
    def _accept(self):
        while not self._stop:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, c):
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = c.recv(4096)
            if not chunk:
                c.close()
                return
            buf += chunk
        head, body = buf.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        method, path = lines[0].split(" ")[:2]
        hdr = {ln.split(":", 1)[0].lower(): ln.split(":", 1)[1].strip() for ln in lines[1:] if ":" in ln}
        if hdr.get("upgrade", "").lower() == "websocket":
            acc = base64.b64encode(hashlib.sha1((hdr["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            c.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {acc}\r\n\r\n".encode())
            self.clients.append(c)
            self._send(c, self.settings_msg())
            self._ws_loop(c)
            return
        n = int(hdr.get("content-length") or 0)
        while len(body) < n:
            body += c.recv(4096)
        code, text = self._http(method, path, json.loads(body or b"{}") if n else {})
        c.sendall(f"HTTP/1.1 {code} X\r\nContent-Type: text/plain\r\nContent-Length: {len(text.encode())}\r\nConnection: close\r\n\r\n{text}".encode())
        c.close()

    def _http(self, method, path, body):
        if method == "POST" and path == "/api/calibration/end":
            ok = self.count >= 12
            if ok:
                self.calibrations = [{"resolution": {"width": 1280, "height": 800},
                                      "cameraIntrinsics": {"rows": 3, "cols": 3, "type": 6,
                                                           "data": [763.0, 0, 640.0, 0, 763.0, 400.0, 0, 0, 1]},
                                      "distCoeffs": {"rows": 1, "cols": 8, "type": 6, "data": [0.0] * 8},
                                      "numSnapshots": self.count, "meanErrors": [0.31] * self.count}]
            self.count, self.calibrating = 0, False
            self.broadcast({"calibrationData": {"count": 0, "minCount": 12, "hasEnough": False}})
            self.broadcast(self.settings_msg())
            return (200, "Camera calibration successfully completed!") if ok else (500, "The calibration process failed")
        return 404, "Not found"

    def _ws_loop(self, c):
        try:
            while not self._stop:
                b0, b1 = self._read(c, 2)
                n = b1 & 0x7f
                if n == 126:
                    n = struct.unpack(">H", self._read(c, 2))[0]
                elif n == 127:
                    n = struct.unpack(">Q", self._read(c, 8))[0]
                mask = self._read(c, 4)
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(self._read(c, n)))
                if b0 & 0x0f == 0x8:
                    break
                if b0 & 0x0f == 0x2:
                    self._message(mp_unpack(data))
        except (OSError, ConnectionError, ValueError):
            pass
        finally:
            if c in self.clients:
                self.clients.remove(c)
            c.close()

    @staticmethod
    def _read(c, n):
        out = b""
        while len(out) < n:
            chunk = c.recv(n - len(out))
            if not chunk:
                raise ConnectionError("closed")
            out += chunk
        return out

    def _send(self, c, msg):
        payload = mp_pack(msg)
        n = len(payload)
        head = struct.pack("B", 0x82) + (struct.pack("B", n) if n < 126 else struct.pack(">BH", 126, n) if n < 65536 else struct.pack(">BQ", 127, n))
        c.sendall(head + payload)

    def broadcast(self, msg):
        for c in list(self.clients):
            try:
                self._send(c, msg)
            except OSError:
                pass

    # ------------------------------------------------------------------ what it does
    def _message(self, msg):
        self.sent.append(msg)
        if "startPnpCalibration" in msg:
            self.calibrating, self.count = True, 0
            self.broadcast({"calibrationData": {"count": 0, "minCount": 12, "hasEnough": False}})
        if msg.get("takeCalibrationSnapshot") and self.calibrating and self.board_visible:
            self.count += 1
            self.broadcast({"calibrationData": {"count": self.count, "minCount": 12, "hasEnough": self.count >= 12}})
        ch = msg.get("changePipelineSetting")
        if isinstance(ch, dict):
            self.settings.update({k: v for k, v in ch.items() if k != "cameraUniqueName"})

    def quality(self):
        """How often a frame sees the tags, from the light, exposure (µs) and gain (0 to 100)."""
        exp = float(self.settings.get("cameraExposureRaw") or 0)
        gain = float(self.settings.get("cameraGain") or 0)
        signal = self.light * exp / 1000.0 * (1 + gain / 25.0)
        seen = max(0.0, min(1.0, (signal - 0.6) / 1.4))
        if self.moving:
            seen *= max(0.0, 1.0 - max(0.0, exp - 1500) / 4000)       # blur past 1.5 ms of exposure
        noise = max(0.0, (gain - 70) / 100)                            # grainy at high gain
        return seen, noise

    def _frames(self):
        rnd = random.Random(7)
        seq = 0
        while not self._stop:
            time.sleep(0.1)
            if not self.clients or self.calibrating:
                continue
            seq += 1
            seen, noise = self.quality()
            targets = []
            if rnd.random() < seen:
                for tid in (7, 8):
                    targets.append({"fiducialId": tid, "ambiguity": round(0.05 + noise * 0.4 + rnd.random() * 0.03, 3),
                                    "yaw": 3.0, "pitch": 1.0, "area": 0.4})
            frame = {"sequenceID": seq, "fps": 60.0, "latency": 12.0, "targets": targets}
            if len(targets) > 1:
                frame["multitagResult"] = {"bestReprojectionError": 0.3 + noise, "fiducialIDsUsed": [7, 8]}
            self.broadcast({"updatePipelineResult": {"luma-p1-cam0": frame}})
