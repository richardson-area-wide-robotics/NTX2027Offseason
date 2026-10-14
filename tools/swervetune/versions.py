"""Is each piece of the robot's software the newest for its year?

* The robot code's vendor libraries (``vendordeps/*.json``): each names where its newest version is
  published (its ``jsonUrl``). PhotonLib's points at the newest build of any year, a 2027 alpha
  included, so PhotonLib is checked against PhotonVision's GitHub releases instead.
* The camera's PhotonVision (read from the robot's NetworkTables, ``/photonvision/version``): it
  must be the same version as the PhotonLib in the code, and should be the newest release.

Only the same FRC year counts as newer: a 2027 alpha is not an update for 2026 code. Nothing here
changes a file; each finding says what to do. Answers are kept for a few hours, and with no
internet the checks say so rather than waiting on each address.
"""

import glob
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

GROUP = "Software versions"
PV_RELEASES = "https://api.github.com/repos/PhotonVision/photonvision/releases?per_page=30"
PV_PAGE = "https://github.com/PhotonVision/photonvision/releases"
CACHE_S = 6 * 3600
_cache = {}


def _check(cid, level, title, why):
    return {"id": cid, "group": GROUP, "level": level, "title": title, "why": why}


def vkey(v):
    """A version as numbers to compare: "v2026.3.4" -> (2026, 3, 4). A pre-release sorts first."""
    s = str(v or "").strip().lstrip("vV")
    nums = tuple(int(x) for x in re.findall(r"\d+", s.split("-")[0]))
    return nums + ((0,) if "-" in s else (1,))


def fetch_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "swervetune-version-check",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _cached(url, fetch):
    hit = _cache.get(url)
    if hit and time.time() - hit[0] < CACHE_S:
        return hit[1]
    val = fetch(url)
    _cache[url] = (time.time(), val)
    return val


