# Harness notes: lessons from playing through the bridge

## Paths and entrances
- A building only works if a path reaches its **doorstep**, the tile just outside its entrance.
- At orientation 0, the entrance offset in `list_blueprints` is (ex, -1), so the doorstep is `(x + ex, y - 1)`, on the south side. Rotating the building rotates the doorstep too.
- Orientation 2 (180°) flips the doorstep to the north side, (x + ex, y + size_y). Example: a flag at (83, 46) with orientation 2 uses the path tile at (83, 47).
- With rotation, (x, y) acts as the pivot corner. At orientation 2 the footprint extends toward −x/−y from (x, y). Example: a Barrack at (75, 46) with orientation 2 covers about x73–75, y45–46, with its path tile at (74, 47). Don't work out offsets by hand. Place it, read `pathTile`, and demolish and retry if it's wrong.
- `list_buildings` gives each building's `pathTile` (the tile the path must cover) and its live `statuses`, such as "Unconnected building" or "Construction lacks materials". **Check statuses after every placement batch.**
- Flags (gatherer, lumberjack) are 1x1 and their doorstep is `(x, y-1)`.
- The district centre's door tile shows as `districts[].x/y` in `get_colony`. The path must start on the tile outside it. On "d", the door faces west and the path starts at (69, 45).

## Save and map study (no game load)
- `save_study.py list | study "<settlement>" [file|cN] | timeline "<settlement>" | maps`. Saves and maps are zips holding `world.json`; it reads them straight from `Documents/Timberborn/{ExperimentalSaves,Saves}`. `cN` = earliest save from cycle N. `maps` pulls every built-in and user map through `GET /api/maps/file` (base64) and lists its natural objects. Results: `12-player-build-study.md`, 10 §16 "Which built-in maps have what".

- **Inspect anything:** `inspect_tile` returns each object's `id` (also natural objects like Unstable Cores and relics). `GET /api/building/inspect?id=...&all=true` adds the read-only state of every component (timers, radius, stockpile rules, deletion blockers). Use it to answer "what does this object do" questions.

## Map survey (read the whole map without moving the camera)
- `survey_map.py scan` (or the `map_summary(refresh=True)` tool) tiles the map through `GET /api/map/columns` (64x64 per call) and caches it in `harness/cache/map-survey.json` and `map-summary.txt`. A scan takes about 4 s. Later calls read the cache; rescan after big builds and during each hazard so the badwater/drought history fills in.
- Sections: `overview` (64-wide height map with ~ water, ! badwater, T trees, R ruins, S slopes, B base), `terraces`, `links`, `features`, `water`, `badwater`, `farmland`, `resources`, `goals` ("map under control" checklist). Run one section at a time to save tokens.
- **Terrain is blocks.** Beavers only change height on a natural **Slope** (map object, 1x1x2 ramp), built Stairs, or by crossing dams/levees. `links` lists the next Stairs spots (stand, enter, step-off tiles) and the natural Slopes; `features` lists every Slope with its orientation. Check these before building stairs.
- `walk_distance(x,y,z,targets)` (`POST /api/map/reachable`) asks the game's nav mesh for walking distance; `null` means unreachable.
- `/api/map/columns` also returns `layered` columns (more than one standing level: overhangs, caves, ground under ledges) with headroom.
- Choke points: narrow water cross-sections with banks on both sides, in moving or still water. "holds N" = how many blocks of water a gate there can hold back (lowest bank minus bed). Clean-river order runs from the clean sources, so "upstream" means toward the clean spring.

## Heights
- Give `z` as the level the building stands on, which is the height `view_map` shows for that tile.
- Some blueprints have `BaseZ > 0`, meaning part of the building sits below ground (the Deep Water Pump has BaseZ 1). The bridge adjusts for this, starting with the build after 0.1.0.

## Pumps
- Deep Water Pump (2x3): at orientation 0 the intake is the row at `y + 2`, hanging over the water at `(x, y+2)`. Rows y and y+1 sit on the bank, and the doorstep is `(x+1, y-1)`.

## Wood
- Lumberjacks **only cut trees inside the tree-cutting area**. Mark it with `mark_tree_cutting` over a stand of trees near the flag.
- Nothing gets built without logs, so on day 1 the order is lumberjack + cutting area + path first.
- Place lumberjack flags next to the trees, not near the district centre. Find tree stands with `view_map` (the legend shows Pine, Birch, Oak).

## Iron Teeth population
- Iron Teeth only grow through **Breeding Pods**. Without pods, the population shrinks as beavers die of old age.
- Build the first pod (10 logs, 1x1) once water and food are stable, which was day 7 in game "d".
- A pod uses about 1 water and 1 berry per day per kit, so pause it when food is short. Its status reads "Breeding halted, waiting for nutrients" when it lacks inputs.
- Keep pods running, including through droughts. The user's rule: a falling population is worse. Only pause a pod if water or berries would actually run out before the hazard ends, and fix shortages by adding production.

