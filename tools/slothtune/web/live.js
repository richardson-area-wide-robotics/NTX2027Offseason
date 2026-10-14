// Live tab: the robot from above, every module's angle, setpoint and speed, and what looks wrong.
"use strict";

(() => {
  const root = $("#tab-live");
  root.innerHTML = `
    <div class="grid2">
      <div class="panel">
        <div class="row live-head"><h2 data-tip="live.above">From above</h2>
          <div class="seg" id="live-view" role="group" aria-label="Show">
            <button data-view="robot" class="on" aria-pressed="true" data-tip="live.view-robot">Robot</button><button data-view="field" aria-pressed="false" data-tip="live.view-field">On the field</button></div></div>
        <p class="hint" id="live-hint-robot">Front is up. Black wheel: where it points. Faint wheel: where it was told to point. Arrows: how fast, full length at top speed; green on target, amber behind, red the wrong way. The faint arrow: the speed it was told.</p>
        <p class="hint" id="live-hint-field" hidden>Blue wall on the left. Solid robot: where it thinks it is. Faint dashed robot: where the cameras alone put it. Green tags: in view now, with a line to each. Faint trail: the last 8 seconds.</p>
        <div id="live-empty" class="empty">Not connected. Connect to a robot or the simulator to see every module live.
          <div class="row" style="justify-content:center;margin-top:10px"><button class="btn primary" data-connect>Connect</button>
          <button class="btn" data-netcheck data-tip="net.check">Check the networks</button></div></div>
        <svg id="robot" class="robot-svg" viewBox="-200 -200 400 400" role="img" aria-label="Swerve modules seen from above" hidden></svg>
        <div id="field-wrap" hidden>
          <div id="field-empty" class="empty" hidden></div>
          <svg id="field" class="field-svg" role="img" aria-label="The robot on the field, seen from above" hidden></svg>
          <div class="small muted" id="field-credit"></div>
        </div>
        <div class="row small muted" id="live-pose" data-tip="live.pose"></div>
      </div>
      <div class="stack">
        <div class="panel">
          <h3 data-tip="live.flags">What looks wrong</h3>
          <div id="flags" class="flags"><span class="hint">Not checking: no robot connected.</span></div>
        </div>
        <div class="panel">
          <h3 data-tip="live.mods" id="mods-h">Modules</h3>
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

  // ---------------------------------------------------------------------------- the module table
  // A column a module, a row a quantity: built when the modules are known, then only its cells'
  // text changes (rebuilt ten times a second, its terms lost focus and clicks).
  const MOD_ROWS = [
    ["angle", `<span class="term" tabindex="0" data-tip="live.angle" data-quiet>Angle</span>`],
    ["motorenc", `<span class="term" tabindex="0" data-tip="live.motorenc" data-quiet>Motor encoder</span>`],
    ["raw", `<span class="term" tabindex="0" data-tip="live.raw" data-quiet>Absolute, raw</span>`],
    ["speed", `<span class="term" tabindex="0" data-tip="live.speedrow" data-quiet>Speed</span>`],
    ["current", `<span class="term" tabindex="0" data-tip="live.current" data-quiet>Current</span>`],
    ["temp", `<span class="term" tabindex="0" data-tip="live.temp" data-quiet>Temperature</span>`],
    ["faults", `<span class="term" tabindex="0" data-tip="live.faults" data-quiet>Faults</span>`],
  ];
  let modsKey = null, cells = {};
  function buildMods(names) {
    $("#mods", root).innerHTML = `<table class="t mods-t" aria-labelledby="mods-h"><thead><tr><td></td>${names.map((n, i) =>
      `<th scope="col" data-col="${i}"><b>${abbr(n)}</b><span class="flag-word"></span> <span class="muted small">${esc(n)}</span></th>`).join("")}</tr></thead>
      <tbody>${MOD_ROWS.map(([k, label]) => `<tr data-row="${k}"${k === "faults" ? " hidden" : ""}><th scope="row">${label}</th>${names.map((_, i) =>
        `<td data-c="${k}-${i}"></td>`).join("")}</tr>`).join("")}</tbody></table>`;
    cells = {};
    $$("#mods [data-c]", root).forEach(td => { cells[td.dataset.c] = td; });
    modsKey = names.join("|");
  }
  function setCell(k, i, html) {
    const td = cells[`${k}-${i}`];
    if (td && td._h !== html) { td._h = html; td.innerHTML = html; }
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
      p.val.textContent = `${fmt(a, 1)}°  ${U.speed(v)}`;
    }
    pods.head.setAttribute("transform", `rotate(${rot(live.heading || 0)})`);
    $("#live-pose", root).textContent = live.pose && live.pose.length
      ? `Odometry x ${U.length(live.pose[0])}, y ${U.length(live.pose[1])} · heading ${fmt(live.heading, 1)}°`
        + (live.vision_pose && live.vision_pose.length ? ` · vision x ${U.length(live.vision_pose[0])}, y ${U.length(live.vision_pose[1])}` : "")
        + (view === "field" && L.seen_tags && !fieldMissing() ? ` · ${L.seen_tags.length} tag${L.seen_tags.length === 1 ? "" : "s"} in view` : "")
        + (live.vision_counts && live.vision_counts.length && (live.vision_counts[0] || live.vision_counts[1])
          ? ` · vision ${live.vision_counts[0]} accepted, ${live.vision_counts[1]} rejected`
            + (live.vision_last_reject ? ` (last: ${live.vision_last_reject})` : "") : "")
      : "";

    const names = L.names || [];
    if (modsKey !== names.join("|")) buildMods(names);
    let anyFault = false;
    names.forEach((name, i) => {
      const err = isFinite(live.steer_sp[i]) ? ((live.steer_sp[i] - live.steer[i] + 540) % 360) - 180 : NaN;
      const gap = ((live.steer[i] - live.steer_motor[i] + 540) % 360) - 180;
      const fault = live.faults && live.faults[i];
      anyFault = anyFault || !!fault;
      setCell("angle", i, `${fmt(live.steer[i], 1)}°<small>told ${fmt(live.steer_sp[i], 1)}°, off ${fmt(err, 1)}°</small>`);
      setCell("motorenc", i, `${fmt(live.steer_motor[i] % 360, 1)}°<small>gap ${fmt(gap, 1)}°</small>`);
      setCell("raw", i, `${fmt(live.steer_raw[i], 1)}°`);
      setCell("speed", i, `${U.speed(live.v[i])}<small>told ${U.speed(live.v_sp[i])}${speedWord[i] || ""}</small>`);
      setCell("current", i, `drive ${fmt(live.drive_amps[i], 1)} A<small>steer ${fmt(live.steer_amps[i], 1)} A</small>`);
      setCell("temp", i, `drive ${fmt(live.drive_temp[i], 0)} °C<small>steer ${fmt(live.steer_temp[i], 0)} °C</small>`);
      setCell("faults", i, fault ? `<span class="bad-ink">${esc(fault)}</span>` : "");
      const on = flagged.has(name), th = $(`#mods th[data-col="${i}"]`, root);
      if (th && th.classList.contains("flag") !== on) {
        th.classList.toggle("flag", on);
        $(".flag-word", th).textContent = on ? " · flagged" : "";
        $$(`#mods td[data-c$="-${i}"]`, root).forEach(td => td.classList.toggle("flag", on));
      }
    });
    const fr = $('#mods tr[data-row="faults"]', root);
    if (fr) fr.hidden = !anyFault;

    // Rebuilt only when the problems themselves change: rebuilding the rows every repaint lost a
    // click on Troubleshoot and threw keyboard focus off it.
    const flags = L.flags || [];
    const fkey = JSON.stringify(flags.map(f => [f.symptom, f.text, f.module]));
    const fbox = $("#flags", root);
    if (fbox._key !== fkey) {
      fbox._key = fkey;
      fbox.innerHTML = flags.length ? flags.map((f, k) => `<div class="flagrow">
          <span>${Learn.link(f.text, 2)} <span class="mono small" data-flag-detail="${k}"></span></span>
          <button class="btn small" data-sym="${esc(f.symptom)}" data-tip="live.trouble">Troubleshoot</button></div>`).join("")
        : `<span class="hint">Nothing wrong right now. Problems the tool spots while you drive appear here, with a link to the fix.</span>`;
      $$("#flags [data-sym]", root).forEach(b => b.onclick = () => Trouble.open(b.dataset.sym));
    }
    flags.forEach((f, k) => { const d = $(`[data-flag-detail="${k}"]`, fbox); if (d && d.textContent !== (f.detail || "")) d.textContent = f.detail || ""; });
  }

  // ---------------------------------------------------------------------------- on the field
  // The robot on this field, once there is a camera to place it and the field's tags are surveyed
  // (Calibrate, 9. New field): without both, a pose on the field is a guess.
  const fieldSvg = $("#field", root), fieldEmpty = $("#field-empty", root);
  const TRAIL_MS = 8000;
  let view = "robot", field = null, fieldProject = null, fb = null, trail = [];
  try { if (localStorage.getItem("slothtune.live.view") === "field") view = "field"; } catch (e) { /* no storage */ }

  async function loadField() {
    fieldProject = (App.state || {}).project || null;
    try { field = await App.api("/api/field"); } catch (e) { field = { ok: false, error: String(e.message || e) }; }
    fb = null;
  }

  // Why there is no field view, or null when there is one.
  function fieldMissing() {
    const env = (App.state && App.state.environment) || {};
    const camera = !!(env.vision_available || env.vision_in_use);
    if (!field) return { text: "Reading this field's tags..." };
    if (!field.ok) return { text: field.error || "Can't read the field." };
    const why = [];
    if (!camera) why.push("the robot reports no camera");
    if (!field.surveyed) why.push("this field's tags aren't surveyed yet");
    return why.length ? { text: `No field view: ${why.join(", and ")}.`, camera, surveyed: field.surveyed, error: field.error } : null;
  }

  function paintMissing(m) {
    fieldEmpty.innerHTML = `${esc(m.text)}${m.error ? `<div class="small muted">${esc(m.error)}</div>` : ""}
      ${m.camera === false ? `<div class="small">The robot says it has a camera once its code sets one up and it is deployed; Calibrate, step 6 checks the camera.</div>` : ""}
      ${m.surveyed === false ? `<div class="small">Put the robot on this field and run New field: it sweeps, works out where every tag really is, and saves the layout.</div>
        <div class="row" style="justify-content:center;margin-top:10px"><button class="btn primary" data-newfield data-tip="live.field-survey">Survey this field</button></div>` : ""}`;
    const b = $("[data-newfield]", fieldEmpty);
    if (b) b.onclick = () => { App.show("calibrate"); const p = $("#cal-newfield"); if (p) p.scrollIntoView({ block: "start" }); };
  }

  // PathPlanner's field pictures (github.com/mjansen4857/pathplanner, images/, MIT; img/fields/),
  // at half PathPlanner's size, placed the way its field_image.dart and path_painter_util.dart
  // place a point: pixel x = (x + margin) * ppm, pixel y = height - (y + margin) * ppm.
  const FIELD_PICS = [
    { name: "2026 REBUILT", src: "img/fields/field26.png", w: 1754, h: 907, ppm: 100, margin: 0.5 },
  ];
  // The picture whose field is this layout's size; none (a plain drawing) for a field PathPlanner
  // has no picture of yet.
  const fieldPic = (len, wid) => FIELD_PICS.find(p => Math.abs(p.w / p.ppm - 2 * p.margin - len) < 0.1
    && Math.abs(p.h / p.ppm - 2 * p.margin - wid) < 0.1) || null;

  function buildField(locations) {
    const len = field.length, wid = field.width, pic = fieldPic(len, wid);
    const k = pic ? pic.ppm : 100, m = pic ? pic.margin : 0.3;
    const w = pic ? pic.w : (len + 2 * m) * k, h = pic ? pic.h : (wid + 2 * m) * k;
    // Field (+x toward the red wall, +y left from the blue wall) to picture: x right, y up.
    const sx = x => (x + m) * k, sy = y => h - (y + m) * k;
    fieldSvg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    fieldSvg.innerHTML = "";
    el("rect", { x: sx(0), y: sy(wid), width: len * k, height: wid * k, class: "fld" }, fieldSvg);
    if (pic) {
      el("image", { href: pic.src, x: 0, y: 0, width: w, height: h, preserveAspectRatio: "none" }, fieldSvg);
    } else {
      el("rect", { x: sx(0) - 0.12 * k, y: sy(wid), width: 0.1 * k, height: wid * k, class: "wall blue" }, fieldSvg);
      el("rect", { x: sx(len) + 0.02 * k, y: sy(wid), width: 0.1 * k, height: wid * k, class: "wall red" }, fieldSvg);
      el("line", { x1: sx(len / 2), y1: sy(0), x2: sx(len / 2), y2: sy(wid), class: "mid" }, fieldSvg);
    }
    $("#field-credit", root).textContent = pic ? `Field: ${pic.name}, picture from PathPlanner (MIT license).`
      : `Field: ${U.length(len, 0)} by ${U.length(wid, 0)}, drawn plain (no PathPlanner picture of this field yet).`;
    const tags = {};
    for (const t of field.tags) {
      const g = el("g", { transform: `translate(${sx(t.x)} ${sy(t.y)}) rotate(${-t.yaw_deg})`, class: "tag" }, fieldSvg);
      el("title", {}, g).textContent = `Tag ${t.id}: x ${U.length(t.x)}, y ${U.length(t.y)}, ${U.length(t.z)} up, facing ${fmt(t.yaw_deg, 0)}°`;
      el("rect", { x: -0.04 * k, y: -0.11 * k, width: 0.08 * k, height: 0.22 * k, class: "tag-face" }, g);   // the tag, edge on
      el("line", { x1: 0.04 * k, y1: 0, x2: 0.3 * k, y2: 0, class: "tag-dir" }, g);                         // the way it faces
      tags[t.id] = { g, x: sx(t.x), y: sy(t.y) };
    }
    const trailEl = el("polyline", { points: "", class: "trail" }, fieldSvg);
    const rays = el("g", { class: "rays" }, fieldSvg);
    // The bumpers as PathPlanner draws them (its settings.json), else the modules plus about
    // 5.5 in of frame and bumper each way. Robot frame: x forward (picture right at heading 0), y left (up).
    const R = field.robot;
    const hx = (R ? R.length / 2 : Math.max(0.2, ...locations.map(l => Math.abs(l[0]))) + 0.14) * k;
    const hy = (R ? R.width / 2 : Math.max(0.2, ...locations.map(l => Math.abs(l[1]))) + 0.14) * k;
    const ox = R ? R.offset[0] * k : 0, oy = R ? -R.offset[1] * k : 0;
    const shape = (cls, attrs) => {
      const g = el("g", { class: cls, ...attrs }, fieldSvg);
      el("rect", { x: ox - hx, y: oy - hy, width: 2 * hx, height: 2 * hy, rx: 0.04 * k, class: "body" }, g);
      el("path", { d: `M ${hx * 0.15} ${-hy * 0.55} L ${hx * 0.8} 0 L ${hx * 0.15} ${hy * 0.55}`, class: "nose" }, g);
      return g;
    };
    const ghost = shape("bot ghost", { "data-tip": "live.field-vision" }), bot = shape("bot", { "data-tip": "live.field-robot" });
    fb = { tags, trailEl, rays, ghost, bot, sx, sy, k, key: JSON.stringify(locations) };
  }

  function paintField(L) {
    const miss = fieldMissing();
    fieldEmpty.hidden = !miss;
    fieldSvg.toggleAttribute("hidden", !!miss);
    if (miss) { paintMissing(miss); trail = []; return; }
    if (!fb || fb.key !== JSON.stringify(L.locations)) buildField(L.locations);
    const live = L.live, pose = live.pose || [], vp = live.vision_pose || [];
    const place = (g, p) => {
      const ok = p.length >= 3 && p.slice(0, 3).every(Number.isFinite);
      g.style.display = ok ? "" : "none";
      if (ok) g.setAttribute("transform", `translate(${fb.sx(p[0])} ${fb.sy(p[1])}) rotate(${-p[2]})`);
      return ok;
    };
    const here = place(fb.bot, pose);
    place(fb.ghost, vp);
    const now = performance.now();
    if (here) trail.push([now, fb.sx(pose[0]), fb.sy(pose[1])]);
    trail = trail.filter(p => now - p[0] < TRAIL_MS);
    fb.trailEl.setAttribute("points", trail.map(p => `${p[1].toFixed(1)},${p[2].toFixed(1)}`).join(" "));
    const seen = new Set(L.seen_tags || []);
    fb.rays.innerHTML = "";
    for (const [id, t] of Object.entries(fb.tags)) {
      const on = seen.has(Number(id));
      t.g.classList.toggle("seen", on);
      if (!on) continue;
      if (here) el("line", { x1: fb.sx(pose[0]), y1: fb.sy(pose[1]), x2: t.x, y2: t.y, class: "ray" }, fb.rays);
      el("text", { x: t.x, y: t.y - 0.3 * fb.k, "text-anchor": "middle", class: "tag-id" }, fb.rays).textContent = id;
    }
  }

  function setView(v) {
    view = v;
    try { localStorage.setItem("slothtune.live.view", v); } catch (e) { /* no storage */ }
    $$("#live-view [data-view]", root).forEach(b => {
      b.classList.toggle("on", b.dataset.view === v);
      b.setAttribute("aria-pressed", String(b.dataset.view === v));
    });
    $("#live-hint-robot", root).hidden = v !== "robot";
    $("#live-hint-field", root).hidden = v !== "field";
    const on = !!((App.state || {}).connected);
    svg.toggleAttribute("hidden", !on || v !== "robot");
    $("#field-wrap", root).hidden = !on || v !== "field";
    // Read the layout afresh each time the view opens: New field may have just saved one.
    if (v === "field" && on) loadField().then(() => App.live && App.live.live && paintField(App.live));
  }
  $$("#live-view [data-view]", root).forEach(b => b.onclick = () => setView(b.dataset.view));
  setView(view);

  App.on("saved", body => { if (body && body.kind === "layout") loadField(); });

  App.on("live", L => {
    if (!L || !L.connected || !L.live || !root.classList.contains("on")) return;
    // An <svg> has no hidden property (only HTML elements do): the attribute itself.
    svg.toggleAttribute("hidden", view !== "robot");
    $("#field-wrap", root).hidden = view !== "field";
    $("#live-empty", root).hidden = true;
    paint(L);
    if (view === "field") {
      if (!field || !field.ok || fieldProject !== (App.state || {}).project) loadField();
      paintField(L);
    }
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
      $("#field-wrap", root).hidden = true;
      trail = [];
      $("#live-empty", root).hidden = false;
      $("#mods", root).innerHTML = "";
      modsKey = null;
      $("#flags", root)._key = null;
      $("#live-pose", root).textContent = "";
      $("#flags", root).innerHTML = `<span class="hint">Not checking: no robot connected.</span>`;
    }
  });
})();
