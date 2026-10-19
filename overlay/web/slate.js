// Slate text comes only from the URL (set by the streamer in OBS) and from the
// local colony feed. Everything is rendered with textContent.
"use strict";

const PRESETS = {
  soon: ["Stream starting soon", "Claude is waking the beavers up. Grab a snack!"],
  brb: ["Be right back", "The beavers are holding the fort - back in a moment."],
  tech: ["Technical difficulties", "Something went splash. Fixing it now - hang tight!"],
  paused: ["Game paused", "Claude is thinking hard about the next move..."],
  ending: ["Thanks for watching!", "The colony will be here next time. Bye for now!"],
};

const params = new URLSearchParams(location.search);
const preset = PRESETS[params.get("msg")] || PRESETS.brb;
document.getElementById("title").textContent = params.get("title") || preset[0];
document.getElementById("sub").textContent = params.get("sub") || preset[1];

// The "Starting soon" slate never shows a countdown (streamer preference),
// even if an older OBS source still passes &minutes=.
const minutes = params.get("msg") === "soon" ? 0 : parseFloat(params.get("minutes"));
const countdown = document.getElementById("countdown");
if (minutes > 0) {
  const end = Date.now() + minutes * 60000;
  const update = () => {
    const left = Math.max(0, Math.round((end - Date.now()) / 1000));
    countdown.textContent = left > 0
      ? `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`
      : "Any moment now...";
  };
  update();
  setInterval(update, 1000);
}

// A small live line about the colony keeps the slate from feeling dead air.
const colonyLine = document.getElementById("colony");
async function refreshColony() {
  // No colony line on "Starting soon" (streamer preference) or when turned off.
  if (params.get("colony") === "off" || params.get("msg") === "soon") return;
  try {
    const response = await fetch("/colony.json", { cache: "no-store" });
    const c = await response.json();
    colonyLine.textContent = c.ok
      ? `Colony: cycle ${c.cycle}, day ${c.day} · ${c.adults + c.kits} beavers · ${c.water} water · ${c.food} food`
      : "";
  } catch (e) {
    colonyLine.textContent = "";
  }
}
refreshColony();
setInterval(refreshColony, 5000);
