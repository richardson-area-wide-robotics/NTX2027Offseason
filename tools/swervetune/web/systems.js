// Systems tab: the robot's mechanisms, grouped by subsystem, and the tuning of each one the code
// registers (TunableSystem). Each is set up in order: its physics (a ReCalc link, or the numbers
// from the AMB spreadsheet), its limits (a person moves it by hand to both ends), its top speed;
// then a closed-loop test that never moves faster than the physics and the team allow.
"use strict";

const Systems = (() => {
  const root = $("#tab-systems");
  let data = null, pick = null, last = null, edits = {}, timer = null;
  const KIND = { FLYWHEEL: "flywheel", ROLLER: "roller", PIVOT: "pivot", ELEVATOR: "elevator" };
  const positional = s => s && (s.kind === "PIVOT" || s.kind === "ELEVATOR");
  const n4 = v => v == null || !Number.isFinite(+v) ? "–" : String(+(+v).toPrecision(4));

  root.innerHTML = `
    <div class="sys">
      <div class="panel sys-bar">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <div class="row"><h2 data-tip="sys.title">Systems</h2><div class="seg" id="sys-pick" role="group" aria-label="Mechanism"></div></div>
          <span class="small mono" id="sys-now"></span></div>
        <p class="hint" id="sys-blurb">Each mechanism the robot code registers, tuned through its own control loop. Set it up top to bottom: physics, limits, top speed; then test it.</p>
        <div id="sys-faults"></div>
      </div>
      <div class="sys-cols">
        <div class="panel sys-groups"><h3 data-tip="sys.groups">Subsystems</h3><div id="sys-groups" class="small"></div></div>
        <div class="panel sys-setup" id="sys-setup"></div>
        <div class="panel sys-test" id="sys-test"></div>
      </div>
    </div>`;

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
    $$("#sys-pick [data-sys]", root).forEach(b => b.onclick = () => { pick = b.dataset.sys; edits = {}; last = null; paintPick(); paintGroups(); paintSetup(); paintTest(); });
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

  // ---------------------------------------------------------------- setup
  function val(k) { const s = current(); return k in edits ? edits[k] : ((s && s.settings) || {})[k]; }

  function paintSetup() {
    const box = $("#sys-setup", root), s = current();
    if (!s) { box.innerHTML = ""; return; }
    const ph = (s.physics || {}), typed = val("physics") || {}, ff = s.feedforward || (s.plan && s.plan.feedforward) || null;
    const kindNow = (s.physics && s.physics.kind) || (KIND[s.kind] === "roller" ? "flywheel" : KIND[s.kind]);
    box.innerHTML = `
      <h3 data-tip="sys.physics">1. Its physics</h3>
      <div class="row"><input id="sys-recalc" placeholder="Paste its ReCalc link (reca.lc/arm, /flywheel, /linear)" value="${esc(val("recalc") || "")}" style="flex:1">
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
        : `${esc(ph.count || 1)} × ${esc(ph.motor)} through ${n4(ph.ratio)}:1. Free speed ${n4(ff && ff.free_speed * (s.scale || 1))} ${esc(s.units)}${positional(s) ? "/s" : ""}${ff ? ` · kV ${n4(ff.kV)} · kA ${n4(ff.kA)}${ff.kG ? ` · kG ${n4(ff.kG)} V` : ""} (per radian)` : ""}`}</p>
      <label class="row small" data-tip="sys.scale">One radian of it${positional(s) ? "" : " per second"} is <input id="sys-scale" type="number" step="any" value="${n4(s.scale)}" style="width:6em"> ${esc(s.units)}</label>
      ${positional(s) ? `<h3 data-tip="sys.limits">2. Its limits</h3>
        <div class="row small"><span style="flex:1">${Number.isFinite(s.min) && Number.isFinite(s.max) ? `${n4(s.min)} to ${n4(s.max)} ${esc(s.units)}${s.limits_from ? ` <span class="muted">(${esc(s.limits_from)})</span>` : ""}` : `<span class="warn-ink">Not set: nothing moves it until a person has moved it by hand to both ends.</span>`}</span>
          <button class="btn small" id="sys-limits" data-tip="sys.limits-run">Set limits by hand…</button></div>` : ""}
      <h3 data-tip="sys.top">${positional(s) ? "3" : "2"}. Its top speed</h3>
      <div class="row small"><label>Team's maximum <input id="sys-vmax" type="number" step="any" value="${esc(val("maxVelocity") ?? "")}" style="width:5em"> ${esc(s.units)}${positional(s) ? "/s" : ""}</label>
        <label>Max acceleration <input id="sys-amax" type="number" step="any" value="${esc(val("maxAccel") ?? "")}" style="width:5em"> ${esc(s.units)}/s${positional(s) ? "²" : ""}</label></div>
      <div class="row"><button class="btn primary small" id="sys-save" data-tip="sys.save">Save to swervetune.json…</button></div>
      ${Object.keys(s.gains || {}).length ? `<div class="row" style="justify-content:space-between"><h3 data-tip="sys.gains">Its gains, live</h3>
          <span class="row small"><span class="muted">Live only: a value to keep goes into the code.</span>
          <button class="btn small" id="sys-apply" data-tip="sys.apply">Apply live</button></span></div>
        <div class="gains sys-gains">${Object.entries(s.gains).map(([k, g]) => `<label class="gain">${esc(k)}<input type="number" step="any" data-g="${esc(k)}" value="${n4(g.value)}"></label>`).join("")}</div>` : ""}`;
    const ap = $("#sys-apply", box);
    if (ap) ap.onclick = async () => {
      const v = {};
      $$("[data-g]", box).forEach(i => { if (i.value !== "" && +i.value !== +((s.gains[i.dataset.g] || {}).value)) v[`${s.name}/${i.dataset.g}`] = +i.value; });
      if (!Object.keys(v).length) { App.toast("Nothing changed."); return; }
      const r = await App.api("/api/systems/gains", { values: v });
      App.toast(r.status || r.error, 6000);
      load();
    };
    $("#sys-recalc", box).onchange = e => { edits.recalc = e.target.value.trim(); };
    $("#sys-read", box).onclick = () => { edits.recalc = $("#sys-recalc", box).value.trim(); delete edits.physics; preview(); };
    $$("[data-ph]", box).forEach(i => i.onchange = () => {
      const p = Object.assign({ kind: kindNow }, val("physics") || {});
      p[i.dataset.ph] = i.tagName === "SELECT" ? i.value : +i.value;
      edits.physics = p;
      edits.recalc = "";
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
    const put = (k, v) => { if (v !== undefined && v !== null && v !== "") e.push({ file: "swervetune.json", path: ["systems", s.name, k], value: v }); };
    put("recalc", set.recalc);
    put("physics", set.recalc ? undefined : set.physics);
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
  function paintTest() {
    const box = $("#sys-test", root), s = current();
    if (!s) { box.innerHTML = ""; return; }
    const p = s.plan || {}, env = App.env();
    const where = ["BLOCKS", "FIELD", "SIM"].includes(env);
    box.innerHTML = `
      <div class="row" style="justify-content:space-between"><h3 data-tip="sys.test">${positional(s) ? "4" : "3"}. Test it</h3>
        <button class="btn primary" id="sys-run" data-tip="sys.run" ${p.ok && App.connected() && where ? "" : "disabled"}>Run</button></div>
      ${p.ok ? `<p class="small">${positional(s) ? `Moves between ${n4(p.a)} and ${n4(p.b)} ${esc(s.units)}` : `Spins up to ${n4(p.a)}, then ${n4(p.b)} ${esc(s.units)}, then down`},
          no faster than <b>${n4(p.vmax)}</b> ${esc(s.units)}${positional(s) ? "/s" : ""}, changing at most ${n4(p.amax)} per second${positional(s) ? " per second" : ""}.
          <span class="muted">${(p.why || []).map(esc).join("; ")}.</span></p>
        <p class="small muted">Robot enabled ${where ? "" : "<b class=\"warn-ink\">(set On blocks or On the floor first)</b> "}and the deadman held; someone watching it, hands clear. It stops at once if it leaves its limits or goes too fast.</p>`
        : `<p class="small warn-ink">Before it can be tested: ${(p.missing || ["its settings"]).map(esc).join("; ")}.</p>`}
      <div class="plotwrap"><canvas class="plot short" id="sys-plot" role="img" aria-label="The goal and what the mechanism did"></canvas></div>
      <div id="sys-report" class="small"></div>`;
    $("#sys-run", box).onclick = run;
    drawRun();
  }

  async function run() {
    const s = current(), p = s.plan;
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
  return { load };
})();
