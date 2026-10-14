"""The camera's PhotonVision from the laptop (photon.py), the new-field routines (newfield.py), and
the server's camera calls, against a stand-in PhotonVision (photonfake.py)."""

import math
import time
import unittest

from swervetune import newfield, photon, photonfake


class MessagePackTest(unittest.TestCase):
    def test_round_trip(self):
        v = {"a": 1, "b": -5, "c": 300, "d": -40000, "e": 2 ** 40, "f": 1.5, "g": "x" * 40, "h": [True, False, None],
             "i": {"j": [1, 2, {"k": "é"}]}, "l": list(range(20)), "m": {str(i): i for i in range(20)}}
        self.assertEqual(photon.mp_unpack(photon.mp_pack(v)), v)

    def test_what_photonvision_sends(self):
        # A float32, a uint16 and a str8 the way Jackson's MessagePack writes them.
        raw = bytes([0x83, 0xa3]) + b"fps" + bytes([0xca]) + (60.0).hex().encode()[:0] + bytes.fromhex("42700000") \
            + bytes([0xa5]) + b"count" + bytes([0xcd, 0x01, 0x2c]) + bytes([0xa4]) + b"name" + bytes([0xd9, 3]) + b"abc"
        self.assertEqual(photon.mp_unpack(raw), {"fps": 60.0, "count": 300, "name": "abc"})


class CameraTest(unittest.TestCase):
    def setUp(self):
        self.fake = photonfake.FakePhoton()
        self.cam = photon.Photon("127.0.0.1", self.fake.port).connect()
        self.addCleanup(self.fake.close)
        self.addCleanup(self.cam.close)
        self.u = self.cam.camera("front")["uniqueName"]

    def test_what_it_is(self):
        self.assertEqual(self.cam.version(), "v2026.3.4")
        self.assertEqual(self.cam.hardware()["hardware"], "Luma P1")
        self.assertEqual(photon.Photon.modes(self.cam.camera("front"))[0]["width"], 1280)

    def test_a_calibration(self):
        self.cam.start_calibration(self.u, 1)
        time.sleep(0.2)
        self.fake.board_visible = False
        self.assertFalse(self.cam.snapshot(self.u, wait=0.5)["counted"], "no board in the picture: not counted")
        self.fake.board_visible = True
        for _ in range(11):
            r = self.cam.snapshot(self.u)
        self.assertEqual(r["count"], 11)
        self.assertFalse(r["enough"])
        r = self.cam.snapshot(self.u)
        self.assertTrue(r["enough"])
        ok, msg = self.cam.finish_calibration(self.u)
        self.assertTrue(ok, msg)
        board = self.fake.sent[0]["startPnpCalibration"]
        self.assertEqual((board["patternWidth"], board["boardType"], board["markerSizeIn"]), (8, 1, 0.75))

    def test_too_few_snapshots(self):
        self.cam.start_calibration(self.u, 1)
        time.sleep(0.2)
        for _ in range(5):
            self.cam.snapshot(self.u)
        ok, _ = self.cam.finish_calibration(self.u)
        self.assertFalse(ok)

    def test_settings_keep_their_types(self):
        self.cam.change_settings(self.u, {"cameraGain": 40, "cameraExposureRaw": 1250.0})
        time.sleep(0.2)
        self.assertEqual(self.fake.settings["cameraGain"], 40)
        self.assertIsInstance(self.fake.settings["cameraGain"], int)
        self.assertEqual(self.fake.settings["cameraExposureRaw"], 1250.0)


class SummaryTest(unittest.TestCase):
    def test_the_field_of_view_from_the_lens(self):
        s = photon.summarize_calibration({"resolution": {"width": 1280, "height": 800},
                                          "cameraIntrinsics": {"data": [763.0, 0, 640, 0, 763.0, 400, 0, 0, 1]},
                                          "meanErrors": [0.2, 0.4]})
        self.assertEqual(s["hfov_deg"], 80.0, "the Luma P1's 80 degrees")
        self.assertAlmostEqual(s["mean_error_px"], 0.3)

    def test_frames(self):
        f = [{"targets": [{"fiducialId": 3, "ambiguity": 0.1}, {"fiducialId": 4, "ambiguity": 0.3}], "multitagResult": {}},
             {"targets": []}]
        s = photon.frame_stats(f)
        self.assertEqual((s["seen"], s["tags"]), (0.5, 1.0))
        self.assertAlmostEqual(s["ambiguity"], 0.2)


