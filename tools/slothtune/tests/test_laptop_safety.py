"""The laptop's half of keeping people safe (server.py): where the robot is, and Hold to run.

* "On blocks" and "On the floor" are retained NetworkTables values, so they outlive the laptop that
  said them, and on reconnecting a laptop sends a restarted robot its last value again. A new GUI
  connection, and a restart of the robot code, must each tell the robot UNSET and ask a person again.
* The page's Hold to run counts for 300 ms after each refresh (the page refreshes it every 100 ms),
  and only while the page itself keeps checking in (every half second at the least).
"""

import os
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

from slothtune import contract as C, link as L, server

try:
    import ntcore
except ImportError:  # pragma: no cover
    ntcore = None

TOOLS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeLink:
    """A robot link that records what the laptop tells the robot."""

    def __init__(self, boot=101):
        self.boot, self.env, self.deadman, self.connected = boot, [], [], True

    def get(self, kind, name, default=None):
        return {C.BOOT_ID: self.boot, C.PROTOCOL: C.PROTOCOL_VERSION}.get(name, default)

    def set_environment(self, mode=None, *_):
        self.env.append(mode)

    def set_gui_deadman(self, held):
        self.deadman.append(bool(held))

    def wait_connected(self, _timeout):
        return True

    def has_harness(self):
        return True

    def start_heartbeat(self, gate=None):
        self.gate = gate

    def robot_info(self):
        return {"name": ""}

    def environment(self):
        return {"active": "UNSET"}

    def status(self):
        return {}

    def gains(self):
        return {}

    def is_connected(self):
        return self.connected

    def close(self):
        self.connected = False


class Clock:
    """Stands in for server.time: the test moves the clock, nothing waits."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def __getattr__(self, name):
        return getattr(time, name)


class WhereIsAskedAgainTest(unittest.TestCase):
    def setUp(self):
        self.s = server.Session()
        self.links = []

        def make(*_a, **_k):
            self.links.append(FakeLink())
            return self.links[-1]

        for p in (mock.patch.object(L, "RobotLink", make), mock.patch.object(L, "ntcore", object())):
            p.start()
            self.addCleanup(p.stop)

    def test_a_new_connection_tells_the_robot_unset(self):
        self.assertTrue(self.s.connect("host", "127.0.0.1"))
        self.assertEqual(self.links[0].env, ["UNSET"], "never inherits an earlier 'On blocks'")
        self.assertEqual(self.s.where_asked, {"n": 1, "why": "connect"})
        with mock.patch.object(server, "S", self.s):
            self.assertEqual(server.api_state(None)["where_asked"], {"n": 1, "why": "connect"}, "the page asks again")

    def test_a_restart_of_the_robot_code_tells_it_unset_again(self):
        self.s.connect("host", "127.0.0.1")
        lk = self.links[0]
        lk.env.append("BLOCKS")          # a person ticked the checklist
        self.s.browser_alive()
        self.assertEqual(lk.env, ["UNSET", "BLOCKS"], "the same robot code: nothing to ask")
        lk.boot = 202                     # the robot code restarted
        self.s.browser_alive()
        self.assertEqual(lk.env, ["UNSET", "BLOCKS", "UNSET"])
        self.assertEqual(self.s.where_asked, {"n": 2, "why": "restart"})
        self.s.browser_alive()
        self.assertEqual(len(lk.env), 3, "once per restart")

    def test_reconnecting_asks_again(self):
        self.s.connect("host", "127.0.0.1")
        self.s.disconnect()
        self.assertIsNone(self.s.where_boot)
        self.s.connect("host", "127.0.0.1")
        self.assertEqual(self.links[1].env, ["UNSET"])
        self.assertEqual(self.s.where_asked, {"n": 2, "why": "connect"})

    def test_a_watch_that_fails_never_stops_the_heartbeat(self):
        self.s.connect("host", "127.0.0.1")
        self.links[0].get = mock.Mock(side_effect=RuntimeError("gone"))
        self.s.last_poll = time.monotonic()
        with mock.patch.object(server.traceback, "print_exc"):
            self.assertTrue(self.s.browser_alive(), "the gate still answers")


class HoldToRunExpiresTest(unittest.TestCase):
    """The deadman's laptop half: what the heartbeat tells the robot, beat by beat (browser_alive is
    its gate, asked every 50 ms)."""

    def setUp(self):
        self.clock = Clock()
        self.s = server.Session()
        self.s.link = FakeLink()
        for p in (mock.patch.object(server, "time", self.clock), mock.patch.object(server, "S", self.s)):
            p.start()
            self.addCleanup(p.stop)

    def at(self, t, poll=True):
        """The time is ``t`` s after the start; ``poll``: the page checked in just now."""
        self.clock.now = 1000.0 + t
        if poll:
            self.s.last_poll = self.clock.now
        alive = self.s.browser_alive()
        return alive, self.s.link.deadman[-1]

    def test_a_held_button_lets_go_300_ms_after_its_last_refresh(self):
        self.at(0.0)
        server.api_deadman({"held": True})
        self.assertEqual(self.at(0.29), (True, True))
        self.assertEqual(self.at(0.31), (True, False), "no refresh for 300 ms: let go")
        server.api_deadman({"held": True})                 # refreshed at 0.31
        self.assertEqual(self.at(0.60), (True, True))
        self.assertEqual(self.at(0.62), (True, False))

    def test_refreshed_every_100_ms_it_stays_held(self):
        for k in range(30):
            self.at(0.1 * k)
            server.api_deadman({"held": True})
            self.assertEqual(self.at(0.1 * k + 0.09), (True, True), k)

    def test_letting_go_is_at_once(self):
        self.at(0.0)
        server.api_deadman({"held": True})
        server.api_deadman({"held": False})
        self.assertEqual(self.at(0.01), (True, False))

    def test_a_silent_browser_drops_it_even_while_refreshed(self):
        # The page stops checking in (tab closed, laptop asleep) though something still refreshes the
        # button: half a second after the last check-in the deadman, and the heartbeat, end.
        self.at(0.0)
        for k in range(1, 6):
            server.api_deadman({"held": True})
            self.assertEqual(self.at(0.1 * k - 0.01, poll=False), (True, True), k)
        server.api_deadman({"held": True})
        self.assertEqual(self.at(0.5, poll=False), (False, False))
        self.assertEqual(self.at(0.7, poll=False), (False, False))


@unittest.skipIf(ntcore is None, "pyntcore not installed")
class OverNetworkTablesTest(unittest.TestCase):
    """The same, as the robot sees it. The robot is a NetworkTables server in its own process, so
    restarting the robot code is what it really is: a new process with a new boot id."""

    PORT = 5893
    ROBOT = """
