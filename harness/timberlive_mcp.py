"""MCP server exposing the TimberLive Bridge mod to Claude as typed game tools.

The bridge (C# mod) listens on 127.0.0.1 only and requires a per-launch token,
which the mod writes to %LOCALAPPDATA%\\TimberLive\\bridge.json. The token is
read from disk on each call and never returned in tool output.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.mcpserver import Image, MCPServer

logging.getLogger("httpx").setLevel(logging.WARNING)

CONNECTION_FILE = Path(os.environ["LOCALAPPDATA"]) / "TimberLive" / "bridge.json"

server = MCPServer(
    name="timberlive",
    instructions=(
        "Tools to observe and play Timberborn through the TimberLive Bridge mod. "
        "Coordinates are (x, y, z) with z = height. Typical loop: pause (set_speed 0), "
        "read get_colony + get_goods, look at view_map / screenshot, act, then unpause."
    ),
)


class BridgeError(Exception):
    pass


def _connection() -> tuple[str, str]:
    try:
        data = json.loads(CONNECTION_FILE.read_text())
    except FileNotFoundError as e:
        raise BridgeError("Bridge not running: start Timberborn with the TimberLive Bridge mod enabled") from e
    return f"http://127.0.0.1:{data['port']}", data["token"]


def _call(method: str, path: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None,
          raw: bool = False) -> Any:
    base, token = _connection()
    try:
        response = httpx.request(method, base + path, params=params, json=body,
                                 headers={"X-TimberLive-Token": token}, timeout=30)
    except httpx.HTTPError as e:
        raise BridgeError(f"Bridge unreachable ({e.__class__.__name__}); is the game running?") from e
    if response.status_code != 200:
        try:
            message = response.json().get("error", response.text)
        except ValueError:
            message = response.text
        raise BridgeError(f"{response.status_code}: {message}")
    return response.content if raw else response.json()


def _compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------- session

@server.tool()
def ping() -> str:
    """Check the bridge is up and which scene is loaded (MainMenu or Game)."""
    return _compact(_call("GET", "/api/ping"))


@server.tool()
def list_saves(limit: int = 5) -> str:
    """List settlements and their most recent saves."""
    return _compact(_call("GET", "/api/saves", params={"limit": limit}))


@server.tool()
def load_save(settlement: str = "", save: str = "", most_recent: bool = False) -> str:
    """Load a save by settlement + save name, or the most recent save."""
    body = {"mostRecent": True} if most_recent else {"settlement": settlement, "save": save}
    return _compact(_call("POST", "/api/load", body=body))


@server.tool()
def new_game_options() -> str:
    """Factions, maps and difficulty modes available for a new game."""
    return _compact(_call("GET", "/api/new-game/options"))


@server.tool()
def new_game(faction: str, map: str, mode: str = "", settlement_name: str = "") -> str:
    """Start a new game. Use ids from new_game_options."""
    body: dict[str, Any] = {"faction": faction, "map": map}
    if mode:
        body["mode"] = mode
    if settlement_name:
        body["settlementName"] = settlement_name
    return _compact(_call("POST", "/api/new-game", body=body))


@server.tool()
def save_game(name: str = "") -> str:
    """Save the current game (optional save name)."""
    return _compact(_call("POST", "/api/save", body={"name": name} if name else {}))


# ---------------------------------------------------------------- observe

@server.tool()
def get_colony() -> str:
    """Time, speed, weather (as shown in the game's weather panel), population, beds, jobs,
    wellbeing, science points and districts."""
    return _compact(_call("GET", "/api/state"))


@server.tool()
def get_goods(include_empty: bool = False) -> str:
    """Global stock and storage capacity of every good."""
    return _compact(_call("GET", "/api/goods", params={"all": str(include_empty).lower()}))


@server.tool()
def list_blueprints(group: str = "") -> str:
    """Buildings you can place: template id, display name, tool group, footprint [x,y,z],
    cost, science cost and whether unlocked."""
    return _compact(_call("GET", "/api/blueprints", params={"group": group} if group else None))


@server.tool()
def list_buildings(template_filter: str = "") -> str:
    """Existing buildings with id, position, finished/progress, priority, workers, paused."""
    params = {"template": template_filter} if template_filter else None
    return _compact(_call("GET", "/api/buildings", params=params))


@server.tool()
def map_size() -> str:
    """Map width/height and max heights."""
    return _compact(_call("GET", "/api/map/size"))


@server.tool()
def view_map(x: int, y: int, w: int = 32, h: int = 32) -> str:
    """Text grids for an area (max 64x64 tiles): surface heights, water depth/contamination,
    soil moisture (where crops/trees can grow) and surface objects with a legend. Rows go from north (high y) to south."""
    result = _call("GET", "/api/map", params={"x": x, "y": y, "w": w, "h": h})
    lines = [result["note"], "", "HEIGHTS:"] + result["heights"]
    lines += ["", "WATER (" + result["waterKey"] + "):"] + ["|" + r + "|" for r in result["water"]]
    if "moisture" in result:
        lines += ["", "MOISTURE (" + result["moistureKey"] + "):"] + ["|" + r + "|" for r in result["moisture"]]
    lines += ["", "OBJECTS:"] + ["|" + r + "|" for r in result["objects"]]
    lines += ["", "LEGEND: " + _compact(result["legend"])]
    return "\n".join(lines)


@server.tool()
def inspect_tile(x: int, y: int) -> str:
    """Surface height, water and every object stacked on one map column."""
    return _compact(_call("GET", "/api/map/tile", params={"x": x, "y": y}))


@server.tool()
def screenshot(width: int = 1280, mode: str = "auto") -> Image:
    """Screenshot of the game. mode: "screen" = what the player sees incl. UI, "camera" = world
    only (works even if the window is hidden), "auto" = screen with camera fallback."""
    data = _call("GET", "/api/screenshot", params={"width": width, "quality": 75, "mode": mode}, raw=True)
    return Image(data=data, format="jpeg")


# ---------------------------------------------------------------- act

@server.tool()
def set_speed(speed: int) -> str:
    """Set game speed: 0 (pause), 1, 3 or 7."""
    return _compact(_call("POST", "/api/speed", body={"speed": speed}))


@server.tool()
def place_building(template: str, x: int, y: int, z: int, orientation: int = 0, flip: bool = False,
                   check: bool = False) -> str:
    """Place one building/structure at (x, y, z). z = the level it stands on (same as
    view_map heights / inspect_tile surfaceHeight). (x, y) is the footprint's min corner before
    rotation; orientation = clockwise quarter turns 0-3. list_blueprints gives size, entrance
    and waterInput offsets (at orientation 0). Returns placed and rejected spots.
    check=True only tests the spot (like hovering the preview): nothing is placed and the
    camera stays still. Use it when searching for a valid spot."""
    body = {"template": template, "x": x, "y": y, "z": z, "orientation": orientation, "flip": flip,
            "check": check}
    return _compact(_call("POST", "/api/place", body=body))


@server.tool()
def place_line(template: str, x0: int, y0: int, x1: int, y1: int, z: int, orientation: int = 0) -> str:
    """Place a straight horizontal or vertical run (paths, levees, fences...) from (x0,y0) to (x1,y1) at height z."""
    if x0 != x1 and y0 != y1:
        raise BridgeError("place_line needs a straight line (same x or same y)")
    step_x = (x1 > x0) - (x1 < x0)
    step_y = (y1 > y0) - (y1 < y0)
    length = max(abs(x1 - x0), abs(y1 - y0)) + 1
    placements = [{"x": x0 + i * step_x, "y": y0 + i * step_y, "z": z, "orientation": orientation}
                  for i in range(length)]
    return _compact(_call("POST", "/api/place", body={"template": template, "placements": placements}))


@server.tool()
def place_area(template: str, x0: int, y0: int, x1: int, y1: int, z: int) -> str:
    """Fill a rectangle with a 1x1 structure (e.g. farmland, platforms) at height z."""
    placements = [{"x": x, "y": y, "z": z}
                  for x in range(min(x0, x1), max(x0, x1) + 1)
                  for y in range(min(y0, y1), max(y0, y1) + 1)]
    return _compact(_call("POST", "/api/place", body={"template": template, "placements": placements}))


@server.tool()
def set_priority(building_id: str, priority: str) -> str:
    """Set construction (unfinished) or work (finished) priority: VeryLow, Low, Normal, High, VeryHigh."""
    return _compact(_call("POST", "/api/building/priority", body={"id": building_id, "priority": priority}))


@server.tool()
def set_workers(building_id: str, workers: int) -> str:
    """Set the desired number of workers at a workplace."""
    return _compact(_call("POST", "/api/building/workers", body={"id": building_id, "workers": workers}))


@server.tool()
def set_paused(building_id: str, paused: bool) -> str:
    """Pause or resume a building."""
    return _compact(_call("POST", "/api/building/pause", body={"id": building_id, "paused": paused}))


@server.tool()
def list_plantables() -> str:
    """Crops and trees that can be marked for planting, which building plants them, and lock state."""
    return _compact(_call("GET", "/api/plantables"))


@server.tool()
def plant_area(plant: str, x0: int, y0: int, x1: int, y1: int) -> str:
    """Mark a rectangle for planting a crop/tree (e.g. Kohlrabi, Pine). Needs a matching
    planter building (farmhouse/forester) in range to actually get planted."""
    body = {"plant": plant, "x0": x0, "y0": y0, "x1": x1, "y1": y1}
    return _compact(_call("POST", "/api/plant", body=body))


@server.tool()
def clear_planting(x0: int, y0: int, x1: int, y1: int) -> str:
    """Remove planting marks in a rectangle."""
    return _compact(_call("POST", "/api/unplant", body={"x0": x0, "y0": y0, "x1": x1, "y1": y1}))


@server.tool()
def demolish_resources(x0: int, y0: int, x1: int, y1: int, unmark: bool = False) -> str:
    """The toolbar's Demolish resources tool: mark plants (crops, bushes, trees, stumps) in a rectangle
    for builders to remove, e.g. to clear a path route. Marking also clears planting marks there.
    unmark=True is the Cancel tool. Removal takes builder time, like in normal play."""
    body = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "unmark": unmark}
    return _compact(_call("POST", "/api/map/demolish-resources", body=body))


@server.tool()
def mark_tree_cutting(x0: int, y0: int, x1: int, y1: int, remove: bool = False) -> str:
    """Add (or remove) a rectangle to the tree cutting area. Lumberjacks only cut marked trees."""
    body = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "remove": remove}
    return _compact(_call("POST", "/api/cutting-area", body=body))


@server.tool()
def unlock_building(template: str) -> str:
    """Spend science points to unlock a building (template id from list_blueprints)."""
    return _compact(_call("POST", "/api/unlock", body={"template": template}))


@server.tool()
def get_needs() -> str:
    """Beaver needs: average level per need and how many beavers are critical/warning."""
    return _compact(_call("GET", "/api/needs"))


@server.tool()
def get_alerts(since: int = 0) -> str:
    """Game notifications (deaths, shortages, events) with sequence numbers; pass the last seen
    'latest' as since to get only new ones."""
    return _compact(_call("GET", "/api/alerts", params={"since": since}))


@server.tool()
def set_work_hours(hours: float) -> str:
    """Set the colony's working hours per day (1-24)."""
    return _compact(_call("POST", "/api/work-hours", body={"hours": hours}))


@server.tool()
def inspect_building(building_id: str, all: bool = False) -> str:
    """A building's panel: inventory/stock, settings (storage good, recipe, floodgate height,
    automation state) and the actions available for building_action. all=True also lists the
    read-only state of every component (timers, explosion radius, blockers). Ids for natural
    objects (Unstable Core, relics) come from inspect_tile."""
    params = {"id": building_id}
    if all:
        params["all"] = "true"
    return _compact(_call("GET", "/api/building/inspect", params=params))


@server.tool()
def building_action(building_id: str, component: str, action: str, args: list[Any] | None = None) -> str:
    """Run a panel action from inspect_building, e.g. ("SingleGoodAllower","Allow",["Water"]),
    ("Manufactory","SetRecipe",["Planks"]), ("HaulPrioritizable","Prioritized",[true]),
    ("Floodgate","SetHeightAndSynchronize",[1.5]), ("Automatable","SetInput",[transmitter_id]),
    ("DepthSensor","SetThreshold",[0.5])."""
    body = {"id": building_id, "component": component, "action": action, "args": args or []}
    return _compact(_call("POST", "/api/building/act", body=body))


@server.tool()
def list_automation() -> str:
    """All automation transmitters (sensors, levers, relays...) with on/off state, and which
    buildings are automated by which transmitter."""
    return _compact(_call("GET", "/api/automation"))


@server.tool()
def get_camera() -> str:
    """Camera target, zoom, angles and whether it auto-follows actions."""
    return _compact(_call("GET", "/api/camera"))


@server.tool()
def set_camera(x: int | None = None, y: int | None = None, zoom: float | None = None,
               horizontal_angle: float | None = None, vertical_angle: float | None = None,
               follow: bool | None = None, orbit: float | None = None) -> str:
    """Pan the stream camera to (x, y) and/or set zoom/angles. Follow mode (on by default) pans
    automatically to every action; keep it on while streaming. orbit = a slow continuous turn in
    degrees per second (about 3 looks calm; 0 stops it)."""
    body: dict[str, Any] = {}
    for key, value in (("x", x), ("y", y), ("zoom", zoom), ("horizontalAngle", horizontal_angle),
                       ("verticalAngle", vertical_angle), ("follow", follow), ("orbit", orbit)):
        if value is not None:
            body[key] = value
    return _compact(_call("POST", "/api/camera", body=body))


@server.tool()
def working_beavers() -> str:
    """Where employed beavers are doing their job right now: [{x, y, z, workplace}].
    Point the camera at them so viewers see beavers at work."""
    return _compact(_call("GET", "/api/camera/working-beavers"))


@server.tool()
def set_layers(level: int | None = None) -> str:
    """The player's layer slider: hide everything above height `level` to see what is below a
    surface (tunnels, pump intakes, the lower floors of stacked buildings). Only the view changes.
    Call with no level to show all layers again; always reset afterwards."""
    body = {"level": level} if level is not None else {"reset": True}
    return _compact(_call("POST", "/api/camera/layers", body=body))


# ---------------------------------------------------------------- stream overlay

OVERLAY_STATE = Path(__file__).resolve().parent.parent / "overlay" / "state.json"
MAX_THOUGHTS_KEPT = 30


def _overlay_load() -> dict:
    try:
        return json.loads(OVERLAY_STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"thoughts": [], "todos": []}


def _overlay_save(state: dict) -> None:
    OVERLAY_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OVERLAY_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OVERLAY_STATE)


