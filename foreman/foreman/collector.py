"""Collector: polls the bridge in tiers (read-only) and keeps the latest state plus a history in the store.

Tiers:
  fast   (5 s)   colony, goods, needs, new alerts, overlay state file, pending requests
  medium (30 s)  buildings, batch progress of long-cycle makers
  slow   (3 min) full map columns (terrain, water, moisture, objects), water sources, plant growth per block
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from . import bridge
from .store import Store

ROOT = Path(__file__).resolve().parents[2]
OVERLAY_STATE = ROOT / "overlay" / "state.json"
POLL_COUNTS = ROOT / "overlay" / "poll_counts.json"
PENDING = ROOT / "harness" / "pending.txt"

TIERS = {"fast": 5, "medium": 30, "slow": 180}
BATCH_MAKERS = ("HydroponicGarden", "OilPress", "Fermenter", "CoffeeBrewery")
CHUNK = 64
PLANT_BLOCK = 32      # /api/map/plants allows 4096 tiles per call; 32x32 blocks also say where dead trees are
OVERLAY_URL = "http://127.0.0.1:8096/colony.json"


def base(template: str) -> str:
    return template.split(".")[0]


def game_day(colony: dict) -> float:
    tm = colony["time"]
    return tm["cycle"] * 100 + tm["cycleDay"] + tm.get("dayProgress", 0)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def collect_fast(store: Store, colony: dict | None = None) -> dict:
    colony = colony or bridge.colony()
    day = game_day(colony)
    goods = bridge.goods(include_empty=True)
    needs = bridge.needs()
    # Alert sequence numbers restart with every bridge load; a lower "latest" means a new load.
    since = store.get("alert_seq", 0)
    new = bridge.alerts(since)
    if new.get("latest", 0) < since:
        new = bridge.alerts(0)
    alerts = new.get("alerts", [])
    store.add_alerts(alerts)
    store.set("alert_seq", new.get("latest", 0))
    overlay = _read_json(OVERLAY_STATE) or {}
    # Only the parts Foreman needs: thought times, plan items, poll meta. Never chat text (there is none here).
    overlay = {"thoughts": [{"at": t.get("at"), "text": t.get("text")} for t in (overlay.get("thoughts") or [])[-3:]],
               "todos": overlay.get("todos") or [], "poll": overlay.get("poll")}
    counts = _read_json(POLL_COUNTS) or {}
    pending = [ln.strip() for ln in PENDING.read_text(encoding="utf-8").splitlines() if ln.strip()] \
        if PENDING.exists() else []
    out = {"colony": colony, "goods": goods, "needs": needs.get("needs", needs), "overlay": overlay,
           "poll_counts": {k: counts.get(k) for k in ("id", "status", "counts")}, "pending": pending,
           "new_alerts": alerts}
    for kind in ("colony", "goods", "needs"):
        store.put_snapshot(kind, out[kind], day)
    return out


MEDIUM_VIEWS = ("production", "power", "sites", "stock", "hours")
SLOW_VIEWS = ("range", "marks", "beavers", "reach")


def _view(name: str):
    try:
        return bridge.foreman_view(name)
    except bridge.BridgeError:
        return None     # an older bridge without ForemanModule: monitors fall back or skip


def collect_medium(store: Store, day: float | None = None) -> dict:
    buildings = bridge.buildings()
    out = {"buildings": buildings}
    for v in MEDIUM_VIEWS:
        out[v] = _view(v)
    if out["production"] is not None:
        names = {b["id"]: base(b["template"]) for b in buildings}
        batches = {p["id"]: {"recipe": p["recipe"], "progress": p["progress"], "inputs_ok": p["ingredients"],
                             "stock": sorted((p.get("stock") or {}).items())}
                   for p in out["production"] if names.get(p["id"]) in BATCH_MAKERS}
    else:   # older bridge: one inspect per batch maker
        batches = {}
        for b in buildings:
            if b["finished"] and base(b["template"]) in BATCH_MAKERS:
                comps = bridge.inspect(b["id"]).get("components", [])
                m = next((c.get("state", {}) for c in comps if c.get("component") == "Manufactory"), {})
                inv = next((c.get("stock", []) for c in comps
                            if c.get("component") == "Inventory" and c.get("name") == "Manufactory"), [])
                batches[b["id"]] = {"recipe": m.get("CurrentRecipe"), "progress": m.get("ProductionProgress", 0),
                                    "inputs_ok": bool(m.get("HasAllIngredients")),
                                    "stock": [(i["good"], i["amount"]) for i in inv]}
    out["batches"] = batches
    for k, v in out.items():
        store.put_snapshot(k, v, day)
    out["health"] = health()
    return out


def health() -> dict:
    """Stream plumbing the AI depends on: overlay server and OBS process (read-only checks)."""
    import httpx
    try:
        overlay = httpx.get(OVERLAY_URL, timeout=0.5).status_code == 200
    except httpx.HTTPError:
        overlay = False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"], capture_output=True, text=True,
                             timeout=3).stdout
        obs = "obs64.exe" in out
    except (OSError, subprocess.SubprocessError):
        obs = None
    return {"overlay": overlay, "obs": obs, "at": time.time()}


def collect_slow(store: Store, day: float | None = None, plants: bool = True) -> dict:
    size = bridge.map_size()
    w, h = size["width"], size["height"]
    rows = {k: [""] * h for k in ("top", "water", "contamination", "flow", "speed", "moist", "objects")}
    legend: dict[str, str] = {}
    features, layered, seen = [], [], set()
    for cy in range(0, h, CHUNK):
        for cx in range(0, w, CHUNK):
            cw, ch = min(CHUNK, w - cx), min(CHUNK, h - cy)
            r = bridge.map_columns(cx, cy, cw, ch)
            # Object chars are per call; re-key them into one global legend.
            remap = {}
            for char, name in r["legend"].items():
                if name not in legend.values():
                    legend[_next_symbol(legend)] = name
                remap[char] = next(k for k, v in legend.items() if v == name)
            for j in range(ch):
                for key in rows:
                    line = r[key][j]
                    if key == "objects":
                        line = "".join(remap.get(c, c) for c in line)
                    rows[key][cy + j] += line
            for f in r["features"]:
                k = (f["name"], f["x"], f["y"], f["z"])
                if k not in seen:
                    seen.add(k)
                    features.append(f)
            layered.extend(r.get("layered") or [])
    try:
        sources = bridge.water_sources()
    except bridge.BridgeError:
        sources = None
    out = {"size": size, **rows, "legend": legend, "features": features, "layered": layered, "sources": sources}
    store.put_snapshot("map", out, day)
    result = {"map": out, "plants": collect_plants(store, day, size) if plants else None}
    for v in SLOW_VIEWS:
        result[v] = _view(v)
        store.put_snapshot(v, result[v], day)
    try:
        result["blueprints"] = bridge.blueprints()
        store.put_snapshot("blueprints", result["blueprints"], day)
    except bridge.BridgeError:
        result["blueprints"] = None
    return result


def collect_plants(store: Store, day: float | None = None, size: dict | None = None) -> list[dict] | None:
    """The plant summary: the slowest read (about 14 s on a 256x256 map), so after a new game it runs on the
    pass after the first one and the first briefing is not held up."""
    size = size or bridge.map_size()
    plants = plant_blocks(size["width"], size["height"])
    store.put_snapshot("plants", plants, day)
    return plants


def plant_blocks(w: int, h: int) -> list[dict] | None:
    """Plant growth summary (grown, growing, dying, dead, ripe) per 32x32 block."""
    out = []
    try:
        for y in range(0, h, PLANT_BLOCK):
            for x in range(0, w, PLANT_BLOCK):
                bw, bh = min(PLANT_BLOCK, w - x), min(PLANT_BLOCK, h - y)
                out.append({"x": x, "y": y, "w": bw, "h": bh, "plants": bridge.plants(x, y, bw, bh)})
    except bridge.BridgeError:
        return None
    return out


def _next_symbol(legend: dict) -> str:
    symbols = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#@$%&*+=?!<>^~"
    for s in symbols:
        if s not in legend:
            return s
    return "?"


def new_game(store: Store, colony: dict) -> bool:
    """A different game is loaded (its District Centre moved): clear the store, the masterplan and the paused
    register so nothing from the old map leaks in. The harness ledger is the old game's too, so skip importing it."""
    from . import masterplan, paused
    key = masterplan.dc_pos(colony)
    old = store.get("game_key")
    if old is None:                              # a store from before game keys: use its last colony snapshot
        last = store.latest("colony")
        old = masterplan.dc_pos(last[1]) if last else None
    if key is None or old == key:
        return False
    store.set("game_key", key)
    if old is None:
        return False                             # first collection for this store: nothing to clear
    store.reset()
    store.set("game_key", key)
    store.set("ledger_imported", True)
    masterplan.forget()
    if paused.PATH.exists():
        paused.PATH.replace(paused.PATH.with_name("paused.prev.json"))
    return True


