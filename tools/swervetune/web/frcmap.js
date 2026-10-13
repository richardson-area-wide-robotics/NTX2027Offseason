// The robot drawn as FIRST draws it: WPILib's "FRC Control System - REV" layout (img/, CC BY 4.0,
// credited under every view), modified as it is shown. A view crops to one area, dims the parts
// these robots don't use (pneumatics, Talon SRX, Koors, Krakens, the servo), dims everything but the
// parts a check is about, outlines and labels those, and can brighten the CAN wiring.
//
// The art is inlined (so the CAN wires can be lifted above the dimming) once per view; a refresh
// redraws only the labels on top.
"use strict";

const FrcMap = (() => {
  const SRC = "img/frc-control-system-layout-rev.svg";
  const NS = "http://www.w3.org/2000/svg";
  let art = null, n = 0;

  // Where each part sits, in the drawing's own units (its viewBox is 2592 x 1728).
  const P = {
    rio: [225, 474, 511, 504], rio_can: [235, 509, 54, 54], rio_power: [308, 484, 43, 70], rio_spi: [615, 484, 38, 78],
    rio_ethernet: [526, 486, 62, 66], rio_leds: [671, 523, 68, 122], rio_rsl: [329, 941, 31, 26],
    radio: [524, 117, 448, 209], radio_power: [962, 148, 26, 40], rsl: [122, 121, 115, 193],
    pdh: [1612, 102, 458, 926], pdh_can: [1720, 952, 64, 76], pdh_term: [1785, 954, 33, 71],
    pdh_battery: [1888, 899, 119, 148], pdh_display: [1804, 813, 105, 66],
    sparkmax: [1194, 113, 272, 136], sparkflex: [2199, 89, 316, 209],
    breaker: [2216, 1013, 264, 173], battery: [2189, 1262, 270, 50],
  };
  const LEFT = [[162, 222], [223, 282], [284, 343], [346, 405], [407, 466], [481, 542], [545, 604], [606, 665], [667, 726], [728, 788]];
  const RIGHT = [[726, 786], [665, 725], [604, 664], [543, 603], [481, 541], [404, 464], [343, 403], [282, 342], [221, 281], [160, 220]];
  for (let i = 0; i < 10; i++) {
    P["pdh_" + i] = [1859, RIGHT[i][0], 216, RIGHT[i][1] - RIGHT[i][0]];
    P["pdh_" + (10 + i)] = [1604, LEFT[i][0], 219, LEFT[i][1] - LEFT[i][0]];
  }
  [[809, 838], [838, 867], [867, 895], [895, 924]].forEach(([a, b], i) => { P["pdh_" + (20 + i)] = [1604, a, 183, b - a]; });

  // Parts these robots don't use. Pneumatics: last used in 2022, and off the final robot.
  const NOT_OURS = [
    { r: [851, 981, 566, 458], label: "Pneumatics: not on our robots" }, { r: [1417, 1111, 715, 328] },
    { r: [1186, 326, 296, 178], label: "Talon SRX: not ours" }, { r: [1186, 542, 330, 212], label: "Koors 40: not ours" },
    { r: [2195, 366, 304, 194], label: "Kraken: not ours" }, { r: [2195, 606, 304, 240], label: "Kraken: not ours" },
    { r: [782, 632, 309, 271], label: "Servo" },
  ];

  const VIEWS = {
    all: [0, 0, 2592, 1728], pdh: [1580, 80, 530, 980], controllers: [1170, 70, 1360, 990],
    can: [60, 60, 2490, 1000], power: [1560, 60, 990, 1300], rio: [200, 440, 580, 560], radio: [80, 80, 940, 300],
  };
  const COLOR = { bad: "#c62828", warn: "#b26a00", ok: "#2e7d32", info: "#0b6e7a", here: "#0b6e7a" };

  async function load() {
    if (!art) {
      const t = await (await fetch(SRC)).text();
      art = t.slice(t.indexOf(">", t.indexOf("<svg")) + 1, t.lastIndexOf("</svg>"));
    }
    return art;
  }

  /** The device kind, from a controller's model or YAGSL type: "sparkmax" or "sparkflex". */
  function kind(model) {
    const m = String(model || "").toLowerCase();
    return m.includes("flex") ? "sparkflex" : m.includes("max") || m.includes("neo") ? "sparkmax" : null;
  }

  /**
   * Shows a view in ``el``: ``{view, focus: [{part, state, label}], wires: "can", caption, alt}``.
   * Calling it again with the same view only redraws the labels.
   */
  async function render(el, opts) {
    const view = VIEWS[opts.view] ? opts.view : "all";
    if (!el._frc || el._frc.view !== view) {
      const src = await load();
      const k = ++n;
      const inner = src.replace(/id="([^"]+)"/g, `id="$1-f${k}"`).replace(/url\(#([^)]+)\)/g, `url(#$1-f${k})`);
      const vb = VIEWS[view];
      el.innerHTML = `<figure class="frcmap"><svg viewBox="${vb.join(" ")}" role="img" aria-label="${esc(opts.alt || "The robot's control system, as FIRST draws it")}">
        <g class="frc-art">${inner}</g><g class="frc-over"></g></svg>
        <figcaption class="small muted">From <a href="https://docs.wpilib.org/en/stable/docs/controls-overviews/control-system-hardware.html" target="_blank" rel="noopener">FRC Control System - REV</a>
          by Team 3161 for WPILib, <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>: cropped, dimmed and labeled by this tool.${opts.caption ? " " + esc(opts.caption) : ""}</figcaption></figure>`;
      el._frc = { view, k };
    }
    overlay(el, opts);
  }

  function overlay(el, opts) {
    const svg = el.querySelector("svg"), g = el.querySelector(".frc-over");
    if (!svg || !g) return;
    const vb = VIEWS[el._frc.view], unit = vb[2] / 100, k = el._frc.k;
    // Several devices of one kind share one drawing: one outline, the worst state, and their names
    // as "SPARK Flex: a, b, c +2 more" (a part with a group says which kind it is).
    const rank = { bad: 3, warn: 2, here: 1, info: 1, ok: 0 }, merged = {};
    for (const f of (opts.focus || []).filter(x => P[x.part] || x.rect)) {
      const key = f.part || f.rect.join(",");
      const m = merged[key] || (merged[key] = Object.assign({}, f, { all: [] }));
      if ((rank[f.state] || 0) > (rank[m.state] || 0)) m.state = f.state;
      if (f.label && !m.all.includes(f.name || f.label)) m.all.push(f.name || f.label);
    }
    const focus = Object.values(merged).map(m => m.all.length > 1
      ? Object.assign(m, { label: `${m.group ? m.group + ": " : ""}${m.all.slice(0, 3).join(", ")}${m.all.length > 3 ? ` +${m.all.length - 3} more` : ""}` })
      : m);
    let h = NOT_OURS.map(d => `<rect x="${d.r[0]}" y="${d.r[1]}" width="${d.r[2]}" height="${d.r[3]}" class="frc-notours"/>`
      + (d.label ? `<text x="${d.r[0] + d.r[2] / 2}" y="${d.r[1] + d.r[3] / 2}" class="frc-notours-t" style="font-size:${Math.max(16, unit * 1.6)}px">${esc(d.label)}</text>` : "")).join("");
    if (focus.length) {
      // Everything but the parts in question fades back.
      h += `<mask id="frcm-${k}"><rect x="0" y="0" width="2592" height="1728" fill="#fff"/>${focus.map(f => {
        const r = f.rect || P[f.part]; return `<rect x="${r[0] - 6}" y="${r[1] - 6}" width="${r[2] + 12}" height="${r[3] + 12}" rx="10" fill="#000"/>`; }).join("")}</mask>
        <rect x="0" y="0" width="2592" height="1728" class="frc-dim" mask="url(#frcm-${k})"/>`;
    }
    g.innerHTML = h;
    // The CAN pair, lifted above the dimming and brightened.
    if (opts.wires === "can") {
      el.querySelectorAll(".frc-art [style*='stroke: #d6dc27'], .frc-art [style*='stroke: #37b04a']").forEach(w => {
        const c = w.cloneNode(true);
        c.classList.add("frc-can");
        g.appendChild(c);
      });
    }
    const sw = Math.max(3, unit * 0.45), fs = Math.max(14, unit * 2.1), placed = [];
    for (const f of focus) {
      const r = f.rect || P[f.part], col = COLOR[f.state] || COLOR.here;
      const box = document.createElementNS(NS, "rect");
      [["x", r[0] - 4], ["y", r[1] - 4], ["width", r[2] + 8], ["height", r[3] + 8], ["rx", 8]].forEach(([a, v]) => box.setAttribute(a, v));
      box.setAttribute("class", "frc-ring");
      box.setAttribute("style", `stroke:${col};stroke-width:${sw}px`);
      g.appendChild(box);
      if (f.label) {
        const t = document.createElementNS(NS, "text");
        t.setAttribute("class", "frc-tag");
        t.setAttribute("style", `font-size:${fs}px;fill:#fff`);
        t.textContent = f.label;
        g.appendChild(t);
        // Its width: measured, or (a view drawn while its tab is hidden measures nothing) guessed.
        t.setAttribute("x", 0); t.setAttribute("y", 0);
        const tw = t.getBBox().width || f.label.length * fs * 0.56, pad = fs * 0.3, lh = fs * 1.5;
        // Centered on the part, kept inside the view.
        const cx = Math.min(Math.max(r[0] + r[2] / 2, vb[0] + tw / 2 + pad * 2), vb[0] + vb[2] - tw / 2 - pad * 2);
        // Above the part (below it near the top), stepped away from any tag already placed.
        const ok = y => y - fs > vb[1] && y + fs * 0.4 < vb[1] + vb[3]
          && !placed.some(q => Math.abs(q.y - y) < lh && Math.abs(q.x - cx) < (q.w + tw) / 2 + pad * 2);
        const tries = [];
        for (let i = 0; i < 6; i++) tries.push(r[1] - fs * 0.55 - i * lh, r[1] + r[3] + fs * 1.15 + i * lh);
        const y = tries.find(ok) ?? tries[0];
        placed.push({ x: cx, y, w: tw });
        t.setAttribute("x", cx); t.setAttribute("y", y);
        const bg = document.createElementNS(NS, "rect");
        [["x", cx - tw / 2 - pad], ["y", y - fs * 0.95], ["width", tw + 2 * pad], ["height", fs * 1.3], ["rx", fs * 0.3]].forEach(([a, v]) => bg.setAttribute(a, v));
        bg.setAttribute("style", `fill:${col}`);
        g.insertBefore(bg, t);
      }
    }
  }

  // Small pictures of one part, for places that repaint often (the Wiring schematic, every second):
  // drawn once onto a canvas from the same file, then reused as a bitmap.
  const THUMB = { rio: P.rio, pdh_top: [1612, 102, 458, 300], sparkmax: P.sparkmax, sparkflex: [2199, 89, 316, 178],
                  radio: P.radio, breaker: P.breaker };
  const thumbs = {}, pending = {};
  let sheet = null;

  function thumbCached(part) { return thumbs[part] || null; }

  // The whole drawing on one canvas, once: Chrome won't cut a source rectangle out of an SVG
  // image reliably (only the top-left part came out), but it will out of a bitmap.
  async function drawSheet() {
    if (!sheet) {
      sheet = (async () => {
        const img = new Image();
        img.src = SRC;
        await img.decode();
        const c = document.createElement("canvas");
        c.width = 2592; c.height = 1728;
        c.getContext("2d").drawImage(img, 0, 0, 2592, 1728);
        return c;
      })();
    }
    return sheet;
  }

  function thumb(part, px = 120) {
    if (thumbs[part] || pending[part] || !THUMB[part]) return pending[part] || Promise.resolve(thumbs[part] || null);
    pending[part] = (async () => {
      const big = await drawSheet(), [x, y, w, h] = THUMB[part];
      const c = document.createElement("canvas");
      c.width = px * 2; c.height = Math.round(px * 2 * h / w);
      c.getContext("2d").drawImage(big, x, y, w, h, 0, 0, c.width, c.height);
      thumbs[part] = c.toDataURL("image/png");
      return thumbs[part];
    })().catch(() => null);
    return pending[part];
  }

  /** A device's parts: its controller drawing and, when known, its PDH port. */
  function deviceFocus(name, model, port, state, extra) {
    const out = [];
    const kd = kind(model);
    const kn = kd === "sparkflex" ? "SPARK Flex" : "SPARK MAX";
    if (kd) out.push({ part: kd, state, name, group: kn, label: `${name}: a ${kn}${extra ? " · " + extra : ""}` });
    if (Number.isInteger(port)) out.push({ part: "pdh_" + port, state, name, label: `PDH ${port}: ${name}` });
    return out;
  }

  return { render, kind, deviceFocus, thumb, thumbCached, PARTS: P, VIEWS };
})();
