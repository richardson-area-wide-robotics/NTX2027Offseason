// Core of the Swerve Tools page: talking to the local server, the header, the environment, the
// deadman, polling, and the shared helpers every tab uses.
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, d = 2) => (v == null || !isFinite(v)) ? "–" : Number(v).toFixed(d);
const ABBR = { frontleft: "FL", frontright: "FR", backleft: "BL", backright: "BR" };
const abbr = n => ABBR[n] || n;
// One word for each place the robot can be, used by every screen (the robot's own names are
// UNSET, BLOCKS, FIELD and SIM; "FIELD" means the shop floor, not the competition field).
const WHERE = { UNSET: "Where: not set", BLOCKS: "On blocks", FIELD: "On the floor", SIM: "Simulator",
  DISABLED: "Robot disabled", ANY: "Anywhere", PRACTICE: "Practice pod" };
const whereWord = k => WHERE[k] || k;
const TEST_NAME = { steer_step: "Steering", drive_step: "Drive speed", drive_ff: "Feedforward", slip: "Slip current",
  spin: "Spin", straight: "Straight line", capture: "Sensor capture", pdh_map: "PDH port finder",
  moi: "Moment of inertia", controller: "Controller check", spin_ff: "Spin feedforward" };
const testName = k => TEST_NAME[k] || k;

