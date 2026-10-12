// Wiring tab: the robot's CAN chain and power feeds as a schematic, live health on it, and where to
// look when something is wrong. The map lives in the robot project (src/main/deploy/wiring.json).
"use strict";

(() => {
  const root = $("#tab-wiring");
  const SVGNS = "http://www.w3.org/2000/svg";
  let data = null, editing = null, demo = "", timer = null, focus = null;

  root.innerHTML = `
    <div class="stack">
      <div class="panel">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2>Wiring</h2>
          <div class="row" style="flex-wrap:wrap">
            <label class="small">See a practice fault
              <select id="w-demo"><option value="">Live robot</option></select></label>
            <button class="btn" id="w-edit">Edit the map</button>
          </div>
        </div>
        <p class="hint" id="w-meta"></p>
        <div id="w-banner"></div>
        <div class="schematic-wrap"><svg id="w-svg" class="schematic" role="img" aria-label="CAN chain and power schematic"></svg></div>
        <div class="row small muted" style="flex-wrap:wrap;gap:14px">
          <span><span class="swatch can-h"></span><span class="term" data-learn="can_bus">CAN-H / CAN-L</span></span>
          <span><span class="swatch ok"></span>heard on the bus</span>
          <span><span class="swatch warn"></span>has had trouble</span>
          <span><span class="swatch bad"></span>missing now</span>
          <span><span class="term" data-learn="can_termination">Ω = terminator</span></span>
          <span>Hover a box for its details; click to mark it.</span>
        </div>
      </div>
      <div class="grid2">
        <div class="panel">
          <h3>Where to look</h3>
          <div id="w-findings"></div>
        </div>
        <div class="stack">
          <div class="panel">
            <h3><span class="term" data-learn="can_termination">Termination check</span></h3>
            <p class="small">Robot <b>off</b>. Multimeter on ohms, probes on CAN-H (yellow) and CAN-L (green) at any free CAN plug.</p>
            <div class="row"><input type="number" id="w-ohms" placeholder="ohms" step="0.1" aria-label="Measured ohms"><button class="btn" id="w-ohms-go">Check</button></div>
            <div id="w-ohms-out" class="small"></div>
          </div>
          <div class="panel" id="w-editor" hidden></div>
        </div>
      </div>
      <div class="panel">
        <h3><span class="term" data-learn="power_path">PDH ports</span></h3>
        <div id="w-pdh" class="pdh-grid"></div>
      </div>
    </div>`;

  // ---------------------------------------------------------------- data
  async function refresh() {
    if (editing) return;
    const d = await App.api("/api/wiring" + (demo ? "?demo=" + encodeURIComponent(demo) : ""));
    if (d.ok === false) { $("#w-meta", root).textContent = d.error; return; }
    data = d;
    paint();
  }

  function rowsByName() {
    const out = {};
    for (const r of ((data && data.snapshot) || {}).motors || []) out[r.name] = r;
    return out;
  }

  function highlighted() {
    const devs = new Map(), segs = [];
    for (const f of (data && data.findings) || []) {
      const w = f.where || {};
      for (const n of w.devices || []) devs.set(n, f.level === "error" ? "bad" : "warn");
      if (w.segment) segs.push({ a: w.segment[0], b: w.segment[1], f });
    }
    return { devs, segs };
  }

  // ---------------------------------------------------------------- schematic
  function el(tag, attrs, parent, text) {
    const e = document.createElementNS(SVGNS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }

  function paint() {
    const m = data.map, bus = m.buses[0], chain = bus.chain;
    const rows = rowsByName(), hl = highlighted(), live = !!(data.snapshot && data.snapshot.motors);
    const [len, measured, segs] = data.lengths[0];
    $("#w-meta", root).innerHTML = `${esc(data.path)} · ${chain.length - 2} devices on ${esc(bus.name)} ·
      bus about ${fmt(len, 1)} m (${measured} of ${segs} segments measured; CAN allows 40 m) ·
      ${bus.orderConfirmed ? `<span class="chip good">order checked on the robot</span>` : `<span class="chip warn">order not checked yet</span>`}
      ${data.demo ? `<span class="chip info">practice: ${esc(data.demos[data.demo])}</span>` : live ? "" : `<span class="chip">no live data</span>`}`;

    const svg = $("#w-svg", root);
    svg.innerHTML = "";
    const W = Math.max(640, svg.clientWidth || 900), bw = 150, bh = 62, gx = 36, gy = 54, pad = 26;
    const perRow = Math.max(2, Math.floor((W - 2 * pad + gx) / (bw + gx)));
    const pos = chain.map((n, i) => {
      const r = Math.floor(i / perRow), c = i % perRow;
      const col = r % 2 === 0 ? c : perRow - 1 - c;  // snake, so the cable stays one line
      return { x: pad + col * (bw + gx), y: pad + r * (bh + gy) };
    });
    const H = pad * 2 + Math.ceil(chain.length / perRow) * (bh + gy) - gy;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.style.height = H + "px";
    const centre = i => ({ x: pos[i].x + bw / 2, y: pos[i].y + bh / 2 });
    const idx = Object.fromEntries(chain.map((n, i) => [n, i]));

    // the cable: CAN-H and CAN-L side by side
    for (let i = 0; i + 1 < chain.length; i++) {
      const a = centre(i), b = centre(i + 1);
      for (const [off, cls] of [[-3, "can-h"], [3, "can-l"]]) {
        const vertical = Math.abs(a.y - b.y) > 1;
        el("line", { x1: a.x + (vertical ? off : 0), y1: a.y + (vertical ? 0 : off), x2: b.x + (vertical ? off : 0),
          y2: b.y + (vertical ? 0 : off), class: "wire " + cls }, svg);
      }
    }
    for (const s of hl.segs) {
      if (!(s.a in idx) || !(s.b in idx)) continue;
      const a = centre(idx[s.a]), b = centre(idx[s.b]);
      const g = el("g", { class: "suspect" }, svg);
      el("title", {}, g, s.f.title + ". " + s.f.why);
      el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "suspect-line" }, g);
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      el("circle", { cx: mx, cy: my, r: 11, class: "suspect-dot" }, g);
      el("text", { x: mx, y: my + 4, "text-anchor": "middle", class: "suspect-mark" }, g, "!");
    }

    chain.forEach((name, i) => {
      const p = pos[i], dev = data.devices[name] || {}, r = rows[name];
      let state = "unknown";
      if (r) state = r.present === 0 ? "bad" : (r.dropouts || r.resets || r.brownouts) ? "warn" : "ok";
      if (hl.devs.has(name)) state = hl.devs.get(name);
      const g = el("g", { class: "node " + state + (focus === name ? " focus" : ""), tabindex: 0 }, svg);
      const port = m.pdhPorts[name];
      const tip = [name, dev.model, dev.can_id != null ? "CAN ID " + dev.can_id : null,
        port != null ? "PDH port " + port : (dev.kind === "controller" ? "PDH port not set" : null), dev.source,
        r ? `heard on the bus: ${r.present ? "yes" : "NO"}; dropped out ${r.dropouts || 0}x; rebooted ${r.resets || 0}x; low supply ${r.brownouts || 0}x` : null,
        r && Number.isFinite(r.bus_volts) ? `supply at the controller ${fmt(r.bus_volts, 2)} V` : null].filter(Boolean).join("\n");
      el("title", {}, g, tip);
      el("rect", { x: p.x, y: p.y, width: bw, height: bh, rx: 8, class: "box" }, g);
      el("text", { x: p.x + 10, y: p.y + 22, class: "nm" }, g, name.length > 19 ? name.slice(0, 18) + "…" : name);
      const sub = name === "roboRIO" ? "120 Ω built in" : name === "PDH"
        ? `CAN ${dev.can_id} · term ${m.pdh.terminationOn ? "ON" : "OFF"}`
        : `CAN ${dev.can_id ?? "?"} · PDH ${port ?? "?"}`;
      el("text", { x: p.x + 10, y: p.y + 42, class: "sub" }, g, sub);
      if (name === "roboRIO" || (name === "PDH" && m.pdh.terminationOn)) {
        el("text", { x: p.x + bw - 22, y: p.y + 22, class: "ohm" }, g, "Ω");
      }
      g.onclick = () => { focus = focus === name ? null : name; paint(); };
    });
    if (!m.pdh.terminationOn) {
      const last = pos[chain.length - 1];
      el("text", { x: last.x, y: last.y + bh + 18, class: "warn-text" }, svg, "No terminator at this end: switch the PDH's termination ON");
    }
    paintPdh(rows);
    paintFindings();
  }

  function paintPdh(rows) {
    const m = data.map, cur = (((data.snapshot || {}).pdh) || {}).currents || [];
    const byPort = {};
    for (const [n, p] of Object.entries(m.pdhPorts)) (byPort[p] = byPort[p] || []).push(n);
    const cells = [];
    for (let p = 0; p < 24; p++) {
      const amps = cur[p], names = byPort[p] || [];
      const pct = Number.isFinite(amps) ? Math.min(100, amps / 40 * 100) : 0;
      cells.push(`<div class="pdh-port ${names.length ? "" : "empty"}" title="${esc(names.join(", ") || "nothing mapped")}">
        <span class="mono small">${p}${p >= 20 ? (p === 23 ? " sw" : " lo") : ""}</span>
        <span class="small">${esc(names.join(", ") || "–")}</span>
        <div class="pdh-bar"><div style="width:${pct}%"></div></div>
        <span class="mono small">${Number.isFinite(amps) ? fmt(amps, 1) + " A" : ""}</span></div>`);
    }
    $("#w-pdh", root).innerHTML = cells.join("") +
      `<p class="hint" style="grid-column:1/-1">Ports 0-19 take 40 A breakers, 20-22 are low-current, 23 is switchable. Live currents come from AdvantageKit's PDH log.</p>`;
  }

  function paintFindings() {
    const F = data.findings || [];
    $("#w-banner", root).innerHTML = F.some(f => f.where && f.where.bus)
      ? `<div class="callout bad">${F.filter(f => f.where && f.where.bus).map(f => esc(f.title)).join(" · ")}</div>` : "";
    $("#w-findings", root).innerHTML = F.length ? F.map(f => `<div class="finding">
        <div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
        <div class="why">${Learn.link(f.why, 3)}</div>
        ${f.fix ? `<div class="small"><b>Do:</b> ${Learn.link(f.fix, 2)}</div>` : ""}</div>`).join("")
      : `<p class="hint">${data.snapshot && data.snapshot.motors ? "Nothing wrong with the CAN bus or the power feeds right now." : "Connect to a robot, or pick a practice fault above to see how a problem shows up."}</p>`;
  }

  // ---------------------------------------------------------------- the map editor
  function openEditor() {
    editing = JSON.parse(JSON.stringify(data.map));
    paintEditor();
  }

  function paintEditor() {
    const box = $("#w-editor", root), bus = editing.buses[0], chain = bus.chain;
    box.hidden = false;
    box.innerHTML = `<h3>Edit the map</h3>
      <p class="small">Follow the CAN cable on the robot from the roboRIO and put the devices in the order you meet them. Then type the PDH port feeding each controller (it is printed next to each breaker).</p>
      <label class="row small"><input type="checkbox" id="we-ok" ${bus.orderConfirmed ? "checked" : ""}> I checked this order on the robot</label>
      <label class="row small"><input type="checkbox" id="we-term" ${editing.pdh.terminationOn ? "checked" : ""}> The PDH's termination switch is ON (it should be, at the end of the chain)</label>
      <ol class="chain-edit">${chain.map((n, i) => `<li>
        <span class="mono small">${i}</span><span>${esc(n)}</span>
        ${n === "roboRIO" || n === "PDH" ? "<span></span><span></span>" : `<input type="number" min="0" max="23" placeholder="PDH" data-port="${esc(n)}" value="${editing.pdhPorts[n] ?? ""}" aria-label="PDH port for ${esc(n)}">
        <span><button class="btn small" data-up="${i}" ${i <= 1 ? "disabled" : ""} aria-label="Move up">↑</button><button class="btn small" data-down="${i}" ${i >= chain.length - 2 ? "disabled" : ""} aria-label="Move down">↓</button></span>`}
      </li>`).join("")}</ol>
      <div class="row"><button class="btn primary" id="we-save">Save to the robot project…</button><button class="btn" id="we-cancel">Cancel</button></div>`;
    $$("[data-up]", box).forEach(b => b.onclick = () => { const i = +b.dataset.up; [chain[i - 1], chain[i]] = [chain[i], chain[i - 1]]; paintEditor(); });
    $$("[data-down]", box).forEach(b => b.onclick = () => { const i = +b.dataset.down; [chain[i + 1], chain[i]] = [chain[i], chain[i + 1]]; paintEditor(); });
    $$("[data-port]", box).forEach(inp => inp.onchange = () => {
      if (inp.value === "") delete editing.pdhPorts[inp.dataset.port]; else editing.pdhPorts[inp.dataset.port] = +inp.value;
    });
    $("#we-ok", box).onchange = e => { bus.orderConfirmed = e.target.checked; };
    $("#we-term", box).onchange = e => { editing.pdh.terminationOn = e.target.checked; };
    $("#we-cancel", box).onclick = () => { editing = null; box.hidden = true; refresh(); };
    $("#we-save", box).onclick = async () => {
      if (await App.previewAndSave({ kind: "wiring", map: editing }, "Save the wiring map")) {
        editing = null; box.hidden = true; refresh();
      }
    };
  }

  // ---------------------------------------------------------------- controls
  $("#w-edit", root).onclick = () => { if (data) openEditor(); };
  $("#w-demo", root).onchange = e => { demo = e.target.value; refresh(); };
  $("#w-ohms-go", root).onclick = async () => {
    const v = await App.api("/api/wiring/termination", { ohms: $("#w-ohms", root).value });
    $("#w-ohms-out", root).innerHTML = `<div class="finding"><div class="head"><span class="level ${v.level}">${v.level}</span><span class="title">${esc(v.title)}</span></div><div class="why">${Learn.link(v.why, 3)}</div></div>`;
  };

  App.on("tab", async t => {
    clearInterval(timer);
    if (t !== "wiring") return;
    await refresh();
    if (data && data.demos && $("#w-demo", root).options.length === 1) {
      $("#w-demo", root).innerHTML = `<option value="">Live robot</option>` +
        Object.entries(data.demos).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
    }
    timer = setInterval(refresh, 1000);
  });
  window.addEventListener("resize", () => { if (data && root.classList.contains("on")) paint(); });
})();
