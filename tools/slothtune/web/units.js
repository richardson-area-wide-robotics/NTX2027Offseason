// The team's units, for everything a person reads: speed in ft/s, lengths in inches, mass in
// pounds, torque in foot-pounds, angles in degrees. The robot, every saved file and every number
// from the server stay in the robot's own units (meters, kilograms, radians, newton-meters): the
// page converts only what it shows, and converts back what a person types (units.py is the
// server's twin of this). A gain stays in the code's units: the number on screen is the number in
// the file. Speed is "ft/s", never "fps": the camera's frames per second share these pages.
"use strict";

const U = (() => {
  const IN_PER_M = 1 / 0.0254, FT_PER_M = 1 / 0.3048, LB_PER_KG = 1 / 0.45359237;
  const FTLB_PER_NM = 1 / 1.3558179483, DEG_PER_RAD = 180 / Math.PI;
  const ok = v => v != null && isFinite(v);
  const n = (v, d, sign) => !ok(v) ? "–" : (sign && v > 0 ? "+" : "") + Number(v).toFixed(d);
  // A mechanism's own units (TunableSystem.units, free text): meters, radians and kilograms show
  // in the team's, anything else (RPM, motor rotations, degrees) as it is.
  const SYS = {
    "m": ["in", IN_PER_M], "meter": ["in", IN_PER_M], "meters": ["in", IN_PER_M], "metres": ["in", IN_PER_M],
    "m/s": ["ft/s", FT_PER_M], "meters per second": ["ft/s", FT_PER_M], "mps": ["ft/s", FT_PER_M],
    "rad": ["deg", DEG_PER_RAD], "radian": ["deg", DEG_PER_RAD], "radians": ["deg", DEG_PER_RAD],
    "rad/s": ["deg/s", DEG_PER_RAD], "radians per second": ["deg/s", DEG_PER_RAD],
    "cm": ["in", IN_PER_M / 100], "centimeters": ["in", IN_PER_M / 100],
    "mm": ["in", IN_PER_M / 1000], "millimeters": ["in", IN_PER_M / 1000],
    "kg": ["lb", LB_PER_KG], "kilograms": ["lb", LB_PER_KG],
    "n·m": ["ft·lb", FTLB_PER_NM], "nm": ["ft·lb", FTLB_PER_NM], "n*m": ["ft·lb", FTLB_PER_NM],
    "newton meters": ["ft·lb", FTLB_PER_NM],
  };
  return {
    IN_PER_M, FT_PER_M, LB_PER_KG, FTLB_PER_NM, DEG_PER_RAD,
    // Numbers, robot units to the team's.
    fps: mps => mps * FT_PER_M,
    inches: m => m * IN_PER_M,
    lb: kg => kg * LB_PER_KG,
    ftlb: nm => nm * FTLB_PER_NM,
    deg: rad => rad * DEG_PER_RAD,
    // And back, for a number a person typed.
    mpsFromFps: v => v / FT_PER_M,
    mFromIn: v => v / IN_PER_M,
    kgFromLb: v => v / LB_PER_KG,
    nmFromFtlb: v => v / FTLB_PER_NM,
    radFromDeg: v => v / DEG_PER_RAD,
    // Words: a number in the team's unit, with the unit.
    speed: (mps, d = 2, sign) => `${n(ok(mps) ? mps * FT_PER_M : NaN, d, sign)} ft/s`,
    accel: (mps2, d = 1, sign) => `${n(ok(mps2) ? mps2 * FT_PER_M : NaN, d, sign)} ft/s²`,
    length: (m, d = 1, sign) => `${n(ok(m) ? m * IN_PER_M : NaN, d, sign)} in`,
    mass: (kg, d = 0) => `${n(ok(kg) ? kg * LB_PER_KG : NaN, d)} lb`,
    torque: (nm, d = 1, sign) => `${n(ok(nm) ? nm * FTLB_PER_NM : NaN, d, sign)} ft·lb`,
    inertia: (kgm2, d = 0) => `${n(ok(kgm2) ? kgm2 * LB_PER_KG * IN_PER_M * IN_PER_M : NaN, d)} lb·in²`,
    angle: (rad, d = 1, sign) => `${n(ok(rad) ? rad * DEG_PER_RAD : NaN, d, sign)}°`,
    angvel: (radps, d = 0, sign) => `${n(ok(radps) ? radps * DEG_PER_RAD : NaN, d, sign)}°/s`,
    // {label, k}: show a mechanism's value * k in label (a rate per second converts the same).
    sys: units => {
      const hit = SYS[String(units || "").trim().toLowerCase()];
      return hit ? { label: hit[0], k: hit[1] } : { label: units || "", k: 1 };
    },
  };
})();
