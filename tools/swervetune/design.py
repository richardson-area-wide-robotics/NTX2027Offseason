"""The robot's design file: every device the mechanical and electrical teams put on the robot, as
they designed it, so a freshly built robot can be brought up against it.

It lives with the code, deployed with it: ``src/main/deploy/design/devices.json``. A device is
written the way YAGSL writes one (``{"type": "sparkflex_vortex", "id": 10, "canbus": "rio"}``),
plus what bring-up checks: the subsystem, the PDH port and its breaker, inversion, brake or coast,
the current limit, the gear ratio, which way is positive, and whether it shares a shaft with other
motors. Sensors name their roboRIO (or SystemCore) port. CAN buses name their cable color: CTRE's
CAN cable comes as one color with green (green is CAN-L), so on a SystemCore robot with several buses
each bus is told apart by its color.

A spreadsheet the design team keeps can be imported (``from_csv``), and ``from_code`` drafts a file
from what the code already says, for the team to correct rather than type from nothing.
``check`` finds what doesn't add up inside the file; ``compare`` finds where the code disagrees with
it. Nothing here needs the robot.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re

from . import motorinv, wiring

VERSION = 1
CONTROLLERS = ("roborio", "roborio2", "systemcore")
# CTRE's CAN cable: each comes as this color with green (CAN-L). Hex values for drawing a bus.
BUS_COLORS = {"yellow": "#e5d300", "orange": "#f28c28", "brown": "#8b5a2b", "lightblue": "#6ec6f0",
              "purple": "#8e5bb5", "grey": "#9aa0a6", "white": "#ffffff", "pink": "#f48fb1"}
CONTROLLER_TYPES = ("sparkmax", "sparkflex", "talonfx", "talonfxs")
MOTOR_SUFFIXES = {"neo": "NEO V1.1", "neo2": "NEO 2.0", "neo550": "NEO 550", "vortex": "NEO Vortex",
                  "krakenx60": "Kraken X60", "krakenx44": "Kraken X44", "falcon500": "Falcon 500", "minion": "Minion"}
SENSOR_TYPES = ("digital", "analog", "dutycycle", "encoder", "pwm")
# roboRIO ports on its own headers, then the MXP. SystemCore's ports are not range-checked here.
RIO_PORTS = {"digital": range(0, 26), "dutycycle": range(0, 26), "encoder": range(0, 26),
             "analog": range(0, 8), "pwm": range(0, 20)}
# Java classes that take a roboRIO port, and which kind of port.
PORT_CLASSES = {"DigitalInput": "digital", "DigitalOutput": "digital", "DutyCycleEncoder": "dutycycle",
                "DutyCycle": "dutycycle", "AnalogInput": "analog", "AnalogPotentiometer": "analog",
                "AnalogEncoder": "analog", "Encoder": "encoder", "PWM": "pwm", "Servo": "pwm",
                "PWMSparkMax": "pwm", "Spark": "pwm", "AddressableLED": "pwm"}


def path(project):
    return os.path.join(project.path, "src", "main", "deploy", "design", "devices.json")


def load(project):
    """The robot's design file, or None if there isn't one yet."""
    try:
        with open(path(project), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


def text(design):
    return json.dumps(design, indent=2) + "\n"


def _f(level, title, why, **extra):
    return dict({"level": level, "title": title, "why": why}, **extra)


def split_type(t):
    """``"sparkflex_vortex"`` -> ``("sparkflex", "vortex")``; a bad type -> ``(None, None)``."""
    m = re.fullmatch(r"([a-z]+)_([a-z0-9]+)", (t or "").strip().lower())
    if not m or m.group(1) not in CONTROLLER_TYPES or m.group(2) not in MOTOR_SUFFIXES:
        return None, None
    return m.group(1), m.group(2)


def buses(design):
    return {b.get("name"): b for b in (design.get("canBuses") or []) if b.get("name")}


# ---------------------------------------------------------------------------- the file on its own


def check(design):
    """What doesn't add up inside the design file itself."""
    F = []
    ctl = (design.get("controller") or "").lower()
    if ctl not in CONTROLLERS:
        F.append(_f("error", f"Controller {design.get('controller')!r} is not one this file knows",
                    "Set \"controller\" to roborio, roborio2 or systemcore: it decides which ports exist."))
    B = buses(design)
    if not B:
        F.append(_f("error", "No CAN bus listed", "List each CAN bus under \"canBuses\" with its name and cable color."))
    colors = {}
    for name, b in B.items():
        c = (b.get("color") or "").lower()
        if c not in BUS_COLORS:
            F.append(_f("error", f"CAN bus {name}: color {b.get('color')!r} is not a CAN cable color",
                        "One of " + ", ".join(BUS_COLORS) + " (each with green, which is CAN-L)."))
        elif c in colors:
            F.append(_f("error", f"CAN buses {colors[c]} and {name} are both {c}",
                        "Each bus gets its own cable color, so nobody plugs a device into the wrong bus."))
        colors.setdefault(c, name)
    labels = {}
    for name, b in B.items():
        lab = (b.get("label") or "").strip().lower()
        if lab and lab in labels:
            F.append(_f("warn", f"CAN buses {labels[lab]} and {name} are both called {b.get('label')!r}",
                        "Give each bus its own label (Drive train, Intake, ...), so a person can say which one."))
        labels.setdefault(lab, name)
    if ctl.startswith("roborio") and len(B) > 1:
        F.append(_f("warn", f"{len(B)} CAN buses on a roboRIO", "A roboRIO has one CAN bus; a second needs a CANivore. Check the list."))

    names, ids, ports = {}, {}, {}
    motors = design.get("motors") or []
    for m in motors:
        n = m.get("name") or ""
        if not n:
            F.append(_f("error", "A motor has no name", "Every motor needs the name the code and the drive team use."))
            continue
        if n in names:
            F.append(_f("error", f"Two motors are called {n!r}", "Names must be unique: alerts and tests name a motor by it."))
        names[n] = m
        dev = m.get("motor") or {}
        ctl_t, mot = split_type(dev.get("type"))
        if not ctl_t:
            F.append(_f("error", f"{n}: type {dev.get('type')!r} is not a controller_motor pair",
                        "Write it as YAGSL does, e.g. sparkflex_vortex, sparkmax_neo550, sparkmax_neo2."))
        bus = dev.get("canbus") if dev.get("canbus") is not None else next(iter(B), None)
        if B and bus not in B:
            F.append(_f("error", f"{n}: CAN bus {bus!r} is not listed", "Use one of the buses under \"canBuses\"."))
        cid = dev.get("id")
        if not isinstance(cid, int) or not 1 <= cid <= 62:
            F.append(_f("error", f"{n}: CAN ID {cid!r} out of range", "CAN IDs run 1 to 62 (0 and 63 are reserved)."))
        else:
            # REV controllers share one ID space on a bus (a SPARK MAX and a SPARK Flex can't both be 10).
            family = "rev" if (ctl_t or "").startswith("spark") else ctl_t
            key = (bus, family, cid)
            if key in ids:
                F.append(_f("error", f"{n} and {ids[key]} both use CAN ID {cid} on {bus}",
                            "Two controllers of one maker on one bus need different IDs, or neither works properly."))
            ids[key] = n
        pdh = m.get("pdh") or {}
        if pdh.get("port") is not None:
            p, brk = pdh.get("port"), pdh.get("breaker")
            if not isinstance(p, int) or not 0 <= p <= 23:
                F.append(_f("error", f"{n}: PDH port {p!r} out of range", "A REV PDH has ports 0 to 23."))
            else:
                if p in ports:
                    F.append(_f("error", f"{n} and {ports[p]} are both on PDH port {p}", "One port feeds one controller."))
                ports[p] = n
                limit = 40 if p <= 19 else 15
                if isinstance(brk, (int, float)) and brk > limit:
                    F.append(_f("error", f"{n}: a {brk} A breaker on PDH port {p}",
                                f"PDH ports 0-19 take at most 40 A, 20-23 at most 15 A."))
    # Followers and shafts.
    for m in motors:
        fol = m.get("follows") or {}
        if fol and fol.get("leader") not in names:
            F.append(_f("error", f"{m.get('name')} follows {fol.get('leader')!r}, which isn't a motor here", "Name the leader exactly."))
    shafts = {}
    for m in motors:
        if m.get("shaft"):
            shafts.setdefault(m["shaft"], []).append(m)
    for s, group in shafts.items():
        if len(group) < 2:
            F.append(_f("warn", f"Shaft {s!r} has one motor", "A shaft is for motors that turn the same shaft: list the others too, or drop it."))
        for m in group:
            if not isinstance(m.get("gearRatio"), (int, float)) or m.get("gearRatio") == 0:
                F.append(_f("error", f"{m['name']} shares shaft {s!r} but has no gear ratio",
                            "Motor turns per shaft turn: the bring-up test checks every motor on a shaft turns it the same way and speed."))
    # Sensors.
    seen = {}
    for s in design.get("sensors") or []:
        t, p = (s.get("type") or "").lower(), s.get("port")
        if t not in SENSOR_TYPES:
            F.append(_f("error", f"{s.get('name')}: sensor type {s.get('type')!r}", "One of " + ", ".join(SENSOR_TYPES) + "."))
            continue
        plist = p if isinstance(p, list) else [p]
        for q in plist:
            if not isinstance(q, int):
                F.append(_f("error", f"{s.get('name')}: port {q!r}", "A port is a number."))
                continue
            if ctl.startswith("roborio") and q not in RIO_PORTS[t]:
                F.append(_f("error", f"{s.get('name')}: {t} port {q} doesn't exist on a roboRIO", "Check the port numbers on the roboRIO and MXP."))
            kind = "analog" if t == "analog" else "pwm" if t == "pwm" else "dio"
            if (kind, q) in seen:
                F.append(_f("error", f"{s.get('name')} and {seen[(kind, q)]} share {kind.upper()} port {q}", "One port, one device."))
            seen[(kind, q)] = s.get("name")
    return F