NARRATE_MAX = 400


@server.tool()
def narrate(thought: str) -> str:
    """Show a short, friendly first-person thought on the stream overlay (what I'm noticing,
    deciding or worried about), e.g. "Water's fine, but food is tight - adding a second farm."
    Aim for 1-2 sentences under ~220 characters, plain language, no internal jargon or coordinates spam.
    Up to 400 characters are shown in full (the panel shrinks the text to fit); anything longer is cut
    at a word boundary and the reply says so."""
    import time
    text = " ".join(thought.split())
    note = "shown"
    if len(text) > NARRATE_MAX:
        text = text[:NARRATE_MAX].rsplit(" ", 1)[0].rstrip(",;:-") + "…"
        note = f"shown, but CUT to {NARRATE_MAX} chars: write shorter thoughts"
    elif len(text) > 220:
        note = f"shown in full ({len(text)} chars); aim for under 220"
    state = _overlay_load()
    state["thoughts"] = (state.get("thoughts", []) + [{"text": text, "at": time.time()}])[-MAX_THOUGHTS_KEPT:]
    _overlay_save(state)
    return note


@server.tool()
def set_plan(items: list[str]) -> str:
    """Replace the on-stream to-do list with these items (in order). Existing items with the
    same text keep their done state."""
    state = _overlay_load()
    done = {t["text"] for t in state.get("todos", []) if t.get("done")}
    state["todos"] = [{"text": " ".join(i.split())[:120], "done": " ".join(i.split())[:120] in done} for i in items][:12]
    _overlay_save(state)
    return _compact(state["todos"])


