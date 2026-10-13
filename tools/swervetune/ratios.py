"""Is the gear ratio in the config the one on the robot? Which one is it really?

A motor's encoder cannot see the gearbox behind it: every speed it reports is the motor's speed
divided by the *configured* ratio. So a wrong ratio is invisible to anything measured against that
same encoder - including a fitted kV, where the error cancels exactly. It shows up only against an
outside reference:

* **Steering:** the absolute encoder sits on the module itself. Motor-encoder degrees over absolute
  degrees equals real ratio over configured ratio. It must be 1.00.
* **Drive, one module unlike the others:** on the floor the chassis makes every wheel travel the
  same distance, so each module's reported travel is proportional to its real ratio. A module
  reporting 8% less than the others has 8% less reduction - one pinion tooth on a MAXSwerve.
* **Drive, every module the same and wrong:** only a ground reference finds it: a tape measure or
  AprilTags in the straight-line test. A scale near a ratio step (8%) is gearing; 1-3% is tread.

On blocks nothing couples the wheels, so blocks runs cannot detect a drive ratio at all.
"""

from __future__ import annotations

from . import revspecs

# The pinion and spur pairs REV sells (base kit, Gear Ratio Upgrade Kit), by REV's names. Every
# MAXSwerve drive ratio is 3:1 at the bevel times spur over pinion; other pairs don't mesh, since
# each gear is cut for one center distance.
MAXSWERVE_DRIVE = [(f"MAXSwerve {name}: {p} pinion, {s} spur", 3.0 * int(s[:-1]) / int(p[:-1]))
                   for name, _, p, s in revspecs.MAXSWERVE["drive_ratios"]]
SDS_DRIVE = [("SDS MK4/MK4i L1", 8.14), ("SDS MK4/MK4i L2", 6.75), ("SDS MK4/MK4i L3", 6.12),
             ("SDS MK4n L1+", 7.13), ("SDS MK4n L2+", 5.90), ("SDS MK4n L3+", 5.36)]
STEER = [("MAXSwerve", 9424 / 203), ("SDS MK4i", 150 / 7), ("SDS MK4", 12.8), ("SDS MK4n", 18.75)]


def family(steer_ratio):
    """Guess the module family from the steering ratio, which differs between them."""
    if steer_ratio and abs(steer_ratio - 46.42) < 0.2:
        return "maxswerve"
    if steer_ratio and any(abs(steer_ratio - r) < 0.2 for _, r in STEER[1:]):
        return "sds"
    return None


def candidates(real_ratio, fam=None, tolerance=0.02):
    """Known ratios within ``tolerance`` of an estimated real ratio, closest first."""
    pool = MAXSWERVE_DRIVE if fam == "maxswerve" else SDS_DRIVE if fam == "sds" else MAXSWERVE_DRIVE + SDS_DRIVE
    scored = sorted(pool, key=lambda nr: abs(nr[1] - real_ratio) / real_ratio)
    return [{"name": n, "ratio": round(r, 4), "off_pct": round(100 * (r - real_ratio) / real_ratio, 2)}
            for n, r in scored if abs(r - real_ratio) / real_ratio <= tolerance][:3]


def module_ratio_findings(travel, configured_ratio, fam=None, threshold=0.03):
    """Per-module travel (any consistent unit) to suspected ratio errors.

    ``travel``: {module name: distance reported over the same stretch of floor}. Returns one dict
    per module whose travel differs from the median by more than ``threshold``.
    """
    vals = sorted(v for v in travel.values() if v and v > 0)
    if len(vals) < 3:
        return []
    med = vals[len(vals) // 2] if len(vals) % 2 else 0.5 * (vals[len(vals) // 2 - 1] + vals[len(vals) // 2])
    out = []
    for name, v in travel.items():
        if not v or med <= 0:
            continue
        r = v / med
        if abs(r - 1) > threshold:
            real = configured_ratio * r
            out.append({"module": name, "travel_ratio": round(r, 4), "estimated_ratio": round(real, 3),
                        "configured_ratio": configured_ratio, "candidates": candidates(real, fam)})
    return out


def describe(f):
    """One sentence for a person."""
    c = f["candidates"]
    guess = f" That matches {c[0]['name']} ({c[0]['ratio']:.2f}:1)." if c else ""
    more = "less" if f["travel_ratio"] < 1 else "more"
    return (f"{f['module']} reports {abs(1 - f['travel_ratio']) * 100:.1f}% {more} travel than the other "
            f"modules over the same floor, so its real ratio looks like {f['estimated_ratio']:.2f}:1, "
            f"not the configured {f['configured_ratio']}:1.{guess}")
