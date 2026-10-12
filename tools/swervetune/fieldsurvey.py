"""Where a field's AprilTags really are, measured by the robot's camera.

Localization trusts the official tag layout to the millimeter, but tags on a real field are hung
by people: a few centimeters off, a degree turned, now and then one on the wrong bracket. A tag
2 cm off moves every pose solved from it by 2 cm.

**How:** drive slowly around the field (or carry the robot) with the camera seeing two or more tags
at once as often as possible. Any frame with two tags measures where they sit relative to each
other, whatever the robot's own position. Averaged over many frames, those pairs give each group of
connected tags its shape; the group is then fitted to the official layout as a whole, and what is
left over is how far each tag really is from where it should be.

What this can and cannot see: tags never seen together with others are not measured; and a group
of tags is placed on the field by its best fit, so a whole structure moved as one piece looks
right. Moving one tag relative to its neighbors, a rotated tag, or a tag on the wrong bracket all
show.

The result is a layout file the robot loads in place of the official one (see ``FieldLayouts`` on
the robot), tag by tag, and only for tags within 30 cm and 10 degrees of the official pose:
anything further is more likely a bad reading than a real field.
"""

from __future__ import annotations

import json
import math
import os
import statistics

from . import camcal as K

TRUST_M = 0.30
TRUST_DEG = 10.0
MAX_AMBIGUITY = 0.2
MAX_RANGE_M = 4.0            # single-tag error grows with range squared: survey close up
MIN_VIEWS = 5                # a tag seen in fewer views than this is not judged
SIGMA_FLOOR_CM = 0.7         # the scatter can't see errors shared by views (the solve's own bias)
SIGMA_FLOOR_DEG = 0.5
SIGNIFICANT = 3.0            # a change smaller than this many standard errors is noise
MIN_FIT_GAP_CM = 0.3         # layouts whose fits differ by less than this can't be told apart
MOVED_CM = 1.0
FIELDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fields")
VARIANTS = ("welded", "andymark")


# ---------------------------------------------------------------------------- layouts


def _pose_from_json(p):
    t = p["translation"]
    q = p["rotation"]["quaternion"]
    return K.quat_to_mat(q["W"], q["X"], q["Y"], q["Z"]), [t["x"], t["y"], t["z"]]


