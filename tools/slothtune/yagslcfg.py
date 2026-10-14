"""Reads, checks and edits a robot project's YAGSL configuration.

Three jobs:

* **load** a project: YAGSL's JSON, ``slothtune.json``, PathPlanner's settings, the vendordep
  versions, and the few things only the Java says (the max speed passed to YAGSL, CAN IDs).
* **lint** it: every finding says what is wrong, why it matters on the robot, and the exact edit.
* **edit** it surgically: only the value being changed is rewritten, so a student's git diff
  shows one changed line, not a reformatted file.

Physics here uses datasheet motor constants (the same ones WPILib's DCMotor uses) and is meant for
sanity checks: free speed, the current at which a wheel breaks traction, nominal kV.
"""

from __future__ import annotations

import difflib
import glob
import json
import math
import os
import re

from . import contract as C
from .plant import MOTORS
from . import revspecs
from . import units as U

G = 9.81
PP_DEFAULT_MASS = 74.088  # what a new PathPlanner project starts with
PP_DEFAULT_MOI = 6.883

# YAGSL 2026.4.x JSON schema. YAGSL 2026.8+ rebuilt on YAMS with a different schema whose loader
# ignores unknown keys - an old file loads without error and silently drops renamed fields.
YAGSL_SCHEMA_MAX = (2026, 4, 99)


def motor_kind(yagsl_type):
    t = (yagsl_type or "").lower()
    if "neo550" in t or "neo_550" in t:
        return "neo550"
    if "vortex" in t:
        return "vortex"
    if "kraken" in t:
        return "krakenx60"
    if "falcon" in t or "talonfx" in t:
        return "falcon500"
    if "neo" in t or t in ("sparkmax", "sparkmax_brushless"):
        return "neo"
    return None


def free_speed_mps(kind, gear, wheel_d_in):
    rpm = MOTORS[kind][3]
    return rpm / 60.0 / gear * math.pi * wheel_d_in * 0.0254


def traction_current(kind, gear, wheel_d_in, mass_kg, mu):
    """Per-motor current at which one wheel's push equals what the carpet can hold."""
    stall_t, stall_i, free_i, _ = MOTORS[kind]
    kt = stall_t / stall_i
    r = wheel_d_in * 0.0254 / 2
    force = mu * mass_kg * G / 4
    return force * r / gear / kt + free_i


def wheel_force(kind, gear, wheel_d_in, amps):
    stall_t, stall_i, free_i, _ = MOTORS[kind]
    return max(0.0, amps - free_i) * stall_t / stall_i * gear / (wheel_d_in * 0.0254 / 2)


# ---------------------------------------------------------------------------- surgical JSON edits


class _Spans:
    """Finds where each value sits in a JSON text, by path, so it can be replaced in place."""

    def __init__(self, text):
        self.s = text
        self.i = 0
        self.spans = {}

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n":
            self.i += 1

    def value(self, path):
        self.ws()
        start = self.i
        c = self.s[self.i]
        if c == "{":
            self.i += 1
            self.ws()
            if self.s[self.i] == "}":
                self.i += 1
            else:
                while True:
                    self.ws()
                    key = self.string()
                    self.ws()
                    assert self.s[self.i] == ":"
                    self.i += 1
                    self.value(path + (key,))
                    self.ws()
                    if self.s[self.i] == ",":
                        self.i += 1
                        continue
                    assert self.s[self.i] == "}"
                    self.i += 1
                    break
        elif c == "[":
            self.i += 1
            self.ws()
            if self.s[self.i] == "]":
                self.i += 1
            else:
                k = 0
                while True:
                    self.value(path + (k,))
                    k += 1
                    self.ws()
                    if self.s[self.i] == ",":
                        self.i += 1
                        continue
                    assert self.s[self.i] == "]"
                    self.i += 1
                    break
        elif c == '"':
            self.string()
        else:
            while self.i < len(self.s) and self.s[self.i] not in ",}] \t\r\n":
                self.i += 1
        self.spans[path] = (start, self.i)

    def string(self):
        assert self.s[self.i] == '"'
        j = self.i + 1
        while self.s[j] != '"':
            j += 2 if self.s[j] == "\\" else 1
        out = json.loads(self.s[self.i:j + 1])
        self.i = j + 1
        return out


def _fmt(value):
    """JSON text for a value, numbers kept short: 263.0 -> 263, 0.050600 -> 0.0506."""
    if isinstance(value, float) and not isinstance(value, bool):
        return f"{round(value, 6):.6g}"
    return json.dumps(value)


