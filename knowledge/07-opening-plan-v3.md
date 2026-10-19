# Opening plan v3 (works on any map)

Every step opens on a measurable gate, not a fixed day. Maps, hazard timing and hazard length change between games. This replaces v2 (`07-opening-plan-v2.md`), whose day-based timings were built around one map.

## Rules of thumb (from runs so far)
- **Food:** about 3 food per beaver per day.
- **Water:** about 2.5 water per beaver per day.
- **Farm size:** 4–5 kohlrabi plots per beaver. One farmhouse per 40–50 plots.
- **Hazard reserve:** beavers × daily use × (longest hazard so far + 3 days of regrowth) × 1.5. Before the first hazard, assume it lasts 4 days.
- **Production must beat consumption** before the population grows: plots × 2 ÷ 3 days must exceed beavers × 3.
- **Overbuild, don't break even (user rule):** aim for 1.5–2× consumption. Run 3 measured ~2.8 water per beaver per day, and one deep pump on a small creek gave only ~18/day, so plan about 1 deep pump per 5 beavers (3 at the start for 13 beavers). Start with 3+ gatherers, and put the first field on land that stays moist in a drought (next to deep or dammed water).

## Priorities (used in every phase)
There are two separate controls, and both are set with `set_priority`:
- **Building priority** applies to sites under construction. It decides which site the builders and haulers go to first.
  - **VeryHigh:** whatever unblocks survival right now, such as the first pump, a tank when water is low, or a farmhouse in a food crisis.
  - **High:** whatever unblocks the next phase, such as the Inventor, the Forester or hazard defences before a warning.
  - **Normal:** everything else.
  - **Low:** decorations and long-term projects.
- **Workplace priority** applies to finished buildings. It decides which jobs fill first when there aren't enough beavers.
  - **VeryHigh / High:** food and water (farmhouses, gatherers, pumps), and the Fermenter while there is cassava to process.
  - **Normal:** wood (lumberjacks, foresters, mill) and builders while sites are waiting.
  - **Low:** inventors when there's no science to spend, hauling posts, and gear workshops whose stores are full.

When to change them:
- **Re-rank whenever the situation changes.** At a hazard warning, raise farms to VeryHigh and put defences top of the build list. After a crisis, put them back.
- **Use priority before pausing.** Pause only when there are far more jobs than beavers, when beavers are starving, or when a building is idle with nothing to do.

## Benchmark (a benchmark player's colonies, `12-player-build-study.md`)
- Normal Iron Teeth at 500 beavers (New Beaverville): about 170 water stored and 5 crop plots per beaver, 8 deep pumps and 3 FarmHouses per 100 beavers.
- Easy colony by cycle 4 at about 30 beavers: 10+ Dams and Levees, 4 deep pumps, 3 Inventors, 2 Scavengers, 6 lumberjacks + 2 Foresters (Foresters VeryHigh), one big bush patch plus one big field.
- Later: one District Center with Tubeways, 18 h work hours, Hauling Posts and spare Builders' Huts VeryLow.

## Phase 0: Scout before placing anything (game paused)
- [ ] **Survey first:** `survey_map.py scan`, then read `overview`, `water`, `links` and `goals`. The checklist below is mostly answered by it.
- [ ] **Natural Slopes:** the map often has ready-made ramps between heights (`features`/`links`). Use them before building Stairs.
- [ ] **Water sources:** find each one, which way it flows, and which ones turn bad in a badtide.
- [ ] **River:** find the deepest pools (for pumps), the fastest flow (for water wheels), and narrow channels (for gates and dams).
- [ ] **Moist land:** find flat areas of 150 tiles or more within about 15 tiles of the river.
- [ ] **Resources:** note the nearest big tree stand, berry bushes, ruins (scrap) and slopes or heights.
- [ ] **Choose the base:**
  - by clean, flowing water, upstream of any badwater
  - next to flat moist land and trees
  - with room to grow in two directions
- [ ] **Plan the corridors:** a main road, plus stairs wherever the land changes height, up *or* down (cliffs, terraces, canyons, river banks). Where a corridor crosses water, use a dam or levee, since beavers can walk on them. Leave space for future fields, and don't wall off any direction with fields or forests.