def official(variant="welded", year=2026):
    """``{"tags": {id: (R, t)}, "field": {...}, "variant": ...}`` from WPILib's layout file."""
    name = {2026: "rebuilt"}[year]
    with open(os.path.join(FIELDS, f"{year}-{name}-{variant}.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    return {"tags": {int(t["ID"]): _pose_from_json(t["pose"]) for t in d["tags"]}, "field": d["field"],
            "variant": variant, "year": year}


def layout_json(tags, field):
    """WPILib's AprilTagFieldLayout JSON for ``{id: (R, t)}``."""
    out = []
    for i in sorted(tags):
        r, t = tags[i]
        w, x, y, z = K.mat_to_quat(r)
        out.append({"ID": i, "pose": {"translation": {"x": round(t[0], 6), "y": round(t[1], 6), "z": round(t[2], 6)},
                                      "rotation": {"quaternion": {"W": round(w, 9), "X": round(x, 9),
                                                                  "Y": round(y, 9), "Z": round(z, 9)}}}})
    return json.dumps({"tags": out, "field": field}, indent=1) + "\n"


# ---------------------------------------------------------------------------- measurements

TAG_HALF_M = 0.1651 / 2      # FRC 36h11 tags: 6.5 in across the black square
OUTLIER_M = 0.015            # a tag this far from the group's fit is left out of the fit
OUTLIER_DEG = 1.0
AGREE_M = 0.01               # tags agree on a camera within this (plus more at range)
ROBUST_TAG_M = 0.02          # a view's estimate of a tag this far from the others counts for less


def _tag_in_camera(s):
    return K.quat_to_mat(s["qw"], s["qx"], s["qy"], s["qz"]), [s["x"], s["y"], s["z"]]


MERGE_M = 0.01               # consecutive frames whose tags all moved less than this are one view


def frames(sightings):
    """Camera views with two or more usable tags: ``[{id: ((R, t) camera->tag, range, weight)}]``.

    A slowly driven robot sends many nearly identical frames; consecutive ones from the same camera
    with the same tags, none moved more than MERGE_M, are averaged into one view that counts for
    all of them. That averages their noise, and keeps the solve quick.
    """
    by = {}
    order = []
    for s in sightings:
        if s.get("ambiguity", 0) > MAX_AMBIGUITY:
            continue
        rng = math.sqrt(s["x"] ** 2 + s["y"] ** 2 + s["z"] ** 2)
        if rng > MAX_RANGE_M:
            continue
        key = (s.get("camera", ""), s["t"])
        if key not in by:
            by[key] = {}
            order.append(key)
        by[key][int(s["tag"])] = (_tag_in_camera(s), rng)
    order.sort(key=lambda k: (k[0], k[1]))
    views, run = [], []

    def flush():
        if not run:
            return
        out = {}
        for i in run[0]:
            items = [f[i] for f in run]
            t = [sum(x[0][1][k] for x in items) / len(items) for k in range(3)]
            r = _weighted_rotation([(x[0][0], 1.0) for x in items])
            out[i] = ((r, t), sum(x[1] for x in items) / len(items), float(len(items)))
        views.append(out)

    last_cam = None
    for key in order:
        f = by[key]
        if len(f) < 2:
            continue
        same = (run and key[0] == last_cam and set(f) == set(run[0])
                and all(math.dist(f[i][0][1], run[0][i][0][1]) < MERGE_M for i in f))
        if not same:
            flush()
            run = []
        run.append(f)
        last_cam = key[0]
    flush()
    return views


def _corners(pose):
    """The tag's four corners: a tag's orientation error moves these only over its half-width."""
    r, t = pose
    out = []
    for dy, dz in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        v = K._vec(r, [0.0, dy * TAG_HALF_M, dz * TAG_HALF_M])
        out.append([v[k] + t[k] for k in range(3)])
    return out


def _jacobi_top(n):
    """The eigenvector of the largest eigenvalue of a symmetric 4x4 matrix (Jacobi rotations)."""
    a = [row[:] for row in n]
    v = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
    for _ in range(60):
        off = max(abs(a[i][j]) for i in range(4) for j in range(4) if i != j)
        if off < 1e-14:
            break
        for p in range(4):
            for q in range(p + 1, 4):
                if abs(a[p][q]) < 1e-18:
                    continue
                th = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = math.copysign(1.0, th) / (abs(th) + math.sqrt(th * th + 1))
                c = 1 / math.sqrt(t * t + 1)
                s_ = t * c
                for k in range(4):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p], a[k][q] = c * akp - s_ * akq, s_ * akp + c * akq
                for k in range(4):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k], a[q][k] = c * apk - s_ * aqk, s_ * apk + c * aqk
                for k in range(4):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p], v[k][q] = c * vkp - s_ * vkq, s_ * vkp + c * vkq
    top = max(range(4), key=lambda i: a[i][i])
    return [v[k][top] for k in range(4)]


def fit_rigid(ps, qs, ws):
    """The rotation and shift taking points ``ps`` onto ``qs`` (weighted least squares; Horn 1987)."""
    w = sum(ws)
    pc = [sum(p[k] * x for p, x in zip(ps, ws)) / w for k in range(3)]
    qc = [sum(q[k] * x for q, x in zip(qs, ws)) / w for k in range(3)]
    m = [[0.0] * 3 for _ in range(3)]
    for p, q, x in zip(ps, qs, ws):
        for i in range(3):
            for j in range(3):
                m[i][j] += x * (p[i] - pc[i]) * (q[j] - qc[j])
    (sxx, sxy, sxz), (syx, syy, syz), (szx, szy, szz) = m
    n = [[sxx + syy + szz, syz - szy, szx - sxz, sxy - syx],
         [syz - szy, sxx - syy - szz, sxy + syx, szx + sxz],
         [szx - sxz, sxy + syx, -sxx + syy - szz, syz + szy],
         [sxy - syx, szx + sxz, syz + szy, -sxx - syy + szz]]
    r = K.quat_to_mat(*_jacobi_top(n))
    rp = K._vec(r, pc)
    return r, [qc[k] - rp[k] for k in range(3)]


