# 00 — Overview (Timberborn 1.1.2.7, Steam experimental)

Tags: [bp] = game blueprints, [code] = decompiled assemblies, [web] = see sources.md. Numbers are in 02-numbers.md.

## Core loop
1. Beavers need **water** (2.12/day) and **food** (2.67/day) each, plus sleep (a home) [bp].
2. Collect **logs** (Lumberjack flag), turn them into **planks** (Lumber Mill), then **gears** (Gear Workshop, needs power). Logs are the bottleneck for everything early.
3. Generate **science** (Inventor: 16 SP/day per worker) to unlock buildings.
4. Every cycle = **temperate season**, then a **hazard** (drought or badtide).
   - Temperate: stockpile water and food, and build reservoirs.
   - Hazard: rivers stop (drought) or turn toxic (badtide). Survive on stock and stored water.
5. Grow population (homes for FT; breeding pods for IT). Raise **wellbeing**, which boosts work speed, lifespan and movement. Build up to industry (metal, treated planks, power, bots), then monuments and the faction **Wonder**.
6. Districts: each District Center runs its own logistics. Goods move between districts only through District Crossings / migration settings. Keep it to one district until about 60–80 beavers or long travel distances (rule of thumb, [web]).

## Win / lose
- **Lose:** every character (beavers and bots) is dead. There's a 10-tick delay before the game-over check fires.
  - **Exception (IT):** a Breeding Pod that already holds enough nutrients to finish an embryo keeps the game alive ("phoenix protocol") [code GameOverChecker].
- **No hard win.** The goals are surviving cycles, achievements, and building the faction **Wonder**: Earth Recultivator (FT) / Earth Repopulator (IT). It costs 20000 SP plus about 1500–2000 each of gears, treated planks and metal blocks [bp]. The first launch on a map counts as that map's "win": a summary window, a completion badge, and **Flexible Start** (choose your DC location) unlocked for future games [web W-Wonders]. The game continues afterwards.
- On a fresh profile, Iron Teeth may be locked until a Folktails colony reaches average wellbeing 15 [web wiki Folktails] (unverified in this build).
- Achievements track surviving droughts and badtides, and so on.

