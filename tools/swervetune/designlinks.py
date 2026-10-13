"""Mechanism designs from ReCalc (reca.lc) and AMBcalc (ambcalc.com) share links.

Teams design a mechanism in one of these calculators: the motor, how many, the gearing, the arm
length or spool or wheel, the load, the current limit. Neither site stores a design on a server:
the whole design is in the link's query string, so **the link is the design**. This module reads
every number a link carries, in SI units, so the tool can

* fill in the robot's configuration from it (the drivetrain's gearing, wheel and mass; each
  mechanism motor's type in the motor inventory), and
* check it against what the code and the robot actually do: the motor really fitted, the team's
  current policy, velocity setpoints the motor can't reach, and what a match log measured.

Formats, as checked on 2026-10-12 against each site's source and live bundle:

* **ReCalc** writes one query parameter per field, every field, always. A value is a number,
  ``true``/``false``, a string, or JSON: a measurement ``{"s": 24, "u": "in"}``, a motor
  ``{"name": "NEO Vortex", "quantity": 2}``, a ratio ``{"magnitude": 9, "ratioType": "Reduction"}``.
  The app was rewritten in July 2026; older links (still all over Chief Delphi) use different
  names on some pages (``currentLimit``, ``comLength``, the flywheel's radii, ``motorRatio``) and
  ``1``/``0`` booleans. Both are read.
* **AMBcalc** writes only the fields a person changed, keyed by the page's HTML ids, applied in
  order over the page's defaults. Checkboxes and radio buttons are ``^`` (on) and ``$`` (off), the
  empty key is the page title, and a unit drop-down's value is the factor to SI units for that
  field. The mechanism page solves for whichever quantity its "driving" radio button picks, so its
  ratio is only in the link when the ratio itself drives; otherwise it is worked out here for REV
  motors, and left unknown (with a note) for others.

A design names its motor as the site does. REV's motors map to :mod:`revspecs`; any other motor
is kept by name, and the checks that need its specs say so.
"""

from __future__ import annotations

import json
import math
import re
from urllib.parse import parse_qsl, urlsplit

from . import revspecs

G = 9.80665

# ---------------------------------------------------------------------------- units
# js-quantities unit strings (ReCalc) to SI: meters, kilograms, m/s, seconds, newtons, kg·m².
_LENGTH = {"in": 0.0254, "inch": 0.0254, "ft": 0.3048, "foot": 0.3048, "mm": 0.001, "cm": 0.01, "m": 1.0}
_MASS = {"oz": 0.028349523, "lbs": 0.45359237, "lb": 0.45359237, "g": 0.001, "kg": 1.0}
_SPEED = {"in/s": 0.0254, "ft/s": 0.3048, "mph": 0.44704, "m/s": 1.0, "kph": 1 / 3.6, "km/h": 1 / 3.6}
_TIME = {"s": 1.0, "ms": 0.001, "min": 60.0, "hr": 3600.0}
_ANGLE_DEG = {"deg": 1.0, "rad": 180 / math.pi}
_ROT_RPM = {"rpm": 1.0, "deg/s": 1 / 6, "rotation/s": 60.0, "rad/s": 60 / (2 * math.pi)}
_MOI = {"in2*lbs": 0.0254 ** 2 * 0.45359237, "lbs*in2": 0.0254 ** 2 * 0.45359237, "kg*m2": 1.0}
_PLAIN = {"A": 1.0, "V": 1.0, "Ohm": 1.0, "ohm": 1.0}
_TABLES = {"length": _LENGTH, "mass": _MASS, "speed": _SPEED, "time": _TIME, "angle": _ANGLE_DEG,
           "rpm": _ROT_RPM, "moi": _MOI, "plain": _PLAIN}


def _measure(raw, kind):
    """A ReCalc measurement ``{"s": 24, "u": "in"}`` (already decoded) in SI, or None."""
    if not isinstance(raw, dict) or "s" not in raw:
        return None
    try:
        v = float(raw["s"])
    except (TypeError, ValueError):
        return None
    u = str(raw.get("u", "")).replace(" ", "")
    f = _TABLES[kind].get(u)
    if f is None:
        f = _TABLES[kind].get(u.lower())
    return v * f if f is not None and math.isfinite(v) else None


