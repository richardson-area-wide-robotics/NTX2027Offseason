// Runs tab: every saved test, robot and practice, to reopen, compare or finish (tape measurements).
"use strict";

(() => {
  const root = $("#tab-runs");
  let filter = "robot";

  async function paint() {
    const r = await App.api("/api/runs");
    const list = (r.runs || []).filter(x => filter === "all" || (filter === "practice") === !!x.practice);
    root.innerHTML = `<div class="panel">
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
    $$("[data-export]", root).forEach(b => b.onclick = async () => {
      const r = await App.api("/api/export", { file: b.dataset.export });
      App.toast(r.ok ? `Wrote ${r.path}. Open it in AdvantageScope${r.sysid ? " or SysId" : ""}.` : (r.error || "Export failed."), 8000);
    });
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
