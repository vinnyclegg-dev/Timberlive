# Game plan v4 (whole game, any map, Iron Teeth)

Replaces v3 (`07-opening-plan-v3.md`). Rebuilt on 2026-10-14 after the run 3 / Lakes / Meander famines and the user's review. Every step opens on a measurable **gate**, not a fixed day.

## Core principles
1. **Get ahead, not "by cycle N".** Each defence (dam, reservoir, indoor food, drought-proof power) is built before the hazard that needs it, as early as logs and science allow.
2. **Use the land fully.** Every moist, reachable tile in farm or forester range is planted (crops or trees). Corridors and pump banks are the only gaps.
3. **Few buildings, fully staffed.** Size farmhouses, pumps and workshops to the land and the demand. Don't add production buildings to soak up workers. The exception is spare Builders' Huts and Hauling Posts on Low priority: they only take beavers nobody else needs and speed up building and hauling.
4. **Food must survive a drought end to end:** raw stock + processing + power + water for the processing all have to hold.
5. **Growth is gated by proven supply**, not a ratio.

---

## 1. Stages of building the colony

### Stage 0: Scout (paused, before anything is placed)
- `survey_map.py scan`, then `overview`, `water`, `links`, `farmland`, `resources`.
- `underground.py --refresh` (every map, cores or not): confirm which source feeds which water (3D trace through caves; never assume), find pressurised caves, what each natural dam/blockage holds, and each Unstable Core's blast date (countdown starts cycle N day 1, blast 10.5 days later) and effects. Any core whose blast opens a new outlet toward the base or joins badwater to clean water gets a counter-measure (levee/dam outside the blast sphere) in the plan before its cycle. Don't build inside a blast sphere (radius + 1 around the core's footprint centre at its z) unless it's cheap and temporary.
- Read the river's **flow direction**. Mark the **last choke downstream of where pumps and fields will be** (dam site), the deepest pools (pump intakes), the fastest drops (wheels), badwater sources and inlets.
- Measure **all** moist, reachable land within ~20 tiles (farmhouse range) of the planned farmhouse spot. This sets the plot count, not a fixed 50.
- **If there's little or no moist land in range**, work down this list:
  1. Move the farmhouse, not the farm: any moist patch within district range (~70 path tiles) of the District Centre, reached by road, Stairs or a natural Slope.
  2. Make moist land with a Dam (0 SP, 20 logs) at a choke: the raised pool spreads moisture ~10 tiles across flat banks (each level up costs ~6 tiles; downhill is free). Mark the plots once MOISTURE shows `#`.
  3. Bridge food meanwhile: 3+ gatherers on wild bushes and a bigger berry store; pods wait until food days are 3+.
  4. Science straight to Levee (120) + Discharge (250) for 1-tile irrigation ponds on the nearest flat dry land, ahead of other unlocks.
  5. Then Hydroponic Gardens (no soil needed) as the main food, so the colony doesn't depend on land at all.
- Plan the road grid: main road + a corridor every 8-10 tiles; keep the river-bank row free for pumps; Stairs/Slopes for every level change.
- Find a higher-ground basin **upstream** of the base for a future reservoir (Stage 4).
- Confirm every opening spot with `plan_opening.py openings/<map>.json` (one batch run; pumps need `water.underwater`); nothing is placed until go-ahead, then `--apply`.

### Stage 1: Opening batch (on go-ahead)
- Path on the District Centre doorstep first.
- **Water:** 2-3 Deep Water Pumps on the deepest water (about 1 per 5 beavers) + 2-3 Small Tanks set to Water.
- **Food:** 3+ Gatherer Flags on the berries + a warehouse. 1 FarmHouse; mark **every** moist reachable tile in its range with `h.safe_plant` (kohlrabi), typically 100-150 plots. Marking is free; farmers plant it over the first days.
- **Wood:** 2 lumberjacks on the **whole** grown stand (check `/api/map/plants` grown), log pile beside them.
- **Pods:** 3 Breeding Pods (10 logs each) by about day 5, once food days ≥ 3.
- **Dam:** the first 20-log Dam at the downstream choke as soon as the pump, farmhouse and pods are placed (day 2-5). If the bed is below the bank, Stairs is the first 70 SP after the Forester.

### Stage 2: Renewable wood and planks (cycle 1)
- Inventor → **Forester** (30 SP). Forester areas cover all remaining moist land not set aside for fields or roads: Birch/Pine near (quick), Oak further out (best long-term).
- Compact Water Wheel **below** the dam spill (fast flow) + Industrial Lumber Mill touching it; Plank pile beside the mill.
- **Gate:** logs hold above 50 and the next stand is marked before the current one runs out.

### Stage 3: Hold the water (cycle 1, before the first drought)
- Full dam line at the downstream choke + Path on top (it becomes a bridge, linked at both ends).
- Levee (120 SP) + Discharge (250 SP) → first **1-tile irrigation pond** for any field that dries in drought (Section 2).
- Tanks to the water reserve.

### Stage 4: Hazard-proof food and power (cycles 2-3)
- Gear Workshop → Medium Tank → Floodgate → Scavenger + Metalsmith → **Hydroponic Garden** → Smelter → **Food Factory** + corn.
- **Drought-proof power** on the food network (Section 3) before the first drought longer than 3 days.
- **Upstream reservoir** with valve-controlled release (Section 2) once Fill/Throttling Valves are affordable.
- Fermenter: 1 per 2-3 Hydroponic Gardens.

### Stage 5: Controlled growth (cycle 3 onward)
- Grow only through the growth gate (Section 4). Each step up: plots, pumps, tanks, storage, beds, processing and power first, then pods.
- Wellbeing basics (Campfire, Shrubs, Scratcher, Rooftop Terrace) once food is safe.
- Automation: Weather Station → floodgates, pods, valves.

### Stage 6: Every building
- `progress.py` checklist, cheapest unlocks first, without breaking any reserve or gate.

---

## 2. Water: retention and manipulation

### Basic facts
- **Pumps only pump standing water above their intake.** With no water at the intake they stop, whatever the tanks say. A pump pool must be held deep (dam) and kept separate from water drawn for irrigation.
- 1 tile × 1 m depth ≈ 5 water goods. Evaporation ≈ 0.045 m/day per exposed tile: **go deep, not wide**.
- Badwater doesn't moisten soil, and contaminated water spreads soil contamination up to 7 tiles.
- Seeps only spill up to 0.8 m; treat them as a small bonus source, not a supply.

### Early (cycle 1)
- **Dam at the last choke downstream of the pumps and fields** (read the flow arrows). It holds the whole stretch upstream. Path on top, linked both ends.
- Water wheels go in the spill **below** the dam, not in the still pool above.
- Plant first fields on land beside the dammed pool, not on riverbank that dries out.

### Mid (cycles 2-4)
- **1-tile irrigation pond:** 4 Levees around a 1-tile hole + a Discharge feeding stored water into it. The land around stays moist through droughts. Use it for every field that can't sit by held water. Budget its water (a Discharge can move up to 3 water/hour; automate it with Depth Sensors + Memory so it only tops up when low).
- **Separate drinking water from irrigation water:** pumps draw from the dam pool; irrigation comes from ponds or a reservoir release, so a drought that drains one doesn't stall the other.
- Floodgates on every inlet that badwater could enter; close them at a badtide warning (later: Weather Station / Contamination Sensor > 0.05, with a 12-24 h delay before reopening).
- Build river crossings while the bed is dry in a drought.

### Late (cycle 4+)
- **Big upstream reservoir, higher than where the water is needed.** Levee walls (stacked in gorges), filled from the river in temperate weather, inlet closed before droughts. Release slowly through **Fill Valves / Throttling Valves** into the field channels and the pump pool: gravity-fed drinking and irrigation water for the whole drought.
- Deep pump pits (dynamite) where the bed is shallow, so the Deep Water Pump's 6 m reach stays under water.
- Cap or divert badwater sources (Badwater Pressurizer, levees, channels off-map) to reclaim land.

---

## 3. Power and industry

### Layout
- **One shared network per industrial area.** Wheels joined wheel-to-wheel along the axle or by Power Shafts; consumers linked by **shafts, not through each other** (a paused building cuts the power passing through it).
- Wheels: middle of the long side, mutual power points; fastest flow (below dams and drops). Check output with `place_building(check=True)` before placing.
- **Check power before and after placing any powered building** (Fermenter, Lumber Mill, Gear Workshop, Smelter, Food Factory, Metalsmith …):
  - Before: `place_building(check=True)` returns `powerConnections`; at least one target tile must be a shaft, wheel or powered building whose own point faces back. If none does, plan the shaft run first or pick another spot.
  - After it's built: some `powerConnections` entry shows `connected: true` (in `list_buildings`), and no "needs power" status. `connected` stays false until the shaft or wheel it meets is finished, so a not-yet-linked building is fine while its partner is still a site.
  - `watch.py` does this automatically: when a power building finishes unlinked it waits while a construction site sits at one of its power points (prints `power: waiting on a site`), and stops with `NO POWER LINK` only when nothing built or being built meets it.
  - `connected: true` only means it touches something. A link to a dead-end shaft still shows "needs power", so check statuses too.
  - Also check the network has spare power for it (total generation vs total use).
- **One drought-proof generator per network**, sized to the food chain at least (Fermenter 50 + Food Factory 120 = 170 hp, plus the mill if planks are needed): Gravity Battery (400 SP) charged by the wheels, Geothermal Engine on a geothermal field (160 SP), Steam Engine (logs + water), or a Large Power Wheel as the last resort.

### Shortage rules
- **Not enough power: pause the least needed leaf buildings first** (never a relay). Order: wellbeing extras → Gear Workshop (if gears stocked) → Metalsmith / Smelter → Lumber Mill (if planks stocked) → … Fermenter and Food Factory last.
- **A full building stops working, and its workers stand idle.** Output full: add storage beside it, a Hauling Post, or haul priority; if it can't be cleared, pause it and move its workers. Input stores full upstream count too.

### Industry
- Store every output beside its producer (piles for logs/planks, warehouses for gears and food) with its good set; obtain-stores at workshop doors, a Hauling Post per cluster.
- Every recipe building gets a recipe set on placement.

---

## 4. Food, water, population and hazards

### Food strategy
- **Drought-proof food chain first:** big stockpiles of **raw Corn and Mushroom** that can be processed during a drought (Food Factory, Fermenter on drought-proof power). Raw stock in warehouses is the reserve; crops in the ground are not.
- Mix: river/pond-watered kohlrabi (fast, 3 days), corn (10 days, best per plot via Food Factory), indoor Hydroponic Gardens (ignore drought and badtide).
- **Kohlrabi is the opening crop only; phase it out slowly.** It's the weakest food per plot (~0.67 vs ~1 for corn via the Food Factory), dies after 2 dry days and ties up farmhouse labour with constant replanting. Once the Food Factory runs on drought-proof power and rations flow:
  - Switch one field block at a time: `clear_planting` the block, then `plant_area` Corn as tiles are harvested (`plant_area` skips tiles with a growing crop).
  - Switch a block only while food days stay on target without it, and never inside a hazard warning (corn takes 10 days).
  - Stagger the switches so corn harvests overlap.
  - End state: corn, mushroom and other processed food. Keep a small kohlrabi patch only if its wellbeing (food variety) is worth the plots.
- **Count the water that food and power use:** Hydroponic Garden ≈ 5 water/day (mushroom) or 5/day (algae); Discharge ponds; Steam Engine burns water. Add these to the water reserve.
- Farmhouses: harvest-first by default; with 2+ houses about 1 in 3 on planting first. Check `PlantingPrioritized` and `Emptiable` whenever food days drop with full fields.

### Levels
- **Food days** = edible stock / (3 × beavers). Floor 3, always. Zero food is a cliff.
- **Hazard reserve** (1.5 × longest hazard so far + 2 days, scaled to beavers): currently water ≥ 26 × beavers, food ≥ 32 × beavers. Raise it every time a hazard runs longer. Raw processable stock (corn, mushroom) counts toward food only if its processing has drought-proof power.
- Water reserve = drinking + hydroponics + ponds + steam engines + the 1-1.5 days the river needs to refill after a drought.

### Population
- At least 3 pods from day 5 (founders die of old age in cycles 1-3), ~beavers/10 + 1 when the gate allows.
- **Growth gate:** food days trend up over several chunks AND production (not stock) covers the target population through the longest hazard AND beds, pumps, tanks and processing exist for it. Plan farm capacity for the population 20-30 days ahead.

### Hazards
- **3 days before every warning:** food days, water days, storage room for the reserve, crops by held water, pods vs food, power for food buildings.
- **Drought:** tanks full → pause all pumps at the start so the river stays high; farms High priority, support Low; harvest early; check field moisture and `/api/map/plants` dying counts daily; re-staff pumps when < 1 day remains.
- **Badtide:** close every inlet floodgate; fields beside clean held water or ponds only; stock food for the badtide + 3 days of regrowth.
- **After:** replant at once, check paused food jobs are back on, record usage in `goals.md`.

---

## 5. Building and job management (new)

### Daily job budget (once per in-game day)
- **Adults vs job slots:** target 0-2 unemployed (spare haulers), no key building short-staffed. Trim with `set_workers`; don't build workplaces nobody can staff.
- **Labour forecast:** count kits maturing in the next 6 days before queuing a new workplace.
- **Building caps** (add only past these):

| Building | Rule |
|---|---|
| FarmHouse | 1 per ~55 plots in its 20-tile range; extra houses only for new fields out of range |
| Deep Water Pump | about 1 per 5 beavers, more only if tanks don't fill |
| Gatherer Flag | while ripe bushes stay unpicked |
| Lumberjack | 1 per ~40 grown trees in its area; move flags before 'grown' hits 0 |
| Forester | 2+ by cycle 2, more while logs < target |
| Fermenter | 1 per 2-3 Hydroponic Gardens |
| Hauling Post | 1 per industry or farm cluster, so stores and workshops are a short walk along a connected path; extras on Low priority |
| Builders' Hut | 1 per build area; extras on Low priority to take spare beavers and speed up big builds |
| Inventor | only while science is being spent |

### Workplace priority tiers
1. **VeryHigh:** pumps when water days < target, farmhouses and food processing.
2. **High:** gatherers, builders while key sites wait.
3. **Normal:** wood (lumberjacks, foresters, mill), industry with demand.
4. **Low:** hauling posts, spare builders' huts, inventors, workshops with full stores, wellbeing. Spare huts and posts on Low are the place for unemployed beavers: they work when nothing more important needs them.

### Paused register
- Every pause is logged with a **reason and a resume condition** (`harness/pause_ids.txt`). The daily audit re-checks each one; food and water jobs are never left paused past their condition.

### Crisis mode (food days < 1.5 or starving)
- Food, water and power jobs only; pause the rest; concentrate labour on a few key food buildings fully staffed rather than many half-staffed.

### Daily audit checklist
- Storage with no good set; recipe buildings with no recipe.
- Buildings with full output, `Emptiable` marked, `not connected`, `no available workers`, unpowered.
- Farmhouse modes; lumberjacks with no grown trees; sites stuck at 0%: check the site's distance to a properly connected path (its door/`pathTile` must sit on a path linked to the district; a site beside a path fragment that isn't connected never gets builders or materials), not its distance to a builders' hut.
- Unspent science.

