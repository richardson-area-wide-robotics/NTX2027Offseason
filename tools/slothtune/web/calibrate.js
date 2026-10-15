// Calibrate tab: measuring the robot itself - where the modules are and how big the wheels really
// are - so odometry starts from the truth. Each tool says what it can and can't measure.
"use strict";

(() => {
  const root = $("#tab-calibrate");
  let pushRun = null, wheels = null;
  let spots = [], surveyTimer = null;

  root.innerHTML = `
    <div class="jobs" data-jobs="calibrate">
      ${HowTo.slot("calibrate")}
      <div class="job-area">
      <div class="panel" id="cal-positions">
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
            ${HowTo.steps({ need: "A tape measure. The robot anywhere, disabled.",
              steps: ["Measure between the <b>centers of the wheels</b>, not the frame: the wheels sit inside it.",
                "Wheelbase is front axle to back axle; track width is the middle of a left wheel to the middle of the right one. Inches, to the nearest 1/8.",
                "Type both and press <b>Compare with the files</b>. If a module moves, <b>Save to the robot files</b>, then redeploy."],
              good: "every module within about 1/8 in of the files. A bigger difference means the code has a wrong number." })}
            <div class="row" style="flex-wrap:wrap">
              <label class="small" data-tip="cal.wb">Wheelbase (in) <input type="number" id="cg-wb" step="0.125" min="6" max="40" style="width:7em"></label>
              <label class="small" data-tip="cal.tw">Track width (in) <input type="number" id="cg-tw" step="0.125" min="6" max="40" style="width:7em"></label>
              <button class="btn" id="cg-tape" data-tip="cal.compare">Compare with the files</button>
            </div>
            <div id="cg-tape-out"></div>
            ${HowTo.nextLine("positions")}
          </div>
        </div>
      </div>
      <div class="panel" id="cal-wheels">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="cal.wheels">2. Wheel sizes</h2>
          <button class="btn" id="cg-wheel-practice" data-tip="cal.practice" data-quiet>Practice</button>
        </div>
        <div data-faults="wheels"></div>
        ${HowTo.block(`<p class="small">Tread wears and compresses, and every distance odometry reports is wheel turns times the wheel size. With the motors coasting, a push makes each wheel roll freely over the same ground, so each one's count against a tape measure is its real size. Driving can't measure this: the speed loop makes every wheel report the speed it was asked for.</p>
        <ol class="small">
          <li>Robot <b>on the floor and disabled</b>. Mark a start and an end <b>10 ft</b> (120 in) apart along a straight line.</li>
          <li>Point every wheel straight ahead.</li>
          <li>Press <b>Record the push</b> (20 s, motors coast), then push the robot slowly and straight from mark to mark. Push on the frame, near the middle, so it doesn't twist.</li>
          <li>Type how far one point of the robot really moved, then <b>Measure</b>.</li>
        </ol>
        <p class="small good-result"><b>A good result:</b> all four wheels within about 1% of each other, and close to the 3 in on the drawing. One wheel far off the others is worn tread, or it slipped during the push.</p>`)}
        <div class="row" style="flex-wrap:wrap">
          <button class="btn primary" id="cg-push" data-tip="cal.push">Record the push</button>
          <label class="small" data-tip="cal.distance">Distance moved (in) <input type="number" id="cg-tape-in" step="0.125" min="20" placeholder="tape it" style="width:7em"></label>
          <button class="btn" id="cg-measure" disabled data-tip="cal.measure">Measure</button>
          <span class="small muted" id="cg-push-state"></span>
        </div>
        <div id="cg-wheel-out"></div>
        ${HowTo.nextLine("wheels")}
      </div>
      <div class="panel" id="cal-spin">
        <h2 data-tip="cal.spin">3. Check with a spin</h2>
        <div data-faults="spin"></div>
        ${HowTo.steps({ steps: ["After the positions and wheel sizes are in, run the <b>Spin</b> test on the floor (Tune drive train, or the Guide's Spin check).",
          "Press <b>Check the newest floor spin</b>: turning on the spot, the gyro's turn rate against the wheels' speeds says whether the two agree as a whole."],
          good: "the gyro and the wheels agree within a few percent. If they don't, recheck the module positions and wheel sizes before blaming the gyro." })}
        <div class="row"><button class="btn" id="cg-spin" data-tip="cal.spin-check">Check the newest floor spin</button></div>
        <div id="cg-spin-out"></div>
        ${HowTo.nextLine("spin")}
      </div>
      <div class="panel" id="cal-gyro">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="cal.gyro">4. Gyro</h2>
          <button class="btn" id="gy-practice" data-tip="cal.practice" data-quiet>Practice</button>
        </div>
        <div data-faults="gyro"></div>
        <div id="cg-box" class="cg-box"></div>
        ${HowTo.block(`<p class="small">Where the gyro sits on the robot doesn't matter for localization: odometry uses only the heading, and every part of the robot turns by the same angle. What matters is how well it reads: does the heading creep while nothing moves, does a full turn read 360 degrees, and is it mounted level.</p>
        <ol class="small">
          <li><b>Standing still:</b> after the gyro has finished calibrating (the top bar), record a minute with nobody touching the robot.</li>
          <li><b>Full turns:</b> line a bumper edge up with a tape line on the floor. Start recording, then turn the robot counter-clockwise (seen from above) exactly that many full turns, with the sticks or by hand, and stop with the same edge back on the line. Press <b>Back on the line</b> (it appears once the recording starts).</li>
        </ol>
        <p class="small good-result"><b>A good result:</b> under 0.5° a minute of drift standing still, and full turns that read within 1% of 360° each. The team corrects the scale only when it is more than 1% off.</p>`)}
        <div class="row" style="flex-wrap:wrap">
          <button class="btn" id="gy-still" data-tip="cal.still">Record a minute still</button>
          <label class="small" data-tip="cal.turns">Full turns <input type="number" id="gy-turns" value="5" min="1" max="20" style="width:5em"></label>
          <button class="btn" id="gy-turn" data-tip="cal.turn">Start recording the turns</button>
          <button class="btn primary" id="gy-done" hidden data-tip="cal.done">Back on the line</button>
          <span class="small muted" id="gy-state"></span>
        </div>
        <div id="gy-out"></div>
        ${HowTo.nextLine("gyro")}
      </div>
      <div class="panel" id="cal-moi">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="cal.moi">5. Mass and moment of inertia</h2>
          <button class="btn" id="mi-practice" data-tip="cal.practice" data-quiet>Practice</button>
        </div>
        <div data-faults="moi"></div>
        ${HowTo.block(`<p class="small">PathPlanner plans every auto from the robot's mass and its moment of inertia (how hard it is to start and stop turning). Weigh the robot with bumpers and battery. The moment of inertia can't be weighed: spinning the robot in place, with every wheel pushing along its circle, measures it against how hard the robot is to push in a straight line.</p>`, "What it's for")}
        <div class="row" style="flex-wrap:wrap">
          <label class="small" data-tip="cal.mass">Weight with bumpers and battery (lb) <input type="number" id="mi-mass" step="0.5" min="22" max="176" style="width:7em"></label>
          <button class="btn" id="mi-mass-save" data-tip="cal.mass-save">Save the mass…</button>
          <span class="small" id="mi-now"></span>
        </div>
        <div id="mi-assumed" class="callout warn" hidden></div>
        ${HowTo.steps({ steps: ["Weigh the robot with bumpers and battery; type it and <b>Save the mass</b>.",
          "Measure the feedforward on the floor first (Guide step 10, <b>Measure the feedforward</b>): this compares against it.",
          "Robot on the floor, at least 3 ft clear all round. Press <b>Spin and measure</b> and hold the deadman for about 20 seconds while it spins each way, slowly, then briskly."],
          good: "a fit the tool calls plausible: for a robot this size, roughly 10,000 to 25,000 lb·in². It saves the number for PathPlanner." })}
        <div class="row"><button class="btn primary" id="mi-run" data-tip="cal.moi-run">Spin and measure</button></div>
        <div id="mi-out"></div>
        ${HowTo.nextLine("moi")}
      </div>
      <div class="panel" id="cal-lens">
        <h2 data-tip="cal.lens">6. Camera lens</h2>
        ${HowTo.block(`<p class="small">Every pose is only as good as the camera's lens calibration, and a Luma ships with none. PhotonVision measures the lens from pictures of the team's ChArUco board, at each resolution separately: calibrate at the one the AprilTag pipeline uses.</p>
        <ol class="small">
          <li>Find the board: the one drawn here. Check a square with a ruler: 1 inch.</li>
          <li>Open the camera's PhotonVision page (port 5800), <b>Cameras</b>, <b>Calibration</b>. Pick the pipeline's resolution and set the board as in the table.</li>
          <li>Lay the board <b>flat</b> and still. Take at least 12 snapshots: near and far, tilted every way, the board in every part of the picture including the corners. Never square-on to the lens. Only take one when the overlay lines up with the board.</li>
          <li>Press <b>Calibrate</b>. Then record it here, with the resolution and the mean error PhotonVision shows.</li>
        </ol>
        <p class="small good-result"><b>A good result:</b> a low mean error, in pixels, and the snapshots spread over the whole picture. One snapshot far worse than the rest: delete it and calibrate again.</p>`)}
        <div class="cal-lens">
          <figure class="board-fig">${boardSvg()}
            <figcaption class="small muted">The board: 9 × 11 in, 8 × 8 squares. Markers drawn for illustration; yours have their own patterns.</figcaption></figure>
          <div>
            <div id="cm-box" class="cm-box"></div>
            <table class="t lens-set"><thead><tr><th>PhotonVision setting</th><th>Set to</th></tr></thead><tbody>
              <tr><td>Board type</td><td class="mono">ChArUco</td></tr>
              <tr><td>Tag family</td><td class="mono">4x4</td></tr>
              <tr><td>Pattern spacing (a square)</td><td class="mono">1.00 in</td></tr>
              <tr><td>Marker size</td><td class="mono">0.75 in</td></tr>
              <tr><td>Board width × height</td><td class="mono">8 × 8</td></tr>
              <tr><td>Old OpenCV pattern</td><td class="mono">off</td></tr></tbody></table>
            <p class="small muted">If your ruler says a square isn't 1 in, type what it is as the pattern spacing, and the marker's own width as the marker size.</p>
            <div class="row" style="flex-wrap:wrap;gap:10px">
              <label class="small" data-tip="cal.cam">Camera <input id="cl-cam" value="front" style="width:7em"></label>
              <label class="small" data-tip="cal.lens-res">Resolution <input id="cl-res" placeholder="1280x800" style="width:7em"></label>
              <label class="small" data-tip="cal.lens-err">Mean error <input id="cl-err" inputmode="decimal" style="width:4em"> px</label>
              <button class="btn primary" id="cl-done" data-tip="cal.lens-done">Record it</button>
            </div>
            <div id="cl-out" class="small"></div>
          </div>
        </div>
        ${HowTo.nextLine("lens")}
      </div>
      <div class="panel" id="cal-camera">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="cal.camera">7. Camera positions</h2>
          <button class="btn" id="cc-practice" data-tip="cal.practice" data-quiet>Practice</button>
        </div>
        ${HowTo.block(`<p class="small">Every vision pose passes through where the code thinks the camera is. A degree of tilt it doesn't know about moves poses about 1.5 in at 7 ft. So measure the mount with the camera itself: one tag on a wall, the robot square to it at a few measured spots.</p>
        <ol class="small">
          <li>Tape one AprilTag <b>flat on a wall</b>, its center at a measured height. FRC tags are 6.5 in across the black square; PhotonVision's tag size must match.</li>
          <li>Put the robot with the camera's side facing the wall, <b>square to it</b>: both bumper corners the same distance from the wall.</li>
          <li>Measure the wall to the robot's <b>center</b> (to the bumper, plus half the robot's length with bumpers), and how far the tag is left (+) or right (-) of the robot's center line, looking from the robot.</li>
          <li><b>Take a sighting</b> (2 s, robot still). Then move: closer, further, to each side. Three spots or more, then <b>Work it out</b>.</li>
        </ol>
        <p class="small good-result"><b>A good result:</b> three or more spots that agree with each other; the tool says how well. A spot that disagrees with the rest was probably measured wrong: remove it and take it again.</p>
        <figure class="cam-lens-fig">
          <img src="img/parts/luma-p1.svg" alt="A Luma P1 from the lens side" width="274.36" height="167.96">
          <figcaption class="small">To check the answer with a tape, measure to the middle of the lens. On a <b>Luma P1</b> it is
            centered across, 0.16 in (4 mm) off the middle of the four holes toward the edge away from the name, and its front is 0.12 in (3 mm)
            out from the case (±0.06 in: it screws in and out to focus). From <a href="https://docs.luma.vision/p1/files/P1%20Assembly%20Public%20Drawing.pdf" target="_blank" rel="noopener">Luma's drawing</a>.</figcaption>
        </figure>`)}
        <div class="row" style="flex-wrap:wrap;gap:10px">
          <label class="small" data-tip="cal.cam">Camera <input id="cc-cam" value="front" style="width:8em"></label>
          <label class="small" data-tip="cal.tag">Tag ID <input type="number" id="cc-tag" value="1" min="0" style="width:5em"></label>
          <label class="small" data-tip="cal.side">Side facing the wall <select id="cc-side"><option>front</option><option>back</option><option>left</option><option>right</option></select></label>
          <label class="small" data-tip="cal.wall">Wall to center (in) <input type="number" id="cc-d" step="0.125" style="width:6em"></label>
          <label class="small" data-tip="cal.left">Tag left of center (in) <input type="number" id="cc-l" step="0.125" value="0" style="width:6em"></label>
          <label class="small" data-tip="cal.height">Tag height (in) <input type="number" id="cc-h" step="0.125" style="width:6em"></label>
          <button class="btn primary" id="cc-take" data-tip="cal.sight">Take a sighting</button>
        </div>
        <div id="cc-spots"></div>
        <div class="row"><button class="btn" id="cc-solve" disabled data-tip="cal.solve">Work it out</button><button class="btn" id="cc-clear" data-tip="cal.clear">Clear the spots</button></div>
        <div id="cc-out"></div>
        ${HowTo.nextLine("camera")}
      </div>
      <div class="panel" id="cal-field">
        <div class="row" style="justify-content:space-between;flex-wrap:wrap">
          <h2 data-tip="cal.field">8. Field tags</h2>
          <button class="btn" id="fs-practice" data-tip="cal.practice" data-quiet>Practice</button>
        </div>
        ${HowTo.block(`<p class="small">Tags on a real field are hung by people: an inch or two off, a degree turned, now and then one on the wrong bracket. This measures where they really are, and the robot localizes with that instead. Measure the camera positions first.</p>
        <ol class="small">
          <li>On the field, robot disabled. Drive slowly (or push the robot) so the camera sees <b>two or more tags at once</b>, within about 13 ft: in front of each hub face, the trenches, the outposts, the towers.</li>
          <li><b>Start recording</b>, cover every group of tags for a minute or two, then <b>Stop</b>.</li>
          <li><b>Work it out</b>. Only tags measured to have really moved are changed; the rest keep their official place.</li>
          <li><b>Save the surveyed layout</b>, redeploy, and upload <span class="mono">surveyed.json</span> to each camera in PhotonVision: the camera solves its multi-tag poses itself.</li>
        </ol>
        <p class="small good-result"><b>A good result:</b> most tags where the field drawing puts them. Only tags measured to have moved by more than the noise change; a move over about 12 in is refused as a misread.</p>`)}
        <div class="row" style="flex-wrap:wrap">
          <button class="btn primary" id="fs-start" data-tip="cal.fs-start">Start recording</button>
          <button class="btn" id="fs-stop" disabled data-tip="cal.fs-stop">Stop</button>
          <label class="small" data-tip="cal.fs-variant">Field <select id="fs-variant"><option value="">Tell from the tags</option><option value="welded">Welded</option><option value="andymark">AndyMark</option></select></label>
          <button class="btn" id="fs-solve" data-tip="cal.fs-solve">Work it out</button>
          <span class="small muted" id="fs-state"></span>
        </div>
        <div id="fs-out"></div>
        ${HowTo.nextLine("field")}
      </div>
      <div class="panel" id="cal-newfield">
        <h2 data-tip="cal.newfield">9. New field</h2>
        ${HowTo.block(`<p class="small">At a new venue the lens is the same, but the light and the tags are not. With the field's match lighting on, do these three: the robot does the work, a person holds the deadman for the sweep.</p>
        <ol class="small">
          <li><b>Light.</b> Robot still, facing two or more tags 6 to 13 ft away. The tool sets the exposure short enough that a fast turn doesn't blur a tag, then tries the gain from low to high and keeps the lowest that sees the tags well, plus a margin. It stays on the camera; the old settings are kept to put back.</li>
          <li><b>Tags.</b> Robot on the floor (Where: on the floor), bumpers on, 3 ft clear all round, someone holding the deadman. <b>Sweep here</b> spins it slowly, a full turn each way, recording every tag it sees. Do it at two or three spots, then <b>Work out where the tags are</b> (step 8 saves the layout).</li>
          <li><b>Mount.</b> From the same sweeps: spinning in place, the vision pose should stay put. If it swings round, the camera's mount is off: measure it again in step 7.</li>
        </ol>
        <p class="small good-result"><b>A good result:</b> tags seen in nearly every frame at a low gain, most tags where the field drawing puts them, and the vision pose within about 1 in while it spins.</p>`)}
        <div class="nf-part"><h3 data-tip="cal.nf-light">1. Light</h3>
          <div class="row" style="flex-wrap:wrap"><button class="btn primary" id="nf-light" data-tip="cal.nf-light-go">Tune the camera to this light</button>
            <button class="btn" id="nf-light-stop" data-tip="cal.nf-light-stop" hidden>Stop</button>
            <button class="btn" id="nf-light-back" data-tip="cal.nf-light-back" hidden>Put the old settings back</button>
            <span class="small muted" id="nf-light-msg"></span></div>
          <div id="nf-light-out"></div></div>
        <div class="nf-part"><h3 data-tip="cal.nf-tags">2. Tags</h3>
          <div class="row" style="flex-wrap:wrap"><button class="btn primary" id="nf-sweep" data-tip="cal.nf-sweep">Sweep here</button>
            <button class="btn" id="nf-solve" data-tip="cal.fs-solve">Work out where the tags are</button>
            <button class="btn" id="nf-reset" data-tip="cal.nf-reset">Start over</button>
            <span class="small muted" id="nf-msg"></span></div>
          <div id="nf-sweeps" class="small"></div></div>
        <div class="nf-part"><h3 data-tip="cal.nf-mount">3. Mount</h3><div id="nf-mount" class="small"><span class="muted">After a sweep.</span></div></div>
      </div>
    </div></div>`;

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
    if (b) b.onclick = async () => {
      if (await App.previewAndSave({ kind: "edits", edits: r.edits }, "Module positions from the tape")) HowTo.mark("calibrate", "cal_positions", true, "Saved: redeploy.");
    };
    if (r.rows.length && r.rows.every(x => !x.change)) HowTo.mark("calibrate", "cal_positions", true, "Matches the files.");
    try { localStorage.setItem("slothtune.tape", JSON.stringify({ wb: $("#cg-wb", root).value, tw: $("#cg-tw", root).value })); } catch (e) { /* storage blocked */ }
  };
  try {
    const t = JSON.parse(localStorage.getItem("slothtune.tape") || "null");
    if (t) { $("#cg-wb", root).value = t.wb; $("#cg-tw", root).value = t.tw; }
  } catch (e) { /* storage blocked */ }

  // ---------------------------------------------------------------- wheel sizes
  function showWheels(r) {
    const out = $("#cg-wheel-out", root);
    wheels = r.ok ? r : null;
    if (!r.ok) { out.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    out.innerHTML = `${r.practice ? `<div class="callout info">Practice: a made-up push of about 10 ft with one worn wheel and one wheel turned a little. Nothing here can be saved.</div>` : ""}
      ${r.rows.length ? `<div class="tblwrap"><table class="t" style="width:auto"><thead><tr><th>Module</th><th>Encoder said</th><th>Wheel angle</th><th>Real diameter</th><th>Against the average</th></tr></thead><tbody>
        ${r.rows.map(x => `<tr><td>${esc(x.name)}</td><td class="num mono">${U.length(x.encoder_m, 1)}</td><td class="num mono">${fmt(x.angle_deg, 1)}°</td>
          <td class="num mono">${fmt(x.diameter_in, 3)} in</td>
          <td class="num mono ${Math.abs(x.vs_average) > 0.01 ? "warn-ink" : ""}">${x.vs_average >= 0 ? "+" : ""}${fmt(x.vs_average * 100, 1)}%</td></tr>`).join("")}
      </tbody></table></div>
      <p class="small muted">Average ${fmt(r.average_in, 3)} in; configured ${fmt(r.configured_in, 3)} in.</p>` : ""}
      ${findings(r.findings)}${r.practice ? "" : saveButton("cg-wheel-save", r.edits)}`;
    const b = $("#cg-wheel-save", out);
    if (b) b.onclick = async () => {
      if (await App.previewAndSave({ kind: "edits", edits: r.edits }, "Wheel diameter from the push")) HowTo.mark("calibrate", "cal_wheels", true, `${fmt(r.average_in, 3)} in, saved: redeploy.`);
    };
    if (!r.practice) {
      const bad = (r.findings || []).find(f => f.level === "error");
      if (bad) HowTo.mark("calibrate", "cal_wheels", false, bad.title);
      else if (!(r.edits || []).length) HowTo.mark("calibrate", "cal_wheels", true, `${fmt(r.average_in, 3)} in: matches the files.`);
    }
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
    // No default: a distance nobody measured would become the wheel size. Typed in inches, sent in meters.
    const tapeIn = +$("#cg-tape-in", root).value;
    if (!(tapeIn > 0)) { App.toast("Type how far the robot moved, in inches, measured with the tape."); $("#cg-tape-in", root).focus(); return; }
    showWheels(await App.api("/api/geometry/wheels", { file: pushRun, tape_m: U.mFromIn(tapeIn) }));
  };
  $("#cg-wheel-practice", root).onclick = async () => showWheels(await App.api("/api/geometry/wheels", { practice: true }));

  // ---------------------------------------------------------------- gyro
  // The robot's own gyro: what it is, and for a Canandgyro (the "Boron", next year's gyro) its
  // calibration, its light and its report rates. A navX calibrates only when it powers on.
  // A reading's name that explains itself on hover, focus or tap.
  const cgTerm = (key, text) => `<span class="term" tabindex="0" data-tip="${key}" data-quiet>${esc(text)}</span>`;
  const CG_RATES = [
    ["yawFramePeriodMs", cgTerm("cal.cg.yaw", "Yaw"), 10, 10],
    ["angularPositionFramePeriodMs", cgTerm("cal.cg.position", "Angular position"), 10, 20],
    ["angularVelocityFramePeriodMs", cgTerm("cal.cg.velocity", "Angular velocity"), 20, 100],
    ["accelerationFramePeriodMs", cgTerm("cal.cg.accel", "Acceleration"), 20, 100],
    ["statusFramePeriodMs", cgTerm("cal.cg.status", "Status"), 100, 100],
  ];
  function paintCanandgyro() {
    const box = $("#cg-box", root);
    if (!box) return;
    const L = App.connected() && App.live && App.live.live, g = (L && L.gyro) || [], d = (L && L.gyro_details) || {};
    const fitted = g[0] || "";
    const imu = ((((App.lint || {}).swervedrive || {}).imu) || {}).type || "";
    const cg = fitted === "Canandgyro" || imu.toLowerCase() === "canandgyro";
    const file = (((App.lint || {}).slothtune || {}).canandgyro) || {};
    const status = !fitted ? `<span class="muted">Connect to the robot to read its gyro.</span>`
      : `<b>${esc(fitted)}</b> · ${esc(g[1] || "")} · ${g[2] === "calibrating" ? `<span class="chip warn">calibrating: keep it still</span>` : esc(g[2] || "")}`
        + (d.temperature ? ` · ${esc(d.temperature)} °C` : "") + (d.firmware ? ` · firmware ${esc(d.firmware)}` : "")
        + (g[3] ? ` · <span class="bad-ink">${esc(g[3])}</span>` : "") + (d.sticky ? ` · <span class="warn-ink">earlier: ${esc(d.sticky)}</span>` : "");
    const can = fitted === "Canandgyro";
    const html = `<div class="row cg-status" style="flex-wrap:wrap"><span class="small" data-tip="cal.cg.status-line">${status}</span>
        <span class="lit small" tabindex="0" data-blink="${fitted === "navX" ? "navX" : "Canandgyro"}">its light</span></div>
      ${cg ? `<div class="row" style="flex-wrap:wrap">
        <button class="btn" id="cg-cal" data-tip="cal.cg.calibrate" ${can ? "" : "disabled"}>Calibrate it</button>
        <button class="btn" id="cg-blink" data-tip="cal.cg.identify" ${can ? "" : "disabled"}>Blink its light</button>
        <button class="btn" id="cg-clear" data-tip="cal.cg.clear" ${can ? "" : "disabled"}>Clear its sticky faults</button>
        <span class="small muted" id="cg-msg"></span></div>
      <details class="cg-rates"><summary data-tip="cal.cg.rates">Canandgyro report rates</summary>
        <p class="small">How often it sends each reading over CAN. YAGSL resets the gyro to its factory settings at every startup, so the robot code sets these again each time (not saved on the gyro). Saved to slothtune.json; they take effect when the robot code restarts.</p>
        <table class="t small"><thead><tr><th>Reading</th><th class="num">Every (ms)</th><th class="num">Redux default</th></tr></thead><tbody>
          ${CG_RATES.map(([k, name, ours, redux]) => `<tr><td>${name}</td>
            <td class="num"><input type="number" min="0" max="${k === "statusFramePeriodMs" ? 16383 : 65535}" step="1" data-cg="${k}" value="${file[k] != null ? file[k] : ours}" style="width:6em" data-tip="cal.cg.rate"></td>
            <td class="num">${redux}</td></tr>`).join("")}</tbody></table>
        <div class="row"><button class="btn" id="cg-save" data-tip="cal.cg.save">Save the report rates…</button></div>
      </details>` : `<p class="small muted">${fitted === "navX" ? "A navX calibrates itself when it powers on: keep the robot still for a few seconds after turning it on (its CAL light goes off when it's done)." : ""}</p>`}`;
    if (box._h === html) return;
    const open = $(".cg-rates", box) && $(".cg-rates", box).open;
    box._h = html;
    box.innerHTML = html;
    if (open && $(".cg-rates", box)) $(".cg-rates", box).open = true;
    const say = r => { const m = $("#cg-msg", box); if (m) m.textContent = r.ok ? r.message : (r.error || r.message || "It didn't work."); };
    if ($("#cg-cal", box)) $("#cg-cal", box).onclick = async () => say(await App.api("/api/gyro/command", { action: "calibrate" }));
    if ($("#cg-blink", box)) $("#cg-blink", box).onclick = async () => say(await App.api("/api/gyro/command", { action: "identify", seconds: 10 }));
    if ($("#cg-clear", box)) $("#cg-clear", box).onclick = async () => say(await App.api("/api/gyro/command", { action: "clear_faults" }));
    if ($("#cg-save", box)) $("#cg-save", box).onclick = () => {
      const edits = $$("[data-cg]", box).map(i => ({ file: "slothtune.json", path: ["canandgyro", i.dataset.cg], value: Math.max(0, Math.round(+i.value || 0)) }));
      App.previewAndSave({ kind: "edits", edits }, "Canandgyro report rates");
    };
  }
  App.on("live", () => { if (root.classList.contains("on")) paintCanandgyro(); });
  App.on("lint", paintCanandgyro);
  App.on("tab", t => { if (t === "calibrate") paintCanandgyro(); });

  function showGyro(r, append) {
    const out = $("#gy-out", root);
    if (r.ok === false) { out.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    const head = r.kind === "still"
      ? `Standing still: drift ${fmt(Math.abs(r.drift_deg_per_min), 2)} degrees a minute${r.tilt_deg != null ? `, mounted ${fmt(r.tilt_deg, 1)} degrees off level` : ""}.`
      : r.scale_error != null ? `${r.turns} turns read ${fmt(Math.abs(r.delta_deg), 1)} degrees (${r.scale_error >= 0 ? "+" : ""}${fmt(r.scale_error * 100, 2)}%).` : "";
    const html = `${r.practice && !append ? `<div class="callout info">Practice: a made-up gyro that drifts a little, reads turns 1.5% short, and sits slightly off level.</div>` : ""}
      ${head ? `<p><b>${esc(head)}</b></p>` : ""}${findings(r.findings)}`;
    out.innerHTML = append ? out.innerHTML + html : html;
    if (!r.practice && (r.kind === "still" || r.kind === "turns")) {
      const bad = (r.findings || []).find(f => f.level === "error" || f.level === "warn");
      HowTo.mark("calibrate", r.kind === "still" ? "cal_gyro_still" : "cal_gyro_turns", !bad, bad ? bad.title : head);
    }
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
    out.innerHTML = `${doc.practice ? `<div class="callout info">Practice: a made-up robot of 121 lb whose moment of inertia is really about 20,500 lb·in². Nothing here can be saved.</div>` : ""}
      <p><b>${esc(r.summary || "")}</b></p>
      ${a.ok ? `<p class="small muted">Turning, in the code's units: kS ${fmt(a.kS, 3)} V, kV ${fmt(a.kV, 3)} V per rad/s, kA ${fmt(a.kA, 3)} V per rad/s² (R² ${fmt(a.r2, 3)}).</p>` : ""}
      ${findings(r.findings)}
      ${act && act.type === "config" && !doc.practice ? `<button class="btn primary" id="mi-save" data-tip="cal.save">Save to slothtune.json…</button>` : ""}`;
    const b = $("#mi-save", out);
    if (b) b.onclick = () => App.previewAndSave({ kind: "edit", file: act.file, path: act.path, value: act.value }, "Moment of inertia");
  }

  async function showMass() {
    const lint = App.lint || await App.api("/api/lint");
    const s = (lint && lint.summary) || {};
    if (s.mass_kg) $("#mi-now", root).textContent = `Now: ${U.mass(s.mass_kg)} (${s.mass_source || ""})`;
    const assumed = /assumed/.test(s.mass_source || "");
    $("#mi-assumed", root).hidden = !assumed;
    if (!assumed) return;
    // Two different guesses: PathPlanner plans with its own robotMass (74 kg out of the box), and
    // this tool's estimates use its own assumption. Say both, so nobody thinks the autos use ours.
    const pp = await App.api("/api/ppcheck");
    const row = ((pp && pp.rows) || []).find(x => x.key === "robotMass");
    const theirs = row && row.pathplanner != null ? `PathPlanner plans every auto with ${U.mass(row.pathplanner)}${row.status === "unknown" ? " (its default)" : ""}, and this` : "This";
    $("#mi-assumed", root).textContent = `Not weighed yet: ${theirs} tool assumes ${U.mass(s.mass_kg)}. Weigh the robot with bumpers and battery, and save it here.`;
  }
  $("#mi-mass-save", root).onclick = async () => {
    // Typed in pounds; slothtune.json keeps kilograms (robotMassKg).
    const lb = +$("#mi-mass", root).value;
    if (!(lb >= 22 && lb <= 176)) { App.toast("Type the weighed robot in pounds (22 to 176)."); return; }
    const kg = +U.kgFromLb(lb).toFixed(3);
    if (await App.previewAndSave({ kind: "edit", file: "slothtune.json", path: ["robotMassKg"], value: kg }, "Robot mass")) showMass();
  };
  $("#mi-run", root).onclick = async () => {
    if (!["FIELD", "SIM"].includes(App.env())) { App.toast("Set the environment to On the floor first (top bar)."); return; }
    $("#mi-out", root).innerHTML = `<p class="hint">Hold the deadman: spinning each way, slowly then briskly (about 20 s)…</p>`;
    try { showInertia(await App.runTest("spin_ff", "ALL", {})); } catch (e) { $("#mi-out", root).innerHTML = `<p class="hint">${esc(e.message)}</p>`; }
  };
  $("#mi-practice", root).onclick = async () => showInertia(await App.api("/api/practice", { loop: "spin_ff" }));
  App.on("tab", t => { if (t === "calibrate") showMass(); });

  // The team's calibration board, drawn to scale so a person can tell they have the right one: a
  // 9 x 11 in board, an 8 x 8 checkerboard of 1 in squares, a 0.75 in ArUco marker in each white
  // square. The markers' patterns are illustrations; a real board's are its own.
  // (A function, not a constant: the page's HTML above draws it before this line runs.)
  function boardSvg() {
    const B = { w: 9, h: 11, n: 8, sq: 1, marker: 0.75 }, ox = (B.w - B.n * B.sq) / 2, oy = ox;
    let seed = 7;
    const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
    let cells = "";
    for (let r = 0; r < B.n; r++) {
      for (let c = 0; c < B.n; c++) {
        const x = ox + c * B.sq, y = oy + r * B.sq;
        if ((r + c) % 2 === 0) { cells += `<rect x="${x}" y="${y}" width="${B.sq}" height="${B.sq}" fill="#000"/>`; continue; }
        // A marker: a black border one cell wide around 4 x 4 cells of pattern.
        const m = B.marker, mx = x + (B.sq - m) / 2, my = y + (B.sq - m) / 2, k = m / 6;
        cells += `<rect x="${mx}" y="${my}" width="${m}" height="${m}" fill="#000"/>`;
        for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
          if (rnd() < 0.5) cells += `<rect x="${(mx + k * (j + 1)).toFixed(4)}" y="${(my + k * (i + 1)).toFixed(4)}" width="${k.toFixed(4)}" height="${k.toFixed(4)}" fill="#fff"/>`;
        }
      }
    }
    const g = oy + B.n * B.sq;
    return `<svg class="board-svg" viewBox="-1.2 -1 ${B.w + 1.6} ${B.h + 1.6}" role="img"
        aria-label="The calibration board: a 9 by 11 inch board with an 8 by 8 checkerboard of 1 inch squares, a small square marker in each white square, and its settings printed below">
      <rect x="0" y="0" width="${B.w}" height="${B.h}" fill="#fff" stroke="#888" stroke-width="0.04" rx="0.15"/>
      ${cells}
      <text x="${B.w / 2}" y="${g + 0.8}" text-anchor="middle" font-size="0.42" fill="#000">ChArUco 8 x 8</text>
      <text x="${B.w / 2}" y="${g + 1.4}" text-anchor="middle" font-size="0.32" fill="#333">1 in squares · 0.75 in markers · 4x4</text>
      <g class="board-dim">
        <line x1="0" y1="-0.45" x2="${B.w}" y2="-0.45"/><text x="${B.w / 2}" y="-0.6" text-anchor="middle">9 in</text>
        <line x1="-0.45" y1="0" x2="-0.45" y2="${B.h}"/><text x="-0.6" y="${B.h / 2}" text-anchor="middle" transform="rotate(-90 -0.6 ${B.h / 2})">11 in</text>
        <line x1="${ox}" y1="${g + 0.15}" x2="${ox + B.sq}" y2="${g + 0.15}"/>
      </g>
    </svg>`;
  }

  // The faults that would spoil each measurement: wheel sizes need the drive encoders, a spin and the
  // inertia every swerve motor and the gyro, the gyro checks the gyro.
  const FAULT_SCOPE = {
    wheels: { kind: "drive", what: "the drive motors" },
    spin: { kind: "swerve", gyro: true, what: "the swerve motors and the gyro" },
    gyro: { gyro: true, what: "the gyro" },
    moi: { kind: "swerve", gyro: true, what: "the swerve motors and the gyro" },
  };
  $$("[data-faults]", root).forEach(el => Faults.mount(el, FAULT_SCOPE[el.dataset.faults]));

  // A lens calibration done in PhotonVision, recorded for the checklist. Below a pixel is good; a
  // number well above it means snapshots that disagree.
  $("#cl-done", root).onclick = async () => {
    const cam = $("#cl-cam", root).value.trim(), res = $("#cl-res", root).value.trim(), err = parseFloat($("#cl-err", root).value);
    if (!cam || !res || !Number.isFinite(err)) { App.toast("Type the camera, the resolution and the mean error first."); return; }
    const ok = err <= 1.0;
    await HowTo.mark("calibrate", "cal_lens_" + cam, ok, `${res}, mean error ${err} px${ok ? "" : ": over 1 px, take the snapshots again"}`);
    $("#cl-out", root).innerHTML = ok ? `<span class="level ok">ok</span> Recorded: ${esc(cam)} at ${esc(res)}, ${esc(String(err))} px. Recalibrate if you change the resolution.`
      : `<span class="level warn">warn</span> ${esc(String(err))} px is high: delete the snapshots that stand out, or take a fresh set, and calibrate again.`;
  };

  // ---------------------------------------------------------------- camera positions
  // The mount is kept in meters and degrees (slothtune.json); x, y and z read in inches. An inch
  // figure gets a second decimal under an inch, where a tenth is a big share of it.
  const inch = m => m == null || !isFinite(m) ? "–" : U.length(m, Math.abs(U.inches(m)) < 1 ? 2 : 1);
  const cmIn = cm => cm == null || !isFinite(cm) ? "–" : fmt(cm / 2.54, Math.abs(cm / 2.54) < 1 ? 2 : 1);
  const AXES = [{ k: "x", show: inch }, { k: "y", show: inch }, { k: "z", show: inch },
    { k: "roll", show: v => fmt(v, 1) + " °" }, { k: "pitch", show: v => fmt(v, 1) + " °" }, { k: "yaw", show: v => fmt(v, 1) + " °" }];

  function paintSpots() {
    const box = $("#cc-spots", root);
    box.innerHTML = spots.length ? `<div class="tblwrap"><table class="t" style="width:auto"><thead><tr><th>#</th><th>Side</th><th>Wall to center</th><th>Tag left</th><th>Tag height</th><th>Tag</th><th>Sightings</th><th></th></tr></thead><tbody>
      ${spots.map((s, i) => `<tr><td>${i + 1}</td><td>${esc(s.side)}</td><td class="num mono">${inch(s.distance_m)}</td><td class="num mono">${inch(s.lateral_m)}</td>
        <td class="num mono">${inch(s.height_m)}</td><td class="num">${s.tag_id}</td><td class="num">${s.count ?? (s.samples || []).length}</td>
        <td>${s.practice ? "" : `<button class="btn small" data-drop="${i}" data-tip="cal.drop" data-quiet aria-label="Remove spot ${i + 1}">Remove</button>`}</td></tr>`).join("")}
      </tbody></table></div>` : "";
    $$("[data-drop]", box).forEach(b => b.onclick = () => { spots.splice(+b.dataset.drop, 1); paintSpots(); });
    $("#cc-solve", root).disabled = !spots.some(s => !s.practice);
  }

  function showMount(r) {
    const out = $("#cc-out", root);
    if (!r.ok) { out.innerHTML = `<p class="hint">${esc(r.error)}</p>`; return; }
    const res = r.result, cur = r.current, truth = r.true_mount;
    out.innerHTML = `${r.practice ? `<div class="callout info">Practice: three made-up spots of a camera whose real mount is known (last column). Nothing here can be saved.</div>` : ""}
      ${res ? `<div class="tblwrap"><table class="t" style="width:auto"><thead><tr><th></th><th>Now in slothtune.json</th><th>Measured</th>${truth ? "<th>Really</th>" : ""}</tr></thead><tbody>
        ${AXES.map(({ k, show }) => `<tr><td>${k}</td><td class="num mono">${cur && cur[k] != null ? show(cur[k]) : "–"}</td>
          <td class="num mono"><b>${show(res[k])}</b></td>${truth ? `<td class="num mono">${show(truth[k])}</td>` : ""}</tr>`).join("")}
      </tbody></table></div>
      <p class="small muted">From ${r.spread.spots} spot${r.spread.spots === 1 ? "" : "s"}; they agree within ${cmIn(r.spread.cm)} in and ${fmt(r.spread.deg, 1)}°. Pitch is negative when the camera looks up.</p>` : ""}
      ${findings(r.findings)}${r.edits && !r.practice ? saveButton("cc-save", r.edits) : ""}`;
    const b = $("#cc-save", out);
    if (b) b.onclick = async () => {
      if (await App.previewAndSave({ kind: "edits", edits: r.edits }, "Camera position for " + r.camera)) HowTo.mark("calibrate", "cal_camera_" + r.camera, true, "Measured and saved: redeploy.");
    };
  }

  $("#cc-take", root).onclick = async () => {
    spots = spots.filter(s => !s.practice);
    // Typed in inches; the spot (and the solve) keeps meters.
    const spot = { side: $("#cc-side", root).value, distance_m: U.mFromIn(+$("#cc-d", root).value), lateral_m: U.mFromIn(+$("#cc-l", root).value),
      height_m: U.mFromIn(+$("#cc-h", root).value), tag_id: +$("#cc-tag", root).value };
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
      const tip = row ? `Tag ${id}: ${row.measured ? `${cmIn(row.moved_cm)} in, ${fmt(row.turned_deg, 1)}° from official (±${cmIn(row.sigma_cm)} in, ${row.views} views)` : "seen, not measured"}` : `Tag ${id}: not seen`;
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
    out.innerHTML = `${r.practice ? `<div class="callout info">Practice: a made-up drive on a field with three tags moved (1.6 in, 1.1 in, a 3° turn) and one on the wrong bracket. Nothing here can be saved.</div>` : ""}
      ${r.official ? fieldMap(r) : ""}
      ${moved.length ? `<div class="tblwrap"><table class="t" style="width:auto"><thead><tr><th>Tag</th><th>Moved</th><th>x / y / z (in)</th><th>Turned</th><th>±</th><th>Views</th><th></th></tr></thead><tbody>
        ${moved.map(x => `<tr><td>${x.id}</td><td class="num mono">${cmIn(x.moved_cm)} in</td>
          <td class="num mono">${cmIn(x.dx_cm)} / ${cmIn(x.dy_cm)} / ${cmIn(x.dz_cm)}</td><td class="num mono">${fmt(x.turned_deg, 1)}°</td>
          <td class="num mono small">${cmIn(x.sigma_cm)} in, ${fmt(x.sigma_deg, 1)}°</td><td class="num">${x.views}</td>
          <td>${x.trusted ? `<span class="chip warn">corrected</span>` : `<span class="chip bad">kept official</span>`}</td></tr>`).join("")}
      </tbody></table></div>` : ""}
      ${findings(r.findings)}
      ${r.layout_text && !r.practice && moved.some(x => x.trusted) ? `<button class="btn primary" id="fs-save" data-tip="cal.save">Save the surveyed layout (${esc(r.path || "")})…</button>` : ""}`;
    const b = $("#fs-save", out);
    if (b) b.onclick = async () => {
      if (!(await App.previewAndSave({ kind: "layout", text: r.layout_text }, "Surveyed AprilTag layout"))) return;
      // The robot starts from the official layout this field is built like; the survey moves tags on it.
      if (r.variant) await App.previewAndSave({ kind: "edit", file: "slothtune.json", path: ["vision", "field"], value: r.variant },
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
  // ---------------------------------------------------------------- 9. New field
  // Light, tags and the mount: newfield.py on the server, the camera through CameraUI's connection.
  let nfTimer = null;
  function paintLight(L) {
    const out = $("#nf-light-out", root), msg = $("#nf-light-msg", root);
    if (!L || L.state === "none") return;
    msg.textContent = L.message || "";
    const running = L.state === "running";
    $("#nf-light", root).disabled = running;
    $("#nf-light-stop", root).hidden = !running;
    $("#nf-light-back", root).hidden = running || !L.before || !Object.keys(L.before).length;
    out.innerHTML = L.trials && L.trials.length ? `<table class="t small"><thead><tr><th class="num">Gain</th><th class="num">Frames with a tag</th>
        <th class="num">Tags a frame</th><th class="num">Ambiguity</th></tr></thead><tbody>${L.trials.map(t => `<tr class="${L.result && L.result.gain === t.gain ? "now" : ""}">
        <td class="num">${t.gain}</td><td class="num">${Math.round(t.seen * 100)}%</td><td class="num">${fmt(t.tags, 1)}</td>
        <td class="num">${t.ambiguity == null ? "–" : fmt(t.ambiguity, 2)}</td></tr>`).join("")}</tbody></table>
        <p class="small muted">Exposure ${L.exposure_us} µs: a fast turn smears a tag by a few pixels at most.</p>` : "";
  }
  function paintNewField(r) {
    if (!r || !r.ok) return;
    if (r.default_host && !App.cameraHost) App.cameraHost = r.default_host;
    $("#nf-msg", root).textContent = r.message || "";
    $("#nf-sweep", root).disabled = r.running;
    const sv = r.survey || {};
    $("#nf-sweeps", root).innerHTML = r.sweeps.length ? `${r.sweeps.length} sweep${r.sweeps.length === 1 ? "" : "s"}: ${r.sweeps.map(s =>
        `${esc(s.when)} ${s.outcome === "DONE" ? "done" : esc(s.outcome.toLowerCase())}`).join(", ")}. ${sv.sightings || 0} sightings of ${(sv.tags || []).length} tags, ${sv.views || 0} views with two or more.` : "";
    const m = r.mount;
    $("#nf-mount", root).innerHTML = !m ? `<span class="muted">After a sweep.</span>` : m.ok == null ? `<span class="level warn">warn</span> ${esc(m.why)}`
      : `<span class="level ${m.ok ? "ok" : "error"}">${m.ok ? "ok" : "error"}</span> ${esc(m.why)} <span class="muted">(${m.samples} poses; ${cmIn(m.spread_cm)} in, ${m.heading_offset_deg}°)</span>`;
    paintLight(r.lighting);
    if (m && m.ok != null) HowTo.mark("calibrate", "cal_newfield", m.ok, m.why);
  }
  async function pollNewField() {
    clearTimeout(nfTimer);
    const r = await App.api("/api/newfield");
    paintNewField(r);
    if (r && (r.running || (r.lighting && r.lighting.state === "running"))) nfTimer = setTimeout(pollNewField, 700);
  }
  $("#nf-light", root).onclick = async () => {
    const cam = CameraUI.info() && CameraUI.currentCam();
    if (!cam) { App.toast("Connect to the camera first: 6. Camera lens, Connect to the camera.", 6000); return; }
    const r = await App.api("/api/camera/lighting", { host: CameraUI.host(), camera: cam.unique });
    if (!r.ok) { $("#nf-light-msg", root).textContent = r.error; return; }
    pollNewField();
  };
  $("#nf-light-stop", root).onclick = () => App.api("/api/camera/lighting/stop", {}).then(pollNewField);
  $("#nf-light-back", root).onclick = () => App.api("/api/camera/lighting/restore", {}).then(pollNewField);
  $("#nf-sweep", root).onclick = async () => {
    const r = await App.api("/api/newfield/sweep", {});
    if (!r.ok) { $("#nf-msg", root).textContent = r.error; return; }
    pollNewField();
  };
  $("#nf-reset", root).onclick = () => App.api("/api/newfield/reset", {}).then(pollNewField);
  $("#nf-solve", root).onclick = async () => {
    // Step 8 works it out and saves it: show it there.
    showSurvey(await App.api("/api/survey/solve", { variant: $("#fs-variant", root).value }));
    const job = $('#tab-calibrate [data-rail-job="field"]');
    if (job) job.click();
  };
  App.on("tab", t => { if (t === "calibrate") pollNewField(); });
  CameraUI.mount($("#cm-box", root));
  $("#fs-practice", root).onclick = async () => {
    $("#fs-out", root).innerHTML = `<p class="hint">Working it out (a few seconds)…</p>`;
    showSurvey(await App.api("/api/survey/solve", { practice: true }));
  };

  // ---------------------------------------------------------------- spin
  $("#cg-spin", root).onclick = async () => {
    const real = wheels && !wheels.practice && wheels.average_in ? wheels.configured_in / wheels.average_in : 1;
    const r = await App.api("/api/geometry/spin?configured_over_real=" + real);
    $("#cg-spin-out", root).innerHTML = (r.run ? `<p class="small muted">From ${esc(r.run)}${real !== 1 ? `, with the wheel sizes just measured taken out` : ""}.</p>` : "") + findings(r.findings);
    // Another robot's spin is shown, never counted for this one.
    if (r.run && r.robot_match) {
      const bad = (r.findings || []).find(f => f.level === "error" || f.level === "warn");
      HowTo.mark("calibrate", "cal_spin", !bad, bad ? bad.title : "The gyro and the wheels agree.");
    }
  };
})();
