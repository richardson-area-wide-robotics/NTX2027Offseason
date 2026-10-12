// Live tab: the robot from above, every pod's angle, setpoint and speed, and what looks wrong.
"use strict";

(() => {
  const root = $("#tab-live");
  root.innerHTML = `
    <div class="grid2">
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2>From above</h2>
          <span class="hint">Front of the robot is up. Gray dashes: where each pod is told to point. Bar: wheel speed.</span>
        </div>
        <svg id="robot" class="robot-svg" viewBox="-200 -200 400 400" role="img" aria-label="Swerve modules seen from above"></svg>
        <div class="row small muted" id="live-pose"></div>
      </div>
      <div class="stack">
        <div class="panel">
          <h3>What looks wrong</h3>
          <div id="flags" class="flags"><span class="hint">Nothing. Problems the tool spots while you drive appear here, with a link to the fix.</span></div>
        </div>
        <div class="panel">
          <h3>Modules</h3>
          <div id="mods" class="mods"></div>
        </div>
        <div class="panel">
          <h3>At startup the robot applied</h3>
          <ul id="startup" class="small" style="margin:0;padding-left:18px"></ul>
        </div>
      </div>
    </div>`;

  const svg = $("#robot", root);
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
    const head = el("path", { d: "M 0 -30 L 0 30 M -10 -18 L 0 -30 L 10 -18", class: "head-arrow" }, svg);
    pods = locations.map(([x, y], i) => {
      const g = el("g", { transform: `translate(${-y * k} ${-x * k})` }, svg);
      const ring = el("circle", { r: 34, class: "pod-ring" }, g);
      const ghost = el("line", { x1: 0, y1: 26, x2: 0, y2: -26, class: "ghost" }, g);
      const wheel = el("rect", { x: -7, y: -22, width: 14, height: 44, rx: 3, class: "wheel" }, g);
      const vel = el("line", { x1: 0, y1: 0, x2: 0, y2: 0, class: "vel ok" }, g);
      const lbl = el("text", { x: 0, y: (x > 0 ? -44 : 56), "text-anchor": "middle", class: "lbl" }, g);
      lbl.textContent = abbr(names[i]);
      const val = el("text", { x: 0, y: (x > 0 ? 54 : -42), "text-anchor": "middle", class: "val" }, g);
      return { ring, ghost, wheel, vel, val };
    });
    pods.head = head;
    built = true;
  }

  // Direction (deg, CCW from forward) to a screen-space rotation for an element drawn pointing up.
  const rot = deg => -deg;

  function paint(L) {
    const live = L.live, n = (live.steer || []).length;
    if (!built || pods.length !== n) build(L.locations, L.names);
    const flagged = new Set((L.flags || []).map(f => f.module));
    const vmax = Math.max(1, ...(live.v_sp || []).map(Math.abs), ...(live.v || []).map(Math.abs));
    for (let i = 0; i < n; i++) {
      const p = pods[i];
      const a = live.steer[i], sp = live.steer_sp[i], v = live.v[i], vsp = live.v_sp[i];
      p.wheel.setAttribute("transform", `rotate(${rot(a)})`);
      p.ghost.setAttribute("transform", `rotate(${rot(isFinite(sp) ? sp : a)})`);
      p.ghost.style.display = isFinite(sp) ? "" : "none";
      const len = Math.min(1, Math.abs(v) / vmax) * 60 * Math.sign(v || 0);
      p.vel.setAttribute("y2", String(-len));
      p.vel.setAttribute("transform", `rotate(${rot(a)})`);
      let cls = "ok";
      if (isFinite(vsp) && Math.abs(vsp) > 0.1) {
        if (v * vsp < 0) cls = "bad";
        else if (Math.abs(v - vsp) / Math.abs(vsp) > 0.25) cls = "lag";
      }
      p.vel.setAttribute("class", "vel " + cls);
      p.ring.setAttribute("class", "pod-ring" + (flagged.has(L.names[i]) ? " flag" : ""));
      p.val.textContent = `${fmt(a, 1)}°  ${fmt(v, 2)} m/s`;
    }
    pods.head.setAttribute("transform", `rotate(${rot(live.heading || 0)})`);
    $("#live-pose", root).textContent = live.pose && live.pose.length
      ? `Odometry x ${fmt(live.pose[0])} m, y ${fmt(live.pose[1])} m · heading ${fmt(live.heading, 1)}°`
        + (live.vision_pose && live.vision_pose.length ? ` · vision x ${fmt(live.vision_pose[0])} y ${fmt(live.vision_pose[1])}` : "")
      : "";

    $("#mods", root).innerHTML = (L.names || []).map((name, i) => {
      const err = isFinite(live.steer_sp[i]) ? ((live.steer_sp[i] - live.steer[i] + 540) % 360) - 180 : NaN;
      const gap = ((live.steer[i] - live.steer_motor[i] + 540) % 360) - 180;
      const fault = live.faults && live.faults[i];
      return `<div class="mod ${flagged.has(name) ? "flag" : ""}"><b>${abbr(name)} <span class="muted small">${esc(name)}</span></b>
        <div class="kv">
          <span><span class="term" data-learn="setpoint">Angle</span></span><span>${fmt(live.steer[i], 1)}° (told ${fmt(live.steer_sp[i], 1)}°, off ${fmt(err, 1)}°)</span>
          <span><span class="term" data-learn="motor_encoder">Motor encoder</span></span><span>${fmt(live.steer_motor[i] % 360, 1)}° (gap ${fmt(gap, 1)}°)</span>
          <span><span class="term" data-learn="absolute_encoder">Raw absolute</span></span><span>${fmt(live.steer_raw[i], 1)}°</span>
          <span>Speed</span><span>${fmt(live.v[i], 2)} m/s (told ${fmt(live.v_sp[i], 2)})</span>
          <span><span class="term" data-learn="current_limit">Current</span></span><span>drive ${fmt(live.drive_amps[i], 1)} A · steer ${fmt(live.steer_amps[i], 1)} A</span>
          <span><span class="term" data-learn="heat_estimate">Temperature</span></span><span>drive ${fmt(live.drive_temp[i], 0)} °C · steer ${fmt(live.steer_temp[i], 0)} °C</span>
          ${fault ? `<span>Faults</span><span style="color:var(--bad)">${esc(fault)}</span>` : ""}
        </div></div>`;
    }).join("");

    const flags = L.flags || [];
    $("#flags", root).innerHTML = flags.length ? flags.map(f => `<div class="flagrow">
        <span>${Learn.link(f.text, 2)} <span class="mono small">${esc(f.detail || "")}</span></span>
        <button class="btn small" data-sym="${esc(f.symptom)}">Troubleshoot</button></div>`).join("")
      : `<span class="hint">Nothing. Problems the tool spots while you drive appear here, with a link to the fix.</span>`;
    $$("#flags [data-sym]", root).forEach(b => b.onclick = () => Trouble.open(b.dataset.sym));
  }

  App.on("live", L => {
    if (!L || !L.connected || !L.live || !root.classList.contains("on")) return;
    paint(L);
  });
  App.on("state", st => {
    const lines = (st.robot && st.robot.startup_report) || [];
    $("#startup", root).innerHTML = lines.length ? lines.map(l => `<li>${esc(l)}</li>`).join("")
      : `<li class="muted">Connect to see what the robot applied from swervetune.json.</li>`;
    if (!st.connected) {
      built = false;
      svg.innerHTML = `<text x="0" y="0" text-anchor="middle" class="front">Connect to a robot or the simulator</text>`;
    }
  });
})();
