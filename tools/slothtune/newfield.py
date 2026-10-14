"""A new field, one button: the camera tuned to its lights, its tags swept, the camera mount checked.

At a new venue the lens is the same, but the light and the tags are not:

1. **Light** (:class:`Lighting`): the robot still, facing tags. The exposure comes from a motion
   blur budget: short enough that a fast turn smears a tag by only a few pixels, from the lens's
   own focal length (its calibration). Then it tries the gain from low to high, watching how often
   each frame sees the tags, keeps the lowest gain that sees them about as well as the best, and
   one step more for margin. PhotonVision's own advice: exposure as low as it can go, gain and
   brightness to make up the light. The settings it found stay on the camera; the old ones are
   kept, to put back.
2. **Tags** (:class:`Sweep`): the robot spins slowly in place, a full turn each way, while the field
   survey records every tag it sees. At two or three spots, the survey works out where the tags
   really hang (step 8 saves the layout).
3. **Mount** (:func:`mount_check`): spinning in place, the robot's center doesn't move, so the vision
   pose shouldn't either. A camera mount measured wrong swings the vision pose round in a circle
   as the robot turns, and its heading stays off by the same angle.
"""

from __future__ import annotations

import math
import threading
import time

from . import photon

GAINS = (0, 20, 40, 60, 80, 100)
BLUR_PX = 6.0          # how far a tag may smear in one exposure...
TURN_DPS = 360.0       # ...turning this fast
SWEEP = {"omega": 1.05, "duration_s": 6.0}   # rad/s for 6 s: a full turn each way, about 60 °/s


def exposure_us(fx, blur_px=BLUR_PX, turn_dps=TURN_DPS, lo=7.0, hi=80000.0):
    """The longest exposure (µs) that keeps a turn's smear within ``blur_px``: a point moves
    ``fx * omega`` pixels a second at the middle of the picture."""
    omega = math.radians(turn_dps)
    t = blur_px / (fx * omega) * 1e6
    return max(lo, min(hi, round(t)))


def choose_gain(trials, margin_step=1):
    """The lowest gain that sees the tags about as well as the best did (90% of its frames, and
    within half a tag a frame), then one step more. None when no gain saw them in half the frames."""
    best = max((t["seen"] for t in trials), default=0)
    if best < 0.5:
        return None
    best_tags = max(t["tags"] for t in trials if t["seen"] >= best - 1e-9)
    ok = [t for t in trials if t["seen"] >= 0.9 * best and t["tags"] >= best_tags - 0.5]
    if not ok:
        return None
    gains = [t["gain"] for t in trials]
    i = gains.index(min(t["gain"] for t in ok))
    return gains[min(len(gains) - 1, i + margin_step)]


class Lighting:
    """Tunes one camera's exposure and gain to the light it sees now. ``start`` runs it in a thread;
    ``state`` says what it's doing; ``restore`` puts the camera's old settings back."""

    def __init__(self, cam: photon.Photon, unique, fx, settle=0.6, hold=2.0, gains=GAINS):
        self.cam, self.unique, self.fx = cam, unique, fx
        self.settle, self.hold, self.gains = settle, hold, gains
        c = cam.camera(unique) or {}
        cur = c.get("currentPipelineSettings") or {}
        self.before = {k: cur[k] for k in ("cameraAutoExposure", "cameraExposureRaw", "cameraGain", "cameraBrightness") if k in cur}
        self.lo, self.hi = float(c.get("minExposureRaw") or 7), float(c.get("maxExposureRaw") or 80000)
        self.trials, self.result = [], None
        self.state, self.message = "ready", ""
        self._stop = False
        self.thread = None

    def start(self):
        self.state = "running"
        self.thread = threading.Thread(target=self._safe, name="slothtune-lighting", daemon=True)
        self.thread.start()

    def stop(self):
        self._stop = True

    def _safe(self):
        try:
            self.run()
        except Exception as e:  # noqa: BLE001 - the page must hear about it
            self.state, self.message = "stopped", f"Stopped on an error: {e}"

    def run(self):
        exp = exposure_us(self.fx, lo=self.lo, hi=self.hi)
        self.exposure = exp
        self.cam.change_settings(self.unique, {"cameraAutoExposure": False})
        self.cam.change_settings(self.unique, {"cameraExposureRaw": float(exp)})
        for g in self.gains:
            if self._stop:
                break
            self.message = f"Trying gain {g} (exposure {exp} µs): keep the robot still, facing the tags."
            self.cam.change_settings(self.unique, {"cameraGain": int(g)})
            time.sleep(self.settle)
            s = photon.frame_stats(self.cam.collect(self.unique, self.hold))
            self.trials.append(dict(s, gain=g))
        if self._stop:
            self.restore()
            self.state, self.message = "stopped", "Stopped: the camera is back on its old settings."
            return
        g = choose_gain(self.trials)
        if g is None:
            self.restore()
            self.state = "finished"
            self.result = None
            self.message = ("It didn't see tags in half the frames at any gain, so its old settings are back. Face the "
                            "robot toward two or more tags 7 to 13 ft away, with nothing in front of them, and try again.")
            return
        self.cam.change_settings(self.unique, {"cameraGain": int(g)})
        chosen = next(t for t in self.trials if t["gain"] == g)
        self.result = {"exposure_us": exp, "gain": g, "seen": chosen["seen"], "tags": chosen["tags"],
                       "ambiguity": chosen["ambiguity"]}
        self.state = "finished"
        self.message = (f"Set: exposure {exp} µs, gain {g}. It saw tags in {round(chosen['seen'] * 100)}% of frames, "
                        f"{chosen['tags']:.1f} a frame. These stay on the camera.")

    def restore(self):
        if self.before:
            if "cameraAutoExposure" in self.before:
                self.cam.change_settings(self.unique, {"cameraAutoExposure": bool(self.before["cameraAutoExposure"])})
            rest = {k: v for k, v in self.before.items() if k != "cameraAutoExposure"}
            if rest:
                self.cam.change_settings(self.unique, rest)

    def to_json(self):
        return {"state": self.state, "message": self.message, "trials": self.trials, "result": self.result,
                "before": self.before, "exposure_us": getattr(self, "exposure", None)}


def mount_check(samples, min_samples=20):
    """From (odometry pose, vision pose) pairs taken while the robot spun in place: how far the
    vision pose wandered (cm, as the radius round its middle) and how far its heading sat from the
    gyro's (degrees). A mount measured right keeps both small."""
    pts = [(v[0], v[1], o[2], v[2]) for o, v in samples if len(o) >= 3 and len(v) >= 3]
    if len(pts) < min_samples:
        return {"ok": None, "samples": len(pts),
                "why": "Too few vision poses while it spun: is the camera's mount in slothtune.json, and did it see tags?"}
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    r = math.sqrt(sum((p[0] - cx) ** 2 + (p[1] - cy) ** 2 for p in pts) / len(pts))
    d = [((p[3] - p[2] + 180) % 360) - 180 for p in pts]
    head = sum(d) / len(d)
    spread_cm, head_deg = round(r * 100, 1), round(head, 1)
    ok = spread_cm <= 3.0 and abs(head_deg) <= 1.5
    why = ("The vision pose stayed put as the robot turned: the mount is right." if ok else
           f"As the robot turned, the vision pose wandered about {spread_cm / 2.54:.1f} in and its heading sat {head_deg}° off "
           "the gyro's: the camera's mount is off. Measure it again (7. Camera positions).")
    return {"ok": ok, "samples": len(pts), "spread_cm": spread_cm, "heading_offset_deg": head_deg, "why": why}
