// Redo one part: a module that was replaced or acts up, a motor, the gyro, a camera, a new field,
// new wheels. Shown in the Guide tab instead of the whole path. Each part's checklist counts only
// what was done to that part since the person started it (server: setup.part_plan), and its steps
// open the same tools, set to that part: the tuner on that module, the camera tool on that camera.
"use strict";

const Parts = (() => {
  const root = $("#tab-guide");
  const WORD = { done: "done", attention: "needs a fix", todo: "to do", later: "later", optional: "optional", skip: "not needed" };
  const CHIP = { done: "good", attention: "bad", todo: "todo", later: "info", optional: "opt", skip: "opt" };
  // What the person sees between paints: a step's result, and a question waiting for an answer.
  let on = false, sel = null, cat = null, plan = null, picked = null, result = {}, asking = null, seq = 0, focusNext = false;
  let liveTimer = null;  // a mechanism's live reading, while its direction step is shown
  let showJob = false;   // a step was picked: bring its panel, with its buttons, into view

  function choose(kind, which) {
    // Another part: nothing from the last one carries over.
    if (!sel || sel.kind !== kind || sel.which !== (which || "")) { result = {}; asking = null; }
    sel = kind ? { kind, which: which || "" } : null;
    picked = null;
  }

  function open(kind, which) {
    on = true;
    if (kind) choose(kind, which);
    focusNext = true;
    if (root.classList.contains("on")) paint(); else App.show("guide");
  }

  /** Back to the whole path, quietly: the caller paints the Guide. */
  function off() { on = false; }

  function leave() {
    on = false;
    Guide.refresh();
  }

  async function paint() {
    // A slow answer must never paint over a newer one, or over the Guide once the person left.
    const my = ++seq;
    clearInterval(liveTimer);
    const c = await App.api("/api/parts");
    if (sel && !sel.which) {
      // A part that needs a pick gets the first choice, as its select shows.
      const k = (c.kinds || []).find(x => x.kind === sel.kind);
      if (k && k.choices && k.choices.length) sel.which = k.choices[0];
    }
    const pl = sel ? await App.api(`/api/parts/plan?kind=${encodeURIComponent(sel.kind)}&which=${encodeURIComponent(sel.which)}`) : null;
    if (my !== seq || !on) return;
    cat = c; plan = pl;
    if (cat.ok === false) { root.innerHTML = `<div class="empty">${esc(cat.error)}</div>`; return; }
    const kindRow = k => {
      const act = cat.active.filter(a => a.kind === k.kind);
      return `<div class="part-kind ${sel && sel.kind === k.kind ? "on" : ""}">
        <div><b>${esc(k.title)}</b><br><span class="small muted">${esc(k.when)}</span></div>
        <div class="row" style="flex-wrap:wrap">
          ${k.choices ? `<select data-pick="${k.kind}" aria-label="Which ${esc(k.title.toLowerCase())}" data-tip="parts.pick" data-quiet>${k.choices.map(c =>
            `<option ${sel && sel.kind === k.kind && sel.which === c ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>` : ""}
          <button class="btn small" data-show="${k.kind}" data-tip="parts.show" data-quiet>Show its checklist</button>
        </div>
        ${act.length ? `<div class="small">${act.map(a => `<button class="linkish" data-open="${esc(a.kind)}" data-which="${esc(a.which)}" data-tip="parts.open" data-quiet>${esc(a.which || a.title)}: ${a.done} of ${a.of} done</button>`).join(" · ")}</div>` : ""}
      </div>`;
    };
    root.innerHTML = `<div class="split parts-split">
      <div class="panel"><h3 data-tip="parts.title">Redo one part</h3>
        <p class="small">Already set up, and one thing changed? Check only that part: the rest of the robot keeps its settings, and only what you do from now on counts for it.</p>
        <div class="stack">${cat.kinds.map(kindRow).join("")}</div>
        <div class="row" style="margin-top:10px"><button class="btn" id="p-leave" data-tip="parts.leave">← The whole robot (the Guide's path)</button></div>
      </div>
      <div class="panel" id="p-body">${body()}</div>
    </div>`;
    $("#p-leave", root).onclick = leave;
    $$("[data-show]", root).forEach(b => b.onclick = () => {
      const s = $(`[data-pick="${b.dataset.show}"]`, root);
      choose(b.dataset.show, s ? s.value : "");
      focusNext = true;
      paint();
    });
    $$("[data-pick]", root).forEach(s => s.onchange = () => { choose(s.dataset.pick, s.value); focusNext = true; paint(); });
    $$("[data-open]", root).forEach(b => b.onclick = () => { choose(b.dataset.open, b.dataset.which); focusNext = true; paint(); });
    mount();
    // A picked step's panel can be below a long checklist: scroll it into view inside its panel.
    if (showJob) {
      showJob = false;
      const pj = $(".part-job", root);
      if (pj) pj.scrollIntoView({ block: "nearest" });
    }
    // The new content can be a screen away on a phone: take the person to it.
    if (focusNext) {
      focusNext = false;
      const h = $("#p-body h2", root);
      if (h) h.focus();
    }
  }

  const when = s => s ? `${+s.slice(4, 6)}/${+s.slice(6, 8)} ${s.slice(9, 11)}:${s.slice(11, 13)}` : "";

  function jobsList(jobs, current, clickable) {
    return `<ol class="plan-jobs">${jobs.map(j => `<li class="${j.id === current ? "now" : ""} ${j.status}">
      <span class="chip ${CHIP[j.status]}">${WORD[j.status]}</span>
      <span class="plan-t">${clickable ? `<button class="linkish" data-job="${esc(j.id)}" data-tip="parts.job" data-quiet><b>${esc(j.title)}</b></button>` : `<b>${esc(j.title)}</b>`}
        <span class="small muted">${esc(j.detail || "")}</span></span></li>`).join("")}</ol>`;
  }

  function body() {
    if (!sel) return `<h2 tabindex="-1">Pick what changed</h2><p>Choose a part on the left, then <b>Show its checklist</b>.</p>`;
    const k = cat.kinds.find(x => x.kind === sel.kind) || {};
    if (!plan || !plan.started) {
      // Not started: the checklist as it would be, nothing counted yet.
      // Start first: a long checklist scrolls, and its button must not scroll away.
      return `<h2 tabindex="-1">${esc((plan && plan.title) || k.title)}</h2><p>${esc(k.when)}.</p>
        <div class="row"><button class="btn primary" id="p-start" data-tip="parts.start">Start this checklist</button>
          <span class="small">Starting stamps the time: only what you do from now on counts for this part, because it changed. Starting moves nothing.</span></div>
        ${plan && plan.jobs ? jobsList(plan.jobs, null, false) : ""}`;
    }
    const job = plan.jobs.find(j => j.id === picked) || plan.next || plan.jobs[0];
    picked = job ? job.id : null;
    const allDone = !plan.next;
    return `<div class="row" style="justify-content:space-between;flex-wrap:wrap">
        <h2 tabindex="-1">${esc(plan.title)} <span class="muted small">${plan.done} of ${plan.of} done · started ${when(plan.started)}</span></h2>
        <div class="row">
          <label class="row small howto-switch" data-tip="howto.switch"><input type="checkbox" data-howto-switch ${HowTo.shown() ? "checked" : ""}> How-to instructions</label>
          <button class="btn small" id="p-restart" data-tip="parts.restart">Start over</button>
          ${allDone ? "" : `<button class="btn small" id="p-stop" data-tip="parts.stop">Stop this checklist</button>`}</div>
      </div>
      <p class="small">${esc(plan.what)}</p>
      ${(plan.bring || []).length ? `<p class="small muted"><b>Bring:</b> ${plan.bring.map(esc).join(" · ")}</p>` : ""}
      ${jobsList(plan.jobs, picked, true)}
      ${job ? `<div class="panel part-job"><h3>${esc(job.title)}</h3>
        ${job.how ? HowTo.block(`<ol class="small">${job.how.map(h => `<li>${esc(h)}</li>`).join("")}</ol>`) : ""}
        <div id="p-act">${actions(job)}</div>
        <div id="p-result">${result[job.id] || ""}</div>
        ${asking && asking.step === job.id ? asking.html : ""}</div>` : ""}
      <div class="row">${plan.next && plan.next.id !== picked ? `<button class="btn primary" data-job="${esc(plan.next.id)}" data-tip="parts.next">First step not done: ${esc(plan.next.title)} →</button>`
        : allDone ? `<span class="chip good">All done for this part</span> <button class="btn primary" id="p-close" data-tip="parts.stop">Close it</button>` : ""}</div>`;
  }

  // What a step's own buttons do, where the step is done here rather than in another tool.
  function actions(job) {
    const g = job.go || {};
    const kind = sel.kind;
    if (kind === "module" && job.id === "hand_wheel") return `<p class="small">Robot disabled. Press Record, then roll <b>${esc(sel.which)}</b>'s wheel so its top moves toward the front, about one turn. Leave the others alone.</p>
      <button class="btn primary" data-act="hand_wheel" data-tip="parts.record">Record (20 s)</button>`;
    if (kind === "module" && job.id === "hand_steer") return `<p class="small">Robot disabled. Press Record, then turn <b>${esc(sel.which)}</b> counter-clockwise, seen from above, about a quarter turn.</p>
      <button class="btn primary" data-act="hand_steer" data-tip="parts.record">Record (20 s)</button>`;
    if (kind === "module" && job.id === "offset") return `<p class="small">Robot disabled. Point <b>${esc(sel.which)}</b>'s wheel straight ahead with the bevel gear (the gear on the side of the wheel) toward the robot's LEFT; hold it with a straight-edge against the frame. Then capture: only its offset changes.</p>
      <button class="btn primary" data-act="offset" data-tip="parts.offset">Capture its offset (4 s)</button>`;
    if (kind === "module" && job.id === "direction") return `<p class="small">On blocks, robot enabled, deadman held. All four wheels spin (forward, stop, backward); watch the TOP of <b>${esc(sel.which)}</b>'s tire while the speed is positive.</p>
      <button class="btn primary" data-act="direction" data-tip="parts.direction">Run it</button>`;
    if (kind === "gyro" && job.id === "hand_gyro") return `<p class="small">Robot disabled, on the floor. Press Record, then turn the whole robot counter-clockwise, seen from above, about a quarter turn.</p>
      <button class="btn primary" data-act="hand_gyro" data-tip="parts.record-gyro">Record (20 s)</button>`;
    if (kind === "field" && job.id === "type") return `<div class="row"><label class="small" data-tip="parts.field">This field is <select id="p-field"><option value="welded">Welded</option><option value="andymark">AndyMark</option></select></label>
      <button class="btn primary" data-act="type" data-tip="parts.field-save">Save it</button></div>`;
    if (kind === "system" && job.id === "direction") return `<p class="small">Robot disabled. Move <b>${esc(sel.which)}</b> by hand toward its top (deployed, raised) end and watch its reading: <b class="mono" id="p-sys-live">…</b></p>
      <div class="row"><button class="btn primary" data-act="sys_dir_up" data-tip="parts.sys-up">It goes up</button>
        <button class="btn" data-act="sys_dir_down" data-tip="parts.sys-down">It goes down</button></div>`;
    if (kind === "system" && job.id === "code_gains") return `<p class="small">Put the gains that worked into <b>${esc(sel.which)}</b>'s subsystem code, redeploy, and run it once more at full speed.</p>
      <button class="btn primary" data-act="sys_code" data-tip="parts.sys-code">Done: in the code and redeployed</button>`;
    if (kind === "field" && job.id === "upload") return `<button class="btn primary" data-act="upload" data-tip="parts.upload">Done: uploaded to every camera</button>`;
    if (job.go) return `<button class="btn primary" data-go-part data-tip="parts.go">${g.tune ? `Open the tuner${g.module ? ` on ${esc(g.module)}` : ""}` : g.guide ? "Open it in the Guide" : g.part ? "Open that part"
      : g.tab === "systems" ? `Open it in Systems${g.speed ? `, at ${g.speed} speed` : ""}` : "Go there"}</button>`;
    return "";
  }

  function mount() {
    const b = id => $(id, root);
    if (b("#p-start")) b("#p-start").onclick = () => start();
    if (b("#p-restart")) b("#p-restart").onclick = e => twice(e, `Press again: forget ${plan.done} done step${plan.done === 1 ? "" : "s"}`, start);
    if (b("#p-stop")) b("#p-stop").onclick = e => twice(e, `Press again: forget ${plan.done} done step${plan.done === 1 ? "" : "s"}`, stop);
    if (b("#p-close")) b("#p-close").onclick = stop;
    const sw = $("[data-howto-switch]", $("#p-body", root));
    if (sw) sw.onchange = e => HowTo.set(e.target.checked);
    $$("[data-job]", root).forEach(x => x.onclick = () => { picked = x.dataset.job; showJob = true; paint(); });
    const gp = $("[data-go-part]", root);
    const job = plan && plan.jobs ? plan.jobs.find(j => j.id === picked) : null;
    if (gp && job) gp.onclick = () => HowTo.go(job.go);
    $$("[data-act]", root).forEach(x => x.onclick = () => act(x.dataset.act));
    // The mechanism's reading, live, while someone moves it by hand.
    const lv = $("#p-sys-live", root);
    if (lv) {
      const tick = async () => {
        if (!on || !root.classList.contains("on") || !document.body.contains(lv)) { clearInterval(liveTimer); return; }
        const r = await App.api("/api/systems");
        const s = ((r && r.systems) || []).find(x => x.name === sel.which);
        // In the team's units when the mechanism's are meters or radians (inches, degrees).
        const su = U.sys(s && s.units);
        lv.textContent = s && s.position != null && isFinite(s.position) ? `${+(s.position * su.k).toPrecision(4)} ${su.label}` : "no reading (connected?)";
      };
      tick();
      liveTimer = setInterval(tick, 500);
    }
    // A question waiting for the person (the direction check): wired on every paint, so a repaint
    // from the run that asked it can't leave dead buttons.
    $$("[data-dir]", root).forEach(x => x.onclick = async () => {
      const ok = x.dataset.dir === "yes";
      asking = null;
      if (await markStep("direction", ok, ok ? "Rolls forward." : "Rolled backwards.")) {
        if (!ok) Trouble.open("wheel_backwards");
      }
      paint();
    });
  }

  // Forgetting work takes two presses.
  function twice(e, ask, then) {
    if (e.target.dataset.sure) { then(); return; }
    e.target.dataset.sure = "1";
    e.target.textContent = ask;
  }

  async function start() {
    const b = $("#p-start", root) || $("#p-restart", root);
    const label = b ? b.textContent : "";
    if (b) { b.disabled = true; b.textContent = "Starting…"; }
    const r = await App.api("/api/parts/start", sel);
    if (r.ok === false) {
      App.toast(r.error);
      if (b) { b.disabled = false; b.textContent = label; }
      return;
    }
    result = {}; asking = null; picked = null; focusNext = true;
    paint();
  }

  async function stop() {
    await App.api("/api/parts/stop", sel);
    sel = null; plan = null; result = {}; asking = null; focusNext = true;
    paint();
  }

  /** Records a step's result; the simulator's never count. Returns whether it was recorded. */
  async function markStep(step, ok, detail) {
    if (App.env() === "SIM") {
      App.toast("The simulator's results never count for a real part: nothing was recorded.", 6000);
      return false;
    }
    const r = await App.api("/api/parts/mark", Object.assign({ step, result: ok ? "pass" : "fail", detail }, sel));
    if (r.ok === false) { App.toast(r.error); return false; }
    return true;
  }

  async function act(what) {
    const m = sel.which;
    try {
      if (what === "sys_dir_up" || what === "sys_dir_down") {
        const up = what === "sys_dir_up";
        await markStep("direction", up, up ? "Its reading goes up toward its top end." : "It reads backwards: invert its encoder in the code before any test.");
      } else if (what === "sys_code") {
        await markStep("code_gains", true, "In the code and redeployed.");
      } else if (what === "hand_wheel" || what === "hand_steer") {
        const kind = what === "hand_wheel" ? "wheel" : "steer";
        App.toast(kind === "wheel" ? `Recording: roll ${m}'s wheel forward now.` : `Recording: turn ${m} counter-clockwise now.`, 6000);
        const doc = await App.runTest("capture", "ALL", { duration_s: 20, coast: 1 });
        const v = (await App.api("/api/handcheck", { file: doc._file, kind, sign: 1 }))[m];
        if (!v) { App.toast(`No reading for ${m}: is it named that in the robot's files?`, 6000); return; }
        const ok = kind === "wheel" ? v.drive.verdict === "AGREES"
          : v.absolute.verdict === "AGREES" && v.motor.verdict === "AGREES" && Math.abs(v.motor_per_module_deg - 1) < 0.03;
        const word = kind === "wheel" ? v.drive.verdict : v.absolute.verdict !== "AGREES" ? "absolute encoder " + v.absolute.verdict
          : v.motor.verdict !== "AGREES" ? "motor encoder " + v.motor.verdict : Math.abs(v.motor_per_module_deg - 1) >= 0.03 ? `gear ratio (motor per module ${fmt(v.motor_per_module_deg, 3)})` : "AGREES";
        result[what] = `<p><span class="level ${ok ? "ok" : "error"}">${esc(word)}</span> ${ok ? "Every sensor agrees." :
          "INVERTED: flip that setting for this module. NO_MOTION: it didn't move far enough, or that sensor isn't reporting. AMBIGUOUS: move it one way only."}</p>`;
        await markStep(what, ok, ok ? "Every sensor agrees." : word);
      } else if (what === "hand_gyro") {
        App.toast("Recording: turn the whole robot counter-clockwise now.", 6000);
        const doc = await App.runTest("capture", "ALL", { duration_s: 20, coast: 1 });
        const g = (await App.api("/api/handcheck", { file: doc._file, kind: "gyro", sign: 1 })).gyro || {};
        const h = g.heading || {}, ok = h.verdict === "AGREES";
        result.hand_gyro = `<p><span class="level ${ok ? "ok" : "error"}">${esc(h.verdict || "NO_DATA")}</span> turned ${fmt(h.net || 0, 1)}°.
          ${h.verdict === "INVERTED" ? `Counter-clockwise reads negative. <button class="btn small" data-imu-fix data-tip="guide.imufix">Flip invertedIMU…</button>` : ""}</p>`;
        await markStep("hand_gyro", ok, ok ? "Counter-clockwise reads positive." : `${h.verdict}: ${fmt(h.net || 0, 1)}°`);
        await paint();
        const fx = $("[data-imu-fix]", root);
        if (fx && g.fix) fx.onclick = () => App.previewAndSave({ kind: "edit", file: g.fix.file, path: g.fix.path, value: g.fix.value }, "Flip the gyro's direction");
        return;
      } else if (what === "offset") {
        const doc = await App.runTest("capture", "ALL", { duration_s: 4, coast: 1 });
        const r = (await App.api("/api/offsets", { file: doc._file }))[m];
        if (!r) { App.toast(`No reading for ${m}.`, 6000); return; }
        result.offset = `<p class="small">Reads ${fmt(r.reading_deg, 2)}° · offset now ${fmt(r.old, 2)}° → new ${fmt(r.new, 2)}°${r.steady ? "" : " · <b>it moved during the capture: hold it still and capture again</b>"}</p>`;
        if (!r.steady) await markStep("offset", false, "It moved during the capture.");
        else if (Math.abs(r.new - r.old) < 0.01) await markStep("offset", true, `Already right: ${fmt(r.old, 2)}°.`);
        else if (await App.previewAndSave({ kind: "offsets", file: doc._file, module: m }, `New offset for ${m}`)) {
          await markStep("offset", true, `Offset ${fmt(r.new, 2)}°: redeploy, then check it reads 0° pointing straight.`);
        }
      } else if (what === "direction") {
        if (App.env() !== "BLOCKS" && App.env() !== "SIM") { openEnvironment("BLOCKS"); return; }
        const doc = await App.runTest("drive_step", m, { s0: 0.4, s1: 0, s2: -0.4, s3: 0, hold_s: 1.5 });
        if (doc.outcome !== "DONE") { App.toast(doc.message || "Stopped part-way.", 6000); return; }
        asking = { step: "direction", html: `<p>Did the top of <b>${esc(m)}</b>'s tire roll toward the front while the speed was positive?</p>
          <div class="row"><button class="btn primary" data-dir="yes" data-tip="parts.dir-yes">Yes</button><button class="btn" data-dir="no" data-tip="parts.dir-no">No, backwards</button></div>` };
      } else if (what === "type") {
        const v = $("#p-field", root).value;
        const lint = App.lint || await App.api("/api/lint");
        const now = (((lint || {}).slothtune || {}).vision || {}).field || "welded";
        if (v === now || await App.previewAndSave({ kind: "edit", file: "slothtune.json", path: ["vision", "field"], value: v }, `This field is the ${v === "andymark" ? "AndyMark" : "welded"} one`)) {
          await markStep("field_type", true, v === "andymark" ? "AndyMark" : "Welded");
        }
      } else if (what === "upload") {
        await markStep("upload", true, "Uploaded to every camera.");
      }
      paint();
    } catch (e) { App.toast(e.message, 6000); }
  }

  return { open, off, paint, leave, get on() { return on; } };
})();
