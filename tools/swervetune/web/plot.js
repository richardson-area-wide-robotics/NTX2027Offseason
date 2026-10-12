// Small canvas plotter: lines and points against a shared x axis, theme-aware, no libraries.
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

  return { draw };
})();
