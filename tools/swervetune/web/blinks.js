// What each device's status light means: every color and pattern, from the makers' own pages
// (each device names its source), drawn as a small light that blinks the way the real one does.
//
// Used three ways: the Wiring tab's device cards, a card on hover over anything marked
// data-blink="<device>" (the Motors table), and Troubleshoot's Status lights view, where each row
// also says what to do. With the robot connected, the rows its state says should be showing now
// are marked.
"use strict";

const Blinks = (() => {
  // The colors as the eye sees them; a light that is off is a dark ring.
  const C = { red: "#ff3b30", green: "#22c55e", blue: "#2f6bff", yellow: "#ffd400", cyan: "#00d5ff",
              magenta: "#ff2bd6", white: "#ffffff", orange: "#ff8a00", amber: "#ffb000" };
  const WORD = { blink: "blinking", slow: "blinking slowly", fast: "blinking fast", solid: "solid", off: "off",
                 count2: "2 blinks, then a pause", count3: "3 blinks, then a pause", count4: "4 blinks, then a pause" };
  const TURN = { slow: ", slowly", fast: ", fast" };
  // The same, shorter, for a hover card: "Cyan, blinking or solid", "Orange/yellow, slow".
  const SHORT = { solid: "solid", blink: "blinking", slow: "slow blink", fast: "fast blink", count2: "2 blinks", count3: "3 blinks", count4: "4 blinks" };

  // A light: its colors ("orange/yellow" takes turns between the two) and its pattern.
  const L = (c, p = "solid") => ({ c: c ? c.split("/") : [], p: c ? p : "off" });

  // A row: looks (one or two, e.g. blinking and solid), what it means (m), what to do (d), where to
  // go for it (go: a symptom, a tab, or the network check), and an id the robot's state can match.
  const row = (looks, m, extra = {}) => ({ looks: Array.isArray(looks) ? looks : [looks], m, ...extra });

  const BRUSHED = "Every motor on these robots is brushless: set the motor type to brushless in the code before running it.";
  const sparkRows = flex => [
    { title: "Running", rows: [
      row([L("cyan", "blink"), L("cyan")], "Brushless, brake mode. Blinking: nothing is commanding it, normal while the robot is disabled. Solid: enabled, output zero.", { id: "idle", s: "Brake mode. Blinking: idle, normal when disabled. Solid: enabled, at zero." }),
      row([L("magenta", "blink"), L("magenta")], "Brushless, coast mode. Blinking: nothing commanding it. Solid: enabled, output zero.", { id: "idle", s: "Coast mode. Blinking: idle. Solid: enabled, at zero." }),
      row([L("green", "blink"), L("green")], "Driving forward. Blinking: part power. Solid: full power.", { s: "Forward: part power, or full." }),
      row([L("red", "blink"), L("red")], "Driving in reverse. Blinking: part power. Solid: full power.", { s: "Reverse: part power, or full." }),
      row(L("green/white", "blink"), "Forward limit switch pressed: it won't drive forward.", { s: "Forward limit switch pressed.", d: "Nothing touching the switch? Check the switch and its wire." }),
      row(L("red/white", "blink"), "Reverse limit switch pressed: it won't drive in reverse.", { s: "Reverse limit switch pressed.", d: "Nothing touching the switch? Check the switch and its wire." }),
      row([L("blue", "blink"), L("blue")], "Brushed mode, brake. Blinking: nothing commanding it.", { s: "Brushed mode: wrong for a NEO.", d: BRUSHED }),
      row([L("yellow", "blink"), L("yellow")], "Brushed mode, coast. Blinking: nothing commanding it.", { s: "Brushed mode: wrong for a NEO.", d: BRUSHED }),
    ] },
    { title: "Identify, firmware, recovery", rows: [
      row(L("white/magenta", "fast"), "Identify: someone pressed Identify for this one in REV Hardware Client.", { s: "Identify (REV Hardware Client)." }),
      flex ? row(L("white/yellow", "blink"), "Updating its firmware over CAN.", { s: "Updating firmware: leave it powered.", d: "Leave it powered until it finishes." })
        : row([L("white/yellow", "blink"), L("green/magenta", "blink")], "Updating its firmware over CAN (white and yellow from firmware 1.5.0; green and magenta on 1.4.0).",
          { s: "Updating firmware: leave it powered.", d: "Leave it powered until it finishes." }),
      row(L("white/blue", "blink"), "A firmware update over CAN is retrying.", { s: "Firmware update retrying.", d: "Run the update again in REV Hardware Client." }),
      row(L(null), "No light: no power, or in USB firmware update or Recovery Mode, or its firmware didn't load.",
        { s: "No power, firmware recovery, or bad firmware.", d: "Check its power first: its PDH port's breaker and its leads. Powered and still dark: recover it in REV Hardware Client (Recovery Mode).",
          go: { tab: "wiring" }, id: "dark" }),
    ] },
    { title: "Faults: orange and a second color, slow", rows: [
      row(L("orange/blue", "slow"), "12 V missing: it has only USB power, so the motor won't drive.", { s: "12 V missing: USB power only.", d: "Normal on USB at the bench. On the robot: its power leads and PDH breaker." }),
      row(L("orange/magenta", "slow"), "Sensor fault: the motor's sensor isn't read right.",
        { s: "Sensor fault: its sensor cable or motor type.", d: "Check the sensor cable is plugged in and undamaged, and that the code sets the right motor type.", id: "sensor fault" }),
      row(L("orange/cyan", "slow"), "Gate driver fault: the controller's own electronics reported a fault.",
        { s: "Gate driver fault: power cycle; then REV.", d: "Power cycle the robot. If it comes back, contact REV.", id: "gate driver fault" }),
      row(L("orange/yellow", "slow"), "CAN fault: it was on the CAN bus and lost it.",
        { s: "CAN fault: check the CAN wiring.", d: "Check the CAN wiring along the bus.", go: { tab: "wiring" }, id: "CAN fault" }),
      ...(flex ? [row(L("orange/green", "slow"), "Too hot: the motor or the controller stopped to cool. It clears itself once cool.",
        { s: "Too hot: cooling; clears itself.", d: "Let it cool. The Motors tab shows its temperature and what drew the current.", go: { tab: "motors" }, id: "over temperature" })] : []),
    ] },
  ];

  const REV_MAX = { title: "REV: SPARK MAX status LED", url: "https://docs.revrobotics.com/brushless/spark-max/status-led" };
  const REV_FLEX = { title: "REV: SPARK Flex status LED", url: "https://docs.revrobotics.com/brushless/spark-flex/status-led" };
  const WPILIB = { title: "WPILib: status light quick reference", url: "https://docs.wpilib.org/en/stable/docs/hardware/hardware-basics/status-lights-ref.html" };
  const REDUX = { title: "Redux Robotics: Canandgyro LED codes", url: "https://docs.reduxrobotics.com/canandgyro/led-codes/" };
  const KAUAI = { title: "Kauai Labs: navX-sensor LED test procedure", url: "https://www.kauailabs.com/support/navx-mxp/kb/faq.php?id=50" };
  const LIMELIGHT = { title: "Limelight: SystemCore specifications (alpha)", url: "https://downloads.limelightvision.io/documents/systemcore_specifications_june15_2025_alpha.pdf" };
  const NAMES = ["CAL", "S1", "S2"];
  const AT_HOME = "At home that is the access point radio (10.TE.AM.4).";
  const BATTERY = "A radio set up as the access point turns its Wi-Fi off when it sees a robot battery: power it from its own supply.";

  const DEVICES = {
    "SPARK MAX": { pic: "SPARK MAX", light: "One status light, in the middle of the case.", source: REV_MAX, groups: sparkRows(false) },
    "SPARK Flex": { pic: "SPARK Flex", light: "One status light, on the SPARK Flex beside its USB-C port.", source: REV_FLEX, groups: sparkRows(true) },
    "roboRIO": { pic: "roboRIO", light: "A row of lights by the USB ports: Power, Status, Radio, Comm, Mode and RSL.", source: WPILIB, groups: [
      { title: "Power", rows: [
        row(L("green"), "Power is good."),
        row(L("amber"), "Brownout protection tripped: its outputs are off.", { s: "Browned out: its outputs are off.", d: "The battery sagged too low: charge or swap it, and check the main breaker and leads.", go: { symptom: "brownout" } }),
        row(L("red"), "Power fault: a short on one of its user power rails (the pins that power sensors).", { s: "A short on its sensor power pins.", d: "Unplug what's on its DIO, PWM, analog and MXP pins until it turns green." }),
      ] },
      { title: "Status", rows: [
        row(L("amber"), "On while it boots, then off: normal."),
        row(L("amber", "count2"), "Software error.", { d: "Reimage the roboRIO (roboRIO Imaging Tool)." }),
        row(L("amber", "count3"), "Safe Mode.", { d: "Restart it; reimage it if this keeps happening." }),
        row(L("amber", "count4"), "Its software crashed twice without rebooting.", { s: "Crashed twice: reboot it.", d: "Reboot it; reimage it if this keeps happening." }),
        row(L("amber", "fast"), "Flashing all the time, or on and never going off: an unrecoverable error.", { s: "Flashing, or never off: unrecoverable.", d: "Reimage it." }),
      ] },
      { title: "Comm", rows: [
        row(L(null), "No communication with a Driver Station.", { s: "No Driver Station.", go: { symptom: "no_comms" } }),
        row(L("red"), "A Driver Station is connected, but no robot code is running.", { s: "Driver Station, but no robot code.", go: { symptom: "no_robot_code" } }),
        row(L("red", "blink"), "E-stopped.", { d: "Restart the roboRIO to clear an E-stop.", id: "estop" }),
        row(L("green"), "Talking to the Driver Station."),
      ] },
      { title: "Mode", rows: [
        row(L(null), "Outputs off: disabled, or browned out.", { id: "DISABLED", s: "Disabled, or browned out." }),
        row(L("orange"), "Enabled in autonomous.", { id: "AUTO" }),
        row(L("green"), "Enabled in teleop.", { id: "TELEOP" }),
        row(L("red"), "Enabled in test.", { id: "TEST" }),
      ] },
      { title: "Radio and RSL", rows: [
        row(L(null), "Radio: not used."),
        row(L("amber", "blink"), "RSL: does what the robot signal light does (see RSL).", { s: "RSL: as the robot signal light." }),
      ] },
    ] },
    "SystemCore": { pic: "SystemCore", light: "Power, Mode and Status lights, and a small screen showing its addresses, faults and team number.", source: LIMELIGHT,
      caution: "From Limelight's alpha specification (June 2025, revised October 2025), marked subject to change: the lights may differ on the robots we get. WPILib has no SystemCore light reference yet.",
      groups: [
      { title: "Power", rows: [
        row(L("green"), "Power is good."),
        row(L(null), "No power, or the power connected backwards.", { d: "Check its power wiring and the polarity." }),
      ] },
      { title: "Mode", rows: [
        row(L("yellow"), "On, disabled.", { id: "DISABLED" }),
        row(L("yellow", "blink"), "On and ENABLED: the robot can move.", { id: "enabled" }),
        row(L(null), "No power."),
      ] },
      { title: "Status", rows: [
        row(L(null), "No faults."),
        row(L("red"), "A hardware fault not yet cleared, brownout protection on, or a display fault.",
          { s: "A fault: read its screen.", d: "Read the fault on its screen. A power-rail overcurrent clears when it is power cycled." }),
        row(L("red", "blink"), "A fault in its display.", { s: "Display fault." }),
      ] },
    ] },
    "RSL": { pic: null, light: "The robot signal light: the orange light on the robot that everyone can see.", source: WPILIB, groups: [
      { title: "The light", rows: [
        row(L("orange"), "Robot on, disabled.", { id: "DISABLED" }),
        row(L("orange", "blink"), "Robot on and ENABLED: it can move. Stay clear.", { id: "enabled" }),
        row(L(null), "Robot off, the robot controller not powered, or the light not wired right.", { d: "Robot on and still off: check the light's wires at the robot controller's RSL port." }),
      ] },
    ] },
    "VH-109 radio": { pic: null, light: "Four lights on the end: Power, SYS, 2.4 GHz and 6 GHz.", source: WPILIB, groups: [
      { title: "Power", rows: [
        row(L("green"), "On, or starting up."),
        row(L(null), "No power.", { d: "Check its power: the cable from the Radio Power Module, and the module's own power." }),
      ] },
      { title: "SYS", rows: [
        row(L("green"), "Reaches the field. " + AT_HOME),
        row(L("green", "blink"), "Can't reach the field (blinking once a second). " + AT_HOME,
          { d: "Check the access point radio is on and set up for this team.", go: { netcheck: true } }),
        row(L("green", "fast"), "Its firmware is being written (20 times a second).", { d: "Leave it powered until it finishes." }),
        row(L("green", "fast"), "First boot, after new firmware or a reset (50 times a second).", { d: "Wait." }),
        row(L(null), "Booting up."),
      ] },
      { title: "2.4 GHz", rows: [
        row(L("green"), "Wi-Fi is on."),
        row(L("green", "fast"), "Blinking fast with SYS blinking: it sees a battery, so its Wi-Fi is off.", { d: BATTERY }),
      ] },
      { title: "6 GHz", rows: [
        row(L("blue"), "6 GHz link made."),
        row(L("blue", "fast"), "Blinking fast with SYS blinking: it sees a battery, so its Wi-Fi is off.", { d: BATTERY }),
      ] },
    ] },
    "REV PDH": { pic: "REV PDH", light: "A status light by the CAN connector, and one light beside each channel.", source: WPILIB, groups: [
      { title: "Status", rows: [
        row(L("blue"), "On, not talking to the roboRIO yet.", { d: "Normal until the robot code starts. Staying blue: check the CAN wiring to the PDH.", go: { tab: "wiring" } }),
        row(L("green"), "Talking to the roboRIO."),
        row(L("magenta", "blink"), "Keep-alive timeout: the roboRIO stopped talking to it.", { d: "Check the CAN wiring, and that the robot code is running.", go: { tab: "wiring" } }),
        row(L("cyan"), "Connected to REV Hardware Client."),
        row(L("orange/blue", "blink"), "Low battery.", { d: "Charge or swap the battery.", go: { symptom: "brownout" } }),
        row(L("orange/yellow", "blink"), "CAN fault.", { d: "Check the CAN wiring and the PDH's TERM switch.", go: { tab: "wiring" } }),
        row(L("orange/cyan", "blink"), "Hardware fault."),
        row(L("orange/red", "blink"), "Fail-safe."),
        row(L("orange/magenta", "blink"), "Over current: the whole PDH drew too much."),
      ] },
      { title: "Each channel", rows: [
        row(L(null), "Has voltage and works."),
        row(L("red"), "No voltage, and a fault: a tripped or missing breaker.", { d: "Check that channel's breaker." }),
        row(L("red", "blink"), "A fault earlier (sticky): its breaker tripped.", { d: "Check that channel's breaker." }),
      ] },
    ] },
    "navX": { pic: null, light: "Four lights on the board: 3.3V (red), CAL (orange), and S1 and S2 (green).", source: KAUAI, groups: [
      { title: "Power", rows: [
        row(L("red"), "3.3V on: it has power."),
        row(L(null), "3.3V off: no power.", { d: "On the MXP port: if the roboRIO's Power light is red too, two MXP pins are shorted. Look for a ground pin touching a power or signal pin; the navX's lid prevents it." }),
      ] },
      { title: "CAL, S1 and S2 together", rows: [
        row([L("orange"), L("green"), L("green")], "For about a second after it starts: a light check. Normal.", { n: NAMES, s: "Starting up: a light check." }),
        row([L("orange", "fast"), L(null), L("green")], "Self-test. Staying like this: it isn't still or flat, or a sensor failed.",
          { n: NAMES, s: "Self-test: hold it still and flat.", d: "Hold the robot still with the navX flat, top up. Still like this after several seconds: a sensor chip is faulty." }),
        row([L("orange", "fast"), L(null), L(null)], "Self-test failed: it can't talk to a sensor chip on its own board.",
          { n: NAMES, s: "Self-test failed: hardware.", d: "A hardware fault: replace the navX." }),
        row([L("orange", "slow"), L("green"), L("green")], "The gyro is calibrating.",
          { n: NAMES, s: "Calibrating: keep it still.", d: "Keep the robot still and flat until CAL goes off: about a second on a navX2, up to about 15 s on an older navX.", id: "calibrating" }),
        row([L(null), L("green"), L("green")], "Working normally.", { n: NAMES, s: "Working." }),
        row([L("green", "blink"), L("green", "blink")], "S1 and S2 blinking in turn: sometimes a self-test failure.", { n: ["S1", "S2"], s: "Sometimes a self-test failure." }),
        row(L(null), "S1 off while it runs: no signals from its sensor chips.", { n: ["S1"], s: "No signals from its sensors.", d: "A hardware fault." }),
        row(L(null), "S2 off after it has started: its processor can't talk to its sensor chips.", { n: ["S2"], s: "Can't reach its sensors.", d: "A hardware fault." }),
      ] },
      { title: "CAL, after its CAL button (OmniMount)", rows: [
        row(L("orange", "blink"), "Held 5 s: flashes for a second, then off. OmniMount setup accepted.", { n: ["CAL"], s: "OmniMount setup accepted.", d: "Press RESET to start OmniMount calibration." }),
        row(L("orange", "slow"), "OmniMount calibrating, about 15 s.", { n: ["CAL"], s: "OmniMount calibrating.", d: "Hold still, with one board axis pointing straight up." }),
        row(L("orange", "fast"), "OmniMount error: it's moving, or no board axis points straight up.", { n: ["CAL"], s: "OmniMount: moving, or tilted.", d: "Fix both; CAL changes to a slow flash." }),
        row(L("orange", "blink"), "Held 10 s: a brief flash. Factory gyro recalibration requested.", { n: ["CAL"], s: "Factory recalibration asked for.", d: "Press RESET, then hold it still and level." }),
      ] },
    ] },
    "Canandgyro": { pic: null, light: "One light on the case.", source: REDUX, groups: [
      { title: "The light", rows: [
        row(L("green", "slow"), "Working, and sees the roboRIO on the CAN bus."),
        row(L("red", "slow"), "Doesn't see the roboRIO, or another CAN fault.", { d: "Check its CAN wiring.", go: { tab: "wiring" } }),
        row(L("yellow"), "Calibrating: it works, less accurately until it finishes.", { d: "Keep the robot still until it finishes." }),
        row(L("blue", "blink"), "Firmware update (DFU) in progress."),
        row(L("blue"), "A firmware update failed.", { d: "Update it again with Redux Alchemist." }),
        row(L("red/yellow", "blink"), "Hardware fault.", { d: "Power cycle it. If it comes back, contact Redux Robotics.", id: "hardware fault" }),
        row(L("red/blue", "blink"), "CAN ID conflict: another device has its CAN ID.", { d: "Give one of them a new CAN ID.", id: "CAN ID conflict" }),
      ] },
    ] },
  };
  const ORDER = ["SPARK MAX", "SPARK Flex", "roboRIO", "SystemCore", "RSL", "VH-109 radio", "REV PDH", "navX", "Canandgyro"];

  /** A light drawn as a dot that blinks like the real one (still, half and half, for reduced motion). */
  function dot(l) {
    if (l.p === "off") return `<span class="led off" aria-hidden="true"></span>`;
    const [a, b] = l.c;
    const kind = b ? "alt" : l.p === "solid" ? "solid" : "blink";
    return `<span class="led ${kind} ${l.p}" style="--a:${C[a]};--b:${C[b || a]}" aria-hidden="true"></span>`;
  }
  /** The same in words, which every row carries: colors are hard to tell apart, and some can't. */
  function words(l) {
    if (l.p === "off") return "Off";
    const c = l.c.map((x, i) => i ? x : x[0].toUpperCase() + x.slice(1)).join(" and ");
    return l.c.length > 1 ? `${c}, in turn${TURN[l.p] || ""}` : `${c}, ${WORD[l.p]}`;
  }
  const named = (r, i, w) => r.n && r.n[i] ? `${r.n[i]}: ${w[0].toLowerCase()}${w.slice(1)}` : w;
  const look = r => r.looks.map((l, i) => `<span class="led-look">${dot(l)}<span>${esc(named(r, i, words(l)))}</span></span>`).join("");
  function shortWords(r) {
    if (r.n) return r.looks.map((l, i) => `${r.n[i]} ${l.p === "off" ? "off" : l.p === "solid" ? "on" : SHORT[l.p]}`).join(", ");
    const name = l => l.p === "off" ? "Off" : l.c.map((x, i) => i ? x : x[0].toUpperCase() + x.slice(1)).join("/");
    const same = r.looks.every(l => name(l) === name(r.looks[0]));
    const pat = l => l.p === "off" ? "" : l.c.length > 1 ? "in turn" + (TURN[l.p] || "").replace("slowly", "slow") : SHORT[l.p];
    if (same) return name(r.looks[0]) + (r.looks[0].p === "off" ? "" : ", " + r.looks.map(pat).join(" or "));
    return r.looks.map(l => name(l) + (l.p === "off" ? "" : ", " + pat(l))).join(" or ");
  }
  const NOW = `<span class="chip warn" data-tip="lights.now" data-quiet>now</span>`;
  const lookShort = (r, on) => `<span class="led-look">${r.looks.map(dot).join("")}<span>${esc(shortWords(r))}</span>${on ? NOW : ""}</span>`;

  /**
   * Which rows the robot's state says should be showing now: ``{mode, flags, present}`` (mode
   * from the Live data, flags a controller's fault words, present 0 when it's gone from the bus).
   */
  function nowIds(name, ctx = {}) {
    const ids = new Set();
    const mode = ctx.mode;
    if (name === "roboRIO" && mode) {
      if (mode === "ESTOP") ids.add("estop");
      else if (["DISABLED", "AUTO", "TELEOP", "TEST"].includes(mode)) ids.add(mode);
    }
    if ((name === "RSL" || name === "SystemCore") && mode) ids.add(mode === "DISABLED" ? "DISABLED" : ["AUTO", "TELEOP", "TEST"].includes(mode) ? "enabled" : "");
    const f = String(ctx.flags || "");
    ["CAN fault", "sensor fault", "gate driver fault", "over temperature", "hardware fault", "CAN ID conflict"]
      .forEach(w => { if (f.includes(w)) ids.add(w); });
    if (ctx.present === 0) ids.add("dark");
    ids.delete("");
    return ids;
  }

  /**
   * One device's lights as a table: ``compact`` for a hover card (no what-to-do column), else
   * Troubleshoot's full table with what to do and where to go.
   */
  function table(name, { compact = false, ctx = {} } = {}) {
    const d = DEVICES[name];
    if (!d) return "";
    const now = nowIds(name, ctx);
    const rows = g => g.rows.map(r => {
      const on = r.id && now.has(r.id);
      const go = r.go ? `<button class="btn small" data-light-go='${esc(JSON.stringify(r.go))}' data-tip="lights.go" data-quiet>${
        r.go.tab ? `Open ${esc(r.go.tab[0].toUpperCase() + r.go.tab.slice(1))}` : r.go.netcheck ? "Check the networks" : "Open that symptom"}</button>` : "";
      return `<tr class="${on ? "now" : ""}"><td class="led-cell">${compact ? lookShort(r, on) : look(r) + (on ? `<span class="chip warn" data-tip="lights.now" data-quiet>should show now</span>` : "")}</td>
        <td>${esc(compact ? r.s || r.m : r.m)}</td>
        ${compact ? "" : `<td>${r.d ? esc(r.d) : ""}${go ? `<div>${go}</div>` : ""}</td>`}</tr>`;
    }).join("");
    return `${d.caution ? `<p class="callout warn small lights-caution">${esc(d.caution)}</p>` : ""}<table class="t lights${compact ? " compact" : ""}">${compact ? "" : `<thead><tr><th>Light</th><th>What it means</th><th>What to do</th></tr></thead>`}
      ${d.groups.map(g => `<tbody><tr class="lights-group"><th colspan="${compact ? 2 : 3}">${esc(g.title)}</th></tr>${rows(g)}</tbody>`).join("")}</table>`;
  }
  const source = name => {
    const s = (DEVICES[name] || {}).source;
    return s ? `<a href="${s.url}" target="_blank" rel="noopener">${esc(s.title)}</a>` : "";
  };

  // A card on hover, focus or tap over anything marked data-blink="<device>".
  let pop = null, popFor = null;
  function show(el) {
    const name = el.dataset.blink;
    if (!DEVICES[name]) return;
    if (!pop) {
      pop = document.createElement("div");
      pop.className = "dcard lights-card";
      pop.setAttribute("role", "tooltip");
      document.body.appendChild(pop);
    }
    popFor = el;
    const ctx = el._blinkCtx || {};
    pop.innerHTML = `<div class="dcard-head"><b>${esc(name)}: its status light</b><span class="small muted">${esc(DEVICES[name].light)}</span></div>
      ${table(name, { compact: true, ctx: { mode: liveMode(), ...ctx } })}<p class="dcard-credit">From ${source(name)}.</p>`;
    pop.hidden = false;
    const b = el.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
    let x = b.right + 10;
    if (x + w > innerWidth - 8) x = Math.max(8, b.left - w - 10);
    pop.style.left = x + "px";
    pop.style.top = Math.min(Math.max(8, b.top - 20), innerHeight - h - 8) + "px";
  }
  function hide(el) {
    if (pop && (!el || popFor === el)) { pop.hidden = true; popFor = null; }
  }
  const liveMode = () => (App.connected() && App.live && App.live.live && App.live.live.mode) || null;
  document.addEventListener("mouseover", e => { const el = e.target.closest && e.target.closest("[data-blink]"); if (el && el !== popFor) show(el); });
  document.addEventListener("mouseout", e => { const el = e.target.closest && e.target.closest("[data-blink]"); if (el && !el.contains(e.relatedTarget)) hide(el); });
  document.addEventListener("focusin", e => { const el = e.target.closest && e.target.closest("[data-blink]"); if (el) show(el); });
  document.addEventListener("focusout", e => { const el = e.target.closest && e.target.closest("[data-blink]"); if (el) hide(el); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") hide(); });

  /** Where a row's "go" leads: a symptom, a tab, or the network check. */
  function go(g) {
    if (g.symptom) Trouble.open(g.symptom);
    else if (g.netcheck) App.checkNetworks();
    else if (g.tab) App.show(g.tab);
  }

  return { DEVICES, ORDER, table, dot, words, source, nowIds, go, liveMode, has: name => !!DEVICES[name] };
})();
