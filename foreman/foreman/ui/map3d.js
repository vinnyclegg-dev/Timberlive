// Map 3D: terrain columns, caves and overhangs (bridge layered columns), water, buildings and the water plans,
// with a height slicer. Caves are carved out of the ground and drawn see-through, so tunnels show under the surface. three.js r169 (MIT) is vendored in /ui/vendor. Game x -> three x, game y -> three -z
// (north away from the camera), game z (height) -> three y.
import * as THREE from "three";
import { OrbitControls } from "/ui/vendor/OrbitControls.js";

const DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
const dec = (c) => DIGITS.indexOf(c);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const LAYERS = [["terrain", "Terrain", true], ["caves", "Caves/overhangs (see-through)", true], ["water", "Water", true],
  ["buildings", "Buildings", true], ["dams", "Dam proposals", true], ["pools", "Held pools", false],
  ["reservoirs", "Reservoirs", false], ["decks", "Platform decks", false]];

let view = null;      // persistent three.js state across re-renders

export async function renderMap3d(el, api) {
  const [M, L, W] = await Promise.all([api("/api/map"), api("/api/map3d"), api("/api/water").catch(() => null)]);
  if (view) { view.dispose(); view = null; }
  const maxTop = Math.max(...M.grids.top.flatMap((r) => [...r].map(dec)));
  el.innerHTML = `<div class="toolbar">${LAYERS.map(([k, label, on]) => `<label><input type="checkbox" data-l="${k}" ${on ? "checked" : ""}> ${label}</label>`).join("")}
    <label>cut above z <input id="zcut" type="range" min="0" max="${maxTop + 4}" value="${maxTop + 4}"> <span id="zval">all</span></label>
    <button id="reset">reset view</button> <button id="tocaves">go to caves</button></div>
    <div class="mapwrap"><div id="three" style="width:min(100%,1100px);height:720px;border:1px solid var(--line)"></div>
    <div id="tileinfo" class="card"><h3>Tile</h3><span class="muted">drag to orbit, wheel to zoom, right-drag to pan; click a tile</span></div></div>`;
  view = build(el.querySelector("#three"), M, L, W, maxTop);
  el.querySelectorAll("input[data-l]").forEach((i) => (i.onchange = () => { view.groups[i.dataset.l].visible = i.checked; view.render(); }));
  el.querySelectorAll("input[data-l]").forEach((i) => { view.groups[i.dataset.l].visible = i.checked; });
  el.querySelector("#zcut").oninput = (e) => {
    const z = +e.target.value;
    el.querySelector("#zval").textContent = z >= maxTop + 4 ? "all" : `z${z}`;
    view.cut(z >= maxTop + 4 ? Infinity : z);
  };
  el.querySelector("#reset").onclick = () => view.home();
  const tc = el.querySelector("#tocaves");
  let ci = -1;
  tc.disabled = !view.caves.length;
  tc.onclick = () => {     // each click: the next cave, biggest first
    ci = (ci + 1) % view.caves.length;
    const c = view.caves[ci];
    view.focus(c.box);
    tc.textContent = `go to caves (${ci + 1}/${view.caves.length}: ${c.tiles} tiles)`;
  };
  if (view.caves.length && /[?&]focus=caves/.test(location.hash)) tc.onclick();
  view.onpick = async (x, y) => {
    const t = await api(`/api/tile?x=${x}&y=${y}`).catch((err) => ({ error: err.message }));
    el.querySelector("#tileinfo").innerHTML = `<h3>Tile ${x},${y}</h3><pre>${esc(JSON.stringify(t, null, 1))}</pre>`;
  };
  view.render();
}