import sys, time
sys.path.insert(0, {tools!r})
import ntcore
from slothtune import contract as C
inst = ntcore.NetworkTableInstance.create()
inst.startServer("", "", 0, {port})
pubs = [inst.getIntegerTopic(C.PROTOCOL).publish(), inst.getIntegerTopic(C.BOOT_ID).publish()]  # kept: a dropped one unpublishes
pubs[0].set(C.PROTOCOL_VERSION)
pubs[1].set({boot})
mode = inst.getStringTopic(C.ENV_MODE).subscribe("nothing yet")
held = inst.getBooleanTopic(C.CLIENT_DEADMAN).subscribe(False)
last = None
while True:
    now = (mode.get(), held.get())
    if now != last:
        print(now[0], now[1], flush=True)
        last = now
    time.sleep(0.01)
"""

    def robot(self, boot):
        """Starts the robot code; what it hears is collected as (boot, time, mode, held)."""
        p = subprocess.Popen([sys.executable, "-u", "-c", self.ROBOT.format(tools=TOOLS, port=self.PORT, boot=boot)],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(self.stop_robot, p)

        def read():
            for line in p.stdout:
                mode, held = line.strip().rsplit(" ", 1)
                self.heard.append((boot, time.monotonic(), mode, held == "True"))
        threading.Thread(target=read, daemon=True).start()
        self.assertTrue(self.until(lambda: self.now(boot)), "the robot code didn't start")
        return p

    def stop_robot(self, p):
        if p.poll() is None:
            p.kill()
            p.wait(10)
        p.stdout.close()

    def now(self, boot):
        """What the robot with this boot id last heard: (mode, held), or None before it is up."""
        rows = [h for h in self.heard if h[0] == boot]
        return rows[-1][2:] if rows else None

    def until(self, cond, seconds=10.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if cond():
                return True
            time.sleep(0.02)
        return False

    def setUp(self):
        self.heard = []
        p = mock.patch.object(L, "NT_PORT", self.PORT)
        p.start()
        self.addCleanup(p.stop)
        self.s = server.Session()
        self.addCleanup(self.s.disconnect)
        # The page polls: the browser stays alive for the heartbeat's gate.
        self.polling = True

        def poll():
            while self.polling:
                self.s.last_poll = time.monotonic()
                time.sleep(0.05)
        threading.Thread(target=poll, daemon=True).start()
        self.addCleanup(setattr, self, "polling", False)

    def restart_after_blocks(self):
        """Connects, a person says BLOCKS, then the robot code restarts: returns the new robot's boot id."""
        first = self.robot(1001)
        self.assertTrue(self.s.connect("host", "127.0.0.1"))
        self.s.link.set_environment("BLOCKS")
        self.assertTrue(self.until(lambda: self.now(1001)[0] == "BLOCKS"))
        self.stop_robot(first)
        self.robot(2002)
        return 2002

    def test_a_new_connection_never_inherits_an_earlier_blocks(self):
        self.robot(1001)
        earlier = L.RobotLink(["127.0.0.1"], client_name="earlier-laptop")
        self.assertTrue(self.until(earlier.is_connected))
        earlier.set_environment("BLOCKS")
        self.assertTrue(self.until(lambda: self.now(1001)[0] == "BLOCKS"))
        earlier.close()                   # that laptop is gone; the robot keeps BLOCKS (retained)
        time.sleep(0.3)
        self.assertEqual(self.now(1001)[0], "BLOCKS")
        self.assertTrue(self.s.connect("host", "127.0.0.1"))
        self.assertTrue(self.until(lambda: self.now(1001)[0] == "UNSET"), self.now(1001))

    def test_a_restarted_robot_is_told_unset_again(self):
        boot = self.restart_after_blocks()
        self.assertTrue(self.until(lambda: self.s.where_asked["why"] == "restart"), self.s.where_asked)
        self.assertTrue(self.until(lambda: self.now(boot)[0] == "UNSET"), self.now(boot))
        time.sleep(0.5)
        self.assertEqual(self.now(boot)[0], "UNSET", "and it stays UNSET")

    def test_without_the_watch_a_restarted_robot_comes_back_on_blocks(self):
        # The hazard the restart watch closes: this laptop's own publisher sends its last value again.
        with mock.patch.object(server.Session, "watch_restart", lambda self: None):
            boot = self.restart_after_blocks()
            self.assertTrue(self.until(lambda: self.now(boot)[0] == "BLOCKS"), self.now(boot))

    def test_the_robot_sees_hold_to_run_let_go_300_ms_after_the_last_refresh(self):
        self.robot(1001)
        self.assertTrue(self.s.connect("host", "127.0.0.1"))
        with mock.patch.object(server, "S", self.s):
            server.api_deadman({"held": True})
            last = time.monotonic()
            self.assertTrue(self.until(lambda: self.now(1001)[1], 0.3), "held, within a beat or two")
            self.assertTrue(self.until(lambda: not self.now(1001)[1], 2.0))
        gone = next(t for b, t, _, held in reversed(self.heard) if b == 1001 and not held) - last
        self.assertGreaterEqual(gone, 0.25, "not before its 300 ms")
        self.assertLess(gone, 0.8, "300 ms, then a 50 ms beat and the network")


