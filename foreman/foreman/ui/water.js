// Water: proposals from hydro.py (dams, badwater diversions, reservoirs, ponds, decks, pumps, wheels) with a
// preview of what each one floods. Nothing here acts: the harness calls are for the playing AI to copy.
const DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
const dec = (c) => DIGITS.indexOf(c);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const calls = (list) => (list || []).length
  ? `<div>${list.map((c) => `<code>${esc(c)}</code>`).join("<br>")} <button data-copy="${esc(list.join("\n"))}">copy</button></div>` : "";
const sevc = { critical: "critical", warn: "warn", info: "info" };

let W = null, M = null, pick = null;

export async function renderWater(el, api) {
  [W, M] = await Promise.all([api("/api/water"), api("/api/map")]);
  const items = [];
  const add = (group, label, obj, shape) => items.push({ group, label, obj, shape });
  W.dams.proposals.forEach((p) => add("Dam proposals", p.why, p, { line: p.line, region: p.region }));
  W.dams.rejected.forEach((p) => add("Rejected (would flood)", `${p.why}; floods ${p.flooded.slice(0, 4).join(", ")}`, p, { line: p.line, region: p.region, bad: true }));
  W.pools.filter((p) => p.full).forEach((p) => add("Existing pools", `${p.kinds.join("/")} x${p.bbox[0]}-${p.bbox[2]} y${p.bbox[1]}-${p.bbox[3]} holds to z${p.level}: predicted ${p.predicted}, standing ${p.observed} (${p.error == null ? "–" : (p.error * 100).toFixed(1) + "%"})`, p, { line: p.tiles, region: p.region }));
  W.badwater.diversions.forEach((p) => add("Badwater diversions", `${p.blocks}: ${p.why}`, p, { line: p.line, region: p.region }));
  W.reservoirs.forEach((r) => add("Reservoirs (dry bowls)", r.why, r, { region: r.cells }));
  W.ponds.forEach((d) => add("Irrigation ponds", d.why, d, { point: d.pond }));
  W.decks.forEach((d) => add("Platform decks", d.why, d, { rect: d.bbox }));
  W.pumps.sites.slice(0, 12).forEach((s) => add("Pump sites", `bank (${s.bank.join(",")}) over water ${s.water.join(",")} depth ${s.depth}${s.held ? " · held by a dam" : ""}`, s, { point: s.bank }));
  W.wheels.forEach((s) => add("Wheel sites", `(${s.x},${s.y},z${s.z}) flow ${s.speed} ${s.dir}${s.bad ? " · badwater" : ""}`, s, { point: [s.x, s.y] }));
  const groups = [...new Set(items.map((i) => i.group))];
  const src = W.sources.map((g) => `<tr><td>${esc(g.name)}${g.bad ? ' <span class="critical">bad</span>' : ""}</td><td>x${g.bbox[0]}-${g.bbox[2]} y${g.bbox[1]}-${g.bbox[3]} z${g.z}</td><td>${g.strength}</td>
    <td>${g.body == null ? '<span class="muted">dry</span>' : "W" + g.body} → ${g.downstream.slice(0, 5).map((b) => "W" + b).join(", ")}</td>
    <td>${g.activates ? `<span class="warn">in ${g.activates.cycles} cycles + ${g.activates.days} d</span>` : ""}</td></tr>`).join("");
  const bodies = W.bodies.slice(0, 12).map((b) => `<tr><td>W${b.id}</td><td>${b.tiles}</td><td>z${b.head}</td><td>${b.volume}</td>
    <td class="${b.dirt >= 0.5 ? "critical" : ""}">${Math.round(b.dirt * 100)}%</td><td>${b.spillsTo.map((x) => "W" + x).join(", ")}</td>
    <td class="muted">${b.fedBy.map(esc).join("<br>")}</td></tr>`).join("");
  el.innerHTML = `<div class="grid" style="grid-template-columns: minmax(420px, 1fr) minmax(420px, 1fr)">
    <div>
      <div class="card"><h3>Water findings</h3>${W.findings.map((f) => `<div><span class="sev ${sevc[f.severity]}">${f.severity}</span> ${esc(f.message)}</div>`).join("") || '<span class="muted">none</span>'}
        <div class="muted" style="margin-top:6px">held behind dams now: ${W.heldVolume} units (~${Math.round(W.heldVolume * W.constants.goodsPerUnit)} water) · dam holds ${W.constants.damHold}, levee ${W.constants.leveeHold}, evaporation ${W.constants.evaporation}/day</div></div>
      ${groups.map((g) => `<div class="card" style="margin-top:12px"><h3>${esc(g)}</h3>${items.map((it, i) => it.group !== g ? "" :
        `<div class="prop" data-i="${i}" style="padding:4px 0;border-bottom:1px solid var(--line);cursor:pointer">${esc(it.label)}${calls(it.obj.calls)}</div>`).join("")}</div>`).join("")}
      <div class="card" style="margin-top:12px"><h3>Sources</h3><table><tr><th>source</th><th>where</th><th>strength</th><th>feeds</th><th>timer</th></tr>${src}</table></div>
      <div class="card" style="margin-top:12px"><h3>Water bodies (largest)</h3><table><tr><th>body</th><th>tiles</th><th>head</th><th>volume</th><th>bad</th><th>spills to</th><th>fed by</th></tr>${bodies}</table></div>
      ${W.cores.length ? `<div class="card" style="margin-top:12px"><h3>Unstable Cores</h3>${W.cores.map((c) => `<div>(${c.x},${c.y},z${c.z}) cycle ${c.countdownCycle}: ${c.effects.map(esc).join("; ")}</div>`).join("")}</div>` : ""}
      <div class="card" style="margin-top:12px"><h3>Natural barriers</h3>${W.barriers.map((b) => `<div>${esc(b.name)} x${b.bbox[0]}-${b.bbox[2]} y${b.bbox[1]}-${b.bbox[3]} z${b.z}: ${esc(b.verdict)}</div>`).join("") || '<span class="muted">none</span>'}</div>
    </div>
    <div style="position:sticky;top:52px;align-self:start"><div class="card"><h3>Preview</h3><canvas id="wprev"></canvas>
      <div id="wsel" class="muted">click a proposal: red = the line, blue = the water it holds, orange = flooded buildings</div></div></div>
  </div>`;
  el.querySelectorAll(".prop").forEach((d) => (d.onclick = (e) => {
    if (e.target.closest("button")) return;
    el.querySelectorAll(".prop").forEach((x) => (x.style.background = ""));
    d.style.background = "#26303a";
    pick = items[+d.dataset.i];
    el.querySelector("#wsel").textContent = pick.label;
    draw(el);
  }));
  if (!pick && items.length) pick = items[0];
  draw(el);
}

