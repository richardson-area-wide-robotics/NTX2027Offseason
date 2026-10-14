// Bring-up tab: a robot just handed over by the mechanical and electrical teams, brought up against
// its design file (src/main/deploy/design/devices.json) before it is tuned. The design file is
// drafted from the code or imported from the design team's spreadsheet, checked against itself and
// the code; then the robot off, the sensors, each mechanism motor alone (the robot's motor_test, with
// a person saying which way it went), each shared shaft, and a signed report.
"use strict";

const Bringup = (() => {
  const root = $("#tab-bringup");
  let data = null;        // /api/bringup
  let last = {};          // motor or shaft -> the latest motor_test report shown

  const isSwerve = n => / (drive|steer)$/.test(n);
  const mechanism = d => ((d && d.motors) || []).filter(m => m.name && !isSwerve(m.name) && !m.follows);
  const shafts = d => {
    const out = {};
    ((d && d.motors) || []).forEach(m => { if (m.shaft) (out[m.shaft] = out[m.shaft] || []).push(m); });
    return Object.fromEntries(Object.entries(out).filter(([, v]) => v.length > 1));
  };
  const findings = F => (F || []).length ? `<div class="cfg-list">${F.map(f => `<div class="finding" data-level="${esc(f.level)}">
      <div class="head"><span class="level ${f.level}">${f.level}</span><span class="title">${esc(f.title)}</span></div>
      <div class="why">${Learn.link(f.why, 2)}</div></div>`).join("")}</div>` : `<p><span class="level ok">ok</span> Nothing to fix.</p>`;
  const swatch = c => `<span class="bus-swatch" style="--c:${esc((data.colors || {})[c] || "#999")}" aria-hidden="true"></span>`;

  root.innerHTML = `
    <div class="jobs" data-jobs="bringup">
    ${HowTo.slot("bringup")}
    <div class="job-area">
      <div class="panel" id="br-design">
        <div class="row" style="justify-content:space-between"><h2 data-tip="br.design">The design file</h2>
          <div class="row"><label class="row small" data-tip="br.controller">Controller <select id="br-ctl">
            <option value="roborio2">roboRIO 2</option><option value="roborio">roboRIO 1</option><option value="systemcore">SystemCore</option></select></label>
            <button class="btn" id="br-draft" data-tip="br.draft">Draft from the code…</button>
            <label class="btn" data-tip="br.csv">Import a spreadsheet (CSV)…<input type="file" id="br-csv" accept=".csv,text/csv" hidden></label></div></div>
        ${HowTo.steps({ need: "The design team's list of every device: CAN IDs, PDH ports and breakers, roboRIO ports, gear ratios, which way is positive, and which motors share a shaft.",
          steps: ["No file yet: <b>Draft from the code</b> writes one from what the code says; or <b>Import a spreadsheet</b> saved as CSV (one row per motor or sensor).",
            "Go through it with the mechanical and electrical leads: correct anything the code got wrong, fill in breakers, ratios and the positive direction.",
            "Save it. It lives with the code (deployed with it), in YAGSL's style: each device is <span class=\"mono\">{\"type\", \"id\", \"canbus\"}</span>."],
          good: "nothing to fix in the file itself." })}
        <div id="br-design-body"><p class="hint">Reading the design file…</p></div>
        ${HowTo.nextLine("design")}
      </div>
      <div class="panel" id="br-code">
        <h2 data-tip="br.code">The code against the design</h2>
        ${HowTo.steps({ steps: ["Each line is the code and the design saying different things: a CAN ID, a SPARK MAX against a SPARK Flex, a follower's direction, a port.",
          "Find out which is right (the label on the controller, the wire on the port), then fix the other one and redeploy."],
          good: "no errors; every motor in both." })}
        <div id="br-code-body"></div>
        ${HowTo.nextLine("code")}
      </div>
      <div class="panel" id="br-handover">
        <h2 data-tip="br.handover">Hand-over check, robot off</h2>
        ${HowTo.steps({ need: "The robot powered off, a multimeter, the electrical lead.",
          steps: ["Go down the list with the robot off; tick each one only once you have seen it.", "Anything not right: <b>Something to fix</b>, and say what."],
          good: "every item ticked before the robot is switched on." })}
        <div id="br-handover-body"></div>
        ${HowTo.nextLine("handover")}
      </div>
      <div class="panel" id="br-sensors">
        <h2 data-tip="br.sensors">Every sensor reads</h2>
        ${HowTo.steps({ need: "The robot on and disabled, connected.",
          steps: ["<b>Start the live readout</b>: each sensor's value, as the robot reads it.",
            "Trip each one by hand (block the beam, press the switch, turn the encoder). It is ticked the moment it changes.",
            "Untick any that changed the wrong way (the design's <b>Means</b> says which way is which), then <b>Stop</b>."],
          good: "every sensor ticked, each changing the way its design says." })}
        <div id="br-sensors-body"></div>
        ${HowTo.nextLine("sensors")}
      </div>
      <div class="panel" id="br-motors">
        <h2 data-tip="br.motors">Each mechanism motor, one at a time</h2>
        ${HowTo.steps({ need: "The robot on blocks, enabled; someone holding the deadman; someone watching the mechanism, clear of hands and hard stops.",
          steps: ["Press <b>Run</b>: the robot's code pauses and the motor runs at 8% for 0.6 s.",
            "Say which way it went. Its encoder always agrees with the code, so only a person can tell if the code's direction is the mechanism's right direction.",
            "A motor that didn't turn: check its PDH port and breaker, then its CAN plug."],
          good: "every motor turned, the way its design says is positive, on its designed PDH port." })}
        <div id="br-motors-body"></div>
        ${HowTo.nextLine("motors")}
      </div>
      <div class="panel" id="br-shafts">
        <h2 data-tip="br.shafts">Motors that share a shaft</h2>
        ${HowTo.steps({ need: "The robot on blocks, enabled; the deadman held; someone watching.",
          steps: ["<b>One alone</b>: runs the first motor while the others on the shaft are held at zero output, so the shaft turns them; each must turn the way its own setting expects.",
            "Only then <b>All together</b>: each at the same low output. If two push against each other the robot stops it at once.",
            "A follower is checked by running its leader."],
          good: "every partner turned with the first, and together they turned freely at low current." })}
        <div id="br-shafts-body"></div>
        ${HowTo.nextLine("shafts")}
      </div>
      <div class="panel" id="br-signoff">
        <h2 data-tip="br.signoff">Sign off</h2>
        ${HowTo.steps({ steps: ["Each lead reads the checklist, then types their name.", "<b>Write the bring-up report</b> saves it, dated, in the robot's <span class=\"mono\">bringup</span> folder. Commit it with the code."] })}
        <div class="row">
          <label class="gain" data-tip="br.signer">Programming lead<input id="br-sign-programming"></label>
          <label class="gain" data-tip="br.signer">Mechanical lead<input id="br-sign-mechanical"></label>
          <label class="gain" data-tip="br.signer">Electrical lead<input id="br-sign-electrical"></label></div>
        <div class="row"><button class="btn primary" id="br-report" data-tip="br.report">Write the bring-up report…</button></div>
        ${HowTo.nextLine("signoff")}
      </div>
    </div></div>`;

  async function load() {
    data = await App.api("/api/bringup");
    paint();
    HowTo.paint("bringup");
  }

  function paint() {
    if (!data) return;
    if (data.ok === false) { $("#br-design-body", root).innerHTML = `<p class="hint">${esc(data.error)}</p>`; return; }
    const d = data.design;
    if (d && d.controller) $("#br-ctl", root).value = d.controller;
    $("#br-design-body", root).innerHTML = data.error ? `<div class="callout bad">${esc(data.error)}</div>` : !d
      ? `<p>No design file yet (<span class="mono">${esc(data.path)}</span>). Draft one from the code, or import the design team's spreadsheet.</p>`
      : `<p class="small"><span class="mono">${esc(data.path)}</span> · ${esc(d.controller || "")} ·
           ${(d.canBuses || []).map(b => `${swatch(b.color)}${b.label ? `<b>${esc(b.label)}</b> ` : ""}${esc(b.name)} (${esc(b.color)}/green)`).join(" · ")}
           <button class="btn small" id="br-buses" data-tip="br.buses">Edit buses…</button> ·
           ${(d.motors || []).length} motors · ${(d.sensors || []).length} sensors</p>${findings(data.check)}`;
    const eb = $("#br-buses", root);
    if (eb) eb.onclick = () => editBuses(d);
    $("#br-code-body", root).innerHTML = d ? findings(data.compare) : `<p class="hint">Needs the design file.</p>`;
    paintHandover(d);
    paintSensors(d);
    paintMotors(d);
    paintShafts(d);
  }

  // ---------------------------------------------------------------- the robot off
  function handoverItems(d) {
    const items = [];
    ((d && d.motors) || []).forEach(m => {
      const p = m.pdh || {};
      if (p.port != null) items.push(`PDH port ${p.port}: ${p.breaker ? p.breaker + " A breaker" : "a breaker (size not in the design)"} for ${m.name}`);
    });
    ((d && d.canBuses) || [{ name: "the CAN bus", color: "yellow" }]).forEach(b =>
      items.push(`${b.label ? `${b.label} (${b.name})` : b.name}: ${b.color}/green cable, every plug latched, a 120 Ω terminator at each end (Wiring's termination check: about 60 Ω with the far one in, 120 with it out)`));
    items.push("Battery strapped down, main breaker bolts tight, the Anderson connector locked");
    items.push("Radio powered and its Ethernet to the robot controller seated");
    items.push("No wire where a mechanism moves; every motor's leads strain-relieved");
    return items;
  }

  function paintHandover(d) {
    const mk = (data.marks || {}).bu_handover;
    $("#br-handover-body", root).innerHTML = `<ul class="checklist">${handoverItems(d).map((t, i) =>
        `<li><label class="row small"><input type="checkbox" data-ho="${i}"> ${esc(t)}</label></li>`).join("")}</ul>
      <div class="row"><button class="btn primary" id="br-ho-ok" data-tip="br.ho-ok" disabled>All checked</button>
        <button class="btn" id="br-ho-bad" data-tip="br.ho-bad">Something to fix…</button>
        ${mk ? `<span class="small muted">Last: ${esc(mk.result)} ${esc(mk.detail || "")}</span>` : ""}</div>`;
    const boxes = $$("[data-ho]", root), ok = $("#br-ho-ok", root);
    boxes.forEach(b => b.onchange = () => { ok.disabled = !boxes.every(x => x.checked); });
    ok.onclick = () => HowTo.mark("bringup", "bu_handover", true, `${boxes.length} items checked with the robot off.`).then(load);
    $("#br-ho-bad", root).onclick = () => note("What needs fixing before power-on?", t => HowTo.mark("bringup", "bu_handover", false, t).then(load));
  }

  function note(question, then) {
    App.modal(`<h2>${esc(question)}</h2><textarea id="br-note" rows="3" style="width:100%" autofocus></textarea>
      <div class="row"><button class="btn primary" id="br-note-ok">Record it</button><button class="btn" id="br-note-x">Cancel</button></div>`, m => {
      $("#br-note-x", m).onclick = () => App.closeModal();
      $("#br-note-ok", m).onclick = () => { const t = $("#br-note", m).value.trim(); App.closeModal(); if (t) then(t); };
    });
  }

  // ---------------------------------------------------------------- sensors
  // The robot's live readout (its "sensors" test): each sensor's value as the robot reads it, ticked
  // the moment it changes. A tick is the person's to take back: one that changed the wrong way.
  let reading = false, live = {}, sensorRep = null;
  const ticked = new Set(), autoTicked = new Set();

  function sensorRows(d) {
    const S = ((d && d.sensors) || []).map(s => Object.assign({}, s));
    const names = new Set(S.map(s => s.name));
    // A sensor the code registers that the design doesn't list is still read: shown, and flagged.
    Object.keys(live).filter(n => !names.has(n)).forEach(n => S.push({ name: n, extra: true }));
    return S;
  }

  function paintSensors(d) {
    const box = $("#br-sensors-body", root), S = sensorRows(d), can = App.connected();
    if (!S.length) { box.innerHTML = `<p class="hint">${d ? "No sensors in the design." : "Needs the design file."}</p>`; return; }
    box.innerHTML = `<div class="tblwrap br-sensors"><table class="t"><thead><tr><th>Sensor</th><th>Port</th><th>Means</th><th>Now</th><th>Reads right</th></tr></thead><tbody>
        ${S.map(s => `<tr data-sname="${esc(s.name)}"><td><b>${esc(s.name)}</b> <span class="small muted">${s.extra ? "in the code, not in the design" : esc(s.subsystem || "")}</span></td>
          <td class="mono">${s.extra ? "" : `${esc(s.type)} ${esc([].concat(s.port).join(", "))}`}</td><td class="small">${esc(s.means || "")}</td>
          <td class="small" data-now></td>
          <td><input type="checkbox" data-sn="${esc(s.name)}" ${ticked.has(s.name) ? "checked" : ""} aria-label="${esc(s.name)} reads right"></td></tr>`).join("")}</tbody></table></div>
      <div class="row">
        <button class="btn primary" id="br-sn-live" data-tip="br.sn-live" ${can && !reading ? "" : "disabled"} ${reading ? "hidden" : ""}>Start the live readout</button>
        <button class="btn primary" id="br-sn-stop" data-tip="br.sn-stop" ${reading ? "" : "hidden"}>Stop</button>
        <button class="btn" id="br-sn-ok" data-tip="br.sn-ok" disabled>Every sensor reads right</button>
        <button class="btn" id="br-sn-bad" data-tip="br.sn-bad">One doesn't…</button>
        ${can ? "" : `<span class="small muted">Connect to the robot to read them.</span>`}</div>
      <div id="br-sn-out">${verdict(sensorRep)}</div>`;
    const boxes = $$("[data-sn]", box), ok = $("#br-sn-ok", box);
    const allTicked = () => { ok.disabled = !boxes.every(x => x.checked); };
    boxes.forEach(b => b.onchange = () => { (b.checked ? ticked.add(b.dataset.sn) : ticked.delete(b.dataset.sn)); allTicked(); });
    allTicked();
    paintLive();
    ok.onclick = () => HowTo.mark("bringup", "bu_sensors", true, `${boxes.length} sensors read right${sensorRep ? ` (${sensorRep.summary})` : ""}.`).then(load);
    $("#br-sn-bad", box).onclick = () => note("Which sensor, and what did it do?", t => HowTo.mark("bringup", "bu_sensors", false, t).then(load));
    $("#br-sn-stop", box).onclick = () => App.api("/api/stop", {});
    $("#br-sn-live", box).onclick = () => readSensors(d);
  }

  // Ten times a second while the readout runs: only the values and ticks change, never the table
  // (rebuilding it would take a person's focus and their tick).
  function paintLive() {
    const box = $("#br-sensors-body", root);
    for (const tr of $$("tr[data-sname]", box)) {
      const n = tr.dataset.sname, v = live[n], cell = $("[data-now]", tr);
      const html = !v ? `<span class="muted">${reading ? "not read" : "–"}</span>`
        : `<span class="mono${reading ? "" : " muted"}">${esc(v.value)}</span>${v.value === "can't read" ? ` <span class="chip warn">can't read</span>` : v.changed ? ` <span class="chip good">changed</span>` : ""}`;
      if (cell._html !== html) { cell._html = html; cell.innerHTML = html; }
      // Ticked once, the first time it changes; after that the person's tick is theirs.
      if (v && v.changed && !autoTicked.has(n)) {
        autoTicked.add(n);
        const cb = $("[data-sn]", tr);
        cb.checked = true;
        cb.dispatchEvent(new Event("change"));
      }
    }
  }

  async function readSensors(d) {
    if (!App.connected()) { App.toast("Connect to the robot first."); return; }
    reading = true;
    live = {};
    sensorRep = null;
    autoTicked.clear();
    paintSensors(d);
    const poll = setInterval(() => {
      const msg = ((App.live || {}).status || {}).message || (App.state.status || {}).message || "";
      const line = App.sensorLine(msg);
      if (!line) return;
      const fresh = Object.keys(line).some(n => !(n in live));
      live = line;
      if (fresh) paintSensors(d); else paintLive();
    }, 100);
    try {
      const doc = await App.runTest("sensors", "ALL", { duration_s: 300 });
      sensorRep = doc.report || null;
      // The robot counted every sample: a beam blocked between two of these polls still counts.
      for (const r of (sensorRep && sensorRep.sensors) || []) {
        live[r.name] = Object.assign({}, live[r.name] || { value: r.problem ? "can't read" : "–" }, { changed: r.changed });
      }
    } catch (e) {
      App.toast(e.message, 6000);
    } finally {
      clearInterval(poll);
      reading = false;
      paintSensors(d);
    }
  }

  // ---------------------------------------------------------------- one motor
  // The motor test picks motors by their place in the robot's list, as bit masks.
  const bit = name => { const i = (data.order || []).indexOf(name); return i < 0 ? null : 2 ** i; };
  const mask = names => names.reduce((a, n) => a + (bit(n) || 0), 0);

  function partnersOf(d, m) {
    const all = (d.motors || []);
    const followers = all.filter(x => x.follows && x.follows.leader === m.name).map(x => x.name);
    const onShaft = m.shaft ? all.filter(x => x.shaft === m.shaft && x.name !== m.name) : [];
    return { watch: [...new Set([...followers, ...onShaft.filter(x => x.follows).map(x => x.name)])],
             zero: onShaft.filter(x => !x.follows).map(x => x.name) };
  }

  async function runTest(key, args) {
    if (!App.connected()) { App.toast("Connect to the robot first."); return null; }
    if (App.env() !== "BLOCKS" && App.env() !== "SIM") { openEnvironment("BLOCKS"); return null; }
    try {
      const doc = await App.runTest("motor_test", "ALL", args);
      last[key] = doc.report || {};
      return doc;
    } catch (e) { App.toast(e.message, 6000); return null; }
  }

  function verdict(rep) {
    if (!rep) return "";
    return `<div class="small"><b>${esc(rep.summary || "")}</b></div>${(rep.findings || []).map(f =>
      `<div class="small ${f.level === "error" ? "bad-ink" : f.level === "warn" ? "warn-ink" : ""}">${esc(f.title)}</div>`).join("")}`;
  }

  function paintMotors(d) {
    const box = $("#br-motors-body", root);
    const M = mechanism(d);
    if (!d || !M.length) { box.innerHTML = `<p class="hint">${d ? "No mechanism motors in the design." : "Needs the design file."}</p>`; return; }
    const marks = data.marks || {}, can = App.connected();
    box.innerHTML = `<div class="tblwrap br-motors"><table class="t"><thead><tr><th>Motor</th><th class="num">CAN</th><th>Shaft</th><th>Positive is</th><th>Result</th><th></th></tr></thead><tbody>
      ${M.map((m, i) => {
        const mk = marks["bu_motor:" + m.name], here = bit(m.name) != null, rep = last["m:" + m.name];
        return `<tr><td><b>${esc(m.name)}</b> <span class="small muted">${esc((m.motor || {}).type || "")}</span></td><td class="num">${esc((m.motor || {}).id ?? "")}</td>
          <td class="small">${esc(m.shaft || "")}</td><td class="small">${esc(m.positive || "not written")}</td>
          <td class="small">${rep ? verdict(rep) : mk ? `<span class="chip ${mk.result === "pass" ? "good" : "bad"}">${mk.result === "pass" ? "right way" : "needs a fix"}</span> ${esc(mk.detail || "")}` : `<span class="muted">not run</span>`}
            ${rep && (rep.ask || []).length ? `<div class="row"><span class="small">${esc(rep.ask[0].question)}</span>
              ${/^Did /.test(rep.ask[0].question) ? `<button class="btn small" data-yes="${i}" data-tip="br.yes">Yes</button><button class="btn small" data-no="${i}" data-tip="br.no">No, the other way</button>` : ""}</div>` : ""}</td>
          <td><button class="btn small" data-run="${i}" data-tip="br.run" ${can && here ? "" : "disabled"}>Run</button>
            ${can && !here ? `<div class="small warn-ink">Not one of the motors the robot watches</div>` : ""}</td></tr>`;
      }).join("")}</tbody></table></div>
      ${can ? "" : `<p class="hint">Connect to the robot, on blocks, to run them.</p>`}`;
    $$("[data-run]", box).forEach(b => b.onclick = async () => {
      const m = M[+b.dataset.run], p = partnersOf(d, m);
      b.disabled = true;
      await runTest("m:" + m.name, { drive: mask([m.name]), watch: mask(p.watch), zero: mask(p.zero) });
      paintMotors(d);
    });
    const answer = (i, ok) => {
      const m = M[i], rep = last["m:" + m.name] || {};
      const bad = (rep.findings || []).find(f => f.level === "error");
      HowTo.mark("bringup", "bu_motor:" + m.name, ok && !bad, bad ? bad.title : ok ? `Turned the right way (${rep.summary || ""}).`
        : "Turned the wrong way: flip its inversion in the code (and the design), then run it again.").then(() => { delete last["m:" + m.name]; load(); });
    };
    $$("[data-yes]", box).forEach(b => b.onclick = () => answer(+b.dataset.yes, true));
    $$("[data-no]", box).forEach(b => b.onclick = () => answer(+b.dataset.no, false));
  }

  // ---------------------------------------------------------------- shared shafts
  function paintShafts(d) {
    const box = $("#br-shafts-body", root);
    const S = shafts(d);
    if (!d || !Object.keys(S).length) { box.innerHTML = `<p class="hint">${d ? "No shared shafts in the design." : "Needs the design file."}</p>`; return; }
    const marks = data.marks || {}, can = App.connected();
    box.innerHTML = Object.entries(S).map(([k, ms]) => {
      const free = ms.filter(m => !m.follows), first = free[0] || ms[0], mk = marks["bu_shaft:" + k];
      const a = last["s1:" + k], b = last["s2:" + k];
      return `<div class="br-shaft"><div class="row" style="justify-content:space-between"><h3>${esc(k)}</h3>
          ${mk ? `<span class="chip ${mk.result === "pass" ? "good" : "bad"}">${mk.result === "pass" ? "turn together" : "needs a fix"}</span>` : ""}</div>
        <p class="small">${ms.map(m => `${esc(m.name)}${m.follows ? ` (follows ${esc(m.follows.leader)}${m.follows.inverted ? ", opposite" : ""})` : ""} ×${esc(m.gearRatio ?? "?")}`).join(" · ")}</p>
        <div class="row"><button class="btn" data-one="${esc(k)}" data-tip="br.one" ${can ? "" : "disabled"}>1. ${esc(first.name)} alone</button>
          ${free.length > 1 ? `<button class="btn" data-all="${esc(k)}" data-tip="br.all" ${can && a && !(a.findings || []).some(f => f.level === "error") ? "" : "disabled"}>2. All together</button>` : ""}</div>
        ${verdict(a)}${verdict(b)}</div>`;
    }).join("");
    const done = (k, ok, detail) => HowTo.mark("bringup", "bu_shaft:" + k, ok, detail).then(load);
    $$("[data-one]", box).forEach(btn => btn.onclick = async () => {
      const k = btn.dataset.one, ms = S[k], free = ms.filter(m => !m.follows), first = free[0] || ms[0];
      const doc = await runTest("s1:" + k, { drive: mask([first.name]), zero: mask(free.slice(1).map(m => m.name)),
                                             watch: mask(ms.filter(m => m.follows).map(m => m.name)) });
      if (!doc) return;
      const bad = ((doc.report || {}).findings || []).find(f => f.level === "error");
      if (bad || free.length < 2) await done(k, !bad, bad ? bad.title : "Every motor on the shaft turned with it, the expected way.");
      else paintShafts(d);
    });
    $$("[data-all]", box).forEach(btn => btn.onclick = async () => {
      const k = btn.dataset.all, free = S[k].filter(m => !m.follows);
      const doc = await runTest("s2:" + k, { drive: mask(free.map(m => m.name)), watch: mask(S[k].filter(m => m.follows).map(m => m.name)) });
      if (!doc) return;
      const bad = ((doc.report || {}).findings || []).find(f => f.level === "error");
      await done(k, !bad && doc.outcome === "DONE", bad ? bad.title : doc.outcome !== "DONE" ? doc.message || "Stopped." : "Together they turned freely at low current.");
    });
  }

  // ---------------------------------------------------------------- the CAN buses
  // Each bus: what people call it (Drive train, Intake), the name the code uses, and its cable color.
  // A bus renamed in the code is renamed on every motor that names it too.
  function editBuses(d) {
    const B = (d.canBuses || []).map(b => Object.assign({ was: b.name }, b));
    const colors = Object.keys(data.colors || {});
    const paintRows = m => {
      $("#bb-rows", m).innerHTML = B.map((b, i) => `<tr>
        <td><span class="bus-swatch" style="--c:${esc((data.colors || {})[b.color] || "#999")}" aria-hidden="true"></span></td>
        <td><input data-bl="${i}" value="${esc(b.label || "")}" placeholder="Drive train" aria-label="What people call bus ${i + 1}"></td>
        <td><input data-bn="${i}" value="${esc(b.name || "")}" style="width:7em" aria-label="Bus ${i + 1} in the code"></td>
        <td><select data-bc="${i}" aria-label="Bus ${i + 1} cable color">${colors.map(c => `<option value="${c}" ${b.color === c ? "selected" : ""}
          ${B.some((x, j) => j !== i && x.color === c) ? "disabled" : ""}>${c === "lightblue" ? "light blue" : c} / green</option>`).join("")}</select></td></tr>`).join("");
      $$("[data-bl]", m).forEach(x => x.onchange = () => { B[+x.dataset.bl].label = x.value.trim(); });
      $$("[data-bn]", m).forEach(x => x.onchange = () => { B[+x.dataset.bn].name = x.value.trim() || B[+x.dataset.bn].name; });
      $$("[data-bc]", m).forEach(x => x.onchange = () => { B[+x.dataset.bc].color = x.value; paintRows(m); });
      $("#bb-add", m).disabled = B.length >= colors.length;
    };
    App.modal(`<h2>CAN buses</h2>
      <p class="small">What people call each bus, the name the code uses for it (YAGSL's <span class="mono">"canbus"</span>), and its cable color: CAN-H is that color, CAN-L green on every bus.</p>
      <table class="t"><thead><tr><th></th><th>Called</th><th>In the code</th><th>Cable</th></tr></thead><tbody id="bb-rows"></tbody></table>
      <div class="row"><button class="btn" id="bb-add" data-tip="br.bus-add">Add a bus</button>
        <button class="btn primary" id="bb-save">Save to the design file…</button><button class="btn" id="bb-x">Cancel</button></div>`, m => {
      paintRows(m);
      $("#bb-add", m).onclick = () => {
        const free = colors.find(c => !B.some(b => b.color === c));
        B.push({ name: "bus" + (B.length + 1), label: "", color: free });
        paintRows(m);
      };
      $("#bb-x", m).onclick = () => App.closeModal();
      $("#bb-save", m).onclick = () => {
        const renamed = Object.fromEntries(B.filter(b => b.was && b.was !== b.name).map(b => [b.was, b.name]));
        const nd = JSON.parse(JSON.stringify(d));
        // Whatever else a bus carried (its terminated ends) stays with it.
        nd.canBuses = B.map(b => {
          const out = Object.assign({}, (d.canBuses || []).find(x => x.name === b.was), { name: b.name, color: b.color });
          if (b.label) out.label = b.label; else delete out.label;
          return out;
        });
        for (const x of [...(nd.motors || []).map(mm => mm.motor || {}), nd.pdh || {}]) {
          if (x.canbus in renamed) x.canbus = renamed[x.canbus];
        }
        App.closeModal();
        save(nd, "The design file's CAN buses");
      };
    });
  }

  // ---------------------------------------------------------------- drafting, importing, saving
  async function save(d, title) {
    if (await App.previewAndSave({ kind: "design", design: d }, title)) load();
  }
  $("#br-draft", root).onclick = async () => {
    const r = await App.api("/api/bringup/draft", { controller: $("#br-ctl", root).value });
    if (!r.ok) { App.toast(r.error); return; }
    await save(r.design, "The design file, drafted from the code");
  };
  $("#br-csv", root).onchange = async e => {
    const f = e.target.files[0];
    if (!f) return;
    const r = await App.api("/api/bringup/draft", { text: await f.text(), controller: $("#br-ctl", root).value });
    e.target.value = "";
    if (!r.ok) { App.toast(r.error); return; }
    const errs = (r.check || []).filter(x => x.level === "error");
    if (errs.length) App.toast(`${errs.length} thing${errs.length === 1 ? "" : "s"} to fix in the spreadsheet; they show once it is saved.`, 6000);
    await save(r.design, `The design file, from ${f.name}`);
  };
  $("#br-report", root).onclick = async () => {
    const signed = Object.fromEntries(["programming", "mechanical", "electrical"].map(k => [k, $("#br-sign-" + k, root).value.trim()]));
    if (await App.previewAndSave({ kind: "bringup_report", signed }, "The bring-up report")) load();
  };

  App.on("tab", t => { if (t === "bringup") load(); });
  App.on("saved", () => { if (root.classList.contains("on")) load(); });
  return { load };
})();
