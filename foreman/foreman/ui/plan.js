// Plan: the masterplan (zones, reserved tiles, staged build order) and the next steps validated against the live
// map. Nothing here acts: harness calls are for the playing AI to copy, and zone accept/reject is a CLI command.
const DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
const dec = (c) => DIGITS.indexOf(c);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const calls = (list) => (list || []).length
  ? `<div>${list.map((c) => `<code>${esc(c)}</code>`).join("<br>")} <button data-copy="${esc(list.join("\n"))}">copy</button></div>` : "";
const cmd = (c) => `<code>${esc(c)}</code> <button data-copy="${esc(c)}">copy</button>`;
const ZC = { core: "#f4b740", farm: "#5fd38d", forest: "#2e8b57", berries: "#c05fd3", industry: "#ff7a45",
  reservoir: "#4aa3ff", deck: "#7fd3ff", ruins: "#b0a090", dam: "#ff4040" };

let P = null, M = null, N = null, pick = null;

// same wording as masterplan.next_text
const state = (s) => s.ready ? "READY" : s.blocked ? `BLOCKED: ${s.blocked}` : s.validation && !s.validation.ok ? "FIX FIRST"
  : s.validation?.warn ? "CHECK" : !s.calls.length ? "SPOT NEEDED" : "READY";

export async function renderPlan(el, api) {
  [P, M, N] = await Promise.all([api("/api/masterplan"), api("/api/map"), api("/api/suggestions?n=5").catch(() => null)]);
  const stages = [...new Set(P.steps.map((s) => s.stage))].sort((a, b) => a - b);
  const op = P.opening || {};
  const next = (N?.next || []).map((s) => `<div style="padding:4px 0;border-bottom:1px solid var(--line)">
      <b>[${s.stage}] ${esc(s.title)}</b> <span class="${s.ready ? "" : "warn"}">${esc(state(s))}</span>
      ${s.note ? `<span class="muted">${esc(s.note)}</span>` : ""}
      ${calls(s.calls)}${s.after?.length ? `<div class="muted">after placing:</div>${calls(s.after)}` : ""}
      ${(s.validation?.problems || []).map((p) => `<div class="${p.severity}">! ${esc(p.message)}${p.fix ? ` → <code>${esc(p.fix)}</code>` : ""}</div>`).join("")}</div>`).join("")
    || '<span class="muted">nothing queued</span>';
  const zones = P.zones.map((z, i) => `<tr class="zrow" data-i="${i}" style="cursor:pointer">
      <td><span style="color:${ZC[z.kind] || "#ccc"}">■</span> ${esc(z.id)}</td><td>${esc(z.status)}</td><td>${esc(z.why)}</td>
      <td>${cmd(`python -m foreman plan --accept ${z.id}`)}<br>${cmd(`python -m foreman plan --reject ${z.id}`)}</td></tr>`).join("");
  const steps = stages.map((st) => `<div class="card" style="margin-top:12px"><h3>Stage ${st}</h3>${P.steps.filter((s) => s.stage === st).map((s) => {
    const i = P.steps.indexOf(s);
    return `<div class="srow" data-s="${i}" style="padding:4px 0;border-bottom:1px solid var(--line);cursor:pointer">
      ${P.done?.[s.id] ? '<span class="muted">✓ done</span>' : "☐"} <b>${esc(s.title)}</b> <span class="muted">${esc(s.zone || "")} · ${esc(s.why)}</span>
      ${(s.rules || []).length ? `<div class="muted">rules: ${s.rules.map(esc).join(", ")}</div>` : ""}
      ${P.done?.[s.id] ? "" : calls(s.calls)}</div>`;
  }).join("")}</div>`).join("");
  el.innerHTML = `<div class="grid" style="grid-template-columns: minmax(460px, 1fr) minmax(420px, 1fr)">
    <div>
      <div class="card"><h3>Masterplan v${P.version ?? "?"}</h3>
        <div class="muted">generated ${esc(P.generated)} · District Centre door (${(P.dc || []).join(",")}) · ${P.steps.length} steps</div>
        <div>Opening batch: ${op.actions ?? 0} actions, <span class="${op.ok ? "" : "critical"}">${op.ok ? "OK" : "PROBLEMS"}</span>
          (${op.critical ?? 0} critical, ${op.warn ?? 0} warn) · cost ${esc(JSON.stringify(op.cost || {}))} · have ${esc(JSON.stringify(op.have || {}))}</div>
        ${(op.problems || []).map((p) => `<div class="warn">${esc(p)}</div>`).join("")}
        ${(P.notes || []).map((n) => `<div class="muted">${esc(n)}</div>`).join("")}
        <div style="margin-top:6px">Regenerate: ${cmd("python -m foreman plan --regenerate")} · one zone: ${cmd("python -m foreman plan --regenerate ZONE")}</div>
        <div>Pre-check any batch: ${cmd('python -m foreman check \'place_building(template="...", x=.., y=.., z=.., orientation=..)\'')}</div></div>
      <div class="card" style="margin-top:12px"><h3>Next (validated against the map now)</h3>${next}</div>
      <div class="card" style="margin-top:12px"><h3>Zones</h3><table><tr><th>zone</th><th>status</th><th>why</th><th>decide</th></tr>${zones}</table></div>
      ${steps}
    </div>
    <div style="position:sticky;top:52px;align-self:start"><div class="card"><h3>Layout</h3><canvas id="pprev"></canvas>
      <div id="psel" class="muted" style="margin-top:6px">click a zone or step to highlight it</div></div></div>
  </div>`;
  el.querySelectorAll(".zrow").forEach((r) => (r.onclick = () => { pick = { zone: P.zones[+r.dataset.i] }; label(el); draw(el); }));
  el.querySelectorAll(".srow").forEach((r) => (r.onclick = (ev) => {
    if (ev.target.closest("button")) return;
    pick = { step: P.steps[+r.dataset.s] }; label(el); draw(el);
  }));
  draw(el);
}

