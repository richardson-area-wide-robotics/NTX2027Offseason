// Calibrate tab: measuring the robot itself - where the modules are and how big the wheels really
// are - so odometry starts from the truth. Each tool says what it can and can't measure.
"use strict";

(() => {
  const root = $("#tab-calibrate");
  let pushRun = null, wheels = null;

  root.innerHTML = `
    <div class="stack">
      <div class="panel">
        <h2>Module positions</h2>
        <div class="grid2">
          <div>
            <svg viewBox="0 0 320 300" class="geo-diagram" role="img" aria-label="Top view of the robot: wheelbase is front axle to back axle, track width is left wheel to right wheel">
              <rect x="50" y="40" width="220" height="220" rx="10" class="frame"></rect>
              <text x="160" y="28" text-anchor="middle" class="lbl">FRONT ▲</text>
              ${[[85, 75], [235, 75], [85, 225], [235, 225]].map(([x, y]) => `<rect x="${x - 9}" y="${y - 18}" width="18" height="36" rx="4" class="wheel"></rect><circle cx="${x}" cy="${y}" r="3" class="axle"></circle>`).join("")}
              <line x1="20" y1="75" x2="20" y2="225" class="dim"></line><line x1="14" y1="75" x2="92" y2="75" class="ext"></line><line x1="14" y1="225" x2="92" y2="225" class="ext"></line>
              <text x="12" y="155" class="lbl" transform="rotate(-90 12 155)" text-anchor="middle">wheelbase</text>
              <line x1="85" y1="285" x2="235" y2="285" class="dim"></line><line x1="85" y1="232" x2="85" y2="292" class="ext"></line><line x1="235" y1="232" x2="235" y2="292" class="ext"></line>
              <text x="160" y="280" class="lbl" text-anchor="middle">track width</text>
            </svg>
          </div>
          <div>
            <p class="small">Measure between the <b>centers of the wheels</b>, not the frame: the wheels sit inside it. Wheelbase is front axle to back axle; track width is the middle of a left wheel to the middle of the right one. Inches, to the nearest 1/8.</p>
            <div class="row" style="flex-wrap:wrap">
              <label class="small">Wheelbase (in) <input type="number" id="cg-wb" step="0.125" min="6" max="40" style="width:7em"></label>
              <label class="small">Track width (in) <input type="number" id="cg-tw" step="0.125" min="6" max="40" style="width:7em"></label>
              <button class="btn" id="cg-tape">Compare with the files</button>
            </div>
            <div id="cg-tape-out"></div>
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2>Wheel sizes</h2>
          <button class="btn" id="cg-wheel-practice">Practice</button>
        </div>
        <p class="small">Tread wears and compresses, and every distance odometry reports is wheel turns times the wheel size. With the motors coasting, a push makes each wheel roll freely over the same ground, so each one's count against a tape measure is its real size. Driving can't measure this: the speed loop makes every wheel report the speed it was asked for.</p>
        <ol class="small">
          <li>Robot <b>on the floor and disabled</b>. Mark a start and an end <b>3 m</b> apart along a straight line.</li>
          <li>Point every wheel straight ahead.</li>
          <li>Press <b>Record the push</b> (20 s, motors coast), then push the robot slowly and straight from mark to mark. Push on the frame, near the middle, so it doesn't twist.</li>
          <li>Type how far one point of the robot really moved, then <b>Measure</b>.</li>
        </ol>
        <div class="row" style="flex-wrap:wrap">
          <button class="btn primary" id="cg-push">Record the push</button>
          <label class="small">Distance moved (m) <input type="number" id="cg-tape-m" step="0.005" min="0.5" value="3.0" style="width:7em"></label>
          <button class="btn" id="cg-measure" disabled>Measure</button>
          <span class="small muted" id="cg-push-state"></span>
        </div>
        <div id="cg-wheel-out"></div>
      </div>
      <div class="panel">
        <h2>Check with a spin</h2>
        <p class="small">After the positions and wheel sizes are in, run the <b>Spin</b> test on the floor (Tune tab). Turning on the spot, the gyro's turn rate against the wheels' speeds says whether the two agree as a whole.</p>
        <div class="row"><button class="btn" id="cg-spin">Check the newest floor spin</button></div>
        <div id="cg-spin-out"></div>
      </div>
    </div>`;

  function findings(F) {
    return (F || []).map(f => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
      <div class="why">${Learn.link(f.why, 2)}</div></div>`).join("");
  }

  function saveButton(id, edits) {
    return edits && edits.length ? `<button class="btn primary" id="${id}">Save to the robot files…</button>` : "";
  }

  // ---------------------------------------------------------------- tape
  $("#cg-tape", root).onclick = async () => {
    const out = $("#cg-tape-out", root);
    const r = await App.api("/api/geometry/tape", { wheelbase_in: $("#cg-wb", root).value, track_in: $("#cg-tw", root).value });
    if (!r.ok) { out.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    out.innerHTML = (r.rows.length ? `<div class="tblwrap"><table class="t" style="width:auto"><thead><tr><th>Module</th><th>Front / left now</th><th>From the tape</th><th></th></tr></thead><tbody>
        ${r.rows.map(x => `<tr><td>${esc(x.name)}</td><td class="num mono">${fmt(x.front, 3)} / ${fmt(x.left, 3)}</td>
          <td class="num mono">${fmt(x.new_front, 3)} / ${fmt(x.new_left, 3)}</td>
          <td>${x.change ? `<span class="chip warn">moves ${fmt(x.moved_in, 2)} in</span>` : `<span class="chip good">matches</span>`}</td></tr>`).join("")}
      </tbody></table></div>` : "") + findings(r.findings) + saveButton("cg-tape-save", r.edits);
    const b = $("#cg-tape-save", out);
    if (b) b.onclick = () => App.previewAndSave({ kind: "edits", edits: r.edits }, "Module positions from the tape");
    try { localStorage.setItem("swervetune.tape", JSON.stringify({ wb: $("#cg-wb", root).value, tw: $("#cg-tw", root).value })); } catch (e) { /* storage blocked */ }
  };
  try {
    const t = JSON.parse(localStorage.getItem("swervetune.tape") || "null");
    if (t) { $("#cg-wb", root).value = t.wb; $("#cg-tw", root).value = t.tw; }
  } catch (e) { /* storage blocked */ }

  // ---------------------------------------------------------------- wheel sizes
  function showWheels(r) {
    const out = $("#cg-wheel-out", root);
    wheels = r.ok ? r : null;
    if (!r.ok) { out.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    out.innerHTML = `${r.practice ? `<div class="callout info">Practice: a made-up push of 3 m with one worn wheel and one wheel turned a little. Nothing here can be saved.</div>` : ""}
      ${r.rows.length ? `<div class="tblwrap"><table class="t" style="width:auto"><thead><tr><th>Module</th><th>Encoder said</th><th>Wheel angle</th><th>Real diameter</th><th>Against the average</th></tr></thead><tbody>
        ${r.rows.map(x => `<tr><td>${esc(x.name)}</td><td class="num mono">${fmt(x.encoder_m, 3)} m</td><td class="num mono">${fmt(x.angle_deg, 1)}°</td>
          <td class="num mono">${fmt(x.diameter_in, 3)} in</td>
          <td class="num mono ${Math.abs(x.vs_average) > 0.01 ? "warn-ink" : ""}">${x.vs_average >= 0 ? "+" : ""}${fmt(x.vs_average * 100, 1)}%</td></tr>`).join("")}
      </tbody></table></div>
      <p class="small muted">Average ${fmt(r.average_in, 3)} in; configured ${fmt(r.configured_in, 3)} in.</p>` : ""}
      ${findings(r.findings)}${r.practice ? "" : saveButton("cg-wheel-save", r.edits)}`;
    const b = $("#cg-wheel-save", out);
    if (b) b.onclick = () => App.previewAndSave({ kind: "edits", edits: r.edits }, "Wheel diameter from the push");
  }

  $("#cg-push", root).onclick = async () => {
    const st = $("#cg-push-state", root);
    try {
      st.textContent = "Recording for 20 s: push now.";
      App.toast("Recording: push the robot from mark to mark now.", 6000);
      const doc = await App.runTest("capture", "ALL", { duration_s: 20, coast: 1 });
      pushRun = doc._file;
      st.textContent = "Recorded. Type the distance and press Measure.";
      $("#cg-measure", root).disabled = false;
    } catch (e) { st.textContent = e.message; }
  };
  $("#cg-measure", root).onclick = async () => {
    if (!pushRun) return;
    showWheels(await App.api("/api/geometry/wheels", { file: pushRun, tape_m: $("#cg-tape-m", root).value }));
  };
  $("#cg-wheel-practice", root).onclick = async () => showWheels(await App.api("/api/geometry/wheels", { practice: true }));

  // ---------------------------------------------------------------- spin
  $("#cg-spin", root).onclick = async () => {
    const real = wheels && !wheels.practice && wheels.average_in ? wheels.configured_in / wheels.average_in : 1;
    const r = await App.api("/api/geometry/spin?configured_over_real=" + real);
    $("#cg-spin-out", root).innerHTML = (r.run ? `<p class="small muted">From ${esc(r.run)}${real !== 1 ? `, with the wheel sizes just measured taken out` : ""}.</p>` : "") + findings(r.findings);
  };
})();
