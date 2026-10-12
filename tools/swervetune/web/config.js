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
          ${f.fix && f.fix.kind === "pathplanner" ? `<div class="row"><button class="btn small" data-pp="1">See the PathPlanner check</button></div>` : ""}
        </div>`).join("") : `<span class="level ok">ok</span> Nothing found.`}</div></div>
    </div>
    <div class="panel" id="pp-panel" style="margin-top:12px"><h2><span class="term" data-learn="pathplanner_model">PathPlanner against the code</span></h2><div id="pp-body"><p class="hint">Checking…</p></div></div>`;
    $$("[data-pp]", root).forEach(b => b.onclick = () => $("#pp-panel", root).scrollIntoView({ behavior: "smooth" }));
    paintPathPlanner();
    $$("[data-fix]", root).forEach(b => b.onclick = () => {
      const f = F[+b.dataset.fix].fix;
      App.previewAndSave({ kind: "edit", file: f.file, path: f.path, value: f.value }, "Fix: " + F[+b.dataset.fix].title);
    });
    $$("[data-guide]", root).forEach(b => b.onclick = () => App.show("guide"));
    $$("[data-tune]", root).forEach(b => b.onclick = () => Tune.open(b.dataset.tune, { target: "robot" }));
  }

  const STATUS = { ok: "good", differs: "bad", missing: "bad", unknown: "" };

  async function paintPathPlanner() {
    const box = $("#pp-body", root);
    if (!box) return;
    const r = await App.api("/api/ppcheck");
    if (r.ok === false) { box.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    if (!r.used) { box.innerHTML = `<p class="hint">This robot doesn't use PathPlanner.</p>`; return; }
    const F = r.findings || [], cap = r.capabilities || {};
    box.innerHTML = `
      <p class="small">PathPlanner keeps its own copy of the robot (<span class="mono">deploy/pathplanner/settings.json</span>), which the robot loads at boot to plan every auto. Each row is a setting PathPlanner plans with, against where the truth lives.</p>
      <div class="tblwrap"><table class="t"><thead><tr><th>Setting</th><th>PathPlanner</th><th>The code</th><th>From</th><th></th></tr></thead><tbody>
        ${(r.rows || []).map(x => `<tr><td class="mono small">${esc(x.key)}</td><td class="num mono">${esc(String(x.pathplanner ?? "–"))}</td>
          <td class="num mono">${esc(String(x.code ?? "–"))}</td><td class="small">${esc(x.source)}</td>
          <td><span class="chip ${STATUS[x.status] || ""}">${esc(x.status === "unknown" ? "measure it" : x.status)}</span></td></tr>`).join("")}
      </tbody></table></div>
      ${(r.fixes || []).length ? `<div class="row"><button class="btn primary" id="pp-fix">Make PathPlanner match the code…</button>
        <span class="small muted">Writes ${r.fixes.length} setting${r.fixes.length === 1 ? "" : "s"} in settings.json. Close the PathPlanner app first, or it writes its old values back.</span></div>` : ""}
      <p class="small muted">What this robot can do, for the path limits: ${fmt(cap.max_speed, 2)} m/s, ${fmt(cap.max_accel, 1)} m/s² (limited by ${esc(cap.accel_limited_by || "")}), turning ${fmt(cap.max_ang_vel_deg, 0)} deg/s.</p>
      ${F.map(f => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
        <div class="why">${Learn.link(f.why, 2)}</div></div>`).join("") || `<p><span class="level ok">ok</span> PathPlanner and the code agree.</p>`}`;
    const fix = $("#pp-fix", box);
    if (fix) fix.onclick = async () => {
      if (await App.previewAndSave({ kind: "pathplanner" }, "Make PathPlanner match the code")) paintPathPlanner();
    };
  }

  App.on("lint", paint);
  App.on("saved", async () => { App.lint = await App.api("/api/lint"); App.emit("lint", App.lint); });
})();