# ---------------------------------------------------------------------------- what the code says


def _configs(src):
    """For each motor variable, the settings its config object gives it: follows, inverted, idle, limit."""
    out = {}
    for motor, cfg in re.findall(r"\b(\w+)\.configure\(\s*(\w+)", src):
        text_ = " ".join(re.findall(r"\b" + re.escape(cfg) + r"((?:\s*\.\s*\w+\([^;]*?\))+)\s*;", src))
        # Nested config groups (cfg.closedLoop.pid) are fine: only these calls are read.
        f = re.search(r"\.follow\(\s*(\w+)\s*(?:,\s*(true|false))?\s*\)", text_)
        inv = re.search(r"\.inverted\(\s*(true|false)\s*\)", text_)
        idle = re.search(r"\.idleMode\([^)]*k(Brake|Coast)\s*\)", text_)
        lim = re.search(r"\.smartCurrentLimit\(\s*(\d+)", text_)
        out[motor] = {"follows": (f.group(1), f.group(2) == "true") if f else None,
                      "inverted": (inv.group(1) == "true") if inv else None,
                      "idle": idle.group(1).lower() if idle else None,
                      "limit": int(lim.group(1)) if lim else None}
    return out


def code_motors(project):
    """Every motor the code creates, with what its configuration says (name, CAN ID, controller,
    motor kind, follows, inverted, idle mode, current limit, file)."""
    kinds = motorinv.code_kinds(project)
    out = []
    for d in wiring.discover(project):
        if d["kind"] != "controller":
            continue
        out.append({"name": d["name"], "can_id": d["can_id"], "controller": motorinv.code_controller(d["model"]),
                    "kind": kinds.get(d["name"]) or motorinv.yagsl_motor(d["model"]), "source": d["source"],
                    "follows": None, "inverted": None, "idle": None, "limit": None})
    by_name = {m["name"]: m for m in out}
    for rel, src in project.java.items():
        names = dict((var, label) for label, var in re.findall(r'\.watch\(\s*"([^"]+)"\s*,\s*(\w+)', src))
        for var, cfg in _configs(src).items():
            m = by_name.get(names.get(var, ""))
            if not m:
                continue
            m.update({k: v for k, v in cfg.items() if k != "follows" and v is not None})
            if cfg["follows"]:
                m["follows"] = {"leader": names.get(cfg["follows"][0], cfg["follows"][0]), "inverted": cfg["follows"][1]}
    return out


