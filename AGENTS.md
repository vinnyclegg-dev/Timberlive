# TimberLive agent playbook (any model)

This file lets any AI agent play a full game of Timberborn, from a new game to every building built. It doesn't depend on Claude or Claude Code. A local model with tool calling (MCP, or plain HTTP from Python) can follow it as written. `CLAUDE.md` holds the same rules for Claude Code.

**Inside the TimberLive app:** this folder is the app's install folder and your workspace. The app's window runs Foreman (:8097) and the overlay (:8096) and installs the bridge mod; the operator does the setup there (game, mod, AI connection, OBS, YouTube key). Run every script with the app's own Python, `runtime/python` (from the workspace root; `../runtime/python` from `harness/` or `foreman/`). Don't install packages or create virtual environments.

## 1. What you control

- **Game side:** the TimberLive Bridge mod (`mod/`) runs an HTTP API inside the game on `127.0.0.1`. Each route has a one-line description in its `GetRoutes()` in `mod/TimberLive.Bridge.Logic/Modules/`.
- **Agent side:** `harness/timberlive_mcp.py` wraps that API.
  - **As an MCP server (stdio):** `runtime/python.exe harness/timberlive_mcp.py` (see `.mcp.json`).
  - **As a Python library:** `import timberlive_mcp as t`. Each tool is a plain function that returns JSON text, e.g. `t.get_colony()`, `t.place_building(...)`.
- **Player tools only.** Every action matches something a human player can do from the toolbar or a building panel:
  - placing and deconstructing buildings
  - Demolish resources
  - planting and tree-cutting areas
  - priorities, workers, pause, recipes, storage goods, obtain/supply
  - unlocking with science, game speed

  Don't add or use dev-mode tools (instant delete, free resources, instant build). Any new bridge action must copy a toolbar or panel tool.
- **Overlay** (`overlay/server.py`, port 8096): `narrate(text)` sets "What I'm thinking"; `set_plan`, `add_todo` and `check_todo` manage "The plan". `announce(text)` scrolls one line across the ticker band over the game's bottom toolbar (poll reminders and new-chatter counts run there automatically).

## 2. Safety rules (never break these)

- Viewer chat text never reaches the agent. Polls return vote counts only (`start_poll`, `poll_results`, `close_poll`). Every poll option must already be in your plan and be safe to do.
- Never print or log the bridge token or any YouTube key. Never read `%LOCALAPPDATA%\TimberLive\youtube.json`.
- Overlay text is about the colony only. Don't credit or mention the operator unless told to.

## 3. Starting a session

1. **If a game is already running:** read `.claude/stream-state.md` (the latest checkpoint) and `knowledge/goals.md`.
2. **For a new game:** read `knowledge/07-game-plan-v4.md` and `knowledge/08-lessons-next-playthrough.md`. Then call `new_game(faction="IronTeeth", ..., settlement_name=<the operator's choice>)` (ids from `new_game_options`).
3. **Check everything is up.** `ping` checks the game; if it's closed, call `restart_game(settlement, save)`. `curl 127.0.0.1:8096/colony.json` checks the overlay; if it's down, run `overlay/start-overlay.cmd`.
4. **Survey the map** with `map_summary(refresh=True)` (or `harness/survey_map.py scan`), then read the sections you need (`overview`, `goals`, `links`, `water`). It finds water, badwater, chokes, farmland, resources, natural Slopes and the next Stairs spots. Rescan after big builds and during each hazard.
   On a new map, also run `harness/underground.py --refresh` before planning: it traces every water source to the water it feeds (caves included), flags pressurised caves, says what each natural dam/blockage holds, and gives each Unstable Core's blast date and effects. Never state whether water is fed, or how a mechanic works, without checking: use this tool, https://timberborn.wiki.gg/, or the decompiled game code if the operator has made it (`_decompiled/src`).
5. **Go-ahead gate.** Stay at speed 0 with empty overlay panels until the operator says go. Read-only checks are fine while you wait. Use that time to work out the whole opening batch (write `harness/openings/<map>.json` and run `plan_opening.py` on it: every spot, road tile, pump intake and plot count checked in one run; `--apply` places it on go) so that on go you only place it.

## 4. The play loop