@server.tool()
def add_todo(item: str) -> str:
    """Append one item to the on-stream to-do list."""
    state = _overlay_load()
    state.setdefault("todos", []).append({"text": " ".join(item.split())[:120], "done": False})
    state["todos"] = state["todos"][-12:]
    _overlay_save(state)
    return _compact(state["todos"])


@server.tool()
def check_todo(item: str, done: bool = True) -> str:
    """Tick (or untick) the to-do item whose text contains the given words."""
    state = _overlay_load()
    needle = item.lower()
    for todo in state.get("todos", []):
        if needle in todo["text"].lower():
            todo["done"] = done
            _overlay_save(state)
            return _compact(state["todos"])
    raise BridgeError(f"No to-do matching '{item}'")


POLL_COUNTS = OVERLAY_STATE.parent / "poll_counts.json"


@server.tool()
def start_poll(question: str, options: list[str], minutes: float = 3.0) -> str:
    """Open a viewer poll on the overlay. Viewers vote by typing 1, 2 or 3 in YouTube chat.
    Every option must be something already in my plan that I'm happy to do; chat only
    picks the order. 2-3 short options. Only vote counts ever come back (poll_results)."""
    import time
    options = [" ".join(o.split())[:40] for o in options if o.strip()]
    if not 2 <= len(options) <= 3:
        raise BridgeError("A poll needs 2 or 3 options")
    now = time.time()
    state = _overlay_load()
    state["poll"] = {"id": int(now), "question": " ".join(question.split())[:60], "options": options,
                     "opened": now, "closes": now + max(0.5, min(minutes, 15.0)) * 60, "closed": False}
    _overlay_save(state)
    from pollguard import ensure_service   # the vote counter must run for every poll
    return _compact({**state["poll"], "counter": ensure_service()})