## Workers
- The minimum desired workers is 1. To stop a workplace, use `set_paused`, not 0 workers.
- `set_workers 0` used to hang the game in an infinite loop. It's fixed now (clamped and bounded), but that froze game "d" and cost about 2 days back to the autosave.

## Mistakes so far (game "d", cycle 1)
- I didn't plan Breeding Pods until the user reminded me. On Iron Teeth they belong in the opening.
- I put a lumberjack flag where there were no trees nearby and no path to it.
- I put a gatherer flag with its doorstep off the path. Fixed it with 2 path tiles at (64,44) and (63,44).
- **Dams/sites in water:** builders can't reach a construction site under water (~0.65 deep). Three river dams got built in the cycle-1 drought while the bed was dry. Plan water works for drought days, or build from the dry side first.
- **Plant growth:** `t._call('GET','/api/map/plants',params=dict(x,y,w,h))` gives a count per plant type: grown, growing, avgGrowth, dying, dead, gatherableRipe. Use it to check whether crops are ripe but unharvested (a FarmHouse is max 2 workers; keep fields close to it) or whether bushes have berries.
- **FarmHouse harvest:** new FarmHouses start with planting prioritised, so ripe crops sit unharvested (this caused the cycle-3 famine). Use `building_action(id,'FarmHouse','UnprioritizePlanting',[])`. watch.py does this automatically when a FarmHouse finishes.
- **Drought 3 (cycle 3, 5 days):** the river dried completely by day 3 despite 3 dams, and the deep pumps stopped. Water fell from 99 to 36 in about 3 days with 14 beavers and 4 pods. Plan about 25 water per day per 10 beavers, plus storage for the whole drought. The dam site at (57,51) got 0 logs even when dry: it can't be reached without Stairs (riverbed 1 level down). Fix: Stairs (69,51) z2 ori3 up to path (70,49-51) z3, plus a path along the riverbed (58-68,51) z2. Beavers can work in clean water, but not in badwater (user).
- **DeepWaterPump pipe:** the pump also fills the tile in front of it, one level down (pump (66,49) uses (66,51) z2). A path there makes it report 'Pipe obstructed'. **Stairs** ori0 at (70,52) z2: you walk on at the bottom from the south (70,53) and step off at the top to the north (70,51) z3.
- Don't box the base in: leave path corridors out of the h3 core. North corridor: path x69 y40-42 z3 -> Stairs (69,37) z3 ori0 -> path x69 y30-36 z4 onto the big dry h4 plateau (x60-73 y20-34). (69,38),(69,39) still kohlrabi; path them after harvest. East plateau h5 starts at x75-83 (2 levels up, needs a h4 step).
- Paths are template 'Path' (no faction suffix). Crops block path placement; clear_planting removes marks, not grown plants.
- POST /api/map/demolish-resources {x0,y0,x1,y1,unmark} (helper `demolish_resources`) = the toolbar's Demolish resources tool. It marks plants for builders to remove and clears planting marks there. The old instant remove-plants (a dev-mode delete) was removed. `demolish` now only takes buildings and paths, like the Deconstruct tool.
- Foresters: `building_action(id,'PlantablePrioritizer','PrioritizePlantable',['Oak'])`.
- Helper scripts: `pathmap.py x0 y0 w h`, `wetplants.py x,y,w,h`, `h.py` (find/ids).
- Next east step: from the h4 plateau at (76,33) put Stairs up to h5 (77,33) -> east plateau x77-90 y35-42.
- 1x1 LumberjackFlag also has an access side: ori0 access = (x, y-1), ori1 = (x-1, y). Check pathTile like any building.
- Stockpile obtain/supply: `building_action(id,'GoodObtainer','EnableObtaining'|'DisableObtaining',[])`, `building_action(id,'GoodSupplier','EnableSupplying'|'DisableSupplying',[])` (bridge gen 7).
- MediumTank ori2 pivot (76,33) z4 has its door at (76,34) on path y34. Paused LJ (68,31): the plateau's dead pines are all cut.
- Dams are walkable: a dam line doubles as a river crossing. Rooftop Terrace placement on barrack (70,35) works at z6, but it needs Platform access.
- Map features (scan of the whole 256x150 map, c5):
  - Fresh WaterSource at (87,84-88): our river comes from there.
  - BadwaterSource at (197-199,67-68).
  - Ruins (scrap for a Scavenger Flag): x22-30 y83-94 (closest), x203-212 y11-15, x214-219 y119-124, x119-125 y102-108.
  - UndergroundRuins at x41-45 y118-119.
  - GeothermalField at x91-97 y132-133.
  - The river cluster (wheels (71,52),(74,53)) runs completely dry in an 8-day drought: riverbed h2, banks h3.
