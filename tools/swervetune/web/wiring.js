// Wiring tab: the robot's CAN chain and power feeds as a schematic, live health on it, and where to
// look when something is wrong. The map lives in the robot project (src/main/deploy/wiring.json).
"use strict";

const Wiring = (() => {
  const root = $("#tab-wiring");
  const SVGNS = "http://www.w3.org/2000/svg";
  let data = null, editing = null, demo = "", timer = null, focus = null, logAt = null;
  let mapFocus, mapFinding = null, ohmsDrawn = false;
  // Findings from this page's own tools (the wiggle test, the PDH finder), drawn on the map too.
  let extra = [];

  root.innerHTML = `
    <div class="jobs" data-jobs="wiring">
      ${HowTo.slot("wiring")}
      <div class="job-area">
      <div class="panel">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="wiring.title">Wiring</h2>
          <div class="row" style="flex-wrap:wrap">
            <label class="small" data-tip="wiring.demo">See a practice fault
              <select id="w-demo"><option value="">Live robot</option></select></label>
            <button class="btn" id="w-edit" data-tip="wiring.edit">Edit the map</button>
          </div>
        </div>
        <p class="hint" id="w-meta"></p>
        <div id="w-banner"></div>
        <div class="schematic-wrap"><svg id="w-svg" class="schematic" role="group" aria-label="CAN chain and power schematic, in cable order"></svg></div>
        <div class="row small muted" style="flex-wrap:wrap;gap:14px">
          <span><span class="swatch can-h"></span><span class="term" tabindex="0" data-learn="can_bus">CAN-H / CAN-L</span>: CAN-H in each bus's cable color, CAN-L green on every bus; numbered in cable order from the roboRIO</span>
          <span><span class="swatch ok"></span>heard on the bus</span>
          <span><span class="swatch warn"></span>had trouble</span>
          <span><span class="swatch bad"></span>missing now</span>
          <span><span class="term" tabindex="0" data-learn="can_termination">Ω = terminator</span></span>
          <span>Click a box (or Tab to it and press Enter) to see its details below.</span>
        </div>
        <div id="w-detail" class="callout" hidden></div>
        <div id="w-detail-map" class="frc-slot"></div>
      </div>
      <!-- Its own section, shown only while editing: a long chain needs the whole work area. -->
      <div class="panel" id="w-editor" hidden></div>
      <div class="grid2">
        <div class="panel">
          <h3 data-tip="wiring.findings">Where to look</h3>
          <div id="w-findings"></div>
          <div id="w-where-map" class="frc-slot"></div>
        </div>
        <div class="stack">
          <div class="panel" id="w-ohms-panel">
            <h3 data-tip="wiring.ohms"><span class="term" tabindex="0" data-learn="can_termination">Termination check</span></h3>
            ${HowTo.steps({ need: "A multimeter. The robot <b>off</b>: a powered device makes the reading meaningless.",
              steps: ["Multimeter on ohms.", "Probes on CAN-H (the bus's color: yellow on the roboRIO's) and CAN-L (green) at any free CAN plug. With several buses, check each.", "Type the reading and press <b>Check</b>."],
              good: "about 60 Ω: the two terminators, one at each end of the chain." })}
            <div id="w-ohms-map" class="frc-slot"></div>
            <div class="row"><label class="row small" data-tip="wiring.ohms-in">Measured <input type="number" id="w-ohms" step="0.1" style="width:6em"> Ω</label><button class="btn" id="w-ohms-go" data-tip="wiring.ohms-go">Check</button></div>
            <div id="w-ohms-out" class="small"></div>
            ${HowTo.nextLine("ohms")}
          </div>
        </div>
      </div>
      <div class="panel">
        <h3 data-tip="wiring.pdh"><span class="term" tabindex="0" data-learn="power_path">PDH ports</span></h3>
        <div id="w-pdh-map" class="frc-slot"></div>
        <details class="small" ${matchMedia("(max-width: 600px)").matches ? "open" : ""}><summary data-tip="wiring.pdh-table">The ports as a table</summary><div id="w-pdh" class="pdh-grid"></div></details>
      </div>
      <div class="panel" id="w-find">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h3 data-tip="wiring.find">Find the PDH ports</h3>
          <div class="row" style="flex-wrap:wrap">
            <button class="btn" id="wf-pulse" data-tip="wiring.pulse">Swerve motors: pulse on blocks</button>
            <button class="btn" id="wf-log" data-tip="wiring.fromlog">Every motor: from a practice log</button>
            <button class="btn" id="wf-practice" data-tip="wiring.practice">Practice</button>
          </div>
        </div>
        ${HowTo.block(`<p class="small">Fills in the port numbers from the robot instead of from labels. <b>On blocks</b>, the robot turns each swerve motor in turn (about 12 s, deadman held) and the port whose current rises is that motor's. <b>From a practice log</b>, each motor's current is matched to the PDH channel that rises and falls with it: no test needed, so it works for mechanisms too, as long as they ran on their own. The PDH measures the <span class="term" data-learn="battery_current">battery side</span>, so expect smaller numbers than the motor's own current.</p>
        <ol class="small"><li>Robot on blocks, connected; the tool set to On blocks.</li><li><b>Swerve motors: pulse on blocks</b>, deadman held, about 12 s.</li>
          <li>For mechanisms, <b>Every motor: from a practice log</b>, picking a log where they ran one at a time.</li><li>Use the ports found, then save the map and redeploy.</li></ol>`)}
        <div id="wf-logs"></div>
        <div id="wf-out"></div>
        ${HowTo.nextLine("pdh")}
      </div>
      <div class="panel" id="w-wiggle">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h3 data-tip="wiring.wiggle"><span class="term" tabindex="0" data-learn="wiggle_test">Wiggle test</span></h3>
          <div class="row" style="flex-wrap:wrap">
            <button class="btn" id="ww-start" data-tip="wiring.wiggle-start">Start on the robot</button>
            <button class="btn" id="ww-practice" data-tip="wiring.practice">Practice</button>
          </div>
        </div>
        ${HowTo.block(`<p class="small">Finds a loose plug or a cracked wire that only fails when it moves. Robot <b>on and disabled</b>: hands in the robot only while it is disabled. Go through the steps, gently wiggling each cable and plug for a few seconds; the tool watches the CAN bus and every controller, and says which step made something happen.</p>`)}
        <div id="ww-body"></div>
        ${HowTo.nextLine("wiggle")}
      </div>
    </div></div>`;

  // ---------------------------------------------------------------- data
  async function refresh() {
    if (editing) return;
    const q = logAt ? `?log=${encodeURIComponent(logAt.path)}&t=${logAt.t}` : demo ? "?demo=" + encodeURIComponent(demo) : "";
    const d = await App.api("/api/wiring" + q);
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
    for (const f of [...((data && data.findings) || []), ...extra]) {
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

  // A bus's cable color: the CAN-H wire; CAN-L is green on every bus.
  const busColor = bi => (data.palette || {})[(data.bus_colors || [])[bi]] || "#e5b31b";
  const swatchOf = bi => `<span class="bus-swatch" style="--c:${esc(busColor(bi))}" aria-hidden="true"></span>`;

  function paint() {
    const m = data.map;
    const rows = rowsByName(), hl = highlighted(), live = !!(data.snapshot && data.snapshot.motors);
    // One bus in full; several, a short line each and the lengths' basis once.
    const count = b => b.chain.filter(n => n !== "roboRIO" && n !== "PDH").length;
    const L = bi => data.lengths[bi] || [0, 0, 0];
    const busLine = m.buses.length === 1
      ? `${count(m.buses[0])} devices on ${esc(m.buses[0].name)} · bus about ${fmt(L(0)[0], 1)} m (${L(0)[1]} of ${L(0)[2]} segments measured; CAN allows 40 m)`
      : m.buses.map((b, bi) => `${swatchOf(bi)}${esc(b.name)}: ${count(b)} devices, about ${fmt(L(bi)[0], 1)} m`).join(" · ")
        + ` (${m.buses.reduce((a, b, bi) => a + L(bi)[1], 0)} of ${m.buses.reduce((a, b, bi) => a + L(bi)[2], 0)} segments measured; CAN allows 40 m on each bus)`;
    const confirmed = m.buses.every(b => b.orderConfirmed);
    $("#w-meta", root).innerHTML = `${esc(data.path)} · ${busLine} ·
      ${confirmed ? `<span class="chip good">order checked on the robot</span>` : `<span class="chip warn">order not checked yet</span>`}
      ${logAt ? `<span class="chip info">from the log at ${fmt(logAt.t, 2)} s <button class="btn small" id="w-live">back to live</button></span>`
        : data.demo ? `<span class="chip info">practice: ${esc(data.demos[data.demo])}</span>` : live ? "" : `<span class="chip">no live data</span>`}`;
    const back = $("#w-live", root);
    if (back) back.onclick = () => { logAt = null; refresh(); };

    const svg = $("#w-svg", root);
    // Several buses draw smaller boxes, without the part's picture, so every bus fits on one screen.
    const multi = m.buses.length > 1;
    const W = Math.max(640, svg.clientWidth || 900), pad = 26, padY = multi ? 6 : pad;
    const [bw, bh, gx, gy] = multi ? [168, 58, 30, 34] : [196, 76, 36, 54];
    const perRow = Math.max(2, Math.floor((W - 2 * pad + gx) / (bw + gx)));
    // Each bus its own snake of boxes (so the cable stays one line), one bus under the next, with its
    // name and cable color above it when there is more than one.
    const labelH = multi ? 24 : 0;
    const slots = [], busTop = [];
    let y0 = padY;
    m.buses.forEach((b, bi) => {
      busTop.push(y0);
      y0 += labelH;
      b.chain.forEach((name, i) => {
        const r = Math.floor(i / perRow), c = i % perRow, col = r % 2 === 0 ? c : perRow - 1 - c;
        slots.push({ bi, i, name, x: pad + col * (bw + gx), y: y0 + r * (bh + gy) });
      });
      y0 += Math.ceil(b.chain.length / perRow) * (bh + gy) - gy + (bi < m.buses.length - 1 ? gy : 0);
    });
    const H = y0 + padY + (multi ? 14 : 0);
    const center = s0 => ({ x: s0.x + bw / 2, y: s0.y + bh / 2 });

    // What each box shows, worked out first: the drawing is rebuilt only when that changes.
    const details = {};
    const nodes = slots.map(({ name, i, bi }) => {
      const dev = data.devices[name] || {}, r = rows[name];
      let state = "unknown";
      if (r) state = r.present === 0 ? "bad" : (r.dropouts || r.resets || r.brownouts) ? "warn" : "ok";
      if (hl.devs.has(name)) state = hl.devs.get(name);
      const word = { bad: "MISSING NOW", warn: "had trouble", ok: "heard", unknown: "" }[state] || "";
      const port = m.pdhPorts[name];
      details[name] = [dev.model, dev.can_id != null ? "CAN ID " + dev.can_id : null,
        port != null ? "PDH port " + port : (dev.kind === "controller" ? "PDH port not set" : null), dev.source,
        r ? `heard on the bus: ${r.present ? "yes" : "NO"}; dropped out ${r.dropouts || 0}×; rebooted ${r.resets || 0}×; low supply ${r.brownouts || 0}×` : null,
        r && Number.isFinite(r.bus_volts) ? `supply at the controller ${fmt(r.bus_volts, 2)} V` : null].filter(Boolean);
      // FIRST's drawing of the part: a cached bitmap, drawn once (the schematic repaints every second).
      const art = name === "roboRIO" ? "rio" : name === "PDH" ? "pdh_top" : FrcMap.kind(dev.model);
      const pic = !multi && art && FrcMap.thumbCached(art);
      if (!multi && art && !pic) FrcMap.thumb(art);
      const sub = name === "roboRIO" ? "120 Ω built in" : name === "PDH"
        ? `CAN ${dev.can_id} · term ${m.pdh.terminationOn ? "ON" : "OFF"}`
        : `CAN ${dev.can_id ?? "?"} · PDH ${port ?? "?"}`;
      return { name, i, bi, state, word, pic, sub, ohm: name === "roboRIO" || (name === "PDH" && m.pdh.terminationOn) };
    });
    // The schematic repaints every second with the live data. Rebuilding it when nothing had changed
    // destroyed the box a person had tabbed to, and pressing Enter destroyed the box pressed.
    const key = JSON.stringify([W, focus, m.pdh.terminationOn, data.bus_colors, m.buses.map(b => b.name), hl.segs.map(x => [x.a, x.b, x.f.title]),
      nodes.map(n => [n.name, n.state, n.word, n.sub, !!n.pic, n.ohm])]);
    if (key !== svg._key) {
      svg._key = key;
      const had = svg.contains(document.activeElement) ? document.activeElement.getAttribute("data-name") : null;
      svg.innerHTML = "";
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
      svg.style.height = H + "px";

      if (multi) {
        // Each bus's name over its two wires: its own color, and green.
        m.buses.forEach((b, bi) => {
          const y = busTop[bi];
          el("line", { x1: pad, y1: y + 9, x2: pad + 26, y2: y + 9, class: "wire can-case" }, svg);
          el("line", { x1: pad, y1: y + 9, x2: pad + 26, y2: y + 9, class: "wire can-h", style: `stroke:${busColor(bi)}` }, svg);
          el("line", { x1: pad, y1: y + 15, x2: pad + 26, y2: y + 15, class: "wire can-l" }, svg);
          el("text", { x: pad + 34, y: y + 17, class: "bus-label" }, svg, `${b.name}: ${(data.bus_colors || [])[bi] || ""} and green`);
        });
      }
      // The cable: CAN-H in the bus's color over a thin edge (a white or grey cable still shows on a
      // light page), CAN-L green, side by side.
      for (let k = 0; k + 1 < slots.length; k++) {
        if (slots[k].bi !== slots[k + 1].bi) continue;
        const a = center(slots[k]), b = center(slots[k + 1]), vertical = Math.abs(a.y - b.y) > 1;
        const at = off => ({ x1: a.x + (vertical ? off : 0), y1: a.y + (vertical ? 0 : off), x2: b.x + (vertical ? off : 0), y2: b.y + (vertical ? 0 : off) });
        el("line", Object.assign(at(-3), { class: "wire can-case" }), svg);
        el("line", Object.assign(at(-3), { class: "wire can-h", style: `stroke:${busColor(slots[k].bi)}` }), svg);
        el("line", Object.assign(at(3), { class: "wire can-l" }), svg);
      }
      for (const sg of hl.segs) {
        const k = slots.findIndex((x, j) => j + 1 < slots.length && slots[j + 1].bi === x.bi
          && ((x.name === sg.a && slots[j + 1].name === sg.b) || (x.name === sg.b && slots[j + 1].name === sg.a)));
        if (k < 0) continue;
        const a = center(slots[k]), b = center(slots[k + 1]);
        const g = el("g", { class: "suspect", "aria-label": "Suspect cable: " + sg.f.title }, svg);
        el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "suspect-line" }, g);
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        el("circle", { cx: mx, cy: my, r: 11, class: "suspect-dot" }, g);
        el("text", { x: mx, y: my + 4, "text-anchor": "middle", class: "suspect-mark" }, g, "!");
      }

      nodes.forEach(({ name, i, state, word, pic, sub, ohm }, k) => {
        const p = slots[k];
        const g = el("g", { class: "node " + state + (focus === name ? " focus" : ""), tabindex: 0, role: "button",
          "data-name": name, "aria-pressed": String(focus === name), "aria-label": `${i}. ${name}${word ? ", " + word : ""}` }, svg);
        el("rect", { x: p.x - 4, y: p.y - 4, width: bw + 8, height: bh + 8, rx: 11, class: "ring" }, g);
        el("rect", { x: p.x, y: p.y, width: bw, height: bh, rx: 8, class: "box" }, g);
        if (pic) {
          // On a white tile, as FIRST draws it: a black SPARK Flex vanished on a dark box, a white MAX on a light one.
          el("rect", { x: p.x + bw - 64, y: p.y + 6, width: 58, height: bh - 12, rx: 4, class: "art-tile" }, g);
          el("image", { href: pic, x: p.x + bw - 62, y: p.y + 8, width: 54, height: bh - 16, preserveAspectRatio: "xMidYMid meet", class: "art" }, g);
        }
        const label = `${i}. ${name}`, cut = multi ? 21 : 19;
        const [y1, y2, y3] = multi ? [20, 37, 52] : [22, 42, 62];
        el("text", { x: p.x + 10, y: p.y + y1, class: "nm" }, g, label.length > cut ? label.slice(0, cut - 1) + "…" : label);
        el("text", { x: p.x + 10, y: p.y + y2, class: "sub" }, g, sub);
        if (word) el("text", { x: p.x + 10, y: p.y + y3, class: "state" }, g, word);
        if (ohm) el("text", { x: p.x + bw - (pic ? 80 : 20), y: p.y + y1, class: "ohm" }, g, "Ω");
        g.onclick = () => { focus = focus === name ? null : name; paint(); };
        // Enter opens it. Not Space: on the Driver Station laptop Space is the E-STOP.
        g.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); g.onclick(); } };
      });
      const pdhSlot = slots.find(x => x.name === "PDH");
      if (!m.pdh.terminationOn && pdhSlot) {
        el("text", { x: pdhSlot.x, y: pdhSlot.y + bh + 16, class: "warn-text" }, svg, "No terminator at this end: switch the PDH's termination ON");
      }
      // A bus that doesn't end at the PDH ends at a terminator someone has to fit.
      m.buses.forEach((b, bi) => {
        const ends = slots.filter(x => x.bi === bi), last = ends[ends.length - 1];
        if (multi && last && last.name !== "PDH" && ends.length > 1) {
          el("text", { x: last.x, y: last.y + bh + 16, class: "hint-text" }, svg, "End of the bus: a 120 Ω terminator goes here");
        }
      });
      // The same box keeps focus across a rebuild (a click, or its state changing).
      if (had) {
        const back = [...svg.querySelectorAll("[data-name]")].find(x => x.getAttribute("data-name") === had);
        if (back) back.focus({ preventScroll: true });
      }
    }
    const det = $("#w-detail", root);
    det.hidden = !focus || !details[focus];
    if (focus && details[focus]) {
      const segs = hl.segs.filter(s => s.a === focus || s.b === focus);
      det.innerHTML = `<b>${esc(focus)}</b><ul style="margin:4px 0 0;padding-left:18px">${details[focus].map(x => `<li>${esc(x)}</li>`).join("")}
        ${segs.map(s => `<li class="bad-ink">Suspect cable next to it: ${esc(s.f.title)}. ${Learn.link(s.f.why, 2)}</li>`).join("")}</ul>`;
    }
    if (focus !== mapFocus) {
      mapFocus = focus;
      const slot = $("#w-detail-map", root);
      if (!focus) { slot.innerHTML = ""; slot._frc = null; }
      else FrcMap.render(slot, deviceView(focus));
    }
    paintPdh(rows);
    paintFindings();
  }

  function deviceView(name) {
    const m = data.map, dev = data.devices[name] || {};
    if (name === "roboRIO") return { view: "rio", focus: [{ part: "rio_can", state: "here", label: "CAN: one end of the chain, 120 Ω inside" },
      { part: "rio_power", state: "here", label: "Power, from the PDH" }], alt: "The roboRIO's CAN and power connectors" };
    if (name === "PDH") return { view: "pdh", focus: [{ part: "pdh_can", state: "here", label: "CAN" },
      { part: "pdh_term", state: m.pdh.terminationOn ? "ok" : "bad", label: `TERM ${m.pdh.terminationOn ? "ON" : "OFF: switch it ON at the chain's end"}` },
      { part: "pdh_battery", state: "here", label: "Battery in" }], alt: "The PDH's CAN, termination and battery connections" };
    const f = FrcMap.deviceFocus(name, dev.model || dev.kind, m.pdhPorts[name], "here", dev.can_id != null ? `CAN ${dev.can_id}` : "");
    return { view: "controllers", focus: f, alt: `Where ${name} is powered from` };
  }

  // A finding on FIRST's drawing: the bus, the devices it names, their PDH ports.
  function findingView(f) {
    const w = f.where || {}, st = f.level === "error" ? "bad" : "warn";
    if (w.bus) return { view: "can", wires: "can", focus: [{ part: "rio_can", state: "here", label: "roboRIO: one end, 120 Ω inside" },
      { part: "pdh_can", state: st, label: "CAN at the PDH" }, { part: "pdh_term", state: st, label: "TERM switch" }],
      caption: "The CAN pair is brightened." };
    const devs = w.devices || [];
    const focus = devs.flatMap(d => FrcMap.deviceFocus(d, (data.devices[d] || {}).model, w.pdh_port != null && devs.length === 1 ? w.pdh_port : data.map.pdhPorts[d], st));
    if (w.segment) return { view: "can", wires: "can", focus: focus.filter(x => !x.part.startsWith("pdh_")),
      title: `Check the CAN plugs between ${w.segment[0]} and ${w.segment[1]}`, caption: "The CAN pair is brightened." };
    return { view: "controllers", focus };
  }

  function paintPdh(rows) {
    const m = data.map, cur = (((data.snapshot || {}).pdh) || {}).currents || [];
    const byPort = {};
    for (const [n, p] of Object.entries(m.pdhPorts)) (byPort[p] = byPort[p] || []).push(n);
    const cells = [];
    for (let p = 0; p < 24; p++) {
      const amps = cur[p], names = byPort[p] || [];
      const pct = Number.isFinite(amps) ? Math.min(100, amps / 40 * 100) : 0;
      cells.push(`<div class="pdh-port ${names.length ? "" : "unmapped"}">
        <span class="mono small">${p}${p >= 20 ? (p === 23 ? " switchable" : " low current") : ""}</span>
        <span class="small names">${esc(names.join(", ") || "nothing mapped")}</span>
        <div class="pdh-bar"><div style="width:${pct}%"></div></div>
        <span class="mono small">${Number.isFinite(amps) ? fmt(amps, 1) + " A" : ""}</span></div>`);
    }
    // The same ports on FIRST's drawing of the PDH: what each one feeds, and how hard.
    const bad = new Set((data.findings || []).filter(f => f.where && f.where.pdh_port != null).map(f => f.where.pdh_port));
    FrcMap.render($("#w-pdh-map", root), { view: "pdh", alt: "The PDH, each mapped port labeled with its motor",
      caption: Object.keys(byPort).length ? "Unmapped ports are faded." : "No ports mapped yet: Find the PDH ports, below, fills them in.",
      focus: Object.entries(byPort).map(([p, names]) => {
        const a = cur[p];
        return { part: "pdh_" + p, state: bad.has(+p) ? "bad" : Number.isFinite(a) && a >= 30 ? "warn" : "info",
          label: names.join(", ") + (Number.isFinite(a) ? ` · ${fmt(a, 0)} A` : "") };
      }) });
    $("#w-pdh", root).innerHTML = cells.join("") +
      `<p class="hint" style="grid-column:1/-1">Ports 0-19 take 40 A breakers, 20-22 are low-current, 23 is switchable. Each bar is full at 40 A. Live currents come from AdvantageKit's PDH log.</p>`;
  }

  function paintFindings() {
    const F = [...extra, ...(data.findings || [])];
    if (mapFinding && !F.some(x => x.title === mapFinding)) { mapFinding = null; $("#w-where-map", root).innerHTML = ""; $("#w-where-map", root)._frc = null; }
    $("#w-banner", root).innerHTML = F.some(f => f.where && f.where.bus)
      ? `<div class="callout bad">${F.filter(f => f.where && f.where.bus).map(f => esc(f.title)).join(" · ")}</div>` : "";
    const html = F.length ? F.map(f => `<div class="finding">
        <div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
        <div class="why">${Learn.link(f.why, 3)}</div>
        ${f.fix ? `<div class="small"><b>Do:</b> ${Learn.link(f.fix, 2)}</div>` : ""}
        ${f.where ? `<div class="row"><button class="btn small ${mapFinding === f.title ? "primary" : ""}" data-show-map="${esc(f.title)}" data-tip="wiring.onrobot" data-quiet>${mapFinding === f.title ? "Shown below" : "Show on the drawing"}</button></div>` : ""}</div>`).join("")
      : `<p class="hint">${data.snapshot && data.snapshot.motors ? "Nothing wrong with the CAN bus or the power feeds right now." : "Connect to a robot, or pick a practice fault above to see how a problem shows up."}</p>`;
    // Every second with the live data: rewritten only when it reads differently, so a button keeps
    // its focus and its tip.
    const box = $("#w-findings", root);
    if (box._html === html) return;
    const had = box.contains(document.activeElement) ? document.activeElement.getAttribute("data-show-map") : null;
    box._html = html;
    box.innerHTML = html;
    if (had) { const back = $$("[data-show-map]", box).find(x => x.dataset.showMap === had); if (back) back.focus({ preventScroll: true }); }
    $$("[data-show-map]", box).forEach(b => b.onclick = () => {
      const f = F.find(x => x.title === b.dataset.showMap);
      mapFinding = f ? f.title : null;
      if (f) FrcMap.render($("#w-where-map", root), findingView(f));
      paintFindings();
    });
  }

  // ---------------------------------------------------------------- the map editor
  // The editor sits in another section than the drawing: show its section while editing, and the
  // drawing's again after.
  const sectionOf = sel => $(sel, root).closest(".job-area > *");
  function openEditor() {
    editing = JSON.parse(JSON.stringify(data.map));
    paintEditor();
    HowTo.select("wiring", sectionOf("#w-editor"));
    const h = $("#w-editor h3", root);
    h.setAttribute("tabindex", "-1");
    h.focus({ preventScroll: true });
    $("#w-editor", root).scrollIntoView({ block: "nearest" });
  }
  function closeEditor() {
    editing = null;
    $("#w-editor", root).hidden = true;
    HowTo.select("wiring", sectionOf("#w-svg"));
    refresh();
  }

  let editBus = 0;
  function paintEditor() {
    const box = $("#w-editor", root);
    if (editBus >= editing.buses.length) editBus = 0;
    const bus = editing.buses[editBus], chain = bus.chain;
    const palette = data.palette || {}, colorNow = (b, i) => b.color || (data.bus_colors || [])[i] || "yellow";
    const taken = editing.buses.map((b, i) => i === editBus ? null : colorNow(b, i));
    box.hidden = false;
    box.innerHTML = `<h3>Edit the map</h3>
      ${editing.buses.length > 1 ? `<div class="seg" style="width:max-content" role="group" aria-label="Bus">${editing.buses.map((b, i) =>
        `<button data-bus="${i}" class="${i === editBus ? "on" : ""}" aria-pressed="${i === editBus}" data-tip="wiring.bus-pick">${esc(b.name)}</button>`).join("")}</div>` : ""}
      <div class="row small">
        <label class="row" data-tip="wiring.bus-name">Bus <input id="we-name" value="${esc(bus.name)}" style="width:10em"></label>
        <label class="row" data-tip="wiring.bus-color">Cable <select id="we-color">${Object.keys(palette).map(c =>
          `<option value="${c}" ${colorNow(bus, editBus) === c ? "selected" : ""} ${taken.includes(c) ? "disabled" : ""}>${c} / green</option>`).join("")}</select></label>
        <button class="btn small" id="we-add" data-tip="wiring.bus-add" ${editing.buses.length >= Object.keys(palette).length ? "disabled" : ""}>Add a bus</button>
      </div>
      <p class="small">Follow the CAN cable on the robot from the roboRIO and put the devices in the order you meet them. Then type the PDH port feeding each controller (it is printed next to each breaker).</p>
      <label class="row small"><input type="checkbox" id="we-ok" ${bus.orderConfirmed ? "checked" : ""}> I checked this order on the robot</label>
      ${chain.includes("PDH") ? `<label class="row small"><input type="checkbox" id="we-term" ${editing.pdh.terminationOn ? "checked" : ""}> The PDH's termination switch is ON (it should be, at the end of the chain)</label>`
        : `<p class="small">No PDH on this bus: its far end needs a 120 Ω terminator.</p>`}
      ${chain.length < 2 ? `<p class="small muted">No devices on this bus yet. On another bus, pick this one in the list beside a device to move it here.</p>` : ""}
      <ol class="chain-edit" ${chain.length > 8 ? `style="grid-auto-flow:column;grid-template-rows:repeat(${Math.ceil(chain.length / 2)},auto)"` : ""}>${chain.map((n, i) => `<li>
        <span class="mono small">${i}</span><span>${esc(n)}</span>
        ${n === "roboRIO" || n === "PDH" ? "<span></span><span></span>" : `<input type="number" min="0" max="23" placeholder="PDH" data-port="${esc(n)}" value="${editing.pdhPorts[n] ?? ""}" aria-label="PDH port for ${esc(n)}">
        <span><button class="btn small" data-up="${i}" ${i <= 1 ? "disabled" : ""} aria-label="Move up">↑</button><button class="btn small" data-down="${i}" ${i >= chain.length - 1 || chain[i + 1] === "PDH" ? "disabled" : ""} aria-label="Move down">↓</button>
          ${editing.buses.length > 1 ? `<select data-move="${esc(n)}" aria-label="Bus for ${esc(n)}" data-tip="wiring.bus-move">${editing.buses.map((b, j) =>
            `<option value="${j}" ${j === editBus ? "selected" : ""}>${esc(b.name)}</option>`).join("")}</select>` : ""}</span>`}
      </li>`).join("")}</ol>
      <div class="row"><button class="btn primary" id="we-save">Save to the robot project…</button><button class="btn" id="we-cancel">Cancel</button></div>
      <p class="small muted">Saved and redeployed, the map goes to the robot too: Robot Health alerts then name each motor's PDH port, and, once the order is checked, the plugs either side of it on the CAN cable.</p>`;
    $$("[data-up]", box).forEach(b => b.onclick = () => { const i = +b.dataset.up; [chain[i - 1], chain[i]] = [chain[i], chain[i - 1]]; paintEditor(); });
    $$("[data-down]", box).forEach(b => b.onclick = () => { const i = +b.dataset.down; [chain[i + 1], chain[i]] = [chain[i], chain[i + 1]]; paintEditor(); });
    $$("[data-port]", box).forEach(inp => inp.onchange = () => {
      if (inp.value === "") delete editing.pdhPorts[inp.dataset.port]; else editing.pdhPorts[inp.dataset.port] = +inp.value;
    });
    $("#we-ok", box).onchange = e => { bus.orderConfirmed = e.target.checked; };
    $$("[data-bus]", box).forEach(b => b.onclick = () => { editBus = +b.dataset.bus; paintEditor(); });
    $("#we-name", box).onchange = e => { bus.name = e.target.value.trim() || bus.name; paintEditor(); };
    $("#we-color", box).onchange = e => { bus.color = e.target.value; };
    $("#we-add", box).onclick = () => {
      const used = editing.buses.map((b, i) => colorNow(b, i));
      editing.buses.push({ name: "bus " + (editing.buses.length + 1), color: Object.keys(palette).find(c => !used.includes(c)) || "orange",
        chain: ["roboRIO"], orderConfirmed: false, segmentLengthsM: {} });
      editBus = editing.buses.length - 1;
      paintEditor();
    };
    // A device moved to another bus goes to that bus's far end (before the PDH): check its place there.
    $$("[data-move]", box).forEach(sel => sel.onchange = () => {
      const to = editing.buses[+sel.value], name = sel.dataset.move;
      if (to === bus) return;
      bus.chain.splice(bus.chain.indexOf(name), 1);
      to.chain.splice(to.chain[to.chain.length - 1] === "PDH" ? to.chain.length - 1 : to.chain.length, 0, name);
      bus.orderConfirmed = to.orderConfirmed = false;
      paintEditor();
    });
    const term = $("#we-term", box);
    if (term) term.onchange = e => { editing.pdh.terminationOn = e.target.checked; };
    $("#we-cancel", box).onclick = closeEditor;
    $("#we-save", box).onclick = async () => {
      if (await App.previewAndSave({ kind: "wiring", map: editing }, "Save the wiring map")) {
        closeEditor();
      }
    };
  }

  // ---------------------------------------------------------------- finding PDH ports
  const STATUS = { found: "found", none: "nothing rose", unclear: "unclear", together: "ran together", idle: "never ran" };
  const VERDICT = { same: "good", new: "info", differs: "warn" };

  async function findByPulse() {
    const out = $("#wf-out", root);
    $("#wf-logs", root).innerHTML = "";
    if (!App.connected()) { App.toast("Connect to the robot first (or try Practice)."); return; }
    if (!["BLOCKS", "SIM"].includes(App.env())) { App.toast("Set the environment to On blocks first (top bar)."); return; }
    out.innerHTML = `<div class="callout info">Every wheel off the ground. Enable the robot, then hold the deadman (the tester's controller right bumper, or Hold to run on screen) for about 12 seconds while each swerve motor turns in turn.</div>`;
    try {
      const doc = await App.runTest("pdh_map", "ALL", {});
      showFound(await App.api("/api/wiring/pdhfind?run=" + encodeURIComponent(doc._file)), "pulse");
    } catch (e) { out.innerHTML = `<p class="hint">${esc(e.message)}</p>`; }
  }

  async function chooseLog() {
    let folder = "";
    try { folder = localStorage.getItem("swervetune.logfolder") || ""; } catch (e) { /* storage blocked */ }
    const box = $("#wf-logs", root);
    $("#wf-out", root).innerHTML = "";
    box.innerHTML = `<div class="row" style="flex-wrap:wrap"><input id="wf-folder" style="min-width:22em" placeholder="Folder with .wpilog files" aria-label="Log folder" value="${esc(folder)}">
      <button class="btn" id="wf-list">List logs</button></div><p class="hint">Best: a practice log where each mechanism ran on its own for a moment.</p><div id="wf-loglist"></div>`;
    const list = async () => {
      const f = $("#wf-folder", box).value;
      try { localStorage.setItem("swervetune.logfolder", f); } catch (e) { /* storage blocked */ }
      const r = await App.api("/api/logs?folder=" + encodeURIComponent(f));
      const ll = $("#wf-loglist", box);
      if (!r.ok) { ll.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
      ll.innerHTML = r.files.length ? `<div class="tblwrap"><table class="t"><tbody>${r.files.slice(0, 20).map(x => `<tr>
          <td class="mono small">${esc(x.name)}</td><td class="small">${new Date(x.mtime * 1000).toLocaleString()}</td>
          <td><button class="btn small" data-plog="${esc(x.path)}">Use this log</button></td></tr>`).join("")}</tbody></table></div>`
        : `<p class="hint">No .wpilog files in that folder.</p>`;
      $$("[data-plog]", ll).forEach(b => b.onclick = async () => {
        $("#wf-out", root).innerHTML = `<p class="hint">Matching currents in ${esc(b.dataset.plog)}…</p>`;
        showFound(await App.api("/api/wiring/pdhfind?log=" + encodeURIComponent(b.dataset.plog)), "log");
      });
    };
    $("#wf-list", box).onclick = list;
    if (folder) list();
  }

  function showFound(r, source) {
    const out = $("#wf-out", root);
    if (r.ok === false) { out.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    const rows = r.rows || [], chain = new Set(data ? data.map.buses.flatMap(b => b.chain) : []);
    const usable = x => x.port != null && !r.practice && x.verdict !== "same" && chain.has(x.name);
    extra = (r.findings || []).filter(f => f.where);
    out.innerHTML = `
      ${r.practice ? `<div class="callout info">Practice data from a made-up robot, so nothing here can be saved. One motor is fed from somewhere else on purpose.</div>` : ""}
      ${rows.length ? `<div class="tblwrap"><table class="t" style="width:auto;min-width:min(100%,640px)"><thead><tr><th>Motor</th><th>Found port</th>
          <th>${source === "log" ? `<span class="term" data-learn="battery_current">Match</span>` : `<span class="term" data-learn="battery_current">Rise</span>`}</th>
          <th>In the map</th><th></th><th>Use</th></tr></thead><tbody>
        ${rows.map((x, i) => `<tr><td>${esc(x.name)}</td>
          <td class="num">${x.port != null ? x.port : x.port_guess != null && x.status !== "none" ? `<span class="muted">${x.port_guess}?</span>` : "–"}</td>
          <td class="num small">${x.rise_a != null ? fmt(x.rise_a, 2) + " A" : x.corr != null ? fmt(x.corr, 2) : ""}</td>
          <td class="num">${x.mapped != null ? x.mapped : "–"}</td>
          <td><span class="chip ${x.status === "found" ? VERDICT[x.verdict] || "" : x.status === "idle" ? "" : "warn"}">${esc(x.status === "found" ? (x.verdict === "same" ? "matches the map" : x.verdict === "new" ? "new" : "differs from the map") : STATUS[x.status] || x.status)}</span></td>
          <td>${usable(x) ? `<input type="checkbox" data-use="${i}" checked aria-label="Use port ${x.port} for ${esc(x.name)}">` : x.port != null && !chain.has(x.name) && !r.practice ? `<span class="small muted">not in the map</span>` : ""}</td></tr>`).join("")}
        </tbody></table></div>` : ""}
      ${(r.findings || []).map(f => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
        <div class="why">${Learn.link(f.why, 2)}</div></div>`).join("")}
      ${r.plot && r.plot.t.length ? `<h4>What the PDH saw</h4><canvas id="wf-plot" style="width:100%;height:240px" aria-label="PDH channel currents during the pulses"></canvas>
        <p class="hint">Current on each PDH port, in amps. Each shaded span is one motor's pulse: the line that jumps inside it is that motor's port. Hover a span for its numbers.</p>` : ""}
      ${rows.some(usable) ? `<button class="btn primary" id="wf-save">Save the ticked ports to the map…</button>` : ""}`;
    if (r.plot && r.plot.t.length) {
      const cols = ["--s0", "--s1", "--s2", "--s3", "--accent", "#e48b32", "#d660a8", "--muted"];
      const series = Object.entries(r.plot.channels).map(([p, y], i) => ({ x: r.plot.t, y, color: cols[i % cols.length], width: 1.4, label: "port " + p }));
      const notes = r.plot.pulses.map(s => ({ type: "vspan", x0: s.x0, x1: s.x1, learn: "battery_current",
        label: s.name.replace(/^(front|back)(left|right) /, (m, a, b) => a[0].toUpperCase() + b[0].toUpperCase() + " "),
        text: s.port != null ? `${s.name}: port ${s.port} rose ${fmt(s.rise_a, 2)} A` : `${s.name}: no port rose clearly` }));
      Plot.draw($("#wf-plot", out), { series, xlabel: "s", annotations: notes });
    }
    const save = $("#wf-save", out);
    if (save) save.onclick = async () => {
      const map = JSON.parse(JSON.stringify(data.map));
      $$("[data-use]", out).forEach(cb => { if (cb.checked) { const x = rows[+cb.dataset.use]; map.pdhPorts[x.name] = x.port; } });
      if (await App.previewAndSave({ kind: "wiring", map }, "Save PDH ports to the wiring map")) { extra = []; out.innerHTML = ""; refresh(); }
    };
    if (data) paint();
  }

  // ---------------------------------------------------------------- the wiggle test
  let wig = null;

  function wiggleSteps() {
    const m = data.map, steps = [], many = m.buses.length > 1;
    for (const b of m.buses) {
      const chain = b.chain;
      for (let i = 0; i + 1 < chain.length; i++) {
        steps.push({ key: `can:${chain[i]}|${chain[i + 1]}`, kind: "can", seg: [chain[i], chain[i + 1]],
          text: `CAN${many ? ` (${esc(b.name)})` : ""}: wiggle the cable and both plugs between <b>${esc(chain[i])}</b> and <b>${esc(chain[i + 1])}</b>.` });
      }
    }
    const devices = [...new Set(m.buses.flatMap(b => b.chain))].filter(n => n !== "roboRIO" && n !== "PDH");
    for (const n of devices) {
      const dev = data.devices[n] || {};
      if (dev.kind && dev.kind !== "controller") continue;
      const port = m.pdhPorts[n];
      steps.push({ key: `power:${n}`, kind: "power", dev: n,
        text: `Power: wiggle <b>${esc(n)}</b>'s power leads, from ${port != null ? `PDH port ${port} and its breaker` : "its PDH port"} to the controller.` });
    }
    steps.push({ key: "main", kind: "main", text: "Main power: wiggle the battery leads, the main breaker and the PDH's input lugs." });
    return steps;
  }

  function changes(prev, now) {
    const out = [], before = {};
    for (const r of prev.motors || []) before[r.name] = r;
    for (const r of now.motors || []) {
      const b = before[r.name];
      if (!b) continue;
      if (b.present && !r.present) out.push(`${r.name} went off the CAN bus`);
      if ((r.dropouts || 0) > (b.dropouts || 0)) out.push(`${r.name} dropped out`);
      if ((r.resets || 0) > (b.resets || 0)) out.push(`${r.name} lost power and rebooted`);
      if ((r.brownouts || 0) > (b.brownouts || 0)) out.push(`${r.name} saw low supply voltage`);
    }
    const a = prev.can || [], c = now.can || [];
    if (c.length > 5 && a.length > 5 && c[5] > a[5]) out.push(`CAN errors (${c[5] - a[5]} loops)`);
    if (c[1] > (a[1] || 0)) out.push("the CAN bus shut itself down (bus-off)");
    return out;
  }

  // Many polls make many small events: add up the CAN error loops, count repeats.
  function summarize(ev) {
    let loops = 0;
    const seen = new Map();
    for (const e of ev) {
      const m = /^CAN errors \((\d+) loops\)$/.exec(e);
      if (m) loops += +m[1]; else seen.set(e, (seen.get(e) || 0) + 1);
    }
    const out = loops ? [`CAN errors in ${loops} robot loop${loops === 1 ? "" : "s"}`] : [];
    for (const [t, n] of seen) out.push(n > 1 ? `${t} (${n} times)` : t);
    return out;
  }

  async function wiggleTick() {
    if (!wig || wig.busy) return;
    wig.busy = true;
    try {
      const step = wig.steps[wig.i];
      const r = wig.practice ? await App.api(`/api/wiring/wiggle?step=${encodeURIComponent(step.key)}`) : await App.api("/api/wiring");
      const snap = r.snapshot || {};
      if (!snap.motors) { wig.note = "No live data: is the robot connected?"; return; }
      if (wig.last) {
        const seen = changes(wig.last, snap);
        if (seen.length) {
          (wig.events[wig.i] = wig.events[wig.i] || []).push(...seen);
          wig.flash = Date.now();
        }
      }
      wig.last = snap;
      wig.live = true;
      wig.note = "";
    } finally {
      if (wig) { wig.busy = false; paintWiggle(); }
    }
  }

  async function startWiggle(practice) {
    if (!data) return;
    if (!practice && !App.connected()) { App.toast("Connect to the robot first (or try Practice)."); return; }
    stopWiggle();
    demo = ""; logAt = null;
    if (practice) await App.api("/api/wiring/wiggle?reset=1");
    wig = { practice, steps: wiggleSteps(), i: 0, events: {}, last: null, note: "", flash: 0, busy: false };
    wig.timer = setInterval(wiggleTick, 250);
    paintWiggle();
  }

  function stopWiggle() {
    if (wig) clearInterval(wig.timer);
  }

  function wiggleFindings() {
    const F = [];
    wig.steps.forEach((s, i) => {
      const ev = wig.events[i];
      if (!ev || !ev.length) return;
      const what = summarize(ev);
      const title = s.kind === "can" ? `Wiggling the CAN cable between ${s.seg[0]} and ${s.seg[1]} caused trouble`
        : s.kind === "power" ? `Wiggling ${s.dev}'s power leads caused trouble` : "Wiggling the main power caused trouble";
      const why = `${what.slice(0, 6).join("; ")}${what.length > 6 ? "; …" : ""}. ` + (s.kind === "can"
        ? "Reseat both plugs, check the pins are fully home and the latches catch, and look for a nicked or crushed wire; re-crimp or replace that cable."
        : s.kind === "power" ? "Check the leads are fully in the Wago or terminal, the crimps hold when tugged, and the breaker is seated firmly in its port."
        : "Tighten the battery and PDH lugs, check the main breaker's bolts, and look for a cracked battery terminal.");
      F.push({ level: "warn", title, why, where: s.kind === "can" ? { segment: s.seg } : s.kind === "power" ? { devices: [s.dev] } : { bus: true } });
    });
    return F;
  }

  function paintWiggle() {
    const box = $("#ww-body", root);
    if (!wig) { box.innerHTML = ""; box._ww = null; return; }
    // Built once per test; four times a second only the parts that read differently are rewritten.
    // Rebuilding it all lost focus on Next, snapped All steps shut and replaced the live region.
    if (!box._ww || box._ww.wig !== wig) {
      box.innerHTML = `<div data-ww="head"></div>
        <div class="wiggle-step" data-ww="card" aria-live="polite"></div>
        <div class="row" data-ww="buttons"><button class="btn" id="ww-back" data-tip="wiring.wiggle-back">◂ Back</button>
          <button class="btn primary" id="ww-next" data-tip="wiring.wiggle-next"></button>
          <button class="btn" id="ww-stop" data-tip="wiring.wiggle-stop">Stop</button></div>
        <details data-ww="all"><summary class="small">All steps</summary><ol class="small wiggle-list" data-ww="list"></ol></details>`;
      box._ww = { wig, html: {} };
      const q = id => $(id, box);
      q("#ww-back").onclick = () => { if (wig.i > 0) { wig.i--; paintWiggle(); } };
      q("#ww-next").onclick = () => {
        if (wig.i + 1 < wig.steps.length) { wig.i++; wig.last = null; paintWiggle(); return; }
        finishWiggle(true);
      };
      q("#ww-stop").onclick = () => finishWiggle(false);
    }
    const part = k => $(`[data-ww="${k}"]`, box);
    const set = (k, html) => { if (box._ww.html[k] !== html) { box._ww.html[k] = html; part(k).innerHTML = html; } };
    const s = wig.steps[wig.i], ev = wig.events[wig.i] || [];
    const done = wig.done;
    if (done) {
      const F = wiggleFindings();
      set("head", F.length ? `<p><b>${F.length} place${F.length > 1 ? "s" : ""} to fix</b>, marked on the map above.</p>`
        : `<p><b>Nothing moved anything.</b> If the fault still happens on the field, it may need the robot moving: try a practice match and the Match logs summary.</p>`);
    } else {
      set("head", `${wig.practice ? `<div class="callout info">Practice: a made-up robot with one loose CAN plug and one loose power lead. Find them.</div>` : ""}
        ${data.map.buses.every(b => b.orderConfirmed) ? "" : `<div class="callout warn">The CAN order in the map has not been checked on the robot, and these steps follow it. Check it first (Edit the map), so each step names the cable you are holding.</div>`}`);
      set("card", `<div class="small muted">Step ${wig.i + 1} of ${wig.steps.length}</div>
        <div class="wiggle-text">${s.text}</div>
        <div class="small">${ev.length ? `<b>Seen during this step:</b> ${esc(summarize(ev).join("; "))}` : "Nothing seen yet. Keep wiggling for a few seconds."}</div>
        ${wig.note ? `<div class="small warn-text">${esc(wig.note)}</div>` : ""}`);
      part("card").classList.toggle("hot", Date.now() - wig.flash < 1500);
      $("#ww-back", box).disabled = wig.i === 0;
      $("#ww-next", box).textContent = wig.i + 1 < wig.steps.length ? "Next ▸" : "Finish";
    }
    part("card").hidden = done;
    part("buttons").hidden = done;
    if (done && !box._ww.opened) { box._ww.opened = true; part("all").open = true; }
    set("list", wig.steps.map((x, i) => {
      const e = wig.events[i] || [];
      return `<li class="${i === wig.i && !done ? "current" : ""}"><span class="chip ${e.length ? "warn" : i < wig.i || done ? "good" : ""}">${e.length ? "trouble" : i < wig.i || done ? "quiet" : "to do"}</span> ${x.text}</li>`;
    }).join(""));
  }

  function finishWiggle(completed) {
    stopWiggle();
    wig.done = true;
    extra = wiggleFindings();
    // Only a test that went through every step, watching a live robot, counts; Stop counts nothing.
    if (!wig.practice && completed && wig.live) {
      const bad = extra.find(f => f.level === "error" || f.level === "warn");
      HowTo.mark("wiring", "wire_wiggle", !bad, bad ? bad.title : "Nothing dropped when a plug moved.");
    }
    paintWiggle();
    paint();
  }

  // ---------------------------------------------------------------- controls
  $("#w-edit", root).onclick = () => { if (data) openEditor(); };
  $("#wf-pulse", root).onclick = findByPulse;
  $("#wf-log", root).onclick = chooseLog;
  $("#wf-practice", root).onclick = async () => { $("#wf-logs", root).innerHTML = ""; showFound(await App.api("/api/wiring/pdhfind?practice=1"), "pulse"); };
  $("#ww-start", root).onclick = () => startWiggle(false);
  $("#ww-practice", root).onclick = () => startWiggle(true);
  $("#w-demo", root).onchange = e => { demo = e.target.value; logAt = null; refresh(); };
  $("#w-ohms-go", root).onclick = async () => {
    const v = await App.api("/api/wiring/termination", { ohms: $("#w-ohms", root).value });
    $("#w-ohms-out", root).innerHTML = `<div class="finding"><div class="head"><span class="level ${v.level}">${v.level}</span><span class="title">${esc(v.title)}</span></div><div class="why">${Learn.link(v.why, 3)}</div></div>`;
    if (v.level !== "info") HowTo.mark("wiring", "wire_ohms", v.level === "ok", v.title);
  };

  App.on("tab", async t => {
    clearInterval(timer);
    if (t !== "wiring") { if (wig && !wig.done) { stopWiggle(); wig = null; paintWiggle(); } return; }
    if (!ohmsDrawn) {
      ohmsDrawn = true;
      FrcMap.render($("#w-ohms-map", root), { view: "can", wires: "can", alt: "Where the CAN bus is terminated and where to measure it",
        focus: [{ part: "rio_can", state: "here", label: "One end: the roboRIO, 120 Ω inside" },
          { part: "pdh_can", state: "here", label: "Probe CAN-H and CAN-L at any free plug" },
          { part: "pdh_term", state: "here", label: "The other end: TERM ON" }] });
    }
    await refresh();
    if (data && data.demos && $("#w-demo", root).options.length === 1) {
      $("#w-demo", root).innerHTML = `<option value="">Live robot</option>` +
        Object.entries(data.demos).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
    }
    timer = setInterval(refresh, 1000);
  });
  window.addEventListener("resize", () => { if (data && root.classList.contains("on")) paint(); });
  return {
    /** Shows the map as it was at a moment in a match log. */
    showLog(path, t) { logAt = { path, t }; App.show("wiring"); },
  };
})();
