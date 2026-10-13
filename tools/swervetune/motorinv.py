"""What each motor and controller is: as the code says, as the robot reports, and as measured.

Three sources, because none is enough alone:

* **The code** creates each controller (YAGSL's module ``type``, or ``new SparkMax``/``new
  SparkFlex`` in a subsystem) and says which motor it drives (the YAGSL type, the motor guard's
  ``watch`` call, or ``swervetune.json``'s motor inventory).
* **The robot** knows which controller is really on each CAN ID: every SPARK reports whether it is
  a MAX or a Flex, and its firmware. A controller created as the wrong one is flagged at boot.
* **A measurement** knows the motor: a floor or blocks ``drive_ff`` gives the drive motors' speed
  per volt, which tells a NEO from a Vortex from a NEO 550 (but not a NEO V1.1 from a NEO 2.0).

The motor inventory in ``swervetune.json`` is the manual setting: what a person says each motor
is, by ``drive``, ``steer`` or a motor's full name. The Motors tab writes it.
"""

from __future__ import annotations

import re

from . import revspecs, wiring

CHOICES = ("NEO V1.1", "NEO 2.0", "NEO Vortex", "NEO 550")
JAVA_CLASS = {"SPARK MAX": "SparkMax", "SPARK Flex": "SparkFlex"}
YAGSL_PREFIX = {"SPARK MAX": "sparkmax", "SPARK Flex": "sparkflex"}
YAGSL_MOTOR = {"neo": "NEO", "neo550": "NEO 550", "vortex": "NEO Vortex", "krakenx60": "Kraken X60",
               "falcon500": "Falcon 500"}


def code_controller(model):
    """``sparkflex_vortex`` or ``SparkFlex`` -> ``SPARK Flex``; ``sparkmax_*`` -> ``SPARK MAX``."""
    m = (model or "").lower()
    if m.startswith("sparkflex"):
        return "SPARK Flex"
    if m.startswith("sparkmax"):
        return "SPARK MAX"
    return model or ""


def yagsl_motor(model):
    m = (model or "").lower()
    return YAGSL_MOTOR.get(m.split("_", 1)[1]) if "_" in m else None


def inventory_key(name):
    """Which inventory entry names this motor: ``drive``/``steer`` for swerve motors, else itself."""
    if name.endswith(" drive"):
        return "drive"
    if name.endswith(" steer"):
        return "steer"
    return name


KIND_LABEL = {"NEO_V1_1": "NEO V1.1", "NEO_2_0": "NEO 2.0", "VORTEX": "NEO Vortex", "NEO_550": "NEO 550",
              "NEO_UNKNOWN": "NEO (V1.1 or 2.0?)"}


def code_kinds(project):
    """The motor each subsystem tells the motor guard it drives: ``watch("Name", motor, MotorKind.X)``."""
    out = {}
    for src in project.java.values():
        for name, kind in re.findall(r'\.watch\(\s*"([^"]+)"\s*,\s*\w+\s*,\s*MotorKind\.(\w+)', src):
            out[name] = KIND_LABEL.get(kind, kind)
    return out


def _family(label):
    l = (label or "").lower()
    return "vortex" if "vortex" in l or "flex" in l else "neo550" if "550" in l else "neo" if "neo" in l else None


def table(project, live_rows=None, measured=None):
    """One row per controller the code creates: ``{"rows", "findings"}``.

    ``live_rows`` are the robot's motors (``RobotLink.motors()``), ``measured`` the drive motors'
    identity from the latest drive_ff (``advisor.motor_identity_findings``).
    """
    inv = ((project.data.get("swervetune.json") or {}).get("motors") or {})
    coded = code_kinds(project)
    live = {r.get("name"): r for r in (live_rows or [])}
    rows, F = [], []
    old_firmware = {}
    for d in wiring.discover(project):
        if d["kind"] != "controller":
            continue
        name, key = d["name"], inventory_key(d["name"])
        code = code_controller(d["model"])
        says = (live.get(name) or {}).get("controller") or ""
        yag = yagsl_motor(d["model"])
        manual = inv.get(name) or (inv.get(key) if key != name else None)
        if manual:
            motor, source = manual, "swervetune.json"
        elif yag:
            motor, source = yag, "YAGSL type"
        elif name in coded:
            motor, source = coded[name], f"{d['source']} watch()"
        elif (live.get(name) or {}).get("kind"):
            motor, source = live[name]["kind"], "the robot's motor guard"
        elif code == "SPARK Flex":
            motor, source = "NEO Vortex", "assumed from the SPARK Flex"
        else:
            motor, source = "", "not said anywhere"
        row = {"name": name, "can_id": d["can_id"], "code_controller": code, "controller": says,
               "firmware": (live.get(name) or {}).get("firmware") or "", "motor": motor, "motor_source": source,
               "key": key, "file": d["source"], "status": "ok", "measured": None}
        if says and code and says != code:
            row["status"] = "bad"
            F.append({"level": "error", "title": f"{name} (CAN {d['can_id']}) is a {says}, but the code creates a {code}",
                      "why": (f"Fix it in {d['source']}: the YAGSL type starts {YAGSL_PREFIX.get(says, says)}_"
                              if key != name else
                              f"Fix it in {d['source']}: new {JAVA_CLASS.get(code, code)}(...) becomes "
                              f"new {JAVA_CLASS.get(says, says)}(...)") + "."})
        if yag and manual and _family(yag) != _family(manual):
            row["status"] = "bad"
            F.append({"level": "warn", "title": f"{name}: YAGSL models a {yag}, the motor inventory says {manual}",
                      "why": f"YAGSL computes free speed and simulation from its type; the motor guard uses the "
                             f"inventory. Make {d['source']} and swervetune.json agree."})
        fw = revspecs.firmware_finding(says or code, row["firmware"])
        if fw:
            old_firmware.setdefault(fw, []).append(name)
        fam = _family(motor)
        ctl = says or code
        if fam == "vortex" and ctl == "SPARK MAX":
            F.append({"level": "info", "title": f"{name}: a Vortex on a SPARK MAX",
                      "why": "Fine only with REV's Solo Adapter; otherwise this should be a SPARK Flex."})
        if key == "drive" and measured and _family(measured["label"]) != fam and fam:
            row["measured"] = measured["label"]
            row["status"] = "bad"
        elif key == "drive" and measured:
            row["measured"] = measured["label"]
        if not motor:
            row["status"] = "unknown"
        rows.append(row)
    if measured and any(r["status"] == "bad" and r["measured"] for r in rows):
        F.append({"level": "error",
                  "title": f"The drive motors measure as {measured['label']}s ({measured['rpm_per_volt']:.0f} rpm per volt)",
                  "why": "The latest drive_ff disagrees with the configured drive motor; set the inventory "
                         "and the YAGSL type to what is really fitted."})
    for (level, title, why), names in old_firmware.items():
        who = ", ".join(names) if len(names) <= 3 else f"{len(names)} controllers"
        F.append({"level": level, "title": f"{who}: {title}", "why": why})
    unknown = [r["name"] for r in rows if r["status"] == "unknown"]
    if unknown:
        F.append({"level": "info", "title": f"Motor not named: {', '.join(unknown)}",
                  "why": "Pick what each one is below, so the motor guard uses the right limits and heat model."})
    return {"rows": rows, "findings": F, "choices": list(CHOICES), "inventory": inv}