def collect(store: Store, tiers=("fast", "medium", "slow"), map_max_age: float = TIERS["slow"],
            defer_plants: bool = False) -> dict:
    """One pass over the requested tiers. The slow tier reuses the stored map if it is fresh enough.
    A new game is detected on the fast tier; then every tier is read at once and the plant summary waits for
    the next pass (`plants_deferred`), so the first briefing comes quickly."""
    from .engine import import_harness_ledger
    state: dict[str, Any] = {"collected_at": time.time()}
    colony = bridge.colony()
    if new_game(store, colony):
        print("collector: new game detected, store and masterplan cleared", flush=True)
        tiers, map_max_age, state["new_game"], defer_plants = ("fast", "medium", "slow"), 0, True, True
    state.update(collect_fast(store, colony))
    day = game_day(state["colony"])
    state["game_day"] = day
    import_harness_ledger(store, day)
    if "medium" in tiers:
        state.update(collect_medium(store, day))
    else:
        for k, empty in (("buildings", []), ("batches", {})) + tuple((v, None) for v in MEDIUM_VIEWS):
            last = store.latest(k)
            state[k] = last[1] if last else empty
    cached = store.latest("map")
    if "slow" in tiers and (not cached or time.time() - cached[0] > map_max_age):
        state.update(collect_slow(store, day, plants=not defer_plants))
        state["map_age"] = 0.0
        if defer_plants:
            state["plants_deferred"] = True
    else:
        state["map"] = cached[1] if cached else None
        state["map_age"] = time.time() - cached[0] if cached else None
        for k in SLOW_VIEWS + ("blueprints", "plants"):
            last = store.latest(k)
            state[k] = last[1] if last else None
    return state