def code_ports(project):
    """Every roboRIO port the code opens: ``{class, kind, ports, file}``."""
    out = []
    cls = "|".join(sorted(PORT_CLASSES, key=len, reverse=True))
    for rel, src in project.java.items():
        if "/swervetune/" in rel.replace("\\", "/"):
            continue
        consts = {k: int(v) for k, v in re.findall(r"\b([A-Z_][A-Z0-9_]*)\s*=\s*(\d+)\s*;", src)}
        for c, args in re.findall(r"\bnew\s+(" + cls + r")\s*\(\s*([^)]*)\)", src):
            vals = []
            for a in [x.strip() for x in args.split(",")][: 2 if c == "Encoder" else 1]:
                vals.append(int(a) if a.isdigit() else consts.get(a))
            if vals and all(v is not None for v in vals):
                out.append({"class": c, "kind": PORT_CLASSES[c], "ports": vals, "file": os.path.basename(rel)})
    return out


_KIND_SUFFIX = {"NEO V1.1": "neo", "NEO 2.0": "neo2", "NEO 550": "neo550", "NEO Vortex": "vortex",
                "NEO (V1.1 or 2.0?)": "neo", "NEO": "neo"}


def from_code(project):
    """A first design file drafted from the code: what the team then checks against the real robot."""
    pdh_ports = (wiring.load_map(project) or {}).get("pdhPorts") or {}
    motors = []
    for m in code_motors(project):
        prefix = motorinv.YAGSL_PREFIX.get(m["controller"], "sparkmax")
        suffix = _KIND_SUFFIX.get(m["kind"] or "", "neo")
        sub = m["name"].split(" ")[0] if not m["name"].endswith((" drive", " steer")) else "Drive"
        entry = {"name": m["name"], "subsystem": sub,
                 "motor": {"type": f"{prefix}_{suffix}", "id": m["can_id"], "canbus": "rio"},
                 "inverted": m["inverted"], "idleMode": m["idle"], "currentLimit": m["limit"],
                 # The breaker is the electrical team's to say: left blank, never guessed.
                 "pdh": {"port": pdh_ports.get(m["name"]), "breaker": None},
                 "gearRatio": None, "positive": "", "shaft": None, "follows": m["follows"]}
        # A swerve motor: YAGSL's files already say its inversion, gear ratio and current limit.
        for mod in project.module_names():
            for part, label in (("drive", "drive"), ("angle", "steer")):
                if m["name"] == f"{mod} {label}":
                    phys = project.phys or {}
                    entry["inverted"] = ((project.module(mod).get("inverted") or {}).get(part))
                    entry["gearRatio"] = (((phys.get("conversionFactors") or {}).get(part) or {}).get("gearRatio"))
                    entry["currentLimit"] = ((phys.get("currentLimit") or {}).get(part))
                    entry["positive"] = "the robot drives forward" if label == "drive" else "the wheel turns counter-clockwise, seen from above"
        motors.append(entry)
    # A leader and its follower turn one shaft: draft them as one.
    for m in motors:
        if m["follows"]:
            lead = next((x for x in motors if x["name"] == m["follows"]["leader"]), None)
            if lead:
                shaft = lead["shaft"] or lead["subsystem"].lower()
                lead["shaft"] = m["shaft"] = shaft
    sensors = [{"name": f"{p['class']} on {p['kind']} {', '.join(map(str, p['ports']))}", "subsystem": "",
                "type": p["kind"], "port": p["ports"] if len(p["ports"]) > 1 else p["ports"][0],
                "means": "", "from": p["file"]} for p in code_ports(project)]
    return {"version": VERSION, "robot": project.name, "controller": "roborio2",
            "_readme": "The robot as designed: drafted from the code, to be checked and corrected by the "
                       "mechanical and electrical teams. Bring-up checks the robot against it.",
            "canBuses": [{"name": "rio", "color": "yellow", "terminated": ["roboRIO", "PDH"]}],
            "pdh": {"type": "rev_pdh", "id": 1, "canbus": "rio"},
            "motors": motors, "sensors": sensors}