@server.tool()
def poll_results() -> str:
    """Current vote counts for the overlay poll (numbers only - no chat text ever reaches me),
    the leading option, whether it's still open, and the counter service status."""
    import time
    poll = _overlay_load().get("poll")
    if not poll:
        return "No poll"
    try:
        counts = json.loads(POLL_COUNTS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        counts = {}
    numbers = counts.get("counts") if counts.get("id") == poll["id"] else None
    numbers = [int(n) for n in numbers] if numbers else [0] * len(poll["options"])
    best = max(numbers)
    leaders = [poll["options"][i] for i, n in enumerate(numbers) if n == best and best > 0]
    return _compact({
        "question": poll["question"],
        "votes": dict(zip(poll["options"], numbers)),
        "leader": leaders[0] if len(leaders) == 1 else (leaders or None),
        "open": not poll.get("closed") and time.time() < poll["closes"],
        "secondsLeft": max(0, round(poll["closes"] - time.time())),
        "service": counts.get("status", "not_running") if counts.get("id") == poll["id"] else "not_running",
    })


@server.tool()
def close_poll(clear: bool = False) -> str:
    """Close the overlay poll now (shows the final result), or clear it from the overlay."""
    state = _overlay_load()
    if not state.get("poll"):
        return "No poll"
    if clear:
        state.pop("poll")
    else:
        state["poll"]["closed"] = True
    _overlay_save(state)
    return "cleared" if clear else "closed"


ANNOUNCE_MAX = 160


@server.tool()
def announce(text: str, repeat: int = 2) -> str:
    """Scroll a one-line announcement across the ticker band over the game's bottom toolbar
    in first person, as myself (never "Claude" or "the AI"), e.g. "Big drought in 3 days: I'm filling
    every water tank first." Shown `repeat` times
    (1-3), about a minute apart, within the next 10 minutes. Max 160 characters. Poll voting
    reminders and new-chatter welcomes (a count only, never names) are added automatically."""
    import time
    text = " ".join(text.split())
    if not text:
        raise BridgeError("Empty announcement")
    note = "queued"
    if len(text) > ANNOUNCE_MAX:
        text = text[:ANNOUNCE_MAX].rsplit(" ", 1)[0].rstrip(",;:-") + "…"
        note = f"queued, but CUT to {ANNOUNCE_MAX} chars"
    state = _overlay_load()
    state["ticker"] = (state.get("ticker", []) + [{"text": text, "at": time.time(),
                                                   "repeat": max(1, min(int(repeat), 3))}])[-5:]
    _overlay_save(state)
    return note


# ---------------------------------------------------------------- dev

@server.tool()
def reload_bridge() -> str:
    """Hot-reload the bridge logic after rebuilding mod/TimberLive.Bridge.Logic (no game restart)."""
    return _compact(_call("POST", "/api/dev/reload"))


def save_and_quit(save: str) -> str:
    """Save under `save`, then close Timberborn like the main menu's Exit (end of stream). Not an MCP tool."""
    import subprocess
    import time
    _call("POST", "/api/save", body={"name": save})
    time.sleep(4)
    _call("POST", "/api/dev/quit")
    for _ in range(60):
        time.sleep(1)
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Timberborn.exe"], capture_output=True, text=True)
        if "Timberborn.exe" not in result.stdout:
            return _compact({"ok": True, "saved": save, "exited": True})
    raise BridgeError("Game did not exit within 60 s")

@server.tool()
def restart_game(settlement: str, save: str, save_first: bool = True) -> str:
    """Save (optional), quit and relaunch Timberborn straight into the given save, skipping the
    mod manager. Only needed when the TimberLive.Bridge shim itself changes."""
    import subprocess
    import time
    if save_first:
        _call("POST", "/api/save", body={"name": save})
        time.sleep(3)
    _call("POST", "/api/dev/quit")
    for _ in range(60):
        time.sleep(1)
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Timberborn.exe"], capture_output=True, text=True)
        if "Timberborn.exe" not in result.stdout:
            break
    else:
        raise BridgeError("Game did not exit within 60 s")
    steam = r"C:\Program Files (x86)\Steam\steam.exe"
    subprocess.Popen([steam, "-applaunch", "1062090", "-skipModManager",
                      "-settlementName", settlement, "-saveName", save])
    for _ in range(180):
        time.sleep(2)
        try:
            if _call("GET", "/api/ping").get("context") == "Game":
                return _compact({"ok": True, "loaded": f"{settlement} - {save}"})
        except BridgeError:
            pass
    raise BridgeError("Game relaunched but did not reach the Game scene within 6 minutes")


@server.tool()
def demolish(building_id: str) -> str:
    """Deconstruct a building or path, exactly like the player's deconstruct tool."""
    return _compact(_call("POST", "/api/demolish", body={"id": building_id}))


# ---------------------------------------------------------------- map survey

def map_columns(x: int, y: int, w: int = 64, h: int = 64, raw: bool = False) -> dict:
    """Raw survey grid for one area (max 64x64). Never moves the camera. Used by survey_map.py."""
    return _call("GET", "/api/map/columns", params={"x": x, "y": y, "w": w, "h": h, "raw": raw})


def scan_spots(template: str, z: int, x0: int = 0, y0: int = 0, x1: int = 0, y1: int = 0,
               orientations: list[int] | None = None, candidates: list[list[int]] | None = None) -> dict:
    """Placement check for a whole area (or a [[x,y,o],...] list) in ONE call. Returns every buildable
    spot with its footprint tiles, doorstep [x,y,z] and, for pumps, the pipe end {x,y,z,underwater,depth}."""
    body = {"template": template, "z": z}
    if candidates is not None:
        body["candidates"] = candidates
    else:
        body.update(x0=x0, y0=y0, x1=x1, y1=y1, orientations=orientations or [0, 1, 2, 3])
    return _call("POST", "/api/place/scan", body=body)


def reachable(start: list[int], targets: list[list[int]]) -> dict:
    """Nav-mesh walking distance from start [x,y,z] to each target (None = can't walk there)."""
    return _call("POST", "/api/map/reachable", body={"from": start, "targets": targets})


@server.tool()
def walk_distance(x: int, y: int, z: int, targets: list[list[int]]) -> str:
    """Walking distance (tiles, on the game's nav mesh) from (x,y,z) to each [x,y,z] target, max 400.
    null = beavers can't walk there yet (needs stairs, a slope, a dam/levee crossing or a path)."""
    return _compact(reachable([x, y, z], targets))


@server.tool()
def map_summary(refresh: bool = False, section: str = "") -> str:
    """Whole-map survey as short text: terraces (flat areas by height), how they link (natural slopes,
    where stairs are needed), water network and dam/floodgate choke points, badwater, farmland,
    resources with walking distance from the base, and the 'map under control' goals.
    Cached in harness/cache/map-survey.json; refresh=True rescans (about 1 s; doesn't move the camera).
    section = terraces | links | features | water | badwater | farmland | resources | goals | overview."""
    import survey_map
    return survey_map.report(refresh=refresh, section=section)


if __name__ == "__main__":
    server.run("stdio")
