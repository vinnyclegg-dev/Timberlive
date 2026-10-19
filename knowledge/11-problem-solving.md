# 11 — Problem solving: symptom → detect → cause → fix

Each entry follows the same pattern:
- **Detect:** the tool calls that confirm the problem.
- **Causes:** ranked, most likely first.
- **Fix:** normal player actions only (place, demolish, `demolish_resources`, set workers, priority, pause, storage goods, plant, mark trees).

References: "09" = `09-buildings.md`, "10 §n" = `10-game-systems.md`, "05 §n" = `05-failure-modes.md`, "03" = water engineering.

Quick tool map:

| Question | Tool |
|---|---|
| How many beavers, homeless, jobless, wellbeing? | `get_colony` |
| Stock and capacity per good | `get_goods` |
| Which need is failing, how many critical | `get_needs` |
| What the game is warning about | `get_alerts` |
| Why one building is idle | `inspect_building` → `statuses`, `pathTile`, workers, inventory |
| Terrain, water depth, moisture, objects | `view_map` (HEIGHTS, WATER, MOISTURE, OBJECTS); keep it to 40x40 |
| Everything on one tile | `inspect_tile(x,y)` |
| Can beavers reach it? | `walk_distance(x,y,z,targets)` (null = no) |
| Map features, slopes, water, farmland | `map_summary(section=features / links / water / badwater / farmland / resources / terraces)` |
| Counts and filters | `list_buildings(template_filter=...)` |

---

## A. Movement and map

### A1. Need to change height (reach a terrace, a cliff top or a field)
- **Detect:**
  - `walk_distance` returns null.
  - `view_map` HEIGHTS shows a step of 1 or more between the path and the target.
- **Fix, in this order:**
  1. **Look for a natural Slope first.** Run `map_summary(section="links")`: it lists Slopes with orientation (`o#`) and the places that still need Stairs. You can also check the OBJECTS grid or `inspect_tile`.
     - A Slope is free, two-way Stairs (10 §16). Unrotated, its high side is −Y.
     - Run a path to its low end and its high end.
  2. No Slope nearby: build **Stairs** (1 Log 4 Plank, 70 SP) on the low tile, facing the step.
     - Read `pathTile` afterwards. If it's wrong, demolish and retry with another rotation (06).
  3. Two or more levels: stack Stairs on Platforms, or use Spiral Stairs (350 SP).
  4. Late game: a Vertical Tubeway, or a Terrain Block ramp (1000 SP, Dirt).
- **Lesson:** the first playthrough spent planks on Stairs next to unused natural Slopes (08 "Map and paths").

### A2. Site or building is "Unreachable"
- **Detect:**
  - `inspect_building` status says unreachable, or no builder ever arrives.
  - `walk_distance` from the District Center returns null.
- **Causes:**
  1. Missing path link, or the entrance faces away from the path (`pathTile` is not on a path).
  2. A height step with no Slope or Stairs (A1).
  3. Water in the way: a flooded path, or a river with no crossing.
  4. **Thorns** or another natural object blocking a corridor (A3).
  5. Another district's territory: no District Crossing.
- **Fix:**
  - Add the path or Stairs.
  - Re-place the building with the door toward the path.
  - Cross water with a path on a Dam or Levee, a Suspension Bridge, or a natural Overhang (10 §16).

### A3. Thorns block a route or farmland
- **Detect:** OBJECTS grid or `map_summary(section="features")` shows `Thorns`. Paths and fields stop at them.
- **Causes:** Thorns block movement, moisture and contamination.
- **Fix:**
  - First, route around them if that costs only a few tiles.
  - Otherwise `demolish_resources` or demolish them. This takes 10 h per tile, and each check has a 0.1 chance of Injury −1 (10 §10).
  - Have a Medical Bed running before you start. Use 1–2 builders.
  - Keep Thorns that shield fields from a badwater channel.

### A4. Everything is slow far from the center
- **Detect:**
  - Long `walk_distance` values.
  - Red paths more than 70 tiles from the District Center.
  - Workers spend most of the day walking (`working_beavers`).
- **Causes:**
  1. One district covering too much map.
  2. Storage far from the producers.
  3. No faster links.
- **Fix:**
  - Put a buffer store beside each workshop (08 "Storage").
  - Build a second District Center plus a District Crossing (10 §11).
  - Later: Tubeways (IT and FT) or Ziplines (FT only).

