// Map 2D: top-down layers on a canvas, north (high y) at the top like view_map and survey_map.py.
const DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
const dec = (c) => DIGITS.indexOf(c);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const LAYERS = [
  ["height", "Height", true], ["water", "Water depth", true], ["badwater", "Badwater", true],
  ["moist", "Moisture", false], ["roads", "Roads", true], ["only", "Single road links", true],
  ["range", "District range", false], ["buildings", "Buildings", true], ["planting", "Planting marks", false],
  ["cutting", "Cutting area", false], ["reach", "Work range", false], ["sources", "Water sources", true],
  ["findings", "Findings", true],
];
const opts = { layers: Object.fromEntries(LAYERS.map(([k, , on]) => [k, on])), scale: 6, reach: "FarmHouse" };
let cache = null;

export async function renderMap(el, api) {
  const fresh = await api("/api/map");
  const first = !el.querySelector("#map2d");
  cache = fresh;
  if (first) {
    el.innerHTML = `<div class="toolbar">${LAYERS.map(([k, label]) => `<label><input type="checkbox" data-layer="${k}" ${opts.layers[k] ? "checked" : ""}> ${label}</label>`).join("")}
      <label>work range of <select id="reachsel">${Object.keys(fresh.reach).sort().map((k) => `<option ${k === opts.reach ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>
      <label>zoom <input id="zoom" type="range" min="3" max="12" value="${opts.scale}"></label></div>
      <div class="mapwrap"><canvas id="map2d"></canvas><div id="tileinfo" class="card"><h3>Tile</h3><span class="muted">hover a tile; click for details</span></div></div>`;
    el.querySelectorAll("input[data-layer]").forEach((i) => (i.onchange = () => { opts.layers[i.dataset.layer] = i.checked; draw(el); }));
    el.querySelector("#reachsel").onchange = (e) => { opts.reach = e.target.value; draw(el); };
    el.querySelector("#zoom").oninput = (e) => { opts.scale = +e.target.value; draw(el); };
    const cv = el.querySelector("#map2d");
    cv.onmousemove = (e) => hover(el, cv, e);
    cv.onclick = async (e) => {
      const { x, y } = tileAt(cv, e);
      const t = await api(`/api/tile?x=${x}&y=${y}`).catch((err) => ({ error: err.message }));
      el.querySelector("#tileinfo").innerHTML = `<h3>Tile ${x},${y}</h3><pre>${esc(JSON.stringify(t, null, 1))}</pre>`;
    };
  }
  draw(el);
}

function tileAt(cv, e) {
  const r = cv.getBoundingClientRect(), H = cache.size.height;
  const x = Math.floor((e.clientX - r.left) / opts.scale), row = Math.floor((e.clientY - r.top) / opts.scale);
  return { x, y: H - 1 - row };
}

function hover(el, cv, e) {
  const { x, y } = tileAt(cv, e);
  const g = cache.grids, H = cache.size.height;
  if (x < 0 || y < 0 || x >= cache.size.width || y >= H) return;
  const water = g.water[y][x], obj = g.objects[y][x];
  const b = cache.buildings.find((b) => b.tiles.some(([tx, ty]) => tx === x && ty === y));
  const f = cache.findings.filter((f) => f.where[0] === x && f.where[1] === y);
  el.querySelector("#tileinfo").innerHTML = `<h3>Tile ${x},${y}</h3>
    height ${dec(g.top[y][x])} · water ${water === " " ? 0 : dec(water) / 10} · badwater ${g.contamination[y][x] === " " ? 0 : dec(g.contamination[y][x]) / 9}<br>
    soil ${{ "#": "moist", x: "contaminated", w: "water", " ": "dry" }[g.moist[y][x]] || g.moist[y][x]} · flow ${g.flow[y][x] === " " ? "–" : g.flow[y][x]}
    ${obj !== " " ? `<br>object ${esc(cache.legend[obj] || obj)}` : ""}${b ? `<br>building <b>${esc(b.name)}</b>${b.finished ? "" : " (site)"}` : ""}
    ${f.map((x) => `<br><span class="${x.severity}">${esc(x.rule)}: ${esc(x.message)}</span>`).join("")}`;
}

function draw(el) {
  const cv = el.querySelector("#map2d");
  const { width: W, height: H } = cache.size, s = opts.scale, L = opts.layers, g = cache.grids;
  cv.width = W * s; cv.height = H * s;
  const ctx = cv.getContext("2d");
  const px = (x, y) => [x * s, (H - 1 - y) * s];
  const fill = (x, y, color, inset = 0) => { const [a, b] = px(x, y); ctx.fillStyle = color; ctx.fillRect(a + inset, b + inset, s - 2 * inset, s - 2 * inset); };
  let maxTop = 1;
  for (const row of g.top) for (const c of row) maxTop = Math.max(maxTop, dec(c));
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const top = dec(g.top[y][x]);
      if (L.height) { const v = 30 + Math.round((top / maxTop) * 150); fill(x, y, `rgb(${v},${v - 6},${v - 18})`); }
      const m = g.moist[y][x];
      if (L.moist && m === "#") fill(x, y, "rgba(70,200,90,.45)");
      if (L.moist && m === "x") fill(x, y, "rgba(200,60,160,.45)");
      const w = g.water[y][x];
      if (L.water && w !== " ") {
        const d = Math.min(1, dec(w) / 30), bad = g.contamination[y][x] === " " ? 0 : dec(g.contamination[y][x]) / 9;
        fill(x, y, L.badwater && bad > 0.05 ? `rgba(${120 + 100 * bad},70,${150 - 80 * bad},${0.45 + 0.5 * d})` : `rgba(40,120,230,${0.35 + 0.6 * d})`);
      }
    }
  }
  if (L.range && cache.range) for (const [x, y] of cache.range) fill(x, y, "rgba(255,255,255,.08)");
  if (L.reach && cache.reach[opts.reach]) for (const [x, y] of cache.reach[opts.reach]) fill(x, y, "rgba(255,220,80,.18)");
  if (L.cutting) for (const [x, y] of cache.cutting) fill(x, y, "rgba(160,100,40,.5)", s / 4);
  if (L.planting) for (const [x, y] of cache.planting) fill(x, y, "rgba(190,240,90,.8)", s / 3);
  if (L.roads) {
    const conn = new Set(cache.connected.map((n) => n.join(",")));
    for (const n of cache.roads) fill(n[0], n[1], conn.has(n.join(",")) ? "#d9c9a3" : "#b05a3a", s / 6);
  }
  if (L.buildings) {
    for (const b of cache.buildings) {
      const color = !b.finished ? "rgba(255,160,40,.55)" : b.paused ? "rgba(120,120,140,.75)" : "rgba(210,215,225,.85)";
      for (const [x, y] of b.tiles) fill(x, y, color, 0.5);
      if (b.door && b.finished) fill(b.door[0], b.door[1], "rgba(90,200,255,.9)", s / 2.6);
    }
  }
  if (L.only) for (const n of cache.only_links) { const [a, b] = px(n[0], n[1]); ctx.strokeStyle = "#ff5c5c"; ctx.lineWidth = 2; ctx.strokeRect(a + 1, b + 1, s - 2, s - 2); }
  if (L.sources) for (const src of cache.sources || []) {
    const [a, b] = px(src.x, src.y); ctx.fillStyle = (src.contamination || 0) > 0 ? "#c060ff" : "#40e0ff";
    ctx.beginPath(); ctx.moveTo(a + s / 2, b - s); ctx.lineTo(a + s * 1.5, b + s * 1.2); ctx.lineTo(a - s / 2, b + s * 1.2); ctx.fill();
  }
  if (L.findings) {
    const col = { critical: "#ff5c5c", warn: "#f4b740", info: "#5cb3ff" };
    for (const f of cache.findings) {
      const [a, b] = px(f.where[0], f.where[1]); ctx.strokeStyle = col[f.severity]; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(a + s / 2, b + s / 2, s * 1.4, 0, 7); ctx.stroke();
    }
  }
}
