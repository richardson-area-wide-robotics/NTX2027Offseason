"""Where each camera sits on the robot, measured with one AprilTag taped to a wall.

Every vision pose goes through one fixed transform: robot center to camera lens. A camera 2 cm off
moves every pose 2 cm; one tilted a degree more than the code thinks moves a pose 3.5 cm at 2 m,
and more the further the tag. Measuring the mount with a tape is hard (where exactly is the lens's
center? how much is it tilted?), so measure it with the camera itself:

1. Tape a tag **flat on a wall**, its center at a measured height.
2. Put the robot **square to the wall** (both bumper corners the same distance from it) at a
   measured distance, the camera's side facing it. Now where the tag is, relative to the robot, is
   known from the tape alone.
3. The camera reports where it sees the tag. The mount is the difference:
   ``robot->camera = robot->tag * (camera->tag)^-1``.
4. Repeat from three or more spots. The spread between them says how much to trust the answer.

Conventions are WPILib's: x forward, y left, z up, meters; ``Rotation3d(roll, pitch, yaw)`` is
extrinsic X, Y, Z (so ``R = Rz(yaw) Ry(pitch) Rx(roll)``) and pitch is negative when a camera looks
up; a tag's own x axis points out of its face, toward whoever is looking at it.
"""

from __future__ import annotations

import math
import statistics

SIDES = {"front": 0.0, "left": 90.0, "back": 180.0, "right": -90.0}
SPREAD_CM_WARN = 2.0
SPREAD_DEG_WARN = 1.0
AMBIGUITY_WARN = 0.2
MIN_SAMPLES = 5


