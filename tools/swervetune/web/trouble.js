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
      <div class="panel"><h2>What is the robot doing?</h2>
        <p class="hint">Pick the closest. The questions go cheapest and most likely first; nothing needs the robot moving until the motionless checks pass.</p></div>
      <div class="symptoms">${symptoms.map(s => `<button class="symptom" data-id="${esc(s.id)}"><span class="t">${esc(s.title)}</span><span class="d">${esc(s.looks_like)}</span></button>`).join("")}</div></div>`;
    $$(".symptom", root).forEach(b => b.onclick = () => open(b.dataset.id));
  }

  async function open(id) {
    App.show("trouble");
    current = await App.api("/api/diagnose/" + encodeURIComponent(id));
    answers = current.checks.map(c => c.auto_answer || null);
    paint();
  }

  function actionButton(a) {
    if (!a) return "";
    const label = { run: `Run ${a.test}`, tune: "Open the tuner", guide: "Open that guide step", troubleshoot: "Open that symptom", config: "Preview the edit" }[a.type] || "Do this";
    return `<button class="btn small primary" data-act='${esc(JSON.stringify(a))}'>${esc(label)}</button>`;
  }

  function paint() {
    const c = current;
    const firstOpen = answers.findIndex(a => a === null);
    const failed = answers.indexOf("no");
    const at = failed >= 0 ? failed : firstOpen;
    root.innerHTML = `<div class="stack">
      <div class="panel"><div class="row" style="justify-content:space-between"><h2>${esc(c.title)}</h2>
        <button class="btn" id="tr-back">All symptoms</button></div><p class="hint">${esc(c.looks_like)}</p></div>
      <div class="checks">${c.checks.map((k, i) => {
        const a = answers[i];
        const state = a === "yes" ? "passed" : a === "no" ? "failed" : i === at ? "current" : "";
        return `<div class="check ${state}">
          <div class="row" style="justify-content:space-between"><span class="q">${i + 1}. ${esc(k.q)}</span><span class="chip">${esc(k.where)}</span></div>
          <div class="hint">${esc(k.how)}</div>
          ${k.auto_answer === "no" ? `<div class="small"><span class="level error">tool found</span> ${esc((k.evidence || []).join(", "))}</div>` : ""}
          ${k.auto_answer === "yes" ? `<div class="small"><span class="level ok">tool checked</span> nothing wrong in the configuration</div>` : ""}
          ${a === "no" ? `<div class="callout safety"><b>Cause:</b> ${esc(k.if_no)}<br><b>Fix:</b> ${esc(k.fix)}</div>
             <div class="row">${actionButton(k.action)}<button class="btn small" data-redo="${i}">I fixed it, check again</button></div>` : ""}
          ${i === at && a === null ? `<div class="row"><button class="btn small primary" data-yes="${i}">Yes</button>
             <button class="btn small" data-no="${i}">No</button>${actionButton(k.action)}</div>` : ""}
        </div>`;
      }).join("")}</div>
      ${failed < 0 && firstOpen < 0 ? `<div class="panel"><b>Every usual cause checked out.</b>
        <p>Record a capture while the problem happens (Guide, Sensor health, or the Tune tab), then bring the saved run to a mentor - the Runs tab has the data.</p></div>` : ""}
    </div>`;
    $("#tr-back", root).onclick = paintList;
    $$("[data-yes]", root).forEach(b => b.onclick = () => { answers[+b.dataset.yes] = "yes"; paint(); });
    $$("[data-no]", root).forEach(b => b.onclick = () => { answers[+b.dataset.no] = "no"; paint(); });
    $$("[data-redo]", root).forEach(b => b.onclick = () => { answers[+b.dataset.redo] = null; paint(); });
    $$("[data-act]", root).forEach(b => b.onclick = () => act(JSON.parse(b.dataset.act)));
  }

  function act(a) {
    if (a.type === "run" || a.type === "tune") {
      const loop = { steer_step: "steer", drive_step: "drive", drive_ff: "ff", spin: "spin", straight: "straight" }[a.test] || a.loop;
      if (loop && loop !== "chassis") { Tune.open(loop, { target: "robot" }); return; }
      if (a.test === "capture") { App.show("guide"); return; }
      Tune.open("spin");
    } else if (a.type === "guide") {
      App.show("guide");
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