# ---------------------------------------------------------------------------- motors
_REV = {"neo": "neo", "neo1.1": "neo", "neov1.1": "neo", "neo2.0": "neo2", "neovortex": "vortex", "vortex": "vortex",
        "neo550": "neo550"}


def motor_key(name):
    """A site's motor name to a :mod:`revspecs` key, or None for a motor that isn't REV's."""
    n = re.sub(r"\s*\(HIGHLY PRELIMINARY\)\s*", "", str(name or "")).replace("*", "")
    return _REV.get(n.lower().replace(" ", ""))


def _motor(name, count):
    key = motor_key(name)
    return {"name": str(name or "").replace("*", "").strip(), "key": key,
            "label": revspecs.MOTORS[key]["label"] if key else str(name or "").strip(), "count": int(count or 1)}


# ---------------------------------------------------------------------------- links
def parse(url):
    """Every number a ReCalc or AMBcalc link carries: a design dict (see :func:`_design`).

    Raises ValueError for a link from somewhere else, or a calculator with nothing to configure.
    """
    u = urlsplit(str(url or "").strip())
    host = (u.hostname or "").lower()
    page = u.path.strip("/").split("/")[-1] if u.path.strip("/") else ""
    if host.endswith("reca.lc"):
        return _recalc(page, u.query, url)
    if host.endswith("ambcalc.com"):
        return _amb(page.removesuffix(".html"), u.query, url)
    raise ValueError("That isn't a ReCalc (reca.lc) or AMBcalc (ambcalc.com) link.")


def _design(source, calculator, kind, url, **kw):
    d = {"source": source, "calculator": calculator, "kind": kind, "url": str(url).strip(), "title": "",
         "motor": None, "ratio": None, "efficiency": None, "voltage": 12.0, "current_limit_a": None,
         "supply_limit_a": None, "notes": []}
    d.update(kw)
    return d


# -------------------------------------------------------------------- ReCalc
def _rc_values(query):
    out = {}
    for k, v in parse_qsl(query, keep_blank_values=True):
        if v[:1] in "{[":
            try:
                v = json.loads(v)
            except ValueError:
                pass
        out[k] = v
    return out


def _rc_ratio(v):
    if isinstance(v, dict) and "magnitude" in v:
        try:
            m = float(v["magnitude"])
        except (TypeError, ValueError):
            return None
        if m <= 0:
            return None
        return 1 / m if str(v.get("ratioType", "")).lower().startswith("step") else m
    return None


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _bool(v):
    return str(v).strip().lower() in ("true", "1")


def _rc_motor(v):
    if isinstance(v, dict) and v.get("name"):
        return _motor(v["name"], v.get("quantity", 1))
    if isinstance(v, str) and v:
        return _motor(v, 1)
    return None


def _first(p, *keys):
    for k in keys:
        if k in p and p[k] not in ("", None):
            return p[k]
    return None


