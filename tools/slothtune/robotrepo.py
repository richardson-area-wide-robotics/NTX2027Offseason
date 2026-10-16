"""Where the robot projects are.

In the team's robot repo, Sloth Tune lives in tools/slothtune and the robots (Peashooter, Black team,
Examples) sit beside tools/. In Sloth Tune's own repo there are no robots: set SLOTHTUNE_ROBOT_REPO to a
checkout of the robot repo and the tool, and its tests of the real robots, read the robots from there.
"""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# The repo Sloth Tune itself is in: its docs and its Java library are here.
TOOL_REPO = os.path.dirname(os.path.dirname(HERE))
# The repo the robots are in: the same one, unless SLOTHTUNE_ROBOT_REPO says otherwise.
ROBOTS = os.path.abspath(os.environ.get("SLOTHTUNE_ROBOT_REPO") or TOOL_REPO)

HAVE_ROBOTS = all(os.path.isdir(os.path.join(ROBOTS, d)) for d in ("Peashooter", "Black team", "Examples"))
WHY = "reads the team's real robots: run it in the robot repo, or set SLOTHTUNE_ROBOT_REPO to a checkout of it"

# For tests that read the real robots' files: skipped, saying why, where there are no robots.
needs_robots = unittest.skipUnless(HAVE_ROBOTS, WHY)


def skip_module_without_robots():
    """For a test module that loads a robot as it is imported."""
    if not HAVE_ROBOTS:
        raise unittest.SkipTest(WHY)
