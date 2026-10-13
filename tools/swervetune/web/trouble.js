// Troubleshoot tab: pick what you see; answer one question at a time; the tool fills in what it
// already knows from the config and the live robot.
"use strict";

const Trouble = (() => {
  const root = $("#tab-trouble");
  let symptoms = [], current = null, answers = [];

  async function list() {
    const r = await App.api("/api/symptoms");
    symptoms = r.symptoms || [];
    paintList();
  }

  function paintList() {
    root.innerHTML = `<div class="stack">
      <div class="panel"><h2 data-tip="trouble.list">What is the robot doing?</h2>
        <p class="hint">Pick the closest. Then answer one yes/no question at a time: <b>yes means that part is fine</b>, and the first <b>no</b> is usually the cause. The questions go cheapest and most likely first; nothing needs the robot moving until the motionless checks pass.</p></div>
      <div class="symptoms">${symptoms.map(s => `<button class="symptom" data-id="${esc(s.id)}" data-tip="trouble.sym.${esc(s.id)}" data-quiet><span class="t">${esc(s.title)}</span><span class="d">${esc(s.looks_like)}</span></button>`).join("")}</div></div>`;
    $$(".symptom", root).forEach(b => b.onclick = () => open(b.dataset.id));
  }

  async function open(id) {
    App.show("trouble");
    current = await App.api("/api/diagnose/" + encodeURIComponent(id));
    answers = current.checks.map(c => c.auto_answer || null);
    paint();
  }

  // Which tuner each test lives in. A "run" action opens that tuner; it never starts a test by itself.
  const TEST_LOOP = { steer_step: "steer", drive_step: "drive", drive_ff: "ff", slip: "slip", spin: "spin", straight: "straight" };
  const LOOP_NAME = { steer: "Steering", drive: "Drive speed", ff: "Feedforward", slip: "Slip current", spin: "Spin", straight: "Straight line" };
  const loopOf = a => TEST_LOOP[a.test] || (a.loop === "chassis" ? "spin" : a.loop) || "spin";

  function actionButton(a) {
    if (!a) return "";
    let label = { guide: "Open that Guide step", troubleshoot: "Open that symptom", config: "Preview the file change" }[a.type] || "Do this";
    if (a.type === "run" || a.type === "tune") {
      const where = a.env && a.env !== "ANY" ? ` (${whereWord(a.env).toLowerCase()})` : "";
      label = a.test === "capture" ? "Open Sensor health in the Guide" : `Open the ${LOOP_NAME[loopOf(a)]} tuner${where}`;
    }
    return `<button class="btn small primary" data-act='${esc(JSON.stringify(a))}' data-tip="trouble.action" data-quiet>${esc(label)}</button>`;
  }

  function paint() {
    const c = current;
    const firstOpen = answers.findIndex(a => a === null);
    const failed = answers.indexOf("no");
    const at = failed >= 0 ? failed : firstOpen;
    root.innerHTML = `<div class="stack">
      <div class="panel"><div class="row" style="justify-content:space-between"><h2>${esc(c.title)}</h2>
        <button class="btn" id="tr-back" data-tip="trouble.back" data-quiet>All symptoms</button></div><p class="hint">${esc(c.looks_like)}</p>
        ${c.note ? `<div class="callout info">${Learn.link(c.note, 2)}</div>` : ""}
        <p class="small"><b>Yes</b> means that part is fine. The first <b>No</b> is usually the cause.</p></div>
      <div class="checks">${c.checks.map((k, i) => {
        const a = answers[i];
        const state = a === "yes" ? "passed" : a === "no" ? "failed" : i === at ? "current" : "";
        return `<div class="check ${state}">
          <div class="row" style="justify-content:space-between"><span class="q" id="tq-${i}">${a === "yes" ? `<span class="level ok">fine</span> ` : ""}${i + 1}. ${esc(k.q)}</span><span class="chip" data-tip="trouble.where" data-quiet>${esc(whereWord(k.where))}</span></div>
          ${a === "yes" ? "" : `<div class="hint">${Learn.link(k.how, 2)}</div>`}
          ${k.auto_answer === "no" ? `<div class="small"><span class="level error" data-tip="trouble.found" data-quiet>tool found</span> ${esc((k.evidence || []).join(", "))}</div>` : ""}
          ${k.auto_answer === "yes" ? `<div class="small"><span class="level ok" data-tip="trouble.found" data-quiet>tool checked</span> nothing wrong in the configuration</div>` : ""}
          ${a === "no" ? `<div class="callout safety"><b>Cause:</b> ${esc(k.if_no)}<br><b>Fix:</b> ${esc(k.fix)}</div>
             <div class="row">${actionButton(k.action)}<button class="btn small" data-redo="${i}" data-tip="trouble.redo" data-quiet>I fixed it, check again</button></div>` : ""}
          ${i === at && a === null ? `<div class="row"><button class="btn small primary" data-yes="${i}" aria-describedby="tq-${i}" data-tip="trouble.yes" data-quiet>Yes</button>
             <button class="btn small" data-no="${i}" aria-describedby="tq-${i}" data-tip="trouble.no" data-quiet>No</button>${actionButton(k.action)}</div>` : ""}
        </div>`;
      }).join("")}</div>
      ${failed < 0 && firstOpen < 0 ? `<div class="panel"><b>Every usual cause checked out.</b>
        <p>Record a capture while the problem happens (Guide, Sensor health, or the Tune tab), then bring the saved run to a mentor - the Runs tab has the data.</p></div>` : ""}
    </div>`;
    $("#tr-back", root).onclick = paintList;
    $$("[data-yes]", root).forEach(b => b.onclick = () => answer(+b.dataset.yes, "yes"));
    $$("[data-no]", root).forEach(b => b.onclick = () => answer(+b.dataset.no, "no"));
    $$("[data-redo]", root).forEach(b => b.onclick = () => answer(+b.dataset.redo, null));
    $$("[data-act]", root).forEach(b => b.onclick = () => act(JSON.parse(b.dataset.act)));
  }

  // Every answer repaints the list, so focus moves to the question now waiting, not to the page top.
  function answer(i, v) {
    answers[i] = v;
    paint();
    const b = $("[data-yes], [data-redo]", root);
    if (b) b.focus();
  }

  function act(a) {
    if (a.type === "run" || a.type === "tune") {
      if (a.test === "capture") { Guide.go("health"); return; }
      Tune.open(loopOf(a), { target: "robot" });
      // Ask where the robot is now, rather than letting Run refuse later.
      if (a.env && a.env !== "ANY" && App.connected() && App.env() !== a.env && App.env() !== "SIM") openEnvironment(a.env);
    } else if (a.type === "guide") {
      Guide.go(a.step);
    } else if (a.type === "troubleshoot") {
      open(a.symptom);
    } else if (a.type === "config") {
      App.previewAndSave({ kind: "edit", file: a.file, path: a.path, value: a.value }, "Change the robot's configuration");
    }
  }

  App.on("tab", t => { if (t === "trouble" && !current) list(); });
  list();
  return { open };
})();
