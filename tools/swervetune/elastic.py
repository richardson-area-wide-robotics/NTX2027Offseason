"""An Elastic dashboard layout for the drive team: which battery is in, the battery, robot health.

Elastic is the dashboard the Driver Station laptop runs. This layout puts the three things the drive
team needs at the cart on one tab:

* **Battery** - the drop-down the robot asks them to pick after every swap (``BatteryPicker``);
* **Battery check** - one line with the verdict: "Battery 7: 12.84 V at rest, charged · next: 3",
  with the grade when it isn't good ("practice only", "RETIRE it") from the laptop's last sent grades. (The
  Driver Station already shows the voltage now, so there is no second voltage widget.)
* **Robot Health** - the robot's alerts (``DashboardAlerts``). Red means broken now: fix it before
  queuing. Yellow happened or needs watching, and stays with its count until the code restarts.

Load it in Elastic with File > Open Layout, picking ``tools/swervetune/elastic/drive-team-layout.json``.
Widget types and properties are Elastic 2026's (checked against its v2026.1.2 source): a
"ComboBox Chooser" reads a String Chooser's ``options``, ``selected``, ``active`` and ``default``;
"Alerts" reads an Alert group's ``errors``, ``warnings`` and ``infos``.
"""

from __future__ import annotations

import json
import os

from . import contract as C

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT_FILE = os.path.join(HERE, "elastic", "drive-team-layout.json")
HEALTH_GROUP = "Robot Health"  # DashboardAlerts.GROUP
PERIOD = 0.06


def _w(title, x, y, w, h, kind, **props):
    return {"title": title, "x": float(x), "y": float(y), "width": float(w), "height": float(h), "type": kind,
            "properties": dict(props, period=PERIOD)}


def layout():
    return {"version": 1.0, "grid_size": 128, "tabs": [{"name": "Drive team", "grid_layout": {"layouts": [], "containers": [
        _w("Battery: pick its number", 0, 0, 256, 128, "ComboBox Chooser", topic=C.BATTERY_CHOOSER.rstrip("/"),
           sort_options=False),
        _w("Battery check", 256, 0, 384, 128, "Text Display", topic=C.BATTERY_CHECK, show_submit_button=False),
        _w("Robot Health: red = fix before queuing", 0, 128, 640, 384, "Alerts",
           topic="/SmartDashboard/" + HEALTH_GROUP),
    ]}}]}


def text():
    return json.dumps(layout(), indent=2) + "\n"


def write(path=LAYOUT_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text())
    return path
