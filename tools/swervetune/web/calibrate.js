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
      <div class="panel">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2><span class="term" data-learn="camera_mount">Camera positions</span></h2>
          <button class="btn" id="cc-practice">Practice</button>
        </div>
        <p class="small">Every vision pose passes through where the code thinks the camera is. A degree of tilt it doesn't know about moves poses 3.5 cm at 2 m. So measure the mount with the camera itself: one tag on a wall, the robot square to it at a few measured spots.</p>
        <ol class="small">
          <li>Tape one AprilTag <b>flat on a wall</b>, its center at a measured height. FRC tags are 6.5 in across the black square; PhotonVision's tag size must match.</li>
          <li>Put the robot with the camera's side facing the wall, <b>square to it</b>: both bumper corners the same distance from the wall.</li>
          <li>Measure the wall to the robot's <b>center</b> (to the bumper, plus half the robot's length with bumpers), and how far the tag is left (+) or right (-) of the robot's center line, looking from the robot.</li>
          <li><b>Take a sighting</b> (2 s, robot still). Then move: closer, further, to each side. Three spots or more, then <b>Work it out</b>.</li>
        </ol>
        <div class="row" style="flex-wrap:wrap;gap:10px">
          <label class="small">Camera <input id="cc-cam" value="front" style="width:8em" aria-label="Camera name, as PhotonVision shows it"></label>
          <label class="small">Tag ID <input type="number" id="cc-tag" value="1" min="0" style="width:5em"></label>
          <label class="small">Side facing the wall <select id="cc-side"><option>front</option><option>back</option><option>left</option><option>right</option></select></label>
          <label class="small">Wall to center (m) <input type="number" id="cc-d" step="0.005" style="width:6em"></label>
          <label class="small">Tag left of center (m) <input type="number" id="cc-l" step="0.005" value="0" style="width:6em"></label>
          <label class="small">Tag height (m) <input type="number" id="cc-h" step="0.005" style="width:6em"></label>
          <button class="btn primary" id="cc-take">Take a sighting</button>
        </div>
        <div id="cc-spots"></div>
        <div class="row"><button class="btn" id="cc-solve" disabled>Work it out</button><button class="btn" id="cc-clear">Clear the spots</button></div>
        <div id="cc-out"></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2><span class="term" data-learn="field_survey">Field tags</span></h2>
          <button class="btn" id="fs-practice">Practice</button>
        </div>
        <p class="small">Tags on a real field are hung by people: a few centimeters off, a degree turned, now and then one on the wrong bracket. This measures where they really are, and the robot localizes with that instead. Measure the camera positions first.</p>
        <ol class="small">
          <li>On the field, robot disabled. Drive slowly (or push the robot) so the camera sees <b>two or more tags at once</b>, within about 4 m: in front of each hub face, the trenches, the outposts, the towers.</li>
          <li><b>Start recording</b>, cover every group of tags for a minute or two, then <b>Stop</b>.</li>
          <li><b>Work it out</b>. Only tags measured to have really moved are changed; the rest keep their official place.</li>
        </ol>
        <div class="row" style="flex-wrap:wrap">
          <button class="btn primary" id="fs-start">Start recording</button>
          <button class="btn" id="fs-stop" disabled>Stop</button>
          <label class="small">Field <select id="fs-variant"><option value="">Tell from the tags</option><option value="welded">Welded</option><option value="andymark">AndyMark</option></select></label>
          <button class="btn" id="fs-solve">Work it out</button>
          <span class="small muted" id="fs-state"></span>
        </div>
        <div id="fs-out"></div>
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
    if (b) b.onclick = () => App.previewAndSave({ kind: "layout", text: r.layout_text }, "Surveyed AprilTag layout");
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
