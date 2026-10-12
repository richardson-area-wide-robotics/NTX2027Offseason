// Runs tab: every saved test, robot and practice, to reopen, compare or finish (tape measurements).
"use strict";

(() => {
  const root = $("#tab-runs");
  let filter = "robot";

  async function paint() {
    const r = await App.api("/api/runs");
    const list = (r.runs || []).filter(x => filter === "all" || (filter === "practice") === !!x.practice);
    root.innerHTML = `<div class="panel">
      <div class="row" style="justify-content:space-between;flex-wrap:wrap"><h2>Match logs</h2>
        <div class="row" style="flex-wrap:wrap"><input id="lg-folder" placeholder="Folder with .wpilog files (USB stick, AdvantageScope downloads)" style="min-width:22em" aria-label="Log folder">
        <button class="btn" id="lg-go">List logs</button></div></div>
      <p class="hint">AdvantageKit writes one log per power-up: to the USB stick in the roboRIO (/U/logs) or, on a roboRIO 2 with no stick, to its SD card (/home/lvuser/logs; to download those, set AdvantageScope's roboRIO log folder to that path). A roboRIO 1 without a stick keeps no logs. Copy them here, or point at the folder AdvantageScope downloads to.</p>
      <div id="lg-list"></div><div id="lg-report"></div></div>
      <div class="panel">
      <div class="row" style="justify-content:space-between"><h2>Saved runs</h2>
        <div class="seg" id="rf"><button data-f="robot">Robot</button><button data-f="practice">Practice</button><button data-f="all">All</button></div></div>
      <p class="hint">Stored in tools/swervetune/runs (not committed). Reopening a run re-analyses it with the current advice.</p>
      ${list.length ? `<div class="tblwrap"><table class="t"><thead><tr><th>When</th><th>Robot</th><th>Test</th><th>Where</th><th>Outcome</th><th>Score</th><th>Summary</th><th></th></tr></thead><tbody>
        ${list.map(x => `<tr><td class="mono">${esc((x.saved || "").replace(/(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)(\d\d)/, "$2/$3 $4:$5"))}</td>
          <td>${esc(x.robot || "")}</td><td>${esc(x.test)}</td><td>${x.practice ? "practice" : esc(x.env || "")}</td>
          <td>${esc(x.outcome || "")}</td><td class="num">${x.score == null ? "–" : x.score}</td><td class="small">${esc(x.summary || "")}</td>
          <td><button class="btn small" data-open="${esc(x.file)}">Open</button>
          <button class="btn small" data-export="${esc(x.file)}" title="Write a WPILOG that AdvantageScope opens${x.test === "drive_ff" ? ", and SysId reads" : ""}">Export</button>
          ${x.test === "straight" ? `<button class="btn small" data-tape="${esc(x.file)}">Enter tape</button>` : ""}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">No runs yet.</div>`}</div>`;
    $$("#rf button", root).forEach(b => { b.classList.toggle("on", b.dataset.f === filter); b.onclick = () => { filter = b.dataset.f; paint(); }; });
    $$("[data-open]", root).forEach(b => b.onclick = async () => {
      const d = await App.api("/api/runs/" + encodeURIComponent(b.dataset.open));
      d._file = b.dataset.open;
      App.show("tune");
      Tune.show(d);
    });
    $$("[data-tape]", root).forEach(b => b.onclick = () => tape(b.dataset.tape));
    let folder = "";
    try { folder = localStorage.getItem("swervetune.logfolder") || ""; } catch (e) { /* storage blocked */ }
    $("#lg-folder", root).value = folder;
    $("#lg-go", root).onclick = () => listLogs($("#lg-folder", root).value);
    if (folder) listLogs(folder);
    $$("[data-export]", root).forEach(b => b.onclick = async () => {
      const r = await App.api("/api/export", { file: b.dataset.export });
      App.toast(r.ok ? `Wrote ${r.path}. Open it in AdvantageScope${r.sysid ? " or SysId" : ""}.` : (r.error || "Export failed."), 8000);
    });
  }

  async function listLogs(folder) {
    try { localStorage.setItem("swervetune.logfolder", folder); } catch (e) { /* storage blocked */ }
    const r = await App.api("/api/logs?folder=" + encodeURIComponent(folder));
    const box = $("#lg-list", root);
    if (!r.ok) { box.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    box.innerHTML = r.files.length ? `<div class="tblwrap"><table class="t"><tbody>${r.files.map(f => `<tr>
        <td class="mono small">${esc(f.name)}</td><td class="num small">${fmt(f.size / 1e6, 1)} MB</td>
        <td class="small">${new Date(f.mtime * 1000).toLocaleString()}</td>
        <td><button class="btn small" data-log="${esc(f.path)}">Summarize</button></td></tr>`).join("")}</tbody></table></div>`
      : `<p class="hint">No .wpilog files in that folder.</p>`;
    $$("[data-log]", box).forEach(b => b.onclick = () => summarize(b.dataset.log));
  }

  async function summarize(path) {
    const box = $("#lg-report", root);
    box.innerHTML = `<p class="hint">Reading ${esc(path)}…</p>`;
    const r = await App.api("/api/logsummary?file=" + encodeURIComponent(path));
    if (r.ok === false) { box.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    const i = r.info || {};
    box.innerHTML = `<h3>${esc(r.summary)}</h3>
      <p class="small muted">${i.FMSAttached ? `${esc(i.EventName || "")} ${esc(i.MatchType || "")} ${esc(i.MatchNumber || "")} · ` : ""}${fmt(r.duration_s, 0)} s ·
        ${r.phases.filter(p => p[2] !== "disabled").map(p => `${p[2]} ${fmt(p[1] - p[0], 0)} s`).join(", ") || "never enabled"}
        ${r.battery_min != null ? ` · battery low ${fmt(r.battery_min, 1)} V` : ""}</p>
      ${(r.findings || []).length ? `<h3>Where to look</h3>${r.findings.map(f => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span>
        ${f.when ? `<span class="small muted">${esc(f.when)}</span>` : ""}</div><div class="why">${Learn.link(f.why, 3)}</div></div>`).join("")}` : ""}
      <h3>What happened</h3>
      ${r.events.length ? `<ol class="story small">${r.events.map(e => `<li><span class="level ${e.level}">${e.level}</span>
        <span class="mono">${esc(e.when)}</span> ${Learn.link(e.text, 2)}
        <button class="btn small" data-at="${e.t}">See on the wiring map</button></li>`).join("")}</ol>` : `<p class="hint">Nothing went wrong in this log.</p>`}`;
    $$("[data-at]", box).forEach(b => b.onclick = () => { Wiring.showLog(path, +b.dataset.at); });
  }

  function tape(file) {
    App.modal(`<h2>Where did it stop?</h2>
      <p>Measure from the start mark to the robot's centre, along the direction it drove (forward) and across it (sideways, left positive).</p>
      <div class="row"><label class="gain">Forward (m)<input type="number" step="0.001" id="tp-f"></label>
      <label class="gain">Sideways (m)<input type="number" step="0.001" id="tp-l"></label></div>
      <div class="row"><button class="btn primary" id="tp-go">Analyse</button><button class="btn" onclick="App.closeModal()">Cancel</button></div>`, box => {
      $("#tp-go", box).onclick = async () => {
        const rep = await App.api("/api/analyze", { file, tape_forward: +$("#tp-f", box).value || null, tape_lateral: +$("#tp-l", box).value || null });
        const d = await App.api("/api/runs/" + encodeURIComponent(file));
        d._file = file; d.report = rep;
        App.closeModal();
        App.show("tune");
        Tune.show(d);
      };
    });
  }

  App.on("tab", t => { if (t === "runs") paint(); });
})();