# ---------------------------------------------------------------------------- the file against the code


def compare(project, design):
    """Where the code disagrees with the design: IDs, controllers, motors, followers, inversion,
    brake/coast, current limits, PDH ports, roboRIO ports, and devices one has and the other not."""
    F = []
    code = {m["name"]: m for m in code_motors(project)}
    by_id = {m["can_id"]: m for m in code.values() if m["can_id"] is not None}
    pdh_map = (wiring.load_map(project) or {}).get("pdhPorts") or {}
    seen = set()
    for d in design.get("motors") or []:
        n, dev = d.get("name"), d.get("motor") or {}
        c = code.get(n) or by_id.get(dev.get("id"))
        if not c:
            F.append(_f("error", f"{n}: not in the code", f"The design has it (CAN {dev.get('id')}); no code creates a controller with that name or ID.",
                        motor=n))
            continue
        seen.add(c["name"])
        where = f" ({c['source']})"
        if c["name"] != n:
            F.append(_f("warn", f"{n}: the code calls CAN {dev.get('id')} {c['name']!r}",
                        "Use one name in both, so alerts and tests name the same motor." + where, motor=n))
        if dev.get("id") != c["can_id"]:
            F.append(_f("error", f"{n}: CAN ID {dev.get('id')} in the design, {c['can_id']} in the code",
                        "One of them is wrong: check the label on the controller, then fix the other." + where, motor=n))
        ctl_t, mot = split_type(dev.get("type"))
        want_ctl = {"sparkmax": "SPARK MAX", "sparkflex": "SPARK Flex"}.get(ctl_t)
        if want_ctl and c["controller"] and want_ctl != c["controller"]:
            F.append(_f("error", f"{n}: a {want_ctl} in the design, the code creates a {c['controller']}",
                        "A SPARK Flex created as a SPARK MAX (or the reverse) misreads its sensor and limits." + where, motor=n))
        want_kind = MOTOR_SUFFIXES.get(mot)
        if want_kind and c["kind"] and want_kind.split()[0] == "NEO" and c["kind"] != want_kind \
                and not (mot == "neo" and c["kind"].startswith("NEO (")):
            F.append(_f("warn", f"{n}: a {want_kind} in the design, the code says {c['kind']}",
                        "The motor guard's heat limits follow the code's MotorKind." + where, motor=n))
        for key, label in (("inverted", "inverted"), ("idleMode", "brake/coast"), ("currentLimit", "current limit")):
            want = d.get(key)
            have = c["inverted"] if key == "inverted" else c["idle"] if key == "idleMode" else c["limit"]
            if want is not None and have is not None and want != have:
                F.append(_f("warn", f"{n}: {label} {want} in the design, {have} in the code", "Make them agree." + where, motor=n))
        fol = d.get("follows")
        cf = c["follows"]
        if bool(fol) != bool(cf) or (fol and cf and (fol.get("leader") != cf["leader"] or bool(fol.get("inverted")) != cf["inverted"])):
            F.append(_f("error", f"{n}: follows {fol!r} in the design, {cf!r} in the code",
                        "A follower set the wrong way turns against its leader on a shared shaft." + where, motor=n))
        port = (d.get("pdh") or {}).get("port")
        if port is not None and pdh_map.get(n) is not None and pdh_map[n] != port:
            F.append(_f("warn", f"{n}: PDH port {port} in the design, {pdh_map[n]} in the wiring map",
                        "Check which port really feeds it (Wiring: Find the PDH ports).", motor=n))
    for n, c in code.items():
        if n not in seen:
            F.append(_f("warn", f"{n}: in the code (CAN {c['can_id']}), not in the design",
                        f"Add it to the design file, or remove it from the code ({c['source']}).", motor=n))
    # roboRIO ports.
    want = {}
    for s in design.get("sensors") or []:
        ps = s.get("port") if isinstance(s.get("port"), list) else [s.get("port")]
        for p in ps:
            want[(s.get("type"), p)] = s.get("name")
    have = {}
    for p in code_ports(project):
        for q in p["ports"]:
            have[(p["kind"], q)] = f"{p['class']} in {p['file']}"
    for k, n in want.items():
        if k not in have:
            F.append(_f("warn", f"{n}: {k[0]} port {k[1]} in the design; the code opens nothing there", "Wire it in the code, or fix the port."))
    for k, w in have.items():
        if k not in want:
            F.append(_f("warn", f"The code opens {k[0]} port {k[1]} ({w}); the design has nothing there", "Add it to the design, or fix the port in the code."))
    return F