def _recalc(page, query, url):
    p = _rc_values(query)
    legacy = any(k in p for k in ("currentLimit", "comLength", "armMass", "motorRatio", "shooterRadius", "chain"))
    eff = _num(p.get("efficiency"))
    common = dict(motor=_rc_motor(p.get("motor")), efficiency=eff / 100 if eff is not None else None,
                  current_limit_a=_measure(_first(p, "statorLimit", "currentLimit", "statorCurrentLimit", "motorCurrentLimit"), "plain"),
                  supply_limit_a=_measure(p.get("supplyLimit"), "plain"),
                  voltage=_measure(_first(p, "supplyVoltage", "batteryVoltageAtRest"), "plain") or 12.0, legacy=legacy)
    if page == "arm":
        lo = _measure(_first(p, "minAngle", "startAngle"), "angle")
        hi = _measure(_first(p, "maxAngle", "endAngle"), "angle")
        return _design("ReCalc", "arm", "arm", url, ratio=_rc_ratio(p.get("ratio")),
                       arm_length_m=_measure(_first(p, "armLength", "comLength"), "length"),
                       mass_kg=_measure(_first(p, "load", "armMass"), "mass"),
                       angles_deg=[lo, hi] if lo is not None and hi is not None else None, **common)
    if page == "linear":
        angle = _measure(p.get("angle"), "angle")
        return _design("ReCalc", "linear", "elevator" if angle is None or abs(angle - 90) < 1 else "linear", url,
                       ratio=_rc_ratio(p.get("ratio")), spool_diameter_m=_measure(p.get("spoolDiameter"), "length"),
                       travel_m=_measure(p.get("travelDistance"), "length"), mass_kg=_measure(p.get("load"), "mass"),
                       angle_deg=angle, cascade=_bool(p.get("cascade", "false")), **common)
    if page == "flywheel":
        d_m = _measure(p.get("shooterDiameter"), "length")
        if d_m is None and p.get("shooterRadius") is not None:
            r = _measure(p.get("shooterRadius"), "length")
            d_m = 2 * r if r is not None else None
        target = _measure(p.get("shooterTargetSpeed"), "rpm")
        return _design("ReCalc", "flywheel", "flywheel", url,
                       ratio=_rc_ratio(_first(p, "ratio", "motorRatio")), wheel_diameter_m=d_m,
                       mass_kg=_measure(p.get("shooterWeight"), "mass"), target_rpm=target, **common)
    if page == "intake":
        return _design("ReCalc", "intake", "roller", url, ratio=_rc_ratio(p.get("ratio")),
                       wheel_diameter_m=_measure(p.get("rollerDiameter"), "length"),
                       travel_m=_measure(p.get("travelDistance"), "length"), **common)
    if page == "drive":
        w = (_measure(p.get("weightInspected"), "mass") or 0) + (_measure(p.get("weightAuxilliary"), "mass") or 0)
        return _design("ReCalc", "drive (old beta)", "drivetrain", url, ratio=_rc_ratio(p.get("ratio")),
                       wheel_diameter_m=_measure(p.get("wheelDiameter"), "length"), mass_kg=w or None,
                       cof=_num(p.get("wheelCOFStatic")), swerve=_bool(p.get("swerve", "true")), **common)
    if page == "motors":
        return _design("ReCalc", "motors", "motor", url, **dict(common, motor=_rc_motor(p.get("motor"))))
    if page == "ratio":
        pairs = p.get("ratioPairs")
        if isinstance(pairs, dict):
            pairs = pairs.get("pairs")
        r = None
        if isinstance(pairs, list) and pairs:
            r = 1.0
            for a, b in pairs:
                r *= float(b) / float(a)
        return _design("ReCalc", "ratio", "gearing", url, ratio=r, legacy=legacy)
    if page in ("gears", "belts", "chains"):
        a = _num(_first(p, "gear1Teeth", "p1Teeth")); b = _num(_first(p, "gear2Teeth", "p2Teeth"))
        return _design("ReCalc", page, "gearing", url, ratio=b / a if a and b else None, legacy=legacy)
    if page in ("ratio-finder", "ratioFinder"):
        return _design("ReCalc", "ratio finder", "gearing", url, ratio=_rc_ratio(p.get("targetReduction")), legacy=legacy)
    raise ValueError(f"ReCalc's {page or 'home'} page has no mechanism to configure.")