- **Large Water Wheel support:** only one of its blocks has a requirement: the front-centre block at local (2,0,2) needs Ground or a Stackable directly under it (`place_building(check=True)` plus `explain: true` lists this as `needs`). Every other block may hang over water. So the axle must rest on a bank 2 higher than the riverbed (or on a platform). A check scan of the whole river x70-92, y54-66 at z2 found no spot: the banks there are only 1 above the bed.
- `/api/place` with `check: true` also returns the preview's `warning` tooltip, and with `explain: true` it returns `needs` (blocks that need ground or a stackable below).
- **Water wheels** (any template with a WaterPoweredGeneratorSpec): each `buildable` (check) and `placed` spot also has `power` (hp the hover preview shows, from current water), `maxPower` (rated output), `flow` (mean flow speed over the wheel's water tiles) and `waterTiles` [{x,y,z,wet,flow,along}] (`along` = flow along the wheel's axis; only |along| above the wheel's minimum counts). Rank candidate spots by `power`.
- **Power connections**: `place_building(check=True)` spots (buildable and rejected), `placed` spots and `inspect_building` all have `powerConnections` [{x,y,z,dir,from}] only for mechanical buildings (generators, consumers, shafts; houses etc. get no field; up/down points into solid terrain are left out): (x,y,z) is the world tile where a shaft/mechanical building must stand (its z = the shaft's place z), `from` is the building's own block, `dir` is +x/-x/+y/-y/up/down; inspect also gives `connected`. Points sit at the transput's block height (Compact Water Wheel: its axle, standing z+1). PowerShaft (1x1x1, Stackable None) needs ground or a stackable block (e.g. Dam) directly below and cannot sit on another PowerShaft.
- **DoubleShower** (1x2x2, 10 Log + 1 Plank) must stand in or next to water deep enough to draw from: on dry land it says "This building needs deeper water to function." Place it at the river edge like a pump. It satisfies the WetFur need.
- Natural Slope objects are walkable only if their foot tile is free: a building on the foot tile blocks the slope. Check reach with walk_distance (null = unreachable).
- **Doorsteps without trial builds:** `h.door_tile(template,x,y,ori)` computes the doorstep from the blueprint entrance; `h.place_on_path` checks it and places once. Never place-and-demolish to probe (user rule).
- Bridge: an exception logged with Debug.LogException opens Timberborn's crash screen. The shim now logs warnings instead; view_map legend no longer collides past 40 object kinds (c7d1 crash).
- **Stream setup tools:** `obs.py launch` starts OBS (collection "TimberLive 6") and checks 1080p30/YouTube/sources; OBS 30.1 keeps its WebSocket settings in `global.ini` [OBSWebSocket]. `youtube_meta.py` (OAuth, token DPAPI-encrypted in `%LOCALAPPDATA%\TimberLive`) sets title/description/tags/thumbnail: `prepare --info ../media/epN/stream-info.md --thumbnail ../media/epN/thumbnail.png`, then `verify`. Set `PYTHONIOENCODING=utf-8` when piping its output (emoji). Tags can take a minute to show in `verify`. The channel has one stream ("Default stream key"); the reusable broadcast is UEfPswUFyMM. Game title "Timberborn" is Studio-only. OBS uses 'Use Stream Key' mode (set by `youtube_meta.py obs-key`), NVENC p5 at 6000 kbps. Each stream is its own YouTube video: `prepare` reuses the upcoming bound broadcast or makes a new one. Broadcasts it creates have auto-stop off, so after `obs.py end-stream` run `youtube_meta.py end` (harmless if already ended).
- **OBS "No Broadcast Configured":** if OBS has a YouTube account connected (Settings → Stream), websocket StartStream silently opens that modal and never goes live. Fix: Settings → Stream → Disconnect Account → Use Stream Key (the key stays set), then `obs.py go-live`.
- list_buildings now includes powerConnections per power building (connected:true once linked; sites show their planned points). Needs reload_bridge after the 2026-10-14 build. Don't use inspect_building/inspect_tile in loops: both move the camera.

## Batch spot search (2026-10-14)
- `t.scan_spots(template, z, x0, y0, x1, y1)` / `candidates=[[x,y,o]]` (bridge `/api/place/scan`): one call, ~0.2 s for 2,400 spots. Each buildable spot gives `tiles` (footprint), `door` [x,y,z] and for pumps `water` = the pipe end (game rule WaterInputPipeCoordinates: drops from the input until terrain, max depth) with `underwater`/`depth`/`contamination`.
- A spot passing the placement check can still have a **dry intake** (Waterfalls (73,62) o2): always filter pumps on `water.underwater`.
- Game gotcha: `PreviewPlacer.GetBuildableCoordinates` is a lazy iterator that only clears its preview list after the last item; enumerate it fully (`ToList()`), or later checks see stale previews.
- `plan_opening.py openings/<map>.json` = the whole opening batch from a spec (roads, buildings near points, cut and plant rects, dam lines); `--apply` places it.
