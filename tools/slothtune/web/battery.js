// Which battery is in: the header's Battery chip, and the picker the drive team taps after a swap.
// The robot asks again after every boot (a swap means the robot was off); the Driver Station
// dashboard's "Battery" drop-down does the same job when this laptop isn't there.
"use strict";

const Battery = (() => {
  let cache = null, loadedAt = 0, askedBoot = null;
  const WORDS = { good: "good", practice: "practice", retire: "retire" };

  async function load() {
    cache = await App.api("/api/battery");
    loadedAt = Date.now();
    return cache;
  }

  function row(id) {
    return ((cache && cache.batteries) || []).find(b => b.id === id) || {};
  }

  function spark(trend, r) {
    if (!trend || trend.length < 2) return "";
    const lo = Math.min(10, ...trend), hi = Math.max(r.practice_max_mohm + 4, ...trend);
    const pts = trend.map((v, i) => `${(i / (trend.length - 1) * 70).toFixed(1)},${(20 - (v - lo) / (hi - lo) * 18).toFixed(1)}`);
    const y = v => (20 - (v - lo) / (hi - lo) * 18).toFixed(1);
    return `<svg class="batt-spark" viewBox="0 0 70 22" aria-hidden="true">
      <line x1="0" x2="70" y1="${y(r.good_max_mohm)}" y2="${y(r.good_max_mohm)}" class="lim"/>
      <polyline points="${pts.join(" ")}"/></svg>`;
  }

  function when(stamp) {
    const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(stamp || "");
    return m ? `${+m[2]}/${+m[3]} ${m[4]}:${m[5]}` : "";
  }

  async function open() {
    const r = await load();
    // Only the team's list (and "Borrowed"); a battery taken off the list keeps its history below.
    const shown = r.batteries.filter(b => b.listed);
    App.modal(`<h2>Which battery is in?</h2>
      <p>Tap the number on the battery; <b>Borrowed</b> for one without a team number.${r.connected ? "" : " <b>Connect to the robot to pick.</b>"}</p>
      ${r.robot_path ? `<div class="callout warn"><b>${esc(r.robot_path.title)}.</b> ${esc(r.robot_path.why)}</div>` : ""}
      ${r.next ? `<p class="batt-next" data-tip="battery.next"><b>Next to use: Battery ${esc(r.next.id)}</b>, ${esc(r.next.why)}</p>` : ""}
      <div class="batt-grid" ${shown.some(b => b.id === r.id) ? "" : "data-nofocus"}>${shown.map(b => `<button class="batt ${b.status || ""} ${b.id === r.id ? "on" : ""}" data-id="${esc(b.id)}" ${b.id === r.id ? "autofocus" : ""}
          ${r.connected ? "" : "disabled"} aria-label="Battery ${esc(b.id)}${b.status ? ", " + WORDS[b.status] : ""}">
          <span class="batt-n${b.id.length > 3 ? " long" : ""}">${esc(b.id)}</span>
          <span class="batt-s">${b.status ? `${WORDS[b.status]} · ${b.mohm} mΩ` : "not measured"}</span>${b.id === r.id ? `<span class="batt-in">in now</span>` : ""}${r.next && b.id === r.next.id ? `<span class="batt-in">next</span>` : ""}</button>`).join("")}</div>
      ${r.id && r.rest_v > 1 ? `<p class="small">Battery ${esc(r.id)} read ${fmt(r.rest_v, 2)} V at rest when it was picked
        (${r.rest_v >= 12.3 ? charge(r.rest_v) : `<b>${charge(r.rest_v)}</b>`}).</p>` : ""}
      <div class="row learn-row" style="flex-wrap:wrap"><span class="small muted" data-tip="battery.plug">Its plug and leads:</span>${Learn.chips(["crimp_sb50", "wire_gauge", "wire_loss"])}</div>
      <details class="batt-details"><summary>How each battery is doing</summary>
        <div class="tblwrap"><table class="t"><thead><tr><th>Battery</th><th></th><th data-tip="battery.sag" data-quiet>Sag</th><th data-tip="battery.rest" data-quiet>At rest</th><th data-tip="battery.measured" data-quiet>Measured</th><th data-tip="battery.trend" data-quiet>Trend</th><th>From</th></tr></thead><tbody>
        ${r.batteries.filter(b => b.n).map(b => `<tr><td><b>${esc(b.id)}</b>${b.listed ? "" : ` <span class="muted small">off the list</span>`}</td>
          <td>${b.status ? `<span class="chip ${b.status === "good" ? "good" : b.status === "practice" ? "warn" : "bad"}">${WORDS[b.status]}</span>` : ""}</td>
          <td class="num">${b.mohm != null ? b.mohm + " mΩ" : "–"}</td><td class="num">${b.v_rest != null ? fmt(b.v_rest, 2) + " V" : "–"}</td>
          <td class="small">${b.n ? `${b.n}×, last ${esc(when(b.when))}` : ""}</td><td>${spark(b.trend, r)}</td>
          <td class="small muted">${esc(b.source || "")}</td></tr>`).join("")}
        </tbody></table></div>
        <p class="hint"><span class="term" data-learn="battery">Sag</span> is how far the voltage drops per amp, battery and connections together, in milliohms: lower is better.
        Good up to ${r.good_max_mohm}, practice up to ${r.practice_max_mohm}, retire above. A new ${esc(r.datasheet.name)} alone is about
        ${r.datasheet.r_ohm * 1000} mΩ (its datasheet). Every wheel test and every match log you open measures the battery that was picked.</p>
      </details>
      ${r.robot_grades_stale ? `<p class="small">The robot's Battery check line on the dashboard shows these grades and the
        battery to use next, from the last grades sent. These are newer.</p>` : ""}
      <div class="row">${r.robot_grades_stale ? `<button class="btn primary" id="batt-send" data-tip="battery.send">Send the grades to the robot…</button>` : ""}<button class="btn" id="batt-edit" data-tip="battery.edit">Edit the battery list…</button><button class="btn" id="batt-close">Close</button></div>`,
    root => {
      $$("[data-id]", root).forEach(b => b.onclick = () => pick(b.dataset.id));
      $("#batt-close", root).onclick = () => App.closeModal();
      $("#batt-edit", root).onclick = () => edit(shown.filter(b => b.listed).map(b => b.id));
      const send = $("#batt-send", root);
      if (send) send.onclick = async () => {
        if (await App.previewAndSave({ kind: "edit", file: "slothtune.json", path: ["batteryGrades"], value: r.robot_grades },
          "Battery grades for the robot")) App.toast("Saved. Redeploy, and the dashboard shows them.", 6000);
      };
    });
  }

  // The charge check on a resting voltage: the same words the robot puts on the dashboard.
  const charge = v => !(v > 1) ? "" : v >= 12.7 ? "charged" : v >= 12.3 ? "partly charged" : "CHARGE IT before a match";

  async function pick(id) {
    const r = await App.api("/api/battery/pick", { id });
    if (!r.ok) { App.toast(r.error); return; }
    App.closeModal();
    const b = row(id);
    // The robot reads the battery the moment it is picked; give it a moment, then say what it read.
    await new Promise(res => setTimeout(res, 600));
    const now = await load();
    const read = now.id === id && now.rest_v > 1 ? `: ${fmt(now.rest_v, 2)} V at rest, ${charge(now.rest_v)}` : "";
    App.toast(`Battery ${id} is in${read}${b.status ? `. Sag last time: ${WORDS[b.status]}, ${b.mohm} mΩ` : ""}.`, 6000);
    if (b.status === "retire") setTimeout(() => App.toast(`Battery ${id} sagged hard last time: use another for matches.`, 6000), 6200);
  }

  function edit(ids) {
    App.modal(`<h2>The team's batteries</h2>
      <p>The numbers written on your batteries, separated by commas. They become the choices here and in
      the dashboard's Battery drop-down after the next deploy. Retire one by leaving it out; its history is kept.</p>
      <label class="gain" data-tip="battery.list">Battery numbers<input id="batt-list" value="${esc(ids.join(", "))}"></label>
      <div class="row"><button class="btn primary" id="batt-save">Save…</button><button class="btn" id="batt-cancel">Cancel</button></div>`,
    root => {
      $("#batt-cancel", root).onclick = () => App.closeModal();
      $("#batt-save", root).onclick = async () => {
        const list = [...new Set($("#batt-list", root).value.split(",").map(s => s.trim()).filter(Boolean))];
        if (!list.length) { App.toast("List at least one battery."); return; }
        await App.previewAndSave({ kind: "edits", edits: [{ file: "slothtune.json", path: ["batteries"], value: list }] },
          "Battery list");
      };
    });
  }

  // Called by the header on every live poll.
  function paintChip(live, robot) {
    const chip = $("#battery-chip");
    if (!chip) return;
    if (!live) { setChip(chip, "Battery –"); delete chip.dataset.tipNow; return; }
    const id = live.battery_id || "";
    if ((!cache || Date.now() - loadedAt > 30000) && !paintChip.loading) {
      paintChip.loading = true;
      load().finally(() => { paintChip.loading = false; });
    }
    if (!id) {
      setChip(chip, "Battery ?", "warn");
      chip.dataset.tipNow = "Nobody has said which battery is in. Tap to pick its number.";
      // Once per robot boot, ask straight away - unless something else is on screen or running.
      const boot = robot && robot.boot_id;
      if (boot && askedBoot !== boot && $("#modal").hidden && !(App.state.test || {}).running) {
        askedBoot = boot;
        open();
      }
      return;
    }
    const b = row(id);
    setChip(chip, "Battery " + id, b.status === "retire" ? "bad" : b.status === "practice" ? "warn" : b.status === "good" ? "good" : "");
    chip.dataset.tipNow = b.status ? `Battery ${id}: ${WORDS[b.status]}, ${b.mohm} mΩ when last measured.` : `Battery ${id} has not been measured yet.`;
  }

  $("#battery-chip").onclick = () => open();
  return { open, paintChip, load };
})();