def json_set(text, path, value):
    """Returns ``text`` with the value at ``path`` replaced, everything else byte-identical.

    A key that does not exist yet is inserted into the deepest object that does, so adding the
    first measured feedforward to an empty ``"driveFeedforward": {}`` changes only those lines.
    """
    path = tuple(path)
    sp = _Spans(text)
    sp.value(())
    if path in sp.spans:
        a, b = sp.spans[path]
        return text[:a] + _fmt(value) + text[b:]
    # Deepest existing ancestor that is an object.
    depth = len(path) - 1
    while depth > 0 and path[:depth] not in sp.spans:
        depth -= 1
    parent = path[:depth]
    a, b = sp.spans[parent]
    if text[a] != "{":
        raise ValueError(f"cannot add {path}: {parent} is not an object")
    missing = path[depth:]
    node = value
    for k in reversed(missing[1:]):
        node = {k: node}
    member_value = node
    inner = text[a + 1:b - 1]
    rendered = json.dumps(member_value) if not isinstance(member_value, float) else _fmt(member_value)
    member = f'"{missing[0]}": {rendered}'
    if inner.strip() == "":
        return text[:a] + "{ " + member + " }" + text[b:]
    # Add after the last existing member, matching how the object is already laid out.
    last_member_end = b - 1
    while text[last_member_end - 1] in " \t\r\n":
        last_member_end -= 1
    if "\n" in inner:
        first_nl = text.index("\n", a)
        indent = ""
        k = first_nl + 1
        while text[k] in " \t":
            indent += text[k]
            k += 1
        return text[:last_member_end] + ",\n" + indent + member + text[last_member_end:]
    return text[:last_member_end] + ", " + member + text[last_member_end:]


def diff(old, new, name):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        fromfile=f"a/{name}", tofile=f"b/{name}"))


# ---------------------------------------------------------------------------- loading