## Phase 1: Opening batch (unpause within about a minute)
- [ ] 2–3 lumberjack flags at the big stand, with the cutting area marked and a log pile next to them.
- [ ] A Deep Water Pump at a deep spot, plus 2 tanks set to Water. Give both VeryHigh building priority, and the pump VeryHigh workplace priority.
- [ ] A gatherer flag on the berries, with a warehouse.
- [ ] A farmhouse and about 50 kohlrabi plots on moist land (check MOISTURE and heights first). Give the farmhouse and the gatherer High workplace priority.
- [ ] Check every door (`pathTile`) and status straight away.

## Phase 2: Wood that renews itself
- [ ] An Inventor (High building priority) to earn 30 science, then unlock the **Forester**.
- [ ] A Compact Water Wheel on flowing water, linked by shafts to an Industrial Lumber Mill (no beaver power).
- [ ] The Forester replants behind the lumberjacks. Plant Birch/Pine for quick wood and Oak for long-term wood.
- [ ] **Gate:** don't build big wood projects until logs hold above 50 without dropping.
- [ ] Keep foresters' planting areas off future farmland.

## Phase 3: Build the food engine before the population grows
- [ ] Have a second farmhouse and enough plots for 1.5× the current beavers.
- [ ] Give new farmhouses High building priority whenever production is below consumption.
- [ ] Add cassava and a Fermenter together, with warehouses for both.
- [ ] Plant in 2–3 batches a day apart, so harvests overlap and there is never a day with zero food.
- [ ] Have food storage capacity of at least the hazard reserve.
- [ ] Set new farmhouses to harvest first.

## Phase 4: Water and hazard defences (before the first warning)
Give dams, gates and tanks High building priority, raised to VeryHigh once a warning appears.
- [ ] Dam the river's outlet, downstream of the pumps and fields, so a pool survives droughts.
- [ ] Build a reservoir **upstream** of the fields (dams or levees) so the river by the fields keeps water.
- [ ] Find the inlet channel where badwater would enter. Plan a Floodgate or Levee line there to keep clean water by the fields during badtides.
- [ ] Have tank capacity of at least the water reserve, and add more pumps when they can't keep up.

## Phase 5: Controlled growth
- [ ] Barracks before pods: free beds should be at least the kits on the way.
- [ ] **Pod gate:** run the Breeding Pods only while food and water are above the reserve *and* production beats consumption.
- [ ] For every +5 beavers: add about 20 plots, and a farmhouse when the plots pass 45 per farmhouse.
- [ ] Set job priority: food and water first, builders while sites are waiting, haulers and inventors Low.

## Phase 6: When a hazard warning appears
- [ ] Re-rank building and workplace priorities for the hazard.
- [ ] Check stock against the reserve. If it's short, pause the pods at once and move spare beavers onto food.
- [ ] **Drought:** with the tanks full, pause most pumps so the river stays high. Check WATER by the fields every day.
- [ ] **Badtide:** close the inlet gate and keep the pumps away from badwater. Badwater doesn't moisten soil, so unprotected fields die.
- [ ] **When it ends:** replant at once (watch the moisture), and record how much food and water it used in `goals.md`.

## Phase 7: Tech path (spend science as it comes in)
1. Forester, then Gear Workshop and Builders' Hut.
2. Medium Tank, Levee and Floodgate (hazard defences).
3. Road to the ruins, then Scavenger Flag and Metalsmith. If the ruins are far, set up a second district.
4. **Hydroponic Garden.** It grows food indoors, so droughts and badtides don't touch it.
5. Wellbeing buildings (Campfire, Shrubs, Scratcher, Shower and so on) once food is safe.
6. Automation (Lever, Relay, sensors) to run the floodgates by themselves.
7. Then work toward one of every building with `progress.py`.

## Daily routine (once per in-game day)
- [ ] Production versus consumption, for both food and water.
- [ ] Storage under 95% full. Fix full stores with more storage or by pausing the producer.
- [ ] Unemployed beavers or empty job slots: adjust worker counts.
- [ ] The building queue has the right site at the top, and the jobs that matter most are full.
- [ ] Unspent science: spend it.
- [ ] Checkpoint.