### A5. Starting a new map: scouting checklist
- `map_summary(section="overview")`, then `features`, `links`, `water`, `badwater`, `farmland` and `resources`.
- Note every:
  - Slope (free stairs)
  - Natural Dam and Blockage (water you can release or keep)
  - Natural Overhang (free bridge)
  - Relic (science)
  - Ruin Column and Underground Ruins (scrap)
  - Geothermal Field
  - Aquifer or Ancient Aquifer Drill
  - Reserve store (pre-filled with one good: Explosives or Water)
  - Unstable Core (no-build zone = its radius + 1 in 3D; read it with `inspect_building(id, all)` or by clicking it)
  - Badtide Drain and delayed source (future badwater)
- Write the coordinates in `goals.md` so later decisions can use them.

## B. Food

### B1. Food falling, Hunger critical
- **Detect:**
  - `get_goods` edible total falling.
  - `get_needs` Hunger critical above 0.
  - `get_alerts` starvation.
- **Causes:**
  1. Crops died (dry, flooded, or badwater soil): B2.
  2. Too few farmers, or farms paused or low priority.
  3. Production is raw, inedible goods: Cassava, Corn, Soybean, Eggplant without a Fermenter or Food Factory (10 §7).
  4. Population outgrew the fields.
  5. Food not stored: no warehouse set to the food ("No storage").
- **Fix:**
  - Raise farm and gatherer priority to VeryHigh, and move free workers there.
  - **Pause the Breeding Pods** only if food will truly run out before the next harvest (user rule).
  - Pause non-food workplaces to free workers (05 §1).
  - Plant Kohlrabi (3 days) for a fast recovery.
  - Build the processor for any raw crop you already have.
  - Add warehouses set to each food.

### B2. Crops dying or not growing
- **Detect:**
  - `inspect_building` on the farm.
  - `view_map` MOISTURE: no `#` under the fields.
  - WATER grid: water standing on crop tiles, or contamination on nearby water.
- **Causes (ranked):**
  1. **Drought:** the river dropped and the soil dried. Each crop has a "dies dry" time, 0.25–3.5 days (10 §7).
  2. **Badtide:** water at contamination 0.53 or more gives no moisture, and contaminated water poisons soil within 7 tiles (10 §6). Crops die even though water is present.
  3. Flooding: water on non-aquatic crops.
  4. Aquatic crops (Cattail, Spadderdock, Mangrove) not under exactly 1 depth of water.
  5. Fields planted on a ledge or out of moisture range.
  6. No planter in range, or `plant_area` never set.
- **Fix:**
  - Drought: pause water pumps once tanks are full, so the river stays high. Dam the river to hold water by the fields. Plant hardy crops (03 layouts).
  - Badtide: before it starts, close a Floodgate or Levee line upstream of the fields so badwater can't reach them (08 "Water and hazards"). Use clean stored water through a Discharge to keep a moat wet.
  - Replant as soon as the soil is moist and clean again.
  - Flooding: lower the dam, or re-plant on higher moist ground.

### B3. Breeding Pods not producing (IT)
- **Detect:** `inspect_building` on the pod: paused, missing Water or Berries, or no workers to deliver.
- **Causes:**
  1. Paused (by you, in a shortage).
  2. No Berries in stock: gatherers out of reach of the bushes, or the bushes died.
  3. Haulers busy elsewhere.
  4. No free housing: children still need homes.
- **Fix:**
  - Unpause when food and water stocks pass the reserve.
  - Plant blueberry bushes near a Gatherer.
  - Set pod priority High.
  - Add Barracks.

## C. Water

### C1. Water stock falling, Thirst critical
- **Detect:**
  - `get_goods` Water falling.
  - `get_needs` Thirst.
  - `inspect_building` on the pumps: "No water", low output, or no workers.
- **Causes:**
  1. Drought dried the pump's water body.
  2. Badtide contamination: output × (1 − contamination).
  3. Pumps paused (for crops) and never resumed.
  4. Too few tanks to carry the colony through the hazard.
  5. No workers at the pumps.
- **Fix:**
  - Move a pump into deep water, or use a Deep Water Pump (depth 6).
  - Hold water behind dams (03).
  - Add tanks (they are set to Water automatically).
  - Raise pump priority.
  - Resume pumps when the drought ends.
  - Size the reserve to 1.5x the longest hazard (02).

### C2. River dries every drought
- **Detect:** WATER grid depth near 0 by mid-drought. `map_summary(section="water")`.
- **Causes:**
  1. No dam at the outflow.
  2. Shallow, wide pools evaporate fast (10 §5).
  3. A natural Blockage or Natural Dam was demolished.
  4. Pumps draining it.
- **Fix:**
  - Dam the outflow (0.65 per Dam; a Levee holds a full 1.0).
  - Build deep, narrow reservoirs upstream.
  - **Keep natural dams** that hold useful water.

