// Auto-tune (Tune drive train, Each pod): every pod's own steering or drive gains, tuned round by
// round while a person holds the deadman (autotune.py). Before it starts, a walkthrough says what to
// check and what will happen; while it runs, a panel says what it is doing now and what each pod has
// done; at the end it offers to save. It never starts a round by itself without the deadman: every
// round is an ordinary test, which waits for it.
"use strict";

const AutoTuneUI = (() => {
  const NAME = { steer: "steering", drive: "drive speed" };
  const PODS = { frontleft: "Front left", frontright: "Front right", backleft: "Back left", backright: "Back right" };
  let panel = null, timer = null, last = null;

  const podName = m => PODS[m] || m;

  /** The walkthrough, then Start. ``o``: {loop, target, surface, gains} from the Tune tab. */
  function open(o) {
    const robot = o.target !== "practice";
    const env = App.env(), live = App.live && App.live.live;
    const volts = live && Number.isFinite(live.bus) ? live.bus : null;
    const where = env === "FIELD" ? "on the floor" : env === "BLOCKS" ? "on blocks" : env === "SIM" ? "in the simulator" : null;
    // On the robot it needs a connection and a place said: every test refuses without them.
    const blocker = !robot ? "" : !App.connected() ? "Connect to the robot first."
      : !where ? "Say where the robot is first: on blocks or on the floor." : "";
    const floorOnly = o.loop === "drive" && env === "BLOCKS";
    const checks = !robot ? [] : [
      ["place", env === "BLOCKS"
        ? "<b>All four wheels off the ground</b>, free to spin, nothing touching them or the steering."
        : "<b>Bumpers on</b>, the floor clear for 2 m all round, and everyone back from the robot."],
      ["holder", "<b>One person holds the deadman the whole time</b> (the tester's joystick right bumper, Driver Station port 1, or <b>Hold to run</b> on this page) and watches the robot, ready to let go."],
      ["enabled", "The robot is <b>enabled</b> in the Driver Station (Teleop or Test), as for any test."],
      ["battery", `A charged battery: 12.5 V or more at rest${volts != null ? ` (it reads ${fmt(volts, 1)} V now)` : ""}. A sagging battery makes every round look worse.`],
    ];
    App.modal(`<h2>Auto-tune every pod's ${NAME[o.loop]}</h2>
      ${robot ? `<p class="small">${where ? `The robot is <b>${esc(where)}</b>.` : "Where the robot is: <b>not said yet</b>."}
        <button class="btn small" id="at-where" data-tip="header.env">${where ? "Change where it is" : "Say where it is"}</button></p>` : `<p class="small">On the four practice pods: nothing moves, so this shows how the tuner works.</p>`}
      ${blocker ? `<div class="callout warn">${esc(blocker)}</div>` : ""}
      ${floorOnly ? `<div class="callout warn">On blocks the drive tune can tune the speed loop but can't measure the feedforward: the wheels carry no weight. It stops at that step and says so. Tune drive speed on the floor for the whole job.</div>` : ""}
      ${robot ? `<h3>Before you start: tick each one</h3>
      <ul class="checklist">${checks.map(([k, t]) => `<li><label class="row"><input type="checkbox" data-at-check="${k}"> <span>${t}</span></label></li>`).join("")}</ul>` : ""}
      <h3>What happens</h3>
      <ol class="small">
        <li>It runs the ${o.loop === "steer" ? "steering steps" : "drive speed steps"} on <b>all four pods at once</b>${robot ? ", as soon as the deadman is held" : ""}, then reads each pod's result <b>on its own</b> and changes <b>only that pod's</b> gains.${o.loop === "drive" ? " On the floor it first measures each pod's feedforward: a slow ramp, then steps." : ""}</li>
        <li>Again, round after round: up to 8. Each change at most doubles or halves a gain.</li>
        <li>A pod that meets every target stops changing; the others carry on. When every pod asks for the same change to a setting they share (a ramp rate), it is made once, for all of them. A pod whose advice needs a person (a limit, a configuration fix) stops and says why.</li>
        ${robot ? `<li><b>Let go of the deadman at any time</b>: the round stops and the tuner waits. Hold it again and press <b>Continue</b> to run that round again.</li>
        <li><b>ABORT</b> (or Esc) stops it for good.</li>` : ""}
        <li>At the end every pod goes back to the best gains it ran. <b>Nothing is written to a file</b> until you press Save.</li>
      </ol>
      <div class="row" style="justify-content:flex-end">
        <button class="btn" id="at-cancel" data-tip="autotune.cancel">Cancel</button>
        <button class="btn primary" id="at-start" data-tip="autotune.start" ${robot ? "disabled" : ""}>Start</button></div>`, root => {
      const boxes = $$("[data-at-check]", root);
      const ready = () => { $("#at-start", root).disabled = !!blocker || !boxes.every(b => b.checked); };
      boxes.forEach(b => b.onchange = ready);
      const w = $("#at-where", root);
      if (w) w.onclick = () => { App.closeModal(); openEnvironment(); };
      $("#at-cancel", root).onclick = () => App.closeModal();
      $("#at-start", root).onclick = async () => {
        App.closeModal();
        const r = await App.api("/api/autotune/start", { loop: o.loop, target: o.target, surface: o.surface, gains: o.gains });
        if (!r.ok) { App.toast(r.error || "The auto-tuner didn't start.", 6000); return; }
        show(r);
        poll();
      };
    });
  }

  function attach(el) {
    panel = el;
    App.api("/api/autotune").then(r => { if (r && r.state && r.state !== "none") { show(r); if (["running", "paused"].includes(r.state)) poll(); } });
  }

  function poll() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const r = await App.api("/api/autotune");
      if (r && r.state) show(r);
      if (r && ["running", "paused"].includes(r.state)) poll();
    }, 500);
  }

  const CHIP = { running: "warn", paused: "warn", finished: "good", stopped: "" };
  const POD_CHIP = { tuning: "warn", done: "good", stopped: "" };
  const WORD = { running: "running", paused: "paused", finished: "finished", stopped: "stopped" };

  // Why each pod finished, each reason once with the pods it applies to.
  function reasons(pods) {
    const by = new Map();
    pods.filter(p => p.reason).forEach(p => by.set(p.reason, [...(by.get(p.reason) || []), podName(p.pod)]));
    return by.size ? `<ul class="small at-why">${[...by].map(([why, who]) =>
      `<li><b>${esc(who.length === pods.length && pods.length > 1 ? "Every pod" : who.join(", "))}:</b> ${esc(why)}</li>`).join("")}</ul>` : "";
  }

  function show(r) {
    last = r;
    if (!panel) return;
    if (!r || r.state === "none") { panel.hidden = true; return; }
    panel.hidden = false;
    const active = ["running", "paused"].includes(r.state);
    const scores = p => p.rounds.map(x => x.score == null ? "ff" : x.score).join(" → ") || "–";
    const html = `<div class="row" style="justify-content:space-between">
        <h3 data-tip="autotune.panel">Auto-tune: ${esc(NAME[r.loop] || r.loop)}${r.target === "practice" ? " (practice pods)" : ""}</h3>
        <span class="chip ${CHIP[r.state] || ""}">${esc(WORD[r.state] || r.state)} · round ${Math.min(r.round + (active ? 1 : 0), r.max_rounds)} of ${r.max_rounds}</span></div>
      <p class="small ${r.state === "paused" ? "warn-ink" : ""}">${esc(r.message || "")}</p>
      <table class="t small at-pods"><thead><tr><th>Pod</th><th data-tip="autotune.scores">Score each round</th><th>Now</th></tr></thead><tbody>
        ${r.pods.map(p => `<tr><td>${esc(podName(p.pod))}</td><td class="mono">${esc(scores(p))}</td>
          <td><span class="chip ${POD_CHIP[p.status] || ""}">${p.status === "tuning" ? "tuning" : p.status === "done" ? "done" : "stopped"}</span></td></tr>`).join("")}</tbody></table>
      ${reasons(r.pods)}
      ${(r.notes || []).length ? `<div class="callout info small">${r.notes.map(esc).join("<br>")}</div>` : ""}
      <div class="row">
        ${r.state === "paused" ? `<button class="btn primary" id="at-continue" data-tip="autotune.continue">Continue</button>` : ""}
        ${active ? `<button class="btn" id="at-stop" data-tip="autotune.stop">Stop</button>` : ""}
        ${!active && r.target !== "practice" && Object.keys(r.best_gains || {}).length ? `<button class="btn primary" id="at-save" data-tip="autotune.save">Save these gains…</button>` : ""}
        ${!active ? `<button class="btn" id="at-close" data-tip="autotune.close">Close</button>` : ""}</div>`;
    if (panel._h !== html) {
      panel._h = html;
      panel.innerHTML = html;
      const b = id => $(id, panel);
      if (b("#at-continue")) b("#at-continue").onclick = () => App.api("/api/autotune/continue", {}).then(poll);
      if (b("#at-stop")) b("#at-stop").onclick = () => App.api("/api/autotune/stop", {}).then(poll);
      if (b("#at-close")) b("#at-close").onclick = () => { panel.hidden = true; panel._h = ""; };
      if (b("#at-save")) b("#at-save").onclick = save;
    }
  }

  // The robot now runs each pod's best gains: save those, this loop's own for every pod.
  async function save() {
    if (!last) return;
    const L = last.loop === "steer" ? "Steer" : "Drive";
    // Each pod's own, and the settings they share that the tuner may have changed for all of them.
    const keys = [...App.modules().flatMap(m => [`Pod/${m}/${L}/`, ...(last.loop === "drive" ? [`FF/${m}/`] : [])]),
      `${L}/RampS`, ...(last.loop === "drive" ? ["Drive/Vel"] : [])];
    await App.previewAndSave({ kind: "gains", keys }, `Save the auto-tuned ${NAME[last.loop]} gains`);
  }

  return { open, attach, state: () => last };
})();
