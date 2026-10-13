// Redo one part: a module that was replaced or acts up, a motor, the gyro, a camera, a new field,
// new wheels. Shown in the Guide tab instead of the whole path. Each part's checklist counts only
// what was done to that part since the person started it (server: setup.part_plan), and its steps
// open the same tools, set to that part: the tuner on that module, the camera tool on that camera.
"use strict";

const Parts = (() => {
  const root = $("#tab-guide");
  const WORD = { done: "done", attention: "needs a fix", todo: "to do", later: "later", optional: "optional", skip: "not needed" };
  const CHIP = { done: "good", attention: "bad", todo: "", later: "info", optional: "", skip: "" };
  let on = false, sel = null, cat = null, plan = null, picked = null, result = {}, seq = 0;

  function open(kind, which) {
    on = true;
    sel = kind ? { kind, which: which || "" } : sel;
    picked = null;
    if (root.classList.contains("on")) paint(); else App.show("guide");
  }

  function leave() {
    on = false;
    Guide.refresh();
  }

  async function paint() {
    // A slow answer must never paint over a newer one, or over the Guide once the person left.
    const my = ++seq;
    const c = await App.api("/api/parts");
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
    root.innerHTML = `<div class="split">
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
      sel = { kind: b.dataset.show, which: s ? s.value : "" };
      picked = null;
      paint();
    });
    $$("[data-open]", root).forEach(b => b.onclick = () => { sel = { kind: b.dataset.open, which: b.dataset.which }; picked = null; paint(); });
    mount();
  }

  function body() {
    if (!sel) return `<h2>Pick what changed</h2><p>Choose a part on the left, then <b>Show its checklist</b>.</p>`;
    const k = cat.kinds.find(x => x.kind === sel.kind) || {};
    const name = `${k.title}${sel.which ? `: ${sel.which}` : ""}`;
    if (!plan || !plan.started) {
      return `<h2>${esc(name)}</h2><p>${esc(k.when)}.</p>
        <p class="small">Starting makes a checklist for this part only. Work done before now doesn't count: the part changed.</p>
        <div class="row"><button class="btn primary" id="p-start" data-tip="parts.start">Start: ${esc(name)}</button></div>`;
    }
    const job = plan.jobs.find(j => j.id === picked) || plan.next || plan.jobs[0];
    picked = job ? job.id : null;
    const when = s => s ? `${+s.slice(4, 6)}/${+s.slice(6, 8)} ${s.slice(9, 11)}:${s.slice(11, 13)}` : "";
    return `<div class="row" style="justify-content:space-between;flex-wrap:wrap">
        <h2 tabindex="-1">${esc(plan.title)} <span class="muted small">${plan.done} of ${plan.of} done · started ${when(plan.started)}</span></h2>
        <div class="row"><button class="btn small" id="p-restart" data-tip="parts.restart">Start over</button><button class="btn small" id="p-stop" data-tip="parts.stop">Finished: close it</button></div>
      </div>
      <p class="small">${esc(plan.what)}</p>
      ${(plan.bring || []).length ? `<p class="small muted"><b>Bring:</b> ${plan.bring.map(esc).join(" · ")}</p>` : ""}
      <ol class="plan-jobs">${plan.jobs.map(j => `<li class="${j.id === picked ? "now" : ""} ${j.status}">
        <span class="chip ${CHIP[j.status]}">${WORD[j.status]}</span>
        <span class="plan-t"><button class="linkish" data-job="${esc(j.id)}" data-tip="parts.job" data-quiet><b>${esc(j.title)}</b></button> <span class="small muted">${esc(j.detail || "")}</span></span></li>`).join("")}</ol>
      ${job ? `<div class="panel part-job"><h3>${esc(job.title)}</h3>
        ${job.how ? HowTo.block(`<ol class="small">${job.how.map(h => `<li>${esc(h)}</li>`).join("")}</ol>`) : ""}
        <div id="p-act">${actions(job)}</div>
        <div id="p-result">${result[job.id] || ""}</div></div>` : ""}
      <div class="row">${plan.next && plan.next.id !== picked ? `<button class="btn primary" data-job="${esc(plan.next.id)}" data-tip="parts.next">Next: ${esc(plan.next.title)} →</button>`
        : !plan.next ? `<span class="chip good">All done for this part</span> <button class="btn primary" id="p-stop2" data-tip="parts.stop">Close it</button>` : ""}</div>`;
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
    if (kind === "module" && job.id === "direction") return `<p class="small">On blocks, robot enabled, deadman held. Only <b>${esc(sel.which)}</b> drives: forward, stop, backward. Watch the TOP of its tire while the speed is positive.</p>
      <button class="btn primary" data-act="direction" data-tip="parts.direction">Run it</button>`;
    if (kind === "field" && job.id === "type") return `<div class="row"><label class="small" data-tip="parts.field">This field is <select id="p-field"><option value="welded">Welded</option><option value="andymark">AndyMark</option></select></label>
      <button class="btn primary" data-act="type" data-tip="parts.field-save">Save it</button></div>`;
    if (kind === "field" && job.id === "upload") return `<button class="btn primary" data-act="upload" data-tip="parts.upload">Done: uploaded to every camera</button>`;
    if (job.go) return `<button class="btn primary" data-go-part data-tip="parts.go">${g.tune ? `Open the tuner${g.module ? ` on ${esc(g.module)}` : ""}` : g.guide ? "Open it in the Guide" : g.part ? "Open that part" : "Go there"}</button>`;
    return "";
  }

  function mount() {
    const b = id => $(id, root);
    if (b("#p-start")) b("#p-start").onclick = () => start();
    if (b("#p-restart")) b("#p-restart").onclick = e => {
      // Two presses: starting over forgets what was done for this part.
      if (e.target.dataset.sure) { start(); return; }
      e.target.dataset.sure = "1";
      e.target.textContent = "Press again: forget what was done";
    };
    [b("#p-stop"), b("#p-stop2")].forEach(x => { if (x) x.onclick = stop; });
    $$("[data-job]", root).forEach(x => x.onclick = () => { picked = x.dataset.job; paint(); });
    const gp = $("[data-go-part]", root);
    const job = plan && plan.jobs ? plan.jobs.find(j => j.id === picked) : null;
    if (gp && job) gp.onclick = () => HowTo.go(job.go);
    $$("[data-act]", root).forEach(x => x.onclick = () => act(x.dataset.act));
  }

  async function start() {
    const b = $("#p-start", root) || $("#p-restart", root);
    if (b) { b.disabled = true; b.textContent = "Starting…"; }
    const r = await App.api("/api/parts/start", sel);
    if (r.ok === false) { App.toast(r.error); return; }
    result = {}; picked = null;
    paint();
  }

  async function stop() {
    await App.api("/api/parts/stop", sel);
    sel = null; plan = null; result = {};
    paint();
  }

  async function markStep(step, ok, detail) {
    const r = await App.api("/api/parts/mark", Object.assign({ step, result: ok ? "pass" : "fail", detail }, sel));
    if (r.ok === false) App.toast(r.error);
  }

  async function act(what) {
    const m = sel.which;
    try {
      if (what === "hand_wheel" || what === "hand_steer") {
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
      } else if (what === "offset") {
        const doc = await App.runTest("capture", "ALL", { duration_s: 4, coast: 1 });
        const r = (await App.api("/api/offsets", { file: doc._file }))[m];
        if (!r) { App.toast(`No reading for ${m}.`, 6000); return; }
        result.offset = `<p class="small">Reads ${fmt(r.reading_deg, 2)}° · offset now ${fmt(r.old, 2)}° → new ${fmt(r.new, 2)}°${r.steady ? "" : " · <b>it moved during the capture: hold it still and capture again</b>"}</p>`;
        if (!r.steady) { await markStep("offset", false, "It moved during the capture."); }
        else if (await App.previewAndSave({ kind: "offsets", file: doc._file, module: m }, `New offset for ${m}`)) {
          await markStep("offset", true, `Offset ${fmt(r.new, 2)}°: redeploy, then check it reads 0° pointing straight.`);
        }
      } else if (what === "direction") {
        if (App.env() !== "BLOCKS" && App.env() !== "SIM") { openEnvironment("BLOCKS"); return; }
        const doc = await App.runTest("drive_step", m, { s0: 0.4, s1: 0, s2: -0.4, s3: 0, hold_s: 1.5 });
        if (doc.outcome !== "DONE") { App.toast(doc.message || "Stopped part-way.", 6000); return; }
        result.direction = `<p>Did the top of <b>${esc(m)}</b>'s tire roll toward the front while the speed was positive?</p>
          <div class="row"><button class="btn primary" data-dir="yes" data-tip="parts.dir-yes">Yes</button><button class="btn" data-dir="no" data-tip="parts.dir-no">No, backwards</button></div>`;
        await paint();
        $$("[data-dir]", root).forEach(x => x.onclick = async () => {
          const ok = x.dataset.dir === "yes";
          result.direction = "";
          await markStep("direction", ok, ok ? "Rolls forward." : "Rolled backwards.");
          if (!ok) Trouble.open("wheel_backwards"); else paint();
        });
        return;
      } else if (what === "type") {
        const v = $("#p-field", root).value;
        const lint = App.lint || await App.api("/api/lint");
        const now = (((lint || {}).swervetune || {}).vision || {}).field || "welded";
        if (v === now || await App.previewAndSave({ kind: "edit", file: "swervetune.json", path: ["vision", "field"], value: v }, `This field is the ${v === "andymark" ? "AndyMark" : "welded"} one`)) {
          await markStep("field_type", true, v === "andymark" ? "AndyMark" : "Welded");
        }
      } else if (what === "upload") {
        await markStep("upload", true, "Uploaded to every camera.");
      }
      paint();
    } catch (e) { App.toast(e.message, 6000); }
  }

  return { open, paint, leave, get on() { return on; } };
})();