# ---------------------------------------------------------------------------- rotations


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _vec(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def _t(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def euler_to_mat(roll, pitch, yaw):
    """Degrees, WPILib's extrinsic X-Y-Z: R = Rz(yaw) Ry(pitch) Rx(roll)."""
    r, p, y = (math.radians(a) for a in (roll, pitch, yaw))
    rx = [[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]]
    ry = [[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]]
    rz = [[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]]
    return _mul(rz, _mul(ry, rx))


def mat_to_euler(m):
    """Degrees (roll, pitch, yaw) for R = Rz Ry Rx."""
    pitch = -math.asin(max(-1.0, min(1.0, m[2][0])))
    roll = math.atan2(m[2][1], m[2][2])
    yaw = math.atan2(m[1][0], m[0][0])
    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def quat_to_mat(w, x, y, z):
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def mat_to_quat(m):
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        return (0.25 * s, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s)
    if m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        return ((m[2][1] - m[1][2]) / s, 0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s)
    if m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        return ((m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s)
    s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
    return ((m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s)


def angle_between(a, b):
    """Degrees of rotation taking ``a`` to ``b``."""
    m = _mul(_t(a), b)
    c = (m[0][0] + m[1][1] + m[2][2] - 1) / 2
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def average_rotation(mats):
    """The mean of rotations that are close together: sign-aligned quaternions, averaged."""
    qs = [mat_to_quat(m) for m in mats]
    ref = qs[0]
    acc = [0.0] * 4
    for q in qs:
        sign = 1.0 if sum(a * b for a, b in zip(q, ref)) >= 0 else -1.0
        for i in range(4):
            acc[i] += sign * q[i]
    return quat_to_mat(*acc)


# A transform is (R, t): a rotation matrix and a translation.
def compose(a, b):
    return _mul(a[0], b[0]), [x + y for x, y in zip(_vec(a[0], b[1]), a[1])]


def inverse(a):
    rt = _t(a[0])
    return rt, [-x for x in _vec(rt, a[1])]


# ---------------------------------------------------------------------------- the method


def tag_in_robot(side, distance_m, lateral_m, height_m):
    """Where the wall tag is in the robot's frame.

    ``side`` faces the wall; ``distance_m`` is wall to robot center; ``lateral_m`` is how far the
    tag is to the left (+) or right (-) of the robot's center line, looking from the robot at the
    wall; ``height_m`` is the tag's center above the floor. The tag's face looks back at the robot.
    """
    phi = SIDES[side]
    a = math.radians(phi)
    u = (math.cos(a), math.sin(a))          # toward the wall
    left = (-math.sin(a), math.cos(a))      # left, looking at the wall
    pos = [distance_m * u[0] + lateral_m * left[0], distance_m * u[1] + lateral_m * left[1], height_m]
    return euler_to_mat(0, 0, phi + 180), pos


def _median_sighting(samples):
    """One camera->tag transform from many: median translation, averaged rotation."""
    t = [statistics.median(s[k] for s in samples) for k in ("x", "y", "z")]
    r = average_rotation([quat_to_mat(s["qw"], s["qx"], s["qy"], s["qz"]) for s in samples])
    return r, t


def estimate(placement):
    """The camera mount from one placement: ``{"mount": (R, t), ...}`` or ``{"error": ...}``."""
    samples = [s for s in placement.get("samples") or [] if int(s.get("tag", -1)) == int(placement["tag_id"])]
    if len(samples) < MIN_SAMPLES:
        return {"error": f"Only {len(samples)} sightings of tag {placement['tag_id']} here; need {MIN_SAMPLES}."}
    rt = tag_in_robot(placement["side"], float(placement["distance_m"]), float(placement["lateral_m"]),
                      float(placement["height_m"]))
    ct = _median_sighting(samples)
    mount = compose(rt, inverse(ct))
    amb = [s.get("ambiguity", -1) for s in samples if s.get("ambiguity", -1) >= 0]
    return {"mount": mount, "count": len(samples), "range_m": math.sqrt(sum(x * x for x in ct[1])),
            "ambiguity": statistics.median(amb) if amb else None}


def as_numbers(mount):
    r, t = mount
    roll, pitch, yaw = mat_to_euler(r)
    return {"x": t[0], "y": t[1], "z": t[2], "roll": roll, "pitch": pitch, "yaw": yaw}


def solve(camera, placements, current=None):
    """The mount from every placement: ``{"result", "per_placement", "spread", "findings", "edit"}``."""
    F, per, mounts = [], [], []
    for i, p in enumerate(placements):
        e = estimate(p)
        if "error" in e:
            per.append({"index": i, "error": e["error"]})
            F.append({"level": "warn", "title": f"Spot {i + 1} is not used", "why": e["error"]})
            continue
        n = as_numbers(e["mount"])
        n.update(index=i, count=e["count"], range_m=e["range_m"], ambiguity=e["ambiguity"])
        per.append(n)
        mounts.append(e["mount"])
        if e["ambiguity"] is not None and e["ambiguity"] > AMBIGUITY_WARN:
            F.append({"level": "warn", "title": f"Spot {i + 1}: the camera wasn't sure which way the tag faced",
                      "why": f"Pose ambiguity {e['ambiguity']:.2f}. Move closer, or face the tag more "
                             "squarely; a tag seen nearly edge-on can flip."})
    if not mounts:
        return {"result": None, "per_placement": per, "findings": F or [{
            "level": "error", "title": "No usable spots yet", "why": "Take a sighting from at least two spots."}]}
    r = average_rotation([m[0] for m in mounts])
    t = [statistics.fmean(m[1][k] for m in mounts) for k in range(3)]
    result = as_numbers((r, t))
    spread_cm = max(math.dist(m[1], t) for m in mounts) * 100
    spread_deg = max(angle_between(m[0], r) for m in mounts)
    if len(mounts) < 3:
        F.append({"level": "info", "title": f"{len(mounts)} spot{'s' if len(mounts) > 1 else ''} so far",
                  "why": "Three or more, at different distances and to each side, show whether the tape "
                         "measurements agree with each other."})
    if len(mounts) > 1 and (spread_cm > SPREAD_CM_WARN or spread_deg > SPREAD_DEG_WARN):
        F.append({"level": "warn",
                  "title": f"The spots disagree by up to {spread_cm:.1f} cm and {spread_deg:.1f} degrees",
                  "why": "Check each spot's tape measurements, that the robot was square to the wall, that "
                         "the tag is flat, and that PhotonVision's tag size matches the printed tag "
                         "(FRC tags: 6.5 in = 0.1651 m across the black square)."})
    if not (0.0 < result["z"] < 1.5):
        F.append({"level": "error", "title": f"The camera comes out {result['z']:.2f} m above the floor",
                  "why": "Not possible on this robot. Check the tag height, and which side of the robot "
                         "faced the wall."})
    edit = None
    if current:
        d_cm = math.dist([current.get(k, 0.0) for k in ("x", "y", "z")], t) * 100
        cur = euler_to_mat(current.get("roll", 0.0), current.get("pitch", 0.0), current.get("yaw", 0.0))
        d_deg = angle_between(cur, r)
        F.append({"level": "warn" if d_cm > 1.0 or d_deg > 0.5 else "ok",
                  "title": f"{d_cm:.1f} cm and {d_deg:.1f} degrees from what slothtune.json says now",
                  "why": "Every vision pose moves by about this much once it's saved and redeployed."})
    if result["z"] > 0 and not any(f["level"] == "error" for f in F):
        edit = ("slothtune.json", ("cameras", camera),
                {k: round(result[k], 4 if k in "xyz" else 2) for k in ("x", "y", "z", "roll", "pitch", "yaw")})
    return {"camera": camera, "result": result, "per_placement": per,
            "spread": {"cm": spread_cm, "deg": spread_deg, "spots": len(mounts)}, "findings": F, "edit": edit}
