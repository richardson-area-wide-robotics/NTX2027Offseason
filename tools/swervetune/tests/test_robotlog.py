"""What the robot keeps reporting (robotlog.py): its console frames read as WPILib sends them, and
each message counted once with how often and how recently."""

import socket
import socketserver
import struct
import threading
import time
import unittest

from swervetune import robotlog as R


def string(s):
    b = s.encode("utf-8")
    return struct.pack("!H", len(b)) + b


def error_frame(details, location="", flags=1, occur=1, code=-1029):
    """Built as WPILib's riolog test sender builds one (vscode-wpilib resources/testing/riosender.py)."""
    inner = struct.pack("!fHHiB", 1.5, 7, occur, code, flags) + string(details) + string(location) + string("trace")
    return struct.pack("!HB", len(inner) + 1, 11) + inner


def print_frame(line):
    inner = struct.pack("!fH", 1.5, 8) + line.encode("utf-8")
    return struct.pack("!HB", len(inner) + 1, 12) + inner


class FramesTest(unittest.TestCase):
    def test_errors_warnings_and_printed_lines(self):
        buf = (error_frame("CAN: timed out waiting for ID 5", "SparkMax.java:120")
               + error_frame("Joystick Button 7 on port 0 not available", flags=0)
               + print_frame("Robot program startup complete")
               + print_frame("Warning: the gyro is not calibrated"))
        frames, rest = R.parse_frames(buf + print_frame("cut")[:4])
        self.assertEqual(len(frames), 4)
        self.assertEqual(len(rest), 4, "half a frame waits for the rest")
        msgs = [R.parse_message(t, b) for t, b in frames]
        self.assertEqual((msgs[0]["level"], msgs[0]["text"], msgs[0]["where"], msgs[0]["code"]),
                         ("error", "CAN: timed out waiting for ID 5", "SparkMax.java:120", -1029))
        self.assertEqual(msgs[1]["level"], "warning", "flags bit 0 clear: a warning")
        self.assertIsNone(msgs[2], "an ordinary printed line counts for nothing")
        self.assertEqual(msgs[3]["level"], "warning")

    def test_printed_lines_that_count(self):
        self.assertEqual(R.classify_print("java.lang.NullPointerException: shooter"), "error")
        self.assertEqual(R.classify_print("Error at frc.robot.Robot.init: no camera"), "error")
        self.assertIsNone(R.classify_print("  at frc.robot.Robot.robotInit(Robot.java:40)"), "a stack frame belongs to the line above")
        self.assertIsNone(R.classify_print("Shooter at speed"))


class TallyTest(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.t = R.Tally(clock=lambda: self.now[0])

    def test_the_same_message_is_counted_not_repeated(self):
        for dt in (0.0213, 0.0187, 0.0302):
            self.t.add("warning", f"Loop time of 0.02s overrun by {dt} s")
        self.t.add("error", "CAN: timed out waiting for ID 5")
        self.t.add("error", "CAN: timed out waiting for ID 6")
        rows = self.t.summary()
        self.assertEqual(len(rows), 3, "measurements merge; CAN IDs stay apart")
        loop = [r for r in rows if "overrun" in r["text"]][0]
        self.assertEqual((loop["count"], loop["repeating"], loop["ongoing"]), (3, True, True))
        self.assertEqual(rows[0]["level"], "error", "errors first")

    def test_what_stopped_and_what_keeps_happening(self):
        self.t.add("error", "Brownout")
        self.now[0] += 300
        self.t.add("warning", "Loop overrun")
        rows = {r["text"]: r for r in self.t.summary()}
        self.assertFalse(rows["Brownout"]["ongoing"])
        self.assertEqual(rows["Brownout"]["last_ago_s"], 300.0)
        self.assertTrue(rows["Loop overrun"]["ongoing"])
        self.assertEqual(self.t.summary()[0]["text"], "Loop overrun", "what is still happening comes first")

    def test_an_alert_counts_each_time_it_comes_on(self):
        on = [("warning", "frontleft drive dropped off the CAN bus once")]
        self.t.alerts(on)
        self.t.alerts(on)
        self.t.alerts([])
        self.t.alerts(on)
        r = self.t.summary()[0]
        self.assertEqual((r["count"], r["source"]), (2, "alert"))

    def test_clear(self):
        self.t.add("error", "x")
        self.t.clear()
        self.assertEqual(self.t.summary(), [])


class ConsoleWatchTest(unittest.TestCase):
    def test_it_reads_a_console_and_counts(self):
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                f = error_frame("CAN: timed out waiting for ID 5")
                self.request.sendall(f[:5])     # a frame split across writes, as the sender does
                time.sleep(0.05)
                self.request.sendall(f[5:] + error_frame("CAN: timed out waiting for ID 5"))
                time.sleep(0.3)

        srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        tally = R.Tally()
        w = R.ConsoleWatch("127.0.0.1", tally, port=srv.server_address[1])
        try:
            end = time.time() + 5
            while time.time() < end and not tally.summary():
                time.sleep(0.05)
            time.sleep(0.2)
            rows = tally.summary()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["count"], 2)
        finally:
            w.stop()
            srv.shutdown()
            srv.server_close()

    def test_no_robot_console_is_not_an_error(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()   # nothing listens there
        w = R.ConsoleWatch("127.0.0.1", R.Tally(), port=port)
        try:
            end = time.time() + 3
            while time.time() < end and w.state == "connecting":
                time.sleep(0.05)
            self.assertEqual(w.state, "not connected")
        finally:
            w.stop()


if __name__ == "__main__":
    unittest.main()
