// Guide tab: the path from "it drives" to "it drives tight", one step at a time, in the order
// that keeps each step honest - signs before gains, blocks before floor, steering before speed.
//
// It opens on the first step not yet done, checks the robot is where that step needs it, and
// ticks a step only from what it measured on the real robot: the simulator and the practice pod
// teach, but never tick. Progress is kept for each robot (server: progress.py).
"use strict";

const Guide = (() => {
  const root = $("#tab-guide");
  let progress = { runs: {} }, active = null, picked = false, lastWhere = null, handView = "";
  // What a step last showed (a run's verdict, the offsets table), kept across repaints: a new run
  // or a lint refresh repaints the Guide, and must not wipe the result the student is reading.
  const shown = {};

  // The newest real result of a test, recorded by the server when the run was saved.
  const result = (test, env) => (progress.runs || {})[`${test}/${env}`];
  const graded = (test, env, pass = 100) => { const r = result(test, env); return !r ? "todo" : r.score >= pass ? "done" : "attention"; };
  const sim = () => App.connected() && (App.env() === "SIM" || App.state.target === "sim");

  // The swerve configuration's findings: PathPlanner's auto checks are for whoever writes the autos.
  const swerveLint = () => ((App.lint && App.lint.findings) || []).filter(f => !String(f.id || "").startsWith("pathplanner"));

  // env: where the robot must be. DISABLED means the Driver Station has it disabled; null means
  // the laptop alone. "where" is the plain description shown under the step's name.
  const STEPS = [
    { id: "connect", env: null, learn: ["control_loop", "gear_ratio", "current_limit"], title: "Connect and check the configuration", where: "Laptop, robot on",
      why: "Most swerve problems are a wrong number in a JSON file. The tool reads every file, does the physics, and lists what does not add up - before anything moves.",
      need: ["The laptop on the robot's network (or the simulator running)"],
      todo: ["Pick the robot code at the top (Black team or Peashooter).", "Press Connect.", "Read every red and yellow item in the Config tab. Fix the red swerve ones before going on; auto (PathPlanner) problems don't block swerve tuning."],
      status: () => !App.connected() ? "todo" : swerveLint().some(f => f.level === "error") ? "attention" : "done",
      body: () => {
        const f = swerveLint(), auto = ((App.lint && App.lint.findings) || []).length - f.length;
        const e = f.filter(x => x.level === "error").length, w = f.filter(x => x.level === "warn").length;
        const n = (k, word) => `<b>${k}</b> ${word}${k === 1 ? "" : "s"}`;
        return `<p>${App.connected() ? "Connected." : "Not connected."} The swerve configuration has ${n(e, "error")} and ${n(w, "warning")}${auto > 0 ? `, plus ${auto} auto (PathPlanner) item${auto === 1 ? "" : "s"} for whoever writes the autos` : ""}.</p>
          <div class="row"><button class="btn primary" data-go="config" data-tip="guide.config">Open the Config tab</button></div>`;
      } },

    { id: "health", env: "DISABLED", learn: ["quantization", "motor_encoder", "absolute_encoder"], title: "Sensor health", where: "Robot disabled",
      why: "A noisy encoder or a drifting gyro makes every later number wrong. Three seconds standing still finds a noisy or slipped encoder. A gyro's drift is too small to see in three seconds, so it gets a minute of its own in the Calibrate tab.",
      need: ["Robot on, disabled, not moving"],
      todo: ["Leave the robot completely still.", "Press Run health check.",
             "Once per robot, and after the gyro is moved: Calibrate tab, panel 4 (Gyro), Record a minute still."],
      run: { label: "Run health check", test: "capture", args: { duration_s: 3 }, record: "health" },
      status: () => progress.health === "pass" ? "done" : progress.health === "fail" ? "attention" : "todo" },

    { id: "hand", env: "DISABLED", learn: ["hand_check", "coast_mode", "inversion", "motor_encoder", "absolute_encoder", "gear_ratio"], title: "Hand check: every direction", where: "Robot disabled, motors coasting",
      why: "Every later test assumes it knows which way is positive. A backwards sign makes a module run away or fight the others, and it looks like a tuning problem. Turning things by hand finds it in a minute, with nothing powered.",
      need: ["Robot disabled", "Somewhere to stand at each corner"],
      todo: ["First turn every module so its wheel points straight ahead with the bevel gear (the gear on the side of the wheel) facing the robot's LEFT side. A module turned the other way reads backwards, and flipping its setting would hide the real mistake.",
             "Press Record wheels (20 s). Roll each wheel so its TOP moves toward the front of the robot, about one turn. Do all four, one direction only.",
             "Press Record steering (20 s). Turn each module counter-clockwise, seen from above, about a quarter turn. All four, one direction only.",
             "Every row must say AGREES, and 'motor per module' must be 1.00 ± 0.03."],
      status: () => progress.hand === "pass" ? "done" : progress.hand === "fail" ? "attention" : "todo",
      body: () => `<div class="row"><button class="btn primary" id="g-hw" data-tip="guide.hw">Record wheels</button><button class="btn primary" id="g-hs" data-tip="guide.hs">Record steering</button></div>
        <div id="g-hand" class="verdicts">${handView}</div>`,
      mount: box => {
        const go = async (kind) => {
          try {
            App.toast(kind === "wheel" ? "Recording: roll each wheel forward now." : "Recording: turn each module counter-clockwise now.", 6000);
            const doc = await App.runTest("capture", "ALL", { duration_s: 20, coast: 1 });
            const v = await App.api("/api/handcheck", { file: doc._file, kind, sign: 1 });
            const steerOk = r => r.absolute.verdict === "AGREES" && r.motor.verdict === "AGREES" && Math.abs(r.motor_per_module_deg - 1) < 0.03;
            const rows = Object.entries(v).map(([name, r]) => kind === "wheel"
              ? `<div class="verdict"><span class="level ${r.drive.verdict === "AGREES" ? "ok" : "error"}" data-tip="guide.verdict">${r.drive.verdict}</span><b>${abbr(name)}</b> wheel: drive encoder moved ${fmt(r.drive.net, 3)} m</div>`
              : `<div class="verdict"><span class="level ${steerOk(r) ? "ok" : "error"}" data-tip="guide.verdict">${r.absolute.verdict}</span>
                 <b>${abbr(name)}</b> steering: absolute ${fmt(r.absolute.net, 1)}°, motor encoder ${r.motor.verdict} ${fmt(r.motor.net, 1)}°, motor per module ${fmt(r.motor_per_module_deg, 3)}</div>`);
            const ok = Object.values(v).every(r => kind === "wheel" ? r.drive.verdict === "AGREES" : steerOk(r));
            handView = handView.replace(new RegExp(`<h3 data-k="${kind}">[\\s\\S]*?(?=<h3 data-k=|$)`), "")
              + `<h3 data-k="${kind}">${kind === "wheel" ? "Wheels" : "Steering"}</h3>` + rows.join("") +
              (ok ? "" : `<p class="hint">INVERTED: flip that setting for that module (see Troubleshoot). NO_MOTION: it did not move far enough, or that sensor is not reporting. AMBIGUOUS: it was rocked; move it one way only and record again.</p>`);
            const k = kind === "wheel" ? "handWheel" : "handSteer";
            const next = { ...progress, [k]: ok ? "pass" : "fail" };
            next.hand = next.handWheel === "pass" && next.handSteer === "pass" ? "pass"
              : (next.handWheel === "fail" || next.handSteer === "fail") ? "fail" : "partial";
            await mark({ [k]: next[k], hand: next.hand });
            paint();
          } catch (e) { App.toast(e.message, 6000); }
        };
        $("#g-hw", box).onclick = () => go("wheel");
        $("#g-hs", box).onclick = () => go("steer");
      } },

    { id: "offsets", env: "DISABLED", learn: ["offset", "absolute_encoder", "bevel_gear", "straight_edge", "hold_still", "coast_mode", "redeploy"], title: "Set the wheel offsets", where: "Robot disabled, motors coasting",
      why: "The offset tells the code where 'straight ahead' is for each module. One degree off is about 1.7 cm of sideways drift for every meter driven. Copied or rounded offsets are the most common swerve fault.",
      need: ["A straight-edge (a long level or a piece of aluminum extrusion)"],
      todo: ["Turn every module so its wheel points straight ahead with its bevel gear facing the robot's LEFT side. All four the same way.",
             "Hold a straight-edge against the front pair of wheels, then the back pair, so each pair lines up. Square the edge to the frame first: the same distance from the frame rail at both ends.",
             "Press Capture offsets and keep the wheels still for 4 seconds.",
             "Review the change, Write files, redeploy, then press Verify: every module must read within 2° of zero."],
      status: () => progress.offsets === "verified" ? "done" : progress.offsets === "written" ? "attention" : "todo",
      body: () => `<div class="row"><button class="btn primary" id="g-off" data-tip="guide.off">Capture offsets</button><button class="btn" id="g-ver" data-tip="guide.ver">Verify after redeploy</button></div><div id="g-offres">${shown.offsets || ""}</div>`,
      mount: box => {
        $("#g-off", box).onclick = async () => {
          try {
            const doc = await App.runTest("capture", "ALL", { duration_s: 4, coast: 1 });
            const res = await App.api("/api/offsets", { file: doc._file });
            shown.offsets = `<table class="t"><tr><th>Module</th><th class="num">Reads</th><th class="num">Offset now</th><th class="num">New offset</th><th></th></tr>${Object.entries(res).map(([n, r]) =>
              `<tr><td>${abbr(n)}</td><td class="num">${fmt(r.reading_deg, 2)}°</td><td class="num">${fmt(r.old, 2)}°</td><td class="num">${fmt(r.new, 2)}°</td><td>${r.steady ? "" : "moved: capture again"}</td></tr>`).join("")}</table>`;
            paint();
            if (Object.values(res).every(r => r.steady) && await App.previewAndSave({ kind: "offsets", file: doc._file }, "Write the new offsets")) {
              await mark({ offsets: "written" }); paint();
            }
          } catch (e) { App.toast(e.message, 6000); }
        };
        $("#g-ver", box).onclick = async () => {
          const live = App.live && App.live.live;
          if (!live) { App.toast("Connect first."); return; }
          const bad = (live.steer || []).map((a, i) => [App.modules()[i], ((a + 180) % 360) - 180]).filter(([, e]) => Math.abs(e) > 2);
          if (bad.length) App.toast("Still off: " + bad.map(([n, e]) => `${abbr(n)} ${fmt(e, 1)}°`).join(", ") + ". Is the new code deployed and the wheels straight?", 7000);
          else if (await mark({ offsets: "verified" })) { paint(); App.toast("Every wheel reads straight."); }
        };
      } },

    { id: "directions", env: "BLOCKS", learn: ["inversion", "environment"], title: "On blocks: every wheel drives the right way", where: "On blocks",
      why: "With the robot in the air you can watch each tire. A wheel that rolls backwards fights the other three and drags the robot sideways.",
      need: ["Blocks under the frame, all four wheels clear", "The tool set to On blocks", "The robot enabled in the Driver Station (Teleop or Test): the first step that turns a motor",
             "Someone holding the deadman for the whole run: the tester's controller right bumper (port 1), or Hold to run on screen"],
      todo: ["Enable the robot in the Driver Station (Teleop or Test mode). The wheels stay still until you press Run.",
             "Press Run directions, then hold the deadman. The wheels give a short kick first: the tool checking they spin free, off the floor. Then watch the TOP of each tire while the speed is positive: it must roll toward the front of the robot.", "Tick each wheel that did, then Confirm."],
      run: { label: "Run directions", test: "drive_step", args: { s0: 0.4, s1: 0, s2: -0.4, s3: 0, hold_s: 1.5 } },
      status: () => progress.directions === "pass" ? "done" : progress.directions === "fail" ? "attention" : "todo",
      body: () => `<div class="row">${App.modules().map(m => `<label class="row" data-tip="guide.dir"><input type="checkbox" class="g-dir" value="${esc(m)}" ${((progress.dirs || {})[m]) ? "checked" : ""}> ${abbr(m)} rolled forward</label>`).join("")}</div>
        <div class="row"><button class="btn" id="g-dirok" data-tip="guide.dirok">Confirm</button></div>`,
      mount: box => {
        $("#g-dirok", box).onclick = async () => {
          const dirs = {};
          $$(".g-dir", box).forEach(c => { dirs[c.value] = c.checked; });
          const pass = Object.values(dirs).every(Boolean);
          if (await mark({ dirs, directions: pass ? "pass" : "fail" })) paint();
          if (!pass) Trouble.open("wheel_backwards");
        };
      } },

    { id: "steer-blocks", env: "BLOCKS", learn: ["step_response", "kP", "kD", "dead_time", "saturation"], title: "Steering, on blocks", where: "On blocks",
      why: "Get the steering loop stable and quick in the air first, where nothing fights it. It passes at 80 out of 100 here: the floor finishes the job.",
      need: ["On blocks", "Someone holding the deadman during each run"],
      todo: ["Open the tuner (Steering, Robot).", "Run, read the advice, press Try this, run again. Repeat until it scores 80 or more.", "Do not save yet: the floor will change the numbers."],
      tune: "steer",
      status: () => graded("steer_step", "BLOCKS", 80) },

    { id: "geometry", env: "DISABLED", learn: ["wheel_size", "gear_ratio", "coast_mode"], title: "Measure the robot: module positions and wheel sizes", where: "On the floor, robot disabled",
      why: "Odometry turns wheel turns into distance with the wheel size, and robot turns into module speeds with the module positions. Measured once and then trusted for everything after - the feedforward's kV is in volts per meter a second, so the wheel size must be right before it is measured.",
      need: ["A tape measure", "3 m of straight floor", "Robot disabled"],
      todo: ["Calibrate tab, Module positions: measure wheelbase and track width between wheel centers, compare, save.",
             "Calibrate tab, Wheel sizes: record a 3 m push in coast, type the distance, measure, save.", "Redeploy, then come back and press Mark as done."],
      body: () => `<div class="row"><button class="btn primary" data-go="calibrate" data-tip="guide.calibrate">Open Calibrate</button>
        <button class="btn" id="g-geo-done" data-tip="guide.mark">${progress.geometry === "done" ? "Done ✓ (press to undo)" : "Mark as done"}</button></div>`,
      mount: box => {
        $("#g-geo-done", box).onclick = async () => { if (await mark({ geometry: progress.geometry === "done" ? "" : "done" })) paint(); };
      },
      status: () => progress.geometry === "done" ? "done" : "todo" },

    { id: "steer-floor", env: "FIELD", learn: ["carpet_scrub", "steady_state_error", "kI", "iZone", "what_if"], title: "Steering, on the floor", where: "On the floor (the robot does not drive)",
      why: "Carpet holds a wheel still until the loop pushes hard enough. Gains that look perfect on blocks usually leave each wheel a few degrees short on carpet - and that is sideways drift.",
      need: ["Robot on carpet, enabled", "The tester's controller in Driver Station port 1: its right bumper is the deadman, held for the whole run"],
      todo: ["Open the tuner (Steering, Robot). The wheels turn in place; the robot stays put.", "Follow the advice until every target is met.", "Save to files."],
      tune: "steer",
      status: () => graded("steer_step", "FIELD") },

    { id: "slip", env: "FIELD", learn: ["traction", "slip_current", "current_limit"], title: "Find where the wheels slip", where: "On the floor, front bumper against a solid wall",
      why: "The drive current limit decides how hard the robot can accelerate. Above the current where a wheel breaks loose, more current only spins the wheel: it wastes battery, wears the tread, and makes odometry count distance the robot never traveled. This measures that current on your carpet, for each corner, so the limit sits just below it instead of at a datasheet number.",
      need: ["A solid wall: the field wall or a shop wall, not a table or a door", "Carpet like the competition's", "A fresh battery", "The tester's controller in port 1, right bumper held as the deadman"],
      todo: ["Put the front bumper flat against the wall, every wheel pointing straight at it. Nobody between the robot and the wall.",
             "Open the tuner (Slip current, Robot) and Run. The push builds over a few seconds; each wheel chirps once as it slips and is cut at once.",
             "Press Try this on the recommended limit and Write the file. Change PathPlanner's drive current limit to match, redeploy, then measure the feedforward."],
      tune: "slip",
      status: () => graded("slip", "FIELD") },

    { id: "ff", env: "FIELD", learn: ["feedforward", "kS", "kV", "kA"], title: "Measure the feedforward", where: "On the floor, about 3 m clear",
      why: "Out of the box YAGSL guesses the drive voltage from the motor datasheet, with nothing for friction and nothing for acceleration. Measured per module, the wheel is within a few percent of its target before the PID does anything.",
      need: ["3 m or more of clear carpet ahead", "A fresh battery", "The tester's controller in port 1, right bumper held as the deadman"],
      todo: ["Open the tuner (Feedforward, Robot) and Run. The robot drives forward and back a few meters.", "If every module fitted, press Try this to apply, then Save to files.",
             "Then, in the Calibrate tab, weigh the robot and measure its moment of inertia: PathPlanner needs both."],
      tune: "ff",
      status: () => graded("drive_ff", "FIELD") },

    { id: "drive", env: "FIELD", learn: ["feedback", "kP", "velocity_filter", "ff_uses_setpoint"], title: "Drive speed", where: "On the floor",
      why: "With the feedforward measured, the drive PID only has to correct small errors, so it can stay gentle and quiet.",
      need: ["Clear carpet", "Deadman held"],
      todo: ["Open the tuner (Drive speed, Robot).", "Follow the advice until every target is met.", "Save to files."],
      tune: "drive",
      status: () => graded("drive_step", "FIELD") },

    { id: "spin", env: "FIELD", learn: ["swerve_module", "module_flip", "gyro"], title: "Spin check", where: "On the floor, clear all round",
      why: "Command, gyro and wheels must agree on how fast the robot turns. This finds an inverted gyro and module positions entered wrong.",
      need: ["About 1 m clear all round", "Deadman held"],
      todo: ["Open the tuner (Spin, Robot) and Run.", "Fix anything it reports."],
      tune: "spin",
      status: () => graded("spin", "FIELD") },

    { id: "straight", env: "FIELD", learn: ["wheel_size", "gear_ratio", "offset"], title: "Straight line", where: "On the floor, 3 m clear",
      why: "The acceptance test. With no heading correction, whatever the robot does is the drivetrain itself.",
      need: ["A tape measure and a tape mark at the start (unless AprilTags are on)", "Deadman held"],
      todo: ["Mark the floor at the robot's center.", "Open the tuner (Straight line, Robot) and Run. Without AprilTags it stops at the far end.", "Measure from the start mark to the robot's center where it stopped, in meters; enter it in Runs to get the wheel scale."],
      tune: "straight",
      status: () => graded("straight", "FIELD") },

    { id: "profile", env: null, title: "Advanced: second-order motion profiles", where: "After steering and drive pass on the floor",
      learn: ["motion_profile", "trapezoid_profile", "cruise_velocity", "max_acceleration", "ff_uses_setpoint", "maxmotion_position", "maxmotion_velocity", "allowed_profile_error"],
      why: "A step asks a mechanism to be somewhere instantly; a motion profile plans a path it can actually follow, limiting both speed and acceleration. That is second-order control, and REV's MAXMotion runs it inside the SPARK. It only helps once the first-order loops - feedforward and PID - are already right, so this step stays locked until they pass.",
      need: ["Steering on the floor and drive speed both passing their targets"],
      todo: ["Read the lessons below, in order.", "The profile tuner arrives here once the first-order steps pass on a real robot."],
      status: () => firstOrderDone() ? "todo" : "locked" },

    { id: "commit", env: null, title: "Save and commit", where: "Laptop",
      why: "Gains changed live are gone at the next restart. The files in the repository are the robot's real settings.",
      need: ["git"],
      todo: ["Save gains for steering, drive and feedforward (each tuner has Save to files).", "Redeploy, reconnect, and check the Live tab's startup list shows the measured feedforward.",
             "Commit on your branch with a message saying what was measured, and open a pull request."],
      status: () => progress.commit === "done" ? "done" : "todo",
      body: () => `<div class="row"><button class="btn" id="g-commit" data-tip="guide.mark">${progress.commit === "done" ? "Done ✓ (press to undo)" : "Mark done"}</button></div>`,
      mount: box => { $("#g-commit", box).onclick = async () => { if (await mark({ commit: progress.commit === "done" ? "" : "done" })) paint(); }; } },
  ];

  const STATE_WORD = { done: "✓ Done", attention: "Needs a look", locked: "Locked" };
  const SAFETY = {
    FIELD: "the robot moves. Clear the space, set On the floor with real measurements, and give the deadman to someone watching the robot.",
    BLOCKS: "the wheels spin while the deadman is held, starting with a short kick that checks they are off the floor. All four must be clear of the floor, and hands, hair and cables clear of every wheel.",
  };

  // Saves marks a person or a measurement set. In the simulator nothing is ticked: it teaches the
  // steps, but its sensors are perfect, so its results say nothing about the robot.
  async function mark(changes) {
    if (sim()) { App.toast("Simulator: the result shows, but nothing is ticked. Tick steps on the real robot.", 5000); return false; }
    progress = await App.api("/api/progress", changes);
    progress.runs = progress.runs || {};
    return true;
  }

  // First-order tuning is done when steering on the floor and drive speed both pass.
  function firstOrderDone() {
    const s = result("steer_step", "FIELD"), d = result("drive_step", "FIELD");
    return !!(s && s.score === 100 && d && d.score === 100);
  }

  async function refresh() {
    progress = await App.api("/api/progress");
    progress.runs = progress.runs || {};
    if (!picked) active = (STEPS.find(s => !["done", "locked"].includes(s.status())) || STEPS[STEPS.length - 1]).id;
    paint();
  }

  // Is the robot where this step needs it? Checked against the live robot, never assumed.
  function whereRow(step) {
    if (!step.env) return "";
    const tip = `data-tip="guide.where"`;
    if (!App.connected()) return `<div class="need-where unmet" ${tip}><b>Needs:</b> ${esc(step.where)}. Connect first.</div>`;
    if (sim()) return `<div class="need-where met" ${tip}><b>Simulator:</b> practice only. Results show, but nothing is ticked.</div>`;
    if (step.env === "DISABLED") {
      const m = ((App.live || {}).live || {}).mode;
      return m === "DISABLED" ? `<div class="need-where met" ${tip}><b>✓ Ready:</b> the robot is disabled.</div>`
        : `<div class="need-where unmet" ${tip}><b>Not ready:</b> disable the robot in the Driver Station first.</div>`;
    }
    const now = App.env();
    return now === step.env
      ? `<div class="need-where met" ${tip}><b>✓ Ready:</b> the tool is set to ${whereWord(now)}.</div>`
      : `<div class="need-where unmet" ${tip}><b>Not ready:</b> this step needs ${whereWord(step.env)}; the tool is set to ${esc(whereWord(now))}.
           <button class="btn primary" id="g-where">Set: ${whereWord(step.env)}</button></div>`;
  }
  // State ticks repaint ONLY this row: a full paint would wipe hand-check results and ticked boxes.
  function paintWhere() {
    const box = $("#g-where-row", root), step = STEPS.find(s => s.id === active);
    if (!box || !step) return;
    const html = whereRow(step);
    if (html === lastWhere) return;
    lastWhere = html;
    box.innerHTML = html;
    const b = $("#g-where", box);
    if (b) b.onclick = () => openEnvironment(step.env);
  }

  function go(id, focus = true) {
    if (STEPS.some(s => s.id === id)) { active = id; picked = true; }
    if (root.classList.contains("on")) paint(focus); else App.show("guide");
  }

  function paint(focus = false) {
    const idx = Math.max(0, STEPS.findIndex(s => s.id === active));
    const step = STEPS[idx];
    const st = step.status(), next = STEPS[idx + 1];
    root.innerHTML = `<div class="split">
      <div class="panel"><h3 data-tip="guide.rail">The path to a tight swerve</h3>
        <p class="small muted">✓ Done means every target was met on the real robot.</p>
        <ol class="guide-steps">${STEPS.map((s, i) => {
          const ss = s.status();
          return `<li><button class="gstep ${s.id === step.id ? "on" : ""} ${ss}" data-s="${s.id}" data-tip="guide.step.${s.id}" data-quiet ${s.id === step.id ? `aria-current="step"` : ""}>
            <span class="n">${i + 1}</span>
            <span><span class="t">${esc(s.title)}</span><br><span class="where">${esc(s.where)}</span>${STATE_WORD[ss] ? ` <span class="state">· ${STATE_WORD[ss]}</span>` : ""}</span></button></li>`;
        }).join("")}</ol></div>
      <div class="panel" id="gbody">
        <h2 tabindex="-1">${idx + 1}. ${esc(step.title)}</h2>
        <div id="g-where-row"></div>
        ${SAFETY[step.env] ? `<div class="callout safety"><b>Safety:</b> ${SAFETY[step.env]} Esc or ABORT stops everything.</div>` : ""}
        <div><b>You need</b><ul style="margin:4px 0 0;padding-left:18px">${step.need.map(n => `<li>${Learn.link(n, 2)}</li>`).join("")}</ul></div>
        <div><b>Do this</b><ol class="do">${step.todo.map(t => `<li>${Learn.link(t, 2)}</li>`).join("")}</ol></div>
        ${step.run || step.tune ? `<div class="row">
          ${step.run ? `<button class="btn primary" id="g-run" data-tip="guide.run">${esc(step.run.label)}</button>` : ""}
          ${step.tune ? `<button class="btn primary" id="g-tune" data-tip="guide.tune">Open the tuner</button>` : ""}
        </div>` : ""}
        <div id="g-extra">${step.body ? step.body() : ""}</div>
        <div id="g-result">${shown[step.id] || ""}</div>
        ${st === "done" && next ? `<div class="row"><button class="btn primary" data-step="${next.id}" data-tip="guide.next">Next: ${idx + 2}. ${esc(next.title)} →</button></div>` : ""}
        <div class="callout"><b>Why this step:</b> ${Learn.link(step.why, 3)}</div>
        ${(step.learn || []).length ? `<div class="row learn-row"><span class="small muted">Learn:</span>${Learn.chips(step.learn)}</div>` : ""}
      </div></div>`;
    lastWhere = null;
    paintWhere();
    $$(".gstep", root).forEach(b => b.onclick = () => go(b.dataset.s));
    $$("[data-step]", root).forEach(b => b.onclick = () => go(b.dataset.step));
    $$("[data-go]", root).forEach(b => b.onclick = () => App.show(b.dataset.go));
    if (step.mount) step.mount($("#gbody", root));
    if (step.tune) $("#g-tune", root).onclick = () => Tune.open(step.tune, { target: "robot" });
    if (step.run) $("#g-run", root).onclick = async () => {
      if (step.env === "BLOCKS" && App.env() !== "BLOCKS" && !sim()) { openEnvironment("BLOCKS"); return; }
      try {
        const doc = await App.runTest(step.run.test, "ALL", step.run.args);
        const rep = doc.report || {};
        shown[step.id] = `<div class="panel"><b>${esc(rep.summary || doc.outcome)}</b>${(rep.findings || []).map(f =>
          `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div><div class="why">${Learn.link(f.why, 2)}</div></div>`).join("")}</div>`;
        if (step.run.record && doc.outcome === "DONE" && !doc.practice && doc.env !== "SIM") await mark({ [step.run.record]: rep.score === 100 ? "pass" : "fail" });
        paint();
      } catch (e) { App.toast(e.message, 6000); }
    };
    // A step picked by a person gets focus; a repaint on a timer or a new run never steals it.
    if (focus) { const h = $("#gbody h2", root); if (h) h.focus(); }
  }

  App.on("tab", t => { if (t === "guide") refresh(); });
  App.on("lint", () => { if (root.classList.contains("on")) paint(); });
  App.on("run", () => { if (root.classList.contains("on")) refresh(); });
  App.on("state", () => { if (root.classList.contains("on")) paintWhere(); });
  App.on("live", () => { if (root.classList.contains("on")) paintWhere(); });

  return { refresh, firstOrderDone, go };
})();
