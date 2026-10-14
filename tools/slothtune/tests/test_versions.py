"""Software versions (versions.py): each library against the newest for its year, PhotonLib against
PhotonVision's releases, and the camera against PhotonLib. The internet is faked."""

import json
import os
import tempfile
import unittest

from slothtune import station, versions as V

RELEASES = [
    {"tag_name": "Dev", "prerelease": True, "assets": []},
    {"tag_name": "v2027.0.0-alpha-2", "prerelease": True, "assets": []},
    {"tag_name": "v2026.3.4", "prerelease": False, "html_url": "https://github.com/PhotonVision/photonvision/releases/tag/v2026.3.4",
     "assets": [{"name": "photonlib-v2026.3.4.json", "browser_download_url": "https://x/photonlib-v2026.3.4.json"},
                {"name": "photonvision-v2026.3.4-linuxarm64_luma_p1.img.xz", "browser_download_url": "https://x/luma.img.xz"}]},
    {"tag_name": "v2026.7", "prerelease": True, "assets": []},          # April Fools
    {"tag_name": "v2026.3.3", "prerelease": False, "assets": []},
]


def project(root, name, deps):
    d = os.path.join(root, name, "vendordeps")
    os.makedirs(d)
    for fname, body in deps.items():
        with open(os.path.join(d, fname), "w", encoding="utf-8") as fh:
            json.dump(body, fh)
    return (name, os.path.join(root, name), None)


def lib(name, version, url, year="2026"):
    return {"name": name, "version": version, "jsonUrl": url, "frcYear": year}


class Fake:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def __call__(self, url):
        self.asked.append(url)
        if url not in self.pages:
            raise OSError("no answer")
        return self.pages[url]


class VersionsTest(unittest.TestCase):
    def setUp(self):
        V._cache.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def robots(self, photon="v2026.3.4", yagsl="2026.4.1"):
        deps = {"photonlib.json": lib("photonlib", photon, "https://maven/photonlib-json-1.0.json"),
                "yagsl.json": lib("YAGSL", yagsl, "https://yagsl/latest.json"),
                "REVLib.json": lib("REVLib", "2026.0.5", "https://rev/latest.json")}
        return [project(self.tmp.name, "Peashooter", deps), project(self.tmp.name, "Black team", deps)]

    def fake(self):
        return Fake({V.PV_RELEASES: RELEASES,
                     "https://yagsl/latest.json": {"version": "2026.10.03", "frcYear": "2026"},
                     "https://rev/latest.json": {"version": "2027.0.0-beta-1", "frcYear": "2027"},
                     # PhotonLib's own address gives the 2027 alpha: it must never be offered.
                     "https://maven/photonlib-json-1.0.json": {"version": "v2027.0.0-alpha-2"}})

    def by_id(self, found):
        return {c["id"]: c for c in found}

    def test_the_newest_2026_release_not_an_alpha_or_a_joke(self):
        r = V.latest_photonvision("2026", RELEASES)
        self.assertEqual(r["version"], "v2026.3.4")
        self.assertEqual(r["luma_image"], "https://x/luma.img.xz")
        self.assertEqual(r["photonlib_json"], "https://x/photonlib-v2026.3.4.json")

    def test_up_to_date(self):
        c = self.by_id(V.checks(self.robots(), "v2026.3.4", fetch=self.fake()))
        self.assertEqual(c["photonlib-peashooter"]["level"], "ok")
        self.assertEqual(c["photonlib-black-team"]["level"], "ok")
        self.assertEqual(c["camera-photonvision"]["level"], "ok")
        self.assertEqual(c["vendordep-revlib"]["level"], "ok", "a 2027 beta is not an update for 2026 code")
        self.assertEqual(c["vendordep-yagsl"]["level"], "warn")
        self.assertIn("2026.10.03", c["vendordep-yagsl"]["title"])

    def test_an_older_photonlib(self):
        c = self.by_id(V.checks(self.robots(photon="v2026.3.3"), None, fetch=self.fake()))
        self.assertEqual(c["photonlib-peashooter"]["level"], "warn")
        self.assertIn("photonlib-v2026.3.4.json", c["photonlib-peashooter"]["why"])

    def test_the_camera_must_match_photonlib(self):
        c = self.by_id(V.checks(self.robots(), "2026.3.3", fetch=self.fake()))
        self.assertEqual(c["camera-photonvision"]["level"], "fail")
        self.assertIn("Luma P1 image", c["camera-photonvision"]["why"])

    def test_no_internet_asks_once(self):
        f = Fake({})
        found = V.checks(self.robots(), "v2026.3.4", fetch=f)
        c = self.by_id(found)
        self.assertEqual(c["versions-offline"]["level"], "info")
        self.assertEqual(c["camera-photonvision"]["level"], "ok", "the camera still matches PhotonLib")
        self.assertEqual(f.asked, [V.PV_RELEASES], "one try, not one wait per library")

    def test_robots_on_different_versions_are_named(self):
        a = project(self.tmp.name, "A", {"y.json": lib("YAGSL", "2026.4.1", "https://yagsl/latest.json")})
        b = project(self.tmp.name, "B", {"y.json": lib("YAGSL", "2026.10.03", "https://yagsl/latest.json")})
        found = [c for c in V.checks([a, b], None, fetch=self.fake()) if c["id"].startswith("vendordep-yagsl")]
        self.assertEqual(len(found), 2)
        self.assertEqual({c["level"] for c in found}, {"warn", "ok"})
        self.assertTrue(all(c["title"].startswith(("A: ", "B: ")) for c in found))

    def test_versions_compare_as_numbers(self):
        self.assertLess(V.vkey("v2026.3.3"), V.vkey("v2026.3.4"))
        self.assertLess(V.vkey("2026.4.1"), V.vkey("2026.10.03"))
        self.assertLess(V.vkey("v2027.0.0-alpha-2"), V.vkey("v2027.0.0"))

    def test_the_network_check_shows_them_before_the_internet(self):
        mine = [{"id": "x", "group": V.GROUP, "level": "ok", "title": "t", "why": "w"}]
        got = station.checks({"checks": []}, 1745, versions=mine)
        self.assertEqual([c["id"] for c in got], ["x"])
        self.assertLess(station.ORDER.index(V.GROUP), station.ORDER.index(station.INTERNET))


if __name__ == "__main__":
    unittest.main()
