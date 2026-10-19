// Foreman UI: vanilla ES modules, no build step. Every page reads the read-only JSON API and re-renders on a timer.
import { renderMap } from "./map2d.js";

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const day = (d) => (d ? `c${Math.floor(d / 100)}d${Math.floor(d % 100)}` : "?");
export const api = async (path) => {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${(await r.text()).slice(0, 200)}`);
  return r.headers.get("content-type")?.includes("json") ? r.json() : r.text();
};

const pages = {
  overview: { every: 5000, render: overview },
  findings: { every: 5000, render: findings },
  buildings: { every: 10000, render: buildings },
  supply: { every: 15000, render: supply },
  map: { every: 30000, render: (el) => renderMap(el, api) },
  map3d: { every: 0, render: (el) => lazy(el, "./map3d.js", "renderMap3d") },
  water: { every: 0, render: (el) => lazy(el, "./water.js", "renderWater") },
  plan: { every: 0, render: (el) => lazy(el, "./plan.js", "renderPlan") },
  requests: { every: 10000, render: requests },
  rules: { every: 0, render: rules },
};
let timer = null;
const state = { sort: {}, filter: {} };

async function lazy(el, path, fn) {
  try {
    const mod = await import(path);
    await mod[fn](el, api);
  } catch (e) {
    el.innerHTML = `<div class="card">Not available yet: ${esc(e.message)}</div>`;
  }
}

async function show() {
  const name = (location.hash || "#overview").slice(1).split("?")[0];
  const page = pages[name] || pages.overview;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("on", a.getAttribute("href") === `#${name}`));
  clearInterval(timer);
  const el = $("#page");
  el.innerHTML = '<span class="muted">loading…</span>';
  const run = async (first) => {
    try {
      await page.render(el, first);
    } catch (e) {
      el.innerHTML = `<div class="card critical">${esc(e.message)}</div>`;
    }
  };
  await run(true);
  if (page.every) timer = setInterval(() => run(false), page.every);
}

async function status() {
  try {
    const s = await api("/api/status");
    const age = s.age == null ? "–" : `${Math.round(s.age)} s ago`;
    $("#status").innerHTML = `${esc(s.source)} · updated ${age}` + (s.error ? ` · <span class="warn">${esc(s.error)}</span>` : "");
  } catch {
    $("#status").innerHTML = '<span class="critical">Foreman service not answering</span>';
  }
}

window.addEventListener("hashchange", show);
document.addEventListener("click", (ev) => {
  const b = ev.target.closest("button[data-copy]");
  if (!b) return;
  navigator.clipboard.writeText(b.dataset.copy);
  b.textContent = "copied";
  setTimeout(() => (b.textContent = "copy"), 1200);
});
show();
status();
setInterval(status, 5000);