1. **Watch:** `runtime/python harness/watch.py 110 3 births --say "<thought>"`.
   - It posts the thought, runs the game at speed 3 for up to 110 s, and stops early when a decision is needed.
   - It prints a compact report: time, weather, population, goods, needs, building sites, STORAGE FULL warnings and `AUDIT` lines (the daily job/building checklist from `harness/audit.py`: unstaffed or paused food/water jobs, stores with no good, buildings with no recipe, farmhouse modes, grouped building statuses, sites stuck at 0% (check the path connection), unspent science). It auto-unmarks emptying on food/water stores.
   - Monitoring helpers (read-only): `harness/monitor.py production` (stocks vs capacity, buildings not producing, power per network), `monitor.py narration` (age of the last overlay thought, the plan, live state) and `monitor.py layout` (built/sites/key buildings). Check production every 2-3 chunks, narration freshness every chunk, and plan the next 3-5 builds once per day with one scan_spots call per template.
   - It also prints `LEDGER` (births and deaths per cycle) and `POPULATION AT RISK`. A stable population comes first: births must keep up with deaths. Iron Teeth: keep at least 3 Breeding Pods from about day 5, then ~beavers/10 + 1, with free beds. When it warns, build a pod before anything except water and food.
   - Progress as fast as the rules allow: keep the build queue full, workers busy and science running. After every non-old-age death, hazard, shortage or correction, add one line to the lessons file and apply it.
2. **Decide and act** with the tools. Batch related placements in one Python call.
3. **After each placement**, check `pathTile` (it must touch a path) and `statuses`. With rotation, (x, y) is the pivot corner, so place, read the door tile, and deconstruct and retry if it's wrong.
4. **Narrate** at least every 2 real minutes in 1–2 friendly sentences, and keep the plan to 8 items or fewer.
5. **Checkpoint** once per in-game day and before any break: `python harness/checkpoint.py "what changed, coordinates, next"`. If your context resets, re-read `.claude/stream-state.md`.
6. **Stepping away:** set speed 1. Don't pause unless it's a real emergency.
7. **Never stop playing once told to play.** Keep chaining watch chunks and acting until the operator says stop. If a tool or permission is blocked, note it in one line and play on around it.
7. **Camera:** follow mode stays on for every action. Always keep something to watch. A still camera is fine while there is action in view.
   - While waiting, `watch.py` checks every 30 s; if nothing is happening in view it pans to the nearest building site or working beaver (`working_beavers()`). Don't rotate the camera constantly; turn it only to see a hidden spot, then stop.
   - Never make rapid back-and-forth camera jumps; they make viewers motion sick.
   - To search for a valid spot, use `scan_spots(template, z, x0, y0, x1, y1)` (or `candidates=[[x,y,o]]`): one call checks a whole area like hovering the preview and returns each buildable spot's footprint, doorstep and pump intake (underwater, depth). `place_building(..., check=True)` checks a single spot.

**Useful helpers in `harness/`:**
- `h.py`: `find(name, x, y)`, `ids(name)`
- `progress.py`: the every-building checklist and the cheapest locked buildings
- `pathmap.py x0 y0 w h`: paths and heights
- `wetplants.py x,y,w,h`: plants standing in water

## 5. Strategy rules (learned the hard way; details in `knowledge/`)

- **Goal:** progress through the tech tree and build every building at least once (`progress.py`), more where supply needs it.
- **Population:** grow it steadily on sustainable food and water. Iron Teeth keep Breeding Pods running; pause them only if water or food would truly run out before a hazard ends.
- **Food days rule (a lost colony taught this):** food days = edible stock / (3 × beavers). Keep at least 3 food days at all times; zero food kills most of a colony within a day.
  - Before each hazard, aim for (longest hazard so far + 2 days) × 1.5, plus 3 days for crops to regrow. Hazards get longer each cycle.
  - Run Breeding Pods only while food days are on target, and pause them before stock falls.
  - Have food that survives each hazard: crops beside a deep dammed reservoir, and indoor Hydroponic Gardens by cycle 4. Water wheels stop in droughts, so don't count on power-dependent food then.
