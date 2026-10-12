// Config tab: what the files say, what the physics says, and what does not add up.
"use strict";

(() => {
  const root = $("#tab-config");

  function paint(L) {
    if (!L || L.ok === false) {
      root.innerHTML = `<div class="empty">${esc((L && L.error) || "Pick a robot project at the top.")}</div>`;
      return;
    }
    const s = L.summary, F = L.findings || [];
    const mods = Object.entries(L.modules || {});
    root.innerHTML = `<div class="grid2">
      <div class="stack">
        <div class="panel"><h2>${esc(L.project)} <span class="muted small">team ${esc(s.team)}</span></h2>
          <table class="t"><tbody>
            <tr><td>Drive</td><td>${esc(s.drive_motor)} at ${s.drive_gear}:1 on ${s.wheel_diameter_in} in wheels</td></tr>
            <tr><td>Steering</td><td>${esc(s.steer_motor)} at ${s.steer_gear}:1</td></tr>
            <tr><td>Module top speed</td><td class="mono">${fmt(s.max_module_speed_mps, 2)} m/s (from motor free speed)</td></tr>
            <tr><td>Speed given to YAGSL</td><td class="mono">${s.create_swerve_max_speed.value == null ? "?" : s.create_swerve_max_speed.value} m/s <span class="muted">(${esc(s.create_swerve_max_speed.literal || "")})</span></td></tr>
            <tr><td>Nominal kV</td><td class="mono">${fmt(s.kv_nominal, 3)} V per m/s</td></tr>
            <tr><td>Wheels slip at</td><td class="mono">${fmt(s.traction_current_a, 0)} A per motor <span class="muted">(${fmt(s.mass_kg, 0)} kg, ${esc(s.mass_source)})</span></td></tr>
            <tr><td>Current limits</td><td class="mono">drive ${esc((s.current_limit || {}).drive)} A · steer ${esc((s.current_limit || {}).angle)} A</td></tr>
            <tr><td>Ramp rates</td><td class="mono">drive ${esc((s.ramp || {}).drive)} s · steer ${esc((s.ramp || {}).angle)} s</td></tr>
            <tr><td>Libraries</td><td class="small">${Object.entries(s.vendordeps || {}).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(" · ")}</td></tr>
          </tbody></table></div>
        <div class="panel"><h3>Modules</h3><div class="tblwrap"><table class="t">
          <tr><th>Module</th><th>Drive ID</th><th>Steer ID</th><th>Offset</th><th>Drive inv.</th><th>Steer inv.</th><th>Abs. inv.</th><th>Front, left (in)</th></tr>
          ${mods.map(([n, m]) => `<tr><td>${abbr(n)}</td><td class="num">${m.drive.id}</td><td class="num">${m.angle.id}</td>
            <td class="num">${m.absoluteEncoderOffset}</td><td>${m.inverted.drive}</td><td>${m.inverted.angle}</td><td>${m.absoluteEncoderInverted}</td>
            <td class="num">${m.location.front}, ${m.location.left}</td></tr>`).join("")}
        </table></div></div>
        <div class="panel"><h3>Gains in the files</h3><table class="t">
          <tr><th></th><th>p</th><th>i</th><th>d</th><th>iz</th><th>f</th></tr>
          ${["angle", "drive"].map(k => { const p = (L.pidf || {})[k] || {}; return `<tr><td>${k === "angle" ? "Steering" : "Drive"}</td>
            <td class="num">${p.p}</td><td class="num">${p.i}</td><td class="num">${p.d}</td><td class="num">${p.iz}</td><td class="num">${p.f}</td></tr>`; }).join("")}
        </table><p class="hint">Units are the SPARK's: output (duty cycle) per degree for steering, per m/s for drive; d is per 1 ms controller step. YAGSL never sends f to a SPARK.</p></div>
      </div>
      <div class="panel"><h2>What does not add up</h2>
        <div>${F.length ? F.map((f, i) => `<div class="finding">
          <div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
          <div class="why">${esc(f.why)}</div>
          ${f.fix && f.fix.kind === "edit" ? `<div class="row"><button class="btn small" data-fix="${i}">Preview the fix</button><span class="small muted">${esc(f.fix.file)}: ${esc(f.fix.path.join("."))} = ${esc(JSON.stringify(f.fix.value))}</span></div>` : ""}
          ${f.fix && f.fix.kind === "manual" && f.fix.instruction ? `<div class="small mono">${esc(f.fix.file)}: ${esc(f.fix.instruction)}</div>` : ""}
          ${f.fix && f.fix.kind === "guide" ? `<div class="row"><button class="btn small" data-guide="1">Open the guide</button></div>` : ""}
          ${f.fix && f.fix.kind === "tune" ? `<div class="row"><button class="btn small" data-tune="${esc(f.fix.loop)}">Open the tuner</button></div>` : ""}
        </div>`).join("") : `<span class="level ok">ok</span> Nothing found.`}</div></div>
    </div>`;
    $$("[data-fix]", root).forEach(b => b.onclick = () => {
      const f = F[+b.dataset.fix].fix;
      App.previewAndSave({ kind: "edit", file: f.file, path: f.path, value: f.value }, "Fix: " + F[+b.dataset.fix].title);
    });
    $$("[data-guide]", root).forEach(b => b.onclick = () => App.show("guide"));
    $$("[data-tune]", root).forEach(b => b.onclick = () => Tune.open(b.dataset.tune, { target: "robot" }));
  }

  App.on("lint", paint);
  App.on("saved", async () => { App.lint = await App.api("/api/lint"); App.emit("lint", App.lint); });
})();
