// Preview only: the ribbon's switch between the laptop tool and the Driver Station dashboard, and
// the dashboard itself: Elastic, drawn from the team's real layout file
// (tools/slothtune/elastic/drive-team-layout.json) with the exact text the robot code publishes
// at four moments, recorded from the robot code's own tests.
"use strict";
(() => {
  const I = {
    cancel: "M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z",
    warning: "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z",
    info: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z",
    check: "M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
    high: "M10 3h4v12h-4zM12 17a2 2 0 1 1 0 4 2 2 0 0 1 0-4z",
    drop: "M7 10l5 5 5-5z",
    gear: "M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.48.48 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.48.48 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6A3.6 3.6 0 1 1 12 8.4a3.6 3.6 0 0 1 0 7.2z",
    add: "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
    close: "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
    back: "M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z",
    fwd: "M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z",
    min: "M5 11h14v2H5z",
    max: "M5 5h14v14H5V5zm2 2v10h10V7H7z",
  };
  const svg = (d, cls = "") => `<svg viewBox="0 0 24 24" class="${cls}" aria-hidden="true"><path d="${d}"/></svg>`;
  const LOGO = `<svg viewBox="0 0 30 30" aria-hidden="true"><rect x="1" y="1" width="12" height="12" fill="#3f7fd9"/><rect x="15" y="1" width="14" height="6" fill="#2d63b8"/>
    <rect x="15" y="9" width="14" height="4" fill="#5b9bf0"/><rect x="1" y="15" width="6" height="14" fill="#2d63b8"/><rect x="9" y="15" width="20" height="14" fill="#3f7fd9"/></svg>`;
  const e = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // What each moment in elastic-moments.json is, for the buttons above the window.
  const MOMENTS = {
    booted: { label: "Just turned on", pick: "", text: "A fresh power-on: no battery picked yet. Robot Health asks for its number, and Battery check names the one to put in next." },
    ready: { label: "Ready to queue", pick: "7", text: "Battery 7 picked and read at rest. Robot Health is empty: nothing to fix before queuing." },
    after_match: { label: "Back from a match", pick: "2", text: "Battery 2, a practice-only battery, read once the robot was disabled. A hot shooter, a motor the code creates as the wrong controller, CAN errors, a drive motor that dropped off the bus and a module that wandered." },
    override: { label: "Heat override held", pick: "3", text: "The driver holds the heat override: shut-off motors run at half power for 14 s more. A stalled intake stays off." },
    charge_it: { label: "Battery needs charging", pick: "4", text: "Battery 4 picked and read at rest: 12.21 V, below the line for a match. Nothing else wrong." },
  };
  const about = k => MOMENTS[k] || { label: k, pick: "", text: "" };
  const OPTIONS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "Borrowed"];
  let data = null, moment = "after_match", pick = about(moment).pick;

  function view(which) {
    document.documentElement.classList.toggle("pv-el", which === "elastic");
    document.querySelectorAll("[data-pv]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.pv === which)));
    try { localStorage.setItem("pv.view", which); } catch (err) { /* storage blocked */ }
    if (which === "elastic") paint();
  }

  function widget(c) {
    const p = c.properties || {}, m = data.moments[moment];
    let body = "";
    if (c.type === "ComboBox Chooser" || c.type === "Dropdown Chooser") {
      body = `<div class="el-chooser"><button class="el-dd" id="el-dd" aria-haspopup="listbox" aria-expanded="false" aria-label="Battery: pick its number"><span>${e(pick)}</span>${svg(I.drop)}</button>
        ${svg(I.check, "el-ok")}</div>`;
    } else if (c.type === "Text Display") {
      body = `<input class="el-text" id="el-text" readonly value="${e(m.check)}" aria-label="${e(c.title)}" title="${e(p.topic)}">`;
    } else if (c.type === "Alerts") {
      const kinds = { kError: ["err", I.cancel], kWarning: ["warn", I.warning], kInfo: ["info", I.info] };
      const rows = ["kError", "kWarning", "kInfo"].flatMap(k => m.alerts.filter(a => a.startsWith(k + ": ")).map(a =>
        `<div class="el-alert">${svg(kinds[k][1], kinds[k][0])}<p>${e(a.slice(k.length + 2))}</p></div>`));
      body = `<div class="el-alerts" role="list">${rows.join("")}</div>`;
    }
    return `<div class="el-w" style="left:${c.x}px;top:${c.y}px;width:${c.width}px;height:${c.height}px">
      <div class="el-card"><div class="el-head" title="${e(p.topic || "")}">${e(c.title)}</div><div class="el-body">${body}</div></div></div>`;
  }

  function paint() {
    const host = document.getElementById("pv-elastic");
    if (!data || !host) return;
    const tab = data.layout.tabs[0];
    host.innerHTML = `<div class="pv-moments">
        <div class="pv-seg" role="group" aria-label="Moment">${Object.keys(data.moments).map(k =>
          `<button data-moment="${e(k)}" aria-pressed="${k === moment}">${e(about(k).label)}</button>`).join("")}</div>
        <p>${e(about(moment).text)} Text from the robot code itself, run in its tests. Widgets are drawn at their real size, from the team's layout file.</p>
      </div>
      <div class="el-scroll"><div class="el-win" role="img" aria-label="Elastic on the Driver Station laptop, ${e(about(moment).label)}">
        <div class="el-top"><span class="it logo">${LOGO}</span><span class="it">File</span><span class="it">Edit</span><span class="it">Help</span>
          <span class="sep"></span><span class="it">${svg(I.gear)} Settings</span><span class="sep"></span><span class="it">${svg(I.add)} Add Widget</span>
          <span class="ttl">Elastic</span><span class="win"><span>${svg(I.min)}</span><span>${svg(I.max)}</span><span>${svg(I.close)}</span></span></div>
        <div class="el-tabs"><span class="el-tab on">${e(tab.name)} ${svg(I.close)}</span>
          <span class="nav">${svg(I.back)}${svg(I.add)}${svg(I.fwd)}</span></div>
        <div class="el-grid">${tab.grid_layout.containers.map(widget).join("")}</div>
        <div class="el-status"><span class="ok">Network Tables: Connected (10.17.45.2)</span><span>Team 1745</span><span class="r">Latency: 3.66 ms</span></div>
      </div></div>`;
    host.querySelectorAll("[data-moment]").forEach(b => b.onclick = () => { moment = b.dataset.moment; pick = about(moment).pick; paint(); });
    const dd = host.querySelector("#el-dd");
    if (dd) dd.onclick = ev => { ev.stopPropagation(); menu(dd); };
  }

  // Elastic's chooser list: a search box over the robot's options.
  function menu(dd) {
    const old = document.querySelector(".el-menu");
    if (old) { old.remove(); dd.setAttribute("aria-expanded", "false"); return; }
    const m = document.createElement("div");
    m.className = "el-menu";
    m.setAttribute("role", "listbox");
    m.innerHTML = `<div class="search"><input id="el-search" placeholder="Search" aria-label="Search"></div>${OPTIONS.map(o => `<button role="option" data-o="${e(o)}">${e(o)}</button>`).join("")}`;
    dd.parentElement.appendChild(m);
    dd.setAttribute("aria-expanded", "true");
    const s = m.querySelector("#el-search");
    s.focus();
    s.oninput = () => m.querySelectorAll("[data-o]").forEach(b => { b.hidden = !b.dataset.o.toLowerCase().includes(s.value.toLowerCase()); });
    s.onclick = ev => ev.stopPropagation();
    m.querySelectorAll("[data-o]").forEach(b => b.onclick = () => { pick = b.dataset.o; paint(); });
  }
  document.addEventListener("click", () => { const m = document.querySelector(".el-menu"); if (m) m.remove(); });
  document.addEventListener("keydown", ev => { if (ev.key === "Escape") { const m = document.querySelector(".el-menu"); if (m) m.remove(); } });

  document.querySelectorAll("[data-pv]").forEach(b => b.onclick = () => view(b.dataset.pv));
  fetch("rec/elastic.json").then(r => r.json()).then(d => {
    data = d;
    if (!(moment in d.moments)) { moment = Object.keys(d.moments)[0]; pick = about(moment).pick; }
    paint();
  });
  let start = "tools";
  try { start = localStorage.getItem("pv.view") || "tools"; } catch (err) { /* storage blocked */ }
  view(start);
  // The ribbon's height comes off the tool's work area (preview.css), and the open "About" closes on
  // a click elsewhere or Escape.
  const ribbon = document.querySelector(".pv-ribbon"), about_ = document.querySelector(".pv-about");
  const fit = () => document.documentElement.style.setProperty("--pv-h", Math.ceil(ribbon.getBoundingClientRect().height) + "px");
  fit();
  addEventListener("resize", fit);
  document.addEventListener("click", ev => { if (about_ && about_.open && !about_.contains(ev.target)) about_.open = false; });
  document.addEventListener("keydown", ev => { if (ev.key === "Escape" && about_) about_.open = false; });
})();