function build(host, M, L, W, maxTop) {
  const { width: MW, height: MH } = M.size, g = M.grids;
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(host.clientWidth, host.clientHeight);
  renderer.localClippingEnabled = true;
  host.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1114);
  const camera = new THREE.PerspectiveCamera(45, host.clientWidth / host.clientHeight, 0.5, 2000);
  const controls = new OrbitControls(camera, renderer.domElement);
  scene.add(new THREE.HemisphereLight(0xdde8ff, 0x3a3020, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4);
  sun.position.set(-60, 120, 40);
  scene.add(sun);
  const clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e6);
  const mat = (opts) => new THREE.MeshLambertMaterial({ clippingPlanes: [clip], ...opts });
  const box = new THREE.BoxGeometry(1, 1, 1);
  const groups = Object.fromEntries(LAYERS.map(([k]) => [k, new THREE.Group()]));
  Object.values(groups).forEach((gr) => scene.add(gr));
  const m4 = new THREE.Matrix4(), col = new THREE.Color();
  const put = (mesh, i, x, y, z0, z1, sx = 1, sy = 1) => {
    m4.makeScale(sx, Math.max(0.02, z1 - z0), sy).setPosition(x + sx / 2, (z0 + z1) / 2, -(y + sy / 2));
    mesh.setMatrixAt(i, m4);
  };

  // terrain: solid ground per tile. A layered column (cave or overhang) is ground up to its lowest standing level,
  // then rock from each level's headroom up to the next level, so the space in between stays open.
  const layered = new Map((L.layered || []).map((c) => [c.y * MW + c.x, c.levels]));
  const segs = [], voids = [];
  for (let y = 0; y < MH; y++) for (let x = 0; x < MW; x++) {
    const t = dec(g.top[y][x]);
    if (t < 0) continue;
    const lv = layered.get(y * MW + x);
    if (!lv) { segs.push([x, y, -1, t]); continue; }
    segs.push([x, y, -1, lv[0][0]]);
    for (let i = 0; i < lv.length - 1; i++) {
      if (lv[i][1] === -1) continue;
      voids.push([x, y, lv[i][0], lv[i][0] + lv[i][1]]);
      segs.push([x, y, lv[i][0] + lv[i][1], lv[i + 1][0]]);
    }
  }
  const terrain = new THREE.InstancedMesh(box, mat({}), segs.length);
  segs.forEach(([x, y, z0, z1], i) => {
    const m = g.moist[y][x];
    put(terrain, i, x, y, z0, z1);
    const v = 0.25 + 0.55 * (z1 / maxTop);
    col.setRGB(v * (m === "#" ? 0.75 : m === "x" ? 1.0 : 1.0), v * (m === "#" ? 1.05 : m === "x" ? 0.6 : 0.95), v * (m === "x" ? 0.9 : 0.75));
    terrain.setColorAt(i, col);
  });
  terrain.userData.tiles = segs;
  groups.terrain.add(terrain);

  // caves and overhangs: the open space under the rock, drawn through the ground (no depth test) so the tunnels
  // show from above; "cut above z" opens the rock itself. Deeper voids are darker.
  if (voids.length) {
    const caves = new THREE.InstancedMesh(box, new THREE.MeshBasicMaterial({ clippingPlanes: [clip], transparent: true,
      opacity: 0.55, depthTest: false, depthWrite: false }), voids.length);
    caves.renderOrder = 10;
    voids.forEach(([x, y, z0, z1], i) => {
      put(caves, i, x + 0.05, y + 0.05, z0 + 0.05, z1 - 0.05, 0.9, 0.9);
      const v = 0.45 + 0.55 * (z0 / Math.max(1, maxTop));
      caves.setColorAt(i, col.setRGB(1.0 * v, 0.55 * v, 0.15 * v));
    });
    groups.caves.add(caves);
  }
  // cave clusters (voids touching side by side), biggest first, for the "go to caves" button
  const caveBoxes = [], seen = new Set(), at = new Map();
  voids.forEach((v) => at.set(v[1] * MW + v[0], [...(at.get(v[1] * MW + v[0]) || []), v]));
  for (const k of at.keys()) {
    if (seen.has(k)) continue;
    const b = [1e9, 1e9, 1e9, -1e9, -1e9, -1e9], todo = [k];
    let n = 0;
    seen.add(k);
    while (todo.length) {
      const c = todo.pop(), x = c % MW, y = (c - x) / MW;
      for (const [, , z0, z1] of at.get(c)) { b[2] = Math.min(b[2], z0); b[5] = Math.max(b[5], z1); }
      b[0] = Math.min(b[0], x); b[1] = Math.min(b[1], y); b[3] = Math.max(b[3], x + 1); b[4] = Math.max(b[4], y + 1); n++;
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const nx = x + dx, ny = y + dy, nk = ny * MW + nx;
        if (nx >= 0 && nx < MW && ny >= 0 && ny < MH && at.has(nk) && !seen.has(nk)) { seen.add(nk); todo.push(nk); }
      }
    }
    caveBoxes.push([n, b]);
  }
  caveBoxes.sort((a, b) => b[0] - a[0]);

  // water: surface tiles plus cave water from the layered columns
  const wet = [];
  for (let y = 0; y < MH; y++) for (let x = 0; x < MW; x++) {
    const w = g.water[y][x];
    if (w === " ") continue;
    const d = dec(w) / 10, t = dec(g.top[y][x]), bad = g.contamination[y][x] === " " ? 0 : dec(g.contamination[y][x]) / 9;
    if (d > 0.04) wet.push([x, y, t, t + d, bad]);
  }
  for (const c of L.layered || []) for (const [z, , d, , dirt] of c.levels.slice(0, -1)) if (d > 0.05) wet.push([c.x, c.y, z, z + d, dirt || 0]);
  const water = new THREE.InstancedMesh(box, mat({ transparent: true, opacity: 0.6, depthWrite: false }), Math.max(1, wet.length));
  wet.forEach(([x, y, z0, z1, bad], i) => {
    put(water, i, x, y, z0, z1);
    water.setColorAt(i, col.setRGB(0.2 + 0.7 * bad, 0.45 - 0.2 * bad, 0.95 - 0.45 * bad));
  });
  groups.water.add(water);

  // buildings: a box over each footprint at its level and blueprint height
  const blds = M.buildings.filter((b) => b.tiles.length);
  const bm = new THREE.InstancedMesh(box, mat({}), Math.max(1, blds.length));
  blds.forEach((b, i) => {
    const xs = b.tiles.map((t) => t[0]), ys = b.tiles.map((t) => t[1]);
    const x0 = Math.min(...xs), y0 = Math.min(...ys), sx = Math.max(...xs) - x0 + 1, sy = Math.max(...ys) - y0 + 1;
    const h = Math.min(4, b.height || 1) * (["Path", "Platform", "Dam", "Levee", "PowerShaft"].includes(b.name) ? 0.3 : 0.9);
    m4.makeScale(sx - 0.1, h, sy - 0.1).setPosition(x0 + sx / 2, b.z + h / 2, -(y0 + sy / 2));
    bm.setMatrixAt(i, m4);
    bm.setColorAt(i, col.set(!b.finished ? 0xffa030 : b.paused ? 0x7a7a90 : b.name === "Dam" || b.name === "Levee" ? 0xb08050 : 0xd8dce6));
  });
  groups.buildings.add(bm);

  // water plans: proposal lines (red), the pool they hold (cyan slab at the held level)
  const slab = (tiles, level, color, opacity, group) => {
    if (!tiles?.length) return;
    const mesh = new THREE.InstancedMesh(box, mat({ color, transparent: true, opacity, depthWrite: false }), tiles.length);
    tiles.forEach(([x, y], i) => put(mesh, i, x, y, dec(g.top[y][x]), level));
    group.add(mesh);
  };
  const line = (tiles, level, color, group) => {
    if (!tiles?.length) return;
    const mesh = new THREE.InstancedMesh(box, mat({ color }), tiles.length);
    tiles.forEach(([x, y], i) => put(mesh, i, x, y, dec(g.top[y][x]), level + 0.05));
    group.add(mesh);
  };
  if (W) {
    W.dams.proposals.slice(0, 4).forEach((p, i) => { line(p.line, p.level, 0xff3b3b, groups.dams); if (i === 0) slab(p.region, p.level, 0x66e0ff, 0.35, groups.dams); });
    W.pools.filter((p) => p.full).forEach((p) => slab(p.region, p.level, 0x4f9dff, 0.35, groups.pools));
    W.reservoirs.forEach((r) => slab(r.cells, r.level, 0x7af0c0, 0.3, groups.reservoirs));
    W.decks.forEach((d) => {
      const t = [];
      for (let y = d.bbox[1]; y <= d.bbox[3]; y++) for (let x = d.bbox[0]; x <= d.bbox[2]; x++) t.push([x, y]);
      slab(t, d.deckZ, 0x5fd38d, 0.6, groups.decks);
    });
  }

  const render = () => renderer.render(scene, camera);
  const home = () => {
    camera.position.set(MW * 0.5, maxTop + MW * 0.75, MH * 0.35);
    controls.target.set(MW / 2, maxTop / 2, -MH / 2);
    controls.update();
    render();
  };
  const focus = ([x0, y0, z0, x1, y1, z1]) => {     // frame a box (game x, y, z) from the south-east, above
    const r = Math.max(8, x1 - x0, y1 - y0, z1 - z0);
    controls.target.set((x0 + x1) / 2, (z0 + z1) / 2, -(y0 + y1) / 2);
    camera.position.set((x0 + x1) / 2 + r * 1.1, z1 + r * 1.4, -(y0 + y1) / 2 + r * 1.6);
    controls.update();
    render();
  };
  controls.addEventListener("change", render);
  home();

  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  let down = null;
  renderer.domElement.addEventListener("pointerdown", (e) => (down = [e.clientX, e.clientY]));
  renderer.domElement.addEventListener("pointerup", (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObject(terrain).find((h) => h.point.y <= clip.constant + 0.01);
    if (hit && api.onpick) api.onpick(...terrain.userData.tiles[hit.instanceId].slice(0, 2));
  });
  const onResize = () => { renderer.setSize(host.clientWidth, host.clientHeight); camera.aspect = host.clientWidth / host.clientHeight; camera.updateProjectionMatrix(); render(); };
  window.addEventListener("resize", onResize);
  const api = {
    groups, render, home, focus, caves: caveBoxes.map(([n, b]) => ({ tiles: n, box: b })),
    cut: (z) => { clip.constant = Number.isFinite(z) ? z + 0.001 : 1e6; render(); },
    set onpick(fn) { api._pick = fn; }, get onpick() { return api._pick; },
    dispose: () => { window.removeEventListener("resize", onResize); controls.dispose(); renderer.dispose(); renderer.domElement.remove(); },
  };
  return api;
}
