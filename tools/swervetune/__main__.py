"""Lets ``py -3.12 tools/swervetune ...`` run the tool from anywhere in the repo."""

import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from swervetune.cli import main
else:
    from .cli import main

sys.exit(main())
