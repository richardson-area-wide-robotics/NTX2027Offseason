// Small canvas plotter: lines and points against a shared x axis, theme-aware, no libraries.
// Annotations (shaded spans, bands, markers, brackets) carry a lesson key and a sentence about
// that moment; hovering one teaches it (see learn.js). A cursor shows a readout at any time.
"use strict";

const Plot = (() => {
  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
  }

  // "Nice" tick step for a range, so axes read 0, 0.2, 0.4 rather than 0, 0.173, 0.346.
  function niceStep(range, target) {
    const raw = range / Math.max(1, target);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const n = raw / mag;
    return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
  }

  function extent(series, key, lo, hi) {
    let min = Infinity, max = -Infinity;
    for (const s of series) {
      const xs = s.x, vs = s[key];
      for (let i = 0; i < vs.length; i++) {
        const v = vs[i];
        if (v == null || !isFinite(v)) continue;
        if (key === "y" && (xs[i] < lo || xs[i] > hi)) continue;
        if (v < min) min = v;
        if (v > max) max = v;
      }
    }
    if (!isFinite(min)) return [0, 1];
    if (min === max) { min -= 1; max += 1; }
    return [min, max];
  }

  function draw(canvas, opts) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    const g = canvas.getContext("2d");
    g.scale(dpr, dpr);
    g.clearRect(0, 0, w, h);
    const series = (opts.series || []).filter(s => s && s.x && s.x.length);
    const ink = css("--ink"), muted = css("--muted"), grid = css("--grid");
    g.font = "11px " + css("--mono");
    if (!series.length) {
      g.fillStyle = muted;
      g.fillText(opts.empty || "No data yet", 16, 24);
      canvas._plot = null;
      return;
    }
    let [x0, x1] = opts.xrange || extent(series, "x");
    let [y0, y1] = opts.yrange || extent(series, "y", x0, x1);
    const pad = (y1 - y0) * 0.08;
    y0 -= pad; y1 += pad;
    const L = 54, R = 12, T = 12, B = 30;
    const pw = w - L - R, ph = h - T - B;
    const X = x => L + (x - x0) / (x1 - x0) * pw;
    const Y = y => T + (1 - (y - y0) / (y1 - y0)) * ph;

    // grid and axes
    g.strokeStyle = grid; g.lineWidth = 1; g.fillStyle = muted;
    const xs = niceStep(x1 - x0, Math.max(4, pw / 90));
    for (let v = Math.ceil(x0 / xs) * xs; v <= x1 + 1e-9; v += xs) {
      g.beginPath(); g.moveTo(X(v), T); g.lineTo(X(v), T + ph); g.stroke();
      const label = +v.toFixed(6);
      g.fillText(String(label), X(v) - 8, T + ph + 16);
    }
    const ys = niceStep(y1 - y0, Math.max(3, ph / 50));
    for (let v = Math.ceil(y0 / ys) * ys; v <= y1 + 1e-9; v += ys) {
      g.beginPath(); g.moveTo(L, Y(v)); g.lineTo(L + pw, Y(v)); g.stroke();
      const label = +v.toFixed(6);
      g.fillText(String(label), 4, Y(v) + 4);
    }
    g.fillStyle = muted;
    if (opts.xlabel) g.fillText(opts.xlabel, L + pw - g.measureText(opts.xlabel).width, h - 4);
    if (opts.ylabel) g.fillText(opts.ylabel, L + 4, T + 10);

    const hits = [];
    const notes = opts.annotations || [];
    g.save();
    g.beginPath(); g.rect(L, T, pw, ph); g.clip();
    // Areas behind the data.
    for (const a of notes) {
      if (a.type !== "vspan" && a.type !== "band") continue;
      const col = css(TONE[a.learn] || "--info");
      const xa = X(a.x0), xb = Math.max(X(a.x1), xa + 2);
      g.globalAlpha = a.type === "band" ? 0.10 : 0.16;
      g.fillStyle = col;
      if (a.type === "vspan") {
        g.fillRect(xa, T, xb - xa, ph);
        hits.push({ a, rank: 3, x: xa, y: T, w: xb - xa, h: ph });
      } else {
        const ya = Y(a.y1), yb = Y(a.y0);
        g.fillRect(xa, ya, xb - xa, yb - ya);
        hits.push({ a, rank: 4, x: xa, y: ya, w: xb - xa, h: Math.max(4, yb - ya) });
      }
      g.globalAlpha = 1;
      if (a.label && a.type === "vspan") {
        g.fillStyle = col;
        g.fillText(a.label, xa + 3, T + ph - 6);
      }
    }
    g.restore();

    // data
    g.save();
    g.beginPath(); g.rect(L, T, pw, ph); g.clip();
    for (const s of series) {
      const color = s.color && s.color.startsWith("--") ? css(s.color) : (s.color || ink);
      g.strokeStyle = color; g.fillStyle = color;
      g.globalAlpha = s.alpha == null ? 1 : s.alpha;
      if (s.points) {
        for (let i = 0; i < s.x.length; i++) {
          const v = s.y[i];
          if (v == null || !isFinite(v)) continue;
          g.fillRect(X(s.x[i]) - 1, Y(v) - 1, 2.2, 2.2);
        }
        continue;
      }
      g.lineWidth = s.width || 1.6;
      g.setLineDash(s.dash || []);
      g.beginPath();
      let pen = false;
      for (let i = 0; i < s.x.length; i++) {
        const v = s.y[i];
        if (v == null || !isFinite(v)) { pen = false; continue; }
        const px = X(s.x[i]), py = Y(v);
        if (pen) g.lineTo(px, py); else g.moveTo(px, py);
        pen = true;
      }
      g.stroke();
    }
    g.restore();
    g.setLineDash([]);
    g.globalAlpha = 1;

    // Markers on top of the data. Labels step down until they clear the ones already drawn.
    const placed = [];
    const labelAt = (text, x, y) => {
      const w = g.measureText(text).width;
      let yy = y;
      for (let k = 0; k < 5 && placed.some(r => x < r.x + r.w && x + w > r.x && Math.abs(yy - r.y) < 12); k++) yy += 13;
      placed.push({ x, y: yy, w });
      g.fillText(text, x, yy);
    };
    for (const a of notes) {
      const col = css(TONE[a.learn] || "--ink");
      g.strokeStyle = col; g.fillStyle = col; g.lineWidth = 1.5;
      if (a.type === "point" && isFinite(a.t) && isFinite(a.y)) {
        const px = X(a.t), py = Y(a.y);
        if (px < L || px > L + pw) continue;
        g.beginPath(); g.arc(px, py, 5, 0, Math.PI * 2); g.stroke();
        g.beginPath(); g.arc(px, py, 2, 0, Math.PI * 2); g.fill();
        if (a.label) labelAt(a.label, px + 7, py - 6);
        hits.push({ a, rank: 0, x: px - 9, y: py - 9, w: 18, h: 18 });
      } else if (a.type === "rise" && isFinite(a.y0) && isFinite(a.y1)) {
        const xa = X(a.x0), xb = X(a.x1), ya = Y(a.y0), yb = Y(a.y1);
        g.beginPath(); g.arc(xa, ya, 3.5, 0, Math.PI * 2); g.stroke();
        g.beginPath(); g.arc(xb, yb, 3.5, 0, Math.PI * 2); g.stroke();
        const yr = T + ph - 14;
        g.setLineDash([3, 3]);
        g.beginPath(); g.moveTo(xa, ya); g.lineTo(xa, yr); g.moveTo(xb, yb); g.lineTo(xb, yr); g.stroke();
        g.setLineDash([]);
        g.beginPath(); g.moveTo(xa, yr); g.lineTo(xb, yr); g.stroke();
        g.fillText(a.label || "rise", xa + 2, yr - 3);
        hits.push({ a, rank: 1, x: xa - 4, y: Math.min(ya, yb) - 4, w: xb - xa + 8, h: yr - Math.min(ya, yb) + 8 });
      } else if (a.type === "bracket" && isFinite(a.y0) && isFinite(a.y1)) {
        const px = X(a.t) - 6, ya = Y(a.y0), yb = Y(a.y1);
        g.beginPath(); g.moveTo(px - 4, ya); g.lineTo(px, ya); g.lineTo(px, yb); g.lineTo(px - 4, yb); g.stroke();
        g.fillText(a.label || "left", px - 4 - g.measureText(a.label || "left").width, (ya + yb) / 2 + 4);
        hits.push({ a, rank: 0, x: px - 40, y: Math.min(ya, yb) - 6, w: 46, h: Math.abs(yb - ya) + 12 });
      }
    }
    g.lineWidth = 1;
    canvas._plot = { X, Y, x0, x1, y0, y1, L, T, pw, ph, hits: hits.sort((p, q) => p.rank - q.rank) };
    canvas._opts = opts;
    wire(canvas);

    // legend
    let lx = L + 8;
    const ly = T + 14;
    for (const s of series) {
      if (!s.label) continue;
      const color = s.color && s.color.startsWith("--") ? css(s.color) : (s.color || ink);
      g.fillStyle = color;
      g.fillRect(lx, ly - 7, 12, 3);
      g.fillStyle = ink;
      g.fillText(s.label, lx + 16, ly - 2);
      lx += 26 + g.measureText(s.label).width;
      if (lx > L + pw - 60) break;
    }
  }

  // Lesson colors: red for flat out, amber for limits and ringing, green for good, blue otherwise.
  const TONE = { saturation: "--bad", current_limit: "--warn", oscillation: "--warn", overshoot: "--warn",
                 steady_state_error: "--bad", dead_time: "--info", feedforward: "--ok", settling_time: "--ok",
                 rise_time: "--accent", kP: "--s0", kD: "--s2", kI: "--s3", ramp_rate: "--warn" };

  // Hover: teach the annotation under the pointer; otherwise move the cursor and its readout.
  function wire(canvas) {
    if (canvas._wired) return;
    canvas._wired = true;
    const wrap = canvas.parentElement;
    let line = null, box = null;
    if (wrap && wrap.classList.contains("plotwrap")) {
      line = document.createElement("div"); line.className = "plot-cursor"; line.hidden = true; wrap.appendChild(line);
      box = document.createElement("div"); box.className = "plot-readout"; box.hidden = true; wrap.appendChild(box);
    }
    let teaching = false;
    canvas.addEventListener("mousemove", e => {
      const P = canvas._plot, o = canvas._opts || {};
      if (!P) return;
      const r = canvas.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      const hit = P.hits.find(h => mx >= h.x && mx <= h.x + h.w && my >= h.y && my <= h.y + h.h && h.rank !== 4)
        || P.hits.find(h => mx >= h.x && mx <= h.x + h.w && my >= h.y && my <= h.y + h.h);
      if (hit && (typeof Learn !== "undefined")) { Learn.showAt(hit.a.learn, e.clientX, e.clientY, hit.a.text); teaching = true; }
      else if (teaching && (typeof Learn !== "undefined")) { Learn.hide(); teaching = false; }
      if (!line || mx < P.L || mx > P.L + P.pw) { if (line) { line.hidden = true; box.hidden = true; } return; }
      const xv = P.x0 + (mx - P.L) / P.pw * (P.x1 - P.x0);
      line.hidden = false;
      line.style.left = mx + "px"; line.style.top = P.T + "px"; line.style.height = P.ph + "px";
      const html = o.readout ? o.readout(xv) : "";
      box.hidden = !html || !!hit;
      if (html) {
        box.innerHTML = html;
        const right = mx > P.L + P.pw * 0.6;
        box.style.left = right ? "" : (mx + 10) + "px";
        box.style.right = right ? (canvas.clientWidth - mx + 10) + "px" : "";
        box.style.top = (P.T + 4) + "px";
      }
    });
    canvas.addEventListener("mouseleave", () => {
      if (line) { line.hidden = true; box.hidden = true; }
      if (teaching && (typeof Learn !== "undefined")) { Learn.hide(); teaching = false; }
    });
  }

  return { draw };
})();