def _weighted_rotation(items):
    qs = [(K.mat_to_quat(r), w) for r, w in items]
    ref = qs[0][0]
    acc = [0.0] * 4
    for q, w in qs:
        sign = 1.0 if sum(a * b for a, b in zip(q, ref)) >= 0 else -1.0
        for k in range(4):
            acc[k] += sign * w * q[k]
    return K.quat_to_mat(*acc)


def _groups(frame_list, known):
    """Tags joined by being seen in the same frame, each group sorted."""
    parent = {}

    def find(n):
        parent.setdefault(n, n)
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for f in frame_list:
        ids = [i for i in f if i in known]
        for i in ids:
            find(i)
        for i in ids[1:]:
            parent[find(i)] = find(ids[0])
    out = {}
    for n in parent:
        out.setdefault(find(n), []).append(n)
    return sorted(sorted(g) for g in out.values())


def _align(poses, ids, target):
    """Moves a group as one rigid piece onto the official layout, fitted on the tags that agree with
    it: one moved tag must not drag the rest. Drops the worst-fitting tag, one at a time, until the
    rest agree (keeping at least half)."""
    if len(ids) < 2:
        return
    keep = list(ids)
    while True:
        ps = [c for i in keep for c in _corners(poses[i])]
        qs = [c for i in keep for c in _corners(target[i])]
        r, t = fit_rigid(ps, qs, [1.0] * len(ps))
        score = {}
        for i in keep:
            pr, pt = K.compose((r, t), poses[i])
            score[i] = max(math.dist(pt, target[i][1]) / OUTLIER_M,
                           K.angle_between(pr, target[i][0]) / OUTLIER_DEG)
        worst = max(keep, key=score.get)
        if score[worst] <= 1.0 or len(keep) <= max(2, (len(ids) + 1) // 2):
            break
        keep.remove(worst)
    for i in ids:
        poses[i] = K.compose((r, t), poses[i])


def _robust_mean(items):
    """A tag's position from many views' estimates, the odd ones out counting for little.

    In a view of just two tags, one of them wrong (a tag on the wrong bracket), there is no telling
    which: both estimates from that view are off. Across all the views of a tag, those few disagree
    with the rest, so they are down-weighted, starting from the median. Returns the position and the
    estimates with their final weights.
    """
    t = [statistics.median(x[0][1][k] for x in items) for k in range(3)]
    out = items
    for _ in range(4):
        out = [(x[0], x[1] / (1 + (math.dist(x[0][1], t) / ROBUST_TAG_M) ** 2)) for x in items]
        w = sum(x[1] for x in out)
        t = [sum(x[0][1][k] * x[1] for x in out) / w for k in range(3)]
    return t, out


def solve(frame_list, layout, iterations=60):
    """The surveyed shape: every seen tag's pose, groups set onto ``layout`` by their best fit.

    Alternates two steps from the official layout: each view's camera pose from its tags' corners
    (so a tag's noisy orientation acts only over its half-width), then each tag's pose from every
    camera that saw it, weighted by the inverse of its noise (which grows with range squared).
    """
    target = layout["tags"]
    groups = _groups(frame_list, target)
    nodes = [i for g in groups for i in g]
    poses = {i: target[i] for i in nodes}
    for _ in range(iterations):
        est = {}
        for f in frame_list:
            ids = [i for i in f if i in poses]
            if len(ids) < 2:
                continue
            ps = {i: _corners(f[i][0]) for i in ids}
            qs = {i: _corners(poses[i]) for i in ids}
            base = {i: f[i][2] / (f[i][1] ** 4) for i in ids}
            agree_m = {i: AGREE_M + AGREE_M * (f[i][1] / 2) ** 2 for i in ids}

            def misfit(cam, j):
                return sum(math.dist([a + b for a, b in zip(K._vec(cam[0], p), cam[1])], q)
                           for p, q in zip(ps[j], qs[j])) / 4

            # Consensus: each tag alone gives a camera pose; the one most tags agree with wins. A tag
            # that moved disagrees, so it doesn't tilt the camera - and gets its estimate from it.
            best = []
            for i in ids:
                cand = K.compose(poses[i], K.inverse(f[i][0]))
                inliers = [j for j in ids if misfit(cand, j) <= agree_m[j]]
                if len(inliers) > len(best):
                    best = inliers
            if len(best) < 2:
                continue   # no two tags agree: this view can't say which moved
            cam = fit_rigid([c for i in best for c in ps[i]], [c for i in best for c in qs[i]],
                            [base[i] for i in best for _ in range(4)])
            for i in ids:
                est.setdefault(i, []).append((K.compose(cam, f[i][0]), base[i]))
        change = 0.0
        for i, items in est.items():
            t, items = _robust_mean(items)
            est[i] = items
            change = max(change, math.dist(t, poses[i][1]))
            poses[i] = (_weighted_rotation([(x[0][0], x[1]) for x in items]), t)
        for g in groups:
            _align(poses, g, target)
        if change < 2e-5:
            break
    count, sigma = {}, {}
    for f in frame_list:
        for i in f:
            count[i] = count.get(i, 0) + int(f[i][2])
    for i, items in est.items():
        # Standard error of each tag's pose: the weighted scatter of the views' estimates over the
        # square root of how many views effectively counted.
        w = sum(x[1] for x in items)
        n_eff = w * w / sum(x[1] * x[1] for x in items)
        mean_t = [sum(x[0][1][k] * x[1] for x in items) / w for k in range(3)]
        mean_r = _weighted_rotation([(x[0][0], x[1]) for x in items])
        sd_t = math.sqrt(sum(x[1] * math.dist(x[0][1], mean_t) ** 2 for x in items) / w)
        sd_r = math.sqrt(sum(x[1] * K.angle_between(x[0][0], mean_r) ** 2 for x in items) / w)
        sigma[i] = (sd_t / math.sqrt(n_eff), sd_r / math.sqrt(n_eff), len(items))
    return {"poses": poses, "groups": groups, "counts": count, "sigma": sigma}


def compare(shape, layout):
    """The surveyed shape set onto one layout: each tag's distance from its official pose."""
    target = layout["tags"]
    poses = dict(shape["poses"])
    for g in shape["groups"]:
        _align(poses, g, target)
    rows = []
    for g_no, g in enumerate(shape["groups"]):
        for i in g:
            r, t = poses[i]
            r0, t0 = target[i]
            d = [t[k] - t0[k] for k in range(3)]
            dist = math.sqrt(sum(x * x for x in d))
            ang = K.angle_between(r0, r)
            se_t, se_r, views = shape["sigma"].get(i, (float("inf"), float("inf"), 0))
            se_t, se_r = max(se_t, SIGMA_FLOOR_CM / 100), max(se_r, SIGMA_FLOOR_DEG)
            measured = len(g) > 1 and views >= MIN_VIEWS
            rows.append({"id": i, "group": g_no, "group_size": len(g), "dx_cm": d[0] * 100, "dy_cm": d[1] * 100,
                         "dz_cm": d[2] * 100, "moved_cm": dist * 100, "turned_deg": ang,
                         "sigma_cm": se_t * 100, "sigma_deg": se_r, "views": views,
                         "frames": shape["counts"].get(i, 0), "measured": measured,
                         "significant": measured and (dist * 100 > max(MOVED_CM, SIGNIFICANT * se_t * 100)
                                                      or ang > max(1.0, SIGNIFICANT * se_r)),
                         "trusted": measured and dist <= TRUST_M and ang <= TRUST_DEG})
    measured = [r for r in rows if r["measured"]]
    rms = math.sqrt(sum(r["moved_cm"] ** 2 for r in measured) / len(measured)) if measured else float("nan")
    return {"rows": rows, "poses": poses, "groups": shape["groups"], "rms_cm": rms}


def survey(sightings, variant=None, year=2026):
    """The whole job: frames, a solve against each layout variant, findings and the layout to save."""
    fl = frames(sightings)
    F = []
    if not fl:
        return {"ok": True, "rows": [], "frames": 0, "findings": [{
            "level": "error", "title": "No frame had two tags in it",
            "why": "Drive (or carry the robot) where the camera sees two or more tags at once: in front of "
                   "a hub face, a trench, the outpost. Slowly, so the frames are sharp."}]}
    shape = solve(fl, official(variant or "welded", year))
    fits = {v: compare(shape, official(v, year)) for v in VARIANTS}
    best = min(fits, key=lambda v: fits[v]["rms_cm"] if math.isfinite(fits[v]["rms_cm"]) else 1e9)
    gap = abs(fits[VARIANTS[0]]["rms_cm"] - fits[VARIANTS[1]]["rms_cm"])
    told_apart = math.isfinite(gap) and gap >= MIN_FIT_GAP_CM
    if not told_apart:
        best = VARIANTS[0]   # most fields are welded; the event can say otherwise
    chosen = variant or best
    res = fits[chosen]
    layout = official(chosen, year)
    if not told_apart:
        F.append({"level": "info", "title": "Can't tell the welded and AndyMark layouts apart from this drive",
                  "why": f"Compared against the {chosen} layout. The two differ by a few centimeters "
                         "across the field, so telling them apart takes views that tie distant tags "
                         "together; or ask the event which tag mounts it uses."})
    elif variant and variant != best and fits[best]["rms_cm"] + 0.5 < fits[variant]["rms_cm"]:
        F.append({"level": "warn", "title": f"This field fits the {best} layout better than {variant}",
                  "why": f"Average tag error {fits[best]['rms_cm']:.1f} cm against {best}, "
                         f"{fits[variant]['rms_cm']:.1f} cm against {variant}. Ask the event which tag "
                         "mounts they use, and load that layout in the robot code."})
    elif not variant:
        others = [v for v in VARIANTS if v != best]
        F.append({"level": "info", "title": f"The tags fit the {best} layout best",
                  "why": f"Average error {fits[best]['rms_cm']:.1f} cm, against "
                         + ", ".join(f"{fits[v]['rms_cm']:.1f} cm for {v}" for v in others) + "."})
    for r in sorted(res["rows"], key=lambda r: -r["moved_cm"]):
        if not r["measured"]:
            continue
        if not r["trusted"]:
            F.append({"level": "error", "title": f"Tag {r['id']} is {r['moved_cm']:.0f} cm and {r['turned_deg']:.0f} degrees off",
                      "why": f"Beyond {TRUST_M * 100:.0f} cm or {TRUST_DEG:g} degrees, more likely a misread or "
                             "a tag on the wrong bracket than a real offset: the robot keeps the official "
                             "pose for it. Look at the tag itself.", "tag": r["id"]})
        elif r["significant"]:
            F.append({"level": "warn", "title": f"Tag {r['id']} is {r['moved_cm']:.1f} cm and {r['turned_deg']:.1f} degrees from its official pose",
                      "why": f"Measured to about ±{r['sigma_cm']:.1f} cm and ±{r['sigma_deg']:.1f} degrees over "
                             f"{r['views']} views. Saved in the surveyed layout, so poses solved from it "
                             "move back by that much.", "tag": r["id"]})
    quiet = [r for r in res["rows"] if r["measured"] and r["trusted"] and not r["significant"]]
    if quiet:
        F.append({"level": "ok", "title": f"{len(quiet)} tags are where they should be, within what this drive can measure",
                  "why": "Their measured offsets are smaller than three times their own measurement noise, "
                         "so they keep their official poses: noise must never move a tag."})
    lone = [r["id"] for r in res["rows"] if not r["measured"]]
    if lone:
        F.append({"level": "info", "title": f"Not measured: tags {', '.join(map(str, lone))}",
                  "why": f"Seen alone, or in fewer than {MIN_VIEWS} views with other tags. They keep "
                         "their official poses. Drive past them again, closer."})
    unseen = sorted(set(layout["tags"]) - {r["id"] for r in res["rows"]})
    tags = dict(layout["tags"])
    for r in res["rows"]:
        if r["trusted"] and r["significant"]:
            tags[r["id"]] = res["poses"][r["id"]]
    return {"ok": True, "variant": chosen, "best_variant": best, "rms_cm": res["rms_cm"],
            "rows": sorted(res["rows"], key=lambda r: r["id"]), "groups": res["groups"], "frames": len(fl),
            "unseen": unseen, "findings": F, "layout_text": layout_json(tags, layout["field"]),
            "fits": {v: fits[v]["rms_cm"] for v in VARIANTS}}