def local(project_path):
    """The robot code's vendor libraries: name, file, version, FRC year and update address."""
    out = []
    for f in sorted(glob.glob(os.path.join(project_path, "vendordeps", "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        out.append({"name": d.get("name") or os.path.basename(f), "file": os.path.basename(f),
                    "version": d.get("version") or "", "year": str(d.get("frcYear") or ""),
                    "url": d.get("jsonUrl") or ""})
    return out


def latest_photonvision(year, releases):
    """The newest full release for ``year`` from PhotonVision's GitHub releases list, with its Luma
    P1 image and its PhotonLib file, or None."""
    best = None
    for r in releases or []:
        tag = r.get("tag_name") or ""
        if r.get("prerelease") or r.get("draft") or not tag.startswith(f"v{year}."):
            continue
        if best is None or vkey(tag) > vkey(best["tag_name"]):
            best = r
    if not best:
        return None
    assets = {a.get("name") or "": a.get("browser_download_url") for a in best.get("assets") or []}
    luma = next((u for n, u in assets.items() if "luma_p1" in n), None)
    lib = next((u for n, u in assets.items() if n.startswith("photonlib-") and n.endswith(".json")), None)
    return {"version": best["tag_name"], "url": best.get("html_url") or PV_PAGE, "luma_image": luma, "photonlib_json": lib}


def online(fetch=fetch_json):
    """Can this laptop reach the internet? One quick try, so a laptop on the robot's network alone
    doesn't wait on every address in turn."""
    try:
        _cached(PV_RELEASES, fetch)
        return True
    except Exception:  # noqa: BLE001 - no internet, a proxy, GitHub down: all "can't check"
        _cache.pop(PV_RELEASES, None)
        return False


def checks(projects, camera_version=None, fetch=fetch_json, is_online=None):
    """Version checks for the robot projects (``[(name, path, year)]``) and the camera's PhotonVision.

    ``camera_version`` is what the connected robot's ``/photonvision/version`` says, if anything.
    """
    out = []
    projects = [p for p in projects if p and p[1]]
    deps = {name: local(path) for name, path, _ in projects}
    photonlib = {name: next((d for d in ds if d["name"].lower() == "photonlib"), None) for name, ds in deps.items()}
    reach = online(fetch) if is_online is None else is_online
    if not reach:
        out.append(_check("versions-offline", "info", "Couldn't check for newer versions: no internet",
                          "Run the check again with the laptop on the internet as well (Wi-Fi beside the robot's network)."))
    year = next((str(y) for _, _, y in projects if y), None) or next(
        (d["year"] for ds in deps.values() for d in ds if d["year"]), None)
    latest = None
    if reach and year:
        try:
            latest = latest_photonvision(year, _cached(PV_RELEASES, fetch))
        except Exception:  # noqa: BLE001
            latest = None

    # PhotonLib in each robot's code.
    for name, lib in photonlib.items():
        if not lib:
            continue
        cid = "photonlib-" + re.sub(r"\W+", "-", name.lower()).strip("-")
        if latest and vkey(lib["version"]) < vkey(latest["version"]):
            out.append(_check(cid, "warn", f"{name}: PhotonLib {lib['version']}, and {latest['version']} is out",
                              f"Replace {name}/vendordeps/photonlib.json with the release's photonlib-{latest['version']}.json, "
                              f"build once with the internet on, and update the camera to {latest['version']} too: "
                              "the two must match."))
        else:
            out.append(_check(cid, "ok", f"{name}: PhotonLib {lib['version']}" + (" (the newest)" if latest else ""),
                              "The camera's PhotonVision must be this same version."))

    # The camera's own PhotonVision.
    libs = {lib["version"] for lib in photonlib.values() if lib}
    if camera_version:
        cam = str(camera_version)
        if libs and not any(vkey(cam)[:3] == vkey(v)[:3] for v in libs):
            out.append(_check("camera-photonvision", "fail",
                              f"The camera runs PhotonVision {cam}; the robot code has PhotonLib {', '.join(sorted(libs))}",
                              "They must be the same version, or the robot gets no camera data. Update the camera "
                              "(flash the release's Luma P1 image, or upload its linuxarm64 .jar on the camera's "
                              "Settings page), or change the code's PhotonLib to match."))
        elif latest and vkey(cam) < vkey(latest["version"]):
            out.append(_check("camera-photonvision", "warn", f"The camera runs PhotonVision {cam}, and {latest['version']} is out",
                              f"Update the camera and the robot code's PhotonLib together ({latest['url']})."))
        else:
            out.append(_check("camera-photonvision", "ok", f"The camera runs PhotonVision {cam}", "The same as the robot code's PhotonLib."))

    # Every other library, against the address it names for its newest version (same year only).
    others = {}
    for proj, ds in deps.items():
        for d in ds:
            if d["name"].lower() != "photonlib" and d["url"]:
                others.setdefault((d["name"], d["version"], d["url"], d["year"]), []).append(proj)
    # A library at different versions in different robots: each finding names its robots.
    split = {k[0] for k in others if sum(1 for j in others if j[0] == k[0]) > 1}
    if reach and others:
        def newest(key):
            try:
                j = _cached(key[2], fetch)
                return key, j.get("version"), str(j.get("frcYear") or "")
            except Exception:  # noqa: BLE001
                return key, None, None
        with ThreadPoolExecutor(max_workers=6) as pool:
            found = list(pool.map(newest, others))
        for key, new, new_year in found:
            lib, have, _url, dep_year = key
            cid = "vendordep-" + re.sub(r"\W+", "-", lib.lower()).strip("-")
            if lib in split:
                cid += "-" + re.sub(r"\W+", "-", str(have))
                lib = f"{' and '.join(others[key])}: {lib}"
            if not new:
                out.append(_check(cid, "info", f"{lib} {have}: couldn't read its newest version", "Its update address didn't answer."))
            elif new_year and dep_year and new_year != dep_year:
                out.append(_check(cid, "ok", f"{lib} {have}", f"Its newest is for {new_year}; this code is {dep_year}."))
            elif vkey(new) > vkey(have):
                out.append(_check(cid, "warn", f"{lib} {have}, and {new} is out",
                                  "WPILib's Manage Vendor Libraries, Check for Updates (online) updates it. Read its "
                                  "release notes, build, and test on the robot before an event."))
            else:
                out.append(_check(cid, "ok", f"{lib} {have} (the newest)", "Nothing to do."))
    return out
