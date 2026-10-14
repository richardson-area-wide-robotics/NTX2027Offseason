// Preview only: stands in for the tool's own server (server.py). Every answer here was recorded
// from the real server, connected to Peashooter's robot code running in the simulator. Anything that
// would move the robot or write a file says so instead.
"use strict";
(() => {
  const REC = fetch("rec/rec.json").then(r => r.json());
  const realFetch = window.fetch.bind(window);
  const NOPE = "This is a preview recorded from the simulator, so nothing here reaches a robot or saves a file. In the real tool this button works.";
  // Actions that would drive the robot, change its settings or write a file.
  const REFUSE = ["/api/test", "/api/gains", "/api/save/apply", "/api/offsets", "/api/env", "/api/abort", "/api/stop",
    "/api/motors/override", "/api/survey/start", "/api/controllers/save", "/api/sim", "/api/export", "/api/netcheck",
    "/api/camcal/sample", "/api/camcal/solve", "/api/survey/solve", "/api/geometry/tape",
    "/api/geometry/wheels", "/api/handcheck", "/api/controllers/step", "/api/controllers/robot", "/api/save/preview",
    "/api/analyze", "/api/predict", "/api/designs/read", "/api/mark", "/api/systems/gains", "/api/netcheck/save"];
  let connected = true, li = 0;
  const started = new Set();  // part checklists started in this preview: "module:frontleft"

  const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "Content-Type": "application/json" } });

  window.fetch = async (input, opt = {}) => {
    const url = typeof input === "string" ? input : input.url;
    if (!url.startsWith("/api/")) return realFetch(input, opt);
    const rec = await REC;
    const path = url.split("?")[0];
    const method = (opt.method || "GET").toUpperCase();
    // A moment's delay, as over the robot's network.
    await new Promise(r => setTimeout(r, path === "/api/live" ? 0 : 60));
    if (method === "GET") {
      if (path === "/api/live") {
        if (!connected) return json({ connected: false });
        const s = rec.live[li++ % rec.live.length];
        return json(s);
      }
      if (path === "/api/state") {
        const s = Object.assign({}, rec.state[0]);
        if (!connected) Object.assign(s, { connected: false, target: null });
        return json(s);
      }
      if (path.startsWith("/api/runs/")) {
        const r = await realFetch("rec/runs/" + encodeURIComponent(decodeURIComponent(path.slice(10))));
        return r.ok ? r : json({ ok: false, error: "That run wasn't recorded for this preview." });
      }
      if (path === "/api/parts/plan") {
        const q = new URLSearchParams(url.split("?")[1] || ""), key = q.get("kind") + ":" + (q.get("which") || "");
        const mine = key in (rec.started || {}) ? key : Object.keys(rec.started || {}).find(k => k.split(":")[0] === q.get("kind"));
        if (started.has(key) && mine) return json(Object.assign({}, rec.started[mine], q.get("which") && mine !== key ? { title: rec.started[mine].title.replace(/:.*/, ": " + q.get("which")) } : {}));
        // Another choice of the same part than the ones recorded: that part's answer, never another part's.
        if (!(url in rec.get)) {
          const same = Object.keys(rec.get).find(k => k.split("?")[0] === path && new URLSearchParams(k.split("?")[1] || "").get("kind") === q.get("kind"));
          if (same) return json(rec.get[same]);
        }
      }
      if (url in rec.get) return json(rec.get[url]);
      // Another module, motor or camera than the one recorded: the recorded one's answer.
      const near = Object.keys(rec.get).find(k => k.split("?")[0] === path);
      if (near) return json(rec.get[near]);
      return json({ ok: false, error: "Not recorded for this preview." });
    }
    let body = {};
    try { body = JSON.parse(opt.body || "{}"); } catch (e) { /* not JSON */ }
    if (path === "/api/connect") { connected = true; return json({ ok: true }); }
    if (path === "/api/disconnect") { connected = false; return json({ ok: true }); }
    if (path === "/api/deadman") return json({ ok: true });
    if (path === "/api/parts/start") { started.add(body.kind + ":" + (body.which || "")); return json({ ok: true }); }
    if (path === "/api/parts/stop") { started.delete(body.kind + ":" + (body.which || "")); return json({ ok: true }); }
    if (path === "/api/parts/mark") return json({ ok: false, error: NOPE });
    if (REFUSE.includes(path)) return json({ ok: false, error: NOPE });
    // The termination check answers the example readings recorded for each bus; other numbers say which.
    if (path === "/api/wiring/termination") {
      const norm = v => String(v == null ? "" : v).trim().toUpperCase();
      const hit = rec.post.find(p => p.path === path && p.body.bus === body.bus && norm(p.body.ohms) === norm(body.ohms) && norm(p.body.without) === norm(body.without));
      if (hit) return json(hit.resp);
      const ex = [...new Set(rec.post.filter(p => p.path === path).map(p => `${p.body.ohms}${p.body.without ? " then " + p.body.without : " alone"}`))];
      return json({ level: "info", title: "Not recorded for this preview", why: "The preview answers these readings: " + ex.join("; ") + "." });
    }
    // A mechanism's physics: only the example's, worked out when it was recorded.
    if (path === "/api/systems/physics") {
      const hit = rec.post.find(p => p.path === path && JSON.stringify(p.body) === JSON.stringify(body));
      return json(hit ? hit.resp : { ok: false, error: "This preview has only the example's physics worked out. In the real tool this works out what you enter." });
    }
    const same = rec.post.filter(p => p.path === url);
    const exact = same.find(p => JSON.stringify(p.body) === JSON.stringify(body));
    if (exact || same.length) return json((exact || same[same.length - 1]).resp);
    return json({ ok: false, error: NOPE });
  };
})();