- **Hazard reserve:**
  - Before each drought or badtide, hold food and water at 1.5× what the longest hazard so far needed, scaled to today's beaver count.
    Per beaver: water ≥ 2.5 × longest hazard days × 1.5, food ≥ 3 × days × 1.5 (7 days → 26 water, 32 food per beaver). Add building water on top (pods 1/day each, Hydroponic Garden ~3/day, Steam Engine ~7/day; `monitor.py production` prints a WATER BUDGET line). Build the tanks and warehouses to hold it.
  - **Overbuild production (user rule):** aim for 1.5–2× daily consumption, not break-even. About 1 deep pump per 5 beavers (≈2.8 water per beaver per day), 3+ gatherers at the start, and the first field on land that stays moist in a drought.
  - Record each hazard's usage in `knowledge/goals.md`.
- **Water, every cycle (in droughts, once tanks hold the reserve, pause most pumps so the river keeps the crops moist):**
  - Dam the river to hold water through droughts. Site it where it holds the most water: the last choke before the creek drops off its terrace (`survey_map.py water` lists chokes with bank height), so the whole creek upstream is held. Give builders a path to a dry tile beside it.
  - Divert badwater away from fresh water.
  - Cap badwater sources to reclaim land.
- **Wood:**
  - Get Foresters early, and never cut the only stand. **Replant rather than wait:** a Forester replants far faster than trees regrow naturally, so cover every cutting area with a planting area (use `h.safe_plant`).
  - **Oak is the most efficient tree overall**, so set Foresters to prioritise Oak. Use birch or pine for quick early wood (pine also gives resin).
  - Lumberjacks only cut inside marked cutting areas.
