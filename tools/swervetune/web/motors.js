// Motors tab: every watched motor's heat, current, stall time and health, and the thermal override.
"use strict";

(() => {
  const root = $("#tab-motors");
  const STAGE_CLASS = { OK: "good", WARN: "warn", DERATE: "warn", SHUTOFF: "bad" };
  root.innerHTML = `
    <div class="grid2">
      <div class="stack">
        <div class="panel">
          <div class="row" style="justify-content:space-between">
            <h2>Motors</h2>
            <span class="hint">Heat is the guard's estimate of the windings, as a share of what burns them out.</span>
          </div>
          <div id="motor-off" class="callout bad" hidden>The motor guard is switched off in swervetune.json: nothing protects these motors from heat, stalls or failure.</div>
          <div class="table-wrap">
            <table class="motors">
              <thead><tr><th>Motor</th><th>Stage</th><th>Heat</th><th>Temp</th><th>Current</th><th>Stall</th><th>Why</th></tr></thead>
              <tbody id="motor-rows"><tr><td colspan="7" class="muted">Connect to a robot to see its motors.</td></tr></tbody>
            </table>
          </div>
        </div>
        <div class="panel">
          <h3>Recent changes</h3>
          <ul id="motor-events" class="small mono" style="margin:0;padding-left:18px"></ul>
        </div>
      </div>
      <div class="stack">
        <div class="panel">
          <h3>Thermal override</h3>
          <p class="small">For the end of a match, when losing a motor costs more than the motor. Holds heat
            shutoffs at half current for up to <span id="ovr-max">20</span> s. Never lifts a stall cut, and never
            holds off a motor already 10 °C past its shutoff or at 95% heat: past those it is being destroyed.</p>
          <div class="row" style="margin-top:8px;flex-wrap:wrap;gap:8px">
            <select id="ovr-name" aria-label="Motor"><option value="ALL">Every motor</option></select>
            <input id="ovr-secs" type="number" min="0" max="20" step="1" value="20" aria-label="Seconds">
            <button id="ovr-go" class="btn primary">Hold shutoffs</button>
            <button id="ovr-cancel" class="btn">Cancel override</button>
          </div>
          <div id="ovr-reply" class="small muted" style="margin-top:6px"></div>
        </div>
        <div class="panel">
          <h3>How the guard decides</h3>
          <ul class="small" style="margin:0;padding-left:18px">
            <li><b>Heat estimate</b> from current: the only judge fast enough for a NEO 550, whose sensor lags its windings by tens of seconds.</li>
            <li><b>Sensor temperature</b>: a slower second opinion.</li>
            <li><b>Stall timer</b>: at the current limit without turning, a jam. Not used on drive motors, which stall in every pushing match.</li>
            <li><b>WARN</b> tells you. <b>DERATE</b> halves the current limit. <b>SHUTOFF</b> drops it to 2 A. Nothing is saved to the controller's flash; a reboot restores the code's limits.</li>
          </ul>
          <table class="motors small" style="margin-top:8px">
            <thead><tr><th>Motor</th><th>Policy</th><th>Warn</th><th>Derate</th><th>Shutoff</th></tr></thead>
            <tbody id="motor-kinds"></tbody>
          </table>
        </div>
        <div class="panel">
          <h3>At startup</h3>
          <ul id="motor-report" class="small" style="margin:0;padding-left:18px"></ul>
        </div>
      </div>
    </div>`;

  const heatBar = pct => {
    const known = Number.isFinite(pct);
    const v = known ? Math.max(0, Math.min(100, pct)) : 0;
    const cls = v >= 85 ? "bad" : v >= 50 ? "warn" : "good";
    return `<div class="heat" title="WARN 50% · DERATE 70% · SHUTOFF 85%"><div class="${cls}" style="width:${v}%"></div>
      <span class="mono">${known ? fmt(pct, 0) + "%" : "–"}</span></div>`;
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
      return `<tr class="${m.flags ? "flagged" : ""}">
        <td><b>${esc(m.name)}</b><div class="muted small">${esc(m.kind)}</div></td>
        <td><span class="chip ${STAGE_CLASS[m.stage] || ""}">${esc(m.stage)}</span>${ovr}</td>
        <td>${heatBar(Number.isFinite(m.amps) ? m.heat_pct : NaN)}</td>
        <td class="mono">${Number.isFinite(m.temp) ? fmt(m.temp, 0) + " °C" : "–"}</td>
        <td class="mono">${Number.isFinite(m.amps) ? fmt(m.amps, 1) + " A" : "–"}<div class="muted small">${limit}</div></td>
        <td class="mono">${m.stall_s > 0 ? fmt(m.stall_s, 1) + " s" : "–"}</td>
        <td class="small">${esc(m.cause || "")}${m.flags ? `<div style="color:var(--bad)">! ${esc(m.flags)}</div>` : ""}</td>
      </tr>`;
    }).join("") : `<tr><td colspan="7" class="muted">No motors are being watched${L.connected ? "" : " (not connected)"}.</td></tr>`;

    const events = guard.events || [];
    $("#motor-events", root).innerHTML = events.length
      ? events.slice().reverse().map(e => `<li>${esc(e)}</li>`).join("")
      : `<li class="muted">No stage changes since the robot started.</li>`;
    const report = guard.report || [];
    $("#motor-report", root).innerHTML = report.length ? report.map(l => `<li>${esc(l)}</li>`).join("")
      : `<li class="muted">Every motor's current limit is within the team policy.</li>`;

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
    const failing = rows.filter(m => m.flags).length;
    chip.hidden = !rows.length;
    chip.className = "chip " + (failing ? "bad" : STAGE_CLASS[worst.stage] || "");
    chip.textContent = failing ? `Motors: ${failing} failing` : worst.stage === "OK" ? "Motors OK"
      : `${worst.name}: ${worst.stage}`;
  }

  async function override(seconds) {
    const r = await App.api("/api/motors/override", { name: $("#ovr-name", root).value, seconds });
    $("#ovr-reply", root).textContent = r.message || r.error || "";
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
  App.on("state", st => {
    const kinds = st.motor_kinds || {};
    $("#ovr-max", root).textContent = st.max_override_s || 20;
    $("#ovr-secs", root).max = st.max_override_s || 20;
    $("#motor-kinds", root).innerHTML = Object.values(kinds).map(([label, amps, w, d, s]) =>
      `<tr><td>${esc(label)}</td><td class="mono">${amps} A</td><td class="mono">${w} °C</td><td class="mono">${d} °C</td><td class="mono">${s} °C</td></tr>`).join("");
  });
})();
