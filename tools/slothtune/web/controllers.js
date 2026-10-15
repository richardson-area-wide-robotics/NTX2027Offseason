// Joysticks tab (internally "controllers"): check the drive team's joysticks in the pit - drift, deadband, reach, triggers,
// buttons - from a joystick plugged into this laptop. No robot needed.
"use strict";

(() => {
  const root = $("#tab-controllers");
  const STEPS = [
    { id: "rest", title: "Hands off", secs: 4,
      text: "Put the joystick down flat and don't touch it." },
    { id: "sticks", title: "Circle the sticks", secs: 10,
      text: "Roll both sticks slowly round their edges, pressing outward, three times each." },
    { id: "returns", title: "Flick and let go", secs: 12,
      text: "Push a stick all the way in any direction and let it snap back; wait a moment. Five times with each stick." },
    { id: "triggers", title: "Squeeze the triggers", secs: 6,
      text: "Squeeze both triggers all the way and let go, three times." },
    { id: "buttons", title: "Press every button", secs: 60, manual: true,
      text: "Press each button three times, firmly, one at a time. Each lights while it's held and keeps a green ring once it's seen. Press Done when the line under the drawing says every button is seen." },
  ];
  const BUTTONS = ["A", "B", "X", "Y", "Left bumper", "Right bumper", "Left trigger", "Right trigger", "Back", "Start",
    "Left stick press", "Right stick press", "D-pad up", "D-pad down", "D-pad left", "D-pad right"];
  const WPI = { 0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 8: 7, 9: 8, 10: 9, 11: 10 };
  const DIGITAL = BUTTONS.map((_, i) => i).filter(i => i !== 6 && i !== 7);

  let pad = null, codeDb = [], codeSticks = {}, operator = {}, results = {}, rep = null, rec = null, src = "laptop";
  let recording = null, seen = new Set(), lastTs = -1, poller = null, trails = { left: [], right: [] };

  root.innerHTML = `
    <div class="jobs" data-jobs="controllers">
    ${HowTo.slot("controllers")}
    <div class="job-area">
    <div class="panel" id="ct-check">
      <div class="row" style="justify-content:space-between;flex-wrap:wrap">
        <h2 data-tip="ct.title">Check a joystick</h2>
        <span id="ct-rate" class="small muted"></span>
      </div>
      ${HowTo.steps({ note: "No robot needed: the Driver Station reads the same joystick the same way. Do this for every joystick at the start of an event.",
        steps: ["Plug the joystick into this laptop with USB and press any button on it.",
          "Say which one it is (Driver, Operator, Spare 1): its saved checks are kept under that name.",
          "Run the Steps in order: rest, sticks, return to center, triggers, buttons.",
          "Read the report, then <b>Save the check</b>."],
        good: "drift inside the code's deadband, full reach every way, and no stuck or bouncing button." })}
      <div class="row" style="flex-wrap:wrap;gap:12px">
        <label class="gain" data-tip="ct.src">Read from<select id="ct-src">
          <option value="laptop">This laptop (USB)</option>
          <option value="0">The robot: Driver Station port 0 (driver)</option>
          <option value="1">The robot: Driver Station port 1</option></select></label>
        <label class="gain" id="ct-pad-box" data-tip="ct.pad">Joystick<select id="ct-pad"><option value="">none seen yet</option></select></label>
        <label class="gain" data-tip="ct.label">Which one is it?<input id="ct-label" list="ct-labels" placeholder="Driver, Operator, Spare 1"></label>
        <datalist id="ct-labels"></datalist>
      </div>
      <p id="ct-port-note" class="hint" hidden></p>
      <p id="ct-mapping" class="hint" hidden></p>
      <section class="ct-steps-row">
        <h3 data-tip="ct.steps">Steps</h3>
        <ol id="ct-steps" class="ct-steps" role="list"></ol>
        <div id="ct-step-box"></div>
      </section>
    <div class="ct-cols">
      <section class="ct-live-col">
        <h3 data-tip="ct.live">Live</h3>
        <div class="ct-live">
          <svg id="ct-svg" viewBox="0 0 340 302" role="img" aria-label="Stick positions, with each stick's center zoomed in below"></svg>
        </div>
        <div id="ct-axes" class="small mono"></div>
        <details class="small"><summary>What the drawing shows</summary><p class="hint">Top: the whole stick, with its trail. Below: its center, 5 times bigger.
          <span class="ct-key-code">Dashed outline</span>: what the robot code ignores (<span id="ct-code">no deadband found</span>):
          a circle where the deadband is round (distance from center), a square where each axis has its own.
          <span class="ct-key-rec">Green outline</span>: what this joystick needs, once measured. A button keeps a green ring once it's seen;
          the number by it is the one robot code uses.</p></details>
      </section>
      <section class="ct-pad-col">
        <h3 data-tip="ct.colors">Buttons</h3>
        <svg id="ct-buttons" class="ct-pad" viewBox="0 0 360 214" role="list" aria-label="Buttons, laid out as on an Xbox controller"></svg>
        <p class="small muted ct-pad-key" id="ct-pad-key" aria-live="polite"></p>
      </section>
    </div>
    <section class="ct-report-row">
      <h3 data-tip="ct.report">Report</h3>
      <div id="ct-report"><p class="hint">Run the Steps; the report appears here.</p></div>
      ${HowTo.nextLine("driver")}${HowTo.nextLine("tester")}
    </section>
    </div>
    <div class="panel" id="ct-hist">
      <h3 data-tip="ct.history">Every joystick checked</h3>
      <div id="ct-history"></div>
    </div></div></div>`;

  // ---------------------------------------------------------------- reading the joystick
  function pads() { return Array.from(navigator.getGamepads ? navigator.getGamepads() : []).filter(Boolean); }
  function current() { return pads().find(p => p.index === pad) || null; }

  function listPads() {
    const sel = $("#ct-pad", root), list = pads();
    const want = pad;
    sel.innerHTML = list.length ? list.map(p => `<option value="${p.index}">${p.index}: ${esc(p.id)}</option>`).join("")
      : `<option value="">none seen yet: press a button on it</option>`;
    if (list.length && !list.some(p => p.index === want)) pad = list[0].index;
    if (list.length) sel.value = String(pad);
    const p = current();
    const m = $("#ct-mapping", root);
    m.hidden = !p || p.mapping === "standard";
    m.textContent = p && p.mapping !== "standard"
      ? "This joystick isn't in the browser's standard layout, so the names below may be wrong. An Xbox joystick is." : "";
  }

  function row(p) {
    return [p.timestamp || performance.now(), ...[0, 1, 2, 3].map(i => p.axes[i] || 0),
      ...BUTTONS.map((_, i) => (p.buttons[i] ? p.buttons[i].value : 0))];
  }

  function poll() {
    const p = current();
    if (!p || p.timestamp === lastTs) return;
    lastTs = p.timestamp;
    const r = row(p);
    if (recording) {
      recording.rows.push(r);
      if (recording.step.id === "buttons") {
        DIGITAL.forEach(i => { if (r[5 + i] >= 0.5) seen.add(i); });
      }
    }
  }

  // ---------------------------------------------------------------- drawing
  function stickSvg(cx, x, y, trail, label, key) {
    const R = 62, cy = 80;
    const mine = codeSticks[key];
    const code = mine ? mine.value : null, round = !!(mine && mine.round);
    const pts = trail.map(([a, b]) => `${(cx + a * R).toFixed(1)},${(cy + b * R).toFixed(1)}`).join(" ");
    // The center, 5x: a 0.1 deadband is 6 px at full size, hidden under the dot; here it is 31 px.
    const S = 5 * R, H = 0.15, zy = 228, clamp = v => Math.max(-H, Math.min(H, v));
    // A round deadband ignores a circle round the center; a per-axis one, a square.
    const zsq = (d, cls) => round ? `<circle cx="${cx}" cy="${zy}" r="${d * S}" class="${cls}"/>`
      : `<rect x="${cx - d * S}" y="${zy - d * S}" width="${2 * d * S}" height="${2 * d * S}" class="${cls}"/>`;
    const zpts = trail.filter(([a, b]) => Math.abs(a) < H * 1.3 && Math.abs(b) < H * 1.3)
      .map(([a, b]) => `${(cx + clamp(a) * S).toFixed(1)},${(zy + clamp(b) * S).toFixed(1)}`).join(" ");
    return `<circle cx="${cx}" cy="${cy}" r="${R}" class="ct-ring"/>
      <line x1="${cx - R}" x2="${cx + R}" y1="${cy}" y2="${cy}" class="ct-axis"/><line x1="${cx}" x2="${cx}" y1="${cy - R}" y2="${cy + R}" class="ct-axis"/>
      <polyline points="${pts}" class="ct-trail"/>
      <circle cx="${cx + x * R}" cy="${cy + y * R}" r="6" class="ct-dot"/>
      <text x="${cx}" y="160" text-anchor="middle" class="ct-label">${label}</text>
      <rect x="${cx - H * S}" y="${zy - H * S}" width="${2 * H * S}" height="${2 * H * S}" rx="6" class="ct-zoom"/>
      <line x1="${cx - H * S}" x2="${cx + H * S}" y1="${zy}" y2="${zy}" class="ct-axis"/><line x1="${cx}" x2="${cx}" y1="${zy - H * S}" y2="${zy + H * S}" class="ct-axis"/>
      ${code ? zsq(code, "ct-code") : ""}
      ${rec ? zsq(rec, "ct-rec") : ""}
      <polyline points="${zpts}" class="ct-trail"/>
      ${Math.abs(x) <= H && Math.abs(y) <= H ? `<circle cx="${cx + x * S}" cy="${zy + y * S}" r="4" class="ct-dot"/>` : ""}
      <text x="${cx}" y="296" text-anchor="middle" class="ct-label">center, 5×</text>`;
  }

  // The buttons, drawn where they are on an Xbox controller (browser button numbers: 0 A, 1 B,
  // 2 X, 3 Y, 4 LB, 5 RB, 6 LT, 7 RT, 8 Back, 9 Start, 10 and 11 the stick presses, 12-15 the
  // D-pad). Built once; only their classes change, 60 times a second, so a focus or tip on one
  // survives. A press lights in the joystick's color: the driver's blue, the tester's orange.
  const PAD = (() => {
    const btn = (i, shape, lx, ly, text, nx, ny, caption) => ({ i, shape, lx, ly, text, nx, ny, caption });
    const c = (cx, cy, r) => `<circle cx="${cx}" cy="${cy}" r="${r}" class="ct-btn"/>`;
    const rr = (x, y, w, h, r) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" class="ct-btn"/>`;
    return [
      btn(4, rr(58, 26, 74, 14, 7), 95, 37, "LB", 140, 37),
      btn(5, rr(228, 26, 74, 14, 7), 265, 37, "RB", 220, 37),
      btn(10, c(98, 84, 21), 98, 88, "L3", 72, 112),
      btn(11, c(226, 132, 19), 226, 136, "R3", 252, 160),
      btn(8, c(150, 84, 8), 150, 104, "Back", 150, 70, true),
      btn(9, c(210, 84, 8), 210, 104, "Start", 210, 70, true),
      btn(3, c(264, 64, 10), 264, 68, "Y", 280, 56),
      btn(2, c(244, 84, 10), 244, 88, "X", 228, 76),
      btn(1, c(284, 84, 10), 284, 88, "B", 300, 76),
      btn(0, c(264, 104, 10), 264, 108, "A", 280, 116),
      btn(12, rr(126, 112, 16, 18, 3), 134, 125, "▲", null, null),
      btn(13, rr(126, 146, 16, 18, 3), 134, 159, "▼", null, null),
      btn(14, rr(108, 130, 18, 16, 3), 117, 142, "◀", null, null),
      btn(15, rr(142, 130, 18, 16, 3), 151, 142, "▶", null, null),
    ];
  })();
  function buildButtons() {
    const body = `<path class="ct-body" d="M95 46 L265 46 C298 46 318 62 326 92 L344 170 C350 196 330 212 312 202 C296 194 286 178 270 164
      L90 164 C74 178 64 194 48 202 C30 212 10 196 16 170 L34 92 C42 62 62 46 95 46 Z"/>`;
    // The triggers, above the bumpers: filled as far as they are squeezed.
    const trig = (i, x, label) => `<g role="listitem" aria-label="${label}" data-b="${i}" data-tip="ct.trig" data-quiet>
      <rect x="${x}" y="2" width="34" height="20" rx="5" class="ct-btn"/>
      <rect x="${x}" y="2" width="34" height="0" rx="5" class="ct-trig-fill" id="ct-${label.toLowerCase()}"/>
      <text x="${x + 17}" y="16" text-anchor="middle" class="ct-btn-text">${label}</text></g>`;
    const buttons = PAD.map(b => `<g role="listitem" aria-label="${esc(BUTTONS[b.i])}${WPI[b.i] ? `, button ${WPI[b.i]}` : ""}" data-b="${b.i}"
      ${WPI[b.i] ? `data-tip="ct.button"` : `data-tip="ct.dpad"`} data-quiet>${b.shape}
      <text x="${b.lx}" y="${b.ly}" text-anchor="middle" class="${b.caption ? "ct-btn-cap" : "ct-btn-text"}">${b.text}</text>
      ${WPI[b.i] && b.nx != null ? `<text x="${b.nx}" y="${b.ny}" text-anchor="middle" class="ct-btn-num">${WPI[b.i]}</text>` : ""}</g>`).join("");
    $("#ct-buttons", root).innerHTML = body + trig(6, 78, "LT") + trig(7, 248, "RT") + buttons;
  }

  // Whose joystick this is: the driver's (its port, or "Driver" in its name) or the tester's or
  // an operator's. Their presses light in different colors; unnamed ones in ink.
  function role() {
    const { drive, deadman } = ports();
    const label = ($("#ct-label", root).value || "").toLowerCase();
    if (src !== "laptop") return +src === drive ? "driver" : +src === deadman ? "operator" : "";
    if (/driv/.test(label)) return "driver";
    if (/operat|test|deadman|co-?pilot/.test(label)) return "operator";
    return "";
  }
  // Names the robot sends in its live line, "Pressed now: A, D-pad up".
  function robotPressed() {
    const msg = (((App.live || {}).status) || {}).message || (App.state.status || {}).message || "";
    if (!msg.startsWith("Pressed now:")) return new Set();
    const names = msg.slice(12).split(",").map(s => s.trim());
    return new Set(DIGITAL.filter(i => names.includes(BUTTONS[i])));
  }

  function paint() {
    if (!root.classList.contains("on")) return;
    const p = current();
    const a = p ? [0, 1, 2, 3].map(i => p.axes[i] || 0) : [0, 0, 0, 0];
    for (const [k, i] of [["left", 0], ["right", 2]]) {
      trails[k].push([a[i], a[i + 1]]);
      if (trails[k].length > 60) trails[k].shift();
    }
    $("#ct-svg", root).innerHTML = stickSvg(85, a[0], a[1], trails.left, "Left stick", "left") + stickSvg(255, a[2], a[3], trails.right, "Right stick", "right");
    const b = i => (p && p.buttons[i] ? p.buttons[i].value : 0);
    if (!$("#ct-buttons [data-b]", root)) buildButtons();
    for (const [id, i] of [["#ct-lt", 6], ["#ct-rt", 7]]) {
      const v = Math.max(0, Math.min(1, b(i))), el = $(id, root);
      if (el) { el.setAttribute("height", (20 * v).toFixed(1)); el.setAttribute("y", (22 - 20 * v).toFixed(1)); }
    }
    $("#ct-axes", root).textContent = p
      ? `Left X ${fmt(a[0], 3)}  Y ${fmt(a[1], 3)} · Right X ${fmt(a[2], 3)}  Y ${fmt(a[3], 3)} · LT ${fmt(b(6), 2)}  RT ${fmt(b(7), 2)}`
      : "No joystick yet.";
    const viaRobot = recording && recording.robot ? robotPressed() : null;
    if (viaRobot) viaRobot.forEach(i => seen.add(i));
    const pad = $("#ct-buttons", root), who = role();
    pad.classList.toggle("role-driver", who === "driver");
    pad.classList.toggle("role-operator", who === "operator");
    $$("#ct-buttons [data-b]", root).forEach(c => {
      // A trigger shows how far it is squeezed in its own fill; the others light when pressed.
      const i = +c.dataset.b, down = i !== 6 && i !== 7 && (viaRobot ? viaRobot.has(i) : b(i) >= 0.5);
      c.classList.toggle("down", down);
      c.classList.toggle("seen", seen.has(i));
    });
    paintKey(who);
  }

  // The line under the drawing says in words what its colors say: whose joystick it is and, while
  // the buttons are being checked, which are still to press. Written only when it changes.
  let keyWas = "";
  function paintKey(who) {
    const whom = who === "driver" ? `<b class="ct-key-driver">Driver's joystick</b>: presses light blue.`
      : who === "operator" ? `<b class="ct-key-operator">Tester's or operator's joystick</b>: presses light orange.`
      : `<b>Not named yet</b>: presses fill solid. Say which one it is above to color them.`;
    const left = DIGITAL.filter(i => !seen.has(i));
    const checking = recording && recording.step.id === "buttons";
    const todo = !checking ? " Green ring: seen. Numbers: as robot code counts them."
      : left.length ? ` Still to press (${left.length}): ${left.map(i => esc(BUTTONS[i])).join(", ")}.` : " <b>Every button seen.</b>";
    const html = whom + todo;
    if (html !== keyWas) { keyWas = html; $("#ct-pad-key", root).innerHTML = html; }
  }

  function frame() { paint(); requestAnimationFrame(frame); }

  // ---------------------------------------------------------------- steps
  function paintSteps() {
    $("#ct-steps", root).innerHTML = STEPS.map(s => {
      const r = results[s.id];
      const bad = r && r.findings.some(f => f.level === "error"), warn = r && r.findings.some(f => f.level === "warn");
      return `<li><button class="btn ${recording && recording.step.id === s.id ? "primary" : ""}" data-step="${s.id}" data-tip="ct.step.${s.id}"
        ${recording ? "disabled" : ""}>${esc(s.title)}</button>
        ${r ? `<span class="chip ${bad ? "bad" : warn ? "warn" : "good"}">${bad ? "problem" : warn ? "check" : "ok"}</span>` : ""}</li>`;
    }).join("");
    $$("[data-step]", root).forEach(b => b.onclick = () => start(STEPS.find(s => s.id === b.dataset.step)));
  }

  function start(step) {
    if (src !== "laptop") return startRobot(step);
    if (!current()) { App.toast("Plug in a joystick and press a button on it first."); return; }
    recording = { step, rows: [], t0: performance.now() };
    if (step.id === "buttons") seen = new Set();
    const box = $("#ct-step-box", root);
    box.innerHTML = `<p><b>${esc(step.title)}.</b> ${esc(step.text)}</p>
      <div class="bar"><div id="ct-bar"></div></div>
      <div class="row">${step.manual ? `<button class="btn primary" id="ct-done" data-tip="ct.done">Done</button>` : ""}
        <button class="btn" id="ct-cancel" data-tip="ct.cancel">Cancel</button></div>`;
    if (step.manual) $("#ct-done", box).onclick = finish;
    $("#ct-cancel", box).onclick = () => { recording = null; box.innerHTML = ""; paintSteps(); };
    paintSteps();
    const tick = () => {
      if (!recording || recording.step !== step) return;
      const f = (performance.now() - recording.t0) / (step.secs * 1000);
      const bar = $("#ct-bar", root);
      if (bar) bar.style.width = Math.min(100, f * 100).toFixed(0) + "%";
      if (f >= 1) finish(); else setTimeout(tick, 100);
    };
    tick();
  }

  // Through the robot: the robot records the Driver Station port (disabled) and the laptop judges it.
  async function startRobot(step) {
    if (!App.connected()) { App.toast("Connect to the robot first."); return; }
    recording = { step, rows: [], t0: performance.now(), robot: true };
    if (step.id === "buttons") seen = new Set();
    const box = $("#ct-step-box", root);
    box.innerHTML = `<p><b>${esc(step.title)}.</b> ${esc(step.text)}</p>
      <p class="small muted">The robot is recording what the Driver Station sends on port ${src}. Keep it disabled.${step.id === "buttons" ? " Each button lights as the robot sees it." : ""}</p>
      <div class="bar"><div id="ct-bar"></div></div>
      <div class="row">${step.manual ? `<button class="btn primary" id="ct-done" data-tip="ct.done">Done</button>` : ""}</div>`;
    if (step.manual) $("#ct-done", box).onclick = () => App.api("/api/stop", {});
    paintSteps();
    const secs = step.manual ? 30 : step.secs;
    const tick = () => {
      if (!recording || recording.step !== step) return;
      const bar = $("#ct-bar", root);
      if (bar) bar.style.width = Math.min(100, (performance.now() - recording.t0) / (secs * 10)).toFixed(0) + "%";
      setTimeout(tick, 100);
    };
    tick();
    const r = await App.api("/api/controllers/robot", { step: step.id, port: +src, secs });
    recording = null;
    show(step, r);
  }

  async function finish() {
    if (!recording) return;
    const { step, rows } = recording;
    recording = null;
    show(step, await App.api("/api/controllers/step", { step: step.id, samples: rows }));
  }

  async function show(step, r) {
    const box = $("#ct-step-box", root);
    if (!r.ok) { box.innerHTML = `<p class="hint">${esc(r.error)}</p>`; paintSteps(); return; }
    results[step.id] = r;
    if (A_finite(r.interval_ms)) $("#ct-rate", root).textContent = r.source === "robot"
      ? `The robot gets the joystick every ${fmt(r.interval_ms, 1)} ms${r.name ? ` (${r.name})` : ""}`
      : `This laptop sees the joystick every ${fmt(r.interval_ms, 1)} ms`;
    box.innerHTML = r.findings.length ? r.findings.map(f => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span>
      <span class="title">${esc(f.title)}</span></div><div class="why">${esc(f.why)}</div></div>`).join("")
      : `<p class="small">${esc(step.title)}: nothing wrong.</p>`;
    const next = STEPS[STEPS.indexOf(step) + 1];
    if (next) box.innerHTML += `<div class="row"><button class="btn primary" id="ct-next" data-tip="ct.next">Next: ${esc(next.title)}</button></div>`;
    if (next) $("#ct-next", box).onclick = () => start(next);
    paintSteps();
    await report();
  }

  function A_finite(x) { return typeof x === "number" && isFinite(x); }

  async function report() {
    rep = await App.api("/api/controllers/report", { steps: results });
    rec = rep.recommended_deadband;
    const box = $("#ct-report", root);
    const done = STEPS.filter(s => results[s.id]).length;
    const code = codeDb.length ? Math.min(...codeDb.map(d => d.value)) : null;
    box.innerHTML = `
      <div class="row" style="gap:16px;flex-wrap:wrap">
        <span class="chip ${rep.verdict === "error" ? "bad" : rep.verdict === "warn" ? "warn" : "good"}">${rep.verdict === "error" ? "don't use in a match" : rep.verdict === "warn" ? "check the notes" : "good"}</span>
        <span>Drift <b class="mono">${A_finite(rep.worst_offset) ? fmt(rep.worst_offset, 3) : "–"}</b>
          <span class="small muted">${Object.entries(rep.round_deadbands || {}).map(([n]) => `${esc(n)} stick from center ${fmt((rep.stick_drift || {})[n], 2)}`)
            .concat(Object.entries(rep.axis_drift || {}).map(([n, v]) => `${esc(n)} ${fmt(v, 2)}`)).join(" · ")}</span></span>
        <span>Needs a deadband of <b class="mono">${rec != null ? fmt(rec, 2) : "–"}</b></span>
        <span>The code uses <b class="mono">${code != null ? code : "none found"}</b></span>
        <span class="small muted">${done} of ${STEPS.length} steps</span>
      </div>
      ${rep.findings.map(f => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span>
        <span class="title">${esc(f.title)}</span></div><div class="why">${f.learn ? Learn.link(f.why, 2) : esc(f.why)}</div></div>`).join("")}
      <div class="row"><button class="btn primary" id="ct-save" ${done ? "" : "disabled"} data-tip="ct.save">Save this check</button>
        <span class="small muted">Saved checks show which joysticks are wearing out.</span></div>`;
    $("#ct-save", box).onclick = save;
  }

  async function save() {
    const p = current();
    const device = src === "laptop" ? (p ? p.id : "") : `through the robot, port ${src}`;
    const r = await App.api("/api/controllers/save", { label: $("#ct-label", root).value, device, report: rep });
    if (!r.ok) { App.toast(r.error); return; }
    App.toast(`Saved: ${r.entry.label}.`);
    history();
    HowTo.paint("controllers");
  }

  async function history() {
    const h = (await App.api("/api/controllers/history")).history || [];
    $("#ct-labels", root).innerHTML = [...new Set(h.map(e => e.label))].map(l => `<option value="${esc(l)}">`).join("");
    const when = s => { const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(s || ""); return m ? `${+m[2]}/${+m[3]} ${m[4]}:${m[5]}` : ""; };
    $("#ct-history", root).innerHTML = h.length ? `<div class="tblwrap"><table class="t"><thead><tr><th>Joystick</th><th>When</th>
      <th data-tip="ct.h-drift" data-quiet>Drift</th><th data-tip="ct.h-deadband" data-quiet>Deadband needed</th><th></th><th>Problems</th></tr></thead><tbody>
      ${h.slice().reverse().map(e => `<tr><td>${esc(e.label)}</td><td class="small">${esc(when(e.when))}</td>
        <td class="num">${A_finite(e.worst_offset) ? fmt(e.worst_offset, 3) : "–"}</td><td class="num">${e.recommended_deadband != null ? fmt(e.recommended_deadband, 2) : "–"}</td>
        <td><span class="chip ${e.verdict === "error" ? "bad" : e.verdict === "warn" ? "warn" : "good"}">${e.verdict === "error" ? "problem" : e.verdict === "warn" ? "check" : "good"}</span></td>
        <td class="small">${esc((e.problems || []).join("; "))}</td></tr>`).join("")}</tbody></table></div>`
      : `<p class="hint">None saved yet.</p>`;
  }

  async function loadCode() {
    const r = await App.api("/api/controllers/code");
    codeDb = r.deadbands || [];
    codeSticks = r.sticks || {};
    const where = [...new Set(codeDb.map(d => `${d.value} in ${d.file}`))].join(", ");
    $("#ct-code", root).textContent = where || "no deadband found in the robot code";
    operator = r.operator || {};
    const { drive, deadman, button } = ports();
    for (const p of [0, 1]) {
      const o = $(`#ct-src option[value="${p}"]`, root);
      if (o) o.textContent = `The robot: Driver Station port ${p}` + (p === drive ? " (driver)" : p === deadman ? ` (deadman: button ${button})` : "");
    }
    portNote();
  }

  // slothtune.json "operator": the driver's port, and the port and button that hold a test's deadman.
  function ports() {
    const n = (v, d) => Number.isInteger(v) ? v : d;
    return { drive: n(operator.driverPort, 0), deadman: n(operator.deadmanPort, 1), button: n(operator.deadmanButton, 6) };
  }

  // The deadman joystick matters to the tests for one button only: say so, so nobody fails it
  // for a drifting stick the drivetrain never reads.
  function portNote() {
    const { drive, deadman, button } = ports();
    const label = ($("#ct-label", root).value || "").toLowerCase();
    const isDeadman = deadman !== drive && (src === String(deadman) || label.includes("deadman"));
    const el = $("#ct-port-note", root);
    el.hidden = !isDeadman;
    if (isDeadman) {
      el.textContent = `Port ${deadman} is the deadman joystick: the swerve tests read only button ${button}`
        + `${button === 6 ? " (the right bumper)" : ""}. Hold it and a test runs; let go and it stops. Its sticks`
        + " never move the drivetrain, so check them only if the robot code uses this joystick for something else.";
    }
  }

  $("#ct-pad", root).onchange = e => { pad = +e.target.value; trails = { left: [], right: [] }; listPads(); };
  $("#ct-label", root).addEventListener("input", portNote);
  $("#ct-src", root).onchange = e => {
    src = e.target.value;
    portNote();
    $("#ct-pad-box", root).hidden = src !== "laptop";
    results = {}; rep = null; rec = null;
    $("#ct-report", root).innerHTML = `<p class="hint">Run the steps above; the report appears here.</p>`;
    $("#ct-step-box", root).innerHTML = src === "laptop" ? "" : `<p class="hint">Through the robot: plug the joystick
      into the Driver Station laptop, connect this app to the robot, keep the robot disabled. The live view still shows
      a joystick plugged into this laptop, if any.</p>`;
    paintSteps();
  };
  window.addEventListener("gamepadconnected", listPads);
  window.addEventListener("gamepaddisconnected", listPads);
  App.on("tab", t => {
    if (t !== "controllers") return;
    listPads(); loadCode(); history(); paintSteps();
    if (!poller) poller = setInterval(poll, 4);
  });
  App.on("lint", loadCode);  // sent after the robot project changes
  paintSteps();
  requestAnimationFrame(frame);
})();