function draw(el) {
  const cv = el.querySelector("#wprev");
  const { width: MW, height: MH } = M.size, g = M.grids;
  let box = [0, 0, MW - 1, MH - 1];
  const sh = pick?.shape || {};
  const pts = [...(sh.line || []), ...(sh.region || [])];
  if (sh.rect) pts.push([sh.rect[0], sh.rect[1]], [sh.rect[2], sh.rect[3]]);
  if (sh.point) pts.push(sh.point);
  if (pts.length) {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const pad = 8;
    box = [Math.max(0, Math.min(...xs) - pad), Math.max(0, Math.min(...ys) - pad), Math.min(MW - 1, Math.max(...xs) + pad), Math.min(MH - 1, Math.max(...ys) + pad)];
  }
  const bw = box[2] - box[0] + 1, bh = box[3] - box[1] + 1;
  const s = Math.max(2, Math.min(14, Math.floor(560 / Math.max(bw, bh))));
  cv.width = bw * s; cv.height = bh * s;
  const ctx = cv.getContext("2d");
  const px = (x, y) => [(x - box[0]) * s, (box[3] - y) * s];
  const fill = (x, y, c, inset = 0) => { if (x < box[0] || x > box[2] || y < box[1] || y > box[3]) return; const [a, b] = px(x, y); ctx.fillStyle = c; ctx.fillRect(a + inset, b + inset, s - 2 * inset, s - 2 * inset); };
  let maxTop = 1;
  for (const row of g.top) for (const c of row) maxTop = Math.max(maxTop, dec(c));
  for (let y = box[1]; y <= box[3]; y++) for (let x = box[0]; x <= box[2]; x++) {
    const t = dec(g.top[y][x]), v = 30 + Math.round((t / maxTop) * 150);
    fill(x, y, `rgb(${v},${v - 6},${v - 18})`);
    const w = g.water[y][x];
    if (w !== " ") {
      const bad = g.contamination[y][x] === " " ? 0 : dec(g.contamination[y][x]) / 9;
      fill(x, y, bad > 0.05 ? `rgba(200,70,110,.75)` : `rgba(40,120,230,${0.35 + 0.6 * Math.min(1, dec(w) / 30)})`);
    }
  }
  for (const b of M.buildings) for (const [x, y] of b.tiles) fill(x, y, "rgba(210,215,225,.8)", s > 4 ? 1 : 0);
  if (sh.region) for (const [x, y] of sh.region) fill(x, y, sh.bad ? "rgba(255,90,90,.35)" : "rgba(90,200,255,.55)");
  if (pick?.obj?.flooded?.length) {
    const hit = new Set(pick.obj.flooded);
    for (const b of M.buildings) if (hit.has(`${b.name}(${b.x},${b.y})`)) for (const [x, y] of b.tiles) fill(x, y, "rgba(255,160,40,.95)", 1);
  }
  if (sh.line) for (const [x, y] of sh.line) fill(x, y, "#ff4040");
  if (sh.rect) { const [a, b] = px(sh.rect[0], sh.rect[3]); ctx.strokeStyle = "#5fd38d"; ctx.lineWidth = 2; ctx.strokeRect(a, b, (sh.rect[2] - sh.rect[0] + 1) * s, (sh.rect[3] - sh.rect[1] + 1) * s); }
  if (sh.point) { const [a, b] = px(sh.point[0], sh.point[1]); ctx.strokeStyle = "#ffe066"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(a + s / 2, b + s / 2, Math.max(6, s * 1.5), 0, 7); ctx.stroke(); }
  ctx.fillStyle = "#fff"; ctx.font = "11px system-ui"; ctx.fillText(`x${box[0]}-${box[2]} y${box[1]}-${box[3]} (north up)`, 4, 12);
}