### C3. Badwater reaching fields or homes
- **Detect:**
  - `map_summary(section="badwater")`.
  - WATER grid contamination.
  - OBJECTS: `BadwaterSource`, `BadwaterSeep`, `BadtideDrain`.
- **Causes:**
  1. Every source turns bad in a badtide.
  2. A Badtide Drain only flows in badtides, so it surprises you if you didn't scout it.
  3. A delayed source switching on after cycle 5 + 10 days ("Activates soon").
  4. Badwater seeps that were always there.
- **Fix:**
  - Levees and Floodgates to divert the badwater into a dead-end channel.
  - Keep fields more than 7 tiles (horizontal) from badwater, or uphill of it (+1 height = 5 tiles).
  - Irrigation Barrier (IT) or Contamination Barrier (FT) along the field edge.
  - Late game: cap a Badwater Source with a Badwater Pressurizer, or pump it for Explosives and Extract.
  - Badtide Drains and water sources can't be demolished; you can only redirect their flow.

### C4. Need to drain or release water (reclaim land, open a channel)
- **Detect:** OBJECTS `Blockage`, `NaturalDam`; WATER depth behind them.
- **Fix:**
  - Demolish the Blockage or Natural Dam (4 h each).
  - First check `view_map` HEIGHTS downstream for buildings that would flood.
  - Release it in temperate weather, never just before a drought.

## D. Wood, construction, workers

### D1. Wood collapse (Log stock near 0)
- **Detect:** `get_goods` Log; lumberjacks idle (`inspect_building`: "no trees").
- **Causes:**
  1. The cutting area is used up.
  2. No Forester replanting.
  3. ChippedTeeth (−75% cutting success; never heals on its own): D3.
  4. Logs piled with no Industrial Pile space.
- **Fix:**
  - Mark a new `mark_tree_cutting` area. Never strip the only stand (user rule).
  - Forester planting Oak (8 logs per tree).
  - Teeth Grindstone near the lumberjacks.
  - Add Industrial Piles (05 §6).

### D2. Builders idle or construction stalls
- **Detect:** `inspect_building` on the site: "Lacks resources", "Unreachable", or no builder assigned. `get_colony` unemployed count.
- **Causes:**
  1. Missing materials (Plank, Gear, Scrap, Metal).
  2. The site can't be reached (A2).
  3. Builders on other sites with higher priority.
  4. Too few builders.
  5. A stump or plant on the tile.
- **Fix:**
  - Produce or haul the missing good.
  - Raise construction priority (`set_priority`).
  - Add builders at the District Center or a Builders' Hut.
  - Clear the tile with `demolish_resources`.

### D3. Workers can't work (Injury, ChippedTeeth, contamination)
- **Detect:** `get_needs` Injury, ChippedTeeth or BadwaterContamination critical; `get_alerts`; fewer active workers.
- **Causes:**
  1. Workshop accidents (09 §1 risk list).
  2. Demolishing Thorns.
  3. Wading in badwater.
  4. Lumberjacking.
- **Fix** (10 §10):
  - **Injury:** Medical Bed (+0.36/day versus 0.1/day natural healing).
  - **ChippedTeeth:** Teeth Grindstone.
  - **Contamination:** Decontamination Pod (IT) or Antidote (FT). It never heals on its own.
  - Prevention: keep paths out of badwater.

### D4. Idle or unemployed beavers, or jobs left empty
- **Detect:** `get_colony` unemployed and free jobs. `list_buildings` for paused workplaces.
- **Causes:**
  1. Workplaces paused.
  2. Worker slots set too low or too high.
  3. Homes too far from the jobs.
- **Fix:**
  - Trim multi-worker buildings to what they need, and give the spare beavers food or water jobs.
  - Use `set_workers` (minimum 1) or `set_paused`.

### D5. Hauling gridlock: goods piled at a producer, consumer starved
- **Detect:** the producer's `inspect_building` inventory is full; the consumer says "Lacks resources".
- **Causes:**
  1. Storage far away.
  2. No storage set for that good.
  3. Too few haulers.
- **Fix:**
  - A buffer store beside both buildings.
  - Hauling Post with 1–2 workers.
  - Storage goods set with `building_action`.

## E. Storage

### E1. "No storage" or a producer stopped full
- **Detect:** `inspect_building` statuses; `get_goods` shows capacity full.
- **Causes:**
  1. No store of the right type: Pileable needs a Pile, Box needs a Warehouse, Liquid needs a Tank (10 §12).
  2. The store isn't set to that good.
  3. Every store is full.
