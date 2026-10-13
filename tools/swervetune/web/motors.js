// Motors tab: every watched motor's heat, current, stall time and health, and the thermal override.
"use strict";

(() => {
  const root = $("#tab-motors");
  // A column header that explains itself on hover, focus or tap (no printed line: columns are narrow).
  const t = (key, text) => `<span class="term" tabindex="0" data-tip="${key}" data-quiet>${esc(text)}</span>`;
  // Four stages, four looks: OK is plain, WARN a tint, DERATE solid amber, SHUTOFF solid red.
  const STAGE_CLASS = { OK: "", WARN: "warn", DERATE: "derate", SHUTOFF: "shutoff" };
  const STAGE_DO = { WARN: "getting hot: ease off", DERATE: "at half power to cool", SHUTOFF: "cut to 2 A until it cools" };
  root.innerHTML = `
    <div class="grid2">
      <div class="stack">
        <div class="panel">
          <h2 data-tip="motors.title">Motors</h2>
          <p class="hint">Red means broken now: fix it. Amber happened earlier or is getting hot: check it. Heat is the guard's estimate of the windings, as a share of what burns them out; the ticks are 50, 70 and 85%.</p>
          <div id="motor-off" class="callout bad" hidden>The motor guard is switched off in swervetune.json: nothing protects these motors from heat, stalls or failure.</div>
          <div class="tblwrap">
            <table class="t">
              <thead><tr><th>Motor</th><th>${t("motors.stage", "Stage")}</th><th>${t("motors.heat", "Heat")}</th><th class="num">${t("motors.temp", "Temp")}</th><th class="num">${t("motors.current", "Current")}</th><th class="num">${t("motors.stall", "Stall")}</th><th>${t("motors.why", "Why")}</th></tr></thead>
              <tbody id="motor-rows"><tr><td colspan="7" class="muted">Connect to a robot to see its motors.</td></tr></tbody>
            </table>
          </div>
        </div>
        <div class="panel">
          <h3 data-tip="motors.events">Recent changes</h3>
          <ul id="motor-events" class="small mono" style="margin:0;padding-left:18px"></ul>
        </div>
      </div>
      <div class="stack">
        <div class="panel">
          <h3 data-tip="motors.override"><span class="term" tabindex="0" data-learn="thermal_override">Thermal override</span></h3>
          <p class="small">For the end of a match, when losing a motor costs more than the motor. A motor the guard
            cut off for heat runs at half power instead, for up to <span id="ovr-max">20</span> s. Never lifts a stall cut, and never
            holds off a motor already 10 °C past its shutoff or at 95% heat: past those it is being destroyed.
            The driver's Back button does the same for every motor: a short buzz when it took, a long one when a motor stays off.</p>
          <div id="ovr-now" class="callout warn" hidden></div>
          <div class="row" style="margin-top:8px;flex-wrap:wrap;gap:8px">
            <label class="row small" data-tip="motors.ovr-name">Motor <select id="ovr-name"><option value="ALL">Every motor</option></select></label>
            <label class="row small" data-tip="motors.ovr-secs">for <input id="ovr-secs" type="number" min="0" max="20" step="1" value="20" style="width:5em"> s</label>
            <button id="ovr-go" class="btn" data-tip="motors.ovr-go">Keep running past shutoff</button>
            <button id="ovr-cancel" class="btn" data-tip="motors.ovr-cancel">Cancel override</button>
          </div>
          <div id="ovr-reply" class="small" style="margin-top:6px"></div>
        </div>
        <div class="panel">
          <h3 data-tip="motors.rules">How the guard decides</h3>
          <ul class="small" style="margin:0;padding-left:18px">
            <li><b>Heat estimate</b> from current: the only judge fast enough for a NEO 550, whose sensor lags its windings by tens of seconds.</li>
            <li><b>Sensor temperature</b>: a slower second opinion.</li>
            <li><b>Stall timer</b>: at the current limit without turning, a jam. Not used on drive motors, which stall in every pushing match.</li>
            <li><b>WARN</b> tells you. <b>DERATE</b> halves the current limit. <b>SHUTOFF</b> drops it to 2 A. Nothing is saved to the controller's flash; a reboot restores the code's limits.</li>
          </ul>
          <table class="t small" style="margin-top:8px">
            <thead><tr><th>Motor</th><th class="num">${t("motors.policy", "Policy")}</th><th class="num">${t("motors.warn", "Warn")}</th><th class="num">${t("motors.derate", "Derate")}</th><th class="num">${t("motors.shutoff", "Shutoff")}</th></tr></thead>
            <tbody id="motor-kinds"></tbody>
          </table>
        </div>
        <div class="panel">
          <h3 data-tip="motors.startup">At startup</h3>
          <ul id="motor-report" class="small" style="margin:0;padding-left:18px"></ul>
        </div>
      </div>
    </div>
    <div class="panel" style="margin-top:12px">
      <div class="row" style="justify-content:space-between;flex-wrap:wrap">
        <h2 data-tip="motors.inventory">Motors and controllers</h2>
        <button class="btn" id="inv-refresh" data-tip="motors.refresh">Check again</button>
      </div>
      <p class="small">What each controller is, three ways: what the code creates, what the controller itself reports over CAN (when connected), and what motor it drives, set here by hand or read from the code. A drive_ff run also measures the drive motors' speed per volt, which tells a NEO from a Vortex.</p>
      <div id="inv-body"><p class="hint">Reading the code…</p></div>
    </div>`;

  // The number sits beside the bar, never on it: on the fill it was 1.4-3.1:1.
  const heatBar = pct => {
    const known = Number.isFinite(pct);
    const v = known ? Math.max(0, Math.min(100, pct)) : 0;
    const cls = v >= 85 ? "bad" : v >= 50 ? "warn" : "good";
    return `<div class="heatcell"><div class="heat" aria-hidden="true"><div class="${cls}" style="width:${v}%"></div></div>
      <span class="heat-pct">${known ? fmt(pct, 0) + "%" : "–"}</span></div>`;
  };

  function paint(L) {
    const rows = (L.live && L.live.motors) || [];
    const guard = L.motor_guard || {};
    $("#motor-off", root).hidden = guard.guard_on !== false;
    $("#motor-rows", root).innerHTML = rows.length ? rows.map(m => {
      const limit = m.limit < m.base_limit
        ? `<b style="color:var(--bad)">${fmt(m.limit, 0)}</b> of ${fmt(m.base_limit, 0)} A`
        : `limit ${fmt(m.base_limit, 0)} A`;
      const ovr = m.override_s > 0 ? ` <span class="chip info">override ${fmt(m.override_s, 0)} s</span>` : "";
      // Red: broken now. Amber: happened earlier, or a stage short of a cut.
      const row = m.flags ? "flagged" : (m.history || m.stage === "WARN" || m.stage === "DERATE") ? "history" : "";
      return `<tr class="${row}">
        <td><b>${esc(m.name)}</b><div class="muted small">${esc(m.kind)}</div></td>
        <td>${m.stage === "OK" ? `<span class="muted">OK</span>` : `<span class="chip ${STAGE_CLASS[m.stage] || ""}">${esc(m.stage)}</span>`}${ovr}</td>
        <td>${heatBar(Number.isFinite(m.amps) ? m.heat_pct : NaN)}</td>
        <td class="num">${Number.isFinite(m.temp) ? fmt(m.temp, 0) + " °C" : "–"}</td>
        <td class="num">${Number.isFinite(m.amps) ? fmt(m.amps, 1) + " A" : "–"}<div class="muted small">${limit}</div></td>
        <td class="num">${m.stall_s > 0 ? fmt(m.stall_s, 1) + " s" : "–"}</td>
        <td class="small">${STAGE_DO[m.stage] ? `<b>${STAGE_DO[m.stage]}</b>${m.cause ? ": " : ""}` : ""}${esc(m.cause || "")}
          ${m.flags ? `<div class="bad-ink"><b>Broken now:</b> ${esc(m.flags)}</div>` : ""}
          ${m.history ? `<div class="warn-ink">Earlier: ${esc(m.history)}</div>` : ""}</td>
      </tr>`;
    }).join("") : `<tr><td colspan="7" class="muted">No motors are being watched${L.connected ? "" : " (not connected)"}.</td></tr>`;

    const events = guard.events || [];
    $("#motor-events", root).innerHTML = events.length
      ? events.slice().reverse().map(e => `<li>${esc(e)}</li>`).join("")
      : `<li class="muted">No stage changes since the robot started.</li>`;
    const report = guard.report || [];
    $("#motor-report", root).innerHTML = report.length ? report.map(l => `<li>${esc(l)}</li>`).join("")
      : `<li class="muted">Every motor's current limit is within the team policy.</li>`;

    const left = Math.max(0, ...rows.map(m => m.override_s || 0));
    $("#ovr-now", root).hidden = !(left > 0);
    $("#ovr-now", root).textContent = left > 0 ? `Override on, ${fmt(left, 0)} s left: motors cut off for heat run at half power. Stalls still cut out.` : "";
    const sel = $("#ovr-name", root);
    const names = rows.map(m => m.name);
    if (sel.dataset.names !== names.join("|")) {
      sel.dataset.names = names.join("|");
      sel.innerHTML = `<option value="ALL">Every motor</option>` + names.map(n => `<option>${esc(n)}</option>`).join("");
    }
  }

  // Worst stage across every motor, on the header, whichever tab is open.
  function paintChip(L) {
    const chip = $("#motors-chip");
    const rows = (L && L.live && L.live.motors) || [];
    const order = ["OK", "WARN", "DERATE", "SHUTOFF"];
    const worst = rows.reduce((w, m) => order.indexOf(m.stage) > order.indexOf(w.stage) ? m : w, { stage: "OK" });
    // Only what is broken now is red; a fault that already cleared is "to check".
    const failing = rows.filter(m => m.flags).length, check = rows.filter(m => m.history).length;
    chip.hidden = !rows.length;
    setChip(chip, failing ? `Motors: ${failing} broken` : worst.stage !== "OK" ? `${worst.name}: ${worst.stage}`
      : check ? `Motors: ${check} to check` : "Motors OK",
      failing ? "bad" : worst.stage !== "OK" ? STAGE_CLASS[worst.stage] : check ? "warn" : "");
  }

  async function override(seconds) {
    const r = await App.api("/api/motors/override", { name: $("#ovr-name", root).value, seconds });
    $("#ovr-reply", root).textContent = r.message || r.error || "";
    $("#ovr-reply", root).className = "small " + (r.ok === false ? "bad-ink" : "");
    if (r.ok === false) App.toast(r.error || "The override did not reach the robot.");
  }
  $("#ovr-go", root).onclick = () => override(Number($("#ovr-secs", root).value) || 0);
  $("#ovr-cancel", root).onclick = () => override(0);
  $("#motors-chip").onclick = () => App.show("motors");

  App.on("live", L => {
    paintChip(L);
    if (!L || !L.connected || !root.classList.contains("on")) return;
    paint(L);
  });
  // ---------------------------------------------------------------- motors and controllers
  let inv = null, pending = {};

  async function paintInventory() {
    const box = $("#inv-body", root);
    const r = await App.api("/api/motors/inventory");
    if (r.ok === false) { box.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    inv = r;
    pending = {};
    const chip = s => s === "bad" ? `<span class="chip bad">check</span>` : s === "unknown" ? `<span class="chip warn">name it</span>` : `<span class="muted small">✓ ok</span>`;
    box.innerHTML = `
      ${r.connected ? "" : `<p class="hint">Not connected: "Robot says" fills in when the robot is.</p>`}
      <div class="tblwrap"><table class="t"><thead><tr><th>${t("motors.inv.name", "Name")}</th><th>${t("motors.inv.status", "Status")}</th><th class="num">${t("motors.inv.can", "CAN")}</th><th>${t("motors.inv.code", "Code creates")}</th><th>${t("motors.inv.robot", "Robot says")}</th><th>${t("motors.inv.fw", "Firmware")}</th><th>${t("motors.inv.motor", "Motor type")}</th><th>${t("motors.inv.from", "From")}</th><th>${t("motors.inv.set", "Set it")}</th></tr></thead><tbody>
        ${r.rows.map((x, i) => `<tr><td>${esc(x.name)}</td><td>${chip(x.status)}</td><td class="num">${x.can_id ?? "?"}</td>
          <td>${esc(x.code_controller)}</td><td>${x.controller ? esc(x.controller) : `<span class="muted">–</span>`}</td>
          <td class="mono small">${esc(x.firmware || "")}</td>
          <td>${esc(x.motor || "?")}${x.measured ? ` <span class="small muted">(measures as ${esc(x.measured)})</span>` : ""}</td>
          <td class="small muted">${esc(x.motor_source)}</td>
          <td><select data-inv="${i}" data-tip="motors.inv.pick" data-quiet aria-label="What ${esc(x.name)} drives"><option value="">${x.key === x.name ? "leave" : `leave (all ${esc(x.key)})`}</option>
            ${r.choices.map(c => `<option ${c === (r.inventory[x.name] || (x.key !== x.name ? r.inventory[x.key] : "")) ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></td></tr>`).join("")}
      </tbody></table></div>
      ${r.measured_run ? `<p class="small muted">Drive motors measured from ${esc(r.measured_run)}.</p>` : ""}
      <div class="row"><button class="btn primary" id="inv-save" disabled data-tip="motors.inv.save">Save the motor inventory…</button>
        <span class="small muted">Writes swervetune.json's "motors"; redeploy so the motor guard uses it.</span></div>
      ${(r.findings || []).map((f, i) => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
        <div class="why">${Learn.link(f.why, 2)}</div>
        ${f.edits ? `<div class="row"><button class="btn" data-fix="${i}" data-tip="motors.fix">Fix the module files…</button></div>` : ""}</div>`).join("")}`;
    $$("[data-fix]", box).forEach(b => b.onclick = async () => {
      const f = r.findings[+b.dataset.fix];
      if (await App.previewAndSave({ kind: "edits", edits: f.edits }, f.title)) paintInventory();
    });
    $$("[data-inv]", box).forEach(sel => sel.onchange = () => {
      const row = r.rows[+sel.dataset.inv];
      pending[row.key === row.name ? row.name : row.key] = sel.value;
      if (row.key !== row.name) {   // one choice for every swerve drive (or steer) motor
        $$("[data-inv]", box).forEach(o => { if (r.rows[+o.dataset.inv].key === row.key) o.value = sel.value; });
      }
      $("#inv-save", box).disabled = false;
    });
    $("#inv-save", box).onclick = async () => {
      const edits = Object.entries(pending).filter(([, v]) => v).map(([k, v]) => ({ file: "swervetune.json", path: ["motors", k], value: v }));
      if (!edits.length) return;
      if (await App.previewAndSave({ kind: "edits", edits }, "Motor inventory")) paintInventory();
    };
  }
  $("#inv-refresh", root).onclick = paintInventory;
  App.on("tab", t => { if (t === "motors") paintInventory(); });

  App.on("state", st => {
    const kinds = st.motor_kinds || {};
    $("#ovr-max", root).textContent = st.max_override_s || 20;
    $("#ovr-secs", root).max = st.max_override_s || 20;
    $("#motor-kinds", root).innerHTML = Object.values(kinds).map(([label, amps, w, d, s]) =>
      `<tr><td>${esc(label)}</td><td class="num">${amps} A</td><td class="num">${w} °C</td><td class="num">${d} °C</td><td class="num">${s} °C</td></tr>`).join("");
  });
})();
