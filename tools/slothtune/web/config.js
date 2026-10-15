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
    // PathPlanner's findings are listed in full in their own panel below, so here they get one line.
    // Errors first, then warnings, then notes: each keeps its index, so its fix button still finds it.
    const RANK = { error: 0, warn: 1, info: 2 };
    const own = F.map((f, i) => [f, i]).filter(([f]) => !String(f.id || "").startsWith("pathplanner"))
      .sort(([a], [b]) => (RANK[a.level] ?? 3) - (RANK[b.level] ?? 3));
    const pp = F.filter(f => String(f.id || "").startsWith("pathplanner"));
    const tip = (key, text) => `<span class="term" tabindex="0" data-tip="${key}" data-quiet>${esc(text)}</span>`;
    const yes = v => v === true ? "<b>yes</b>" : v === false ? "no" : esc(String(v));
    root.innerHTML = `<div class="jobs" data-jobs="config">${HowTo.slot("config")}<div class="job-area">
      <div class="stack" id="cfg-files">
        <div class="panel"><h2 data-tip="config.summary">${esc(L.project)} <span class="muted small">team ${esc(s.team)}</span></h2>
          <table class="t"><tbody>
            <tr><th scope="row"><span class="term" tabindex="0" data-tip="config.sum-drive">Drive</span></th><td>${esc(s.drive_motor)} at ${s.drive_gear}:1 on ${s.wheel_diameter_in} in wheels</td></tr>
            <tr><th scope="row"><span class="term" tabindex="0" data-tip="config.sum-steer">Steering</span></th><td>${esc(s.steer_motor)} at ${s.steer_gear}:1</td></tr>
            <tr><th scope="row"><span class="term" tabindex="0" data-tip="config.topspeed">Module top speed</span></th><td class="mono">${U.speed(s.max_module_speed_mps)} (from motor free speed)</td></tr>
            <tr><th scope="row"><span class="term" tabindex="0" data-tip="config.maxspeed">Speed given to YAGSL</span></th><td class="mono">${s.create_swerve_max_speed.value == null ? "?" : U.speed(s.create_swerve_max_speed.value)} <span class="muted">(${esc(s.create_swerve_max_speed.literal || "")})</span></td></tr>
            <tr><th scope="row"><span class="term" tabindex="0" data-tip="config.kv">Nominal kV</span></th><td class="mono">${fmt(s.kv_nominal, 3)} V per m/s <span class="muted">(the code's units)</span></td></tr>
            <tr><th scope="row"><span class="term" tabindex="0" data-tip="config.slip">Wheels slip at</span></th><td class="mono">${fmt(s.traction_current_a, 0)} A per motor <span class="muted">(${U.mass(s.mass_kg)}, ${esc(s.mass_source)})</span></td></tr>
            <tr><th scope="row"><span class="term" tabindex="0" data-tip="config.sum-limits">Current limits</span></th><td class="mono">drive ${esc((s.current_limit || {}).drive)} A · steer ${esc((s.current_limit || {}).angle)} A</td></tr>
            <tr><th scope="row"><span class="term" tabindex="0" data-tip="config.sum-ramp">Ramp rates</span></th><td class="mono">drive ${esc((s.ramp || {}).drive)} s · steer ${esc((s.ramp || {}).angle)} s</td></tr>
            <tr><th scope="row">Libraries</th><td class="small">${Object.entries(s.vendordeps || {}).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(" · ")}</td></tr>
          </tbody></table></div>
        <div class="panel"><h3 data-tip="config.modules">Modules</h3><div class="tblwrap"><table class="t">
          <tr><th>Module</th><th class="num">${tip("config.driveid", "Drive ID")}</th><th class="num">${tip("config.steerid", "Steer ID")}</th><th class="num">${tip("config.offset", "Offset")}</th>
            <th>${tip("config.driveinv", "Drive flipped")}</th><th>${tip("config.steerinv", "Steer flipped")}</th><th>${tip("config.absinv", "Abs. flipped")}</th><th class="num">${tip("config.location", "Front, left (in)")}</th></tr>
          ${mods.map(([n, m]) => `<tr><th scope="row">${abbr(n)}</th><td class="num">${m.drive.id}</td><td class="num">${m.angle.id}</td>
            <td class="num">${m.absoluteEncoderOffset}°</td><td>${yes(m.inverted.drive)}</td><td>${yes(m.inverted.angle)}</td><td>${yes(m.absoluteEncoderInverted)}</td>
            <td class="num">${m.location.front}, ${m.location.left}</td></tr>`).join("")}
        </table></div></div>
        <div class="panel"><h3 data-tip="config.gains">Gains in the files</h3><table class="t">
          <tr><th></th><th class="num">${Learn.term("kP", "kP")}</th><th class="num">${Learn.term("kI", "kI")}</th><th class="num">${Learn.term("kD", "kD")}</th><th class="num">${Learn.term("iZone", "IZone")}</th><th class="num">${Learn.term("feedforward", "FF")}</th></tr>
          ${["angle", "drive"].map(k => { const p = (L.pidf || {})[k] || {}; return `<tr><th scope="row">${k === "angle" ? "Steering" : "Drive"}</th>
            <td class="num">${p.p}</td><td class="num">${p.i}</td><td class="num">${p.d}</td><td class="num">${p.iz}</td><td class="num">${p.f}</td></tr>`; }).join("")}
        </table><p class="hint">Units are the SPARK's: output (duty cycle) per degree for steering, per m/s for drive; kD is per 1 ms controller step. YAGSL never sends FF to a SPARK: the real feedforward is measured per module in Tune drive train.</p></div>
      </div>
      <div class="panel" id="cfg-findings"><h2 data-tip="config.findings">What does not add up</h2>
        ${HowTo.steps({ steps: ["<b>Errors</b> first: each says what is wrong, why it matters, and how to fix it.",
          "<b>Preview the fix</b> shows the exact line that changes; <b>Write files</b> writes it. Redeploy, then this list checks again.",
          "<b>Warnings</b> next: read them. Most are settled by the Guide's tests, which measure what the files can only guess.",
          "<b>Open the Guide</b> or <b>Open the tuner</b> takes you to the step that settles a finding."],
          good: "no errors. Warnings may stay until the Guide's tests have run." })}
        <div class="cfg-list">${own.length ? own.map(([f, i]) => `<div class="finding" data-level="${esc(f.level)}">
          <div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
          <div class="why">${Learn.link(f.why, 3)}</div>
          ${f.fix && f.fix.kind === "edit" ? `<div class="row"><button class="btn small" data-fix="${i}" data-tip="config.fix" data-quiet>Preview the fix</button><span class="small muted">${esc(f.fix.file)}: ${esc(f.fix.path.join("."))} = ${esc(JSON.stringify(f.fix.value))}</span></div>` : ""}
          ${f.fix && f.fix.kind === "manual" && f.fix.instruction ? `<div class="small mono">${esc(f.fix.file)}: ${esc(f.fix.instruction)}</div>` : ""}
          ${f.fix && f.fix.kind === "guide" ? `<div class="row"><button class="btn small" data-guide="${esc(f.fix.step || "")}" data-tip="config.guide">Open the Guide</button></div>` : ""}
          ${f.fix && f.fix.kind === "tune" ? `<div class="row"><button class="btn small" data-tune="${esc(f.fix.loop)}" data-tip="config.tune">Open the ${esc(({ steer: "Steering", drive: "Drive speed", ff: "Feedforward", slip: "Slip current", spin: "Spin", straight: "Straight line" })[f.fix.loop] || "")} tuner</button></div>` : ""}
        </div>`).join("") : `<span class="level ok">ok</span> Nothing found in the swerve files.`}
        ${pp.length ? `<div class="finding"><div class="head"><span class="level ${pp.some(f => f.level === "error") ? "error" : "warn"}">auto</span><span class="title">${pp.length} PathPlanner item${pp.length === 1 ? "" : "s"} for whoever writes the autos</span></div>
          <div class="row"><button class="btn small" data-pp="1" data-tip="config.see-pp">See the PathPlanner check</button></div></div>` : ""}</div></div>
    <div class="panel" id="pp-panel"><h2 data-tip="config.pp">PathPlanner against the code</h2><div id="pp-body"><p class="hint">Checking…</p></div></div>
    <div class="panel" id="dl-panel"><h2 data-tip="config.designs">Mechanism designs</h2>
      ${HowTo.steps({ note: `Designed a mechanism in <a href="https://www.reca.lc/" target="_blank" rel="noopener">ReCalc</a> or
        <a href="https://ambcalc.com/" target="_blank" rel="noopener">AMBcalc</a>? The link holds the whole design: the tool reads it, attaches it to the motors it is for, and checks it against the code and the robot.`,
        steps: ["In the calculator, press Copy Link (or copy the address bar).", "Paste it into the link box and press <b>Read it</b>.",
          "Name the mechanism and tick its motors if the tool guessed wrong.", "<b>Save the design</b>; tick a number only if you want it written too."],
        good: "no errors under <b>Checked against the robot</b>. After a practice match, check the saved designs against its log." })}
      <div class="row"><label class="row small" data-tip="config.dl-url" style="flex:1">Design link
        <input id="dl-url" style="flex:1;min-width:16em" placeholder="https://www.reca.lc/arm?…  or  https://ambcalc.com/mechanism?…"></label>
        <button class="btn primary" id="dl-read" data-tip="config.dl-read">Read it</button></div>
      <div id="dl-out"></div>
      <h3 data-tip="config.dl-saved">Saved designs</h3>
      <div class="row small" id="dl-log-row"></div>
      <div id="dl-saved"><p class="hint">Checking…</p></div>
    </div></div></div>`;
    $$("[data-pp]", root).forEach(b => b.onclick = () => HowTo.go({ tab: "config", panel: "pp-panel" }));
    paintPathPlanner();
    Designs.mount();
    HowTo.paint("config");
    $$("[data-fix]", root).forEach(b => b.onclick = () => {
      const f = F[+b.dataset.fix].fix;
      App.previewAndSave({ kind: "edit", file: f.file, path: f.path, value: f.value }, "Fix: " + F[+b.dataset.fix].title);
    });
    $$("[data-guide]", root).forEach(b => b.onclick = () => b.dataset.guide ? Guide.go(b.dataset.guide) : App.show("guide"));
    $$("[data-tune]", root).forEach(b => b.onclick = () => Tune.open(b.dataset.tune, { target: "robot" }));
  }

  // Anything fine is quiet so the rows that need work stand out.
  const STATUS = { differs: "bad", missing: "bad", unknown: "warn" };
  // PathPlanner's settings.json keeps meters, m/s, kilograms and kg·m²; a row reads in the team's
  // units (the file and the fix keep PathPlanner's). Wheel radius and module places to the
  // thousandth of an inch, so two that differ never print the same.
  const PP_UNIT = [[/^driveWheelRadius$/, v => U.length(v, 3)], [/Module[XY]$/, v => U.length(v, 3)],
    [/^maxDriveSpeed$/, v => U.speed(v)], [/^robotMass$/, v => U.mass(v)], [/^robotMOI$/, v => U.inertia(v)]];
  const ppVal = (key, v) => {
    const hit = typeof v === "number" && isFinite(v) && PP_UNIT.find(([re]) => re.test(key));
    return esc(hit ? hit[1](v) : String(v ?? "–"));
  };

  async function paintPathPlanner() {
    const box = $("#pp-body", root);
    if (!box) return;
    const r = await App.api("/api/ppcheck");
    if (r.ok === false) { box.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    if (!r.used) { box.innerHTML = `<p class="hint">This robot doesn't use PathPlanner.</p>`; return; }
    const F = r.findings || [], cap = r.capabilities || {};
    box.innerHTML = `
      ${HowTo.steps({ note: "PathPlanner keeps its own copy of the robot (<span class=\"mono\">deploy/pathplanner/settings.json</span>), which the robot loads at boot to plan every auto. Each row is a setting PathPlanner plans with, against where the truth lives. The rows read in inches, ft/s and pounds; PathPlanner's own app shows the same numbers in meters and kilograms.",
        steps: ["Close the PathPlanner app first: it writes its own values back when it closes.",
          "Press <b>Make PathPlanner match the code</b> and check the diff.", "Rows marked <b>measure it</b> (mass, moment of inertia) come from Calibrate: measure them there, then come back."],
        good: "every row the same; the named commands each registered (\"Shoot B\" is kept on purpose)." })}
      <div class="pp-cols"><div class="tblwrap"><table class="t"><thead><tr><th>Setting</th><th class="num" data-tip="config.pp-pp" data-quiet>PathPlanner</th><th class="num" data-tip="config.pp-code" data-quiet>The code</th><th>From</th><th data-tip="config.pp-match" data-quiet><span class="sr">Match</span></th></tr></thead><tbody>
        ${(r.rows || []).slice().sort((a, b) => (a.status === "ok") - (b.status === "ok")).map(x => `<tr><td class="mono small">${esc(x.key)}</td><td class="num mono">${ppVal(x.key, x.pathplanner)}</td>
          <td class="num mono">${ppVal(x.key, x.code)}</td><td class="small">${esc(x.source)}</td>
          <td>${x.status === "ok" ? `<span class="muted small">✓ same</span>` : `<span class="chip ${STATUS[x.status] || ""}" ${x.status === "unknown" ? `data-tip="config.measure" data-quiet` : ""}>${esc(x.status === "unknown" ? "measure it" : x.status)}</span>`}</td></tr>`).join("")}
      </tbody></table></div><div class="stack">
      ${(r.fixes || []).length ? `<div class="row"><button class="btn primary" id="pp-fix" data-tip="config.ppfix">Make PathPlanner match the code…</button>
        <span class="small muted">Writes ${r.fixes.length} setting${r.fixes.length === 1 ? "" : "s"} in settings.json. Close the PathPlanner app first, or it writes its old values back.</span></div>` : ""}
      <p class="small muted">What this robot can do, for the path limits: ${U.speed(cap.max_speed)}, ${U.accel(cap.max_accel)} (limited by ${esc(cap.accel_limited_by || "")}), turning ${fmt(cap.max_ang_vel_deg, 0)}°/s.</p>
      ${F.map(f => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
        <div class="why">${Learn.link(f.why, 2)}</div></div>`).join("") || `<p><span class="level ok">ok</span> PathPlanner and the code agree.</p>`}</div></div>`;
    const fix = $("#pp-fix", box);
    if (fix) fix.onclick = async () => {
      if (await App.previewAndSave({ kind: "pathplanner" }, "Make PathPlanner match the code")) paintPathPlanner();
    };
  }

  // ---------------------------------------------------------------- mechanism designs
  const Designs = (() => {
    let read = null, log = "";
    const LEVEL = { error: "error", warn: "warn", info: "info", ok: "ok" };
    const findingsHtml = F => (F || []).map(f => `<div class="finding"><div class="head"><span class="level ${LEVEL[f.level] || "info"}">${esc(f.level)}</span>
      <span class="title">${esc(f.title)}</span></div><div class="why">${Learn.link(f.why, 2)}</div></div>`).join("");
    const saysHtml = rows => `<table class="t"><tbody>${(rows || []).map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${esc(v)}</td></tr>`).join("")}</tbody></table>`;

    async function mount() {
      const box = $("#dl-panel", root);
      if (!box) return;
      $("#dl-read", box).onclick = () => readLink();
      $("#dl-url", box).onkeydown = e => { if (e.key === "Enter") readLink(); };
      let folder = "";
      try { folder = localStorage.getItem("slothtune.logfolder") || ""; } catch (e) { /* storage blocked */ }
      $("#dl-log-row", box).innerHTML = folder
        ? `<button class="btn small" id="dl-log" data-tip="config.dl-log">Check against the newest match log</button> <span class="muted">from ${esc(folder)}</span>`
        : `<span class="muted">To check against what a match measured, pick a log folder on the Runs tab first.</span>`;
      const b = $("#dl-log", box);
      if (b) b.onclick = async () => {
        const r = await App.api("/api/logs?folder=" + encodeURIComponent(folder));
        if (!r.ok || !r.files.length) { App.toast(r.error || "No match logs in that folder."); return; }
        log = r.files[0].path;
        paintSaved();
      };
      paintSaved();
    }

    async function readLink(motors) {
      const box = $("#dl-out", root);
      const body = { url: $("#dl-url", root).value, mechanism: read ? $("#dl-mech", root).value : "" };
      if (motors) body.motors = motors;
      if (log) body.log = log;
      const r = await App.api("/api/designs/read", body);
      if (!r.ok) { box.innerHTML = `<div class="callout warn">${esc(r.error)}</div>`; read = null; return; }
      read = r;
      const d = r.design, mech = r.mechanism || "";
      const choices = (await App.api("/api/designs")).motors || [];
      box.innerHTML = `<div class="grid2" style="margin-top:8px">
        <div><h3>What the link says <span class="muted small">${esc(d.source)} · ${esc(d.calculator)}${d.legacy ? " · an older link" : ""}</span></h3>
          ${saysHtml(r.describe)}${(d.notes || []).map(n => `<p class="small warn-ink">${esc(n)}</p>`).join("")}</div>
        <div class="stack">
          <label class="gain" data-tip="config.dl-mech">Mechanism name<input id="dl-mech" value="${esc(mech)}" placeholder="Shooter, Arm, Elevator"></label>
          ${d.kind === "drivetrain" || d.kind === "gearing" ? "" : `<div><b>Its motors</b> <span class="small muted">(the tool picked these from the name; change them if it guessed wrong)</span>
            ${r.motors.length ? "" : `<p class="small warn-ink">No motor's name starts with "${esc(mech)}": tick the ones this design is for.</p>`}
            <div class="row" id="dl-motors">${choices.map(c => `<label class="row small" data-tip="config.dl-motor" data-quiet><input type="checkbox" value="${esc(c.name)}" ${r.motors.includes(c.name) ? "checked" : ""}>
              ${esc(c.name)} <span class="muted">${esc(c.motor || "?")}</span></label>`).join("")}</div></div>`}
          <div><b>Checked against the robot</b>${findingsHtml(r.findings)}</div>
          ${r.edits.length ? `<div><b>Numbers it can fill in</b>${r.edits.map((e, i) => `<label class="row small" data-tip="config.dl-edit" data-quiet><input type="checkbox" class="dl-edit" data-i="${i}"> ${esc(e.label)}</label>`).join("")}</div>` : ""}
          <div class="row"><button class="btn primary" id="dl-save" data-tip="config.dl-save">Save the design${r.edits.length ? " and the ticked numbers" : ""}…</button></div>
        </div></div>`;
      $$("#dl-motors input", box).forEach(c => c.onchange = () => readLink($$("#dl-motors input:checked", box).map(x => x.value)));
      // A new name picks the motors again, by that name.
      $("#dl-mech", box).onchange = () => readLink();
      $("#dl-save", box).onclick = save;
    }

    async function save() {
      const name = $("#dl-mech", root).value.trim();
      if (!name) { App.toast("Name the mechanism first (Shooter, Arm, Elevator)."); return; }
      const edits = [{ file: "slothtune.json", path: ["designs", name], value: { url: read.url, motors: read.motors } }];
      $$(".dl-edit:checked", root).forEach(c => edits.push(read.edits[+c.dataset.i]));
      if (await App.previewAndSave({ kind: "edits", edits: edits.map(e => ({ file: e.file, path: e.path, value: e.value })) }, "Mechanism design: " + name)) {
        $("#dl-out", root).innerHTML = "";
        $("#dl-url", root).value = "";
        read = null;
        paintSaved();
      }
    }

    async function paintSaved() {
      const box = $("#dl-saved", root);
      if (!box) return;
      const r = await App.api("/api/designs" + (log ? "?log=" + encodeURIComponent(log) : ""));
      if (!r.ok) { box.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
      const note = log ? `<p class="small muted">Checked against ${esc(log.split(/[\\/]/).pop())}${r.log_motors.length ? "" : ": it has no motor speeds (robot code older than October 2026 doesn't log them)"}.</p>` : "";
      box.innerHTML = note + (r.designs.length ? r.designs.map(d => `<details class="design" ${d.findings && d.findings.some(f => f.level === "error") ? "open" : ""}>
        <summary><b>${esc(d.mechanism)}</b> <span class="muted small">${d.design ? `${esc(d.design.source)} ${esc(d.design.calculator)} · ${esc((d.motors || []).join(", ") || "drivetrain")}` : esc(d.error || "")}</span>
          ${d.findings ? ["error", "warn"].map(l => { const n = d.findings.filter(f => f.level === l).length; return n ? ` <span class="level ${l}">${n} ${l}</span>` : ""; }).join("") : ""}</summary>
        ${d.design ? `<div class="grid2"><div>${saysHtml(d.describe)}<p class="small"><a href="${esc(d.url)}" target="_blank" rel="noopener">Open it in ${esc(d.design.source)}</a></p></div>
          <div>${findingsHtml(d.findings)}</div></div>` : ""}
        <div class="row"><button class="btn small" data-forget="${esc(d.mechanism)}" data-tip="config.dl-forget">Forget this design…</button></div></details>`).join("")
        : `<p class="hint">None saved yet.</p>`);
      $$("[data-forget]", box).forEach(b => b.onclick = async () => {
        if (await App.previewAndSave({ kind: "edit", file: "slothtune.json", path: ["designs", b.dataset.forget], value: null }, "Forget a design")) paintSaved();
      });
    }

    return { mount };
  })();

  App.on("lint", paint);
  App.on("saved", async () => { App.lint = await App.api("/api/lint"); App.emit("lint", App.lint); });
})();