- **Fix:**
  - Build the right store type and set its good.
  - **Look for map Reserve stores first:** Reserve Pile, Reserve Tank and Reserve Warehouse (10 §16). Connect them with a path and check them with `inspect_building`, they come pre-filled (Explosives or Water).

## F. Power and industry

### F1. Machine slow or stopped: not enough power
- **Detect:** `inspect_building` power status, supply and demand on the network.
- **Causes:**
  1. Water wheels stopped (drought, or no flow).
  2. Demand higher than supply.
  3. A broken shaft link: not attached at the wheel's middle, or a gap.
  4. A beaver-powered wheel with no workers.
- **Fix:**
  - Build wheels in a spillway or below a dam.
  - Add a Gravity Battery for droughts.
  - Reconnect the shafts.
  - **Geothermal Field nearby?** A Geothermal Engine there gives a constant 400 power, droughts included (10 §16).

### F2. Need Scrap or Metal and have none
- **Detect:** `get_goods` Scrap 0; `map_summary(section="resources")`.
- **Fix:**
  1. **Ruin Columns:** a Scavenger Flag in range; 15 Scrap per height level, 1.8 h each.
  2. **Underground Ruins (5x5):** a Mine or Efficient Mine must sit on them. This is the endless source.
  3. Pre-filled Reserve stores (if any).
  - Then Smelter (Metal Block) and Metalsmith (IT Metal Part).

### F3. Need science fast
- **Detect:** science stock versus the next unlock.
- **Fix:**
  1. **Relics:** demolish them from the top for 200, 800 or 3000 SP (2, 4 and 8 h). Check `map_summary(section="features")`.
  2. More Inventors.
  3. IT Numbercruncher (powered) or FT Observatory.
  - Spend on food and water security first.

## G. Hazards and dangerous map objects

### G1. Unstable Core on the map
- **Detect:** `map_summary(section="features")` lists `UnstableCore`. `inspect_building` shows "Explodes soon" from cycle 5.
- **Facts:** it can't be demolished or disarmed. It explodes with radius 5 after a 10.5-day countdown that starts in cycle 5 (10 §16).
- **Fix:**
  - Build nothing valuable within 5 tiles.
  - Move beavers' paths and jobs out of range before the countdown ends.
  - Don't put reservoirs or dams next to it: [web] the blast also removes terrain and water.

### G2. Water source or seep turned bad, or a new one started
- **Detect:** `get_alerts`; WATER contamination rising; source status "Activates soon".
- **Fix:** see C3. Delayed sources start from cycle 5 + 10 days, so build the diversion levees before then.

### G3. Aquifer or underground water
- **Detect:** OBJECTS `Aquifer`, `AncientAquiferDrill`.
- **Fix:**
  - Power and path-connect an Ancient Aquifer Drill. On a plain Aquifer, build an Aquifer Drill (400 SP, 400 power). Either one is a drought-proof water source.
  - Aquifers also turn bad during badtides, so stop or divert them then.

### G4. Hazard reserve too small
- **Detect:** compare the water and food stock with 1.5 × longest hazard × daily use per beaver × beavers (02).
- **Fix:**
  - Add tanks and warehouses.
  - Push farms and pumps to High priority before the "approaching" warning.
  - Record each hazard's actual usage in `goals.md`.

## H. Wellbeing and population

### H1. Wellbeing low; beavers slow and dying young
- **Detect:** `get_colony` wellbeing; `get_needs` needs below 0.5.
- **Causes:**
  1. Only one food type.
  2. No Social, Fun or Aesthetics buildings.
  3. Contamination or injury penalties.
  4. Wet fur (no shower).
- **Fix:**
  - Add food variety: each new food is +1 to +3 (10 §8).
  - Cheap +1s: Campfire, Scratcher, Shrubs and decorations.
  - Rooftop Terrace on Platforms.
  - Double Shower standing in water.

### H2. Population shrinking (old age)
- **Detect:** deaths in `get_alerts`; few kits.
- **Causes:**
  1. Low wellbeing shortens life (10 §9).
  2. Pods paused for too long.
- **Fix:** keep the pods running whenever stock allows, and raise wellbeing.

### H3. Bots slowing or idle
- **Detect:** bot workplaces slow; `get_needs` bot needs.
- **Causes:**
  1. No Energy (IT) or Biofuel (FT).
  2. No Catalyst, Grease or Punch Card (work speed 0.65 instead of 1.7).
  3. Age past 70 days.
- **Fix:**
  - Build the supply chain before the bots.
  - Replace bots from the Bot Assembler before they wear out.