function label(el) {
  el.querySelector("#psel").textContent = pick?.zone ? `${pick.zone.id}: ${pick.zone.why}` : pick?.step ? `${pick.step.title}: ${pick.step.why}` : "";
}

function draw(el) {
  const cv = el.querySelector("#pprev");
  const { width: MW, height: MH } = M.size, g = M.grids;
  let box = [0, 0, MW - 1, MH - 1];
  const pts = [];
  if (pick?.zone?.bbox) { const b = pick.zone.bbox; pts.push([b[0], b[1]], [b[2], b[3]]); }
  for (const sp of pick?.step?.spots || []) pts.push(...sp.tiles);
  if (pts.length) {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]), pad = 8;
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
    if (g.water[y][x] !== " ") fill(x, y, g.contamination[y][x] !== " " ? "rgba(200,70,110,.75)" : "rgba(40,120,230,.6)");
  }
  for (const b of M.buildings) for (const [x, y] of b.tiles) fill(x, y, "rgba(210,215,225,.8)", s > 4 ? 1 : 0);
  for (const z of P.zones) {
    if (!z.bbox) continue;
    const [a, b] = px(z.bbox[0], z.bbox[3]);
    ctx.strokeStyle = ZC[z.kind] || "#ccc"; ctx.lineWidth = pick?.zone === z ? 3 : 1; ctx.setLineDash(z.status === "accepted" ? [] : [4, 3]);
    ctx.strokeRect(a, b, (z.bbox[2] - z.bbox[0] + 1) * s, (z.bbox[3] - z.bbox[1] + 1) * s);
  }
  ctx.setLineDash([]);
  for (const st of P.steps) for (const sp of st.spots || []) {
    const hi = pick?.step === st;
    for (const [x, y] of sp.tiles) fill(x, y, hi ? "rgba(255,224,102,.95)" : P.done?.[st.id] ? "rgba(120,120,120,.4)" : "rgba(255,224,102,.35)", 1);
    if (hi && sp.door?.length) fill(sp.door[0], sp.door[1], "#ff4040", Math.max(1, s / 4));
  }
  ctx.fillStyle = "#fff"; ctx.font = "11px system-ui"; ctx.fillText(`x${box[0]}-${box[2]} y${box[1]}-${box[3]} (north up)`, 4, 12);
}