class SurveyDropTest(unittest.TestCase):
    """The field survey's recording pauses when the robot drops out, and says so."""

    def setUp(self):
        self.link = FakeLink()
        self.link.sightings = lambda: []
        p = mock.patch.object(server.S, "link", self.link)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.stop)

    def stop(self):
        server.api_survey_stop(None)
        if server.SURVEY["thread"]:
            server.SURVEY["thread"].join(2)

    def wait_for(self, text):
        end = time.time() + 3
        while time.time() < end and text not in server.api_survey_state()["dropped"]:
            time.sleep(0.05)
        return server.api_survey_state()["dropped"]

    def test_a_dropped_connection_is_reported_not_swallowed(self):
        self.assertTrue(server.api_survey_start({})["ok"])
        self.assertEqual(server.api_survey_state()["dropped"], "")
        self.link.connected = False
        self.assertIn("recording paused until it is back", self.wait_for("paused"))
        self.link.connected = True
        self.assertIn("came back", self.wait_for("came back"))

    def test_an_error_reading_the_tags_says_what_it_was(self):
        self.link.sightings = mock.Mock(side_effect=RuntimeError("bad frame"))
        server.api_survey_start({})
        self.assertIn("(bad frame)", self.wait_for("bad frame"))


if __name__ == "__main__":
    unittest.main()
