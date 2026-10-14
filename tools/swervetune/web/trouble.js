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

  // The first page shows the symptoms or the robot's messages, one at a time: side by side, neither
  // fit a laptop screen. The switch carries the messages' count, red while an error keeps happening.
  let homeView = "symptoms";
  function paintList() {
    root.innerHTML = `<div class="stack">
      <div class="panel"><div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="trouble.list">${homeView === "symptoms" ? "What is the robot doing?" : "What the robot keeps reporting"}</h2>
          <div class="seg" role="group" aria-label="Show">
            <button data-home="symptoms" class="${homeView === "symptoms" ? "on" : ""}" aria-pressed="${homeView === "symptoms"}" data-tip="trouble.list">Symptoms</button>
            <button data-home="msgs" class="${homeView === "msgs" ? "on" : ""}" aria-pressed="${homeView === "msgs"}" data-tip="trouble.msgs">Robot messages <span id="tr-msgs-count" class="chip"></span></button></div></div>
        ${homeView === "symptoms" ? `<p class="hint wide">Pick the closest. Then answer one yes/no question at a time: <b>yes means that part is fine</b>, and the first <b>no</b> is usually the cause. The questions go cheapest and most likely first; nothing needs the robot moving until the motionless checks pass.</p>`
          : `<div class="row" style="justify-content:space-between"><p class="small muted" id="tr-msgs-src"></p>
              <button class="btn small" id="tr-msgs-clear" data-tip="trouble.msgs-clear" data-quiet>Clear the counts</button></div>`}</div>
      ${homeView === "symptoms" ? `<div class="panel sym-groups">${[["connect", "Connecting to the robot"], ["robot", "Driving, motors and mechanisms"]].map(([g, name]) => {
          const S = symptoms.filter(s => (s.group || "robot") === g);
          return S.length ? `<h3>${name}</h3><div class="symptoms">${S.map(s => `<button class="symptom" data-id="${esc(s.id)}" data-tip="trouble.sym.${esc(s.id)}" data-quiet><span class="t">${esc(s.title)}</span><span class="d">${esc(s.looks_like)}</span></button>`).join("")}</div>` : "";
        }).join("")}</div>`
        : `<div class="panel tr-msgs"><div id="tr-msgs-list" class="tr-msgs-list"></div></div>`}</div>`;
    $$(".symptom", root).forEach(b => b.onclick = () => open(b.dataset.id));
    $$("[data-home]", root).forEach(b => b.onclick = () => { homeView = b.dataset.home; paintList(); });
    const clear = $("#tr-msgs-clear", root);
    if (clear) clear.onclick = async () => { await App.api("/api/robotlog/clear", {}); loadMessages(); };
    loadMessages();
  }

  // ---------------------------------------------------------------- what the robot keeps reporting
  // Every error and warning the robot has reported, each once with how often and how recently: not a
  // stream of lines, so what keeps coming back stands out.
  const ago = s => s < 60 ? `${Math.round(s)} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${(s / 3600).toFixed(1)} h ago`;
  async function loadMessages() {
    const r = await App.api("/api/robotlog");
    if (!r || r.ok === false) return;
    const M0 = r.messages || [], count = $("#tr-msgs-count", root);
    if (count) {
      const hot = M0.some(m => m.ongoing && m.level === "error");
      count.textContent = M0.length;
      count.className = "chip" + (hot ? " bad" : M0.some(m => m.ongoing) ? " warn" : "");
      count.hidden = !M0.length;
    }
    const list = $("#tr-msgs-list", root);
    if (!list) return;
    const src = !r.connected ? "Connect to the robot: it counts what the robot reports from then on."
      : `Since ${r.since_s < 90 ? "just now" : ago(r.since_s).replace(" ago", "") + " ago"}: the robot's alerts, and its console (${esc(r.console)}). "Still happening" means seen in the last minute.`;
    const src_el = $("#tr-msgs-src", root);
    if (src_el._t !== src) { src_el._t = src; src_el.innerHTML = src; }
    const M = r.messages || [];
    const html = !M.length ? (r.connected ? `<p><span class="level ok">ok</span> Nothing reported.</p>` : "")
      : `<table class="t"><tbody>${M.map(m => `<tr class="${m.ongoing ? "ongoing" : ""}">
          <td><span class="level ${m.level === "error" ? "error" : "warn"}">${m.level}</span></td>
          <td><div class="tr-msg-text">${esc(m.text)}</div>
            <div class="small muted">${m.where ? esc(m.where) + " · " : ""}${m.source === "alert" ? "alert" : "console"} · first ${ago(m.first_ago_s)}, last ${ago(m.last_ago_s)}</div></td>
          <td class="num"><b>${m.count}×</b>${m.ongoing ? `<div><span class="chip ${m.level === "error" ? "bad" : "warn"}">still happening</span></div>` : `<div class="small muted">stopped</div>`}</td></tr>`).join("")}</tbody></table>`;
    if (list._h !== html) { list._h = html; list.innerHTML = html; }
  }
  setInterval(() => { if (root.classList.contains("on") && !current) loadMessages(); }, 2000);

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
    let label = { guide: "Open that Guide step", troubleshoot: "Open that symptom", config: "Preview the file change",
      netcheck: "Check the networks" }[a.type] || "Do this";
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
    // One drawing, beside the checks: where to look for the check being answered (or the one that failed).
    const mapAt = at >= 0 && c.checks[at] && c.checks[at].diagram && answers[at] !== "yes" ? at : -1;
    root.innerHTML = `<div class="tr-view">
      <div class="panel"><div class="row" style="justify-content:space-between"><h2>${esc(c.title)}</h2>
        <button class="btn" id="tr-back" data-tip="trouble.back" data-quiet>All symptoms</button></div><p class="hint">${esc(c.looks_like)}</p>
        ${c.note ? `<div class="callout info">${Learn.link(c.note, 2)}</div>` : ""}
        <p class="small"><b>Yes</b> means that part is fine. The first <b>No</b> is usually the cause.</p></div>
      <div class="tr2 ${mapAt >= 0 ? "has-map" : ""}"><div class="checks">${c.checks.map((k, i) => {
        const a = answers[i];
        const state = a === "yes" ? "passed" : a === "no" ? "failed" : i === at ? "current" : "";
        return `<div class="check ${state}">
          <div class="row" style="justify-content:space-between"><span class="q" id="tq-${i}">${a === "yes" ? `<span class="level ok">fine</span> ` : ""}${i + 1}. ${esc(k.q)}</span><span class="chip" data-tip="trouble.where" data-quiet>${esc(whereWord(k.where))}</span></div>
          ${a === "yes" ? "" : `<div class="hint">${Learn.link(k.how, 2)}</div>`}
          ${k.auto_answer === "no" ? `<div class="small"><span class="level error" data-tip="trouble.found" data-quiet>tool found</span> ${esc((k.evidence || []).join(", "))}</div>` : ""}
          ${k.suggest === "yes" && a === null ? (k.suggest_by === "net"
            ? `<div class="small"><span class="level ok" data-tip="trouble.found" data-quiet>network check: fine</span> the network check found this part fine: press Yes if you agree</div>`
            : `<div class="small"><span class="level ok" data-tip="trouble.found" data-quiet>config looks fine</span> the configuration check found nothing wrong here: press Yes if you agree</div>`) : ""}
          ${a === "no" ? `<div class="callout safety"><b>Cause:</b> ${esc(k.if_no)}<br><b>Fix:</b> ${esc(k.fix)}</div>
             <div class="row">${actionButton(k.action)}<button class="btn small" data-redo="${i}" data-tip="trouble.redo" data-quiet>I fixed it, check again</button></div>` : ""}
          ${i === at && a === null ? `<div class="row"><button class="btn small primary" data-yes="${i}" aria-describedby="tq-${i}" data-tip="trouble.yes" data-quiet>Yes</button>
             <button class="btn small" data-no="${i}" aria-describedby="tq-${i}" data-tip="trouble.no" data-quiet>No</button>${actionButton(k.action)}</div>` : ""}
        </div>`;
      }).join("")}</div>
      ${mapAt >= 0 ? `<div class="panel tr-where"><h3>Where to look: check ${mapAt + 1}</h3><div class="frc-slot" data-diagram="${mapAt}"></div></div>` : ""}</div>
      ${failed < 0 && firstOpen < 0 ? `<div class="panel"><b>Every usual cause checked out.</b>
        <p>Record a capture while the problem happens (the Guide's Sensor health step), then bring the saved run to a mentor - the Runs tab has the data.</p></div>` : ""}
    </div>`;
    $("#tr-back", root).onclick = paintList;
    // Where to look, on FIRST's drawing: only for the check being answered, or one that failed.
    $$("[data-diagram]", root).forEach(el => FrcMap.render(el, c.checks[+el.dataset.diagram].diagram));
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
    } else if (a.type === "netcheck") {
      // Its findings answer this symptom's checks: open it again once the check is done.
      const id = current && current.id;
      App.checkNetworks().then(() => { if (id) open(id); });
    } else if (a.type === "config") {
      App.previewAndSave({ kind: "edit", file: a.file, path: a.path, value: a.value }, "Change the robot's configuration");
    }
  }

  App.on("tab", t => { if (t === "trouble" && !current) list(); });
  list();
  return { open };
})();
