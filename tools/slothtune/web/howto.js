// How-to instructions, "where to start" and "what to do next", for every calibration and
// configuration tool. Each tool is a rail, one section, and that section's how-to: the rail lists
// the tool's jobs in order with what the robot's files, the saved runs and the robot itself say is
// done (server: setup.py) and marks the next one; beside it only the section being worked on shows,
// so every job fits one laptop screen; beside that, its how-to instructions, in their own column. One switch shows or hides
// the instructions everywhere (remembered on this laptop); when a job checks out, its section says
// what comes next, right where the person is looking.
"use strict";

const HowTo = (() => {
  const KEY = "slothtune.howto";
  const WORD = { done: "done", attention: "needs a fix", todo: "to do", later: "later", optional: "optional", skip: "not needed" };
  const MARK = { done: "✓", attention: "!" };
  const NAME = { bringup: "Bring-up", config: "Config", motors: "Motors", wiring: "Wiring", calibrate: "Calibrate", controllers: "Joysticks" };
  const plans = {};   // tab -> the last plan shown
  const seqs = {};    // tab -> the newest paint asked for: a slow answer never paints over it

  function shown() {
    try { return localStorage.getItem(KEY) !== "off"; } catch (e) { return true; }
  }

  function set(on) {
    try { localStorage.setItem(KEY, on ? "on" : "off"); } catch (e) { /* storage blocked: this page only */ }
    apply(document);
    $$("[data-howto-switch]").forEach(c => { c.checked = on; });
    $$(".job-side").forEach(s => { s.hidden = !on || !s._src; });
  }

  /** A panel's instructions, folded away when the switch is off (each one can still be opened). In a
   *  tool with a rail they show in the column beside the section they are for; ``inline`` keeps
   *  them where they are (a panel's own note, in a side column already). */
  function block(html, label = "How to do it", { inline = false } = {}) {
    return `<details class="howto${inline ? " inline" : ""}" data-label="${esc(label)}" ${shown() ? "open" : ""}><summary data-tip="howto.block">${esc(label)}</summary><div class="howto-body">${html}</div></details>`;
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

  /** The rail of a tool: wrap the tool as `<div class="jobs" data-jobs="tab">${slot(tab)}<div class="job-area">…sections…</div></div>`.
   *  Each top-level child of .job-area is one section. */
  const slot = tab => `<nav class="panel rail-panel" data-plan="${tab}" aria-label="${esc(NAME[tab] || tab)} jobs"><p class="hint">Working out where to start…</p></nav>`;
  const nextLine = job => `<div class="howto-next" data-job="${job}" hidden></div>`;

  // ---------------------------------------------------------------- sections
  const wrapOf = tab => $(`[data-jobs="${tab}"]`);
  const sectionsOf = wrap => wrap ? [...$(".job-area", wrap).children] : [];
  function keyOf(sec, i) {
    if (!sec.id && !sec.dataset.section) sec.dataset.section = "s" + i;
    return sec.id || sec.dataset.section;
  }
  /** The section that holds an element (a job's go.panel), in its tool. */
  const sectionOf = el => el && el.closest(".job-area > *");
  /** A section's name: its first heading, without Explain's printed line. */
  function labelOf(sec) {
    const h = sec.querySelector("h2, h3");
    if (!h) return "";
    return [...h.childNodes].filter(n => !(n.classList && n.classList.contains("tipline"))).map(n => n.textContent).join("").trim();
  }
  function remembered(tab) {
    try { return localStorage.getItem("slothtune.section." + tab) || ""; } catch (e) { return ""; }
  }

  /** Shows one section of a tool and marks it in the rail; the rest wait their turn. */
  function select(tab, sec, focusIt) {
    const wrap = wrapOf(tab);
    const secs = sectionsOf(wrap);
    if (!secs.length) return;
    secs.forEach(keyOf);
    if (typeof sec === "string") sec = secs.find(s => keyOf(s) === sec);
    if (!sec || !secs.includes(sec) || sec.hidden) sec = secs[0];
    secs.forEach(s => s.classList.toggle("job-off", s !== sec));
    try { localStorage.setItem("slothtune.section." + tab, keyOf(sec)); } catch (e) { /* storage blocked */ }
    let first = true;
    $$("[data-rail-job], [data-rail-sec]", wrap).forEach(b => {
      const on = b._sec === sec;
      b.classList.toggle("on", on);
      if (on && first) { b.setAttribute("aria-current", "step"); first = false; } else b.removeAttribute("aria-current");
    });
    copyHowTo(wrap, sec);
    if (focusIt) {
      // The section's heading, not its first button: Enter twice must never start a run.
      const h = sec.querySelector("h2, h3");
      if (h) { h.setAttribute("tabindex", "-1"); h.focus({ preventScroll: true }); }
    }
  }

  // The open section's instructions, in their own column beside it (an <aside> after the section;
  // the section's own copy is hidden, so its width goes to its controls and results).
  function copyHowTo(wrap, sec) {
    if (!wrap) return;
    let side = $(":scope > .job-side", wrap);
    if (!side) {
      side = document.createElement("aside");
      side.className = "panel job-side";
      side.setAttribute("aria-label", "How to do it");
      wrap.append(side);
    }
    const html = sec ? [...sec.querySelectorAll("details.howto:not(.inline)")].map(d =>
      `<section><h3>${esc(d.dataset.label || "How to do it")}</h3><div class="howto-body">${$(".howto-body", d).innerHTML}</div></section>`).join("") : "";
    if (side._src !== html) {
      side._src = html;
      side.innerHTML = html;
    }
    side.hidden = !html || !shown();
  }

  function railItem(attrs, cls, mark, title, sub, extra = "") {
    return `<li><button class="rail-item ${cls}" ${attrs} data-tip="howto.go" data-quiet>
      <span class="n" aria-hidden="true">${mark}</span><span class="t">${title}${sub ? `<span class="d">${sub}</span>` : ""}</span></button>${extra}</li>`;
  }

  async function paint(tab) {
    if (!$(`[data-plan="${tab}"]`)) return;
    const wrap0 = wrapOf(tab);
    if (wrap0 && !$(".job-off", wrap0)) select(tab, remembered(tab));
    const my = seqs[tab] = (seqs[tab] || 0) + 1;
    const p = await App.api("/api/setup?tab=" + tab);
    // The tool may have repainted itself (Config does, on every lint) while this was on its way.
    const box = $(`[data-plan="${tab}"]`);
    if (!box || my !== seqs[tab]) return;
    if (p.ok === false) { box.innerHTML = `<p class="hint">${esc(p.error)}</p>`; return; }
    const before = plans[tab];
    plans[tab] = p;
    const wrap = wrapOf(tab), secs = sectionsOf(wrap);
    secs.forEach(keyOf);
    const inTool = j => j && j.go && j.go.tab === tab && j.go.panel ? sectionOf(document.getElementById(j.go.panel)) : null;
    const owned = new Set(p.jobs.map(inTool).filter(Boolean));
    // A hidden section (the Wiring map's editor while closed) is no place to go.
    const others = secs.filter(s => !owned.has(s) && !s.hidden && labelOf(s));
    const head = !p.done ? "Where to start" : p.next ? "What to do next" : "Done here";
    const parts = { calibrate: "camera", motors: "motor", wiring: "motor" }[tab];
    const ord = p.order || {};
    // The order between tools, and an earlier one still to finish.
    const order = ord.chain ? `<p class="small muted rail-chain">Tool ${ord.index + 1} of ${ord.chain.length}: ${ord.chain.map(t => t === tab ? `<b>${NAME[t]}</b>` : NAME[t]).join(" → ")}</p>` : "";
    const earlier = ord.earlier ? `<div class="callout warn small"><b>${esc(NAME[ord.earlier.tab])}</b> comes first: ${ord.earlier.count} job${ord.earlier.count === 1 ? "" : "s"} to do.
      <button class="btn small" data-go-tab="${esc(ord.earlier.tab)}" data-tip="howto.earlier">Start there →</button></div>` : "";
    const jobs = p.jobs.map(j => {
      const isNext = p.next && j.id === p.next.id, away = !inTool(j) && j.go;
      // The state in words beside the mark (never the mark's shape alone); "to do" goes without saying.
      const title = `<span class="tt">${esc(j.title)}</span>${j.status !== "todo" ? ` <span class="st">· ${esc(WORD[j.status])}</span>` : ""}${isNext ? ` <span class="chip info next-chip">Next</span>` : ""}${away ? ` <span class="away" aria-hidden="true">↗</span>` : ""}`;
      // A blocked job's way forward is what it waits for; its own section can't be used yet.
      const first = j.unblock && j.status === "later"
        ? `<button class="btn small rail-first" data-go-unblock="${esc(j.id)}" data-tip="howto.unblock" data-quiet>First: ${esc(j.unblock.label)} →</button>` : "";
      return railItem(`data-rail-job="${esc(j.id)}" aria-label="${esc(j.title)}, ${esc(WORD[j.status])}${isNext ? ", next" : ""}${away ? ", opens elsewhere" : ""}"`,
        j.status, MARK[j.status] || "", title, esc(j.detail || ""), first);
    }).join("");
    const also = others.map(s => railItem(`data-rail-sec="${esc(keyOf(s))}"`, "view", "", `<span class="tt">${esc(labelOf(s))}</span>`, "")).join("");
    box.innerHTML = `<div class="rail-head"><h2 data-tip="howto.plan">${esc(NAME[tab] || tab)}</h2><span class="small muted">${p.done} of ${p.of} done</span></div>
      <p class="sr-status" aria-live="polite">${esc(head)}: ${p.next ? esc(p.next.title) : esc((p.after || {}).label || "")}</p>
      ${order}${earlier}
      ${!p.next && p.after ? `<button class="btn primary" data-go-after data-tip="howto.after">${esc(p.after.label)} →</button>` : ""}
      <ol class="rail">${jobs}</ol>
      ${also ? `<h3 class="rail-group">Also here</h3><ol class="rail">${also}</ol>` : ""}
      <details class="rail-about"><summary class="small" data-tip="howto.about">What this tool is for</summary>
        <p class="small">${esc(p.what)}</p>${(p.bring || []).length ? `<p class="small muted"><b>Bring:</b> ${p.bring.map(esc).join(" · ")}</p>` : ""}</details>
      <div class="row rail-foot">${parts ? `<button class="btn small" data-parts="${parts}" data-tip="howto.parts">Redo one part</button>` : ""}
        <label class="row small howto-switch" data-tip="howto.switch"><input type="checkbox" data-howto-switch ${shown() ? "checked" : ""}> How-to</label></div>`;
    // Each rail item knows its section: a job in this tool selects it; a job elsewhere goes there.
    $$("[data-rail-job]", box).forEach(b => {
      const j = p.jobs.find(x => x.id === b.dataset.railJob);
      b._sec = inTool(j);
      b.onclick = () => { if (b._sec) select(tab, b._sec, true); else go(j && j.go); };
    });
    $$("[data-rail-sec]", box).forEach(b => {
      b._sec = secs.find(s => keyOf(s) === b.dataset.railSec);
      b.onclick = () => select(tab, b._sec, true);
    });
    $("[data-howto-switch]", box).onchange = e => set(e.target.checked);
    $$("[data-go-unblock]", box).forEach(b => b.onclick = () => go((p.jobs.find(j => j.id === b.dataset.goUnblock) || {}).unblock));
    const after = $("[data-go-after]", box);
    if (after) after.onclick = () => go(p.after);
    const gt = $("[data-go-tab]", box);
    if (gt) gt.onclick = () => go({ tab: gt.dataset.goTab });
    const pb = $("[data-parts]", box);
    if (pb) pb.onclick = () => Parts.open(pb.dataset.parts);
    // Open the section last worked on; the first time, the next job's.
    const keep = remembered(tab);
    select(tab, secs.find(s => keyOf(s) === keep) || inTool(p.next) || secs[0]);
    const lines = paintNextLines(tab, p);
    // A job that just checked out: say what comes next, once, unless the section already says it on screen.
    if (before) {
      const was = Object.fromEntries(before.jobs.map(j => [j.id, j.status]));
      const now = p.jobs.find(j => j.status === "done" && was[j.id] && was[j.id] !== "done");
      if (now && !lines.has(now.id)) App.toast(`${now.title}: done.${p.next ? ` Next: ${p.next.title}.` : p.after ? ` ${p.after.label}.` : ""}`, 6000);
    }
  }

  function goButton(j, label) {
    return `<button class="btn primary" data-go-job="${esc(j.id)}" data-tip="howto.go">${esc(label)}</button>`;
  }

  // In each section: once its job is done, a button to the next one. Returns the jobs it showed.
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
        ${p.next ? goButton(p.next, `Next: ${p.next.title} →`) : p.after ? `<button class="btn primary" data-go-after data-tip="howto.after">${esc(p.after.label)} →</button>` : ""}`;
      $$("[data-go-job]", el).forEach(b => b.onclick = () => go((p.jobs.find(x => x.id === b.dataset.goJob) || {}).go));
      const a = $("[data-go-after]", el);
      if (a) a.onclick = () => go(p.after);
    });
    return showing;
  }

  /** Takes the person to a job: a section in a tool, a Guide step, a tuner, the battery picker, a part. */
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
    if (g.tab === "systems" && g.system) { App.show("systems"); Systems.focus(g.system, g); return; }
    if (g.tab) {
      App.show(g.tab);
      if (g.camera) { const c = $("#cc-cam"); if (c) c.value = g.camera; }
      const el = g.panel ? $("#" + g.panel) : null;
      const sec = sectionOf(el);
      if (sec) select(g.tab, sec, true);
      const target = el || $(`[data-plan="${g.tab}"]`);
      if (!target) return;
      target.scrollIntoView({ behavior: "smooth", block: "nearest" });
      target.classList.remove("flash"); void target.offsetWidth; target.classList.add("flash");
      if (!sec) {
        const h = target.querySelector("h2, h3");
        if (h) { h.setAttribute("tabindex", "-1"); setTimeout(() => h.focus({ preventScroll: true }), 400); }
      }
    }
  }

  /** A tool's result for its checklist (the server stamps the time), then the rail again. */
  async function mark(tab, key, ok, detail) {
    await App.api("/api/mark", { key, result: ok ? "pass" : "fail", detail: detail || "" });
    paint(tab);
  }

  const TABS = ["bringup", "calibrate", "config", "motors", "wiring", "controllers"];
  App.on("tab", t => { if (TABS.includes(t)) paint(t); });
  App.on("saved", () => TABS.forEach(t => { if ($(`#tab-${t}`).classList.contains("on")) paint(t); }));
  App.on("run", () => TABS.forEach(t => { if ($(`#tab-${t}`).classList.contains("on")) paint(t); }));

  return { block, steps, slot, nextLine, paint, mark, go, select, shown, set, apply };
})();
