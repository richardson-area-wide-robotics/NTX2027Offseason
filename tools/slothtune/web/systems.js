// Systems tab: the robot's mechanisms, grouped by subsystem, and the tuning of each one the code
// registers (TunableSystem). Each is set up in order: its physics (a ReCalc link, or the numbers
// from the AMB spreadsheet), its limits (a person moves it by hand to both ends), its top speed;
// then a closed-loop test that never moves faster than the physics and the team allow.
"use strict";

const Systems = (() => {
  const root = $("#tab-systems");
  // A mechanism's test runs at half its planned speed until someone picks full: the first runs
  // on the real robot go slowly (the walkthrough's half-speed step).
  let data = null, pick = null, last = null, edits = {}, timer = null, speed = "half", view = "test", lastPiece = null;
  const FACTOR = { half: 0.5, full: 1 };
  const KIND = { FLYWHEEL: "flywheel", ROLLER: "roller", PIVOT: "pivot", ELEVATOR: "elevator" };
  const positional = s => s && (s.kind === "PIVOT" || s.kind === "ELEVATOR");
  const n4 = v => v == null || !Number.isFinite(+v) ? "–" : String(+(+v).toPrecision(4));

  root.innerHTML = `
    <div class="sys">
      <div class="panel sys-bar">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <div class="row"><h2 data-tip="sys.title">Systems</h2><div class="seg" id="sys-pick" role="group" aria-label="Mechanism"></div></div>
          <div class="row"><span class="small mono" id="sys-now"></span>
            <button class="btn small" id="sys-walk" data-tip="sys.walk">First time on the real robot? Walk me through it</button></div></div>
        <p class="hint" id="sys-blurb">Each mechanism the robot code registers, tuned through its own control loop. Set it up top to bottom: physics, limits, top speed; then test it.</p>
        <div id="sys-faults"></div>
      </div>
      <div class="sys-cols">
        <div class="panel sys-groups"><h3 data-tip="sys.groups">Subsystems</h3><div id="sys-groups" class="small"></div></div>
        <div class="panel sys-setup" id="sys-setup"></div>
        <div class="panel sys-test" id="sys-test"></div>
      </div>
    </div>`;

  $("#sys-walk", root).onclick = () => { if (pick) Parts.open("system", pick); else App.toast("Pick a mechanism first."); };

  async function load() {
    data = await App.api("/api/systems");
    if (!data || data.ok === false) { $("#sys-groups", root).innerHTML = `<p class="hint">${esc((data || {}).error || "")}</p>`; return; }
    const S = data.systems || [];
    if (!pick || !S.some(s => s.name === pick)) pick = S.length ? S[0].name : null;
    paintPick();
    paintGroups();
    paintSetup();
    paintTest();
    // Settings typed but not saved yet stay in force: work out their plan again.
    if (Object.keys(edits).length && current()) preview();
  }
  const current = () => ((data && data.systems) || []).find(s => s.name === pick);

  function paintPick() {
    const S = (data && data.systems) || [];
    $("#sys-pick", root).innerHTML = S.map(s => `<button data-sys="${esc(s.name)}" class="${s.name === pick ? "on" : ""}" aria-pressed="${s.name === pick}"
      data-tip="sys.pick">${esc(s.name)}${s.name.toLowerCase().includes(KIND[s.kind] || "~") ? "" : ` <span class="muted small">${KIND[s.kind] || ""}</span>`}</button>`).join("")
      || `<span class="small muted">${data && data.connected ? "The robot code registers no mechanism yet: see the guide for tune.system(...)." : "Connect to the robot to see its mechanisms."}</span>`;
    $$("#sys-pick [data-sys]", root).forEach(b => b.onclick = () => { pick = b.dataset.sys; edits = {}; last = null; speed = "half"; paintPick(); paintGroups(); paintSetup(); paintTest(); });
  }

  function paintGroups() {
    const G = (data && data.groups) || [];
    $("#sys-groups", root).innerHTML = G.map(g => `<div class="sys-group${g.systems.includes(pick) ? " on" : ""}">
        <b>${esc(g.name)}</b> <span class="muted">${g.from.join(" + ")}${(g.aka || []).length ? ` · the design file says ${g.aka.map(esc).join(", ")}` : ""}</span>
        <div>${g.motors.map(m => `<span class="chip">${esc(m)}</span>`).join(" ")}${g.sensors.map(s => ` <span class="chip info">${esc(s)}</span>`).join("")}</div>
        ${g.systems.length ? `<div class="muted">Tunable: ${g.systems.map(esc).join(", ")}</div>` : ""}</div>`).join("")
      || `<p class="hint">No subsystems found in the code.</p>`;
  }

  // The live line: where it is, or how fast, and its goal.
  function paintNow() {
    const s = current();
    $("#sys-now", root).textContent = !s ? "" : positional(s)
      ? `${s.name}: at ${n4(s.position)} ${s.units} · goal ${n4(s.goal)} · ${n4(s.velocity)} ${s.units}/s`
      : `${s.name}: ${n4(s.velocity)} ${s.units} · goal ${n4(s.goal)}`;
  }

  // The gains that apply to its kind: a wheel has no gravity, an elevator's is constant (kG), an
  // arm's follows its angle (kCos). One that doesn't apply shows only if someone set it.
  const OFF_KIND = { FLYWHEEL: ["kG", "kCos"], ROLLER: ["kG", "kCos"], ELEVATOR: ["kCos"], PIVOT: ["kG"] };
  function shownGains(s) {
    const off = OFF_KIND[s.kind] || [];
    return Object.entries(s.gains || {}).filter(([k, g]) => !off.includes(k) || +g.value !== 0);
  }

  // ---------------------------------------------------------------- setup
  function val(k) { const s = current(); return k in edits ? edits[k] : ((s && s.settings) || {})[k]; }

  function paintSetup() {
    const box = $("#sys-setup", root), s = current();
    if (!s) { box.innerHTML = ""; return; }
    const ph = (s.physics || {}), typed = val("physics") || {}, ff = s.feedforward || (s.plan && s.plan.feedforward) || null;
    const kindNow = (s.physics && s.physics.kind) || (KIND[s.kind] === "roller" ? "flywheel" : KIND[s.kind]);
    box.innerHTML = `
      <h3 data-tip="sys.physics">1. Its physics</h3>
      <div class="row"><input id="sys-link" placeholder="Paste its ReCalc or AMBcalc link" value="${esc(val("link") || "")}" style="flex:1">
        <button class="btn small" id="sys-read" data-tip="sys.read">Read it</button></div>
      <details ${typed.motor ? "open" : ""}><summary class="small">Or type the numbers (from the AMB spreadsheet)</summary>
        <div class="row small sys-typed">
          <label>Motor <select data-ph="motor">${(data.motors || []).map(m => `<option ${typed.motor === m ? "selected" : ""}>${esc(m)}</option>`).join("")}</select></label>
          <label>How many <input data-ph="count" type="number" min="1" value="${esc(typed.count ?? 1)}" style="width:4em"></label>
          <label>Ratio <input data-ph="ratio" type="number" step="any" value="${esc(typed.ratio ?? "")}" placeholder="50" style="width:5em"></label>
          ${kindNow === "flywheel" ? `<label>Inertia kg·m² <input data-ph="moi_kgm2" type="number" step="any" value="${esc(typed.moi_kgm2 ?? "")}" style="width:6em"></label>`
            : kindNow === "elevator" ? `<label>Load kg <input data-ph="load_kg" type="number" step="any" value="${esc(typed.load_kg ?? "")}" style="width:5em"></label>
              <label>Spool diameter m <input data-ph="spool_diameter_m" type="number" step="any" value="${esc(typed.spool_diameter_m ?? "")}" style="width:5em"></label>`
            : `<label>Arm length m <input data-ph="arm_length_m" type="number" step="any" value="${esc(typed.arm_length_m ?? "")}" style="width:5em"></label>
              <label>Load kg <input data-ph="load_kg" type="number" step="any" value="${esc(typed.load_kg ?? "")}" style="width:5em"></label>`}
        </div></details>
      <p class="small">${s.physics_error ? `<span class="bad-ink">${esc(s.physics_error)}</span>` : !s.physics ? `<span class="muted">No physics yet.</span>`
        : `${esc(ph.count || 1)} × ${esc(ph.motor)} through ${n4(ph.ratio)}:1. Free speed ${n4(ff && ff.free_speed * (s.scale || 1))} ${esc(s.units)}${positional(s) ? "/s" : ""}${ff ? ` · kV ${n4(ff.kV)} · kA ${n4(ff.kA)}${ff.kG ? ` · kG ${n4(ff.kG)} V` : ""} (per ${s.kind === "ELEVATOR" ? "meter" : "radian"})` : ""}${ph.calculator ? ` <span class="muted">From ${esc(ph.calculator)}.</span>` : ""}${(ph.notes || []).length ? ` <span class="warn-ink">${ph.notes.map(esc).join(" ")}</span>` : ""}`}</p>
      <label class="row small" data-tip="sys.scale">One ${s.kind === "ELEVATOR" ? "meter" : "radian"} of it${positional(s) ? "" : " per second"} is <input id="sys-scale" type="number" step="any" value="${n4(s.scale)}" style="width:6em"> ${esc(s.units)}</label>
      ${positional(s) ? `<h3 data-tip="sys.limits">2. Its limits</h3>
        <div class="row small"><span style="flex:1">${Number.isFinite(s.min) && Number.isFinite(s.max) ? `${n4(s.min)} to ${n4(s.max)} ${esc(s.units)}${s.limits_from ? ` <span class="muted">(${esc(s.limits_from)})</span>` : ""}` : `<span class="warn-ink">Not set: nothing moves it until a person has moved it by hand to both ends.</span>`}</span>
          <button class="btn small" id="sys-limits" data-tip="sys.limits-run">Set limits by hand…</button></div>` : ""}
      <h3 data-tip="sys.top">${positional(s) ? "3" : "2"}. Its top speed</h3>
      <div class="row small"><label>Team's maximum <input id="sys-vmax" type="number" step="any" value="${esc(val("maxVelocity") ?? "")}" style="width:5em"> ${esc(s.units)}${positional(s) ? "/s" : ""}</label>
        <label>Max acceleration <input id="sys-amax" type="number" step="any" value="${esc(val("maxAccel") ?? "")}" style="width:5em"> ${esc(s.units)}/s${positional(s) ? "²" : ""}</label></div>
      <div class="row"><button class="btn primary small" id="sys-save" data-tip="sys.save">Save to slothtune.json…</button></div>
      ${Object.keys(s.gains || {}).length ? `<div class="row" style="justify-content:space-between"><h3 data-tip="sys.gains">Its gains, live</h3>
          <span class="row small"><span class="muted">Live only: a value to keep goes into the code.</span>
          <button class="btn small" id="sys-apply" data-tip="sys.apply">Apply live</button></span></div>
        <div class="gains sys-gains">${shownGains(s).map(([k, g]) => `<label class="gain">${esc(k)}<input type="number" step="any" data-g="${esc(k)}" value="${n4(g.value)}"></label>`).join("")}</div>` : ""}`;
    const ap = $("#sys-apply", box);
    if (ap) ap.onclick = async () => {
      const v = {};
      $$("[data-g]", box).forEach(i => { if (i.value !== "" && +i.value !== +((s.gains[i.dataset.g] || {}).value)) v[`${s.name}/${i.dataset.g}`] = +i.value; });
      if (!Object.keys(v).length) { App.toast("Nothing changed."); return; }
      const r = await App.api("/api/systems/gains", { values: v });
      App.toast(r.status || r.error, 6000);
      load();
    };
    $("#sys-link", box).onchange = e => { edits.link = e.target.value.trim(); };
    $("#sys-read", box).onclick = () => { edits.link = $("#sys-link", box).value.trim(); delete edits.physics; preview(); };
    $$("[data-ph]", box).forEach(i => i.onchange = () => {
      const p = Object.assign({ kind: kindNow }, val("physics") || {});
      p[i.dataset.ph] = i.tagName === "SELECT" ? i.value : +i.value;
      edits.physics = p;
      edits.link = "";
      preview();
    });
    $("#sys-scale", box).onchange = e => { edits.unitsPerRadian = +e.target.value; preview(); };
    $("#sys-vmax", box).onchange = e => { edits.maxVelocity = e.target.value === "" ? null : +e.target.value; preview(); };
    $("#sys-amax", box).onchange = e => { edits.maxAccel = e.target.value === "" ? null : +e.target.value; };
    $("#sys-save", box).onclick = save;
    const lim = $("#sys-limits", box);
    if (lim) lim.onclick = setLimits;
  }

  // What the edited settings give, before saving: the physics and the safe test.
  async function preview() {
    const s = current();
    const r = await App.api("/api/systems/physics", { name: s.name, kind: s.kind, units: s.units, settings: Object.assign({}, s.settings, edits) });
    if (!r.ok) { App.toast(r.error, 6000); return; }
    Object.assign(s, { physics: r.physics, physics_error: null, plan: r.plan, scale: r.scale, feedforward: r.feedforward,
      settings: Object.assign({}, s.settings, edits) });
    paintSetup();
    paintTest();
  }

  async function save() {
    const s = current(), set = Object.assign({}, s.settings, edits), e = [];
    const put = (k, v) => { if (v !== undefined && v !== null && v !== "") e.push({ file: "slothtune.json", path: ["systems", s.name, k], value: v }); };
    put("link", set.link);
    put("physics", set.link ? undefined : set.physics);
    put("unitsPerRadian", edits.unitsPerRadian);
    put("maxVelocity", set.maxVelocity);
    put("maxAccel", set.maxAccel);
    if (positional(s) && Number.isFinite(s.min) && Number.isFinite(s.max)) { put("min", s.min); put("max", s.max); }
    if (!e.length) { App.toast("Nothing to save yet."); return; }
    if (await App.previewAndSave({ kind: "edits", edits: e }, `${s.name}: its settings`)) { edits = {}; load(); }
  }

  // ---------------------------------------------------------------- limits, by hand
  function setLimits() {
    const s = current();
    App.modal(`<h2>${esc(s.name)}: its limits, by hand</h2>
      <ol class="small"><li><b>Disable the robot.</b> Its motors will coast while you move it.</li>
        <li>Move it slowly all the way one way, to its hard stop, and all the way the other.</li>
        <li>Press <b>Done</b>. The lowest and highest it read become its limits; nothing tests it beyond them.</li></ol>
      <p class="mono" id="sl-live">Waiting for the robot…</p>
      <div class="row"><button class="btn primary" id="sl-go">Start</button><button class="btn" id="sl-done" disabled>Done</button><button class="btn" id="sl-x">Cancel</button></div>
      <div id="sl-out" class="small"></div>`, m => {
      let poll = null;
      $("#sl-x", m).onclick = () => { App.api("/api/stop", {}); clearInterval(poll); App.closeModal(); };
      $("#sl-done", m).onclick = () => App.api("/api/stop", {});
      $("#sl-go", m).onclick = async () => {
        $("#sl-go", m).disabled = true;
        $("#sl-done", m).disabled = false;
        poll = setInterval(() => {
          const msg = ((App.live || {}).status || {}).message || (App.state.status || {}).message || "";
          if (msg) $("#sl-live", m).textContent = msg;
        }, 200);
        try {
          const doc = await App.runTest("system_limits", "ALL", { system: s.index, duration_s: 180 });
          const rep = doc.report || {};
          $("#sl-out", m).innerHTML = `<p><b>${esc(rep.summary || "")}</b></p>${(rep.findings || []).map(f => `<div class="${f.level === "error" ? "bad-ink" : ""}">${esc(f.title)}: ${esc(f.why)}</div>`).join("")}`;
          load();
        } catch (e) { $("#sl-out", m).innerHTML = `<p class="bad-ink">${esc(e.message)}</p>`; }
        finally { clearInterval(poll); $("#sl-done", m).disabled = true; $("#sl-x", m).textContent = "Close"; }
      };
    });
  }

  // ---------------------------------------------------------------- the test
  // The test panel: the closed-loop test, or game pieces sensed by current and held by a limit.
  const viewSeg = () => `<div class="seg" id="sys-view" role="group" aria-label="Show">${[["test", "Test it"], ["pieces", "Game pieces"]].map(([k, l]) =>
    `<button data-view="${k}" class="${view === k ? "on" : ""}" aria-pressed="${view === k}" data-tip="sys.view-${k}">${l}</button>`).join("")}</div>`;
  function wireView(box) {
    $$("#sys-view [data-view]", box).forEach(b => b.onclick = () => { view = b.dataset.view; paintTest(); });
  }

  function paintTest() {
    const box = $("#sys-test", root), s = current();
    if (!s) { box.innerHTML = ""; return; }
    if (view === "pieces") { paintPieces(box, s); return; }
    const p = scaled(s), env = App.env();
    const where = ["BLOCKS", "FIELD", "SIM"].includes(env);
    box.innerHTML = `
      ${viewSeg()}
      <div class="row" style="justify-content:space-between"><h3 data-tip="sys.test">${positional(s) ? "4" : "3"}. Test it</h3>
        <div class="row"><div class="seg" id="sys-speed" role="group" aria-label="Test speed">${["half", "full"].map(k =>
          `<button data-speed="${k}" class="${speed === k ? "on" : ""}" aria-pressed="${speed === k}" data-tip="sys.speed-${k}">${k === "half" ? "Half speed" : "Full speed"}</button>`).join("")}</div>
        <button class="btn primary" id="sys-run" data-tip="sys.run" ${p.ok && App.connected() && where ? "" : "disabled"}>Run</button></div></div>
      ${p.ok ? `<p class="small">${positional(s) ? `Moves between ${n4(p.a)} and ${n4(p.b)} ${esc(s.units)}` : `Spins up to ${n4(p.a)}, then ${n4(p.b)} ${esc(s.units)}, then down`},
          no faster than <b>${n4(p.vmax)}</b> ${esc(s.units)}${positional(s) ? "/s" : ""}${speed === "half" ? " (half its planned speed)" : ""}, changing at most ${n4(p.amax)} per second${positional(s) ? " per second" : ""}.
          <span class="muted">${(p.why || []).map(esc).join("; ")}.</span></p>
        <p class="small muted">Robot enabled ${where ? "" : "<b class=\"warn-ink\">(set On blocks or On the floor first)</b> "}and the deadman held; someone watching it, hands clear. It stops at once if it leaves its limits or goes too fast.</p>`
        : `<p class="small warn-ink">Before it can be tested: ${(p.missing || ["its settings"]).map(esc).join("; ")}.</p>`}
      <div class="plotwrap"><canvas class="plot short" id="sys-plot" role="img" aria-label="The goal and what the mechanism did"></canvas></div>
      <div id="sys-report" class="small"></div>`;
    $("#sys-run", box).onclick = run;
    wireView(box);
    $$("#sys-speed [data-speed]", box).forEach(b => b.onclick = () => { speed = b.dataset.speed; paintTest(); });
    drawRun();
  }

  // The plan at the chosen speed: a flywheel's goals are speeds too, a pivot's stay where they are.
  function scaled(s) {
    const p = s.plan || {}, f = FACTOR[speed];
    if (!p.ok || f === 1) return p;
    return Object.assign({}, p, { vmax: p.vmax * f, amax: p.amax * f }, positional(s) ? {} : { a: p.a * f, b: p.b * f });
  }

  async function run() {
    const s = current(), p = scaled(s);
    $("#sys-run", root).disabled = true;
    try {
      last = await App.runTest("system_step", "ALL", { system: s.index, a: p.a, b: p.b, vmax: p.vmax, amax: p.amax, hold_s: 1, moves: 2 });
    } catch (e) { App.toast(e.message, 8000); }
    finally { $("#sys-run", root).disabled = false; }
    drawRun();
  }

  function drawRun() {
    const out = $("#sys-report", root), cv = $("#sys-plot", root);
    if (!cv) return;
    if (!last) { Plot.draw(cv, { series: [] }); out.innerHTML = ""; return; }
    const ch = last.channels || {}, s = current(), pos = positional(s);
    Plot.draw(cv, { xlabel: "s", ylabel: s.units, series: [
      { x: ch.t, y: ch.goal, color: "--muted", dash: [2, 3], width: 1, label: "headed for" },
      { x: ch.t, y: ch.sp, color: "--sp", dash: [6, 4], width: 1.6, label: "goal", learn: "setpoint" },
      { x: ch.t, y: pos ? ch.pos : ch.vel, color: "--s0", width: 2, label: s.name, learn: "measurement" }] });
    const rep = last.report || {};
    out.innerHTML = `<p><b>${esc(rep.summary || "")}</b>${rep.score != null ? ` · score ${rep.score}` : ""}</p>
      ${(rep.findings || []).map(f => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div><div class="why">${esc(f.why)}</div></div>`).join("")}
      ${(rep.actions || []).map((a, i) => `<button class="btn small" data-act="${i}" data-tip="sys.try">${esc(a.label)}</button>`).join(" ")}`;
    $$("[data-act]", out).forEach(b => b.onclick = async () => {
      const a = rep.actions[+b.dataset.act];
      const r = await App.api("/api/systems/gains", { values: a.values });
      App.toast((r.status || r.error) + " Run again to see it.", 7000);
      load();
    });
  }

  // ---------------------------------------------------------------- game pieces
  // A current sensor on this mechanism's motor is calibrated with a set number of pieces; a hold is
  // tuned like the slip test. Both are runs on the robot, a person helping, the deadman held.
  function paintPieces(box, s) {
    const P = ((data && data.pieces) || []).filter(p => p.system === s.name || s.motors.includes(p.motor));
    const H = ((data && data.holds) || []).filter(h => h.system === s.name || s.motors.includes(h.motor));
    const env = App.env(), ok = App.connected() && ["BLOCKS", "FIELD", "SIM"].includes(env);
    box.innerHTML = `${viewSeg()}
      <h3 data-tip="sys.pieces">Game pieces</h3>
      ${!P.length && !H.length ? `<p class="small muted">The code registers no current sensor or hold on ${esc(s.name)}'s motors. In its subsystem:
          <span class="mono">tune.currentSensor("${esc(s.name)} has piece", "${esc(s.motors[0] || "motor name")}")</span>, or
          <span class="mono">tune.holdCurrent("${esc(s.motors[0] || "motor name")}", motor::set)</span>.</p>` : ""}
      ${P.map(p => `<div class="pc-row"><div><b>${esc(p.name)}</b> <span class="small muted">${esc(p.motor)}, ${esc(p.mode === "aboveBaseline" ? "above its empty current" : p.mode)}</span>
          <div class="small">now ${Number.isFinite(p.amps) ? p.amps.toFixed(1) : "–"} A · ${Number.isFinite(p.threshold) ? `threshold ${p.threshold.toFixed(1)} A` : `<span class="warn-ink">not calibrated: it never sees a piece</span>`}
            ${p.has_piece ? ` · <span class="level ok">has a piece</span>` : ""}</div></div>
        <button class="btn" data-cal="${p.index}" data-tip="sys.piece-cal" ${ok ? "" : "disabled"}>Calibrate with pieces…</button></div>`).join("")}
      ${H.map(h => `<div class="pc-row"><div><b>Hold: ${esc(h.motor)}</b>
          <div class="small">${h.amps.toFixed(0)} A at ${h.duty.toFixed(2)} power${h.tuned ? "" : ` · <span class="warn-ink">not tuned: half its limit</span>`}${h.on ? ` · <span class="level ok">holding</span>` : ""}</div></div>
        <button class="btn" data-hold="${h.index}" data-tip="sys.hold-tune" ${ok ? "" : "disabled"}>Tune the hold current…</button></div>`).join("")}
      ${ok ? "" : `<p class="small muted">Connect, and say where the robot is (on blocks, or on the floor for a ground intake), to run these.</p>`}
      <div id="pc-report" class="small"></div>`;
    wireView(box);
    $$("[data-cal]", box).forEach(b => b.onclick = () => calibrateWalk(s, P.find(p => p.index === +b.dataset.cal)));
    $$("[data-hold]", box).forEach(b => b.onclick = () => holdWalk(s, H.find(h => h.index === +b.dataset.hold)));
    paintPieceReport();
  }

  function walk(title, checks, body, start) {
    App.modal(`<h2>${title}</h2><ul class="checklist">${checks.map((t, k) => `<li><label class="row"><input type="checkbox" data-pc-check="${k}"> <span>${t}</span></label></li>`).join("")}</ul>
      ${body}<div class="row" style="justify-content:flex-end"><button class="btn" id="pc-cancel" data-tip="autotune.cancel">Cancel</button>
      <button class="btn primary" id="pc-go" data-tip="sys.piece-go" disabled>Start</button></div>`, m => {
      const boxes = $$("[data-pc-check]", m);
      // A roller needs its speed: Start waits for it too.
      const ready = () => { const g = $("#pc-goal", m); $("#pc-go", m).disabled = !boxes.every(y => y.checked) || (g && !(Math.abs(+g.value) > 0)); };
      boxes.forEach(x => x.onchange = ready);
      const g = $("#pc-goal", m);
      if (g) g.oninput = ready;
      $("#pc-cancel", m).onclick = () => App.closeModal();
      $("#pc-go", m).onclick = () => { const args = start(m); App.closeModal(); runPiece(args); };
    });
  }

  function calibrateWalk(s, p) {
    const pos = positional(s), plan = scaled(s).ok ? scaled(s) : (s.plan || {});
    walk(`Calibrate ${esc(p.name)}`, [
      "The robot is enabled and someone holds the deadman for the whole run.",
      pos ? `${esc(s.name)}'s limits are set, and it is clear to sweep between them.` : "Hands stay clear of the rollers: feed each piece the way the game does (roll it in), never by hand into the rollers.",
      "You have the pieces ready, the same kind the robot will see in a match.",
      env() === "FIELD" ? "On the floor: a ground intake picks pieces off the carpet, as in a match." : "On blocks: for a ground intake, do it on the carpet too (Where: on the floor).",
    ], `<div class="row" style="gap:10px"><label class="small" data-tip="sys.piece-n">Pieces <input type="number" id="pc-n" value="3" min="1" max="10" style="width:4em"></label>
      ${pos ? "" : `<label class="small" data-tip="sys.piece-speed">Runs at <input type="number" id="pc-goal" value="${n4(plan.a || 0)}" step="any" style="width:6em"> ${esc(s.units)}</label>`}</div>
      <p class="small">${pos ? "It sweeps slowly between its limits empty, then once with each piece: put a piece in when the banner says, take it out when it says."
        : "It runs empty, then for each piece it starts, the banner says <b>Feed piece 1 now</b>, and it stops so you can take it out. About 7 s a piece."}
       The tool then sets the threshold halfway between empty and a piece, and how long to ignore its spin-up.</p>`,
      m => {
        const n = Math.max(1, Math.min(10, +$("#pc-n", m).value || 3));
        return { test: "system_piece", args: Object.assign({ sensor: p.index, system: s.index, pieces: n },
          pos ? { vmax: (plan.vmax || 0) * 0.5, amax: (plan.amax || 0) * 0.5 } : { goal: +$("#pc-goal", m).value || 0 }) };
      });
  }
  const env = () => App.env();

  function holdWalk(s, h) {
    walk(`Tune the hold current: ${esc(h.motor)}`, [
      "A piece is in, held the way it is in a match.",
      "The robot is enabled and someone holds the deadman for the whole run.",
      "Someone pulls the piece out steadily when the banner says, the same way every time (a hand, or a spring scale at a set pull), hands clear of the rollers.",
    ], `<p class="small">It holds at its limit (30 A at most) while the piece seats, then lowers the current every 2.5 s while you pull. When the roller turns, the piece is slipping: it then holds at 1.5 times that current for 10 s, with the pull let go, to see how warm the motor gets. Like the slip test for the drive.</p>`,
      () => ({ test: "system_hold", args: { hold: h.index } }));
  }

  async function runPiece(r) {
    try {
      lastPiece = await App.runTest(r.test, "ALL", r.args);
    } catch (e) {
      lastPiece = { report: { summary: e.message, findings: [] } };   // a refusal shows where the result would
    }
    view = "pieces";
    paintTest();
  }

  function paintPieceReport() {
    const out = $("#pc-report", root);
    if (!out || !lastPiece) return;
    const rep = lastPiece.report || {};
    const rows = (rep.pieces || []).map(p => `<tr><td>${p.piece}</td><td class="num">${p.peak_a == null ? "–" : p.peak_a.toFixed(1) + " A"}</td></tr>`).join("");
    out.innerHTML = `<p><b>${esc(rep.summary || "")}</b></p>
      ${rows ? `<table class="t small pc-table"><thead><tr><th>Piece</th><th class="num">Held current</th></tr></thead><tbody>${rows}</tbody></table>` : ""}
      ${(rep.findings || []).map(f => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div><div class="why">${esc(f.why)}</div></div>`).join("")}
      ${(rep.save || []).length ? `<button class="btn primary" id="pc-save" data-tip="sys.piece-save">Save to slothtune.json…</button>` : ""}`;
    const sv = $("#pc-save", out);
    if (sv) sv.onclick = () => App.previewAndSave({ kind: "edits", edits: rep.save }, "Save the calibration");
  }

  Faults.mount($("#sys-faults", root), () => {
    const s = current();
    return s && s.motors.length ? { kind: "named", names: s.motors, quiet: true, what: `${s.name}'s motors` } : null;
  });
  App.on("tab", t => {
    clearInterval(timer);
    if (t !== "systems") return;
    load();
    timer = setInterval(async () => {
      const r = await App.api("/api/systems");
      if (r && r.ok) {
        // Only the live numbers: rebuilding the page would lose what is being typed.
        for (const s of r.systems || []) {
          const mine = ((data && data.systems) || []).find(x => x.name === s.name);
          if (mine) Object.assign(mine, { position: s.position, velocity: s.velocity, goal: s.goal, min: s.min, max: s.max, limits_from: s.limits_from });
        }
        if (data && (r.systems || []).length !== (data.systems || []).length) load(); else paintNow();
      }
    }, 1000);
  });
  /** Opens on one mechanism, at a speed: the walkthrough's steps land here. */
  function focus(name, o) {
    o = o || {};
    if (name && name !== pick) { pick = name; edits = {}; last = null; }
    if (o.speed) speed = o.speed;
    load();
  }

  return { load, focus };
})();