class Project:
    """One robot project folder, e.g. ``Peashooter``."""

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.name = os.path.basename(self.path.rstrip("\\/"))
        self.swerve = os.path.join(self.path, "src", "main", "deploy", "swerve")
        if not os.path.isdir(self.swerve):
            raise FileNotFoundError(f"{self.swerve} not found: is {path} a robot project?")
        self.files = {}
        self.data = {}
        self._load("swervedrive.json")
        self._load("controllerproperties.json")
        self._load("modules/physicalproperties.json")
        self._load("modules/pidfproperties.json")
        self.module_files = list(self.data["swervedrive.json"].get("modules", []))
        for mf in self.module_files:
            self._load("modules/" + mf)
        if os.path.exists(os.path.join(self.swerve, "slothtune.json")):
            self._load("slothtune.json")
        else:
            self.data["slothtune.json"] = {}
        self.pathplanner = self._read_json(os.path.join(self.path, "src", "main", "deploy",
                                                        "pathplanner", "settings.json"))
        self.java = {}
        for f in glob.glob(os.path.join(self.path, "src", "main", "java", "**", "*.java"),
                           recursive=True):
            with open(f, encoding="utf-8", errors="replace") as fh:
                self.java[os.path.relpath(f, self.path)] = fh.read()
        self.vendordeps = {}
        for f in glob.glob(os.path.join(self.path, "vendordeps", "*.json")):
            d = self._read_json(f) or {}
            self.vendordeps[d.get("name", os.path.basename(f))] = d.get("version", "?")
        prefs = self._read_json(os.path.join(self.path, ".wpilib", "wpilib_preferences.json")) or {}
        self.team = prefs.get("teamNumber")
        self.year = prefs.get("projectYear")

    @staticmethod
    def _read_json(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _load(self, rel):
        full = os.path.join(self.swerve, rel)
        with open(full, encoding="utf-8") as fh:
            text = fh.read()
        self.files[rel] = text
        self.data[rel] = json.loads(text)

    # ------------------------------------------------------------------ convenience views
    @property
    def phys(self):
        return self.data["modules/physicalproperties.json"]

    @property
    def pidf(self):
        return self.data["modules/pidfproperties.json"]

    @property
    def tune(self):
        return self.data["slothtune.json"]

    def module(self, name):
        return self.data["modules/" + (name if name.endswith(".json") else name + ".json")]

    def module_names(self):
        return [m[:-5] for m in self.module_files]

    def drive_kind(self):
        return motor_kind(self.module(self.module_names()[0])["drive"]["type"])

    def steer_kind(self):
        return motor_kind(self.module(self.module_names()[0])["angle"]["type"])

    def drive_gear(self):
        return float(self.phys["conversionFactors"]["drive"]["gearRatio"])

    def steer_gear(self):
        return float(self.phys["conversionFactors"]["angle"]["gearRatio"])

    def wheel_d_in(self):
        return float(self.phys["conversionFactors"]["drive"]["diameter"])

    def max_module_speed(self):
        kind = self.drive_kind()
        return free_speed_mps(kind, self.drive_gear(), self.wheel_d_in()) if kind else float("nan")

    def offsets(self):
        return {n: float(self.module(n).get("absoluteEncoderOffset", 0)) for n in self.module_names()}

    def mass(self):
        """Robot mass and where it came from. Bumpers and battery included."""
        if self.tune.get("robotMassKg"):
            return float(self.tune["robotMassKg"]), "slothtune.json"
        pp = self.pathplanner or {}
        if pp.get("robotMass") and abs(pp["robotMass"] - PP_DEFAULT_MASS) > 0.5:
            return float(pp["robotMass"]), "PathPlanner settings"
        dm = self._design_mass()
        if dm:
            return dm, "assumed: the drivetrain design's, until the robot is weighed"
        return 55.0, "assumed (set robotMassKg in slothtune.json)"

    def _design_mass(self):
        """A saved drivetrain design's mass, when its link set it (not the calculator's default)."""
        from . import designlinks
        for v in ((self.data.get("slothtune.json") or {}).get("designs") or {}).values():
            try:
                d = designlinks.parse((v or {}).get("url", ""))
            except Exception:  # noqa: BLE001 - a link that no longer reads gives no mass
                continue
            if d.get("kind") == "drivetrain" and d.get("mass_kg") and "mass_kg" not in (d.get("assumed") or []):
                return round(d["mass_kg"], 1)
        return None

    def moi(self):
        """Robot moment of inertia about its center, kg m^2, and where it came from.

        Until it is measured, a uniform slab the size of the frame plus bumpers: m (L^2 + W^2) / 12.
        Real robots carry weight near the edges (bumpers, battery), so expect 10-30% more.
        """
        if self.tune.get("robotMoiKgM2"):
            return float(self.tune["robotMoiKgM2"]), "slothtune.json"
        pp = self.pathplanner or {}
        if pp.get("robotMOI") and abs(pp["robotMOI"] - PP_DEFAULT_MOI) > 0.001:
            return float(pp["robotMOI"]), "PathPlanner settings"
        mods = [self.module(n) for n in self.module_names()]
        xs = [abs(m["location"]["front"]) * 0.0254 for m in mods]
        ys = [abs(m["location"]["left"]) * 0.0254 for m in mods]
        bumper = 0.12  # module center to bumper face, each side
        length, width = 2 * (max(xs) + bumper), 2 * (max(ys) + bumper)
        mass, _ = self.mass()
        return mass * (length ** 2 + width ** 2) / 12, (
            f"estimated as a {U.inches(length):.0f} x {U.inches(width):.0f} in slab (set robotMoiKgM2 in slothtune.json)")

    def create_swerve_max_speed(self):
        """The maxSpeed literal passed to SwerveParser.createSwerveDrive, resolved if a constant."""
        for rel, src in self.java.items():
            m = re.search(r"createSwerveDrive\(\s*([^,\)]+)", src)
            if not m:
                continue
            arg = m.group(1).strip()
            try:
                return float(arg.rstrip("dDfF")), rel, arg
            except ValueError:
                pass
            c = re.search(r"\b" + re.escape(arg) + r"\s*=\s*([0-9.]+)", src)
            if c:
                return float(c.group(1)), rel, arg
            return None, rel, arg
        return None, None, None

    def can_ids(self):
        ids = {}
        for n in self.module_names():
            m = self.module(n)
            for part in ("drive", "angle"):
                ids.setdefault(int(m[part]["id"]), []).append(f"{n} {part}")
            enc = m.get("encoder", {})
            if enc.get("type") not in (None, "attached", "none") and "id" in enc:
                ids.setdefault(int(enc["id"]), []).append(f"{n} encoder")
        # A constant (Black team's Intake: new SparkMax(CAN_ID, ...)) is looked up in its own file
        # first, then in any file that defines that name only once.
        per_file = {rel: dict(re.findall(r"\b([A-Z_][A-Z0-9_]*)\s*=\s*(\d+)\s*;", src)) for rel, src in self.java.items()}
        seen = {}
        for consts in per_file.values():
            for k, v in consts.items():
                seen.setdefault(k, set()).add(v)
        anywhere = {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}
        for rel, src in self.java.items():
            for mm in re.finditer(r"new\s+(SparkMax|SparkFlex|TalonFX|TalonFXS|CANcoder)\s*\(\s*([\w.]+)", src):
                arg = mm.group(2).split(".")[-1]
                cid = arg if arg.isdigit() else per_file[rel].get(arg) or anywhere.get(arg)
                if cid is not None:
                    ids.setdefault(int(cid), []).append(f"{os.path.basename(rel)} {mm.group(1)}")
        return ids

    # ------------------------------------------------------------------ editing
    def writable(self, rel):
        """Whether a save may write ``rel``: one of the swerve config files this project loaded, or
        slothtune.json. Never a path that climbs out ("../"), an absolute path, or anything that
        isn't JSON - a save must not be able to overwrite the robot's code."""
        r = str(rel or "").replace("\\", "/")
        if not r.endswith(".json") or r.startswith("/") or ":" in r or ".." in r.split("/"):
            return False
        return r in self.files or r == "slothtune.json"

    def preview(self, edits):
        """``edits``: list of (file, path, value). Returns {file: (old, new)} for changed files."""
        out = {}
        for rel, path, value in edits:
            if not self.writable(rel):
                raise ValueError(f"{rel!r} is not one of this robot's config files")
            old = out[rel][1] if rel in out else self.files.get(rel, "{}\n")
            new = json_set(old, path, value)
            out[rel] = (self.files.get(rel, "{}\n"), new)
        return {k: v for k, v in out.items() if v[0] != v[1]}

    def apply(self, edits):
        """Writes the edits. Returns the unified diff of everything written."""
        changes = self.preview(edits)
        text = []
        for rel, (old, new) in changes.items():
            with open(os.path.join(self.swerve, rel), "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
            self.files[rel] = new
            self.data[rel] = json.loads(new)
            text.append(diff(old, new, rel))
        return "".join(text)


# ---------------------------------------------------------------------------- gains <-> files


def edits_for_gains(project, gains):
    """Maps live gain names to the JSON fields that keep them. Unknown names are ignored.

    A pod's own gains go to slothtune.json's "podGains", only where they differ from the shared
    ones (pidfproperties.json): a pod running the shared gains needs no entry, and one it already
    has is set back to the shared values so it no longer overrides them."""
    e = []
    pid_map = {"kP": "p", "kI": "i", "kD": "d", "IZone": "iz"}
    pidf = (project.data.get("modules/pidfproperties.json") or {}) if project else {}
    pods_in_file = ((project.data.get("slothtune.json") or {}).get("podGains") or {}) if project else {}

    def shared(loop, k):
        if f"{loop}/{k}" in gains:
            return gains[f"{loop}/{k}"]
        return (pidf.get("angle" if loop == "Steer" else "drive") or {}).get(pid_map[k], 0.0)

    for key, value in gains.items():
        parts = key.split("/")
        if parts[0] == "Pod" and len(parts) == 4 and parts[2] in ("Steer", "Drive") and parts[3] in pid_map:
            pod, loop, k = parts[1], parts[2], parts[3]
            has = loop.lower() in (pods_in_file.get(pod) or {})
            differs = abs(float(value) - float(shared(loop, k))) > 1e-12
            if differs or has:
                e.append(("slothtune.json", ("podGains", pod, loop.lower(), pid_map[k]), value))
            continue
        if parts[0] in ("Steer", "Drive") and parts[1] in pid_map:
            e.append(("modules/pidfproperties.json",
                      ("angle" if parts[0] == "Steer" else "drive", pid_map[parts[1]]), value))
        elif key == "Steer/RampS":
            e.append(("modules/physicalproperties.json", ("rampRate", "angle"), value))
        elif key == "Drive/RampS":
            e.append(("modules/physicalproperties.json", ("rampRate", "drive"), value))
        elif key == "Drive/VelPeriodMs":
            e.append(("slothtune.json", ("driveVelocityFilter", "periodMs"), int(value)))
        elif key == "Drive/VelDepth":
            e.append(("slothtune.json", ("driveVelocityFilter", "depth"), int(value)))
        elif parts[0] == "FF" and len(parts) == 3:
            e.append(("slothtune.json", ("driveFeedforward", parts[1], parts[2]), value))
        elif key == "Chassis/AngVelCoeff":
            on = value != 0
            e += [("slothtune.json", ("angularVelocityCompensation", "coefficient"), value),
                  ("slothtune.json", ("angularVelocityCompensation", "teleop"), on),
                  ("slothtune.json", ("angularVelocityCompensation", "auto"), on)]
        elif key == "EncoderSync/Enabled":
            e.append(("slothtune.json", ("encoderAutoSync", "enabled"), bool(value)))
        elif key == "EncoderSync/DeadbandDeg":
            e.append(("slothtune.json", ("encoderAutoSync", "deadbandDeg"), value))
    return e


# ---------------------------------------------------------------------------- lint


def _f(level, fid, title, why, fix=None, **evidence):
    d = {"level": level, "id": fid, "title": title, "why": why}
    if fix:
        d["fix"] = fix
    if evidence:
        d["evidence"] = evidence
    return d


def lint(project):
    p = project
    F = []
    names = p.module_names()
    mods = {n: p.module(n) for n in names}

    # ---- module geometry and naming
    for n, m in mods.items():
        loc = m.get("location", {})
        front, left = loc.get("front", 0), loc.get("left", 0)
        nl = n.lower()
        want_front = 1 if "front" in nl else -1 if ("back" in nl or "rear" in nl) else 0
        want_left = 1 if "left" in nl else -1 if "right" in nl else 0
        if (want_front and front * want_front <= 0) or (want_left and left * want_left <= 0):
            F.append(_f("error", "location_sign", f"{n}: location does not match its name",
                        f"{n} is at front={front}, left={left}. +front is toward the front of the "
                        "robot and +left toward its left. A swapped sign makes the kinematics send "
                        "this corner the wrong speed whenever the robot turns."))

    # ---- inversions
    drive_inv = {n: bool(m.get("inverted", {}).get("drive", False)) for n, m in mods.items()}
    if len(set(drive_inv.values())) > 1:
        majority = max(set(drive_inv.values()), key=list(drive_inv.values()).count)
        odd = [n for n, v in drive_inv.items() if v != majority]
        F.append(_f(
            "warn", "drive_inversion_mixed",
            f"Drive inversion differs on {', '.join(odd)}",
            "Identical modules should all have the same drive inversion. One that differs is the "
            "classic sign of an absolute-encoder offset that is 180 degrees out: the wheel points "
            "backwards, so it was 'fixed' by inverting the motor. It drives, but the module's angle "
            "reads 180 degrees wrong, which confuses odometry and every tool that reads it. Redo "
            "that module's offset with the bevel gear facing the same way as the others, then set "
            "its drive inversion to match the rest.",
            {"kind": "guide", "step": "offsets", "symptom": "wheel_backwards"}, inversions=drive_inv))
    for key in ("absoluteEncoderInverted",):
        vals = {n: bool(m.get(key, False)) for n, m in mods.items()}
        if len(set(vals.values())) > 1:
            F.append(_f("warn", "abs_inversion_mixed", f"{key} differs between modules",
                        "Identical modules read their absolute encoders the same way. A different one "
                        "steers backwards: it turns away from its target and never settles.",
                        evidence_values=vals))
    vals = {n: bool(m.get("inverted", {}).get("angle", False)) for n, m in mods.items()}
    if len(set(vals.values())) > 1:
        F.append(_f("warn", "angle_inversion_mixed", "Steering motor inversion differs between modules",
                    "Identical modules turn their steering motors the same way. A different one fights "
                    "its own encoder and runs away.", evidence_values=vals))

    # ---- offsets
    offs = p.offsets()
    seen = {}
    for n, o in offs.items():
        key = round(o % 360, 1)
        seen.setdefault(key, []).append(n)
    dup = [v for v in seen.values() if len(v) > 1]
    if dup:
        F.append(_f("warn", "offsets_duplicate",
                    f"Modules share an identical offset: {'; '.join(', '.join(d) for d in dup)}",
                    "Two hand-measured offsets agreeing to a tenth of a degree is very unlikely. "
                    "Usually one was copied from the other. Capture fresh offsets with the tool.",
                    {"kind": "guide", "step": "offsets"}, offsets=offs))
    round_ones = [n for n, o in offs.items() if abs(o % 90) < 1e-9]
    steer_ratio = ((p.phys.get("conversionFactors") or {}).get("angle") or {}).get("gearRatio")
    from . import ratios as _R
    if round_ones and len(round_ones) >= 2 and _R.family(steer_ratio) != "maxswerve":
        # (MAXSwerve modules zeroed with REV's Hardware Client sit at whole quarter turns by design.)
        F.append(_f("info", "offsets_round",
                    f"Offsets that are exact multiples of 90: {', '.join(round_ones)}",
                    "Real measured offsets are rarely whole quarter turns. These may be template or "
                    "placeholder values. If the wheels line up perfectly, fine - otherwise capture "
                    "them.", {"kind": "guide", "step": "offsets"}, offsets=offs))

    # ---- ramp rates
    ramp = p.phys.get("rampRate", {})
    if float(ramp.get("angle", 0)) > 0.02:
        F.append(_f(
            "warn", "steer_ramp",
            f"Steering ramp rate is {ramp.get('angle')} s",
            "YAGSL applies the ramp rate to the closed loop as well as open loop, so every steering "
            "correction is slew-limited: pure added lag in a position loop. The current limit "
            "already protects the steering motor. Try 0, live, and compare a steer_step.",
            {"kind": "edit", "file": "modules/physicalproperties.json", "path": ["rampRate", "angle"],
             "value": 0.0}))
    if float(ramp.get("drive", 0)) > 0.1:
        F.append(_f(
            "info", "drive_ramp",
            f"Drive ramp rate is {ramp.get('drive')} s",
            "The ramp slows the velocity loop's corrections too, which PathPlanner sees as lag. The "
            "current limit is what keeps the wheels from slipping. 0.05 s is usually enough.",
            {"kind": "edit", "file": "modules/physicalproperties.json", "path": ["rampRate", "drive"],
             "value": 0.05}))

    # ---- steering feedback
    angle_factor = float(p.phys["conversionFactors"]["angle"].get("factor", 0) or 0)
    attached = all(m.get("encoder", {}).get("type") == "attached" for m in mods.values())
    sync = bool((p.tune.get("encoderAutoSync") or {}).get("enabled"))
    if attached and angle_factor != 360 and not sync:
        F.append(_f(
            "info", "steer_feedback",
            "Steering runs on the motor encoder, set once at boot and never re-checked",
            "With the absolute encoder plugged into the SPARK and the steering factor computed from "
            "the gear ratio, YAGSL closes the steering loop on the NEO 550's own encoder, copied from "
            "the absolute encoder at startup. If that read is bad, or a gear skips, the module points "
            "wrong until the next reboot. Two fixes, test either on blocks: turn on encoderAutoSync "
            "in slothtune.json, or steer on the absolute encoder (factor 360 plus steerFeedback "
            "\"absolute\" - the tool sets both; YAGSL needs both or the offset is applied twice).",
            {"kind": "edit", "file": "slothtune.json", "path": ["encoderAutoSync", "enabled"],
             "value": True}))
    if angle_factor == 360 and (p.tune.get("steerFeedback") or "motor") != "absolute":
        F.append(_f(
            "error", "factor_360_without_absolute",
            "Steering factor is 360 but steerFeedback is not \"absolute\"",
            "With factor 360 YAGSL points the SPARK's PID at the absolute encoder, but it keeps the "
            "offset in software unless useExternalFeedbackSensor() pushes it into the SPARK. The "
            "SPARK then aims for the raw angle and every module points off by its own offset. Set "
            "steerFeedback to \"absolute\" in slothtune.json (the harness then pushes the offsets).",
            {"kind": "edit", "file": "slothtune.json", "path": ["steerFeedback"], "value": "absolute"}))

    # ---- "f" does nothing on a SPARK in YAGSL 2026.4
    for loop in ("drive", "angle"):
        f = float(p.pidf.get(loop, {}).get("f", 0) or 0)
        if f:
            F.append(_f("info", f"{loop}_f_ignored", f"pidfproperties {loop}.f = {f} does nothing",
                        "YAGSL 2026.4 never sends f to a SPARK. The drive feedforward comes from the "
                        "module feedforward (kS, kV, kA), which the tool measures and stores in "
                        "slothtune.json."))

    # ---- gains sanity
    dk = p.drive_kind()
    d_p = float(p.pidf.get("drive", {}).get("p", 0) or 0)
    d_d = float(p.pidf.get("drive", {}).get("d", 0) or 0)
    if dk:
        vmax = p.max_module_speed()
        kv_duty = 1.0 / vmax  # duty per (m/s) the feedforward supplies
        if d_p < 0.05 * kv_duty:
            F.append(_f("info", "drive_p_tiny", f"Drive kP {d_p:g} barely corrects anything",
                        f"At 1 m/s of error it adds {d_p * 100:.2f}% output; the feedforward alone "
                        f"is {kv_duty * 100:.0f}% per m/s. The drive is effectively open loop: fine "
                        "if the feedforward is measured, slow and battery-sensitive if not. Measure "
                        "the feedforward, then tune kP (around 0.04 to start)."))
        if d_p > 2.0 * kv_duty or d_d > 0.05:
            F.append(_f("warn", "drive_p_hot", f"Drive kP {d_p:g}, kD {d_d:g} is very aggressive",
                        f"kP {d_p:g} is {d_p / kv_duty:.1f}x the feedforward's own slope. The speed "
                        f"comes from {revspecs.drive_speed_sensor(dk)[3]}, measured a little late, "
                        "so a gain this large turns every bump and flicker into a voltage kick: the "
                        "drive buzzes and overshoots, and kD on a velocity loop multiplies it. Expect "
                        "twitchy, hot drive motors.",
                        {"kind": "tune", "loop": "drive"}))
    a_p = float(p.pidf.get("angle", {}).get("p", 0) or 0)
    if a_p and a_p < 0.015:
        F.append(_f("info", "steer_p_soft", f"Steering kP {a_p:g} may be soft on carpet",
                    f"Carpet scrub holds a wheel still until kP times the error overcomes it. At kP "
                    f"{a_p:g}, small corrections can stop a few degrees short on the floor, and each "
                    "degree is about 2 in of sideways drift per 10 ft. Measure it: run steer_step "
                    "on the floor.", {"kind": "tune", "loop": "steer"}))

    # ---- current limits and traction
    mass, mass_src = p.mass()
    mu = float(p.phys.get("wheelGripCoefficientOfFriction", 1.1))
    lim = p.phys.get("currentLimit", {})
    d_lim, a_lim = float(lim.get("drive", 40)), float(lim.get("angle", 20))
    if dk:
        slip = traction_current(dk, p.drive_gear(), p.wheel_d_in(), mass, mu)
        rec = 5 * round(0.85 * slip / 5)
        if d_lim > 1.1 * slip:
            assumed = "assumed" in str(mass_src)
            F.append(_f(
                "info" if assumed else "warn", "drive_current_over_traction",
                f"Drive current limit {d_lim:.0f} A may be above where the wheels slip (about {slip:.0f} A)",
                f"An estimate from {U.mass(mass)} ({mass_src}) and a datasheet grip of {mu}: each wheel "
                f"should break loose near {slip:.0f} A. Above that, hard acceleration only spins the "
                "wheels and odometry counts distance the robot never covered. Don't change the limit "
                "from this estimate: the slip test measures it on your carpet and recommends the "
                "number.", {"kind": "tune", "loop": "slip"}))
        elif d_lim < 0.6 * slip:
            F.append(_f("info", "drive_current_low",
                        f"Drive current limit {d_lim:.0f} A leaves acceleration on the table",
                        f"Wheels would grip up to about {slip:.0f} A. Fine if brownouts are the worry."))
    # ---- every module the same motors, offsets in a turn, a ratio REV sells
    for part in ("drive", "angle"):
        types = {n: (m.get(part) or {}).get("type") for n, m in mods.items()}
        if len(set(types.values())) > 1:
            F.append(_f("error", f"modules_mixed_{part}_types",
                        f"The modules' {'drive' if part == 'drive' else 'steering'} motor types differ: "
                        + ", ".join(f"{n} {t}" for n, t in types.items()),
                        "YAGSL builds each module from its own file; a module with another type gets another "
                        "controller and another free speed. Make them match what is fitted (Motors tab)."))
    for n, o in offs.items():
        if not (0 <= o < 360):
            F.append(_f("warn", "offset_out_of_range", f"{n}'s offset is {o:g}°",
                        "An offset is an angle within one turn, 0 to 360. YAGSL wraps it, but a number outside "
                        "that range is usually a typo or a copy from another robot: capture it again.",
                        {"kind": "guide", "step": "offsets"}))
    drive_ratio = ((p.phys.get("conversionFactors") or {}).get("drive") or {}).get("gearRatio")
    if _R.family(steer_ratio) == "maxswerve" and drive_ratio and not _R.candidates(float(drive_ratio), "maxswerve", 0.005):
        F.append(_f("warn", "drive_ratio_not_sold", f"Drive gear ratio {drive_ratio}:1 isn't one REV sells for MAXSwerve",
                    "REV sells " + ", ".join(f"{r:.2f}" for _, r in _R.MAXSWERVE_DRIVE) + ". Count the pinion's "
                    "teeth and set the matching ratio: every distance and speed scales with it."))

    # ---- a velocity setpoint the motor can never reach (Peashooter's shootX asked a Vortex for 9999 rpm)
    from . import designcheck as _DC, revspecs as _RS
    kinds = {"VORTEX": "vortex", "NEO_550": "neo550", "NEO_V1_1": "neo", "NEO_2_0": "neo", "NEO_UNKNOWN": "neo"}
    for fname, src in (p.java or {}).items():
        if "velocityConversionFactor" in src:
            continue  # setpoints in its own units, not motor rpm
        ks = [kinds[k] for k in re.findall(r"MotorKind\.(\w+)", src) if k in kinds]
        if not ks:
            continue
        free = max(_RS.MOTORS[k]["free_rpm"] for k in ks)
        label = _RS.MOTORS[max(ks, key=lambda k: _RS.MOTORS[k]["free_rpm"])]["label"]
        for sp in _DC.velocity_setpoints(src):
            if sp > free:
                F.append(_f("error", "setpoint_unreachable",
                            f"{os.path.basename(fname)} asks for {sp:g} rpm; a {label} tops out at {free} rpm",
                            "The loop runs the motor flat out and never gets there, so it never settles and every "
                            "shot is different. Pick a speed the motor can hold with margin (about 80% of free "
                            "speed), or gear it differently: a ReCalc or AMBcalc link in Config shows what the "
                            "mechanism can reach."))

    # ---- the team's current policy (Stuart, 2026-10): Vortex 80, NEO 1.1 60, NEO 2.0 80, NEO 550 20
    inventory = p.tune.get("motors", {}) if isinstance(p.tune.get("motors"), dict) else {}
    for key, what in (("guard", "the motor guard (heat, stall and failure protection)"),
                      ("enforcePolicy", "the team's current-limit policy")):
        if inventory.get(key) is False:
            F.append(_f("error", f"slothtune_{key}_off", f"slothtune.json turns off {what}",
                        f'"motors": {{"{key}": false}} switches it off on every motor, and nothing on the robot '
                        "says so. Remove it before the robot drives in a match.",
                        {"kind": "edit", "file": "slothtune.json", "path": ["motors", key], "value": True}))
    for part, kind, limit, key in (("drive", dk, d_lim, "drive"), ("steer", p.steer_kind(), a_lim, "angle")):
        mk = C.motor_kind_from_text(inventory.get(part) or {"neo550": "neo550", "vortex": "vortex",
                                                            "neo": "neo"}.get(kind or "", ""))
        if kind not in ("neo550", "vortex", "neo"):
            continue
        label, policy = C.MOTOR_KINDS[mk][0], C.MOTOR_KINDS[mk][1]
        if limit > policy:
            unknown = (" A NEO V1.1 and a NEO 2.0 look identical to the robot; if these are NEO 2.0s"
                       f", say so in slothtune.json (\"motors\": {{\"{part}\": \"NEO 2.0\"}}) and"
                       " the policy is 80 A." if mk == "NEO_UNKNOWN" else "")
            F.append(_f(
                "warn", f"{part}_current_over_policy",
                f"{'Drive' if part == 'drive' else 'Steering'} current limit {limit:.0f} A is over the "
                f"{policy} A policy for a {label}",
                f"The team limits a {label} to {policy} A. The motor guard lowers it at every boot and "
                f"says so; set it here so the code and the robot agree.{unknown}",
                {"kind": "edit", "file": "modules/physicalproperties.json",
                 "path": ["currentLimit", key], "value": policy}))
    if a_lim < 15:
        F.append(_f("info", "steer_current", f"Steering current limit {a_lim:.0f} A",
                    "Below about 15 A a NEO 550 steers sluggishly on carpet."))

    # ---- the max speed handed to YAGSL
    ms, where, literal = p.create_swerve_max_speed()
    vmax = p.max_module_speed()
    if ms is not None and A_finite(vmax):
        if ms > 1.3 * vmax:
            F.append(_f(
                "error", "max_speed_unreal",
                f"{where} gives YAGSL a max speed of {U.speed(ms)} ({ms:g} m/s in the code); the modules "
                f"top out at {U.speed(vmax)}",
                f"YAGSL desaturates to the real module speed, so nothing breaks outright, but "
                f"anything that scales a stick by getMaximumChassisVelocity() asks for {U.speed(ms)}: "
                f"full speed arrives at about {100 * vmax / ms:.0f}% stick, so fine control is gone, "
                "and when translation is saturated the desaturation shrinks rotation with it - the "
                "robot will not turn while driving. Pass the real top speed to createSwerveDrive: "
                f"{vmax * 0.95:.1f}, in the m/s the code takes ({U.speed(vmax * 0.95, 1)}).",
                {"kind": "manual", "file": where,
                 "instruction": f"change createSwerveDrive({literal}, ...) to createSwerveDrive({vmax * 0.95:.1f}, ...)"},
                literal=literal, value=ms, module_free_speed=vmax))
        elif ms < 0.6 * vmax:
            F.append(_f("info", "max_speed_low", f"Max speed {U.speed(ms)} is well under {U.speed(vmax)}",
                        "Deliberate speed limits are fine; just know this one is in effect."))

    # ---- CAN IDs
    for cid, users in sorted(p.can_ids().items()):
        if len(users) > 1:
            F.append(_f("error", "can_duplicate", f"CAN ID {cid} used twice: {', '.join(users)}",
                        "Two devices on one ID answer each other's messages; both misbehave."))

    # ---- PathPlanner agreement (the whole check lives in ppcheck)
    from . import ppcheck

    for f in ppcheck.check(p)["findings"]:
        lvl, title, why, fix = f["level"], f["title"], f["why"], {"kind": "pathplanner"}
        if lvl == "info":
            continue
        if f["kind"] == "names":
            F.append(_f(lvl, "pathplanner_names", title, why, fix))
        elif f["kind"] == "limits":
            F.append(_f(lvl, "pathplanner_limits", title, why, fix))
        elif "default" in title:
            F.append(_f(lvl, "pathplanner_defaults", title, why, fix))
        else:
            F.append(_f(lvl, "pathplanner_mismatch", title, why, fix))

    # ---- library versions and the 2027 road
    yv = p.vendordeps.get("YAGSL", "")
    try:
        parts = tuple(int(x) for x in yv.split(".")[:3])
    except ValueError:
        parts = ()
    if parts and parts > YAGSL_SCHEMA_MAX:
        F.append(_f("error", "yagsl_schema",
                    f"YAGSL {yv} uses a new JSON schema these tools do not read yet",
                    "YAGSL 2026.8 and later build on YAMS with renamed JSON fields, and old files load "
                    "without error while silently dropping the renamed ones. Check every value in the "
                    "YAGSL schema-changes page before trusting a lint result here."))
    imu_cfg = p.data["swervedrive.json"].get("imu") or {}
    imu = imu_cfg.get("type", "")
    if imu.lower() == "canandgyro":
        if imu_cfg.get("id") in (0, None):
            F.append(_f("warn", "canandgyro_id_0", "The Canandgyro is set to CAN ID 0",
                        "A new Canandgyro comes as ID 0, and Redux advise against using 0. Give it its own ID in "
                        "Alchemist (docs/GYRO_CANANDGYRO.md), then put that ID in swervedrive.json's imu.id."))
        if str(imu_cfg.get("canbus") or "").strip():
            F.append(_f("info", "canandgyro_canbus", f"imu.canbus is \"{imu_cfg.get('canbus')}\": YAGSL 2026.4.1 ignores it",
                        "It always opens the Canandgyro on the robot controller's own CAN bus, and the Canandgyro "
                        "can't work on a CANivore (it isn't CAN FD). Wire it to the main bus."))
    if "spi" in imu.lower():
        F.append(_f("info", "imu_spi_2027", f"Gyro is {imu}: there is no SPI on SystemCore",
                    "The 2027 control system has no MXP or SPI port. Plan on its onboard IMU (YAGSL "
                    "2027 type 'systemcore') or a CAN gyro. See docs/MIGRATION_2027.md."))

    order = {"error": 0, "warn": 1, "info": 2}
    F.sort(key=lambda f: order[f["level"]])
    return F


def A_finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def summary(project):
    p = project
    dk, sk = p.drive_kind(), p.steer_kind()
    mass, src = p.mass()
    mu = float(p.phys.get("wheelGripCoefficientOfFriction", 1.1))
    out = {
        "project": p.name, "team": p.team, "modules": p.module_names(),
        "drive_motor": dk, "steer_motor": sk, "drive_gear": p.drive_gear(),
        "steer_gear": p.steer_gear(), "wheel_diameter_in": p.wheel_d_in(),
        "max_module_speed_mps": p.max_module_speed(), "mass_kg": mass, "mass_source": src,
        "offsets": p.offsets(), "pidf": p.pidf, "ramp": p.phys.get("rampRate"),
        "current_limit": p.phys.get("currentLimit"), "vendordeps": p.vendordeps,
        "kv_nominal": 12.0 / p.max_module_speed() if dk else None,
    }
    if dk:
        out["traction_current_a"] = traction_current(dk, p.drive_gear(), p.wheel_d_in(), mass, mu)
    ms = p.create_swerve_max_speed()
    out["create_swerve_max_speed"] = {"value": ms[0], "file": ms[1], "literal": ms[2]}
    return out


def find_projects(repo_root):
    out = []
    for d in sorted(os.listdir(repo_root)):
        if os.path.isdir(os.path.join(repo_root, d, "src", "main", "deploy", "swerve")):
            out.append(os.path.join(repo_root, d))
    return out