# -------------------------------------------------------------------- AMBcalc
# Each page's defaults (what the page holds after loading), for the fields read here. Unit fields
# hold their SI factor; "^" means checked.
_AMB_DEFAULTS = {
    "mechanism": {"motor": "Kraken X60", "mot_num": "1", "volt": "12", "radius": "1", "radius-u": "0.0254",
                  "load": "50", "load-u": "4.448", "gbx_eff": "90", "rat": "", "rat-c": True,
                  "rot_f-u": "6.283", "rot_l-u": "6.283", "lin_f-u": "0.3048", "lin_l-u": "0.3048"},
    "startup": {"motor": "Kraken X60", "mot_num": "1", "volt": "12", "maxI": "", "radius": "24", "radius-u": "0.0254",
                "mass": "10", "mass-u": "0.4535", "load": "50", "load-u": "4.448", "gbx_eff": "90", "sim-ratio": ""},
    "drivetrain": {"motor": "Kraken X60", "mot_num": "4", "eff": "80", "vrest": "12.7", "ilim": "", "weight": "154",
                   "weight-u": "0.453592", "wheel_diam": "4", "wheel_diam-u": "0.0254", "cofs": "1.1",
                   "g1a": "", "g1b": "", "g2a": "", "g2b": "", "g3a": "", "g3b": ""},
    "motor_curves": {"num-motors": "[0]"},
}
_DRIVING = ("rat-c", "rot_f-c", "rot_l-c", "lin_f-c", "lin_l-c", "current-c", "st_load-c", "st_volt-c",
            "max_power-c", "max_eff-c", "stall-c")
# AMBcalc renamed "NEO" to "NEO 1.1" in November 2025; an older link still says NEO.
_AMB_SPECS = {k: (m["free_rpm"], m["stall_nm"]) for k, m in revspecs.MOTORS.items()}


def _amb_state(page, query):
    st = dict(_AMB_DEFAULTS.get(page, {}))
    given = set()
    title = ""
    for k, v in parse_qsl(query, keep_blank_values=True):
        if k == "":
            title = v
            continue
        if v == "":
            continue
        given.add(k)
        if v == "^":
            if k in _DRIVING:
                for r in _DRIVING:
                    st[r] = False
            st[k] = True
        elif v == "$":
            st[k] = False
        else:
            st[k] = v
    # Which fields the link itself set: everything else is the page's default, never the robot's.
    st["__given"] = given
    return st, title.strip()


def _si(st, field, default_unit=1.0):
    v = _num(st.get(field))
    if v is None:
        return None
    f = _num(st.get(field + "-u"))
    return v * (f if f is not None else default_unit)


def _amb_ratio_from_target(st, key, eff, count, volts):
    """The mechanism page's ratio when a target (not the ratio) drives it, from AMBcalc's own
    formulas, for REV motors only (their specs are known here)."""
    if not key:
        return None, "the ratio is worked out by AMBcalc from its target, for a motor this tool has no specs for"
    free_rpm, stall_nm = _AMB_SPECS[key]
    wf = free_rpm * math.pi / 30 * volts / 12                    # free speed, rad/s
    ts = stall_nm * volts / 12 * eff * count                     # stall torque at the output, N·m
    r = _si(st, "radius", 0.0254)
    f = _si(st, "load", 4.448)
    if st.get("lin_f-c") and _si(st, "lin_f") and r:
        return wf * r / _si(st, "lin_f"), None
    if st.get("rot_f-c") and _si(st, "rot_f"):
        return wf / _si(st, "rot_f"), None
    if st.get("lin_l-c") and _si(st, "lin_l") and r and f is not None and ts > 0:
        v = _si(st, "lin_l")
        disc = 1 - 4 * (r * f / ts) * (v / r / wf)
        if disc < 0:
            return None, "that loaded speed is more than this motor can give"
        return wf / (2 * v / r) * (1 + math.sqrt(disc)), None
    if st.get("rot_l-c") and _si(st, "rot_l") and r and f is not None and ts > 0:
        w = _si(st, "rot_l")
        disc = 1 - 4 * (r * f / ts) * (w / wf)
        if disc < 0:
            return None, "that loaded speed is more than this motor can give"
        return wf / (2 * w) * (1 + math.sqrt(disc)), None
    if st.get("stall-c") and r and f and ts > 0:
        return r * f / ts, None
    return None, "the ratio is worked out by AMBcalc from a target this tool doesn't solve; open the link to read it"


