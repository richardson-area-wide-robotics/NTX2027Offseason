// Calibrate tab: measuring the robot itself - where the modules are and how big the wheels really
// are - so odometry starts from the truth. Each tool says what it can and can't measure.
"use strict";

(() => {
  const root = $("#tab-calibrate");
  let pushRun = null, wheels = null;
  let spots = [], surveyTimer = null;

  root.innerHTML = `
    <div class="stack">
      <div class="panel">
        <p class="small">Measure the robot in this order: each one uses the ones before it. Every panel has <b>Practice</b>, which runs it on made-up data with a known answer, so you can see what a good result looks like before measuring for real.</p>
      </div>
      <div class="panel">
        <h2 data-tip="cal.positions">1. Module positions</h2>
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
              <label class="small" data-tip="cal.wb">Wheelbase (in) <input type="number" id="cg-wb" step="0.125" min="6" max="40" style="width:7em"></label>
              <label class="small" data-tip="cal.tw">Track width (in) <input type="number" id="cg-tw" step="0.125" min="6" max="40" style="width:7em"></label>
              <button class="btn" id="cg-tape" data-tip="cal.compare">Compare with the files</button>
            </div>
            <p class="small good-result"><b>A good result:</b> every module within about 1/8 in of the files. A bigger difference means the code has a wrong number.</p>
            <div id="cg-tape-out"></div>
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="cal.wheels">2. Wheel sizes</h2>
          <button class="btn" id="cg-wheel-practice" data-tip="cal.practice" data-quiet>Practice</button>
        </div>
        <p class="small">Tread wears and compresses, and every distance odometry reports is wheel turns times the wheel size. With the motors coasting, a push makes each wheel roll freely over the same ground, so each one's count against a tape measure is its real size. Driving can't measure this: the speed loop makes every wheel report the speed it was asked for.</p>
        <ol class="small">
          <li>Robot <b>on the floor and disabled</b>. Mark a start and an end <b>3 m</b> apart along a straight line.</li>
          <li>Point every wheel straight ahead.</li>
          <li>Press <b>Record the push</b> (20 s, motors coast), then push the robot slowly and straight from mark to mark. Push on the frame, near the middle, so it doesn't twist.</li>
          <li>Type how far one point of the robot really moved, then <b>Measure</b>.</li>
        </ol>
        <div class="row" style="flex-wrap:wrap">
          <button class="btn primary" id="cg-push" data-tip="cal.push">Record the push</button>
          <label class="small" data-tip="cal.distance">Distance moved (m) <input type="number" id="cg-tape-m" step="0.005" min="0.5" placeholder="tape it" style="width:7em"></label>
          <button class="btn" id="cg-measure" disabled data-tip="cal.measure">Measure</button>
          <span class="small muted" id="cg-push-state"></span>
        </div>
        <p class="small good-result"><b>A good result:</b> all four wheels within about 1% of each other, and close to the 3 in on the drawing. One wheel far off the others is worn tread, or it slipped during the push.</p>
        <div id="cg-wheel-out"></div>
      </div>
      <div class="panel">
        <h2 data-tip="cal.spin">3. Check with a spin</h2>
        <p class="small">After the positions and wheel sizes are in, run the <b>Spin</b> test on the floor (Tune tab). Turning on the spot, the gyro's turn rate against the wheels' speeds says whether the two agree as a whole.</p>
        <div class="row"><button class="btn" id="cg-spin" data-tip="cal.spin-check">Check the newest floor spin</button></div>
        <p class="small good-result"><b>A good result:</b> the gyro and the wheels agree within a few percent. If they don't, recheck the module positions and wheel sizes before blaming the gyro.</p>
        <div id="cg-spin-out"></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="cal.gyro">4. Gyro</h2>
          <button class="btn" id="gy-practice" data-tip="cal.practice" data-quiet>Practice</button>
        </div>
        <p class="small">Where the gyro sits on the robot doesn't matter for localization: odometry uses only the heading, and every part of the robot turns by the same angle. What matters is how well it reads: does the heading creep while nothing moves, does a full turn read 360 degrees, and is it mounted level.</p>
        <ol class="small">
          <li><b>Standing still:</b> after the gyro has finished calibrating (the top bar), record a minute with nobody touching the robot.</li>
          <li><b>Full turns:</b> line a bumper edge up with a tape line on the floor. Start recording, then turn the robot counter-clockwise (seen from above) exactly that many full turns, with the sticks or by hand, and stop with the same edge back on the line. Press <b>Back on the line</b> (it appears once the recording starts).</li>
        </ol>
        <div class="row" style="flex-wrap:wrap">
          <button class="btn" id="gy-still" data-tip="cal.still">Record a minute still</button>
          <label class="small" data-tip="cal.turns">Full turns <input type="number" id="gy-turns" value="5" min="1" max="20" style="width:5em"></label>
          <button class="btn" id="gy-turn" data-tip="cal.turn">Start recording the turns</button>
          <button class="btn primary" id="gy-done" hidden data-tip="cal.done">Back on the line</button>
          <span class="small muted" id="gy-state"></span>
        </div>
        <p class="small good-result"><b>A good result:</b> under 0.5° a minute of drift standing still, and full turns that read within 1% of 360° each. The team corrects the scale only when it is more than 1% off.</p>
        <div id="gy-out"></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="cal.moi">5. Mass and moment of inertia</h2>
          <button class="btn" id="mi-practice" data-tip="cal.practice" data-quiet>Practice</button>
        </div>
        <p class="small">PathPlanner plans every auto from the robot's mass and its moment of inertia (how hard it is to start and stop turning). Weigh the robot with bumpers and battery. The moment of inertia can't be weighed: spinning the robot in place, with every wheel pushing along its circle, measures it against how hard the robot is to push in a straight line.</p>
        <div class="row" style="flex-wrap:wrap">
          <label class="small" data-tip="cal.mass">Mass with bumpers and battery (kg) <input type="number" id="mi-mass" step="0.1" min="10" max="80" style="width:7em"></label>
          <button class="btn" id="mi-mass-save" data-tip="cal.mass-save">Save the mass…</button>
          <span class="small" id="mi-now"></span>
        </div>
        <div id="mi-assumed" class="callout warn" hidden></div>
        <ol class="small">
          <li>Measure the feedforward on the floor first (Guide step 10, <b>Measure the feedforward</b>): this compares against it.</li>
          <li>Robot on the floor, at least a meter clear all round. Hold the deadman for about 20 seconds while it spins each way, slowly, then briskly.</li>
        </ol>
        <div class="row"><button class="btn primary" id="mi-run" data-tip="cal.moi-run">Spin and measure</button></div>
        <p class="small good-result"><b>A good result:</b> a fit the tool calls plausible: for a robot this size, a few kg·m². It saves the number for PathPlanner.</p>
        <div id="mi-out"></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="cal.camera">6. Camera positions</h2>
          <button class="btn" id="cc-practice" data-tip="cal.practice" data-quiet>Practice</button>
        </div>
        <p class="small">Every vision pose passes through where the code thinks the camera is. A degree of tilt it doesn't know about moves poses 3.5 cm at 2 m. So measure the mount with the camera itself: one tag on a wall, the robot square to it at a few measured spots.</p>
        <ol class="small">
          <li>Tape one AprilTag <b>flat on a wall</b>, its center at a measured height. FRC tags are 6.5 in across the black square; PhotonVision's tag size must match.</li>
          <li>Put the robot with the camera's side facing the wall, <b>square to it</b>: both bumper corners the same distance from the wall.</li>
          <li>Measure the wall to the robot's <b>center</b> (to the bumper, plus half the robot's length with bumpers), and how far the tag is left (+) or right (-) of the robot's center line, looking from the robot.</li>
          <li><b>Take a sighting</b> (2 s, robot still). Then move: closer, further, to each side. Three spots or more, then <b>Work it out</b>.</li>
        </ol>
        <div class="row" style="flex-wrap:wrap;gap:10px">
          <label class="small" data-tip="cal.cam">Camera <input id="cc-cam" value="front" style="width:8em"></label>
          <label class="small" data-tip="cal.tag">Tag ID <input type="number" id="cc-tag" value="1" min="0" style="width:5em"></label>
          <label class="small" data-tip="cal.side">Side facing the wall <select id="cc-side"><option>front</option><option>back</option><option>left</option><option>right</option></select></label>
          <label class="small" data-tip="cal.wall">Wall to center (m) <input type="number" id="cc-d" step="0.005" style="width:6em"></label>
          <label class="small" data-tip="cal.left">Tag left of center (m) <input type="number" id="cc-l" step="0.005" value="0" style="width:6em"></label>
          <label class="small" data-tip="cal.height">Tag height (m) <input type="number" id="cc-h" step="0.005" style="width:6em"></label>
          <button class="btn primary" id="cc-take" data-tip="cal.sight">Take a sighting</button>
        </div>
        <div id="cc-spots"></div>
        <div class="row"><button class="btn" id="cc-solve" disabled data-tip="cal.solve">Work it out</button><button class="btn" id="cc-clear" data-tip="cal.clear">Clear the spots</button></div>
        <p class="small good-result"><b>A good result:</b> three or more spots that agree with each other; the tool says how well. A spot that disagrees with the rest was probably measured wrong: remove it and take it again.</p>
        <div id="cc-out"></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="cal.field">7. Field tags</h2>
          <button class="btn" id="fs-practice" data-tip="cal.practice" data-quiet>Practice</button>
        </div>
        <p class="small">Tags on a real field are hung by people: a few centimeters off, a degree turned, now and then one on the wrong bracket. This measures where they really are, and the robot localizes with that instead. Measure the camera positions first.</p>
        <ol class="small">
          <li>On the field, robot disabled. Drive slowly (or push the robot) so the camera sees <b>two or more tags at once</b>, within about 4 m: in front of each hub face, the trenches, the outposts, the towers.</li>
          <li><b>Start recording</b>, cover every group of tags for a minute or two, then <b>Stop</b>.</li>
          <li><b>Work it out</b>. Only tags measured to have really moved are changed; the rest keep their official place.</li>
        </ol>
        <div class="row" style="flex-wrap:wrap">
          <button class="btn primary" id="fs-start" data-tip="cal.fs-start">Start recording</button>
          <button class="btn" id="fs-stop" disabled data-tip="cal.fs-stop">Stop</button>
          <label class="small" data-tip="cal.fs-variant">Field <select id="fs-variant"><option value="">Tell from the tags</option><option value="welded">Welded</option><option value="andymark">AndyMark</option></select></label>
          <button class="btn" id="fs-solve" data-tip="cal.fs-solve">Work it out</button>
          <span class="small muted" id="fs-state"></span>
        </div>
        <p class="small good-result"><b>A good result:</b> most tags where the field drawing puts them. Only tags measured to have moved by more than the noise change; a move over 30 cm is refused as a misread.</p>
        <div id="fs-out"></div>
      </div>
    </div>`;

  function findings(F) {
    return (F || []).map(f => `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
      <div class="why">${Learn.link(f.why, 2)}</div></div>`).join("");
  }

  function saveButton(id, edits) {
    return edits && edits.length ? `<button class="btn primary" id="${id}" data-tip="cal.save">Save to the robot files…</button>` : "";
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
    // No default: a distance nobody measured would become the wheel size.
    if (!(+$("#cg-tape-m", root).value > 0)) { App.toast("Type how far the robot moved, measured with the tape."); $("#cg-tape-m", root).focus(); return; }
    showWheels(await App.api("/api/geometry/wheels", { file: pushRun, tape_m: $("#cg-tape-m", root).value }));
  };
  $("#cg-wheel-practice", root).onclick = async () => showWheels(await App.api("/api/geometry/wheels", { practice: true }));

  // ---------------------------------------------------------------- gyro
  function showGyro(r, append) {
    const out = $("#gy-out", root);
    if (r.ok === false) { out.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    const head = r.kind === "still"
      ? `Standing still: drift ${fmt(Math.abs(r.drift_deg_per_min), 2)} degrees a minute${r.tilt_deg != null ? `, mounted ${fmt(r.tilt_deg, 1)} degrees off level` : ""}.`
      : r.scale_error != null ? `${r.turns} turns read ${fmt(Math.abs(r.delta_deg), 1)} degrees (${r.scale_error >= 0 ? "+" : ""}${fmt(r.scale_error * 100, 2)}%).` : "";
    const html = `${r.practice && !append ? `<div class="callout info">Practice: a made-up gyro that drifts a little, reads turns 1.5% short, and sits slightly off level.</div>` : ""}
      ${head ? `<p><b>${esc(head)}</b></p>` : ""}${findings(r.findings)}`;
    out.innerHTML = append ? out.innerHTML + html : html;
  }

  $("#gy-still", root).onclick = async () => {
    $("#gy-state", root).textContent = "Recording a minute: don't touch the robot.";
    try {
      const doc = await App.runTest("capture", "ALL", { duration_s: 60 });
      showGyro(await App.api("/api/gyro", { kind: "still", file: doc._file }));
      $("#gy-state", root).textContent = "";
    } catch (e) { $("#gy-state", root).textContent = e.message; }
  };
  $("#gy-turn", root).onclick = async () => {
    const turns = +$("#gy-turns", root).value || 5;
    $("#gy-state", root).textContent = `Recording: turn it ${turns} times counter-clockwise, then stop on the line.`;
    $("#gy-done", root).hidden = false;
    try {
      const doc = await App.runTest("capture", "ALL", { duration_s: 120 });
      showGyro(await App.api("/api/gyro", { kind: "turns", file: doc._file, turns }));
      $("#gy-state", root).textContent = "";
    } catch (e) { $("#gy-state", root).textContent = e.message; }
    $("#gy-done", root).hidden = true;
  };
  $("#gy-done", root).onclick = () => App.api("/api/stop", {});
  $("#gy-practice", root).onclick = async () => {
    showGyro(await App.api("/api/gyro", { kind: "still", practice: true }));
    showGyro(await App.api("/api/gyro", { kind: "turns", practice: true, turns: 5 }), true);
  };

  // ---------------------------------------------------------------- mass and moment of inertia
  function showInertia(doc) {
    const r = doc.report || doc, out = $("#mi-out", root);
    const a = (r.measured || {}).angular || {};
    const act = r.next && r.next.action;
    out.innerHTML = `${doc.practice ? `<div class="callout info">Practice: a made-up robot of 55 kg whose moment of inertia is really 6.0 kg·m². Nothing here can be saved.</div>` : ""}
      <p><b>${esc(r.summary || "")}</b></p>
      ${a.ok ? `<p class="small muted">Turning: kS ${fmt(a.kS, 3)} V, kV ${fmt(a.kV, 3)} V per rad/s, kA ${fmt(a.kA, 3)} V per rad/s² (R² ${fmt(a.r2, 3)}).</p>` : ""}
      ${findings(r.findings)}
      ${act && act.type === "config" && !doc.practice ? `<button class="btn primary" id="mi-save">Save to swervetune.json…</button>` : ""}`;
    const b = $("#mi-save", out);
    if (b) b.onclick = () => App.previewAndSave({ kind: "edit", file: act.file, path: act.path, value: act.value }, "Moment of inertia");
  }

  async function showMass() {
    const lint = App.lint || await App.api("/api/lint");
    const s = (lint && lint.summary) || {};
    if (s.mass_kg) $("#mi-now", root).textContent = `Now: ${fmt(s.mass_kg, 1)} kg (${s.mass_source || ""})`;
    const assumed = /assumed/.test(s.mass_source || "");
    $("#mi-assumed", root).hidden = !assumed;
    if (assumed) $("#mi-assumed", root).textContent = `Not weighed yet: PathPlanner is planning every auto with an assumed ${fmt(s.mass_kg, 0)} kg. Weigh the robot with bumpers and battery, and save it here.`;
  }
  $("#mi-mass-save", root).onclick = async () => {
    const kg = +$("#mi-mass", root).value;
    if (!(kg >= 10 && kg <= 80)) { App.toast("Type the weighed mass in kilograms (10 to 80)."); return; }
    if (await App.previewAndSave({ kind: "edit", file: "swervetune.json", path: ["robotMassKg"], value: kg }, "Robot mass")) showMass();
  };
  $("#mi-run", root).onclick = async () => {
    if (!["FIELD", "SIM"].includes(App.env())) { App.toast("Set the environment to On the floor first (top bar)."); return; }
    $("#mi-out", root).innerHTML = `<p class="hint">Hold the deadman: spinning each way, slowly then briskly (about 20 s)…</p>`;
    try { showInertia(await App.runTest("spin_ff", "ALL", {})); } catch (e) { $("#mi-out", root).innerHTML = `<p class="hint">${esc(e.message)}</p>`; }
  };
  $("#mi-practice", root).onclick = async () => showInertia(await App.api("/api/practice", { loop: "spin_ff" }));
  App.on("tab", t => { if (t === "calibrate") showMass(); });

  // ---------------------------------------------------------------- camera positions
  const AXES = [{ k: "x", u: "m", d: 3 }, { k: "y", u: "m", d: 3 }, { k: "z", u: "m", d: 3 },
    { k: "roll", u: "°", d: 1 }, { k: "pitch", u: "°", d: 1 }, { k: "yaw", u: "°", d: 1 }];

  function paintSpots() {
    const box = $("#cc-spots", root);
    box.innerHTML = spots.length ? `<div class="tblwrap"><table class="t" style="width:auto"><thead><tr><th>#</th><th>Side</th><th>Wall to center</th><th>Tag left</th><th>Tag height</th><th>Tag</th><th>Sightings</th><th></th></tr></thead><tbody>
      ${spots.map((s, i) => `<tr><td>${i + 1}</td><td>${esc(s.side)}</td><td class="num mono">${fmt(s.distance_m, 3)} m</td><td class="num mono">${fmt(s.lateral_m, 3)} m</td>
        <td class="num mono">${fmt(s.height_m, 3)} m</td><td class="num">${s.tag_id}</td><td class="num">${s.count ?? (s.samples || []).length}</td>
        <td>${s.practice ? "" : `<button class="btn small" data-drop="${i}" aria-label="Remove spot ${i + 1}">Remove</button>`}</td></tr>`).join("")}
      </tbody></table></div>` : "";
    $$("[data-drop]", box).forEach(b => b.onclick = () => { spots.splice(+b.dataset.drop, 1); paintSpots(); });
    $("#cc-solve", root).disabled = !spots.some(s => !s.practice);
  }

  function showMount(r) {
    const out = $("#cc-out", root);
    if (!r.ok) { out.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    const res = r.result, cur = r.current, truth = r.true_mount;
    out.innerHTML = `${r.practice ? `<div class="callout info">Practice: three made-up spots of a camera whose real mount is known (last column). Nothing here can be saved.</div>` : ""}
      ${res ? `<div class="tblwrap"><table class="t" style="width:auto"><thead><tr><th></th><th>Now in swervetune.json</th><th>Measured</th>${truth ? "<th>Really</th>" : ""}</tr></thead><tbody>
        ${AXES.map(({ k, u, d }) => `<tr><td>${k}</td><td class="num mono">${cur && cur[k] != null ? fmt(cur[k], d) + " " + u : "–"}</td>
          <td class="num mono"><b>${fmt(res[k], d)} ${u}</b></td>${truth ? `<td class="num mono">${fmt(truth[k], d)} ${u}</td>` : ""}</tr>`).join("")}
      </tbody></table></div>
      <p class="small muted">From ${r.spread.spots} spot${r.spread.spots === 1 ? "" : "s"}; they agree within ${fmt(r.spread.cm, 1)} cm and ${fmt(r.spread.deg, 1)}°. Pitch is negative when the camera looks up.</p>` : ""}
      ${findings(r.findings)}${r.edits && !r.practice ? saveButton("cc-save", r.edits) : ""}`;
    const b = $("#cc-save", out);
    if (b) b.onclick = () => App.previewAndSave({ kind: "edits", edits: r.edits }, "Camera position for " + r.camera);
  }

  $("#cc-take", root).onclick = async () => {
    spots = spots.filter(s => !s.practice);
    const spot = { side: $("#cc-side", root).value, distance_m: +$("#cc-d", root).value, lateral_m: +$("#cc-l", root).value,
      height_m: +$("#cc-h", root).value, tag_id: +$("#cc-tag", root).value };
    if (!(spot.distance_m > 0 && spot.height_m > 0)) { App.toast("Type the wall distance and the tag height first."); return; }
    $("#cc-take", root).disabled = true;
    try {
      const r = await App.api("/api/camcal/sample", { camera: $("#cc-cam", root).value, tag_id: spot.tag_id, seconds: 2 });
      if (!r.ok) { App.toast(r.error, 6000); return; }
      if (!r.count) { $("#cc-out", root).innerHTML = `<p class="hint">${esc(r.hint)}</p>`; return; }
      spots.push(Object.assign(spot, { samples: r.samples }));
      paintSpots();
    } finally { $("#cc-take", root).disabled = false; }
  };
  $("#cc-solve", root).onclick = async () => showMount(await App.api("/api/camcal/solve", { camera: $("#cc-cam", root).value, placements: spots.filter(s => !s.practice) }));
  $("#cc-clear", root).onclick = () => { spots = []; paintSpots(); $("#cc-out", root).innerHTML = ""; };
  $("#cc-practice", root).onclick = async () => {
    const r = await App.api("/api/camcal/solve", { camera: "practice", practice: true });
    spots = (r.placements || []).map(p => Object.assign(p, { practice: true }));
    paintSpots();
    showMount(r);
  };

  // ---------------------------------------------------------------- field survey
  async function surveyState() {
    const r = await App.api("/api/survey/state");
    $("#fs-state", root).textContent = `${r.running ? "Recording: " : ""}${r.sightings} sightings, ${r.views} views with two or more tags, ${r.tags.length} tags seen`;
    $("#fs-start", root).disabled = r.running;
    $("#fs-stop", root).disabled = !r.running;
    if (!r.running) { clearInterval(surveyTimer); surveyTimer = null; }
  }

  function fieldMap(r) {
    const f = r.field, W = 760, H = Math.round(W * f.width / f.length), k = W / f.length, EX = 20, MAXPX = 60;
    const X = x => x * k, Y = y => H - y * k;
    const rows = Object.fromEntries((r.rows || []).map(x => [x.id, x]));
    const labels = [];   // tags within a label's height of each other share one label
    const marks = Object.entries(r.official).map(([id, o]) => {
      const row = rows[id], cls = !row ? "unseen" : !row.measured ? "lone" : !row.trusted ? "bad" : row.significant ? "moved" : "ok";
      const a = o.yaw * Math.PI / 180, nx = Math.cos(a) * 9, ny = Math.sin(a) * 9;
      const near = labels.find(l => Math.hypot(l.x - X(o.x), l.y - Y(o.y)) < 14);
      if (near) near.ids.push(id); else labels.push({ x: X(o.x), y: Y(o.y), ids: [id] });
      let arrow = "";
      if (row && row.measured && (row.significant || !row.trusted)) {
        let dx = row.dx_cm / 100 * EX * k, dy = -row.dy_cm / 100 * EX * k;
        const len = Math.hypot(dx, dy);
        if (len > MAXPX) { dx *= MAXPX / len; dy *= MAXPX / len; }   // a wild one still fits the map
        arrow = `<line x1="${X(o.x)}" y1="${Y(o.y)}" x2="${X(o.x) + dx}" y2="${Y(o.y) + dy}" class="fs-arrow ${cls}"></line>`;
      }
      const tip = row ? `Tag ${id}: ${row.measured ? `${fmt(row.moved_cm, 1)} cm, ${fmt(row.turned_deg, 1)}° from official (±${fmt(row.sigma_cm, 1)} cm, ${row.views} views)` : "seen, not measured"}` : `Tag ${id}: not seen`;
      return `<g class="fs-tag ${cls}"><title>${esc(tip)}</title>${arrow}
        <line x1="${X(o.x)}" y1="${Y(o.y)}" x2="${X(o.x) + nx}" y2="${Y(o.y) - ny}" class="fs-face"></line>
        <circle cx="${X(o.x)}" cy="${Y(o.y)}" r="5"></circle></g>`;
    }).join("");
    const text = labels.map(l => `<text x="${l.x + 7}" y="${l.y - 7}" class="fs-label">${l.ids.join(", ")}</text>`).join("");
    return `<svg viewBox="-12 -16 ${W + 60} ${H + 30}" class="fs-map" role="img" aria-label="Field map of AprilTags and how far each was measured from its official place">
      <rect x="0" y="0" width="${W}" height="${H}" class="fs-field"></rect>${marks}${text}</svg>
      <p class="hint">Arrows show how far a tag moved, drawn ${EX} times longer (the longest are cut short). Hover a tag for its numbers.
        <span class="fs-key ok">official</span> <span class="fs-key moved">moved</span> <span class="fs-key bad">refused</span> <span class="fs-key lone">not measured</span> <span class="fs-key unseen">not seen</span></p>`;
  }

  function showSurvey(r) {
    const out = $("#fs-out", root);
    if (r.ok === false) { out.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    const moved = (r.rows || []).filter(x => x.measured && (x.significant || !x.trusted));
    out.innerHTML = `${r.practice ? `<div class="callout info">Practice: a made-up drive on a field with three tags moved (4 cm, 2.7 cm, a 3° turn) and one on the wrong bracket. Nothing here can be saved.</div>` : ""}
      ${r.official ? fieldMap(r) : ""}
      ${moved.length ? `<div class="tblwrap"><table class="t" style="width:auto"><thead><tr><th>Tag</th><th>Moved</th><th>x / y / z</th><th>Turned</th><th>±</th><th>Views</th><th></th></tr></thead><tbody>
        ${moved.map(x => `<tr><td>${x.id}</td><td class="num mono">${fmt(x.moved_cm, 1)} cm</td>
          <td class="num mono">${fmt(x.dx_cm, 1)} / ${fmt(x.dy_cm, 1)} / ${fmt(x.dz_cm, 1)}</td><td class="num mono">${fmt(x.turned_deg, 1)}°</td>
          <td class="num mono small">${fmt(x.sigma_cm, 1)} cm, ${fmt(x.sigma_deg, 1)}°</td><td class="num">${x.views}</td>
          <td>${x.trusted ? `<span class="chip warn">corrected</span>` : `<span class="chip bad">kept official</span>`}</td></tr>`).join("")}
      </tbody></table></div>` : ""}
      ${findings(r.findings)}
      ${r.layout_text && !r.practice && moved.some(x => x.trusted) ? `<button class="btn primary" id="fs-save">Save the surveyed layout (${esc(r.path || "")})…</button>` : ""}`;
    const b = $("#fs-save", out);
    if (b) b.onclick = async () => {
      if (!(await App.previewAndSave({ kind: "layout", text: r.layout_text }, "Surveyed AprilTag layout"))) return;
      // The robot starts from the official layout this field is built like; the survey moves tags on it.
      if (r.variant) await App.previewAndSave({ kind: "edit", file: "swervetune.json", path: ["vision", "field"], value: r.variant },
        `This field is the ${r.variant === "andymark" ? "AndyMark" : "welded"} one`);
    };
  }

  $("#fs-start", root).onclick = async () => {
    const r = await App.api("/api/survey/start", {});
    if (!r.ok) { App.toast(r.error, 6000); return; }
    clearInterval(surveyTimer);
    surveyTimer = setInterval(surveyState, 1000);
    surveyState();
  };
  $("#fs-stop", root).onclick = async () => { await App.api("/api/survey/stop", {}); surveyState(); };
  $("#fs-solve", root).onclick = async () => {
    $("#fs-out", root).innerHTML = `<p class="hint">Working it out (a few seconds)…</p>`;
    showSurvey(await App.api("/api/survey/solve", { variant: $("#fs-variant", root).value }));
  };
  $("#fs-practice", root).onclick = async () => {
    $("#fs-out", root).innerHTML = `<p class="hint">Working it out (a few seconds)…</p>`;
    showSurvey(await App.api("/api/survey/solve", { practice: true }));
  };

  // ---------------------------------------------------------------- spin
  $("#cg-spin", root).onclick = async () => {
    const real = wheels && !wheels.practice && wheels.average_in ? wheels.configured_in / wheels.average_in : 1;
    const r = await App.api("/api/geometry/spin?configured_over_real=" + real);
    $("#cg-spin-out", root).innerHTML = (r.run ? `<p class="small muted">From ${esc(r.run)}${real !== 1 ? `, with the wheel sizes just measured taken out` : ""}.</p>` : "") + findings(r.findings);
  };
})();