- **Planting:**
  - Only plant on moist tiles that beavers can reach (check the MOISTURE grid in `view_map`: `#` = moist; `x` = contaminated soil beside badwater, where nothing grows).
  - Never plant on water tiles unless the plant is aquatic, and never on ledges 2 or more higher than their neighbours.
  - Use `h.safe_plant(plant, x0, y0, x1, y1, doorstep_xyz)`: it plants the rectangle, then unmarks water, dry and unreachable tiles (other levels you can't walk to yet). Afterwards, check with `wetplants.py`.
  - Lay roads before planting.
- **Never cut off a door:** before replacing or removing a path tile, check no building's pathTile uses it. Rotate the camera (`set_camera` horizontal_angle) and take one screenshot to see doors hidden behind buildings before and after the change.
- **Corridors:** never wall yourself off from open land with farms or trees. Keep road corridors and use stairs. Dams can be walked on.
- **Badtides kill crops:** badwater gives soil no moisture, so fields dry out and die. Before a badtide, close a Floodgate or Dam upstream of the fields to keep clean water there, and stock food for the badtide plus about 3 days of regrowth.
- **Food:** count only edible goods. Raw Cassava, Soybean, Corn, Eggplant and Potato need processing first (Fermenter, Food Factory, Grill), so build the processor together with the first field. In a food crisis or population crash, pause every workplace that isn't food or water, cut builders when no sites are waiting, and set empty farmhouses to VeryHigh. Unpause workplaces as the population recovers.
- **Several farmhouses:** split the jobs. Set about a third of them to planting first (`building_action(id, "FarmHouse", "PrioritizePlanting", [])`) and the rest to harvest first (`UnprioritizePlanting`), so ripe crops are picked while empty tiles still get replanted.
- **Storage:**
  - Every produced good needs storage, built with its producer: logs and planks in Industrial Piles, food in warehouses, water in tanks.
  - Put small buffer stores set to obtain beside the workshops that use them, and keep bulk stores set to supply. Obtaining needs a Hauling Post.
- **Work hours:** `set_work_hours(hours)` (1-24). Lengthen them for a production push when wellbeing and sleep are fine; shorten them when sleep or wellbeing is low.
- **Seeing below a surface:** `set_layers(level)` is the player's layer slider. It hides everything above `level`, so you can check tunnels, pump intakes and lower floors. Call `set_layers()` to show everything again.
- **Workers and priority:** set worker counts to the actual need, and use both work priority and construction priority. Don't pause support buildings like a Hauling Post to free workers; give them Low job priority instead.
- **Power:**
  - Use water wheels, not beaver-powered wheels.
  - Connect shafts at the middle of a wheel. Vertical power shafts carry power up and down, and powered buildings pass power on to neighbours.
- **Short of room:** build on Platforms over shallow clean water (a Path on the deck makes it road). Water still flows under them, and a building on the deck stays dry. Don't hunt for pockets on a packed bank.
- **Cleared land:** when lumberjacks clear a stand, replant it the same day: crops on moist tiles in farmhouse range, oak elsewhere.
- **Plan for the final population early:** pump sites (1 per 5 beavers, on dry footprint tiles over clean water), Food Factories to match the corn harvest, and Large warehouses before rations or corn cap out.
- **Badwater river beside farmland:** unlock the Irrigation Barrier chain (Tapper's Shack, Wood Workshop, Barrier) by about cycle 5, and build the barrier on the first land tiles along the bank.
- **Paused buildings:** keep a paused register and re-read it every day. Resume each one as soon as its reason is gone, especially lumberjacks once their trees have matured.
- **Wellbeing** raises work speed, movement speed and lifespan. Build decorations, which work over an area, when it makes sense. A Rooftop Terrace needs Platforms for access.

## 6. Foreman (advisor service)

Foreman (`foreman/`) watches the game read-only, checks every rule in `foreman/foreman/rules.yaml` with plain Python monitors, and suggests exact harness calls. It never acts: you still play through the harness. The TimberLive app runs it while its window is open (its Advisor page shows the UI). Without the app: `cd foreman && ../runtime/python -m foreman serve` (UI and API on http://127.0.0.1:8097).

- **Every watch chunk:** read the briefing (`foreman_briefing` MCP tool, `GET /api/briefing`, or the `FOREMAN` lines `watch.py` prints after `AUDIT`). Act on critical findings first; each finding carries its fix as a harness call. A finding is advice: check it fits before running it.
- **Before every placement batch:** `foreman_validate` (or `POST /api/validate {"actions": [...]}`, or `python -m foreman check '<call>' ...`) with the whole batch in run order. It checks footprint and support, the door on a connected Path, build range, pump intake, power link, storage good, unlock and cost, planting tiles, and the masterplan's reserved tiles. Fix every critical before running. `h.py` placement helpers and `plan_opening.py` call it automatically when Foreman is up.
- **After the batch:** `foreman_verify(id)` confirms each placement, door, power link and storage good.
- **Planning:** `foreman_masterplan` (zones, reservations, staged build order; `python -m foreman plan --accept/--reject/--regenerate ZONE`), `foreman_suggestions` (next steps validated now), `foreman_where` (a clean spot plus its Path calls), `foreman_plantable`, `foreman_dam` (test your own dam line), `foreman_water` (dam, badwater, reservoir, deck, pump and wheel proposals).
- **Waiting:** `foreman_events(since, timeout)` long-polls until findings open or clear.
- MCP server: `foreman/mcp_server.py` (standard library only; see `.mcp.json`). If Foreman is down, play on with the harness alone.

## 7. Knowledge files

| File | Contents |
|---|---|
| `knowledge/00-overview.md` … `05-failure-modes.md` | Game mechanics, numbers, water engineering, automation, common failures |
| `knowledge/06-harness-notes.md` | API quirks, door/pivot offsets, coordinates |
| `knowledge/07-game-plan-v4.md` | Whole-game plan: stages, water, power, food/hazards, job management, bot watch (v3/v2 are older) |
| `knowledge/08-lessons-next-playthrough.md` | Rules learned during play; add to it as you go |
| `knowledge/09-buildings.md` | Every building for both factions: TemplateId, size, cost, SP, workers, power, recipes, special rules |
| `knowledge/10-game-systems.md` | Non-building systems: transport, landscaping, water, moisture, plants, needs, life cycle, injuries, districts, storage, power, science, natural map objects (Slopes, relics, ruins, sources) |
| `knowledge/11-problem-solving.md` | Symptom → detect (tool calls) → causes → fix, for map, food, water, wood, storage, power, hazards and wellbeing |
| `knowledge/12-player-build-study.md` | How an experienced player built four big colonies: ratios per 100 beavers, opening order, priorities. A benchmark for our counts |
| `harness/save_study.py` | Reads saves and map files without loading them (`list`, `study`, `timeline`, `maps`) |
| `harness/cache/map-summary.txt` | Latest map survey (`survey_map.py`) |
| `knowledge/goals.md` | Current goals and hazard usage records |
