// Runs tab: every saved test, robot and practice, to reopen, compare or finish (tape measurements).
"use strict";

(() => {
  const root = $("#tab-runs");
  let filter = "all";
  // Robot runs are the real robot only: the simulator's sensors are perfect, and the practice pod is a model.
  const KIND = x => x.practice ? "practice" : x.env === "SIM" ? "sim" : "robot";
  const stamp = s => {
    const m = /(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)/.exec(s || "");
    if (!m) return s || "";
    const h = +m[4];
    return `${+m[2]}/${+m[3]} ${h % 12 || 12}:${m[5]} ${h < 12 ? "AM" : "PM"}`;
  };

  async function paint() {
    const r = await App.api("/api/runs");
    const list = (r.runs || []).filter(x => filter === "all" || KIND(x) === filter);
    const logs = `<div class="panel runs-logs">
      <div class="row" style="justify-content:space-between;flex-wrap:wrap"><h2 data-tip="runs.logs">Match logs</h2>
        <div class="row" style="flex-wrap:wrap"><label class="row small" data-tip="runs.folder">Log folder <input id="lg-folder" placeholder="USB stick or AdvantageScope downloads" style="min-width:20em"></label>
        <button class="btn" id="lg-go" data-tip="runs.list">List logs</button></div></div>
      ${HowTo.block(`<p class="small">AdvantageKit writes one log per power-up: to the USB stick in the roboRIO (/U/logs) or, on a roboRIO 2 with no stick, to its SD card (/home/lvuser/logs; to download those, set AdvantageScope's roboRIO log folder to that path). A roboRIO 1 without a stick keeps no logs. Copy them here, or point at the folder AdvantageScope downloads to.</p>`, "Where the logs are")}
      <div id="lg-list"></div><div id="lg-report"></div></div>`;
    root.innerHTML = `<div class="runs2"><div class="panel runs-saved">
      <div class="row" style="justify-content:space-between"><h2 data-tip="runs.saved">Saved runs</h2>
        <div class="seg" id="rf" role="group" aria-label="Show"><button data-f="robot" data-tip="runs.f.robot">Robot</button><button data-f="sim" data-tip="runs.f.sim">Simulator</button><button data-f="practice" data-tip="runs.f.practice">Practice pod</button><button data-f="all" data-tip="runs.f.all">All</button></div></div>
      <p class="hint">Stored in tools/swervetune/runs (not committed). Press a run's time to open it; reopening re-checks it with the current advice.</p>
      ${list.length ? `<div class="tblwrap"><table class="t"><thead><tr><th><span class="term" tabindex="0" data-tip="runs.when" data-quiet>When</span></th><th>Robot</th><th>Test</th><th><span class="term" tabindex="0" data-tip="runs.where" data-quiet>Where</span></th><th><span class="term" tabindex="0" data-tip="runs.outcome" data-quiet>Outcome</span></th><th class="num"><span class="term" tabindex="0" data-tip="runs.score" data-quiet>Score</span></th><th>Summary</th></tr></thead><tbody>
        ${list.map(x => `<tr class="${x.outcome && x.outcome !== "DONE" ? "stopped" : ""}"><td class="nowrap"><button class="linkbtn" data-open="${esc(x.file)}">${esc(stamp(x.saved))}</button>
          ${x.test === "straight" ? ` <button class="btn small" data-tape="${esc(x.file)}" data-tip="runs.tape" data-quiet>Enter tape</button>` : ""}</td>
          <td>${esc(x.robot || "")}</td><td>${esc(testName(x.test))}</td><td>${{ practice: "Practice pod", sim: "Simulator" }[KIND(x)] || esc(whereWord(x.env || ""))}</td>
          <td>${x.outcome === "DONE" ? "finished" : esc((x.outcome || "").toLowerCase())}</td><td class="num">${x.score == null || x.outcome !== "DONE" ? "–" : x.score}</td><td class="small">${esc(x.summary || "")}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty">No runs ${filter === "all" ? "yet" : "of this kind yet"}.</div>`}</div>${logs}</div>`;
    $$("#rf button", root).forEach(b => { b.classList.toggle("on", b.dataset.f === filter); b.setAttribute("aria-pressed", String(b.dataset.f === filter)); b.onclick = () => { filter = b.dataset.f; paint(); }; });
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
      <p>Measure from the start mark to the robot's center where it stopped at the far end, in meters: along the direction it drove (forward) and across it (sideways, left positive).</p>
      <div class="row"><label class="gain" data-tip="runs.tape.f">Forward (m)<input type="number" step="0.001" id="tp-f"></label>
      <label class="gain" data-tip="runs.tape.l">Sideways (m)<input type="number" step="0.001" id="tp-l"></label></div>
      <div class="row"><button class="btn primary" id="tp-go" data-tip="runs.tape.go">Analyze</button><button class="btn" onclick="App.closeModal()">Cancel</button></div>`, box => {
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