# ---------------------------------------------------------------------------- a spreadsheet


CSV_COLUMNS = ("name", "subsystem", "kind", "type", "id", "canbus", "pdh_port", "breaker", "inverted", "idle",
               "current_limit", "gear_ratio", "positive", "shaft", "follows", "follows_inverted", "port", "means")


def _bool(v):
    v = (v or "").strip().lower()
    return True if v in ("true", "yes", "y", "1") else False if v in ("false", "no", "n", "0") else None


def _num(v, cast=float):
    v = (v or "").strip()
    try:
        return cast(v) if v else None
    except ValueError:
        return None


def from_csv(text_, *, robot="", controller="roborio2", buses_=None):
    """A design file from a spreadsheet saved as CSV: one row per motor (kind ``motor``) or sensor (kind
    ``digital``, ``analog``, ``dutycycle``, ``encoder`` or ``pwm``), columns as ``CSV_COLUMNS``. A row of
    kind ``bus`` lists a CAN bus: ``name`` as the code calls it, ``type`` its cable color, ``subsystem``
    what people call it (Drive train, Intake)."""
    motors, sensors, bus_rows = [], [], []
    for row in csv.DictReader(io.StringIO(text_)):
        r = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        if not r.get("name"):
            continue
        kind = (r.get("kind") or "motor").lower()
        if kind == "bus":
            bus_rows.append({"name": r["name"], "label": r.get("subsystem", ""), "color": (r.get("type") or "").lower()})
            continue
        if kind == "motor":
            motors.append({"name": r["name"], "subsystem": r.get("subsystem", ""),
                           "motor": {"type": r.get("type", ""), "id": _num(r.get("id"), int), "canbus": r.get("canbus") or "rio"},
                           "inverted": _bool(r.get("inverted")), "idleMode": (r.get("idle") or None) and r["idle"].lower(),
                           "currentLimit": _num(r.get("current_limit"), int),
                           "pdh": {"port": _num(r.get("pdh_port"), int), "breaker": _num(r.get("breaker"), int)},
                           "gearRatio": _num(r.get("gear_ratio")), "positive": r.get("positive", ""),
                           "shaft": r.get("shaft") or None,
                           "follows": {"leader": r["follows"], "inverted": bool(_bool(r.get("follows_inverted")))} if r.get("follows") else None})
        else:
            ports = [int(p) for p in re.findall(r"\d+", r.get("port", ""))]
            sensors.append({"name": r["name"], "subsystem": r.get("subsystem", ""), "type": kind,
                            "port": ports if len(ports) > 1 else (ports[0] if ports else None), "means": r.get("means", "")})
    names = sorted({(m["motor"]["canbus"]) for m in motors} or {"rio"})
    colors = list(BUS_COLORS)
    return {"version": VERSION, "robot": robot, "controller": controller,
            "canBuses": buses_ or bus_rows or [{"name": n, "color": colors[i % len(colors)]} for i, n in enumerate(names)],
            "pdh": {"type": "rev_pdh", "id": 1, "canbus": names[0]},
            "motors": motors, "sensors": sensors}