def _amb(page, query, url):
    if page not in _AMB_DEFAULTS and page not in ("chain_belt", "planetary", "reduction_swap", "gearbox_options"):
        raise ValueError(f"AMBcalc's {page or 'home'} page has no mechanism to configure.")
    st, title = _amb_state(page, query)
    if page == "motor_curves":
        try:
            ids = [i for i in json.loads(st.get("num-motors", "[0]")) if i]
        except ValueError:
            ids = []
        if not ids:
            raise ValueError("That motor-curves link has no motors in it.")
        i = ids[0]
        d = _design("AMBcalc", "motor curves", "motor", url, title=title,
                    motor=_motor(st.get(f"motor-type{i}", "Kraken X60"), _num(st.get(f"mot_num{i}")) or 1),
                    ratio=_num(st.get(f"mot_rat{i}")) or 1.0, current_limit_a=_num(st.get(f"mot_maxi{i}")),
                    voltage=_num(st.get(f"mot_volt{i}")) or 12.0)
        if len(ids) > 1:
            d["notes"].append(f"The link compares {len(ids)} motors; this reads the first.")
        return d
    if page in ("chain_belt", "planetary", "reduction_swap", "gearbox_options"):
        if page == "chain_belt":
            a, b = _num(st.get("t1")), _num(st.get("t2"))
            r = b / a if a and b else None
        else:
            r = _num(st.get("desired" if page == "planetary" else "ratio"))
        return _design("AMBcalc", page.replace("_", " "), "gearing", url, title=title, ratio=r)
    motor = _motor(st.get("motor"), _num(st.get("mot_num")) or 1)
    if motor["name"] == "Custom":
        motor["label"] = "a custom motor"
    if page == "mechanism":
        eff = (_num(st.get("gbx_eff")) or 100) / 100
        volts = _num(st.get("volt")) or 12.0
        notes = []
        if st.get("rat-c"):
            ratio = _num(st.get("rat"))
            if ratio is None:
                notes.append("The ratio box is empty in this link.")
        else:
            ratio, why = _amb_ratio_from_target(st, motor["key"], eff, motor["count"], volts)
            if why:
                notes.append(why[0].upper() + why[1:] + ".")
        return _design("AMBcalc", "mechanism", "mechanism", url, title=title, motor=motor, ratio=ratio,
                       efficiency=eff, voltage=volts, radius_m=_si(st, "radius", 0.0254),
                       load_n=_si(st, "load", 4.448), notes=notes)
    if page == "startup":
        lim = _num(st.get("maxI"))
        return _design("AMBcalc", "startup", "mechanism", url, title=title, motor=motor,
                       ratio=_num(st.get("sim-ratio")), efficiency=(_num(st.get("gbx_eff")) or 100) / 100,
                       voltage=_num(st.get("volt")) or 12.0, current_limit_a=lim if lim is not None else 60.0,
                       radius_m=_si(st, "radius", 0.0254), mass_kg=_si(st, "mass", 0.4535),
                       load_n=_si(st, "load", 4.448),
                       assumed=[f for f, k in (("mass_kg", "mass"),) if k not in st["__given"]])
    # drivetrain
    ratio = 1.0
    for a, b in (("g1a", "g1b"), ("g2a", "g2b"), ("g3a", "g3b")):
        x, y = _num(st.get(a)), _num(st.get(b))
        ratio *= (y / x) if x and y else 1.0
    return _design("AMBcalc", "drivetrain", "drivetrain", url, title=title, motor=motor, ratio=ratio,
                   efficiency=(_num(st.get("eff")) or 100) / 100, voltage=_num(st.get("vrest")) or 12.7,
                   current_limit_a=_num(st.get("ilim")), mass_kg=_si(st, "weight", 0.453592),
                   wheel_diameter_m=_si(st, "wheel_diam", 0.0254), cof=_num(st.get("cofs")), swerve=None,
                   # AMBcalc fills in 154 lb, 4 in wheels and a grip of 1.1 when a link doesn't change them.
                   assumed=[f for f, k in (("mass_kg", "weight"), ("wheel_diameter_m", "wheel_diam"), ("cof", "cofs"))
                            if k not in st["__given"]])


