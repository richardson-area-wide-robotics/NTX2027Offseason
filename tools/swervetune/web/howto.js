// How-to instructions, "where to start" and "what to do next", for every calibration and
// configuration tool. Each tool's panels keep their instructions in a fold-away "How to" block;
// one switch shows or hides them all (remembered on this laptop). The card at the top of each tool
// lists its jobs in order with what the robot's files, the saved runs and the robot itself say is
// done (server: setup.py), and points at the next one; when a job checks out, the panel says what
// comes next, right where the person is looking.
"use strict";

const HowTo = (() => {
  const KEY = "swervetune.howto";
  const WORD = { done: "done", attention: "needs a fix", todo: "to do", later: "later", optional: "optional", skip: "not needed" };
  const CHIP = { done: "good", attention: "bad", todo: "todo", later: "info", optional: "opt", skip: "opt" };
  const NAME = { config: "Config", motors: "Motors", wiring: "Wiring", calibrate: "Calibrate", controllers: "Controllers" };
  const plans = {};   // tab -> the last plan shown
  const seqs = {};    // tab -> the newest paint asked for: a slow answer never paints over it
  const showAll = {}; // tab -> on a phone, every job listed rather than only the next

  function shown() {
    try { return localStorage.getItem(KEY) !== "off"; } catch (e) { return true; }
  }

  function set(on) {
    try { localStorage.setItem(KEY, on ? "on" : "off"); } catch (e) { /* storage blocked: this page only */ }
    apply(document);
    $$("[data-howto-switch]").forEach(c => { c.checked = on; });
  }

  /** A panel's instructions, folded away when the switch is off (each one can still be opened). */
  function block(html, label = "How to do it") {
    return `<details class="howto" ${shown() ? "open" : ""}><summary data-tip="howto.block">${esc(label)}</summary><div class="howto-body">${html}</div></details>`;
  }

  /** Steps, a good result and what you need, in the house layout. */
  function steps({ need, steps: list, good, note } = {}) {
    return block(`${need ? `<p class="small"><b>You need:</b> ${need}</p>` : ""}
      ${list ? `<ol class="small">${list.map(s => `<li>${s}</li>`).join("")}</ol>` : ""}
      ${note ? `<p class="small">${note}</p>` : ""}
      ${good ? `<p class="small good-result"><b>A good result:</b> ${good}</p>` : ""}`);
  }

  function apply(root) {
    const on = shown();
    $$("details.howto", root).forEach(d => { d.open = on; });
  }

  /** Where a tool's card goes, and the line under a panel that says what comes next. */
  const slot = tab => `<div class="panel plan" data-plan="${tab}"><p class="hint">Working out where to start…</p></div>`;
  const nextLine = job => `<div class="howto-next" data-job="${job}" hidden></div>`;

  function goButton(j, label, primary) {
    return `<button class="btn ${primary ? "primary" : "small"}" data-go-job="${esc(j.id)}" data-tip="howto.go" ${primary ? "" : `data-quiet aria-label="Go to ${esc(j.title)}"`}>${esc(label)}</button>`;
  }

  async function paint(tab) {
    if (!$(`[data-plan="${tab}"]`)) return;
    const my = seqs[tab] = (seqs[tab] || 0) + 1;
    const p = await App.api("/api/setup?tab=" + tab);
    // The tool may have repainted itself (Config does, on every lint) while this was on its way.
    const box = $(`[data-plan="${tab}"]`);
    if (!box || my !== seqs[tab]) return;
    if (p.ok === false) { box.innerHTML = `<p class="hint">${esc(p.error)}</p>`; return; }
    const before = plans[tab];
    plans[tab] = p;
    const head = !p.done ? "Where to start" : p.next ? "What to do next" : "Done here";
    const parts = { calibrate: "camera", motors: "motor", wiring: "motor" }[tab];
    const ord = p.order || {};
    // The order between tools, and an earlier one still to finish.
    const order = ord.chain ? `<p class="small muted">Tool ${ord.index + 1} of ${ord.chain.length}: ${ord.chain.map(t => t === tab ? `<b>${NAME[t]}</b>` : NAME[t]).join(" → ")}</p>` : "";
    const earlier = ord.earlier ? `<div class="callout warn small"><b>${esc(NAME[ord.earlier.tab])}</b> comes first and has ${ord.earlier.count} job${ord.earlier.count === 1 ? "" : "s"} to do.
      <button class="btn small" data-go-tab="${esc(ord.earlier.tab)}" data-tip="howto.earlier">Start there →</button></div>` : "";
    const primary = p.next ? goButton(p.next, `${p.done ? "Next" : "Start here"}: ${p.next.title} →`, true)
      : p.after ? `<button class="btn primary" data-go-after data-tip="howto.after">${esc(p.after.label)} →</button>` : "";
    const jobs = p.jobs.map(j => {
      const now = p.next && j.id === p.next.id;
      // A blocked job's only button is to what it waits for; its own panel can't be used yet.
      const btn = j.unblock && j.status === "later"
        ? `<button class="btn small" data-go-unblock="${esc(j.id)}" data-tip="howto.unblock" data-quiet>First: ${esc(j.unblock.label)} →</button>`
        : j.go && !now && j.status !== "skip" ? goButton(j, "Go", false) : "";
      return `<li class="${now ? "now" : ""} ${j.status}"><span class="chip ${CHIP[j.status]}">${WORD[j.status]}</span>
        <span class="plan-t"><b>${esc(j.title)}</b> <span class="small muted">${esc(j.detail || "")}</span></span>${btn}</li>`;
    }).join("");
    box.innerHTML = `<div class="row plan-head" style="justify-content:space-between;flex-wrap:wrap;gap:8px">
        <h2 data-tip="howto.plan">${head} <span class="muted small">${p.done} of ${p.of} done</span></h2>
        <label class="row small howto-switch" data-tip="howto.switch"><input type="checkbox" data-howto-switch ${shown() ? "checked" : ""}> Show how-to instructions</label>
      </div>
      <p class="sr-status" aria-live="polite">${esc(head)}: ${p.next ? esc(p.next.title) : esc((p.after || {}).label || "")}</p>
      <div class="row plan-primary" style="flex-wrap:wrap">${primary}
        ${parts ? `<button class="btn" data-parts="${parts}" data-tip="howto.parts">Redo one part</button>` : ""}</div>
      ${order}${earlier}
      <p class="small">${esc(p.what)}</p>
      ${(p.bring || []).length ? `<p class="small muted"><b>Bring:</b> ${p.bring.map(esc).join(" · ")}</p>` : ""}
      <ol class="plan-jobs ${showAll[tab] ? "all" : ""}">${jobs}</ol>
      <button class="btn small plan-all" data-show-all data-tip="howto.all">${showAll[tab] ? "Show only the next job" : `Show all ${p.jobs.length} jobs`}</button>`;
    $("[data-howto-switch]", box).onchange = e => set(e.target.checked);
    $$("[data-go-job]", box).forEach(b => b.onclick = () => go((p.jobs.find(j => j.id === b.dataset.goJob) || {}).go));
    $$("[data-go-unblock]", box).forEach(b => b.onclick = () => go((p.jobs.find(j => j.id === b.dataset.goUnblock) || {}).unblock));
    const after = $("[data-go-after]", box);
    if (after) after.onclick = () => go(p.after);
    const gt = $("[data-go-tab]", box);
    if (gt) gt.onclick = () => go({ tab: gt.dataset.goTab });
    const pb = $("[data-parts]", box);
    if (pb) pb.onclick = () => Parts.open(pb.dataset.parts);
    $("[data-show-all]", box).onclick = () => { showAll[tab] = !showAll[tab]; paint(tab); };
    const lines = paintNextLines(tab, p);
    // A job that just checked out: say what comes next, once, unless the panel already says it on screen.
    if (before) {
      const was = Object.fromEntries(before.jobs.map(j => [j.id, j.status]));
      const now = p.jobs.find(j => j.status === "done" && was[j.id] && was[j.id] !== "done");
      if (now && !lines.has(now.id)) App.toast(`${now.title}: done.${p.next ? ` Next: ${p.next.title}.` : p.after ? ` ${p.after.label}.` : ""}`, 6000);
    }
  }

  // Under each panel: once its job is done, a button to the next one. Returns the jobs it showed.
  function paintNextLines(tab, p) {
    const root = $(`#tab-${tab}`), showing = new Set();
    $$(".howto-next", root).forEach(el => {
      const j = p.jobs.find(x => x.id === el.dataset.job);
      const show = j && j.status === "done";
      el.hidden = !show;
      if (!show) return;
      const r = el.getBoundingClientRect();
      if (r.bottom > 0 && r.top < innerHeight) showing.add(j.id);
      el.innerHTML = `<span class="chip good">✓ done</span> ${esc(j.detail || "")}
        ${p.next ? goButton(p.next, `Next: ${p.next.title} →`, true) : p.after ? `<button class="btn primary" data-go-after data-tip="howto.after">${esc(p.after.label)} →</button>` : ""}`;
      $$("[data-go-job]", el).forEach(b => b.onclick = () => go((p.jobs.find(x => x.id === b.dataset.goJob) || {}).go));
      const a = $("[data-go-after]", el);
      if (a) a.onclick = () => go(p.after);
    });
    return showing;
  }

  /** Takes the person to a job: a panel in a tool, a Guide step, a tuner, the battery picker, a part. */
  function go(g) {
    if (!g) return;
    if (g.part) { Parts.open(g.part, g.which); return; }
    if (g.battery) { Battery.open(); return; }
    if (g.connect) { const c = $("#connect"); if (c) c.focus(); App.toast("Connect at the top of the page."); return; }
    if (g.tune) { Tune.open(g.tune, { target: "robot", module: g.module }); return; }
    if ("guide" in g) {
      // Redoing one part has the Guide's tab: leave it, or the Guide step never shows.
      Parts.off();
      if (g.guide) Guide.go(g.guide); else { App.show("guide"); Guide.refresh(); }
      return;
    }
    if (g.tab) {
      App.show(g.tab);
      if (g.camera) { const c = $("#cc-cam"); if (c) c.value = g.camera; }
      const el = g.panel ? $("#" + g.panel) : $(`[data-plan="${g.tab}"]`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
        // The panel's heading, not its first button: Enter twice must never start a run.
        const h = el.querySelector("h2, h3");
        if (h) { h.setAttribute("tabindex", "-1"); setTimeout(() => h.focus({ preventScroll: true }), 400); }
      }
    }
  }

  /** A tool's result for its checklist (the server stamps the time), then the card again. */
  async function mark(tab, key, ok, detail) {
    await App.api("/api/mark", { key, result: ok ? "pass" : "fail", detail: detail || "" });
    paint(tab);
  }

  const TABS = ["calibrate", "config", "motors", "wiring", "controllers"];
  App.on("tab", t => { if (TABS.includes(t)) paint(t); });
  App.on("saved", () => TABS.forEach(t => { if ($(`#tab-${t}`).classList.contains("on")) paint(t); }));
  App.on("run", () => TABS.forEach(t => { if ($(`#tab-${t}`).classList.contains("on")) paint(t); }));

  return { block, steps, slot, nextLine, paint, mark, go, shown, set, apply };
})();