const App = {
  state: {}, live: null, lint: null, listeners: {},

  on(evt, fn) { (this.listeners[evt] = this.listeners[evt] || []).push(fn); },
  emit(evt, data) { (this.listeners[evt] || []).forEach(fn => { try { fn(data); } catch (e) { console.error(e); } }); },

  // This run's token, from the page the tool served: every change sends it back (server.py).
  token: (document.querySelector('meta[name="swervetune-token"]') || {}).content || "",

  async api(path, body) {
    const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-SwerveTune-Token": this.token }, body: JSON.stringify(body) };
    const r = await fetch(path, opt);
    const j = await r.json().catch(() => ({ ok: false, error: "The tool's server sent something unreadable." }));
    if (!r.ok && j.ok === undefined) j.ok = false;
    return j;
  },

  toast(msg, ms = 3200) {
    const t = $("#toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(this._toast);
    this._toast = setTimeout(() => { t.hidden = true; }, ms);
  },

  modal(html, mount) {
    $("#modal-body").innerHTML = html;
    $("#modal").hidden = false;
    if (mount) mount($("#modal-body"));
    // [autofocus] picks what gets focus; [data-nofocus] means nothing should look chosen yet.
    const first = $("#modal-body [autofocus]") || $("#modal-body button, #modal-body input");
    if (first && !$("#modal-body [data-nofocus]")) first.focus();
  },
  closeModal() { $("#modal").hidden = true; $("#modal-body").innerHTML = ""; },

  show(tab) {
    $$(".tabs button").forEach(b => {
      b.classList.toggle("on", b.dataset.tab === tab);
      if (b.dataset.tab === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    $$(".tab").forEach(s => s.classList.toggle("on", s.id === "tab-" + tab));
    try { localStorage.setItem("swervetune.tab", tab); } catch (e) { /* storage blocked */ }
    this.emit("tab", tab);
  },

  connected() { return !!(this.state && this.state.connected); },
  env() { return (this.state.environment && this.state.environment.active) || "UNSET"; },
  modules() { return (this.state.robot && this.state.robot.modules) || ["frontleft", "frontright", "backleft", "backright"]; },
  gains() { return this.state.gains || {}; },

  // Runs a test on the robot and resolves with the saved run (channels + report).
  async runTest(test, module = "ALL", args = {}) {
    if (!this.connected()) throw new Error("Connect to a robot (or the simulator) first.");
    const r = await this.api("/api/test", { test, module, args });
    if (!r.ok) throw new Error(r.message || r.error);
    for (;;) {
      await new Promise(res => setTimeout(res, 150));
      const st = await this.api("/api/state");
      this.state = st;
      const t = st.test || {};
      if (!t.running) {
        if (t.state === "REFUSED" || t.state === "ERROR") throw new Error(t.message);
        if (!t.run) throw new Error(t.message || "The robot returned no data.");
        const doc = await this.api("/api/runs/" + encodeURIComponent(t.run));
        doc._file = t.run;
        this.emit("run", doc);
        return doc;
      }
    }
  },

  async previewAndSave(body, title) {
    const p = await this.api("/api/save/preview", body);
    if (!p.ok) { this.toast(p.error); return false; }
    if (!p.diff) { this.toast("The files already say this. Nothing to change."); return false; }
    return new Promise(resolve => {
      this.modal(`<h2>${esc(title || "Save to the robot's files")}</h2>
        <p>These lines change in the robot project. Nothing is written until you press Write. After
        writing, redeploy the robot code so it loads them at startup, then commit the change.</p>
        <pre class="diff">${colorDiff(p.diff)}</pre>
        <div class="row"><button class="btn primary" id="m-write">Write files</button>
        <button class="btn" id="m-cancel">Cancel</button></div>`, root => {
        $("#m-cancel", root).onclick = () => { this.closeModal(); resolve(false); };
        $("#m-write", root).onclick = async () => {
          const a = await this.api("/api/save/apply", body);
          this.closeModal();
          this.toast(a.ok ? "Written. Redeploy the robot code to load it." : a.error, 5000);
          this.emit("saved", body);
          resolve(!!a.ok);
        };
      });
    });
  },
};

function colorDiff(text) {
  return text.split("\n").map(l => {
    const cls = l.startsWith("+++") || l.startsWith("---") || l.startsWith("@@") ? "hdr" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : "";
    return cls ? `<span class="${cls}">${esc(l)}</span>` : esc(l);
  }).join("\n");
}

// ------------------------------------------------------------------ header
async function loadProjects() {
  const p = await App.api("/api/projects");
  const sel = $("#project");
  sel.innerHTML = p.projects.map(n => `<option ${n === p.current ? "selected" : ""}>${esc(n)}</option>`).join("");
  sel.onchange = async () => {
    await App.api("/api/project", { name: sel.value });
    await refreshLint();
  };
}

async function refreshLint() {
  App.lint = await App.api("/api/lint");
  App.emit("lint", App.lint);
}

$("#target").onchange = () => { $("#host").hidden = $("#target").value !== "host"; };
$("#connect").onclick = async () => {
  if (App.connected()) {
    await App.api("/api/disconnect", {});
    App.toast("Disconnected.");
    return;
  }
  $("#connect").disabled = true;
  $("#connect").textContent = "Connecting…";  // paintHeader leaves the label alone while disabled
  const r = await App.api("/api/connect", { target: $("#target").value, host: $("#host").value });
  $("#connect").disabled = false;
  if (!r.ok) App.modal(`<h2>Could not connect</h2><p>${esc(r.error)}</p>
      <p class="hint">Robot code must be running with SwerveTune installed (it is, on this branch).
      With a VPN on this laptop, run <code>tools\\robot_preflight.ps1</code>.</p>
      <div class="row"><button class="btn" onclick="App.closeModal()">Close</button></div>`);
  else { App.toast("Connected."); await refreshLint(); }
};

$("#abort").onclick = () => abortNow();
// Esc always sends ABORT, whatever else it closes. The toast says whether anything was running,
// so "stopped" never becomes a message students learn to ignore.
async function abortNow() {
  const running = !!((((App.live || {}).test) || {}).running || (App.state.test || {}).running);
  await App.api("/api/abort", {});
  App.toast(running ? "Stopped. ABORT sent to the robot." : "Esc always sends ABORT. Nothing was running.");
}

$("#env-chip").onclick = () => openEnvironment();
$("#tags-chip").onclick = () => openEnvironment();

function openEnvironment(preset) {
  if (!App.connected()) { App.toast("Connect first."); return; }
  const env = App.state.environment || {};
  const sim = App.env() === "SIM";
  let mode = preset || (env.requested && env.requested !== "UNSET" ? env.requested : "BLOCKS");
  App.modal(`<h2>Where is the robot?</h2>
    <p>This decides which tests may run and how the robot keeps everyone safe. ${sim ? "<b>Simulation is always SIM.</b>" : ""}</p>
    <div class="grid2">
      <div class="envopt" data-mode="BLOCKS"><b>On blocks</b>
        <span class="hint">Frame on blocks, all four wheels clear of the floor. Wheels spin; the robot must not move. If the gyro sees it turn, the test stops.</span></div>
      <div class="envopt" data-mode="FIELD"><b>On the floor</b>
        <span class="hint">It will really drive. Every motion test needs the deadman held, fits in the space below, and stops on impact or any stick.</span></div>
    </div>
    <div id="field-opts" class="stack">
      <div class="row">
        <label class="gain">Clear floor ahead (m)<input type="number" id="env-fwd" step="0.1" min="0" value="${env.space_forward || ""}"></label>
        <label class="gain">Clear to each side (m)<input type="number" id="env-side" step="0.1" min="0" value="${env.space_side || ""}"></label>
        <label class="gain">Speed cap (m/s)<input type="number" id="env-cap" step="0.1" min="0.1" max="3" value="${env.speed_cap || 1.0}"></label>
      </div>
      <p class="hint">Measure the space; do not guess. Tests are sized to fit inside it and the robot stops if it leaves it.</p>
    </div>
    <label class="row"><input type="checkbox" id="env-tags" ${env.apriltags ? "checked" : ""}> AprilTags are on this field
      <span class="hint">${env.vision_available ? "Robot code has a vision source." : "Robot code has no vision source yet; tests use the gyro and a tape measure."}</span></label>
    <label class="row"><input type="checkbox" id="env-confirm"> <span id="env-confirm-text"></span></label>
    <div class="row"><button class="btn primary" id="env-save" disabled>Set</button>
      <button class="btn" id="env-cancel">Cancel</button></div>`, root => {
    const sync = () => {
      $$(".envopt", root).forEach(o => o.classList.toggle("on", o.dataset.mode === mode));
      $("#field-opts", root).hidden = mode !== "FIELD";
      $("#env-confirm-text", root).textContent = mode === "FIELD"
        ? "People are clear of the robot's path, and the person holding the deadman can see the robot."
        : "All four wheels are off the floor and free to spin, and hands are clear of them.";
    };
    $$(".envopt", root).forEach(o => o.onclick = () => { mode = o.dataset.mode; sync(); });
    $("#env-confirm", root).onchange = e => { $("#env-save", root).disabled = !e.target.checked; };
    $("#env-cancel", root).onclick = () => App.closeModal();
    $("#env-save", root).onclick = async () => {
      const body = { mode, apriltags: $("#env-tags", root).checked, speed_cap: +$("#env-cap", root).value || 1.0 };
      if (mode === "FIELD") {
        body.space_forward = +$("#env-fwd", root).value;
        body.space_side = +$("#env-side", root).value;
      }
      const r = await App.api("/api/env", body);
      if (!r.ok) { App.toast(r.error); return; }
      App.closeModal();
      App.toast("The robot now knows it is " + (mode === "FIELD" ? "on the floor." : "on blocks."));
    };
    sync();
  });
}

// ------------------------------------------------------------------ deadman: hold SPACE
let deadmanTimer = null;
function typing() {
  const a = document.activeElement;
  return a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.tagName === "SELECT");
}
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { abortNow(); if (!$("#modal").hidden) App.closeModal(); return; }
  if (e.code === "Space" && !typing()) {
    e.preventDefault();
    if (!deadmanTimer) {
      const send = () => App.api("/api/deadman", { held: true });
      send();
      deadmanTimer = setInterval(send, 100);
    }
  }
});
function releaseDeadman() {
  if (deadmanTimer) { clearInterval(deadmanTimer); deadmanTimer = null; App.api("/api/deadman", { held: false }); }
}
document.addEventListener("keyup", e => { if (e.code === "Space") releaseDeadman(); });
window.addEventListener("blur", releaseDeadman);

// ------------------------------------------------------------------ polling
// A chip's classes: "chip", its own (data-chip), and its state. Rewritten on every repaint, so
// nothing else may add classes to a chip.
function setChip(el, text, cls) {
  if (el.textContent !== text) el.textContent = text;
  const want = ["chip", el.dataset.chip, cls].filter(Boolean).join(" ");
  if (el.className !== want) el.className = want;
}
const MODE_WORD = { DISABLED: "Disabled", ESTOP: "E-STOPPED", TELEOP: "Enabled (teleop)", AUTO: "Enabled (auto)", TEST: "Enabled (test)" };

function paintHeader() {
  const st = App.state, live = App.live && App.live.live;
  const on = App.connected();
  const btn = $("#connect");
  if (!btn.disabled) btn.textContent = on ? "Disconnect" : "Connect";
  btn.classList.toggle("primary", !on);  // when nothing is connected, Connect is the one thing to do
  if (on && st.target && document.activeElement !== $("#target")) $("#target").value = st.target;
  const env = App.env();
  ["env-chip", "bus-chip", "battery-chip", "tags-chip"].forEach(id => { $("#" + id).hidden = !on; });
  $("#deadman-chip").hidden = !(on && env === "FIELD");
  if (on && live) {
    const m = live.mode;
    setChip($("#mode-chip"), (st.robot && st.robot.name ? st.robot.name + " · " : "") + (MODE_WORD[m] || m),
      m === "DISABLED" ? "" : m === "ESTOP" ? "bad" : "warn");
    // Disabled, the battery is at rest: grade it like the charge check (12.7 charged, under 12.3
    // charge it). Enabled, it sags with load: amber under 12.2, red under 11.5.
    const rest = m === "DISABLED";
    setChip($("#bus-chip"), "Voltage " + fmt(live.bus, 1) + " V" + (rest ? " at rest" : ""),
      rest ? (live.bus >= 12.7 ? "good" : live.bus >= 12.3 ? "warn" : "bad")
        : (live.bus < 11.5 ? "bad" : live.bus < 12.2 ? "warn" : "good"));
  } else {
    setChip($("#mode-chip"), on ? "Connected · waiting for data" : "Not connected");
    setChip($("#bus-chip"), "Voltage –");
  }
  if (typeof Battery !== "undefined") Battery.paintChip(on && live, st.robot);
  setChip($("#env-chip"), whereWord(env), env === "UNSET" || env === "FIELD" ? "warn" : env === "BLOCKS" ? "info" : env === "SIM" ? "good" : "");
  const tags = st.environment && st.environment.apriltags;
  setChip($("#tags-chip"), "AprilTags " + (tags ? (st.environment.vision_in_use ? "on" : "on, no source") : "off"), tags ? "info" : "");
  const held = App.live && App.live.deadman;
  setChip($("#deadman-chip"), held ? "Deadman: HELD" : "Deadman: not held", held ? "good" : "");

  const t = (App.live && App.live.test) || st.test || {};
  const status = (App.live && App.live.status) || st.status || {};
  const banner = $("#banner");
  const running = t.running || status.state === "RUNNING" || status.state === "WAITING";
  banner.hidden = !running;
  if (running) {
    const waiting = status.state === "WAITING" || t.state === "WAITING";
    banner.className = "banner" + (waiting ? " waiting" : "");
    $("#banner-state").textContent = testName(status.test || t.test || "test") + " · " + (status.state || t.state || "");
    $("#banner-msg").textContent = status.message || t.message || "";
    $("#banner-bar").style.width = Math.round(100 * (status.progress || t.progress || 0)) + "%";
    $("#banner-hint").hidden = !(env === "FIELD");
  }
}

async function pollLive() {
  try {
    App.live = await App.api("/api/live");
    App.emit("live", App.live);
  } catch (e) { App.live = null; }
  paintHeader();
  setTimeout(pollLive, 100);
}

async function pollState() {
  try {
    App.state = await App.api("/api/state");
    App.emit("state", App.state);
  } catch (e) { /* server restarting */ }
  paintHeader();
  setTimeout(pollState, 1000);
}

$$(".tabs button").forEach(b => b.onclick = () => App.show(b.dataset.tab));
// The header wraps on a narrow screen, so its height is measured: the test banner and the
// Lessons drawer sit just under it, and ABORT is never covered.
if (window.ResizeObserver) {
  new ResizeObserver(([e]) => document.documentElement.style.setProperty("--top-h", Math.ceil(e.target.getBoundingClientRect().height) + "px"))
    .observe($(".top"));
}
$("#lessons").onclick = () => Learn.open(null);
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") App.closeModal(); });

window.addEventListener("DOMContentLoaded", async () => {
  await loadProjects();
  await refreshLint();
  pollState();
  pollLive();
  let tab = "guide";
  try { tab = localStorage.getItem("swervetune.tab") || "guide"; } catch (e) { /* storage blocked */ }
  if (location.hash.length > 1) tab = location.hash.slice(1);
  App.show(tab);
});