## Time and speeds
- 1 day ≈ 7.7 min real at 1× (768 ticks × 0.6 s). 24 h per day; daytime is 16 h; working hours are adjustable (default ≈ 16 h) [bp/code].
- Speeds: pause (Space or `), 1× (key 1), 3× (key 2), 7× (key 3). Building pause = P. Tick-once = `.` [bp KeyBindings].
- **Speeds above 1× are throttled as population grows.** 7× falls to about 3.4× at 200+ characters [code GameSpeedThrottler]. Expect late game to run slower in real time.
- Autosave every 10 min [bp].

## Cycles and hazards [bp NewGameModes, code HazardousWeather*]
- Cycle = temperate (Normal: 13–17 days) followed by a hazard.
- **Drought:**
  - Water sources stop flowing, so rivers and shallow pools dry out.
  - Unirrigated soil dries, crops die after their "dies dry" time (carrots 2 d, wheat 0.5 d), and water wheels stop.
  - Normal: duration ramps from about 2–3 days in cycle 1 to 5–9 days by cycle 6.
- **Badtide:**
  - Water sources emit badwater (contaminated).
  - Water pumps' output scales with (1 − contamination), so they drop to ~0 on a fully contaminated river [code WaterInputManufactoryLimiter].
  - Contaminated water spreads soil contamination up to 7 tiles, which kills crops and trees.
  - Beavers wading in contaminated water (≥5%) can become infected: 3 days of incubation, then −10 wellbeing, −70% movement and **can't work**.
  - **No natural recovery.** Cure with Antidote (FT Herbalist) or a Decontamination Pod (IT) [bp/code].
  - Normal: possible from cycle 5, 40% chance per cycle, 4–8 days (ramping).
- The weather panel warns "Drought/Badtide approaching". A Weather Station with early activation can signal up to 3 days before the hazard [code/loc].
- Hard mode: temperate only 5–8 days, droughts and badtides up to 15–30 days, start water 0. Easy: consumption ×0.4 and short hazards.

## Difficulty settings (presets; custom games can change them)
- Starting beavers (all presets: 9 adults + 4 kids)
- Starting food and water
- Food and water consumption multipliers
- Temperate, drought and badtide duration ranges with "handicap" ramps
- Badtide start cycle and chance
- Injury chance
- Demolition refund
- Toggles: droughts on/off, badtides on/off

Full table in 02-numbers.md.

## Factions — key differences [bp]
| | **Folktails** (FT; recommended first) | **Iron Teeth** (IT; harder, industrial) |
|---|---|---|
| Housing | Lodge 3 beds (12 Log, 0 SP); Double 6, Triple 9, Mini 1. **Lodges breed kits automatically.** A lodge with a free bed and 2+ adult residents has an **18.75% chance per day** to spawn a kit [code ProcreationHouse]. Full lodges don't breed, so control growth by bed count | Barrack 10 beds (40 Log, 0 SP), Rowhouse 5, Large Rowhouse 8, Large Barrack 16. **No natural births** |
| Population growth | Births in lodges | **Breeding Pod** (10 Log): 1 water + 1 berries per day for 5 days → child. Advanced Pod (1000 SP): berries + extract → adult |
| Water | Water Pump (depth 2, 1 worker); Large Water Pump (depth 4, 3 workers, 400 SP) | **Deep Water Pump** (depth 6, 1 worker, 0 SP); later Deep Mechanical Pump |
| Early food | Berries (gatherer), carrots, potatoes → Grill (0 SP), sunflower; later wheat → Gristmill → Bakery, cattail/spadderdock (Aquatic Farmhouse), maple syrup | Berries, kohlrabi (3-day crop), cassava → Fermenter (0 SP, 50 power), corn → Food Factory, soybean/eggplant/canola oil, hydroponics (mushroom, algae) |
| Farmhouse | Efficient Farmhouse, **3 workers**, 25 Log | Farmhouse, 2 workers, 20 Log |
| Wood processing | Lumber Mill 1 worker, 50 power | Industrial Lumber Mill **2 workers**, 75 power (0 SP) |
| Power | Water Wheel 270 (50 Log), Power Wheel 50 (1 walker), Wind Turbines 150/300 | Compact Water Wheel 120, Large Water Wheel 540, Large Power Wheel 300 (4 walkers), Steam Engine 400 (logs + water) |
| Science | Inventor; Observatory (4 workers) | Inventor; Numbercruncher (no workers, 500 power) |
| Transport | Ziplines (+150% speed) | Tubeways (+300% speed) |
| Bots | Need Biofuel (Refinery) | Need Energy (Charging Station) |
| Badwater | Badwater Pump/Rig, Badwater Dome; Herbalist (antidote) | Deep Badwater Pump, Badwater Pressurizer, Decontamination Pod, Irrigation Barrier |
| Wellbeing extras | Dance Hall, Agora, Carousel, Books, Lido, Mud Pit | Motivatorium, Coffee, Exercise Plaza, Wind Tunnel, Mud Bath, Swimming Pool |

Practical faction notes:
- **FT** grow on their own. The danger is overpopulation outrunning water, food and beds, and children (non-workers) eating stock. Control growth by limiting free beds.
- **IT** grow only as fast as you feed pods (1 water + 1 berries per pod per day). Population is fully controllable. Early berries are critical, because they're the pod input and food at once. Both factions' starter homes cost 4 Log per bed. The IT barrack packs 10 beds into one site.
- Max wellbeing is about 84 for either faction.

## Version notes (verify against older guides)

Timeline [web Steam News API, wiki]:

| Release | Date | What it changed |
|---|---|---|
| Update 5 | 2024-01 | Badwater, badtides, contamination |
| Update 6 | 2024-10 | 3D water, Wonders, Sluice |
| Update 7 | 2025-05-08 | Ziplines, tubeways, tunnels; work speed +20% per wellbeing milestone; Forester 30 SP; birch 7 d |
| **1.0** | **2026-03-12** | Automation; Sluice removed; 9 starting adults; IT Metalsmith and Metal Parts; new map objects (seeps, aquifers, badtide drains, unstable cores, thorns, relics); source strength units changed (new 1 = old 2) |
| **1.1** | experimental 2026-06-10, main 2026-09-03 | Statistics tab, Airlock, Compact Mechanical Pump, 8-input relays, Fluid Dump→Discharge, Badwater Discharge→Pressurizer |
| Patch | 2026-10-06 | DC / Builders' Hut inventories no longer count in the top bar or Resource Counter (may or may not be in 1.1.2.7) |

Guides from before Update 5 (no badtides) are badly outdated, and pre-1.0 numbers often are too.
- **Sluice → "Fill Valve"** and **Valve → "Throttling Valve"**. They were renamed and reworked, and old saves auto-convert.
  - Fill Valve = one-way outlet that holds the downstream level at a target height.
  - Throttling Valve = one-way outlet with a flow limit (0–2).
  - The old sluice "auto-close on contamination" option is now built from a Contamination Sensor plus automation [bp BackwardCompatibleTemplateNames, code].
- The automation family replaces older names: Water Level Sensor → Depth Sensor, Water Contamination Sensor → Contamination Sensor, Wind Gauge, Latch → Memory, Clock → Chronometer, HttpServer/HttpClient → HTTP Lever/HTTP Adapter [bp].
- This build has buildings that older guides don't mention: Numbercruncher, Dirt Excavator, Terrain Block, Tunnel, Detonator, Aquifer Drill, Fill/Throttling Valves, Airlock, Gate. (Which version added each is unverified.) Guides from before 1.0 (2024 or earlier, "Update 5/6") use different numbers. Check 02-numbers.md before trusting them.
