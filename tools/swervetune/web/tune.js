// Tune tab: run a test, see it, read the advice, try the suggestion, compare, save.
"use strict";

const Tune = (() => {
  const root = $("#tab-tune");
  const LOOPS = {
    steer: { label: "Steering", test: "steer_step", practice: true,
      blurb: "How fast and how precisely each wheel turns to the angle it is told. Run it on blocks first, then on the floor: the robot does not drive, the wheels only turn in place, and carpet is where the real numbers come from." },
    slip: { label: "Slip current", test: "slip", practice: true,
      blurb: "Finds the drive current where each wheel starts to slip on this carpet, so the current limit can sit just below it instead of at a datasheet number. Front bumper flat against a solid wall, every wheel pointing into it. The push ramps up until each wheel breaks loose; each is cut the moment it slips, and the tool recommends a limit." },
    ff: { label: "Feedforward", test: "drive_ff", practice: true,
      blurb: "Measures, per module, the voltage it takes to start moving (kS), to hold each speed (kV) and to accelerate (kA). The biggest single step to a tight drivetrain. Floor for real numbers; blocks finds a binding module." },
    drive: { label: "Drive speed", test: "drive_step", practice: true,
      blurb: "How well each wheel holds the speed it is told, once the feedforward is measured. On blocks it only checks direction and delay; tune it on the floor, where the wheel carries the robot." },
    spin: { label: "Spin", test: "spin", practice: false,
      blurb: "Spins in place both ways and compares command, gyro and wheels. Finds an inverted gyro and wrong module positions." },
    straight: { label: "Straight line", test: "straight", practice: false,
      blurb: "Drives a measured line with no heading correction and stops at the far end. Scores against a tape measure from your start mark, or AprilTags in view at both ends." },
  };
  const GAINS = {
    steer: [["Steer/kP", "kP", "output per degree of error"], ["Steer/kI", "kI", "per degree, per ms"],
            ["Steer/kD", "kD", "per degree change per ms"], ["Steer/IZone", "IZone", "degrees"],
            ["Steer/RampS", "Ramp", "seconds to full output"]],
    drive: [["Drive/kP", "kP", "output per m/s of error"], ["Drive/kI", "kI", "per m/s, per ms"],
            ["Drive/kD", "kD", "per m/s change per ms"], ["Drive/RampS", "Ramp", "seconds to full output"],
            ["Drive/VelPeriodMs", "Speed window", "ms (0 = controller default)"],
            ["Drive/VelDepth", "Speed averaging", "samples (0 = default)"]],
    chassis: [["Chassis/AngVelCoeff", "Skew correction", "-0.15 to 0.15"],
              ["EncoderSync/Enabled", "Encoder auto-sync", "1 = on"],
              ["EncoderSync/DeadbandDeg", "Sync deadband", "degrees"]],
  };
  const COLORS = ["--s0", "--s1", "--s2", "--s3"];

  let loop = "steer", target = "robot", surface = "floor", module = "ALL", pattern = 0;
  let edits = {}, practiceGains = null, current = null, compare = null, zoom = null;
  let xmod = 0, whatIf = { values: {}, pred: null, seq: 0 }, predTimer = null, stepSel = null;
  // With the whole run in view, only what needs attention is marked; pick a step to see it all.
  const ALARMS = new Set(["saturation", "current_limit", "ramp_rate", "overshoot", "oscillation", "steady_state_error"]);
  // Sliders in the "what if" panel: gain key, lesson, the slider's top end when the gain is 0.
  const XGAINS = {
    steer: [["Steer/kP", "kP", 0.08], ["Steer/kD", "kD", 2.0], ["Steer/kI", "kI", 0.0005], ["Steer/IZone", "iZone", 10]],
    drive: [["Drive/kP", "kP", 0.3], ["FF/{m}/kS", "kS", 0.5], ["FF/{m}/kV", "kV", 4.0]],
  };
  const NOTE_LABEL = { dead_time: "dead time", saturation: "flat out", current_limit: "current limit", oscillation: "ringing",
                       overshoot: "overshoot", steady_state_error: "left", rise_time: "rise", kP: "P max", kD: "D brakes",
                       feedforward: "FF share", ramp_rate: "ramp" };
  const learnKey = key => /kP$/.test(key) ? "kP" : /kI$/.test(key) ? "kI" : /kD$/.test(key) ? "kD" : /IZone$/.test(key) ? "iZone"
    : /RampS$/.test(key) ? "ramp_rate" : /VelPeriodMs|VelDepth/.test(key) ? "velocity_filter" : /kS$/.test(key) ? "kS"
    : /kV$/.test(key) ? "kV" : /kA$/.test(key) ? "kA" : /EncoderSync/.test(key) ? "encoder_sync" : null;
  // The tip for each gain box.
  const gainTip = key => /kP$/.test(key) ? "kP" : /kI$/.test(key) ? "kI" : /kD$/.test(key) ? "kD" : /IZone$/.test(key) ? "iZone"
    : /RampS$/.test(key) ? "ramp" : /VelPeriodMs/.test(key) ? "velwindow" : /VelDepth/.test(key) ? "veldepth"
    : /kS$/.test(key) ? "kS" : /kV$/.test(key) ? "kV" : /kA$/.test(key) ? "kA" : /AngVelCoeff/.test(key) ? "skew"
    : /EncoderSync\/Enabled/.test(key) ? "sync" : "syncdb";
  // A gain by the name its box shows: "Ramp", "FL kV".
  const GAIN_LABEL = Object.fromEntries(Object.values(GAINS).flat().map(([k, l]) => [k, l]));
  const gainName = k => GAIN_LABEL[k] || k.replace(/^FF\/(\w+)\/(k[SVA])$/, (_, m, g) => `${abbr(m)} ${g}`);
  const num = v => v == null || !isFinite(v) ? "–" : String(+(+v).toPrecision(4));
  // The gains a test uses: a steering run's "what changed" is about steering gains only.
  const USES = { steer_step: ["Steer/"], drive_step: ["Drive/", "FF/"], drive_ff: ["FF/", "Drive/"], slip: ["Drive/"],
                 spin: ["Chassis/", "EncoderSync/", "Steer/"], straight: ["Chassis/", "EncoderSync/", "Steer/", "Drive/", "FF/"] };
  const uses = (test, k) => (USES[test] || [""]).some(p => k.startsWith(p));
  const gainDiff = (test, a, b) => [...new Set([...Object.keys(a), ...Object.keys(b)])]
    .filter(k => uses(test, k) && num(a[k] || 0) !== num(b[k] || 0));
  // 12-hour time from a run's stamp, "20261012-211051" -> "9:10 PM".
  function clock(stamp) {
    const m = /(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)/.exec(stamp || "");
    if (!m) return "";
    const h = +m[4];
    return `${h % 12 || 12}:${m[5]} ${h < 12 ? "AM" : "PM"}`;
  }

  root.innerHTML = `
    <div class="tune">
      <div class="panel tune-bar">
        <div class="row tune-picks">
          <div class="seg" id="loopseg" role="group" aria-label="Test">${Object.entries(LOOPS).map(([k, v]) => `<button data-loop="${k}" data-tip="tune.loop.${k}">${v.label}</button>`).join("")}</div>
          <div class="row"><span class="small muted" id="lbl-target">Run on</span>
            <div class="seg" id="targetseg" role="group" aria-labelledby="lbl-target"><button data-t="robot" data-tip="tune.target.robot">Robot</button><button data-t="practice" data-tip="tune.target.practice">Practice pod</button></div></div>
          <div class="row" id="surfacerow"><span class="small muted" id="lbl-surf">Practice surface</span>
            <div class="seg" id="surfseg" role="group" aria-labelledby="lbl-surf"><button data-s="floor" data-tip="tune.surface.floor">Floor</button><button data-s="blocks" data-tip="tune.surface.blocks">Blocks</button></div></div>
          <div class="row" id="modrow">
            <label class="row small" data-tip="tune.module">Module <select id="module"><option>ALL</option><option>FL</option><option>FR</option><option>BL</option><option>BR</option></select></label>
            <label class="row small" data-tip="tune.pattern">Steps <select id="pattern"><option value="0">Standard</option><option value="1">Small (friction)</option><option value="2">Large (flat out)</option></select></label></div>
        </div>
        <p class="hint" id="blurb"></p>
        <div id="tune-faults"></div>
      </div>
      <div class="tune-col tune-left">
        <div class="panel">
          <div class="row" style="justify-content:space-between"><h3 data-tip="tune.gains">Gains</h3><span class="hint" id="gainsrc"></span></div>
          <div class="gains" id="gains"></div>
          <div class="row">
            <button class="btn" id="apply" data-tip="tune.apply">Apply live</button>
            <button class="btn" id="revert" data-tip="tune.revert">Revert edits</button>
            <button class="btn" id="save" data-tip="tune.save">Save to files…</button>
          </div>
          <div id="needs"></div>
          <button class="btn primary" id="run" aria-describedby="needs" data-tip="tune.run">Run</button>
        </div>
        <details class="panel" id="history-panel" open>
          <summary><h3 data-tip="tune.history">Earlier runs</h3></summary>
          <div id="history" class="small"></div>
        </details>
      </div>
      <div class="tune-col tune-plots">
        <div class="panel">
          <div class="row" style="justify-content:space-between;align-items:flex-start">
            <div><h2 id="res-title" data-tip="tune.title" data-quiet>No run yet</h2><div class="small muted mono" id="res-file"></div></div>
            <div class="row">
              <label class="row small" id="cmp-wrap" data-tip="tune.cmp" data-quiet hidden><input type="checkbox" id="cmp" checked> overlay the run before</label>
              <button class="btn small" id="export" data-tip="tune.export" data-quiet hidden>Export</button>
            </div>
          </div>
          <div id="practice-flag" class="practice-flag" hidden>Practice pod: a model of a MAXSwerve module, not your robot.</div>
          <div id="empty-run" class="callout"><b>Start here.</b> No run yet. The practice pod is a model of one MAXSwerve module: nothing moves, so it's the place to learn what each gain does before touching the robot.
            <div class="row" style="margin-top:8px"><button class="btn primary" id="try-practice" data-tip="tune.try-practice">Try the practice pod</button></div></div>
          <div id="run-view" class="stack" hidden>
            <div class="plotwrap"><canvas class="plot" id="plot" role="img" aria-label="The setpoint and what the mechanism did" aria-describedby="story"></canvas></div>
            <div class="steps" id="steps" role="group" aria-label="Zoom to a step"></div>
            <div id="explain-head" class="row" style="justify-content:space-between" hidden>
              <h3>What the controller <span class="term" tabindex="0" data-learn="error">saw</span> and <span class="term" tabindex="0" data-learn="control_effort">did</span></h3>
              <label class="row small" data-tip="tune.xmod">Module <select id="xmod"></select></label>
            </div>
            <div class="plotwrap" id="plot2wrap" hidden><canvas class="plot short" id="plot2" role="img" aria-label="The controller's output, split into its parts, in volts"></canvas></div>
            <p class="hint" id="explain-hint" hidden>Volts, so the parts add up. Hover the graph to read every part at that moment; hover a shaded area or a marker to learn what is happening there.</p>
            <details id="metrics-wrap" hidden><summary data-tip="tune.metrics" data-quiet>Every step, in numbers</summary><div class="tblwrap" id="metrics"></div></details>
          </div>
        </div>
      </div>
      <div class="tune-col tune-right">
        <div id="next-step" class="next-step" hidden></div>
        <!-- The advice, the prediction and the story take turns in one pane. -->
        <div class="panel panes" id="panes" hidden>
          <div class="seg" id="paneseg" role="group" aria-label="Show">
            <button data-pane="report" data-tip="tune.pane.report">Goals and advice</button>
            <button data-pane="whatif" data-tip="tune.whatif">What if…</button>
            <button data-pane="story-panel" data-tip="tune.story">What this run shows</button></div>
          <div class="pane" id="report" hidden></div>
          <div class="pane" id="whatif" hidden>
            <div class="row" style="justify-content:space-between"><span class="small"><span class="term" tabindex="0" data-learn="what_if">What if…</span></span><span class="small" id="wi-quality"></span></div>
            <div class="row"><button class="btn" id="wi-use" data-tip="tune.wi-use">Put these in the gains box</button><button class="btn" id="wi-reset" data-tip="tune.wi-reset">Back to the run's gains</button></div>
            <p class="hint">Drag a gain: the "what if" line on the top graph becomes the prediction for this same run with the new value.</p>
            <div id="wi-sliders" class="wi-sliders"></div>
            <div id="wi-table" class="tblwrap"></div>
          </div>
          <div class="pane" id="story-panel" hidden>
            <h3 id="story-head" class="sr" data-quiet>What this run shows</h3>
            <ol id="story" class="story small"></ol>
          </div>
        </div>
      </div>
    </div>`;

  // ---------------------------------------------------------------- the pane on the right
  // Goals and advice, What if, and the story take turns. Each tool code shows or hides its pane as
  // before ([hidden] = nothing to show); this picks which of the available ones is in view.
  let pane = "report";
  function paintPanes() {
    const box = $("#panes", root), ids = ["report", "whatif", "story-panel"];
    const has = Object.fromEntries(ids.map(id => [id, !$("#" + id, root).hidden]));
    box.hidden = !ids.some(id => has[id]);
    if (!has[pane]) pane = ids.find(id => has[id]) || "report";
    ids.forEach(id => $("#" + id, root).classList.toggle("sel", id === pane));
    $$("#paneseg button", root).forEach(b => {
      const on = b.dataset.pane === pane;
      b.disabled = !has[b.dataset.pane];
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    });
  }
  function showPane(id) { pane = id; paintPanes(); }
  $$("#paneseg button", root).forEach(b => b.onclick = () => showPane(b.dataset.pane));
  new MutationObserver(paintPanes).observe($("#panes", root), { attributes: true, attributeFilter: ["hidden"], subtree: true });

  // ---------------------------------------------------------------- gains
  function liveGains() {
    if (target === "practice") {
      if (!practiceGains) practiceGains = fromFiles();
      return practiceGains;
    }
    return App.gains();
  }

  function fromFiles() {
    const L = App.lint || {}, p = L.pidf || {}, ph = L.physical || {}, tune = L.swervetune || {};
    const g = {
      "Steer/kP": (p.angle || {}).p || 0.01, "Steer/kI": (p.angle || {}).i || 0, "Steer/kD": (p.angle || {}).d || 0,
      "Steer/IZone": (p.angle || {}).iz || 0, "Steer/RampS": (ph.rampRate || {}).angle || 0,
      "Drive/kP": (p.drive || {}).p || 0.002, "Drive/kI": (p.drive || {}).i || 0, "Drive/kD": (p.drive || {}).d || 0,
      "Drive/RampS": (ph.rampRate || {}).drive || 0,
      "Drive/VelPeriodMs": (tune.driveVelocityFilter || {}).periodMs || 0, "Drive/VelDepth": (tune.driveVelocityFilter || {}).depth || 0,
    };
    for (const m of ["frontleft", "frontright", "backleft", "backright"]) {
      const f = (tune.driveFeedforward || {})[m] || {};
      // An unmeasured kV is left out: the practice pod then uses YAGSL's default for its motor.
      g[`FF/${m}/kS`] = f.kS || 0; if (f.kV) g[`FF/${m}/kV`] = f.kV; g[`FF/${m}/kA`] = f.kA || 0;
    }
    return g;
  }

  function fields() {
    if (loop === "steer") return GAINS.steer;
    if (loop === "drive") return GAINS.drive;
    if (loop === "slip") return [];
    if (loop === "ff") {
      const mods = target === "practice" ? ["frontleft"] : App.modules();
      return mods.flatMap(m => [[`FF/${m}/kS`, `${abbr(m)} kS`, "volts"], [`FF/${m}/kV`, `${abbr(m)} kV`, "V per m/s"], [`FF/${m}/kA`, `${abbr(m)} kA`, "V per m/s²"]]);
    }
    return GAINS.chassis;
  }

  function paintGains() {
    const g = liveGains();
    $("#gainsrc", root).textContent = target === "practice" ? "the practice pod's own copy" : (App.connected() ? "running on the robot" : "connect to see the robot's");
    if (!fields().length) {
      $("#gains", root).innerHTML = `<p class="hint">Nothing to set by hand here: the test measures the drive ${Learn.term("current_limit", "current limit")} and offers to write it to the files.</p>`;
      return;
    }
    $("#gains", root).innerHTML = fields().map(([key, label, unit]) => {
      const v = key in edits ? edits[key] : g[key];
      const lk = learnKey(key);
      // A feedforward has a box per module: the same tip four times would bury the screen, so it shows on hover only.
      return `<label class="gain" data-tip="tune.gain.${gainTip(key)}" ${key.startsWith("FF/") ? "data-quiet" : ""}>${esc(label)}<input type="number" step="any" data-key="${esc(key)}" value="${v == null || !isFinite(v) ? "" : +(+v).toPrecision(6)}" class="${key in edits ? "changed" : ""}"><span class="unit">${esc(unit)}</span></label>`;
    }).join("");
    $$("#gains input", root).forEach(inp => inp.oninput = () => {
      const k = inp.dataset.key;
      if (inp.value === "") delete edits[k]; else edits[k] = +inp.value;
      inp.classList.toggle("changed", k in edits);
    });
  }

  async function applyEdits(values, reason) {
    const vals = values || edits;
    if (!Object.keys(vals).length) { App.toast("Nothing changed."); return true; }
    if (target === "practice") {
      Object.assign(practiceGains, vals);
      edits = {};
      paintGains();
      App.toast("Practice gains set. Run again to see the effect.");
      return true;
    }
    if (!App.connected()) { App.toast("Connect first."); return false; }
    // The reason goes into the robot's match log with the change.
    const r = await App.api("/api/gains", { values: vals, reason: reason || "Tune tab: typed by hand" });
    App.toast(r.status || r.error, 6000);
    if (r.gains) App.state.gains = r.gains;
    edits = {};
    paintGains();
    return r.ok;
  }

  // ---------------------------------------------------------------- run
  // What stands between the student and a run: a blocker disables Run and says how to clear it;
  // an instruction is what to do while it runs.
  function needs() {
    const L = LOOPS[loop];
    const block = text => ({ block: true, text }), say = text => ({ block: false, text });
    if (target === "practice") return L.practice ? say("") : block("Spin and Straight line need a whole robot; the practice pod is one module.");
    if (!App.connected()) return block("Connect to a robot or the simulator first (top of the page), or run it on the practice pod.");
    const env = App.env();
    if (env === "UNSET") return block("Say where the robot is first: press \"Where: not set\" at the top.");
    if (loop === "straight" && env === "BLOCKS") return block("The Straight line test needs the robot on the floor.");
    if (loop === "slip" && env === "BLOCKS") return block("The Slip current test needs the robot on carpet with a bumper against a wall: set On the floor.");
    if (loop === "slip" && env === "FIELD") return say("Front bumper flat against a solid wall, every wheel pointing into it. Hold the deadman for the whole run: the tester's controller right bumper, or Hold to run on screen.");
    if (env === "FIELD") return say("On the floor: hold the deadman for the whole run (the tester's controller right bumper, or Hold to run on screen).");
    if (env === "BLOCKS") return say("On blocks: hold the deadman for the whole run (the tester's controller right bumper, or Hold to run on screen).");
    return say("");
  }

  async function run() {
    const L = LOOPS[loop];
    $("#run", root).disabled = true;
    try {
      let doc;
      if (target === "practice") {
        doc = await App.api("/api/practice", { loop, surface, gains: practiceGains || fromFiles() });
        if (doc.ok === false) throw new Error(doc.error);
      } else {
        if (Object.keys(edits).length && !(await applyEdits())) return;
        const args = loop === "steer" ? { pattern } : {};
        doc = await App.runTest(L.test, loop === "steer" ? module : "ALL", args);
      }
      show(doc);
      loadHistory();
    } catch (e) {
      App.modal(`<h2>The test did not run</h2><p>${esc(e.message)}</p><div class="row"><button class="btn" onclick="App.closeModal()">OK</button></div>`);
    } finally {
      $("#run", root).disabled = false;
    }
  }

  // ---------------------------------------------------------------- results
  function modIdx(ch, suffix) {
    return Object.keys(ch).filter(k => /^m\d+\./.test(k) && k.endsWith("." + suffix)).map(k => +k.slice(1, k.indexOf("."))).sort();
  }

  // The run before is drawn in full color but dotted, labeled once: faint lines were 1.7:1 and unnamed.
  function seriesFor(doc, faded) {
    const ch = doc.channels || {}, t = ch.t || [], names = (doc.robot && doc.robot.modules) || [];
    const a = faded && !["steer_step", "drive_step"].includes(doc.test) ? 0.35 : 1, out = [];
    let first = true;
    const label = i => {
      if (!faded) return abbr(names[i] || "m" + i);
      const l = first ? "before" : null;
      first = false;
      return l;
    };
    const style = (o, i) => faded ? Object.assign(o, { dash: [1, 3], width: 1.4 }) : Object.assign(o, { learn: "measurement" });
    if (doc.test === "steer_step") {
      const sp = modIdx(ch, "sp");
      // Every module is told the same angles, so one "told" line says it for all of them.
      if (!faded && sp.length) out.push({ x: t, y: ch[`m${sp[0]}.sp`], color: "--sp", dash: [5, 4], width: 1.4, label: "told", learn: "setpoint" });
      for (const i of sp) out.push(style({ x: t, y: ch[`m${i}.steer`], color: COLORS[i % 4], alpha: a, label: label(i) }, i));
    } else if (doc.test === "drive_step") {
      if (!faded) out.push({ x: t, y: ch.sp, color: "--sp", dash: [5, 4], width: 1.4, label: "told", learn: "setpoint" });
      for (const i of modIdx(ch, "v")) out.push(style({ x: t, y: ch[`m${i}.v`], color: COLORS[i % 4], alpha: a, label: label(i) }, i));
    } else if (doc.test === "drive_ff") {
      for (const i of modIdx(ch, "volts")) out.push({ x: ch[`m${i}.v`], y: ch[`m${i}.volts`], color: COLORS[i % 4], points: true, alpha: a, label: label(i) });
    } else if (doc.test === "spin") {
      const h = ch.heading || [], rate = h.map((v, k) => k ? (v - h[k - 1]) / (t[k] - t[k - 1]) * Math.PI / 180 : NaN);
      out.push({ x: t, y: ch.cmd_omega, color: "--sp", dash: [5, 4], alpha: a, label: faded ? null : "told rad/s" });
      out.push({ x: t, y: rate, color: COLORS[0], alpha: a, label: faded ? null : "gyro rad/s" });
    } else if (doc.test === "straight") {
      out.push({ x: ch.x || [], y: ch.y || [], color: COLORS[0], alpha: a, label: faded ? null : "odometry path (m)" });
    } else if (doc.test === "slip") {
      for (const i of modIdx(ch, "amps")) out.push({ x: t, y: ch[`m${i}.amps`].map(Math.abs), color: COLORS[i % 4], alpha: a, label: label(i) });
      const cap = (doc.meta || {}).ceiling_a;
      if (cap && !faded) out.push({ x: [t[0], t[t.length - 1]], y: [cap, cap], color: "--bad", dash: [6, 4], width: 1, label: "ceiling" });
    } else if (doc.test === "capture") {
      for (const i of modIdx(ch, "steer")) out.push({ x: t, y: ch[`m${i}.steer`], color: COLORS[i % 4], alpha: a, label: label(i) });
    }
    return out;
  }

  function axes(doc) {
    return { steer_step: ["s", "degrees"], drive_step: ["s", "m/s"], drive_ff: ["m/s", "volts"], spin: ["s", "rad/s"],
             straight: ["x (m)", "y (m)"], capture: ["s", "degrees"], slip: ["s", "amps"] }[doc.test] || ["s", ""];
  }

  function explained() {
    const e = current && current.explain;
    return e && e.modules && e.modules[xmod] ? e.modules[xmod] : null;
  }

  function at(ex, x) {
    const t = ex.t;
    let lo = 0, hi = t.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (t[mid] <= x) lo = mid; else hi = mid; }
    return Math.abs(t[hi] - x) < Math.abs(t[lo] - x) ? hi : lo;
  }

  function readout(ex, x) {
    const k = at(ex, x), u = ex.units;
    const v = (a, d = 2) => fmt(ex[a][k], d);
    return `<b>${fmt(ex.t[k], 3)} s</b> · ${esc(abbr(ex.module))}<br>
      told ${v("sp", 2)}${u} · ${ex.loop === "steer" ? "wheel" : "wheel speed"} ${v("measured", 2)}${u}<br>
      the loop sees ${v("seen", 2)}${u} · <b>error ${v("error", 2)}${u}</b><br>
      <span class="c-p">P ${v("p")}</span> · <span class="c-i">I ${v("i")}</span> · <span class="c-d">D ${v("d")}</span>${ex.loop === "drive" ? ` · <span class="c-ff">FF ${v("ff")}</span>` : ""} V<br>
      asked <b>${v("asked")} V</b> · applied <b>${v("applied")} V</b> · battery ${v("battery", 1)} V`;
  }

  function notes(list) {
    return (list || []).filter(a => stepSel == null ? ALARMS.has(a.learn) : a.step === stepSel)
      .map(a => Object.assign({ label: stepSel == null ? null : NOTE_LABEL[a.learn] }, a));
  }

  function redraw() {
    if (!current) return;
    const s = seriesFor(current, false);
    if (compare && $("#cmp", root).checked && compare.test === current.test) s.unshift(...seriesFor(compare, true));
    const ex = explained();
    const p = whatIf.pred;
    if (ex && p && p.ok && whatIf.file === current._file && whatIf.index === ex.index) {
      s.push({ x: p.t, y: p.predicted, color: "--accent", dash: [8, 3, 2, 3], width: 2.4, label: "what if", learn: "what_if" });
    }
    const [xl, yl] = axes(current);
    $("#cmp-wrap", root).hidden = !(compare && compare.test === current.test);
    Plot.draw($("#plot", root), { series: s, xrange: zoom, xlabel: xl, ylabel: yl,
      annotations: ex ? notes(ex.response) : ((current.report || {}).annotations || []), readout: ex ? x => readout(ex, x) : null });
    $("#explain-head", root).hidden = !ex;
    $("#plot2wrap", root).hidden = !ex;
    $("#explain-hint", root).hidden = !ex;
    if (!ex) return;
    const t = ex.t, neg = ex.battery.map(b => -b);
    const c = [
      { x: t, y: ex.battery, color: "--bad", dash: [6, 4], width: 1, label: "battery", learn: "voltage_sag" },
      { x: t, y: neg, color: "--bad", dash: [6, 4], width: 1 },
      ...(ex.loop === "drive" ? [{ x: t, y: ex.ff, color: "--sp", width: 1.6, label: "FF", learn: "feedforward" }] : []),
      { x: t, y: ex.p, color: "--s0", width: 1.4, label: "P", learn: "kP" },
      ...(ex.gains.kI ? [{ x: t, y: ex.i, color: "--s3", width: 1.4, label: "I", learn: "kI" }] : []),
      ...(ex.gains.kD ? [{ x: t, y: ex.d, color: "--s2", width: 1.4, label: "D", learn: "kD" }] : []),
      { x: t, y: ex.asked, color: "--ink", dash: [4, 3], width: 1.2, label: "asked", learn: "control_effort" },
      { x: t, y: ex.applied, color: "--ink", width: 1.8, label: "applied", learn: "saturation" },
    ];
    const lim = Math.max(...ex.battery.filter(isFinite), 12) * 1.15;
    Plot.draw($("#plot2", root), { series: c, xrange: zoom, xlabel: "s", ylabel: "volts", yrange: [-lim, lim],
      annotations: notes(ex.controller), readout: x => readout(ex, x) });
  }

  // ---------------------------------------------------------------- the story and "what if"
  function paintStory() {
    const ex = explained();
    $("#story-panel", root).hidden = !ex || !ex.story.length;
    if (!ex) return;
    const chip = n => `<button class="chip learn-chip" data-lesson="${esc(n.learn)}" data-learn="${esc(n.learn)}">${esc((Learn.L[n.learn] || {}).title || n.learn)}</button>`;
    let items;
    if (stepSel != null) {
      // One step, in time order: what happened, moment by moment.
      items = ex.story.filter(n => n.step === stepSel).map(n => `<li><span class="mono">${fmt(n.t, 2)} s</span> ${chip(n)} ${Learn.link(n.text, 3)}</li>`);
      $("#story-head", root).textContent = `Step ${stepSel}, moment by moment`;
    } else {
      // Whole run: each idea once, from the biggest step that shows it, and how often it happened.
      const steps = new Set(ex.story.map(n => n.step)).size;
      const by = {};
      for (const n of ex.story) {
        const b = by[n.learn] || (by[n.learn] = { n, steps: new Set() });
        b.steps.add(n.step);
        if ((n.size || 0) > (b.n.size || 0)) b.n = n;
      }
      const order = ["dead_time", "kP", "rise_time", "saturation", "current_limit", "ramp_rate", "kD", "overshoot", "oscillation", "settling_time", "steady_state_error", "feedforward"];
      items = Object.values(by).sort((a, b) => order.indexOf(a.n.learn) - order.indexOf(b.n.learn)).map(b =>
        `<li>${chip(b.n)} <span class="muted small">in ${b.steps.size} of ${steps} steps.</span> ${Learn.link(b.n.text, 3)}
          <button class="btn small" data-step="${b.n.step}">Zoom to step ${b.n.step}</button></li>`);
      $("#story-head", root).textContent = "What this run shows";
    }
    $("#story", root).innerHTML = items.join("") + (stepSel == null ? `<li class="muted" style="list-style:none">Pick a step above the graphs to read it moment by moment.</li>` : "");
    $$("[data-step]", root).forEach(b => b.onclick = () => selectStep(+b.dataset.step));
  }

  function wiKeys(ex) {
    return XGAINS[ex.loop].map(([k, lk, top]) => [k.replace("{m}", ex.module), lk, top]);
  }

  function paintWhatIf() {
    const ex = explained();
    const panel = $("#whatif", root);
    panel.hidden = !ex || !current._file;
    if (panel.hidden) return;
    const g = current.gains || {};
    $("#wi-sliders", root).innerHTML = wiKeys(ex).map(([key, lk, top]) => {
      const base = +(g[key] || 0), val = key in whatIf.values ? whatIf.values[key] : base;
      const max = Math.max(top, base * 4);
      return `<label class="wi"><span class="term" data-learn="${lk}">${esc(lk === "iZone" ? "IZone" : lk)}</span>
        <input type="range" min="0" max="${max}" step="${max / 400}" value="${val}" data-key="${esc(key)}" aria-label="${esc(lk)}">
        <span class="mono" data-v="${esc(key)}">${+(+val).toPrecision(3)}</span><span class="muted small">this run: ${+(+base).toPrecision(3)}</span></label>`;
    }).join("");
    $$("#wi-sliders input", root).forEach(inp => inp.oninput = () => {
      whatIf.values[inp.dataset.key] = +inp.value;
      $(`[data-v="${CSS.escape(inp.dataset.key)}"]`, root).textContent = +(+inp.value).toPrecision(3);
      clearTimeout(predTimer);
      predTimer = setTimeout(predictNow, 180);
    });
    paintPrediction();
  }

  async function predictNow() {
    const ex = explained();
    if (!ex || !current._file) return;
    const seq = ++whatIf.seq;
    const r = await App.api("/api/predict", { file: current._file, module: ex.index, gains: whatIf.values });
    if (seq !== whatIf.seq) return;
    Object.assign(whatIf, { pred: r, file: current._file, index: ex.index });
    paintPrediction();
    redraw();
  }

  function paintPrediction() {
    const p = whatIf.pred, ex = explained();
    const q = $("#wi-quality", root), box = $("#wi-table", root);
    if (!p || !ex || whatIf.file !== current._file || whatIf.index !== ex.index) { q.textContent = ""; box.innerHTML = ""; return; }
    if (!p.ok) { q.textContent = ""; box.innerHTML = `<p class="hint">${esc(p.reason || p.error || "No prediction.")}</p>`; return; }
    q.innerHTML = `<span class="chip ${p.quality === "good" ? "good" : p.quality === "fair" ? "warn" : "bad"}">model ${esc(p.quality)}</span>`;
    const S = p.summary, u = p.units;
    const row = (label, lk, f) => `<tr><td><span class="term" data-learn="${lk}">${label}</span></td>${["measured", "replay", "predicted"].map(k => `<td class="num">${f(S[k] || {})}</td>`).join("")}</tr>`;
    const ms = v => v == null ? "–" : fmt(v * 1000, 0) + " ms";
    box.innerHTML = `<table class="t"><thead><tr><th></th><th>This run</th><th>Model replay</th><th>Prediction</th></tr></thead><tbody>
      ${row("Rise", "rise_time", s => ms(s.rise_time))}
      ${row("Overshoot", "overshoot", s => s.overshoot_pct == null ? "–" : fmt(s.overshoot_pct, 1) + "%")}
      ${row("Settle", "settling_time", s => s.settled === false ? "never" : ms(s.settling_time))}
      ${row("Left over", "steady_state_error", s => s.steady_state_error == null ? "–" : fmt(s.steady_state_error, 3) + u)}
      ${row("Swings", "oscillation", s => s.oscillations == null ? "–" : s.oscillations)}</tbody></table>
      <p class="hint">${esc(p.note)} Learned: kS ${fmt(p.model.kS, 3)} V, kV ${fmt(p.model.kV, 4)}, kA ${fmt(p.model.kA, 5)}; the recording runs ${p.delay_ms} ms late.</p>`;
  }

  function paintExplain() {
    const e = current && current.explain;
    const sel = $("#xmod", root);
    sel.innerHTML = e && e.modules ? e.modules.map((m, i) => `<option value="${i}">${esc(abbr(m.module))}</option>`).join("") : "";
    sel.value = String(xmod);
    paintStory();
    paintWhatIf();
  }

  function paintSteps() {
    const ch = (current && current.channels) || {};
    const box = $("#steps", root);
    if (!current || !(current.test === "steer_step" || current.test === "drive_step")) { box.innerHTML = ""; return; }
    const sp = current.test === "steer_step" ? ch[`m${modIdx(ch, "sp")[0]}.sp`] : ch.sp;
    const t = ch.t || [];
    if (!sp) { box.innerHTML = ""; return; }
    const segs = [], unit = current.test === "steer_step" ? "°" : " m/s";
    let start = 0;
    for (let i = 1; i <= sp.length; i++) {
      if (i === sp.length || Math.abs(sp[i] - sp[i - 1]) > 1e-6) { segs.push([start, i - 1]); start = i; }
    }
    box.innerHTML = `<button class="btn small ${stepSel == null ? "on" : ""}" data-z="all" data-tip="tune.steps">Whole run</button>` +
      segs.slice(1).map(([a, b], k) => {
        const d = sp[a] - sp[a - 1];
        return `<button class="btn small ${stepSel === k + 1 ? "on" : ""}" data-k="${k + 1}" data-a="${t[a]}" data-b="${t[b]}" data-tip="tune.steps" data-quiet>Step ${k + 1}: ${d > 0 ? "+" : ""}${+d.toFixed(2)}${unit}</button>`;
      }).join("");
    $$("button", box).forEach(b => b.onclick = () => selectStep(b.dataset.z ? null : +b.dataset.k));
  }

  function selectStep(k) {
    const b = k == null ? null : $(`#steps button[data-k="${k}"]`, root);
    stepSel = b ? k : null;
    zoom = b ? [Math.max(0, +b.dataset.a - 0.05), +b.dataset.b] : null;
    // A step picked: the story says what happens in it, moment by moment.
    if (b) showPane("story-panel");
    $$("#steps button", root).forEach(x => x.classList.toggle("on", x === b || (!b && x.dataset.z)));
    paintStory();
    redraw();
  }

  function paintMetrics() {
    const rep = (current && current.report) || {};
    const mods = rep.modules || {};
    const rows = [];
    for (const [name, m] of Object.entries(mods)) {
      for (const s of (m.steps || [])) {
        rows.push(`<tr><td>${abbr(name)}</td><td class="num">${fmt(s.from, 2)} → ${fmt(s.to, 2)}</td>
          <td class="num">${fmt(s.dead_time * 1000, 0)}</td><td class="num">${fmt(s.rise_time * 1000, 0)}</td>
          <td class="num">${fmt(s.overshoot_pct, 1)}</td><td class="num">${s.settled ? fmt(s.settling_time * 1000, 0) : "never"}</td>
          <td class="num">${fmt(s.steady_state_error, 3)}</td><td class="num">${s.oscillations}</td>
          <td class="num">${s.saturation == null ? "–" : fmt(100 * s.saturation, 0)}</td></tr>`);
      }
      if (m.kV != null || m.kS != null) {
        rows.push(`<tr><td>${abbr(name)}</td><td colspan="8" class="mono">kS ${fmt(m.kS, 3)} V · kV ${fmt(m.kV, 3)} V/(m/s) · kA ${fmt(m.kA, 3)} V/(m/s²) · R² ${fmt(m.r2, 4)} · ${m.samples || 0} samples ${m.ok === false ? "· " + esc(m.reason) : ""}</td></tr>`);
      }
    }
    const th = (label, lk) => `<th class="num"><span class="term" tabindex="0" data-learn="${lk}">${label}</span></th>`;
    const u = current && current.test === "steer_step" ? "°" : "m/s";
    $("#metrics", root).innerHTML = rows.length ? `<table class="t"><thead><tr><th>Module</th><th class="num">Step (${u})</th>${th("Delay ms", "dead_time")}
      ${th("Rise ms", "rise_time")}${th("Overshoot %", "overshoot")}${th("Settle ms", "settling_time")}${th(`Left over (${u})`, "steady_state_error")}${th("Swings", "oscillation")}${th("Flat out %", "saturation")}</tr></thead>
      <tbody>${rows.join("")}</tbody></table>` : "";
    $("#metrics-wrap", root).hidden = !rows.length;
  }

  function describeAction(a) {
    if (a.type === "gains") {
      const g = liveGains();
      return Object.entries(a.values).map(([k, v]) => `${gainName(k)} ${num(g[k])} → ${num(v)}`).join(", ");
    }
    if (a.type === "run") return `run ${testName(a.test)}${a.env && a.env !== "ANY" ? " (" + whereWord(a.env).toLowerCase() + ")" : ""}`;
    if (a.type === "config") return `edit ${a.file}: ${a.path.join(".")} = ${a.value}`;
    if (a.type === "troubleshoot") return "open the troubleshooter";
    if (a.type === "save") return "save gains to the files";
    return "";
  }

  async function doAction(a, why) {
    if (a.type === "gains") {
      await applyEdits(Object.fromEntries(Object.entries(a.values).map(([k, v]) => [k, +v])),
        why ? "Tune tab, advice: " + why : "Tune tab, advice");
      if (a.then) {
        // Gains measured by one test are checked by another (the feedforward, by Drive speed).
        const to = Object.entries(LOOPS).find(([, v]) => v.test === a.then.test);
        if (to) { setLoop(to[0]); App.toast(`Applied. Now run ${testName(a.then.test)}.`); return; }
      }
      if (target === "practice") run();
    } else if (a.type === "run") {
      const to = Object.entries(LOOPS).find(([, v]) => v.test === a.test);
      if (to) setLoop(to[0]);
      if (a.env && target === "robot" && App.env() !== a.env && a.env !== "ANY") openEnvironment(a.env);
    } else if (a.type === "troubleshoot") {
      Trouble.open(a.symptom);
    } else if (a.type === "config") {
      let value = a.value;
      if (value === "toggle") value = !(((App.lint || {}).swervedrive || {}).invertedIMU);
      if (typeof value === "string" && value.startsWith("x")) {
        // A scale, e.g. the wheel diameter times the measured wheel scale.
        const d = ((((App.lint || {}).physical || {}).conversionFactors || {}).drive || {}).diameter;
        value = +(d * +value.slice(1)).toFixed(4);
      }
      await App.previewAndSave({ kind: "edit", file: a.file, path: a.path, value }, "Change the robot's configuration");
    } else if (a.type === "save") {
      saveGains();
    }
  }

  // What changed since the run before: the gains that differ and the goals that moved.
  function whatChanged() {
    if (!compare || compare.test !== current.test) return "";
    const a = compare.gains || {}, b = current.gains || {};
    const g = gainDiff(current.test, a, b).map(k => `${gainName(k)} ${num(a[k] || 0)} → ${num(b[k] || 0)}`);
    const was = Object.fromEntries(((compare.report || {}).targets || []).map(t => [t.name, t.value]));
    const t = ((current.report || {}).targets || []).filter(x => x.name in was && num(was[x.name]) !== num(x.value))
      .map(x => `${x.name} ${num(was[x.name])} → ${num(x.value)}`);
    return `<p class="small"><b>Since the run before:</b> ${g.length ? esc(g.join(", ")) : "no gain changed"}${t.length ? " · " + esc(t.join(" · ")) : " · no goal moved"}.</p>`;
  }

  function paintReport() {
    const rep = current && current.report;
    const box = $("#report", root), card = $("#next-step", root);
    box.hidden = false;
    if (!rep) { box.innerHTML = `<span class="hint">No analysis for this run.</span>`; card.hidden = true; return; }
    const T = rep.targets || [];
    const goal = t => `${t.lower_is_better === false ? "at least" : "under"} ${num(t.target)}`;
    const targets = T.map(t => `<div class="target ${t.met ? "met" : "miss"}"><span aria-hidden="true">${t.met ? "✓" : "✗"}</span>
      <span><span class="sr">${t.met ? "met:" : "missed:"}</span> ${esc(t.name)}</span><span class="v">${typeof t.value === "number" ? num(t.value) : t.value == null ? (t.lower_is_better === false ? "–" : "never") : esc(t.value)}, goal ${goal(t)}</span></div>`).join("");
    // rep.next is a copy of one finding after JSON parsing, so find it by content, not identity.
    const nextIdx = rep.next ? (rep.findings || []).findIndex(f => f.title === rep.next.title
      && JSON.stringify(f.action || null) === JSON.stringify(rep.next.action || null)) : -1;
    const next = nextIdx >= 0 ? rep.findings[nextIdx] : null;
    const where = target === "practice" ? ", then runs again on the practice pod" : next && next.action.type === "gains" ? ", live on the robot" : "";
    card.innerHTML = `<p><b>${esc(rep.summary || "")}</b></p>
      ${T.length ? `<p class="small">${T.filter(t => t.met).length} of ${T.length} goals met${rep.score != null ? ` · score ${rep.score}` : ""}.</p>` : ""}
      ${next && next.action.type !== "stop" ? `<div class="row"><button class="btn primary" data-i="${nextIdx}" data-tip="tune.next" data-quiet>Try this</button>
        <span><b>${esc(next.title)}</b> <span class="small muted">${esc(describeAction(next.action))}${where}</span></span></div>` : ""}
      ${whatChanged()}`;
    card.hidden = false;
    // The banner already says "practice pod", so its finding would only repeat it.
    const findings = (rep.findings || []).map((f, i) => f.kind === "practice" ? "" : `<div class="finding">
      <div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span>${i === nextIdx ? `<span class="small muted">· the next step, above</span>` : ""}</div>
      <div class="why">${Learn.link(f.why, 3)}</div>
      ${f.action && i !== nextIdx && f.action.type !== "stop" ? `<div class="row"><button class="btn small" data-i="${i}" data-tip="tune.do" data-quiet>Do this</button>
        <span class="small muted">${esc(describeAction(f.action))}</span></div>` : ""}</div>`).join("");
    box.innerHTML = `<div class="stack">
      ${targets ? `<div><h3>Goals</h3><div class="targets">${targets}</div></div>` : ""}
      <div>${findings}</div></div>`;
    $$("[data-i]", box).concat($$("[data-i]", card)).forEach(b => b.onclick = () => doAction(rep.findings[+b.dataset.i].action, rep.findings[+b.dataset.i].title));
  }

  function show(doc) {
    if (current && current.test === doc.test) compare = current;
    current = doc;
    zoom = null;
    stepSel = null;
    xmod = 0;
    whatIf = { values: {}, pred: null, seq: whatIf.seq };
    const where = doc.practice ? "practice pod" : whereWord(doc.env || "").toLowerCase();
    $("#res-title", root).textContent = [testName(doc.test), where, clock(doc.saved || (doc._file || "").slice(0, 15))]
      .filter(Boolean).join(" · ") + (doc.outcome && doc.outcome !== "DONE" ? ` · ${doc.outcome.toLowerCase()}` : "");
    $("#res-file", root).textContent = doc._file || "";
    $("#export", root).hidden = !doc._file || !!doc.practice;
    $("#cmp-wrap", root).hidden = !(compare && compare.test === doc.test);
    $("#empty-run", root).hidden = true;
    $("#run-view", root).hidden = false;
    $("#practice-flag", root).hidden = !doc.practice;
    paintExplain();
    redraw();
    paintSteps();
    paintMetrics();
    paintReport();
    $$("#history tr", root).forEach(tr => tr.toggleAttribute("aria-current", tr.dataset.f === doc._file));
  }

  async function loadHistory() {
    const r = await App.api("/api/runs");
    const test = LOOPS[loop].test;
    const list = (r.runs || []).filter(x => x.test === test).slice(0, 12);
    // What each run changed from the one before it (the list is newest first).
    const changed = (x, prev) => {
      if (!prev) return "";
      const a = prev.gains || {}, b = x.gains || {};
      const d = gainDiff(x.test, a, b);
      return d.length ? d.slice(0, 2).map(k => `${gainName(k)} → ${num(b[k] || 0)}`).join(", ") + (d.length > 2 ? ` +${d.length - 2}` : "") : "same gains";
    };
    $("#history", root).innerHTML = list.length ? `<table class="t"><caption class="sr">Earlier runs of this test</caption>
      <thead><tr><th>When</th><th>Where</th><th class="num">Score</th><th>Changed</th></tr></thead><tbody>${list.map((x, i) => `<tr data-f="${esc(x.file)}">
      <td class="nowrap"><button class="linkbtn" data-open="${esc(x.file)}">${esc(clock(x.saved))}</button></td><td>${x.practice ? "practice" : esc(whereWord(x.env || "").toLowerCase())}</td>
      <td class="num">${x.score == null || (x.outcome && x.outcome !== "DONE") ? "–" : x.score}</td><td class="small">${esc(changed(x, list[i + 1]))}</td></tr>`).join("")}</tbody></table>`
      : `<span class="hint">None yet for this test.</span>`;
    $$("#history [data-open]", root).forEach(b => b.onclick = async () => {
      const d = await App.api("/api/runs/" + encodeURIComponent(b.dataset.open));
      d._file = b.dataset.open;
      show(d);
    });
    if (current) $$("#history tr", root).forEach(tr => tr.toggleAttribute("aria-current", tr.dataset.f === current._file));
  }

  async function saveGains() {
    if (target === "practice") { App.toast("Practice gains are not the robot's. Try them on the robot, then save."); return; }
    if (loop === "slip") { App.toast("Use Try this on the recommended limit to write it to the files."); return; }
    const prefix = { steer: ["Steer"], drive: ["Drive"], ff: ["FF"], spin: ["Chassis", "EncoderSync"], straight: ["Chassis", "EncoderSync"] }[loop];
    await App.previewAndSave({ kind: "gains", keys: prefix }, "Save the gains the robot is running");
  }

  // The faults on what this test runs: the steer motors (one module's, when one is picked), the drive
  // motors, or all of them and the gyro for a chassis test. None for the practice pod.
  const MODNAME = { FL: "front left", FR: "front right", BL: "back left", BR: "back right" };
  function faultScope() {
    if (target === "practice") return null;
    if (loop === "steer") return { kind: "steer", module, quiet: true, what: module === "ALL" ? "the steer motors" : `the ${MODNAME[module] || module} steer motor` };
    if (["drive", "ff", "slip"].includes(loop)) return { kind: "drive", quiet: true, what: "the drive motors" };
    return { kind: "swerve", gyro: true, quiet: true, what: "the swerve motors and the gyro" };
  }

  // ---------------------------------------------------------------- controls
  function setLoop(l) {
    loop = l;
    edits = {};
    if (!LOOPS[l].practice) target = "robot";
    $$("#loopseg button", root).forEach(b => b.classList.toggle("on", b.dataset.loop === l));
    $("#blurb", root).innerHTML = Learn.link(LOOPS[l].blurb, 3);
    $("#modrow", root).hidden = l !== "steer";
    sync();
    loadHistory();
  }

  function sync() {
    $$("#targetseg button", root).forEach(b => {
      b.classList.toggle("on", b.dataset.t === target);
      b.disabled = b.dataset.t === "practice" && !LOOPS[loop].practice;
    });
    $$("#surfseg button", root).forEach(b => b.classList.toggle("on", b.dataset.s === surface));
    $("#surfacerow", root).hidden = target !== "practice";
    const why = needs();
    $("#needs", root).innerHTML = why.text ? `<div class="callout ${why.block ? "warn" : ""}">${esc(why.text)}</div>` : "";
    $("#run", root).disabled = why.block;
    $("#run", root).textContent = target === "practice" ? "Run on the practice pod" : "Run on the robot";
    $("#apply", root).textContent = target === "practice" ? "Use these" : "Apply live";
    paintGains();
  }

  $$("#loopseg button", root).forEach(b => b.onclick = () => setLoop(b.dataset.loop));
  $$("#targetseg button", root).forEach(b => b.onclick = () => { target = b.dataset.t; edits = {}; sync(); });
  $$("#surfseg button", root).forEach(b => b.onclick = () => { surface = b.dataset.s; sync(); });
  $("#module", root).onchange = e => { module = e.target.value; };
  $("#pattern", root).onchange = e => { pattern = +e.target.value; };
  $("#run", root).onclick = run;
  $("#try-practice", root).onclick = () => { target = "practice"; edits = {}; sync(); run(); };
  $("#export", root).onclick = async () => {
    if (!current || !current._file) return;
    const r = await App.api("/api/export", { file: current._file });
    App.toast(r.ok ? `Wrote ${r.path}. Open it in AdvantageScope${r.sysid ? " or SysId" : ""}.` : (r.error || "Export failed."), 8000);
  };
  $("#apply", root).onclick = () => applyEdits();
  $("#revert", root).onclick = () => { edits = {}; paintGains(); };
  $("#save", root).onclick = saveGains;
  $("#cmp", root).onchange = redraw;
  $("#xmod", root).onchange = e => { xmod = +e.target.value; whatIf = { values: {}, pred: null, seq: whatIf.seq }; paintStory(); paintWhatIf(); redraw(); };
  $("#wi-reset", root).onclick = () => { whatIf = { values: {}, pred: null, seq: whatIf.seq + 1 }; paintWhatIf(); redraw(); };
  $("#wi-use", root).onclick = () => {
    if (!Object.keys(whatIf.values).length) { App.toast("Drag a slider first."); return; }
    Object.assign(edits, whatIf.values);
    paintGains();
    App.toast(target === "practice" ? "In the gains box. Press Use these, then Run, to check the prediction." : "In the gains box. Apply live and Run to see what the robot really does.", 6000);
  };
  window.addEventListener("resize", redraw);

  App.on("state", () => { if (root.classList.contains("on") && !Object.keys(edits).length) { sync(); } });
  App.on("lint", () => { practiceGains = null; paintGains(); });
  App.on("tab", t => { if (t === "tune") { sync(); redraw(); } });
  App.on("run", doc => { if (root.classList.contains("on")) return; if (Object.values(LOOPS).some(v => v.test === doc.test)) show(doc); });

  // On a phone the earlier-runs list starts closed, so the result isn't pushed below it.
  if (window.matchMedia && matchMedia("(max-width: 900px)").matches) $("#history-panel", root).open = false;
  setLoop("steer");
  Faults.mount($("#tune-faults", root), faultScope);
  return {
    open(l, opts = {}) {
      if (opts.target) target = opts.target;
      if (opts.module) {
        // One part: the tuner on that module only (a replaced or misbehaving one).
        module = abbr(opts.module);
        const m = $("#module", root);
        if (m) m.value = module;
      }
      if (opts.fresh) {
        // From the Guide: every module, the standard steps. A one-corner run (the troubleshooter's
        // "pick FL only") never stands in for all four.
        module = "ALL"; pattern = 0;
        const m = $("#module", root), p = $("#pattern", root);
        if (m) m.value = "ALL";
        if (p) p.value = "0";
      }
      setLoop(l);
      App.show("tune");
    },
    show,
  };
})();