---

## 6. Bot watch (Haiku helpers, new)

**Recommendation:** split monitoring into two layers.
1. **Deterministic steward (python, zero tokens)** in `watch.py`: the mechanical checks from the daily audit, plus whitelisted auto-fixes that are always safe (set Water on new tanks, unmark `Emptiable` on food buildings, harvest-first on new farmhouses, flag any capped stock). It prints one-line findings in the report.
2. **Haiku 5.5 auditor (low effort, background, read-only + whitelist)** once per in-game day or on demand: reads the colony state, cross-checks the job budget, building caps, pause register and power balance, and returns a short digest (≤ 10 lines) ranked by urgency. It may apply only the same safe whitelist; it never places, demolishes, narrates, changes pods, or runs `watch.py` (one game driver at a time).

I keep every real decision (placements, pods, hazards, priorities beyond the whitelist) and narrate them.

**Built (2026-10-14):** `harness/audit.py` (also printed as `AUDIT` lines at the end of every `watch.py` report; `python audit.py --no-fix` standalone). `list_buildings` now carries `setup` (`good`, `recipe`, `emptying`, `plantingFirst`). The Haiku auditor is the `colony-auditor` agent (`.claude/agents/colony-auditor.md`; it runs `audit.py --no-fix` plus a goods/colony read). Being tested on the Pressure test game.
