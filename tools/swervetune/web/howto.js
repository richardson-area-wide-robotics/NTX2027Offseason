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
  const CHIP = { done: "good", attention: "bad", todo: "", later: "info", optional: "", skip: "" };
  const plans = {};   // tab -> the last plan shown
  const seqs = {};    // tab -> the newest paint asked for: a slow answer never paints over it

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
  const slot = tab => `<div class="panel plan" data-plan="${tab}" aria-live="polite"><p class="hint">Working out where to start…</p></div>`;
  const nextLine = job => `<div class="howto-next" data-job="${job}" hidden></div>`;

  function goButton(j, label, primary) {
    return `<button class="btn ${primary ? "primary" : "small"}" data-go-job="${esc(j.id)}" data-tip="howto.go" ${primary ? "" : "data-quiet"}>${esc(label)}</button>`;
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
    const parts = { calibrate: ["camera", "field", "gyro", "wheels"], motors: ["motor", "module"], wiring: ["motor"] }[tab];
    box.innerHTML = `<div class="row" style="justify-content:space-between;flex-wrap:wrap;gap:8px">
        <h2 data-tip="howto.plan">${head} <span class="muted small">${p.done} of ${p.of} done</span></h2>
        <label class="row small howto-switch" data-tip="howto.switch"><input type="checkbox" data-howto-switch ${shown() ? "checked" : ""}> How-to instructions</label>
      </div>
      <p class="small">${esc(p.what)}</p>
      ${(p.bring || []).length ? `<p class="small muted"><b>Bring:</b> ${p.bring.map(esc).join(" · ")}</p>` : ""}
      <ol class="plan-jobs">${p.jobs.map(j => `<li class="${p.next && j.id === p.next.id ? "now" : ""} ${j.status}">
          <span class="chip ${CHIP[j.status]}">${WORD[j.status]}</span>
          <span class="plan-t"><b>${esc(j.title)}</b> <span class="small muted">${esc(j.detail || "")}</span>
          ${j.unblock && j.status === "later" ? `<button class="btn small" data-go-unblock="${esc(j.id)}" data-tip="howto.unblock" data-quiet>${esc(j.unblock.label)}</button>` : ""}</span>
          ${j.go && !(p.next && j.id === p.next.id) && j.status !== "skip" ? goButton(j, "Go", false) : ""}</li>`).join("")}</ol>
      <div class="row" style="flex-wrap:wrap">
        ${p.next ? goButton(p.next, `${p.done ? "Next" : "Start here"}: ${p.next.title} →`, true)
          : p.after ? `<button class="btn primary" data-go-after data-tip="howto.after">${esc(p.after.label)} →</button>` : ""}
        ${parts ? `<button class="btn" data-parts="${parts[0]}" data-tip="howto.parts">Only one part changed?</button>` : ""}
      </div>`;
    $("[data-howto-switch]", box).onchange = e => set(e.target.checked);
    $$("[data-go-job]", box).forEach(b => b.onclick = () => go((p.jobs.find(j => j.id === b.dataset.goJob) || {}).go));
    $$("[data-go-unblock]", box).forEach(b => b.onclick = () => go((p.jobs.find(j => j.id === b.dataset.goUnblock) || {}).unblock));
    const after = $("[data-go-after]", box);
    if (after) after.onclick = () => go(p.after);
    const pb = $("[data-parts]", box);
    if (pb) pb.onclick = () => Parts.open(pb.dataset.parts);
    paintNextLines(tab, p);
    // A job that just checked out: say what comes next, once.
    if (before) {
      const was = Object.fromEntries(before.jobs.map(j => [j.id, j.status]));
      const now = p.jobs.find(j => j.status === "done" && was[j.id] && was[j.id] !== "done");
      if (now) App.toast(`${now.title}: done.${p.next ? ` Next: ${p.next.title}.` : p.after ? ` ${p.after.label}.` : ""}`, 6000);
    }
  }

  // Under each panel: once its job is done, a button to the next one.
  function paintNextLines(tab, p) {
    const root = $(`#tab-${tab}`);
    $$(".howto-next", root).forEach(el => {
      const j = p.jobs.find(x => x.id === el.dataset.job);
      const show = j && j.status === "done";
      el.hidden = !show;
      if (!show) return;
      el.innerHTML = `<span class="chip good">✓ done</span> ${esc(j.detail || "")}
        ${p.next ? goButton(p.next, `Next: ${p.next.title} →`, true) : p.after ? `<button class="btn primary" data-go-after data-tip="howto.after">${esc(p.after.label)} →</button>` : ""}`;
      $$("[data-go-job]", el).forEach(b => b.onclick = () => go((p.jobs.find(x => x.id === b.dataset.goJob) || {}).go));
      const a = $("[data-go-after]", el);
      if (a) a.onclick = () => go(p.after);
    });
  }

  /** Takes the person to a job: a panel in a tool, a Guide step, a tuner, the battery picker, a part. */
  function go(g) {
    if (!g) return;
    if (g.part) { Parts.open(g.part, g.which); return; }
    if (g.battery) { Battery.open(); return; }
    if (g.connect) { const c = $("#connect"); if (c) c.focus(); App.toast("Connect at the top of the page."); return; }
    if (g.tune) { Tune.open(g.tune, { target: "robot", module: g.module }); return; }
    if ("guide" in g) { if (g.guide) Guide.go(g.guide); else App.show("guide"); return; }
    if (g.tab) {
      App.show(g.tab);
      if (g.camera) { const c = $("#cc-cam"); if (c) c.value = g.camera; }
      if (g.panel) {
        const el = $("#" + g.panel);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
          el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
          const f = el.querySelector("input, select, button:not([disabled])");
          if (f) setTimeout(() => f.focus({ preventScroll: true }), 400);
        }
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
