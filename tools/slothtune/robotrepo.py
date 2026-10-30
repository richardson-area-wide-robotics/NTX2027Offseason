"""Where the robot projects are.

In the team's robot repo, Sloth Tune lives in tools/slothtune and the robots (Peashooter, Black team,
Examples) sit beside tools/. In Sloth Tune's own repo there are no robots: set SLOTHTUNE_ROBOT_REPO to a
checkout of the robot repo and the tool, and its tests of the real robots, read the robots from there.
The robots are in the team repo, NTX2027Offseason, on its StuartTesting branch.
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


def none_found(robots=None):
    """What the GUI and the command line say when there are no robot projects where they look
    (robots, else ROBOTS), and how to fix it: run from the team repo, or point
    SLOTHTUNE_ROBOT_REPO at a checkout of it."""
    robots = robots or ROBOTS
    where = (f"SLOTHTUNE_ROBOT_REPO is {robots}, and there are no robot projects there"
             if os.environ.get("SLOTHTUNE_ROBOT_REPO") else f"No robot projects found in {robots}")
    return (f"{where} (a robot project is a folder with src/main/deploy/swerve). The robots are in the team "
            "repo, NTX2027Offseason, on its StuartTesting branch. Run Sloth Tune from there, where nothing "
            "needs setting, or point this copy at a checkout of it: "
            'setx SLOTHTUNE_ROBOT_REPO "C:\\path\\to\\NTX2027Offseason", then open a new terminal and start '
            "it again.")