class LightingTest(unittest.TestCase):
    def test_exposure_from_the_blur_budget(self):
        # 6 px of smear at 360 degrees a second with the Luma's 763 px focal length: about 1.25 ms.
        self.assertEqual(newfield.exposure_us(763.0), round(6 / (763.0 * 2 * math.pi) * 1e6))
        self.assertEqual(newfield.exposure_us(763.0, lo=7, hi=500), 500)

    def test_the_lowest_gain_that_sees_them_then_one_more(self):
        trials = [{"gain": g, "seen": s, "tags": t} for g, s, t in
                  [(0, 0.1, 0.2), (20, 0.6, 1.2), (40, 0.95, 1.9), (60, 1.0, 2.0), (80, 1.0, 2.0), (100, 0.98, 2.0)]]
        self.assertEqual(newfield.choose_gain(trials), 60)
        self.assertIsNone(newfield.choose_gain([{"gain": 0, "seen": 0.2, "tags": 0.2}]))

    def run_job(self, light):
        fake = photonfake.FakePhoton(light=light)
        cam = photon.Photon("127.0.0.1", fake.port).connect()
        self.addCleanup(fake.close)
        self.addCleanup(cam.close)
        u = cam.camera("front")["uniqueName"]
        job = newfield.Lighting(cam, u, 763.0, settle=0.15, hold=0.5)
        job.run()
        time.sleep(0.2)
        return job, fake

    def test_tuned_to_the_light(self):
        job, fake = self.run_job(light=1.0)
        self.assertEqual(job.state, "finished")
        self.assertIsNotNone(job.result, job.message)
        self.assertEqual(fake.settings["cameraGain"], job.result["gain"])
        self.assertFalse(fake.settings["cameraAutoExposure"])
        self.assertEqual(fake.settings["cameraExposureRaw"], newfield.exposure_us(763.0))

    def test_too_dark_puts_the_old_settings_back(self):
        job, fake = self.run_job(light=0.05)
        self.assertIsNone(job.result)
        self.assertIn("didn't see tags", job.message)
        self.assertEqual(fake.settings["cameraGain"], 75, "its old gain is back")
        self.assertEqual(fake.settings["cameraExposureRaw"], 20.0)


class MountTest(unittest.TestCase):
    def spin(self, mount_err_m=0.0, yaw_err_deg=0.0, n=60):
        out = []
        for i in range(n):
            h = 360.0 * i / n
            a = math.radians(h)
            v = [mount_err_m * math.cos(a), mount_err_m * math.sin(a), h + yaw_err_deg]
            out.append(([0.0, 0.0, h], v))
        return out

    def test_a_right_mount_stays_put(self):
        r = newfield.mount_check(self.spin())
        self.assertTrue(r["ok"])
        self.assertEqual(r["spread_cm"], 0.0)

    def test_a_mount_off_by_5_cm_swings_round(self):
        r = newfield.mount_check(self.spin(0.05))
        self.assertFalse(r["ok"])
        self.assertAlmostEqual(r["spread_cm"], 5.0, places=1)

    def test_a_turned_mount(self):
        r = newfield.mount_check(self.spin(0.0, 3.0))
        self.assertFalse(r["ok"])
        self.assertEqual(r["heading_offset_deg"], 3.0)

    def test_too_few_poses(self):
        self.assertIsNone(newfield.mount_check(self.spin(n=5))["ok"])


class ServerTest(unittest.TestCase):
    def test_connect_and_compare_with_photonlib(self):
        from swervetune import server
        fake = photonfake.FakePhoton(version="v2026.3.3")
        self.addCleanup(fake.close)
        server.S.set_project("Peashooter")
        r = server.api_camera_connect({"host": f"127.0.0.1:{fake.port}"})
        self.addCleanup(lambda: server.CAMERA["photon"] and server.CAMERA["photon"].close())
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["photonlib"], "v2026.3.4")
        self.assertFalse(r["match"], "a 2026.3.3 camera with 2026.3.4 PhotonLib")
        self.assertEqual(r["cameras"][0]["nickname"], "front")
        self.assertTrue(r["cameras"][0]["stream"].endswith(":1181/stream.mjpg"))

    def test_lighting_needs_a_lens_calibration(self):
        from swervetune import server
        fake = photonfake.FakePhoton()
        self.addCleanup(fake.close)
        server.api_camera_connect({"host": f"127.0.0.1:{fake.port}"})
        self.addCleanup(lambda: server.CAMERA["photon"] and server.CAMERA["photon"].close())
        r = server.api_camera_lighting({"camera": "front"})
        self.assertFalse(r["ok"])
        self.assertIn("Calibrate the lens", r["error"])

    def test_no_camera_there(self):
        from swervetune import server
        r = server.api_camera_connect({"host": "127.0.0.1:1"})
        self.assertFalse(r["ok"])
        self.assertIn("No PhotonVision", r["error"])


if __name__ == "__main__":
    unittest.main()
