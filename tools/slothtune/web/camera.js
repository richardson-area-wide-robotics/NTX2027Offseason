// The camera from this laptop (Calibrate, 6. Camera lens): connect to its PhotonVision, see its
// version against the robot code's PhotonLib, and calibrate the lens with the tool leading the
// person who holds the board, pose by pose, in letters big enough to read from a few meters away.
// PhotonVision does the solving, as its own page does (photon.py talks to it the same way).
"use strict";

const CameraUI = (() => {
  let info = null, host = "", box = null;

  // Where to hold the board, one pose at a time: every part of the picture, near and far, tilted
  // every way (PhotonVision: up to 45 degrees, never square-on, the whole board in the picture).
  const AREA = { tl: "top left", t: "top", tr: "top right", l: "left", c: "middle", r: "right", bl: "bottom left", b: "bottom", br: "bottom right" };
  const POSES = [
    ["c", "near", "turned to the left"], ["c", "near", "turned to the right"], ["c", "mid", "tipped back (top away from the camera)"],
    ["tl", "mid", "turned to the right"], ["t", "mid", "tipped forward (bottom away)"], ["tr", "mid", "turned to the left"],
    ["l", "mid", "turned to the right"], ["r", "mid", "turned to the left"], ["bl", "mid", "tipped back"],
    ["b", "mid", "tipped back"], ["br", "mid", "tipped forward"], ["c", "far", "turned to the left"],
    ["tl", "far", "tipped forward"], ["tr", "far", "tipped back"], ["bl", "far", "turned to the right"],
    ["br", "far", "turned to the left"], ["c", "near", "tipped forward"], ["t", "near", "turned to the right"],
    ["b", "near", "turned to the left"], ["c", "mid", "turned and tipped (one corner away)"],
  ];
  const DIST = { near: "close: the board fills about half the picture", mid: "about a meter away", far: "about two meters away" };
  const GRID = ["tl", "t", "tr", "l", "c", "r", "bl", "b", "br"];

  const defaultHost = () => (App.cameraHost || "");

  /** The connect box in step 6. */
  function mount(el) {
    box = el;
    paint();
  }

  function paint(msg) {
    if (!box) return;
    const cams = (info && info.cameras) || [];
    const cam = cams[0];
    const lib = info && info.photonlib;
    box.innerHTML = `<div class="row" style="flex-wrap:wrap;gap:8px">
        <label class="small" data-tip="cam.host">Camera address <input id="cm-host" value="${esc(host || defaultHost())}" placeholder="10.17.45.11" style="width:9em"></label>
        <button class="btn" id="cm-connect" data-tip="cam.connect">${info ? "Connected: again" : "Connect to the camera"}</button></div>
      ${msg ? `<p class="small bad-ink">${esc(msg)}</p>` : ""}
      ${info ? `<p class="small">PhotonVision <b>${esc(info.version)}</b> on a ${esc(info.hardware || "camera")}${cams.length ? ` · ${cams.map(c => esc(c.nickname || c.unique)).join(", ")}` : " · no camera found"}.
          ${info.match ? `<span class="level ok">ok</span> the same as the robot code's PhotonLib.`
            : lib ? `<span class="level error">error</span> The robot code has PhotonLib ${esc(lib)}: they must match, or the robot gets no camera data. Check the networks, Software versions, says how.` : ""}</p>
        ${cam ? `<div class="row" style="flex-wrap:wrap;gap:8px">
          ${cams.length > 1 ? `<label class="small" data-tip="cal.cam">Camera <select id="cm-cam">${cams.map(c => `<option value="${esc(c.unique)}">${esc(c.nickname || c.unique)}</option>`).join("")}</select></label>` : ""}
          <label class="small" data-tip="cam.mode">Resolution <select id="cm-mode">${cam.modes.map(m => `<option value="${m.index}" ${m.width === 1280 ? "selected" : ""}>${m.width} × ${m.height}</option>`).join("")}</select></label>
          <label class="small" data-tip="cam.square">Square <input id="cm-square" value="1.00" inputmode="decimal" style="width:4em"> in</label>
          <label class="small" data-tip="cam.marker">Marker <input id="cm-marker" value="0.75" inputmode="decimal" style="width:4em"> in</label>
          <button class="btn primary" id="cm-guided" data-tip="cam.guided">Calibrate, the tool leading…</button></div>
          ${cam.calibrations.length ? `<p class="small muted">Calibrated now: ${cam.calibrations.map(c => `${c.width} × ${c.height}${c.mean_error_px != null ? `, ${c.mean_error_px} px` : ""}${c.hfov_deg ? `, ${c.hfov_deg}° × ${c.vfov_deg}°` : ""}`).join("; ")}.</p>` : `<p class="small muted">No lens calibration on it yet.</p>`}` : ""}` : ""}`;
    $("#cm-connect", box).onclick = connect;
    const g = $("#cm-guided", box);
    if (g) g.onclick = () => guided(currentCam(), +$("#cm-mode", box).value, parseFloat($("#cm-square", box).value) || 1.0,
      parseFloat($("#cm-marker", box).value) || 0.75);
  }

  function currentCam() {
    const sel = box && $("#cm-cam", box);
    const cams = (info && info.cameras) || [];
    return cams.find(c => !sel || c.unique === sel.value) || cams[0];
  }

  async function connect() {
    host = $("#cm-host", box).value.trim();
    const r = await App.api("/api/camera/connect", { host });
    if (!r.ok) { info = null; paint(r.error); return; }
    info = r;
    App.cameraHost = host;
    try { localStorage.setItem("slothtune.camera.host", host); } catch (e) { /* not kept */ }
    paint();
    App.emit("camera", info);
  }

  // ---------------------------------------------------------------- the guided calibration
  function guided(cam, mode, square, marker) {
    const m = cam.modes.find(x => x.index === mode) || cam.modes[0];
    const name = cam.nickname || cam.unique;
    let i = 0, paused = false, timer = null, count = 0, phase = "checks", note = "";
    const CHECKS = [
      `The board is printed at <b>100%</b> (no scaling) and taped <b>flat</b> to something stiff: not held floppy.`,
      `A square measures <b>${square.toFixed(2)} in</b> and a marker <b>${marker.toFixed(2)} in</b>, checked with calipers (if not, cancel and type what they really are).`,
      `The lens is <b>focused</b> and won't be touched again: refocusing makes this calibration wrong.`,
      `<b>Even light</b> on the board: no glare and no shadow across it.`,
      `The robot is <b>disabled</b> and stays put: the board moves, not the camera.`,
    ];
    const stop = () => { clearTimeout(timer); timer = null; };
    const close = () => { stop(); App.closeModal(); };

    function shell(body) {
      App.modal(`<div class="cal-guide">
          <div class="cg-view"><img src="${esc(cam.stream)}" alt="What the camera sees" onerror="this.replaceWith(Object.assign(document.createElement('p'),{className:'hint',textContent:'No live picture from the camera here. The snapshots still work: PhotonVision checks each one for the whole board.'}))">
            <p class="small muted">${esc(name)} at ${m.width} × ${m.height}</p></div>
          <div class="cg-say">${body}</div></div>`, root => wire(root));
    }

    function grid(area) {
      return `<div class="cg-grid" aria-hidden="true">${GRID.map(a => `<span class="${a === area ? "on" : ""}"></span>`).join("")}</div>`;
    }

    function render() {
      if (phase === "checks") {
        shell(`<h2>Calibrate ${esc(name)}'s lens</h2>
          <p>One person holds the board in front of the camera; the tool says where, then counts down and takes a snapshot. About 20 poses, 7 seconds each.</p>
          <ul class="checklist">${CHECKS.map((t, k) => `<li><label class="row"><input type="checkbox" data-cg-check="${k}"> <span>${t}</span></label></li>`).join("")}</ul>
          <div class="row"><button class="btn" id="cg-cancel" data-tip="cam.cancel">Cancel</button>
            <button class="btn primary" id="cg-go" data-tip="cam.go" disabled>Start</button></div>`);
      } else if (phase === "poses") {
        const [area, dist, tilt] = POSES[i % POSES.length];
        shell(`<p class="cg-count">Pose ${i + 1} of ${POSES.length} · <b>${count}</b> snapshot${count === 1 ? "" : "s"} (12 needed, 20 better)</p>
          ${grid(area)}
          <p class="cg-big">The <b>${AREA[area]}</b> of the picture, ${DIST[dist]}, <b>${tilt}</b>.</p>
          <p class="cg-big cg-now" id="cg-now">${esc(note)}</p>
          <div class="row" style="flex-wrap:wrap">
            <button class="btn" id="cg-pause" data-tip="cam.pause">${paused ? "Go on" : "Pause"}</button>
            <button class="btn" id="cg-skip" data-tip="cam.skip">Skip this pose</button>
            <button class="btn primary" id="cg-finish" data-tip="cam.finish" ${count >= 12 ? "" : "disabled"}>Work it out</button>
            <button class="btn" id="cg-cancel" data-tip="cam.cancel">Cancel</button></div>`);
      } else if (phase === "solving") {
        shell(`<h2>Working it out</h2><p class="cg-big">PhotonVision is solving the lens from ${count} snapshots: up to a minute.</p>`);
      }
    }

    function wire(root) {
      const boxes = $$("[data-cg-check]", root);
      boxes.forEach(b => b.onchange = () => { $("#cg-go", root).disabled = !boxes.every(x => x.checked); });
      const on = (id, fn) => { const b = $(id, root); if (b) b.onclick = fn; };
      on("#cg-cancel", async () => { close(); if (phase !== "checks") await App.api("/api/camera/cal/cancel", { host, camera: cam.unique }); });
      on("#cg-go", async () => {
        const r = await App.api("/api/camera/cal/start", { host, camera: cam.unique, mode, square_in: square, marker_in: marker });
        if (!r.ok) { App.toast(r.error || "It didn't start.", 6000); return; }
        phase = "poses"; i = 0; count = 0; note = "Get the board into place…";
        render();
        cycle(4);
      });
      on("#cg-pause", () => { paused = !paused; if (paused) { stop(); note = "Paused."; render(); } else { note = "Get the board into place…"; render(); cycle(3); } });
      on("#cg-skip", () => { stop(); i++; note = "Get the board into place…"; render(); if (!paused) cycle(4); });
      on("#cg-finish", finish);
    }

    // Time to move the board, a countdown, the snapshot, and on to the next pose (or the same one again).
    function cycle(moveS) {
      stop();
      let left = moveS + 3;
      const tick = async () => {
        if (paused || phase !== "poses") return;
        const now = $("#cg-now");
        if (left > 3) { if (now) now.textContent = "Move it there…"; }
        else if (left > 0) { if (now) now.textContent = `Hold it still… ${left}`; }
        else {
          if (now) now.textContent = "Snap!";
          const r = await App.api("/api/camera/cal/snap", { host, camera: cam.unique });
          if (phase !== "poses") return;
          if (r.ok && r.counted) {
            count = r.count; i++;
            note = `Got it.${i >= POSES.length && count >= 12 ? " That's every pose: Work it out." : ""}`;
            render();
            if (i < POSES.length) cycle(4);
          } else {
            note = r.ok ? "It didn't see the whole board: keep all of it in the picture, hold it steadier, and again…"
              : (r.error || "No answer from the camera.");
            render();
            cycle(2);
          }
          return;
        }
        left--;
        timer = setTimeout(tick, 1000);
      };
      tick();
    }

    async function finish() {
      stop();
      phase = "solving";
      render();
      const r = await App.api("/api/camera/cal/finish", { host, camera: cam.unique, width: m.width, height: m.height });
      const c = r.calibration;
      const err = c && c.mean_error_px;
      const fovOk = c && c.hfov_deg != null && Math.abs(c.hfov_deg - 80) <= 10 && Math.abs(c.vfov_deg - 56) <= 10;
      const good = r.ok && err != null && err <= 1.0;
      if (r.ok && err != null) {
        await HowTo.mark("calibrate", "cal_lens_" + name, good,
          `${m.width}x${m.height}, mean error ${err} px${c.hfov_deg ? `, ${c.hfov_deg}° × ${c.vfov_deg}°` : ""}${good ? "" : ": over 1 px, take the snapshots again"}`);
      }
      shell(`<h2>${r.ok ? (good ? "Calibrated" : "Calibrated, but not well enough") : "It didn't work"}</h2>
        ${r.ok && c ? `<table class="t cg-res"><tbody>
            <tr><td>Mean error</td><td><b>${err} px</b> ${good ? `<span class="level ok">ok</span> under 1 px` : `<span class="level warn">warn</span> over 1 px`}</td></tr>
            ${c.hfov_deg != null ? `<tr><td>Field of view</td><td><b>${c.hfov_deg}° × ${c.vfov_deg}°</b> ${fovOk ? `<span class="level ok">ok</span> the Luma P1's is 80° × 56°` : `<span class="level warn">warn</span> far from the Luma P1's 80° × 56°: check the board's sizes`}</td></tr>` : ""}
            <tr><td>Snapshots</td><td>${c.snapshots}</td></tr></tbody></table>
          <p>${good ? "Recorded for the checklist. Recalibrate if the lens is refocused or the resolution changes." : "Take a fresh set: hold the board flatter and stiller, cover the corners, and tilt it more."}</p>`
          : `<p class="cg-big">${esc(r.error || "No answer from the camera.")}</p>`}
        <div class="row"><button class="btn primary" id="cg-done" data-tip="cam.done">Done</button></div>`);
      const d = $("#cg-done");
      if (d) d.onclick = async () => { close(); await connect(); };
    }

    render();
  }

  try { App.cameraHost = App.cameraHost || localStorage.getItem("slothtune.camera.host") || ""; } catch (e) { /* not kept */ }
  return { mount, connect, info: () => info, host: () => host || App.cameraHost || "", currentCam };
})();
