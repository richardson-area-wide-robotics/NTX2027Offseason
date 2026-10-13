// Guide tab: the path from "it drives" to "it drives tight", one step at a time, in the order
// that keeps each step honest - signs before gains, blocks before floor, steering before speed.
"use strict";

const Guide = (() => {
  const root = $("#tab-guide");
  let progress = {}, runsCache = [], active = "connect";

  const lastRun = (test, env, pred) => runsCache.find(r => r.test === test && !r.practice && (!env || r.env === env) && (!pred || pred(r)));

  // The swerve configuration's findings: PathPlanner's auto checks are for whoever writes the autos.
  const swerveLint = () => ((App.lint && App.lint.findings) || []).filter(f => !String(f.id || "").startsWith("pathplanner"));

  const STEPS = [
    { id: "connect", learn: ["control_loop", "gear_ratio", "current_limit"], title: "Connect and check the configuration", where: "Anywhere",
      why: "Most swerve problems are a wrong number in a JSON file. The tool reads every file, does the physics, and lists what does not add up - before anything moves.",
      need: ["The laptop on the robot's network (or the simulator running)"],
      todo: ["Pick the robot code at the top (Black team or Peashooter).", "Press Connect.", "Read every red and yellow item in the Config tab. Fix the red swerve ones before going on; auto (PathPlanner) problems don't block swerve tuning."],
      status: () => !App.connected() ? "todo" : swerveLint().some(f => f.level === "error") ? "attention" : "done",
      body: () => {
        const f = swerveLint(), auto = ((App.lint && App.lint.findings) || []).length - f.length;
        const e = f.filter(x => x.level === "error").length, w = f.filter(x => x.level === "warn").length;
        return `<p>${App.connected() ? "Connected." : "Not connected."} The swerve configuration has <b>${e}</b> errors and <b>${w}</b> warnings${auto > 0 ? `, plus ${auto} auto (PathPlanner) items for whoever writes the autos` : ""}.</p>
          <div class="row"><button class="btn" data-go="config">Open the Config tab</button></div>`;
      } },

    { id: "health", learn: ["quantization", "motor_encoder", "absolute_encoder"], title: "Sensor health", where: "Robot disabled",
      why: "A noisy encoder or a drifting gyro makes every later number wrong. Two seconds standing still finds both.",
      need: ["Robot on, disabled, not moving"],
      todo: ["Leave the robot completely still.", "Press Run health check."],
      run: { label: "Run health check", test: "capture", args: { duration_s: 3 } },
      status: () => { const r = lastRun("capture"); return !r ? "todo" : r.score === 100 ? "done" : "attention"; } },

    { id: "hand", learn: ["hand_check", "coast_mode", "inversion", "motor_encoder", "absolute_encoder", "gear_ratio"], title: "Hand check: every direction", where: "Robot disabled, motors coasting",
      why: "Every later test assumes it knows which way is positive. A backwards sign makes a module run away or fight the others, and it looks like a tuning problem. Turning things by hand finds it in a minute, with nothing powered.",
      need: ["Robot disabled", "Somewhere to stand at each corner"],
      todo: ["First turn every module so its wheel points straight ahead with the bevel gear (the gear on the side of the wheel) facing the robot's LEFT side. A module turned the other way reads backwards, and flipping its setting would hide the real mistake.",
             "Press Record wheels (20 s). Roll each wheel so its TOP moves toward the front of the robot, about one turn. Do all four, one direction only.",
             "Press Record steering (20 s). Turn each module counter-clockwise, seen from above, about a quarter turn. All four, one direction only.",
             "Every row must say AGREES, and 'motor per module' must be 1.00 ± 0.03."],
      status: () => progress.hand === "pass" ? "done" : progress.hand === "fail" ? "attention" : "todo",
      body: () => `<div class="row"><button class="btn primary" id="g-hw">Record wheels</button><button class="btn primary" id="g-hs">Record steering</button></div>
        <div id="g-hand" class="verdicts">${progress.handHtml || ""}</div>`,
      mount: box => {
        const go = async (kind) => {
          try {
            App.toast(kind === "wheel" ? "Recording: roll each wheel forward now." : "Recording: turn each module counter-clockwise now.", 6000);
            const doc = await App.runTest("capture", "ALL", { duration_s: 20, coast: 1 });
            const v = await App.api("/api/handcheck", { file: doc._file, kind, sign: 1 });
            const rows = Object.entries(v).map(([name, r]) => kind === "wheel"
              ? `<div class="verdict"><span class="level ${r.drive.verdict === "AGREES" ? "ok" : "error"}">${r.drive.verdict}</span><b>${abbr(name)}</b> wheel: drive encoder moved ${fmt(r.drive.net, 3)} m</div>`
              : `<div class="verdict"><span class="level ${r.absolute.verdict === "AGREES" && r.motor.verdict === "AGREES" && Math.abs(r.motor_per_module_deg - 1) < 0.03 ? "ok" : "error"}">${r.absolute.verdict}</span>
                 <b>${abbr(name)}</b> steering: absolute ${fmt(r.absolute.net, 1)}°, motor encoder ${r.motor.verdict} ${fmt(r.motor.net, 1)}°, motor per module ${fmt(r.motor_per_module_deg, 3)}</div>`);
            const ok = Object.values(v).every(r => kind === "wheel" ? r.drive.verdict === "AGREES"
              : r.absolute.verdict === "AGREES" && r.motor.verdict === "AGREES" && Math.abs(r.motor_per_module_deg - 1) < 0.03);
            progress[kind === "wheel" ? "handWheel" : "handSteer"] = ok ? "pass" : "fail";
            progress.handHtml = (progress.handHtml || "") + `<h3>${kind === "wheel" ? "Wheels" : "Steering"}</h3>` + rows.join("") +
              (ok ? "" : `<p class="hint">INVERTED: flip that setting for that module (see Troubleshoot). NO_MOTION: it did not move far enough, or that sensor is not reporting. AMBIGUOUS: it was rocked; move it one way only and record again.</p>`);
            progress.hand = progress.handWheel === "pass" && progress.handSteer === "pass" ? "pass"
              : (progress.handWheel === "fail" || progress.handSteer === "fail") ? "fail" : "partial";
            await save(); paint();
          } catch (e) { App.toast(e.message, 6000); }
        };
        $("#g-hw", box).onclick = () => go("wheel");
        $("#g-hs", box).onclick = () => go("steer");
      } },

    { id: "offsets", learn: ["offset", "absolute_encoder", "bevel_gear", "straight_edge", "hold_still", "coast_mode", "redeploy"], title: "Set the wheel offsets", where: "Robot disabled, motors coasting",
      why: "The offset tells the code where 'straight ahead' is for each module. One degree off is about 1.7 cm of sideways drift for every meter driven. Copied or rounded offsets are the most common swerve fault.",
      need: ["A straight-edge (a long level or a piece of aluminum extrusion)"],
      todo: ["Turn every module so its wheel points straight ahead with its bevel gear facing the robot's LEFT side. All four the same way.",
             "Hold a straight-edge against the front pair of wheels, then the back pair, so each pair lines up.",
             "Press Capture offsets and keep the wheels still for 4 seconds.",
             "Review the change, Write files, redeploy, then press Verify: every pod must read within 2° of zero."],
      status: () => progress.offsets === "verified" ? "done" : progress.offsets === "written" ? "attention" : "todo",
      body: () => `<div class="row"><button class="btn primary" id="g-off">Capture offsets</button><button class="btn" id="g-ver">Verify after redeploy</button></div><div id="g-offres"></div>`,
      mount: box => {
        $("#g-off", box).onclick = async () => {
          try {
            const doc = await App.runTest("capture", "ALL", { duration_s: 4, coast: 1 });
            const res = await App.api("/api/offsets", { file: doc._file });
            $("#g-offres", box).innerHTML = `<table class="t"><tr><th>Module</th><th>Reads</th><th>Offset now</th><th>New offset</th><th></th></tr>${Object.entries(res).map(([n, r]) =>
              `<tr><td>${abbr(n)}</td><td class="num">${fmt(r.reading_deg, 2)}°</td><td class="num">${fmt(r.old, 2)}</td><td class="num">${fmt(r.new, 2)}</td><td>${r.steady ? "" : "moved: capture again"}</td></tr>`).join("")}</table>`;
            if (Object.values(res).every(r => r.steady) && await App.previewAndSave({ kind: "offsets", file: doc._file }, "Write the new offsets")) {
              progress.offsets = "written"; await save(); paint();
            }
          } catch (e) { App.toast(e.message, 6000); }
        };
        $("#g-ver", box).onclick = () => {
          const live = App.live && App.live.live;
          if (!live) { App.toast("Connect first."); return; }
          const bad = (live.steer || []).map((a, i) => [App.modules()[i], ((a + 180) % 360) - 180]).filter(([, e]) => Math.abs(e) > 2);
          if (bad.length) App.toast("Still off: " + bad.map(([n, e]) => `${abbr(n)} ${fmt(e, 1)}°`).join(", ") + ". Is the new code deployed and the wheels straight?", 7000);
          else { progress.offsets = "verified"; save(); paint(); App.toast("Every wheel reads straight."); }
        };
      } },

    { id: "directions", learn: ["inversion", "environment"], title: "On blocks: every wheel drives the right way", where: "On blocks",
      why: "With the robot in the air you can watch each tire. A wheel that rolls backwards fights the other three and drags the robot sideways.",
      need: ["Blocks under the frame, all four wheels clear", "Environment set to On blocks"],
      todo: ["Set the environment to On blocks.", "Press Run directions and watch the TOP of each tire while the speed is positive: it must roll toward the front of the robot.", "Tick each wheel that did."],
      run: { label: "Run directions", test: "drive_step", args: { s0: 0.4, s1: 0, s2: -0.4, s3: 0, hold_s: 1.5 }, env: "BLOCKS" },
      status: () => progress.directions === "pass" ? "done" : progress.directions === "fail" ? "attention" : "todo",
      body: () => `<div class="row">${App.modules().map(m => `<label class="row"><input type="checkbox" class="g-dir" value="${esc(m)}" ${((progress.dirs || {})[m]) ? "checked" : ""}> ${abbr(m)} rolled forward</label>`).join("")}</div>
        <button class="btn" id="g-dirok">Confirm</button>`,
      mount: box => {
        $("#g-dirok", box).onclick = async () => {
          progress.dirs = {};
          $$(".g-dir", box).forEach(c => { progress.dirs[c.value] = c.checked; });
          progress.directions = Object.values(progress.dirs).every(Boolean) ? "pass" : "fail";
          await save(); paint();
          if (progress.directions === "fail") Trouble.open("wheel_backwards");
        };
      } },

    { id: "geometry", learn: ["gear_ratio", "coast_mode"], title: "Measure the robot: module positions and wheel sizes", where: "Floor, robot disabled",
      why: "Odometry turns wheel turns into distance with the wheel size, and robot turns into module speeds with the module positions. Measured once and then trusted for everything after - the feedforward's kV is in volts per meter a second, so the wheel size must be right before it is measured.",
      need: ["A tape measure", "3 m of straight floor", "Robot disabled"],
      todo: ["Calibrate tab, Module positions: measure wheelbase and track width between wheel centers, compare, save.",
             "Calibrate tab, Wheel sizes: record a 3 m push in coast, type the distance, measure, save.", "Redeploy."],
      body: () => `<div class="row"><button class="btn primary" data-go="calibrate">Open Calibrate</button>
        <button class="btn" id="g-geo-done">${progress.geometry === "done" ? "Done ✓" : "Mark as done"}</button></div>`,
      mount: box => {
        $("#g-geo-done", box).onclick = async () => { progress.geometry = progress.geometry === "done" ? "" : "done"; await save(); paint(); };
      },
      status: () => progress.geometry === "done" ? "done" : "todo" },

    { id: "steer-blocks", learn: ["step_response", "kP", "kD", "dead_time", "saturation"], title: "Steering, on blocks", where: "On blocks",
      why: "Get the steering loop stable and quick in the air first, where nothing fights it.",
      need: ["On blocks"],
      todo: ["Open the tuner (Steering, Robot).", "Run, read the advice, press Try this, run again. Repeat until the targets are met.", "Do not save yet: the floor will change the numbers."],
      tune: "steer",
      status: () => { const r = lastRun("steer_step", "BLOCKS"); return !r ? "todo" : r.score >= 80 ? "done" : "attention"; } },

    { id: "steer-floor", learn: ["carpet_scrub", "steady_state_error", "kI", "iZone", "what_if"], title: "Steering, on the floor", where: "On the floor (the robot does not drive)",
      why: "Carpet holds a wheel still until the loop pushes hard enough. Gains that look perfect on blocks usually leave each wheel a few degrees short on carpet - and that is sideways drift.",
      need: ["Robot on carpet", "Environment set to On the floor", "Someone holding the deadman"],
      todo: ["Open the tuner (Steering, Robot). The wheels turn in place; the robot stays put.", "Follow the advice until every target is met.", "Save to files."],
      tune: "steer",
      status: () => { const r = lastRun("steer_step", "FIELD"); return !r ? "todo" : r.score === 100 ? "done" : "attention"; } },

    { id: "slip", learn: ["traction", "slip_current", "current_limit"], title: "Find where the wheels slip", where: "On the floor, front bumper against a solid wall",
      why: "The drive current limit decides how hard the robot can accelerate. Above the current where a wheel breaks loose, more current only spins the wheel: it wastes battery, wears the tread, and makes odometry count distance the robot never traveled. This measures that current on your carpet, for each corner, so the limit sits just below it instead of at a datasheet number.",
      need: ["A solid wall: the field wall or a shop wall, not a table or a door", "Carpet like the competition's", "A fresh battery", "Someone holding the deadman"],
      todo: ["Set the environment to On the floor.", "Put the front bumper flat against the wall, every wheel pointing straight at it. Nobody between the robot and the wall.",
             "Open the tuner (Slip current, Robot) and Run. The push builds over a few seconds; each wheel chirps once as it slips and is cut at once.",
             "Press Do this on the recommended limit and Write the file. Change PathPlanner's drive current limit to match, redeploy, then measure the feedforward."],
      tune: "slip",
      status: () => { const r = lastRun("slip", "FIELD"); return !r ? "todo" : r.score === 100 ? "done" : "attention"; } },

    { id: "ff", learn: ["feedforward", "kS", "kV", "kA"], title: "Measure the feedforward", where: "On the floor, about 3 m clear",
      why: "Out of the box YAGSL guesses the drive voltage from the motor datasheet, with nothing for friction and nothing for acceleration. Measured per module, the wheel is within a few percent of its target before the PID does anything.",
      need: ["3 m or more of clear carpet ahead", "A fresh battery", "Deadman held"],
      todo: ["Open the tuner (Feedforward, Robot) and Run. The robot drives forward and back a few meters.", "If every module fitted, press Try this to apply, then Save to files.",
             "Then, in the Calibrate tab, weigh the robot and measure its moment of inertia: PathPlanner needs both."],
      tune: "ff",
      status: () => { const r = lastRun("drive_ff", "FIELD"); return !r ? "todo" : r.score === 100 ? "done" : "attention"; } },

    { id: "drive", learn: ["feedback", "kP", "velocity_filter", "ff_uses_setpoint"], title: "Drive speed", where: "On the floor",
      why: "With the feedforward measured, the drive PID only has to correct small errors, so it can stay gentle and quiet.",
      need: ["Clear carpet", "Deadman held"],
      todo: ["Open the tuner (Drive speed, Robot).", "Follow the advice until every target is met.", "Save to files."],
      tune: "drive",
      status: () => { const r = lastRun("drive_step", "FIELD"); return !r ? "todo" : r.score === 100 ? "done" : "attention"; } },

    { id: "spin", learn: ["swerve_module", "module_flip"], title: "Spin check", where: "On the floor, clear all round",
      why: "Command, gyro and wheels must agree on how fast the robot turns. This finds an inverted gyro and module positions entered wrong.",
      need: ["About 1 m clear all round", "Deadman held"],
      todo: ["Open the tuner (Spin, Robot) and Run.", "Fix anything it reports."],
      tune: "spin",
      status: () => { const r = lastRun("spin", "FIELD"); return !r ? "todo" : r.score === 100 ? "done" : "attention"; } },

    { id: "straight", learn: ["gear_ratio", "offset"], title: "Straight line", where: "On the floor, 3 m clear",
      why: "The acceptance test. With no heading correction, whatever the robot does is the drivetrain itself.",
      need: ["A tape measure and a tape mark at the start (unless AprilTags are on)", "Deadman held"],
      todo: ["Mark the floor at the robot's center.", "Open the tuner (Straight line, Robot) and Run. Without AprilTags it stops at the far end.", "Measure from the start mark to the robot's center where it stopped, in meters; enter it in Runs to get the wheel scale."],
      tune: "straight",
      status: () => { const r = lastRun("straight", "FIELD"); return !r ? "todo" : r.score === 100 ? "done" : "attention"; } },

    { id: "profile", title: "Advanced: second-order motion profiles", where: "After steering and drive pass on the floor",
      learn: ["motion_profile", "trapezoid_profile", "cruise_velocity", "max_acceleration", "ff_uses_setpoint", "maxmotion_position", "maxmotion_velocity", "allowed_profile_error"],
      why: "A step asks a mechanism to be somewhere instantly; a motion profile plans a path it can actually follow, limiting both speed and acceleration. That is second-order control, and REV's MAXMotion runs it inside the SPARK. It only helps once the first-order loops - feedforward and PID - are already right, so this step stays locked until they pass.",
      need: ["Steering on the floor and drive speed both passing their targets"],
      todo: ["Read the lessons below, in order.", "The profile tuner arrives here once the first-order steps pass on a real robot."],
      status: () => firstOrderDone() ? "todo" : "locked" },

    { id: "commit", title: "Save and commit", where: "Laptop",
      why: "Gains changed live are gone at the next restart. The files in the repository are the robot's real settings.",
      need: ["git"],
      todo: ["Save gains for steering, drive and feedforward (each tuner has Save to files).", "Redeploy, reconnect, and check the Live tab's startup list shows the measured feedforward.",
             "Commit on your branch with a message saying what was measured, and open a pull request."],
      status: () => progress.commit === "done" ? "done" : "todo",
      body: () => `<button class="btn" id="g-commit">Mark done</button>`,
      mount: box => { $("#g-commit", box).onclick = async () => { progress.commit = "done"; await save(); paint(); }; } },
  ];

  async function save() { await App.api("/api/progress", progress); }

  // First-order tuning is done when steering on the floor and drive speed both pass.
  function firstOrderDone() {
    const s = lastRun("steer_step", "FIELD"), d = lastRun("drive_step", "FIELD");
    return !!(s && s.score === 100 && d && d.score === 100);
  }

  async function refresh() {
    const r = await App.api("/api/runs");
    runsCache = r.runs || [];
    progress = await App.api("/api/progress");
    paint();
  }

  function paint() {
    const step = STEPS.find(s => s.id === active) || STEPS[0];
    root.innerHTML = `<div class="split">
      <div class="panel"><h3>The path to a tight swerve</h3><div class="guide-steps">${STEPS.map((s, i) => {
        const st = s.status();
        return `<button class="gstep ${s.id === active ? "on" : ""} ${st}" data-s="${s.id}"><span class="n">${st === "done" ? "✓" : st === "locked" ? "🔒" : i + 1}</span>
          <span><span>${esc(s.title)}</span><br><span class="where">${esc(s.where)}</span></span></button>`;
      }).join("")}</div></div>
      <div class="panel" id="gbody">
        <div class="row" style="justify-content:space-between"><h2>${esc(step.title)}</h2><span class="chip">${esc(step.where)}</span></div>
        <div class="callout"><b>Why:</b> ${Learn.link(step.why, 3)}</div>
        ${(step.learn || []).length ? `<div class="row learn-row"><span class="small muted">Learn:</span>${Learn.chips(step.learn)}</div>` : ""}
        ${step.where.startsWith("On the floor") ? `<div class="callout safety"><b>Safety:</b> the robot moves. Clear the space, set the environment to On the floor with real measurements, and keep the deadman in the hand of someone watching the robot. Esc or the red button stops everything.</div>` : ""}
        <div><b>You need</b><ul style="margin:4px 0 0;padding-left:18px">${step.need.map(n => `<li>${Learn.link(n, 2)}</li>`).join("")}</ul></div>
        <div><b>Do this</b><ol class="do">${step.todo.map(t => `<li>${Learn.link(t, 2)}</li>`).join("")}</ol></div>
        <div class="row">
          ${step.run ? `<button class="btn primary" id="g-run">${esc(step.run.label)}</button>` : ""}
          ${step.tune ? `<button class="btn primary" id="g-tune">Open the tuner</button>` : ""}
        </div>
        <div id="g-extra">${step.body ? step.body() : ""}</div>
        <div id="g-result"></div>
      </div></div>`;
    $$(".gstep", root).forEach(b => b.onclick = () => { active = b.dataset.s; paint(); });
    $$("[data-go]", root).forEach(b => b.onclick = () => App.show(b.dataset.go));
    if (step.mount) step.mount($("#gbody", root));
    if (step.tune) $("#g-tune", root).onclick = () => Tune.open(step.tune, { target: "robot" });
    if (step.run) $("#g-run", root).onclick = async () => {
      if (step.run.env && App.env() !== step.run.env && App.env() !== "SIM") { openEnvironment(step.run.env); return; }
      try {
        const doc = await App.runTest(step.run.test, "ALL", step.run.args);
        const rep = doc.report || {};
        $("#g-result", root).innerHTML = `<div class="panel"><b>${esc(rep.summary || doc.outcome)}</b>${(rep.findings || []).map(f =>
          `<div class="finding"><div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div><div class="why">${esc(f.why)}</div></div>`).join("")}</div>`;
        await refresh();
      } catch (e) { App.toast(e.message, 6000); }
    };
  }

  App.on("tab", t => { if (t === "guide") refresh(); });
  App.on("lint", () => { if (root.classList.contains("on")) paint(); });
  App.on("run", () => { if (root.classList.contains("on")) refresh(); });
  // Opens one step from anywhere (Troubleshoot, Config): the Guide stays on it until the student picks another.
  function go(id) {
    if (STEPS.some(s => s.id === id)) active = id;
    if (root.classList.contains("on")) paint(); else App.show("guide");
  }

  return { refresh, firstOrderDone, go };
})();