// ------------------------------------------------------------------ helpers
const fixCell = (fix) => (fix ? `<code>${esc(fix)}</code> <button data-copy="${esc(fix)}">copy</button>` : "");
const sev = (s) => `<span class="sev ${s}">${s}</span>`;
function bar(value, max, mark, color) {
  const pct = Math.max(0, Math.min(100, (100 * value) / (max || 1)));
  const m = mark != null ? `<b style="left:${Math.min(100, (100 * mark) / (max || 1))}%"></b>` : "";
  return `<div class="bar"><i style="width:${pct}%;background:${color || "var(--ok)"}"></i>${m}</div>`;
}
function findingRows(list) {
  return list
    .map((f) => `<tr><td>${sev(f.severity)}</td><td><b>${esc(f.rule)}</b><br><span class="muted">${f.runs > 1 ? "x" + f.runs : ""}
      ${f.first_day ? " since " + day(f.first_day) : ""}</span></td><td>${esc(f.message)}${f.where ? ` <span class="muted">@ ${f.where.join(",")}</span>` : ""}
      <br>${fixCell(f.fix)}</td></tr>`)
    .join("");
}
function sortable(el, key, rows, cols, fmt) {
  const st = state.sort[key] || { col: null, dir: 1 };
  if (st.col) rows.sort((a, b) => (a[st.col] > b[st.col] ? 1 : a[st.col] < b[st.col] ? -1 : 0) * st.dir);
  el.innerHTML = `<table><thead><tr>${cols.map(([c, label]) => `<th data-col="${c}">${label}${st.col === c ? (st.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(fmt).join("")}</tbody></table>`;
  el.querySelectorAll("th").forEach((th) =>
    th.addEventListener("click", () => {
      const c = th.dataset.col;
      state.sort[key] = { col: c, dir: st.col === c ? -st.dir : 1 };
      sortable(el, key, rows, cols, fmt);
    }));
}

// ------------------------------------------------------------------ pages
async function overview(el) {
  const o = await api("/api/overview");
  const t = o.time, w = o.weather, p = o.population, lg = o.ledger;
  const weather = w.state === "approaching" ? `<span class="warn">${esc(w.hazard)} in ${w.daysUntil} days</span>`
    : w.state === "hazardous" ? `<span class="critical">${esc(w.hazard)}: ${w.daysRemaining} days left</span>` : esc(w.state);
  const foodOk = o.food.stock >= o.food.need, waterOk = o.water.stock >= o.water.need;
  const trend = Object.entries(o.trend || {}).filter(([k]) => k !== "span")
    .map(([k, v]) => `<span class="pill ${v < 0 ? "warn" : ""}">${k} ${v > 0 ? "+" : ""}${Math.round(v)}/day</span>`).join(" ");
  el.innerHTML = `<div class="grid">
    <div class="card"><h3>Time</h3><div class="big">c${t.cycle} d${t.cycleDay}</div>
      <div>${Math.round((t.dayProgress || 0) * 100)}% of the day · speed ${t.speed} · ${weather}</div>
      <div class="muted">longest hazard so far ${o.hazard_days} days${o.hours ? ` · workday ${Math.round(o.hours.hours)} h` : ""}</div></div>
    <div class="card"><h3>Food</h3><div class="big ${o.food.days < 3 ? "critical" : ""}">${o.food.days} days</div>
      ${bar(o.food.stock, Math.max(o.food.stock, o.food.need) * 1.2, o.food.need, foodOk ? "var(--ok)" : "var(--crit)")}
      <div>${o.food.stock} edible vs hazard reserve ${o.food.need} <span class="${foodOk ? "ok" : "critical"}">${foodOk ? "ok" : "SHORT"}</span></div></div>
    <div class="card"><h3>Water</h3><div class="big">${o.water.days} days</div>
      ${bar(o.water.stock, o.water.cap || o.water.stock, o.water.need, waterOk ? "var(--info)" : "var(--crit)")}
      <div>${o.water.stock} / ${o.water.cap} stored · reserve ${o.water.need} <span class="${waterOk ? "ok" : "critical"}">${waterOk ? "ok" : "SHORT"}</span></div>
      <div class="muted">use ${o.water.use}/day: beavers ${o.water.drink}${Object.entries(o.water.build).map(([k, v]) => `, ${k} ${v}`).join("")}</div></div>
    <div class="card"><h3>Population</h3><div class="big">${o.beavers}</div>
      <div>${p.adults} adults + ${p.children} kits · ${p.freeBeds} free beds · homeless ${p.homeless} · unemployed ${p.unemployed}</div>
      <div>this cycle +${lg.cycle.born} −${lg.cycle.died} · last cycle +${lg.previous.born} −${lg.previous.died}</div>
      <div class="${lg.running < lg.need ? "warn" : "muted"}">pods ${lg.running}/${lg.pods} running, want ≥ ${lg.need}</div>
      <div class="muted">science ${o.science} · wellbeing ${o.wellbeing}</div></div>
    <div class="card"><h3>Power</h3>${o.power.map((n, i) => `<div>net ${i + 1}: ${n.supply}/${n.demand} hp · ${n.generators} generators · ${n.machines} machines (nominal ${n.nominal})</div>
      ${bar(n.nominal, Math.max(n.supply, n.nominal), null, n.nominal > n.supply ? "var(--crit)" : "var(--ok)")}`).join("") || '<span class="muted">no networks</span>'}</div>
    <div class="card"><h3>Progress</h3>${o.progress ? `<div class="big">${o.progress.done}/${o.progress.total}</div>
      <div>ready to place: ${o.progress.ready.map((n) => `<span class="pill">${esc(n)}</span>`).join("") || "none"}</div>
      <div class="muted">next: ${o.progress.locked.map(([n, s]) => `${esc(n)} ${s}`).join(" · ")}</div>` : '<span class="muted">no blueprints yet</span>'}</div>
    <div class="card"><h3>Needs</h3>${o.needs.map((n) => `<div>${esc(n.need)} ${bar(n.average + 1, 2, null, n.critical ? "var(--crit)" : n.warning ? "var(--warn)" : "var(--ok)")}
      <span class="muted">avg ${n.average}${n.critical ? ` · <span class="critical">${n.critical} critical</span>` : ""}</span></div>`).join("")}</div>
    <div class="card"><h3>Trend</h3>${trend || '<span class="muted">needs a quarter day of history</span>'}
      <h3 style="margin-top:12px">Stream</h3>${o.health ? `overlay <span class="${o.health.overlay ? "ok" : "critical"}">${o.health.overlay ? "up" : "down"}</span> ·
      OBS <span class="${o.health.obs ? "ok" : "muted"}">${o.health.obs ? "running" : "not running"}</span>` : '<span class="muted">not checked yet</span>'}</div>
  </div>
  <div class="card" style="margin-top:12px"><h3>Top findings · ${o.counts.critical} critical, ${o.counts.warn} warn, ${o.counts.info} info</h3>
    <table>${findingRows(o.top)}</table></div>`;
}

async function findings(el, first) {
  const d = await api("/api/findings");
  const f = state.filter.findings || (state.filter.findings = { sev: "all", q: "" });
  const keep = (x) => (f.sev === "all" || x.severity === f.sev) && (!f.q || JSON.stringify(x).toLowerCase().includes(f.q));
  const open = d.open.filter(keep);
  el.innerHTML = `<div class="toolbar"><label>severity <select id="fsev">${["all", "critical", "warn", "info"]
    .map((s) => `<option ${s === f.sev ? "selected" : ""}>${s}</option>`).join("")}</select></label>
    <input id="fq" type="search" placeholder="filter" value="${esc(f.q)}"> <span class="muted">${open.length} of ${d.open.length} open · now ${day(d.now_day)}</span></div>
    <div class="card"><table>${findingRows(open)}</table></div>
    <div class="card" style="margin-top:12px"><h3>Recently cleared</h3><table>${d.cleared.filter(keep).map((c) =>
      `<tr><td>${sev(c.severity)}</td><td>${esc(c.rule)}</td><td>${esc(c.message)}</td><td class="muted">${day(c.first_day)}–${day(c.last_day)}</td></tr>`).join("")}</table></div>`;
  $("#fsev", el).onchange = (e) => { f.sev = e.target.value; findings(el); };
  const q = $("#fq", el);
  q.oninput = (e) => { f.q = e.target.value.toLowerCase(); findings(el).then(() => { const n = $("#fq", el); n.focus(); n.selectionStart = n.value.length; }); };
}

async function buildings(el) {
  const d = await api("/api/buildings");
  const f = state.filter.buildings || (state.filter.buildings = { q: "", problems: false });
  let rows = d.buildings.map((b) => ({
    ...b, label: `${b.name}(${b.x},${b.y})`, state: !b.finished ? "site" : b.paused ? "paused" : "on",
    problems: b.findings.length, work: b.workers ? `${b.workers[0]}/${b.workers[1]}` : "",
  }));
  rows = rows.filter((b) => (!f.q || JSON.stringify(b).toLowerCase().includes(f.q)) && (!f.problems || b.problems || b.statuses.length || b.connected === false));
  el.innerHTML = `<div class="toolbar"><input id="bq" type="search" placeholder="filter (name, status, recipe…)" value="${esc(f.q)}">
    <label><input id="bp" type="checkbox" ${f.problems ? "checked" : ""}> only with problems</label><span class="muted">${rows.length} buildings</span></div><div id="btab"></div>`;
  const cols = [["label", "Building"], ["state", "State"], ["work", "Workers"], ["power", "Power"], ["connected", "Road"],
    ["recipe", "Producing"], ["priority", "Priority"], ["problems", "Findings / reason"]];
  sortable($("#btab", el), "buildings", rows, cols, (b) => `<tr>
    <td>${esc(b.label)}<br><span class="muted">z${b.z}</span></td>
    <td>${b.state === "site" ? `site ${Math.round((b.progress || 0) * 100)}%` : b.state}${b.statuses.length ? `<br><span class="warn">${b.statuses.map(esc).join(", ")}</span>` : ""}</td>
    <td>${b.work}</td>
    <td>${b.power ? `<span class="${b.power === "linked" ? "ok" : "warn"}">${esc(b.power)}</span>` : ""}${b.network ? `<br><span class="muted">${b.network[0]}/${b.network[1]} hp</span>` : ""}</td>
    <td>${b.connected === null ? "" : b.connected ? '<span class="ok">yes</span>' : '<span class="critical">no</span>'}</td>
    <td>${b.recipe ? `${esc(b.recipe)} ${Math.round((b.batch || 0) * 100)}%` : b.setup?.good ? `stores ${esc(b.setup.good)}` : ""}</td>
    <td>${esc(b.priority || "")}</td>
    <td>${b.findings.map((x) => `${sev(x.severity)} ${esc(x.message)}`).join("<br>")}${b.reason ? `<br><span class="muted">paused: ${esc(b.reason.reason)}${b.reason.until ? " until " + esc(b.reason.until) : ""}</span>` : ""}</td></tr>`);
  const q = $("#bq", el);
  q.oninput = (e) => { f.q = e.target.value.toLowerCase(); buildings(el).then(() => { const n = $("#bq", el); n.focus(); n.selectionStart = n.value.length; }); };
  $("#bp", el).onchange = (e) => { f.problems = e.target.checked; buildings(el); };
}

function chart(canvas, pts, cap, mark) {
  const ctx = canvas.getContext("2d");
  const W = (canvas.width = canvas.clientWidth * devicePixelRatio), H = (canvas.height = canvas.clientHeight * devicePixelRatio);
  ctx.clearRect(0, 0, W, H);
  if (pts.length < 2) { ctx.fillStyle = "#8b96a1"; ctx.fillText("collecting history…", 8, 16 * devicePixelRatio); return; }
  const x0 = pts[0][0], x1 = pts[pts.length - 1][0];
  const top = Math.max(cap || 0, mark || 0, ...pts.map((p) => p[1])) * 1.05 || 1;
  const X = (d) => ((d - x0) / (x1 - x0 || 1)) * (W - 4) + 2, Y = (v) => H - 2 - (v / top) * (H - 4);
  const hline = (v, color) => { ctx.strokeStyle = color; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(0, Y(v)); ctx.lineTo(W, Y(v)); ctx.stroke(); ctx.setLineDash([]); };
  if (cap) hline(cap, "#5c6670");
  if (mark) hline(mark, "#f4b740");
  ctx.strokeStyle = "#5fd38d"; ctx.lineWidth = 1.5 * devicePixelRatio; ctx.beginPath();
  pts.forEach(([d, v], i) => (i ? ctx.lineTo(X(d), Y(v)) : ctx.moveTo(X(d), Y(v))));
  ctx.stroke();
}

async function supply(el) {
  const d = await api("/api/supply");
  const goods = Object.fromEntries(d.goods.map((g) => [g.id, g]));
  const ids = ["food", "Water", ...Object.keys(d.series).filter((k) => k !== "food" && k !== "Water").sort()];
  const r = d.reserve;
  el.innerHTML = `<div class="grid">${ids.filter((k) => d.series[k] || goods[k]).map((k) => {
    const g = goods[k] || {}, rate = d.rates[k];
    return `<div class="card"><h3>${esc(k)}</h3><div>${k === "food" ? r.food_stock : g.available ?? 0}${g.capacity ? " / " + g.capacity : ""}
      ${rate != null ? `<span class="${rate < 0 ? "warn" : "ok"}"> ${rate > 0 ? "+" : ""}${Math.round(rate)}/day</span>` : ""}</div>
      <canvas class="chart" data-k="${esc(k)}"></canvas></div>`;
  }).join("")}</div>
  <div class="card" style="margin-top:12px"><h3>Water budget</h3>use ${r.water_use.toFixed(1)}/day ·
    ${Object.entries(r.water_build).map(([k, v]) => `${esc(k)} ${v}`).join(", ") || "no building water"} · hazard reserve ${Math.round(r.water_need)}
    (${r.hazard_days} days × 1.5)</div>
  <div class="card" style="margin-top:12px"><h3>Farms and foresters (plots in each work range)</h3><table>
    ${d.farms.map((f) => `<tr><td>${esc(f.label)}</td><td>${f.workers ?? ""} workers</td><td>${Object.entries(f.plots).map(([p, n]) => `<span class="pill">${esc(p)} ${n}</span>`).join("") || '<span class="warn">no marked plots in range</span>'}</td>
    <td class="muted">${f.plantingFirst == null ? "" : f.plantingFirst ? "plants first" : "harvests first"}</td></tr>`).join("")}</table></div>`;
  el.querySelectorAll("canvas[data-k]").forEach((c) => {
    const k = c.dataset.k;
    chart(c, d.series[k] || [], goods[k]?.capacity, k === "food" ? r.food_need : k === "Water" ? r.water_need : null);
  });
}

async function requests(el) {
  const d = await api("/api/requests");
  el.innerHTML = `<div class="card"><h3>Open operator requests (harness/pending.txt)</h3><table>${d.requests.map((q) =>
    `<tr><td>${esc(q.text)}</td><td class="muted">${q.open_days != null ? q.open_days + " days open" : ""}</td></tr>`).join("") || "<tr><td>none</td></tr>"}</table></div>`;
}

async function rules(el) {
  const d = await api("/api/rules");
  const f = state.filter.rules || (state.filter.rules = { status: "all", q: "" });
  const counts = d.rules.reduce((a, r) => ((a[r.status] = (a[r.status] || 0) + 1), a), {});
  const rows = d.rules.filter((r) => (f.status === "all" || r.status === f.status) && (!f.q || JSON.stringify(r).toLowerCase().includes(f.q)));
  el.innerHTML = `<div class="toolbar"><label>status <select id="rs">${["all", "checked", "manual", "conduct"].map((s) => `<option ${s === f.status ? "selected" : ""}>${s}</option>`).join("")}</select></label>
    <input id="rq" type="search" placeholder="filter" value="${esc(f.q)}">
    <span class="muted">${d.rules.length} rules: ${counts.checked || 0} checked, ${counts.manual || 0} manual, ${counts.conduct || 0} conduct</span>
    ${d.unknown.length ? `<span class="warn">monitor rule ids missing from rules.yaml: ${esc(d.unknown.join(", "))}</span>` : ""}</div>
    <div class="card"><table><tr><th>Rule</th><th>Status</th><th>Text</th><th>Last raised</th></tr>${rows.map((r) => `<tr><td><b>${esc(r.id)}</b></td>
    <td>${r.status === "checked" ? `<span class="ok">${r.monitors.map(esc).join("<br>")}</span>` : r.status === "manual" ? `<span class="warn">manual (phase ${r.phase})</span>` : '<span class="muted">conduct</span>'}</td>
    <td>${esc(r.text)}<br><span class="muted">${esc(r.source || "")}</span></td><td class="muted">${r.last_day ? day(r.last_day) : ""}</td></tr>`).join("")}</table></div>`;
  $("#rs", el).onchange = (e) => { f.status = e.target.value; rules(el); };
  $("#rq", el).onchange = (e) => { f.q = e.target.value.toLowerCase(); rules(el); };
}
