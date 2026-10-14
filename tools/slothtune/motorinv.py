"""What each motor and controller is: as the code says, as the robot reports, and as measured.

Three sources, because none is enough alone:

* **The code** creates each controller (YAGSL's module ``type``, or ``new SparkMax``/``new
  SparkFlex`` in a subsystem) and says which motor it drives (the YAGSL type, the motor guard's
  ``watch`` call, or ``slothtune.json``'s motor inventory).
* **The robot** knows which controller is really on each CAN ID: every SPARK reports whether it is
  a MAX or a Flex, and its firmware. A controller created as the wrong one is flagged at boot.
* **A measurement** knows the motor: a floor or blocks ``drive_ff`` gives the drive motors' speed
  per volt, which tells a NEO from a Vortex from a NEO 550 (but not a NEO V1.1 from a NEO 2.0).

The motor inventory in ``slothtune.json`` is the manual setting: what a person says each motor
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


NEO550_ONLY_RPM = 7200


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


_SUFFIX = {"vortex": "vortex", "neo550": "neo550", "neo": "neo"}


def yagsl_type(controller, family):
    """``("SPARK Flex", "vortex")`` -> ``sparkflex_vortex``: the type YAGSL's module files take."""
    prefix, suffix = YAGSL_PREFIX.get(controller), _SUFFIX.get(family)
    return f"{prefix}_{suffix}" if prefix and suffix else None


def swerve_type_fixes(project, rows, inv, measured=None):
    """The YAGSL type every module file should have for its drive and steer motors, when any differs.

    The controller is the one the robot reports, else the one the code creates; the motor is what a
    drive_ff measured, then what only a NEO 550 can do (turn past 7200 rpm), then the motor
    inventory, else what the files already say. Each finding carries ``edits`` for every module file
    that differs, so one save fixes all four.
    """
    F = []
    for key, part, label in (("drive", "drive", "drive"), ("steer", "angle", "steering")):
        mine = [r for r in rows if r["key"] == key]
        if not mine:
            continue
        ctl = next((r["controller"] for r in mine if r["controller"]), None) or mine[0]["code_controller"]
        reported = any(r["controller"] for r in mine)
        current = [yagsl_motor(r.get("model") or "") for r in mine]
        if key == "drive" and measured and _family(measured["label"]):
            fam, because = _family(measured["label"]), f"the latest drive_ff measured {measured['label']}s"
            caveat = " If you doubt the measurement, run drive_ff on blocks again first."
        elif any(r["measured"] == "NEO 550" for r in mine):
            fam, because, caveat = "neo550", "a motor turned faster than only a NEO 550 can", ""
        elif inv.get(key):
            fam, because = _family(inv[key]), f"the motor inventory says {inv[key]}"
            caveat = " If the inventory is what's wrong, change it below instead."
        else:
            fam = next((_family(c) for c in current if c), None)
            because, caveat = "the motor stays the one the files name", ""
        want = yagsl_type(ctl, fam)
        if not want:
            continue
        edits = []
        for n in project.module_names():
            cur = ((project.module(n) or {}).get(part) or {}).get("type")
            if cur != want:
                edits.append({"file": f"modules/{n}.json", "path": [part, "type"], "value": want})
        if not edits:
            continue
        olds = sorted({str(((project.module(n) or {}).get(part) or {}).get("type")) for n in project.module_names()} - {want})
        F.append({"level": "warn", "title": f"Set the swerve {label} motors' YAGSL type to {want}",
                  "why": (f"The files say {', '.join(olds)}; {'the robot reports' if reported else 'the code creates'} "
                          f"a {ctl}, and {because}. YAGSL works out free speed, the feedforward and the "
                          f"simulation from this type. Fixing it changes {len(edits)} module file"
                          f"{'' if len(edits) == 1 else 's'}; redeploy afterwards.{caveat}"),
                  "edits": edits, "learn": "motor_inventory"})
    return F


def table(project, live_rows=None, measured=None):
    """One row per controller the code creates: ``{"rows", "findings"}``.

    ``live_rows`` are the robot's motors (``RobotLink.motors()``), ``measured`` the drive motors'
    identity from the latest drive_ff (``advisor.motor_identity_findings``).
    """
    inv = ((project.data.get("slothtune.json") or {}).get("motors") or {})
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
            motor, source = manual, "slothtune.json"
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
        row = {"name": name, "can_id": d["can_id"], "code_controller": code, "controller": says, "model": d["model"],
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
                             f"inventory. Make {d['source']} and slothtune.json agree."})
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
        # Only a NEO 550 turns faster than about 7000 rpm (NEO 5676, Vortex 6784 free): a reading
        # above that proves one, whatever the code says.
        rpm = abs((live.get(name) or {}).get("rpm") or 0)
        if rpm > NEO550_ONLY_RPM and fam and fam != "neo550":
            row["status"] = "bad"
            row["measured"] = "NEO 550"
            F.append({"level": "error", "title": f"{name} turns at {rpm:.0f} rpm: it must be a NEO 550, not a {motor}",
                      "why": "A NEO tops out at 5676 rpm and a Vortex at 6784; only a NEO 550 goes faster. Set it "
                             "in the inventory (and the code's watch(..., MotorKind.NEO_550)), so the motor guard "
                             "uses the right heat model and limits."})
        if not motor:
            row["status"] = "unknown"
        rows.append(row)
    if measured and any(r["status"] == "bad" and r["measured"] for r in rows):
        F.append({"level": "error",
                  "title": f"The drive motors measure as {measured['label']}s ({measured['rpm_per_volt']:.0f} rpm per volt)",
                  "why": "The latest drive_ff disagrees with the configured drive motor; set the inventory "
                         "and the YAGSL type to what is really fitted."})
    F.extend(swerve_type_fixes(project, rows, inv, measured))
    for (level, title, why), names in old_firmware.items():
        who = ", ".join(names) if len(names) <= 3 else f"{len(names)} controllers"
        F.append({"level": level, "title": f"{who}: {title}", "why": why})
    unknown = [r["name"] for r in rows if r["status"] == "unknown"]
    if unknown:
        F.append({"level": "info", "title": f"Motor not named: {', '.join(unknown)}",
                  "why": "Pick what each one is below, so the motor guard uses the right limits and heat model."})
    return {"rows": rows, "findings": F, "choices": list(CHOICES), "inventory": inv}
