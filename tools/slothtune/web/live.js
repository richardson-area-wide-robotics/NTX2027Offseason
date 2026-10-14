// Live tab: the robot from above, every module's angle, setpoint and speed, and what looks wrong.
"use strict";

(() => {
  const root = $("#tab-live");
  root.innerHTML = `
    <div class="grid2">
      <div class="panel">
        <h2 data-tip="live.above">From above</h2>
        <p class="hint">Front is up. Black wheel: where it points. Faint wheel: where it was told to point. Arrows: how fast, full length at top speed; green on target, amber behind, red the wrong way. The faint arrow: the speed it was told.</p>
        <div id="live-empty" class="empty">Not connected. Connect to a robot or the simulator to see every module live.
          <div class="row" style="justify-content:center;margin-top:10px"><button class="btn primary" data-connect>Connect</button>
          <button class="btn" data-netcheck data-tip="net.check">Check the networks</button></div></div>
        <svg id="robot" class="robot-svg" viewBox="-200 -200 400 400" role="img" aria-label="Swerve modules seen from above" hidden></svg>
        <div class="row small muted" id="live-pose" data-tip="live.pose"></div>
      </div>
      <div class="stack">
        <div class="panel">
          <h3 data-tip="live.flags">What looks wrong</h3>
          <div id="flags" class="flags"><span class="hint">Not checking: no robot connected.</span></div>
        </div>
        <div class="panel">
          <h3 data-tip="live.mods">Modules</h3>
          <div id="mods" class="mods"></div>
        </div>
        <div class="panel">
          <h3 data-tip="live.startup">At startup the robot applied</h3>
          <ul id="startup" class="small" style="margin:0;padding-left:18px"></ul>
        </div>
      </div>
    </div>`;

  const svg = $("#robot", root);
  $("[data-connect]", root).onclick = () => $("#connect").click();
  $$("[data-netcheck]", root).forEach(b => b.onclick = () => App.checkNetworks());
  let built = false, pods = [];
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };

  // Robot frame (+x forward, +y left) to screen (up, left): screen x = -y, screen y = -x.
  function build(locations, names) {
    svg.innerHTML = "";
    const maxR = Math.max(0.2, ...locations.map(([x, y]) => Math.max(Math.abs(x), Math.abs(y))));
    const k = 120 / maxR;
    el("rect", { x: -150, y: -150, width: 300, height: 300, rx: 10, class: "frame" }, svg);
    el("text", { x: 0, y: -160, "text-anchor": "middle", class: "front" }, svg).textContent = "FRONT";
    const head = el("path", { d: "M 0 -30 L 0 30 M -10 -18 L 0 -30 L 10 -18", class: "head-arrow", "data-tip": "live.heading" }, svg);
    pods = locations.map(([x, y], i) => {
      const g = el("g", { transform: `translate(${-y * k} ${-x * k})` }, svg);
      const ring = el("circle", { r: 34, class: "pod-ring", "data-tip": "live.ring" }, g);
      // The setpoint as a ghost: a faint wheel where it was told to point, and a faint arrow for the
      // speed it was told; the black wheel and the solid arrow are what it really does.
      const ghost = el("rect", { x: -7, y: -22, width: 14, height: 44, rx: 3, class: "ghost-wheel", "data-tip": "live.ghost" }, g);
      const ghostVel = el("path", { d: "", class: "ghost-vel", "data-tip": "live.ghost-speed" }, g);
      const wheel = el("rect", { x: -7, y: -22, width: 14, height: 44, rx: 3, class: "wheel", "data-tip": "live.wheel" }, g);
      // The speed arrow sits on a casing in the panel color, so it reads against the dark wheel.
      const velCase = el("path", { d: "", class: "vel-case" }, g);
      const vel = el("path", { d: "", class: "vel ok", "data-tip": "live.speed" }, g);
      const lbl = el("text", { x: 0, y: (x > 0 ? -44 : 56), "text-anchor": "middle", class: "lbl" }, g);
      lbl.textContent = abbr(names[i]);
      const val = el("text", { x: 0, y: (x > 0 ? 54 : -42), "text-anchor": "middle", class: "val" }, g);
      return { ring, ghost, ghostVel, wheel, velCase, vel, val };
    });
    pods.head = head;
    built = true;
  }

  // Direction (deg, CCW from forward) to a screen-space rotation for an element drawn pointing up.
  const rot = deg => -deg;
  // An arrow up the wheel, as long as the speed is against the top speed (pointing back when negative).
  const ARROW = 70;
  function arrow(len) {
    if (!Number.isFinite(len) || Math.abs(len) < 2) return "";
    const s = Math.sign(len), tip = -len, head = Math.min(9, Math.abs(len) / 2);
    return `M 0 0 L 0 ${tip} M -6 ${tip + s * head} L 0 ${tip} L 6 ${tip + s * head}`;
  }
  // The robot's top module speed: from the robot, else the config check, else a NEO-ish 4.5 m/s.
  function topSpeed() {
    const r = (App.state && App.state.robot) || {}, lint = (App.lint && App.lint.summary) || {};
    return [r.max_module_speed, lint.max_module_speed_mps].find(v => Number.isFinite(v) && v > 0.5) || 4.5;
  }

  function paint(L) {
    const live = L.live, n = (live.steer || []).length;
    if (!built || pods.length !== n) build(L.locations, L.names);
    const flagged = new Set((L.flags || []).map(f => f.module));
    const speedWord = [];
    // Against the top speed, not the fastest wheel now: the arrows grow as the robot speeds up.
    const vmax = Math.max(topSpeed(), ...(live.v_sp || []).map(Math.abs), ...(live.v || []).map(Math.abs));
    for (let i = 0; i < n; i++) {
      const p = pods[i];
      const a = live.steer[i], sp = live.steer_sp[i], v = live.v[i], vsp = live.v_sp[i];
      p.wheel.setAttribute("transform", `rotate(${rot(a)})`);
      p.ghost.setAttribute("transform", `rotate(${rot(isFinite(sp) ? sp : a)})`);
      p.ghost.style.display = isFinite(sp) ? "" : "none";
      const len = Math.min(1, Math.abs(v) / vmax) * ARROW * Math.sign(v || 0);
      for (const line of [p.velCase, p.vel]) {
        line.setAttribute("d", arrow(len));
        line.setAttribute("transform", `rotate(${rot(a)})`);
      }
      const lenSp = isFinite(vsp) ? Math.min(1, Math.abs(vsp) / vmax) * ARROW * Math.sign(vsp || 0) : NaN;
      p.ghostVel.setAttribute("d", arrow(lenSp));
      p.ghostVel.setAttribute("transform", `rotate(${rot(isFinite(sp) ? sp : a)})`);
      let cls = "ok";
      if (isFinite(vsp) && Math.abs(vsp) > 0.1) {
        if (v * vsp < 0) cls = "bad";
        else if (Math.abs(v - vsp) / Math.abs(vsp) > 0.25) cls = "lag";
      }
      p.vel.setAttribute("class", "vel " + cls);
      speedWord[i] = cls === "bad" ? " · <b>WRONG WAY</b>" : cls === "lag" ? " · <b>behind</b>" : "";
      p.ring.setAttribute("class", "pod-ring" + (flagged.has(L.names[i]) ? " flag" : ""));
      p.val.textContent = `${fmt(a, 1)}°  ${fmt(v, 2)} m/s`;
    }
    pods.head.setAttribute("transform", `rotate(${rot(live.heading || 0)})`);
    $("#live-pose", root).textContent = live.pose && live.pose.length
      ? `Odometry x ${fmt(live.pose[0])} m, y ${fmt(live.pose[1])} m · heading ${fmt(live.heading, 1)}°`
        + (live.vision_pose && live.vision_pose.length ? ` · vision x ${fmt(live.vision_pose[0])} y ${fmt(live.vision_pose[1])}` : "")
        + (live.vision_counts && live.vision_counts.length && (live.vision_counts[0] || live.vision_counts[1])
          ? ` · vision ${live.vision_counts[0]} accepted, ${live.vision_counts[1]} rejected`
            + (live.vision_last_reject ? ` (last: ${live.vision_last_reject})` : "") : "")
      : "";

    $("#mods", root).innerHTML = (L.names || []).map((name, i) => {
      const err = isFinite(live.steer_sp[i]) ? ((live.steer_sp[i] - live.steer[i] + 540) % 360) - 180 : NaN;
      const gap = ((live.steer[i] - live.steer_motor[i] + 540) % 360) - 180;
      const fault = live.faults && live.faults[i];
      return `<div class="mod ${flagged.has(name) ? "flag" : ""}"><b>${abbr(name)} <span class="muted small">${esc(name)}</span></b>
        <div class="kv">
          <span class="term" tabindex="0" data-tip="live.angle" data-quiet>Angle</span><span>${fmt(live.steer[i], 1)}° (told ${fmt(live.steer_sp[i], 1)}°, off ${fmt(err, 1)}°)</span>
          <span class="term" tabindex="0" data-tip="live.motorenc" data-quiet>Motor encoder</span><span>${fmt(live.steer_motor[i] % 360, 1)}° (gap ${fmt(gap, 1)}°)</span>
          <span class="term" tabindex="0" data-tip="live.raw" data-quiet>Absolute, raw</span><span>${fmt(live.steer_raw[i], 1)}°</span>
          <span class="term" tabindex="0" data-tip="live.speedrow" data-quiet>Speed</span><span>${fmt(live.v[i], 2)} m/s (told ${fmt(live.v_sp[i], 2)})${speedWord[i] || ""}</span>
          <span class="term" tabindex="0" data-tip="live.current" data-quiet>Current</span><span>drive ${fmt(live.drive_amps[i], 1)} A · steer ${fmt(live.steer_amps[i], 1)} A</span>
          <span class="term" tabindex="0" data-tip="live.temp" data-quiet>Temperature</span><span>drive ${fmt(live.drive_temp[i], 0)} °C · steer ${fmt(live.steer_temp[i], 0)} °C</span>
          ${fault ? `<span class="term" tabindex="0" data-tip="live.faults" data-quiet>Faults</span><span style="color:var(--bad)">${esc(fault)}</span>` : ""}
        </div></div>`;
    }).join("");

    const flags = L.flags || [];
    $("#flags", root).innerHTML = flags.length ? flags.map(f => `<div class="flagrow">
        <span>${Learn.link(f.text, 2)} <span class="mono small">${esc(f.detail || "")}</span></span>
        <button class="btn small" data-sym="${esc(f.symptom)}" data-tip="live.trouble">Troubleshoot</button></div>`).join("")
      : `<span class="hint">Nothing wrong right now. Problems the tool spots while you drive appear here, with a link to the fix.</span>`;
    $$("#flags [data-sym]", root).forEach(b => b.onclick = () => Trouble.open(b.dataset.sym));
  }

  App.on("live", L => {
    if (!L || !L.connected || !L.live || !root.classList.contains("on")) return;
    // An <svg> has no hidden property (only HTML elements do): the attribute itself.
    svg.toggleAttribute("hidden", false);
    $("#live-empty", root).hidden = true;
    paint(L);
  });
  App.on("state", st => {
    const lines = (st.robot && st.robot.startup_report) || [];
    $("#startup", root).innerHTML = lines.length ? lines.map(l => `<li>${esc(l)}</li>`).join("")
      : `<li class="muted">Connect to see what the robot applied from slothtune.json.</li>`;
    if (!st.connected) {
      // Nothing is measured, so nothing may look fine: no drawing, no modules, no "nothing wrong".
      built = false;
      svg.innerHTML = "";
      svg.toggleAttribute("hidden", true);
      $("#live-empty", root).hidden = false;
      $("#mods", root).innerHTML = "";
      $("#live-pose", root).textContent = "";
      $("#flags", root).innerHTML = `<span class="hint">Not checking: no robot connected.</span>`;
    }
  });
})();
