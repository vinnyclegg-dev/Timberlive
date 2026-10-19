// TimberLive app window. Talks to Python through window.pywebview.api (see timberlive_app/api.py).
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let api = null;
let state = null;

function toast(msg, ok = true) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show " + (ok ? "ok" : "bad");
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.className = ""), 5000);
}

async function act(name, ...args) {
  try {
    const r = await api[name](...args);
    if (r && r.message) toast(r.message, r.ok !== false);
    await refresh();
    return r;
  } catch (e) {
    toast(String(e), false);
  }
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

// ---- navigation --------------------------------------------------------------------------------------------
function show(page) {
  $$("nav a").forEach((a) => a.classList.toggle("on", a.dataset.page === page));
  $$(".page").forEach((p) => p.classList.toggle("on", p.id === page));
  if (page === "advisor") loadAdvisor();
  if (page === "stream") loadOverlay();
  if (page === "help") loadLog();
}
$$("nav a").forEach((a) => a.addEventListener("click", () => show(a.dataset.page)));

// ---- home ----------------------------------------------------------------------------------------------------
function svc(key) {
  return (state?.services || []).find((s) => s.key === key) || { state: "stopped" };
}
const UP = (s) => s.state === "running" || s.state === "external";

function renderSteps() {
  const g = state.game, m = state.mod, b = state.bridge, cc = state.claude_code, cd = state.claude_desktop;
  const aiDone = cc.configured || cd.configured;
  const steps = [
    {
      done: g.found, title: "Timberborn",
      text: g.found ? `Found at ${g.path}` : "Not found. Install Timberborn on Steam.",
      btn: g.found ? null : ["Open Steam store", () => api.open_url("https://store.steampowered.com/app/1062090/Timberborn/")],
    },
    {
      done: m.up_to_date || (!m.bundled && m.installed), warn: m.bundled && m.installed && !m.up_to_date,
      title: "TimberLive Bridge mod",
      text: m.up_to_date ? `Installed (v${m.installed_version})`
        : !m.bundled ? (m.installed ? `Installed (v${m.installed_version}); this copy of the app has no bundled mod.`
          : "Not installed, and this copy of the app has no bundled mod (build it with packaging/build.py).")
        : m.installed ? "Installed, but differs from this app's copy: update it." : "Not installed yet.",
      btn: m.bundled && !m.up_to_date ? [m.installed ? "Update mod" : "Install mod", () => act("install_mod")] : null,
    },
    {
      done: b.connected, title: "Game running with the mod",
      text: b.connected ? "The bridge is answering." :
        "Start Timberborn, enable TimberLive Bridge in the Mod manager, then load or start a game.",
      btn: b.connected || !g.found ? null : ["Launch Timberborn", () => act("launch_game")],
    },
    {
      done: aiDone, title: "Connect your AI",
      text: aiDone ? [cc.configured && "Claude Code workspace ready", cd.configured && "Claude Desktop added"]
        .filter(Boolean).join(" · ") : "Give Claude (or another AI) the game tools.",
      btn: ["Connect", () => show("connect")],
    },
  ];
  $("#steps").innerHTML = "";
  for (const s of steps) {
    const li = document.createElement("li");
    li.className = s.done ? "done" : s.warn ? "warn" : "";
    li.innerHTML = `<div class="txt"><b>${esc(s.title)}</b><span>${esc(s.text)}</span></div>`;
    if (s.btn) {
      const bt = document.createElement("button");
      bt.textContent = s.btn[0];
      bt.onclick = s.btn[1];
      if (!s.done) bt.className = "primary";
      li.appendChild(bt);
    }
    $("#steps").appendChild(li);
  }
}

const SVC_TEXT = {
  running: ["running", "ok"], external: ["running (started elsewhere)", "ok"], starting: ["starting", "warn"],
  crashed: ["stopped unexpectedly", "bad"], stopped: ["stopped", ""],
};
const SVC_ABOUT = {
  foreman: "Watches the game and checks rules for your AI.",
  overlay: "Thoughts, plan and ticker for OBS.",
  polls: "Counts viewer votes from YouTube chat.",
};

function renderServices() {
  $("#services").innerHTML = "";
  for (const s of state.services) {
    const [label, cls] = SVC_TEXT[s.state] || [s.state, ""];
    const div = document.createElement("div");
    div.className = "card svc";
    div.innerHTML = `<i class="dot ${cls === "ok" ? "ok" : cls === "bad" ? "bad" : cls === "warn" ? "warn" : ""}"></i>
      <div class="name"><b>${esc(s.title)}</b><span>${esc(SVC_ABOUT[s.key] || "")}</span>
      <span class="pill ${cls}">${esc(label)}</span>${s.error ? ` <span class="pill bad">${esc(s.error)}</span>` : ""}</div>`;
    const bt = document.createElement("button");
    if (s.state === "running" || s.state === "starting") {
      bt.textContent = "Stop";
      bt.onclick = () => act("stop_service", s.key);
    } else if (s.state !== "external") {
      bt.textContent = "Start";
      bt.onclick = () => act("start_service", s.key);
    } else {
      bt.disabled = true;
      bt.textContent = "Running";
    }
    div.appendChild(bt);
    $("#services").appendChild(div);
  }
}

function renderSide() {
  const dot = (id, ok) => ($(id).className = "dot " + (ok ? "ok" : ""));
  dot("#dot-bridge", state.bridge.connected);
  dot("#dot-foreman", UP(svc("foreman")));
  dot("#dot-overlay", UP(svc("overlay")));
}

// ---- connect -------------------------------------------------------------------------------------------------
function pill(el, ok, yes, no) {
  el.textContent = ok ? yes : no;
  el.className = "pill " + (ok ? "ok" : "");
}

function renderConnect() {
  const cc = state.claude_code, cd = state.claude_desktop;
  pill($("#cc-state"), cc.configured, "set up", "not set up");
  pill($("#cd-state"), cd.configured, "added", cd.installed ? "not added" : "not installed");
  $("#cc-ws").textContent = cc.workspace;
  $("#cd-cfg").textContent = cd.config;
}

// ---- stream --------------------------------------------------------------------------------------------------
let streamFilled = false;
function renderStream() {
  const s = state.stream;
  $("#overlay-url").textContent = s.overlay_url;
  pill($("#obs-state"), s.obs_installed, "installed", "not installed");
  pill($("#yt-state"), s.youtube_key_set, "key saved", "not set up");
  if (!streamFilled) {
    $("#obs-collection").value = s.obs_collection;
    $("#obs-profile").value = s.obs_profile;
    $("#yt-channel").value = s.youtube_channel_id;
    $("#yt-video").value = s.youtube_video_id;
    streamFilled = true;
  }
}

function loadOverlay() {
  const f = $("#overlay-frame");
  const box = f.parentElement;
  f.style.transform = `scale(${box.clientWidth / 1920})`;
  if (UP(svc("overlay")) && !f.src) f.src = "http://127.0.0.1:8096/";
}
window.addEventListener("resize", () => $("#stream").classList.contains("on") && loadOverlay());

// ---- advisor -------------------------------------------------------------------------------------------------
function loadAdvisor() {
  const up = UP(svc("foreman"));
  $("#advisor-down").classList.toggle("hidden", up);
  $("#advisor-frame").classList.toggle("hidden", !up);
  if (up && !$("#advisor-frame").src) $("#advisor-frame").src = "http://127.0.0.1:8097/";
}

// ---- help ----------------------------------------------------------------------------------------------------
async function loadLog() {
  $("#log").textContent = await api.service_log($("#log-pick").value, 80);
}
$("#log-pick").addEventListener("change", loadLog);

// ---- wiring --------------------------------------------------------------------------------------------------
document.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.start) act("start_service", b.dataset.start);
  if (b.dataset.open) act("open_path", b.dataset.open);
  const a = b.dataset.act;
  if (!a) return;
  if (a === "save_obs") act(a, $("#obs-collection").value, $("#obs-profile").value);
  else if (a === "save_youtube") {
    act(a, $("#yt-key").value, $("#yt-channel").value, $("#yt-video").value);
    $("#yt-key").value = "";
  } else act(a);
});

function copy(text) {
  navigator.clipboard.writeText(text).then(() => toast("Copied"), () => toast("Couldn't copy", false));
}
$("#copy-snippet").onclick = () => copy($("#snippet").textContent);
$("#copy-first").onclick = () => copy($("#first-msg").textContent);

$("#lm-run").onclick = () => act("run_local_model", $("#lm-url").value, $("#lm-model").value, $("#lm-live").checked);

async function refresh() {
  state = await api.overview();
  $("#ver").textContent = " v" + state.version;
  renderSteps();
  renderServices();
  renderSide();
  renderConnect();
  renderStream();
  if ($("#advisor").classList.contains("on")) loadAdvisor();
}

window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  $("#snippet").textContent = await api.mcp_snippet();
  await refresh();
  setInterval(refresh, 4000);
});
