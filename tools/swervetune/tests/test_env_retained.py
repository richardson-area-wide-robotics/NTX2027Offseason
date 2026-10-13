"""The environment a one-shot command line sets outlives the command (gap check, agent B1)."""

import os
import subprocess
import sys
import time
import unittest

try:
    import ntcore
except ImportError:  # pragma: no cover
    ntcore = None

from swervetune import contract as C

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
PORT = 5897

CLIENT = """
import sys, time
sys.path.insert(0, {tools!r})
from swervetune import link as L
L.NT_PORT = {port}
lk = L.RobotLink(["127.0.0.1"], client_name="one-shot")
for _ in range(100):
    if lk.inst.isConnected():
        break
    time.sleep(0.05)
lk.set_environment(mode="BLOCKS", space_forward=3.0, space_side=1.5)
time.sleep(0.5)
lk.close()
"""


@unittest.skipIf(ntcore is None, "pyntcore not installed")
class EnvOutlivesTheCommandTest(unittest.TestCase):
    def test_the_robot_keeps_the_environment_after_the_command_exits(self):
        server = ntcore.NetworkTableInstance.create()
        server.startServer("", "", 0, PORT)
        try:
            mode = server.getStringTopic(C.ENV_MODE).subscribe("UNSET")
            space = server.getDoubleTopic(C.ENV_SPACE_FORWARD).subscribe(0.0)
            subprocess.run([sys.executable, "-c", CLIENT.format(tools=TOOLS, port=PORT)], check=True, timeout=30)
            time.sleep(1.0)  # the client is gone: before the fix the topic went with it
            self.assertEqual(mode.get(), "BLOCKS")
            self.assertEqual(space.get(), 3.0)
        finally:
            server.stopServer()
            ntcore.NetworkTableInstance.destroy(server)
