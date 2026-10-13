// Controllers tab: check the drive team's controllers in the pit - drift, deadband, reach, triggers,
// buttons - from a controller plugged into this laptop. No robot needed.
"use strict";

(() => {
  const root = $("#tab-controllers");
  const STEPS = [
    { id: "rest", title: "Hands off", secs: 4,
      text: "Put the controller down flat and don't touch it." },
    { id: "sticks", title: "Circle the sticks", secs: 10,
      text: "Roll both sticks slowly round their edges, pressing outward, three times each." },
    { id: "returns", title: "Flick and let go", secs: 12,
      text: "Push a stick all the way in any direction and let it snap back; wait a moment. Five times with each stick." },
    { id: "triggers", title: "Squeeze the triggers", secs: 6,
      text: "Squeeze both triggers all the way and let go, three times." },
    { id: "buttons", title: "Press every button", secs: 60, manual: true,
      text: "Press each button three times, firmly, one at a time. Each lights up when it's seen. Press Done when they're all lit." },
  ];
  const BUTTONS = ["A", "B", "X", "Y", "Left bumper", "Right bumper", "Left trigger", "Right trigger", "Back", "Start",
    "Left stick press", "Right stick press", "D-pad up", "D-pad down", "D-pad left", "D-pad right"];
  const WPI = { 0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 8: 7, 9: 8, 10: 9, 11: 10 };
  const DIGITAL = BUTTONS.map((_, i) => i).filter(i => i !== 6 && i !== 7);

  let pad = null, codeDb = [], codeSticks = {}, results = {}, rep = null, rec = null, src = "laptop";
  let recording = null, seen = new Set(), lastTs = -1, poller = null, trails = { left: [], right: [] };

  root.innerHTML = `
    <div class="panel">
      <div class="row" style="justify-content:space-between;flex-wrap:wrap">
        <h2 data-tip="ct.title">Check a controller</h2>
        <span id="ct-rate" class="small muted"></span>
      </div>
      <p class="small">Plug the controller into this laptop with USB and press any button on it. No robot needed: the
        Driver Station reads the same controller the same way. Do this for every controller at the start of an event.</p>
      <div class="row" style="flex-wrap:wrap;gap:12px">
        <label class="gain" data-tip="ct.src">Read from<select id="ct-src">
          <option value="laptop">This laptop (USB)</option>
          <option value="0">The robot: Driver Station port 0 (driver)</option>
          <option value="1">The robot: Driver Station port 1</option></select></label>
        <label class="gain" id="ct-pad-box" data-tip="ct.pad">Controller<select id="ct-pad"><option value="">none seen yet</option></select></label>
        <label class="gain" data-tip="ct.label">Which one is it?<input id="ct-label" list="ct-labels" placeholder="Driver, Operator, Spare 1"></label>
        <datalist id="ct-labels"></datalist>
      </div>
      <p id="ct-mapping" class="hint" hidden></p>
    </div>
    <div class="grid2" style="margin-top:12px">
      <div class="panel">
        <h3 data-tip="ct.live">Live</h3>
        <div class="ct-live">
          <svg id="ct-svg" viewBox="0 0 340 302" role="img" aria-label="Stick positions, with each stick's center zoomed in below"></svg>
          <div class="ct-trig" role="group" aria-label="Triggers" data-tip="ct.trig" data-quiet><div><b><i id="ct-lt"></i></b><span>LT (axis 2)</span></div><div><b><i id="ct-rt"></i></b><span>RT (axis 3)</span></div></div>
        </div>
        <div id="ct-axes" class="small mono"></div>
        <div id="ct-buttons" class="ct-buttons" role="list" aria-label="Buttons"></div>
        <p class="hint">Top: the whole stick, with its trail. Below: its center, 5 times bigger.
          <span class="ct-key-code">Dashed outline</span>: what the robot code ignores (<span id="ct-code">no deadband found</span>):
          a circle where the deadband is round (distance from center), a square where each axis has its own.
          <span class="ct-key-rec">Green outline</span>: what this controller needs, once measured. A button turns green with ✓ once seen;
          the number is the one robot code uses.</p>
      </div>
      <div class="panel">
        <h3 data-tip="ct.steps">Steps</h3>
        <ol id="ct-steps" class="ct-steps" role="list"></ol>
        <div id="ct-step-box"></div>
      </div>
    </div>
    <div class="panel" style="margin-top:12px">
      <h3 data-tip="ct.report">Report</h3>
      <div id="ct-report"><p class="hint">Run the steps above; the report appears here.</p></div>
    </div>
    <div class="panel" style="margin-top:12px">
      <h3 data-tip="ct.history">Every controller checked</h3>
      <div id="ct-history"></div>
    </div>`;

  // ---------------------------------------------------------------- reading the controller
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
      ? "This controller isn't in the browser's standard layout, so the names below may be wrong. An Xbox controller is." : "";
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

  // The button chips are built once and only their classes change, 60 times a second: rebuilding
  // them every frame would throw away any focus or tip on them.
  function buildButtons() {
    $("#ct-buttons", root).innerHTML = DIGITAL.map(i => `<span class="chip" role="listitem" data-b="${i}" ${WPI[i] ? `data-tip="ct.button"` : `data-tip="ct.dpad"`} data-quiet>
      ${esc(BUTTONS[i])}${WPI[i] ? ` <span class="muted">${WPI[i]}</span>` : ""}</span>`).join("");
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
    $("#ct-lt", root).style.height = (b(6) * 100).toFixed(0) + "%";
    $("#ct-rt", root).style.height = (b(7) * 100).toFixed(0) + "%";
    $("#ct-axes", root).textContent = p
      ? `Left X ${fmt(a[0], 3)}  Y ${fmt(a[1], 3)} · Right X ${fmt(a[2], 3)}  Y ${fmt(a[3], 3)} · LT ${fmt(b(6), 2)}  RT ${fmt(b(7), 2)}`
      : "No controller yet.";
    const viaRobot = recording && recording.robot ? robotPressed() : null;
    if (viaRobot) viaRobot.forEach(i => seen.add(i));
    if (!$("#ct-buttons [data-b]", root)) buildButtons();
    $$("#ct-buttons [data-b]", root).forEach(c => {
      const i = +c.dataset.b, down = viaRobot ? viaRobot.has(i) : b(i) >= 0.5;
      c.classList.toggle("down", down);
      c.classList.toggle("seen", seen.has(i));
    });
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
    if (!current()) { App.toast("Plug in a controller and press a button on it first."); return; }
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
      ? `The robot gets the controller every ${fmt(r.interval_ms, 1)} ms${r.name ? ` (${r.name})` : ""}`
      : `This laptop sees the controller every ${fmt(r.interval_ms, 1)} ms`;
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
        <span class="small muted">Saved checks show which controllers are wearing out.</span></div>`;
    $("#ct-save", box).onclick = save;
  }

  async function save() {
    const p = current();
    const device = src === "laptop" ? (p ? p.id : "") : `through the robot, port ${src}`;
    const r = await App.api("/api/controllers/save", { label: $("#ct-label", root).value, device, report: rep });
    if (!r.ok) { App.toast(r.error); return; }
    App.toast(`Saved: ${r.entry.label}.`);
    history();
  }

  async function history() {
    const h = (await App.api("/api/controllers/history")).history || [];
    $("#ct-labels", root).innerHTML = [...new Set(h.map(e => e.label))].map(l => `<option value="${esc(l)}">`).join("");
    const when = s => { const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(s || ""); return m ? `${+m[2]}/${+m[3]} ${m[4]}:${m[5]}` : ""; };
    $("#ct-history", root).innerHTML = h.length ? `<div class="tblwrap"><table class="t"><thead><tr><th>Controller</th><th>When</th>
      <th>Drift</th><th>Deadband needed</th><th></th><th>Problems</th></tr></thead><tbody>
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
  }

  $("#ct-pad", root).onchange = e => { pad = +e.target.value; trails = { left: [], right: [] }; listPads(); };
  $("#ct-src", root).onchange = e => {
    src = e.target.value;
    $("#ct-pad-box", root).hidden = src !== "laptop";
    results = {}; rep = null; rec = null;
    $("#ct-report", root).innerHTML = `<p class="hint">Run the steps above; the report appears here.</p>`;
    $("#ct-step-box", root).innerHTML = src === "laptop" ? "" : `<p class="hint">Through the robot: plug the controller
      into the Driver Station laptop, connect this app to the robot, keep the robot disabled. The live view still shows
      a controller plugged into this laptop, if any.</p>`;
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
