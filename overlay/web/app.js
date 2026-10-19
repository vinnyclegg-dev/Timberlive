// Polls the local overlay server. All text is set with textContent, never as HTML.
"use strict";

const MAX_THOUGHTS = 5;
let lastThoughtsKey = "";
let doneSeen = new Set();

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Make a panel's content fit its fixed height without cutting text. With `keep` set (thoughts), try
// text scales 1, 0.9, 0.8 and at each one drop the oldest items until it fits; stop at the first
// scale that still shows two items, so a long thought shrinks a bit before older ones vanish.
// Without `keep` (plan, poll), only shrink the scale --k, down to 0.6.
function fit(panel, list, keep) {
  const over = () => panel.scrollHeight > panel.clientHeight + 1;
  const items = [...list.children];
  if (keep !== undefined) {
    for (const k of [1, 0.9, 0.8]) {
      panel.style.setProperty("--k", String(k));
      list.replaceChildren(...items);
      while (over() && list.children.length > keep) list.lastElementChild.remove();
      if (list.children.length >= Math.min(2, items.length)) break;
    }
  } else {
    panel.style.setProperty("--k", "1");
  }
  let k = parseFloat(panel.style.getPropertyValue("--k"));
  while (over() && k > 0.6) { k -= 0.05; panel.style.setProperty("--k", k.toFixed(2)); }
}

function ago(seconds) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - seconds));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  return m === 1 ? "1 min ago" : `${m} mins ago`;
}

function renderThoughts(thoughts) {
  const list = document.getElementById("thoughts");
  const recent = thoughts.slice(-MAX_THOUGHTS).reverse();
  const key = recent.map(t => t.at).join(",");
  if (key === lastThoughtsKey) {
    list.querySelectorAll(".when").forEach((node, i) => { node.textContent = ago(recent[i].at); });
    return;
  }
  lastThoughtsKey = key;
  list.replaceChildren(...recent.map(t => {
    const item = el("li", null, t.text);
    item.appendChild(el("span", "when", ago(t.at)));
    return item;
  }));
  fit(document.getElementById("thoughts-panel"), list, 1);
}

function renderTodos(todos) {
  const list = document.getElementById("todos");
  const firstOpen = todos.findIndex(t => !t.done);
  list.replaceChildren(...todos.map((t, i) => {
    const item = el("li", t.done ? "done" : (i === firstOpen ? "active" : ""), t.text);
    if (t.done && !doneSeen.has(t.text)) item.classList.add("just-done");
    return item;
  }));
  doneSeen = new Set(todos.filter(t => t.done).map(t => t.text));
  fit(document.getElementById("todo-panel"), list);
}

function setStat(id, text, level) {
  const node = document.getElementById(id);
  node.textContent = text;
  node.className = "value" + (level ? " " + level : "");
}

function renderColony(c) {
  if (!c.ok) {
    setStat("s-time", "loading...", "warn");
    return;
  }
  // The bridge reports the time scale (1, 3, 7); the game's buttons call these speed 1, 2, 3.
  const button = { 1: 1, 3: 2, 7: 3 }[c.speed];
  const speed = c.speed === 0 ? " (paused)" : button ? ` (speed ${button})` : ` (x${c.speed})`;
  setStat("s-time", `${c.cycle} - day ${c.day}${speed}`);
  const w = c.weather || {};
  if (w.state === "hazardous") {
    setStat("s-weather", `${w.hazard === "BadtideWeather" ? "Badtide" : "Drought"}: ${Math.ceil(w.daysRemaining)}d left`, "bad");
  } else if (w.state === "approaching") {
    setStat("s-weather", `${w.hazard === "BadtideWeather" ? "Badtide" : "Drought"} in ${Math.ceil(w.daysUntil)}d`, "warn");
  } else {
    setStat("s-weather", "Temperate", "good");
  }
  const beavers = c.adults + c.kits;
  setStat("s-pop", `${c.adults} + ${c.kits} kits`, c.homeless > 0 ? "warn" : "");
  const waterDays = beavers ? c.water / (beavers * 2.12) : 99;
  const foodDays = beavers ? c.food / (beavers * 2.67) : 99;
  setStat("s-water", `${c.water} (${waterDays.toFixed(1)}d)`, waterDays < 2 ? "bad" : waterDays < 4 ? "warn" : "good");
  setStat("s-food", `${c.food} (${foodDays.toFixed(1)}d)`, foodDays < 2 ? "bad" : foodDays < 4 ? "warn" : "good");
  setStat("s-logs", String(c.logs) + (c.planks ? ` / ${c.planks} planks` : ""));
  setStat("s-science", String(c.science));
  setStat("s-wellbeing", String(c.wellbeing), c.wellbeing < 0 ? "bad" : "");
}

let pollState = null;
let pollCounts = {};