FORCE: set = set()     # tiers to read on the next pass, whatever their period (verify wants fresh buildings)
TIER_AT: dict = {}     # tier -> start time of its last pass


def run(store: Store, on_state=None, stop=lambda: False) -> None:
    """Long-running loop: each tier on its own period; calls on_state(state) after every fast pass."""
    last = {k: 0.0 for k in TIERS}
    plants_due = False
    while not stop():
        now = time.time()
        due = tuple(k for k, period in TIERS.items() if now - last[k] >= period or k in FORCE)
        FORCE.difference_update(due)
        try:
            if plants_due:                       # the plant summary held back from the first pass
                collect_plants(store, store.latest("colony") and game_day(store.latest("colony")[1]))
                plants_due = False
            state = collect(store, tiers=due, map_max_age=0 if "slow" in due else float("inf"),
                            defer_plants=last["slow"] == 0.0)
            plants_due = bool(state.get("plants_deferred"))
            for k in due:
                last[k] = now
            if on_state:
                on_state(state)
            TIER_AT.update({k: now for k in due})   # after on_state, so the analysis already holds this pass
            pause = TIERS["fast"]
        except bridge.BridgeError as e:          # game closed or loading: look again soon
            print("collector:", e)
            pause = 1.0
        time.sleep(max(0.2 if plants_due else 0.5, pause - (time.time() - now)))
