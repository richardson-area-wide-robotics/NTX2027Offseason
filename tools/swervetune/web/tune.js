// Tune tab: run a test, see it, read the advice, try the suggestion, compare, save.
"use strict";

const Tune = (() => {
  const root = $("#tab-tune");
  const LOOPS = {
    steer: { label: "Steering", test: "steer_step", practice: true,
      blurb: "How fast and how precisely each wheel turns to the angle it is told. Run it on blocks first, then on the floor: the robot does not drive, the wheels only turn in place, and carpet is where the real numbers come from." },
    drive: { label: "Drive speed", test: "drive_step", practice: true,
      blurb: "How well each wheel holds the speed it is told. On blocks it only checks direction and delay; tune it on the floor, where the wheel carries the robot." },
    ff: { label: "Feedforward", test: "drive_ff", practice: true,
      blurb: "Measures, per module, the voltage it takes to start moving (kS), to hold each speed (kV) and to accelerate (kA). The biggest single step to a tight drivetrain. Floor for real numbers; blocks finds a binding module." },
    spin: { label: "Spin", test: "spin", practice: false,
      blurb: "Spins in place both ways and compares command, gyro and wheels. Finds an inverted gyro and wrong module positions." },
    straight: { label: "Straight line", test: "straight", practice: false,
      blurb: "Drives a measured line with no heading correction. Scores against AprilTags if on, otherwise a tape measure from your start mark." },
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

  root.innerHTML = `
    <div class="split">
      <div class="stack">
        <div class="panel">
          <div class="seg" id="loopseg">${Object.entries(LOOPS).map(([k, v]) => `<button data-loop="${k}">${v.label}</button>`).join("")}</div>
          <p class="hint" id="blurb"></p>
          <div class="row"><span class="small muted">Run on</span>
            <div class="seg" id="targetseg"><button data-t="robot">Robot</button><button data-t="practice">Practice pod</button></div></div>
          <div class="row" id="surfacerow"><span class="small muted">Practice surface</span>
            <div class="seg" id="surfseg"><button data-s="floor">Floor</button><button data-s="blocks">Blocks</button></div></div>
          <div class="row" id="modrow"><span class="small muted">Module</span>
            <select id="module"><option>ALL</option><option>FL</option><option>FR</option><option>BL</option><option>BR</option></select>
            <select id="pattern"><option value="0">Standard steps</option><option value="1">Small steps (friction)</option><option value="2">Large steps (saturation)</option></select></div>
          <div id="needs" class="hint"></div>
          <button class="btn primary" id="run">Run</button>
        </div>
        <div class="panel">
          <div class="row" style="justify-content:space-between"><h3>Gains</h3><span class="hint" id="gainsrc"></span></div>
          <div class="gains" id="gains"></div>
          <div class="row">
            <button class="btn" id="apply">Apply live</button>
            <button class="btn" id="revert">Revert edits</button>
            <button class="btn" id="save">Save to files…</button>
          </div>
          <p class="hint">Apply live changes the running robot only (never its flash); a restart puts back the files. Save writes the files.</p>
        </div>
        <div class="panel">
          <h3>Earlier runs</h3>
          <div id="history" class="small"></div>
        </div>
      </div>
      <div class="stack">
        <div class="panel">
          <div class="row" style="justify-content:space-between">
            <h2 id="res-title">No run yet</h2>
            <label class="row small"><input type="checkbox" id="cmp"> overlay the run before</label>
          </div>
          <div id="practice-flag" class="practice-flag" hidden>Practice pod: a model of a MAXSwerve module, not your robot.</div>
          <div class="plotwrap"><canvas class="plot" id="plot" aria-label="The setpoint and what the mechanism did"></canvas></div>
          <div class="steps" id="steps"></div>
          <div id="explain-head" class="row" style="justify-content:space-between" hidden>
            <h3>What the controller <span class="term" data-learn="error">saw</span> and <span class="term" data-learn="control_effort">did</span></h3>
            <label class="row small">Explain <select id="xmod"></select></label>
          </div>
          <div class="plotwrap" id="plot2wrap" hidden><canvas class="plot short" id="plot2" aria-label="The controller's output, split into its parts, in volts"></canvas></div>
          <p class="hint" id="explain-hint" hidden>Volts, so the parts add up. Hover the graph to read every part at that moment; hover a shaded area or a marker to learn what is happening there.</p>
          <div class="tblwrap" id="metrics"></div>
        </div>
        <div class="panel" id="report"><span class="hint">Run a test and the analysis and advice appear here.</span></div>
        <div class="panel" id="whatif" hidden>
          <div class="row" style="justify-content:space-between"><h3><span class="term" data-learn="what_if">What if…</span></h3><span class="small" id="wi-quality"></span></div>
          <p class="hint">Drag a gain: the dashed line on the top graph becomes the prediction for this same run with the new value. Then run it for real - the robot has the final word.</p>
          <div id="wi-sliders" class="wi-sliders"></div>
          <div id="wi-table" class="tblwrap"></div>
          <div class="row"><button class="btn" id="wi-use">Put these in the gains box</button><button class="btn" id="wi-reset">Back to the run's gains</button></div>
        </div>
        <div class="panel" id="story-panel" hidden>
          <h3 id="story-head">What this run shows</h3>
          <ol id="story" class="story small"></ol>
        </div>
      </div>
    </div>`;

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
      g[`FF/${m}/kS`] = f.kS || 0; g[`FF/${m}/kV`] = f.kV || 2.915; g[`FF/${m}/kA`] = f.kA || 0;
    }
    return g;
  }

  function fields() {
    if (loop === "steer") return GAINS.steer;
    if (loop === "drive") return GAINS.drive;
    if (loop === "ff") {
      const mods = target === "practice" ? ["frontleft"] : App.modules();
      return mods.flatMap(m => [[`FF/${m}/kS`, `${abbr(m)} kS`, "volts"], [`FF/${m}/kV`, `${abbr(m)} kV`, "V per m/s"], [`FF/${m}/kA`, `${abbr(m)} kA`, "V per m/s²"]]);
    }
    return GAINS.chassis;
  }

  function paintGains() {
    const g = liveGains();
    $("#gainsrc", root).textContent = target === "practice" ? "practice copy" : (App.connected() ? "running on the robot" : "connect to see the robot's");
    $("#gains", root).innerHTML = fields().map(([key, label, unit]) => {
      const v = key in edits ? edits[key] : g[key];
      const lk = learnKey(key);
      return `<label class="gain">${lk ? `<span class="term" data-learn="${lk}">${esc(label)}</span>` : esc(label)}<input type="number" step="any" data-key="${esc(key)}" value="${v == null || !isFinite(v) ? "" : +(+v).toPrecision(6)}" class="${key in edits ? "changed" : ""}"><span class="unit">${esc(unit)}</span></label>`;
    }).join("");
    $$("#gains input", root).forEach(inp => inp.oninput = () => {
      const k = inp.dataset.key;
      if (inp.value === "") delete edits[k]; else edits[k] = +inp.value;
      inp.classList.toggle("changed", k in edits);
    });
  }

  async function applyEdits(values) {
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
    const r = await App.api("/api/gains", { values: vals });
    App.toast(r.status || r.error, 6000);
    if (r.gains) App.state.gains = r.gains;
    edits = {};
    paintGains();
    return r.ok;
  }

  // ---------------------------------------------------------------- run
  function needs() {
    const L = LOOPS[loop];
    if (target === "practice") return L.practice ? "" : "Spin and straight line need a real robot.";
    if (!App.connected()) return "Connect to a robot or the simulator.";
    const env = App.env();
    if (env === "UNSET") return "Say where the robot is first (Environment, at the top).";
    if ((loop === "straight") && env === "BLOCKS") return "The straight-line test needs the robot on the floor.";
    if (env === "FIELD") return "On the floor: hold SPACE (or the tester's controller bumper) for the whole run.";
    return "";
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

  function seriesFor(doc, faded) {
    const ch = doc.channels || {}, t = ch.t || [], names = (doc.robot && doc.robot.modules) || [];
    const a = faded ? 0.35 : 1, out = [];
    const label = i => faded ? null : abbr(names[i] || "m" + i);
    if (doc.test === "steer_step") {
      for (const i of modIdx(ch, "sp")) {
        out.push({ x: t, y: ch[`m${i}.sp`], color: COLORS[i % 4], dash: [5, 4], width: 1.2, alpha: a });
        out.push({ x: t, y: ch[`m${i}.steer`], color: COLORS[i % 4], alpha: a, label: label(i) });
      }
    } else if (doc.test === "drive_step") {
      out.push({ x: t, y: ch.sp, color: "--sp", dash: [5, 4], width: 1.4, alpha: a, label: faded ? null : "told" });
      for (const i of modIdx(ch, "v")) out.push({ x: t, y: ch[`m${i}.v`], color: COLORS[i % 4], alpha: a, label: label(i) });
    } else if (doc.test === "drive_ff") {
      for (const i of modIdx(ch, "volts")) out.push({ x: ch[`m${i}.v`], y: ch[`m${i}.volts`], color: COLORS[i % 4], points: true, alpha: a, label: label(i) });
    } else if (doc.test === "spin") {
      const h = ch.heading || [], rate = h.map((v, k) => k ? (v - h[k - 1]) / (t[k] - t[k - 1]) * Math.PI / 180 : NaN);
      out.push({ x: t, y: ch.cmd_omega, color: "--sp", dash: [5, 4], alpha: a, label: faded ? null : "told rad/s" });
      out.push({ x: t, y: rate, color: COLORS[0], alpha: a, label: faded ? null : "gyro rad/s" });
    } else if (doc.test === "straight") {
      out.push({ x: ch.x || [], y: ch.y || [], color: COLORS[0], alpha: a, label: faded ? null : "odometry path (m)" });
    } else if (doc.test === "capture") {
      for (const i of modIdx(ch, "steer")) out.push({ x: t, y: ch[`m${i}.steer`], color: COLORS[i % 4], alpha: a, label: label(i) });
    }
    return out;
  }

  function axes(doc) {
    return { steer_step: ["s", "degrees"], drive_step: ["s", "m/s"], drive_ff: ["m/s", "volts"], spin: ["s", "rad/s"],
             straight: ["x (m)", "y (m)"], capture: ["s", "degrees"] }[doc.test] || ["s", ""];
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
      s.push({ x: p.t, y: p.predicted, color: "--accent", dash: [2, 3], width: 2.2, label: "what if" });
    }
    const [xl, yl] = axes(current);
    Plot.draw($("#plot", root), { series: s, xrange: zoom, xlabel: xl, ylabel: yl,
      annotations: ex ? notes(ex.response) : [], readout: ex ? x => readout(ex, x) : null });
    $("#explain-head", root).hidden = !ex;
    $("#plot2wrap", root).hidden = !ex;
    $("#explain-hint", root).hidden = !ex;
    if (!ex) return;
    const t = ex.t, neg = ex.battery.map(b => -b);
    const c = [
      { x: t, y: ex.battery, color: "--bad", dash: [6, 4], width: 1, label: "battery" },
      { x: t, y: neg, color: "--bad", dash: [6, 4], width: 1 },
      ...(ex.loop === "drive" ? [{ x: t, y: ex.ff, color: "--sp", width: 1.6, label: "FF" }] : []),
      { x: t, y: ex.p, color: "--s0", width: 1.4, label: "P" },
      ...(ex.gains.kI ? [{ x: t, y: ex.i, color: "--s3", width: 1.4, label: "I" }] : []),
      ...(ex.gains.kD ? [{ x: t, y: ex.d, color: "--s2", width: 1.4, label: "D" }] : []),
      { x: t, y: ex.asked, color: "--ink", dash: [4, 3], width: 1.2, label: "asked" },
      { x: t, y: ex.applied, color: "--ink", width: 1.8, label: "applied" },
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
    const chip = n => `<span class="chip learn-chip" data-learn="${esc(n.learn)}">${esc((Learn.L[n.learn] || {}).title || n.learn)}</span>`;
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
        `<li>${chip(b.n)} <span class="muted small">in ${b.steps.size} of ${steps} steps · biggest:</span>
          <button class="btn small" data-step="${b.n.step}">step ${b.n.step}</button> ${Learn.link(b.n.text, 3)}</li>`);
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
        <span class="mono" data-v="${esc(key)}">${+(+val).toPrecision(3)}</span><span class="muted small">ran ${+(+base).toPrecision(3)}</span></label>`;
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
    const segs = [];
    let start = 0;
    for (let i = 1; i <= sp.length; i++) {
      if (i === sp.length || Math.abs(sp[i] - sp[i - 1]) > 1e-6) { segs.push([start, i - 1]); start = i; }
    }
    box.innerHTML = `<button class="btn small ${stepSel == null ? "on" : ""}" data-z="all">Whole run</button>` +
      segs.slice(1).map(([a, b], k) => {
        const d = sp[a] - sp[a - 1];
        return `<button class="btn small ${stepSel === k + 1 ? "on" : ""}" data-k="${k + 1}" data-a="${t[a]}" data-b="${t[b]}">Step ${k + 1}: ${d > 0 ? "+" : ""}${+d.toFixed(2)}</button>`;
      }).join("");
    $$("button", box).forEach(b => b.onclick = () => selectStep(b.dataset.z ? null : +b.dataset.k));
  }

  function selectStep(k) {
    const b = k == null ? null : $(`#steps button[data-k="${k}"]`, root);
    stepSel = b ? k : null;
    zoom = b ? [Math.max(0, +b.dataset.a - 0.05), +b.dataset.b] : null;
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
    const th = (label, lk) => `<th><span class="term" data-learn="${lk}">${label}</span></th>`;
    $("#metrics", root).innerHTML = rows.length ? `<table class="t"><thead><tr><th>Module</th><th>Step</th>${th("Delay ms", "dead_time")}
      ${th("Rise ms", "rise_time")}${th("Overshoot %", "overshoot")}${th("Settle ms", "settling_time")}${th("Left over", "steady_state_error")}${th("Swings", "oscillation")}${th("Flat out %", "saturation")}</tr></thead>
      <tbody>${rows.join("")}</tbody></table>` : "";
  }

  function describeAction(a) {
    if (a.type === "gains") {
      const g = liveGains();
      return Object.entries(a.values).map(([k, v]) => `${k.replace(/^.*?\//, "").replace("FF/", "")} ${fmt(g[k], 4)} → ${+(+v).toPrecision(4)}`).join(", ");
    }
    if (a.type === "run") return `run ${a.test}${a.env ? " (" + a.env.toLowerCase() + ")" : ""}`;
    if (a.type === "config") return `edit ${a.file}: ${a.path.join(".")} = ${a.value}`;
    if (a.type === "troubleshoot") return "open the troubleshooter";
    if (a.type === "save") return "save gains to the files";
    return "";
  }

  async function doAction(a) {
    if (a.type === "gains") {
      await applyEdits(Object.fromEntries(Object.entries(a.values).map(([k, v]) => [k, +v])));
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

  function paintReport() {
    const rep = current && current.report;
    const box = $("#report", root);
    if (!rep) { box.innerHTML = `<span class="hint">No analysis for this run.</span>`; return; }
    const targets = (rep.targets || []).map(t => `<div class="target"><span>${t.met ? "✓" : "✗"}</span>
      <span>${esc(t.name)}</span><span class="v">${typeof t.value === "number" ? fmt(t.value, 3) : esc(t.value)} / ${esc(t.target)}</span></div>`).join("");
    const findings = (rep.findings || []).map((f, i) => `<div class="finding">
      <div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
      <div class="why">${Learn.link(f.why, 3)}</div>
      ${f.action ? `<div class="row"><button class="btn small ${f === rep.next ? "primary" : ""}" data-i="${i}">${f === rep.next ? "Try this" : "Do this"}</button>
        <span class="small muted">${esc(describeAction(f.action))}</span></div>` : ""}</div>`).join("");
    box.innerHTML = `<div class="stack">
      <p><b>${esc(rep.summary || "")}</b></p>
      ${rep.score != null ? `<div class="score"><span class="mono">${rep.score}/100</span><div class="meter"><div style="width:${rep.score}%"></div></div>
        <span class="small muted">cost ${fmt(rep.cost, 2)} (lower is tighter)</span></div>` : ""}
      ${targets ? `<div class="targets">${targets}</div>` : ""}
      <div>${findings}</div></div>`;
    $$("[data-i]", box).forEach(b => b.onclick = () => doAction(rep.findings[+b.dataset.i].action));
  }

  function show(doc) {
    if (current && current.test === doc.test) compare = current;
    current = doc;
    zoom = null;
    stepSel = null;
    xmod = 0;
    whatIf = { values: {}, pred: null, seq: whatIf.seq };
    $("#res-title", root).textContent = `${doc.test} · ${doc.env || ""} · ${doc.outcome || ""}${doc._file ? " · " + doc._file : ""}`;
    $("#practice-flag", root).hidden = !doc.practice;
    paintExplain();
    redraw();
    paintSteps();
    paintMetrics();
    paintReport();
  }

  async function loadHistory() {
    const r = await App.api("/api/runs");
    const test = LOOPS[loop].test;
    const list = (r.runs || []).filter(x => x.test === test).slice(0, 12);
    $("#history", root).innerHTML = list.length ? `<table class="t"><tbody>${list.map(x => `<tr data-f="${esc(x.file)}" style="cursor:pointer">
      <td class="mono">${esc((x.saved || "").slice(9, 15).replace(/(..)(..)(..)/, "$1:$2:$3"))}</td><td>${x.practice ? "practice" : esc(x.env || "")}</td>
      <td class="num">${x.score == null ? "–" : x.score}</td><td class="num">${fmt(x.cost, 2)}</td></tr>`).join("")}</tbody></table>`
      : `<span class="hint">None yet for this test.</span>`;
    $$("#history tr", root).forEach(tr => tr.onclick = async () => {
      const d = await App.api("/api/runs/" + encodeURIComponent(tr.dataset.f));
      d._file = tr.dataset.f;
      show(d);
    });
  }

  async function saveGains() {
    if (target === "practice") { App.toast("Practice gains are not the robot's. Try them on the robot, then save."); return; }
    const prefix = { steer: ["Steer"], drive: ["Drive"], ff: ["FF"], spin: ["Chassis", "EncoderSync"], straight: ["Chassis", "EncoderSync"] }[loop];
    await App.previewAndSave({ kind: "gains", keys: prefix }, "Save the gains the robot is running");
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
    $("#needs", root).textContent = why;
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

  setLoop("steer");
  return {
    open(l, opts = {}) {
      if (opts.target) target = opts.target;
      setLoop(l);
      App.show("tune");
    },
    show,
  };
})();