function renderPoll() {
  const question = document.getElementById("poll-question");
  const list = document.getElementById("poll-options");
  const footer = document.getElementById("poll-footer");
  const p = pollState;
  if (!p || !p.options || !p.options.length) {
    question.textContent = "Viewer poll";
    list.replaceChildren();
    footer.textContent = "No poll running right now";
    return;
  }
  const counts = pollCounts.id === p.id ? (pollCounts.counts || []) : [];
  const total = counts.reduce((a, b) => a + b, 0);
  const left = Math.max(0, Math.round(p.closes - Date.now() / 1000));
  const open = !p.closed && left > 0;
  const best = Math.max(0, ...counts);
  question.textContent = p.question;
  list.replaceChildren(...p.options.map((text, i) => {
    const n = counts[i] || 0;
    const item = el("li", !open && total && n === best ? "winner" : "");
    const bar = el("span", "bar");
    bar.style.width = total ? `${Math.round(100 * n / total)}%` : "0%";
    item.append(bar, el("span", "num", String(i + 1)), el("span", "opt", text), el("span", "count", String(n)));
    return item;
  }));
  if (open) {
    const nums = p.options.map((_, i) => i + 1).join(", ").replace(/, (\d)$/, " or $1");
    footer.textContent = `Type ${nums} in chat - ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")} left`;
  } else {
    footer.textContent = total ? `Poll closed - ${total} vote${total === 1 ? "" : "s"}` : "Poll closed - no votes";
  }
  fit(document.getElementById("chat-slot"), list);
}

// Ticker over the game's bottom toolbar. One line at a time scrolls in from the right and out to
// the left; the band hides when there is nothing to say. Only these can ever appear: the fixed
// lines below, Claude's announce() texts, poll voting reminders, and a welcome built from a
// new-chatter COUNT (the server only accepts a number, so no names or chat text).
const TICKER_SPEED = 130;    // px per second
const ANNOUNCE_GAP = 60;     // s between repeats of one announcement
const ANNOUNCE_FOR = 600;    // s an announcement stays queued
const POLL_EVERY = 45;       // s between voting reminders while a poll is open
const FIXED_EVERY = 180;     // s between fixed lines
const FIXED_LINES = [   // first person: the ticker speaks as me, never "Claude" or "the AI"
  "Hi, I'm an AI playing Timberborn live, and every move you see is my own decision.",
  "Season 2! This is my brand new Iron Teeth colony, \"Artificial Timbelligence\", on the Waterfalls map. My goal: survive every drought and badtide and build one of everything.",
  "The panels on the right show what I'm thinking and my current plan.",
  "You can help pick what I do next: when a poll opens, type its number in chat to vote.",
];
let tickerItems = [];
let welcome = {};
let welcomeShown = null;
let tickerBusy = false;
let lastPollLine = 0;
let lastFixed = Date.now() / 1000 - FIXED_EVERY + 30;   // first fixed line 30 s after load
let fixedIndex = 0;
const announceShown = new Map();   // announcement time -> {n, last}

function nextTickerLine(now) {
  for (const a of tickerItems) {
    const seen = announceShown.get(a.at) || { n: 0, last: 0 };
    if (now - a.at < ANNOUNCE_FOR && seen.n < (a.repeat || 1) && now - seen.last > ANNOUNCE_GAP) {
      announceShown.set(a.at, { n: seen.n + 1, last: now });
      return a.text;
    }
  }
  if (welcome.id && welcome.id !== welcomeShown && now - welcome.at < 300 && Number.isInteger(welcome.n)) {
    welcomeShown = welcome.id;
    return welcome.n === 1 ? "Welcome to the new person in chat! 👋" : `Welcome to the ${welcome.n} new people in chat! 👋`;
  }
  const p = pollState;
  if (p && p.options && !p.closed && p.closes > now && now - lastPollLine > POLL_EVERY) {
    lastPollLine = now;
    const choices = p.options.map((o, i) => `${i + 1} for ${o}`).join(", ").replace(/, ([^,]*)$/, " or $1");
    const mins = Math.max(1, Math.round((p.closes - now) / 60));
    return `Poll: ${p.question} Type ${choices} in chat to vote (${mins} min left).`;
  }
  if (now - lastFixed > FIXED_EVERY) {
    lastFixed = now;
    return FIXED_LINES[fixedIndex++ % FIXED_LINES.length];
  }
  return null;
}

function runTicker() {
  if (tickerBusy) return;
  const band = document.getElementById("ticker");
  const text = nextTickerLine(Date.now() / 1000);
  if (!text) { band.classList.remove("on"); return; }
  tickerBusy = true;
  band.classList.add("on");
  const line = document.getElementById("ticker-text");
  line.textContent = text;
  const from = band.clientWidth, to = -line.offsetWidth;
  const run = line.animate([{ transform: `translateX(${from}px)` }, { transform: `translateX(${to}px)` }],
                           { duration: 1000 * (from - to) / TICKER_SPEED, easing: "linear" });
  run.onfinish = () => { line.textContent = ""; tickerBusy = false; runTicker(); };
}

async function poll(url, render) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (response.ok) render(await response.json());
  } catch (e) {
    // Server restarting; try again next tick.
  }
}

function tick() {
  poll("/state.json", s => {
    renderThoughts(s.thoughts || []); renderTodos(s.todos || []); pollState = s.poll || null; renderPoll();
    tickerItems = s.ticker || [];
  });
  poll("/welcome.json", w => { welcome = w || {}; });
  poll("/poll_counts.json", c => { pollCounts = c || {}; renderPoll(); });
  poll("/colony.json", renderColony);
  runTicker();
}

tick();
setInterval(tick, 1500);
