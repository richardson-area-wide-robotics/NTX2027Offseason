// Device faults where they matter: a strip in Tune and Calibrate listing the faults, now and since
// the robot code started, on the motors (and the gyro) the job in hand depends on. A steering test
// on a module whose steer encoder reports a sensor fault measures the fault, not the gains.
"use strict";

const Faults = (() => {
  const MOD = { FL: ["front", "left"], FR: ["front", "right"], BL: ["back", "left"], BR: ["back", "right"] };
  const strips = [];

  // A swerve motor's name is "<module> drive" or "<module> steer".
  function wanted(name, kind, module) {
    const m = / (drive|steer)$/.exec(name);
    if (!m) return kind === "all";
    if (kind !== "all" && kind !== "swerve" && kind !== m[1]) return false;
    const mod = MOD[module];
    return !mod || mod.every(w => name.toLowerCase().includes(w));
  }

  // What one motor has reported: broken now (red), and what happened earlier (amber).
  function lines(m, report) {
    const now = [], earlier = [];
    if (m.present === 0) now.push("off the CAN bus");
    if (m.flags) now.push(m.flags);
    if (m.history) earlier.push(m.history.replace(/^faults since last cleared: /, "faults "));
    if (m.resets > 0) earlier.push(`rebooted ${m.resets}×`);
    if (m.brownouts > 0) earlier.push(`low voltage ${m.brownouts}×`);
    if (m.dropouts > 0) earlier.push(`dropped off CAN ${m.dropouts}×`);
    const boot = (report || []).find(r => r.startsWith(m.name + " (CAN") && r.includes("since it powered on"));
    if (boot) earlier.push("before the code started: " + boot.replace(/^.*since it powered on: /, "").replace(/\.$/, ""));
    return { now, earlier };
  }

  /** The strip's HTML: {kind: "steer"|"drive"|"swerve"|"all", module: "ALL"|"FL"..., gyro, quiet, what}. */
  function html(o) {
    if (!o || (!o.kind && !o.gyro)) return "";
    const live = App.live && App.live.live;
    if (!live || !App.connected()) return "";
    const report = (App.live.motor_guard || {}).report || [];
    const items = [];
    if (o.kind) {
      for (const m of live.motors || []) {
        if (!m.name || !wanted(m.name, o.kind, o.module)) continue;
        const l = lines(m, report);
        if (l.now.length || l.earlier.length) items.push({ name: m.name, ...l });
      }
    }
    const g = live.gyro || [];
    if (o.gyro && g.length >= 2 && (g[1] !== "connected" || g[3])) {
      items.push({ name: "Gyro" + (g[0] ? ` (${g[0]})` : ""), now: [g[1] !== "connected" ? "not connected" : String(g[3])], earlier: [] });
    }
    // Quiet: nothing at all when there is nothing wrong (where the page has no room to spare).
    if (!items.length && o.quiet) return "";
    if (!items.length) return `<div class="fault-strip ok small"><span class="level ok">ok</span> No faults on ${esc(o.what)}.</div>`;
    const shown = items.slice(0, 4);
    // One run of text, not a list: it wraps to as few lines as the space allows.
    return `<div class="fault-strip small${items.some(i => i.now.length) ? " bad" : ""}" role="status">
      <b>Faults on ${esc(o.what)}</b>, which can spoil this${items.some(i => i.now.length) ? " (fix what is broken now first)" : ""}:
      ${shown.map(i => `<b>${esc(i.name)}</b>${i.now.length ? ` <span class="bad-ink">now: ${esc(i.now.join("; "))}</span>` : ""}${i.earlier.length ? ` <span class="warn-ink">earlier: ${esc(i.earlier.join("; "))}</span>` : ""}`).join(" · ")}${items.length > shown.length ? ` · <span class="muted">${items.length - shown.length} more on the Motors tab</span>` : ""}.</div>`;
  }

  /** Keeps a strip current while it shows: its options may be a function of the page's state. */
  function mount(el, opts) {
    strips.push({ el, opts });
    paintOne(strips[strips.length - 1]);
  }
  function paintOne(s) {
    if (!s.el.isConnected || !s.el.offsetParent) return;
    const h = html(typeof s.opts === "function" ? s.opts() : s.opts);
    if (s.el._h !== h) { s.el._h = h; s.el.innerHTML = h; }
  }
  // The live data comes ten times a second; a strip is rewritten only when its text changes.
  App.on("live", () => strips.forEach(paintOne));
  return { html, mount, refresh: () => strips.forEach(paintOne) };
})();