# ---------------------------------------------------------------------------- what a design predicts
def predicts(d):
    """What the design implies for a REV motor, at 12 V: the output's free speed, and for an arm
    whether the motors can hold the load out level."""
    m = d.get("motor") or {}
    key, ratio = m.get("key"), d.get("ratio")
    out = {}
    if not key or not ratio:
        return out
    spec = revspecs.MOTORS[key]
    out["motor_free_rpm"] = spec["free_rpm"]
    out["output_free_rpm"] = spec["free_rpm"] / ratio
    dia = d.get("wheel_diameter_m") or d.get("spool_diameter_m")
    if dia:
        v = spec["free_rpm"] / 60 / ratio * math.pi * dia
        out["free_speed_mps"] = v * (2 if d.get("cascade") else 1)
    if d["kind"] == "arm" and d.get("arm_length_m") and d.get("mass_kg"):
        kt = spec["stall_nm"] / spec["stall_a"]
        amps = d.get("current_limit_a") or spec["stall_a"]
        torque = kt * min(amps, spec["stall_a"]) * m.get("count", 1) * ratio * (d.get("efficiency") or 1)
        need = d["mass_kg"] * G * d["arm_length_m"]
        out["hold_margin"] = torque / need if need > 0 else None
    return out


# ---------------------------------------------------------------------------- what the link says, in words
def _fmt(v, unit, digits=3):
    return f"{float(f'{v:.{digits}g}'):g} {unit}".strip()


def describe(d):
    """``[(label, value)]``: every number the link carries, in plain words, metric with US in brackets."""
    rows = []
    m = d.get("motor")
    if m:
        rows.append(("Motor", f"{m['count']} × {m['label']}" + ("" if m["key"] else " (not a REV motor)")))
    if d.get("ratio"):
        rows.append(("Gear ratio", f"{d['ratio']:.4g}:1 (motor turns per output turn)"))
    if d.get("efficiency") is not None:
        rows.append(("Efficiency", f"{d['efficiency'] * 100:.0f}%"))
    if d.get("current_limit_a") is not None:
        rows.append(("Current limit", _fmt(d["current_limit_a"], "A") + " per motor"))
    if d.get("supply_limit_a") is not None:
        rows.append(("Supply limit", _fmt(d["supply_limit_a"], "A") + " per motor"))
    for key, label in (("arm_length_m", "Arm length (pivot to load)"), ("spool_diameter_m", "Spool diameter"),
                       ("wheel_diameter_m", "Wheel diameter"), ("radius_m", "Radius"), ("travel_m", "Travel")):
        if d.get(key):
            rows.append((label, f"{d[key]:.4g} m ({d[key] / 0.0254:.3g} in)"))
    if d.get("mass_kg"):
        rows.append(("Mass" if d["kind"] == "drivetrain" else "Load", f"{d['mass_kg']:.3g} kg ({d['mass_kg'] / 0.45359237:.3g} lb)"))
    if d.get("load_n"):
        rows.append(("Load force", f"{d['load_n']:.3g} N ({d['load_n'] / 4.448:.3g} lbf)"))
    if d.get("angles_deg"):
        rows.append(("Range of motion", f"{d['angles_deg'][0]:g}° to {d['angles_deg'][1]:g}°"))
    if d.get("target_rpm"):
        rows.append(("Target speed", f"{d['target_rpm']:.4g} rpm at the wheel"))
    if d.get("cascade"):
        rows.append(("Rigging", "cascade"))
    if d.get("cof"):
        rows.append(("Wheel grip (static COF)", f"{d['cof']:g}"))
    rows.append(("Battery voltage", f"{d.get('voltage') or 12:g} V"))
    p = predicts(d)
    if p.get("output_free_rpm"):
        rows.append(("Free speed at the output", f"{p['output_free_rpm']:.4g} rpm (motor {p['motor_free_rpm']} rpm at 12 V)"))
    if p.get("free_speed_mps"):
        # A wheel's rim speed is not how fast anything travels: say which it is.
        label = "Surface speed of the wheel, at free speed" if d["kind"] in ("flywheel", "roller", "mechanism") else "Free speed"
        rows.append((label, f"{p['free_speed_mps']:.3g} m/s ({p['free_speed_mps'] / 0.3048:.3g} ft/s)"))
    if p.get("hold_margin"):
        rows.append(("Holding the load out level", f"{p['hold_margin']:.2g}× what it takes"))
    return rows
