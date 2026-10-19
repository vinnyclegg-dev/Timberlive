# 02 — Numbers (v1.1.2.7)

**Sources.**
- **[bp]** = game blueprints `Timberborn_Data\StreamingAssets\Modding\Blueprints.zip` (this exact build; authoritative).
- **[code]** = decompiled assemblies in `_decompiled\src`.
- **[derived]** = arithmetic on [bp] values; assumptions are stated.
- **[web]** = see sources.md.

Re-extraction instructions are at the bottom of this file.

## Time
- 1 tick = 0.6 s real at 1× speed. 1 day = 768 ticks = **460.8 s ≈ 7.7 min at 1×**. 1 hour = 32 ticks = 19.2 s [bp TickTime, DayNightCycle].
- Daytime = 16 h. Working hours default ≈ 16 h, adjustable (Chronometer default 0–16 h) [bp, code].
- Speed buttons: **0 (pause), 1, 3, 7**. Keys: Space or ` = pause, 1/2/3 = speeds 1/3/7 [code SpeedControlPanel, bp KeyBindings].
- **Population throttle:** speeds above 1 are scaled down as population grows. Effective speed = lerp(1, speed, s), where s goes from 1.0 at ≤30 characters to 0.4 at ≥200 characters. So at 200+ pop, "7×" ≈ 3.4× and "3×" ≈ 1.8× [bp GameSpeedThrottler, code SpeedManager].
- Autosave every 10 real minutes, 3 slots per settlement [bp Autosaver].

## Difficulty presets [bp NewGameModes]
| | Easy | Normal | Hard |
|---|---|---|---|
| Start beavers | 9 adults + 4 kids | 9 + 4 | 9 + 4 |
| Start food / water | 300 / 250 | 130 / **0** | 90 / **0** |
| Food & water consumption ×| 0.4 | 1.0 | 1.0 |
| Temperate days | 16–19 | 13–17 | **5–8** |
| Drought days (full) | 2–4 | 5–9 | 15–30 |
| Drought ramp: cycle-1 multiplier → full by cycle | 0.25 → 9 | 0.38 → 6 | 0.2 → 13 |
| Badtide possible from cycle | 6 | **5** | 4 |
| Badtide chance per cycle | 40% | 40% | 40% |
| Badtide days (full) | 1–3 | 4–8 | 15–30 |
| Badtide ramp | 0.3 → 7 | 0.15 → 6 | 0.4 → 10 |
| Injury chance × | 0.3 | 1.0 | 1.0 |
| Demolish refund | 90% | 75% | 75% |

- Duration in cycle c = round(rand(min,max) × lerp(mult, 1, (c−1)/rampCycles)), at least 1 [code HazardousWeatherHelper].
  - **Normal cycle 1 drought ≈ 2–3 days. Cycle 6+ drought = 5–9 days.**
- Badtide streak logic lowers the chance of long runs of the same hazard [code HazardousWeatherRandomizer].
- A custom game can disable droughts or badtides [loc].

## Per-beaver consumption [bp Needs, Goods; derived]
| Need | Decay/day | 1 unit restores | Units/beaver/day (Normal) | Easy (×0.4) |
|---|---|---|---|---|
| Thirst | 0.7 | Water 0.33 | **2.12 water** | 0.85 |
| Hunger | 0.8 | any food 0.3 | **2.67 food** | 1.07 |

- Children have the same needs (CharacterType "Beaver").
- Bots don't eat or drink. FT bots need Biofuel (0.58/day ÷ 0.3 = **1.93 biofuel/day**). IT bots need Energy (Charging Station, 50 power).
- Need range is −3 … +1. Starting from full, a beaver reaches 0 after ~1.4 days without water (1.25 days without food). It then has ~4.3 days (water) or ~3.75 days (food) before hitting −3, which is lethal [derived; the wiki agrees: death 3.75 d after "Starving", 4.29 d after "Dehydrated"]. While unmet: hunger costs −50% work speed and −40% kit growth; thirst costs −25% movement [bp PunitiveNeedSpec].
- Planning rule: **2.5 water and 3 food per beaver per day**, to cover margin and spoil-free buffer.

## Production per worker (base speed, 16 h/day, before wellbeing bonus) [bp Recipes/Buildings; derived]
Progress scales with each worker's working speed, so more workers means proportionally more output [code ProduceExecutor].
| Building (faction, cost, SP) | Workers | Recipe | Output/day per building at full staff |
|---|---|---|---|
| Water Pump (FT, 12 Log, 0) | 1 | 1 water / 0.33 h, pipe depth 2 | **≈48 water** (~22 beavers) |
| Deep Water Pump (IT, 12 Log, 0) | 1 | same, depth 6 | ≈48 water |
| Large Water Pump (FT, 20 Log 5 Gear 10 TPlank, 400) | 3 | 5 water / 1 h each, depth 4 | ≈240 water (~110 beavers) |
| Lumber Mill (FT, 15 Log, 0, 50 power) | 1 | 1 Log→1 Plank / 1.25 h | 12.8 planks |
| Industrial Lumber Mill (IT, 20 Log, 0, 75 power) | 2 | same | 25.6 planks |
| Gear Workshop (100 SP, 120 power) | 1 | 1 Plank→1 Gear / 3 h | 5.3 gears |
| Inventor (12 Log, 0) | 1 | 1 SP / h | **16 SP** |
| Observatory (FT, 1000 SP, 200 power) | 4 | 12 SP / 4 h each | 192 SP |
| Numbercruncher (IT, 1500 SP, 500 power) | 0 | 10 SP / h, automatic | 160–240 SP (unverified: 16 h vs 24 h) |
| Grill (FT, 25 Log, 0) | 1 | 1 Potato→4 / 0.52 h; Chestnut→2 / 0.33 h; Spadderdock→3 / 0.4 h; 1 Log per 10 cycles | ≈123 grilled potatoes (31 potatoes, 3 logs) |
| Gristmill (FT, 180 SP, 60 power) | 1 | Wheat→Flour / 0.5 h; CattailRoot→CattailFlour / 0.25 h | 32 flour / 64 cattail flour |
| Bakery (FT, 160 SP) | 1 | Flour→5 Bread / 1 h; CattailFlour→4 Crackers / 0.5 h; Flour+Syrup→3 Pastry / 1.5 h | 80 bread |
| Food Factory (IT, 300 SP, 120 power) | 1 | Corn→5 / 0.5 h; Eggplant+Oil→6 / 0.5 h; Algae+Oil→6 / 0.25 h | 160 corn rations |
| Fermenter (IT, 25 Log, 0, 50 power) | 1 | 4 Cassava→10 / 2 h; 4 Mushroom→16 / 2 h; 6 Soy+1 Oil→20 / 3 h | 80 fermented cassava |
| Hydroponic Garden (IT, 200 SP) | 1 | 40 Water→45 Mushroom / 192 worked h; 60 Water→70 Algae / 288 h | slow; worker-hours |
| Paper Mill (FT, 250 SP, 80 power) | 1 | 1 Log→2 Paper / 1.56 h | 20 paper |
| Wood Workshop (800 SP, 250 power) | 1 | Plank+PineResin→TreatedPlank / 3 h | 5.3 |
| Smelter (300 SP, 200 power) | 1 | 2 Scrap→1 MetalBlock / 2 h; 1 Log per 5 cycles | 8 metal blocks |
| Metalsmith (IT, 150 SP) | 1 | 1 Scrap→1 MetalPart / 3 h | 5.3 |
| Centrifuge (600 SP, 200 power) | 2 | 4 Badwater→1 Extract / 1.5 h | 21 extract |
| Explosives Factory (400 SP, 150 power) | 1 | 5 Badwater→1 Explosives / 3 h | 5.3 |
| Herbalist (FT, 300 SP) | 1 | 1 Paper+2 Dandelion+2 Berries→2 Antidote / 2 h | 16 antidote |
| Refinery (FT, 400 SP) | 2 | 2 Potato+2 Water→30 Biofuel / 6 h (carrot→5, spadderdock→25) | ≈160 biofuel from potatoes |

Hauling: an adult carries 14 weight and a bot 20. Water weighs 2, everything else 1. Hauling Post / District Crossing workers get +100% carrying capacity [bp].

## Crops and trees [bp NaturalResources; derived food/tile/day]
| Plant | Grow days | Yield | Dies dry after | Food-units/tile/day |
|---|---|---|---|---|
| Carrot (FT) | 4 | 3 | 2 d | 0.75 (raw) |
| Potato (FT) | 6 | 1 | 1 d | 0.67 (grilled ×4) |
| Wheat (FT) | 10 | 3 | 0.5 d | 1.5 (bread ×5) |
| Cattail (FT, aquatic, needs 1 m water) | 8 | 3 | 1 d | 1.5 (crackers ×4) |
| Spadderdock (FT, aquatic) | 12 | 3 | 0.3 d | 0.75 (grilled ×3) |
| Sunflower (FT) | 5 | 2 seeds | 3.5 d | 0.4 (raw) |
| Kohlrabi (IT) | 3 | 2 | 2 d | 0.67 (raw) |
| Corn (IT) | 10 | 2 | 2 d | 1.0 (ration ×5) |
| Cassava (IT) | 5 | 1 | 3 d | 0.5 (fermented ×2.5) |
| Soybean (IT) | 8 | 2 | 0.25 d | 0.83 (+oil) |
| Eggplant (IT) | 12 | 3 | 1 d | 1.5 (+1 oil each) |
| Canola (IT) | 9 | 3 seeds | 0.5 d | oil only |
| Blueberry bush (gatherer) | 12, then 3 berries per 12 d | | 9 d | 0.25 per bush |
| Chestnut tree | 23; 3 nuts / 8 d; 4 logs | | 8 d | 0.75 (grilled ×2) |
| Mangrove (aquatic) | 10; 4 fruit / 10 d; 2 logs | | 6 d | 0.4 |

Community 1.0 guide (after ~20% labour loss) [web 3696284505]: carrots ≈5 tiles/beaver, grilled potatoes ≈7, bread ≈3. Plan ~50 fast-crop tiles per farmhouse and 100+ for wheat.

Rough tiles per beaver for 2.67 food/day: carrots ≈3.6, wheat→bread ≈1.8, potato→grill ≈4, corn→ration ≈2.7, kohlrabi ≈4. Add ~30% for replant gaps and travel [derived].

Trees (logs per cut; stump remains for replanting):

| Tree | Grow days | Logs | Other / dies dry after |
|---|---|---|---|
| Birch | 7 | 1 | dies dry 11 d |
| Pine | 12 | 2 | + 2 resin / 7 d; dies dry 13 d |
| Oak | 30 | 8 | dies dry 15 d |
| Maple | 28 | 6 | + 3 syrup / 12 d |
| Chestnut | 23 | 4 | |

Logs per tile-day: Oak 0.27, Maple 0.21, Pine 0.17, Birch 0.14. Pine is needed for resin (treated planks).

## Storage and housing [bp]
| Building | Capacity | Cost / SP |
|---|---|---|
| Small / Medium / Large Warehouse (boxes: food, gears, etc.) | 30 / **200** / 1200 | 3 Log / 15 Log / 60 Log 80 Plank (250 SP) |
| Small / Large Pile (logs, planks, metal) | 20 / 180 | FT 2 / 6 Log; IT Industrial 4 / 12 Log |
| Underground Pile (FT) | 1000 | 1000 SP |
| Small / Medium / Large Tank (liquids) | 30 / 300 / 1200 | 15 Log / 30 Plank 20 Gear (120 SP) / 80 Plank 60 Gear 30 MetalBlock (600 SP) |
| FT Lodge / Mini / Double / Triple | 3 / 1 / 6 / 9 beds | 12 / 5 / 20 / 35 Log; 0 / 50 / 150 / 250 SP |
| IT Barrack / Rowhouse / Large Rowhouse / Large Barrack | 10 / 5 / 8 / 16 | 40 / 20 / 35 / 70 Log; 0 / 180 / 600 / 400 SP |

FT lodges are "procreation houses": kits are born in them. IT Barracks aren't; IT grows through Breeding Pods.

## Population growth [bp]
- Lifespan averages 50 days; childhood lasts 6 days [bp LifeService]. Wellbeing extends lifespan (see the tiers below).
- IT **Breeding Pod** (10 Log, 0 SP): needs **1 Water + 1 Berries per day** for **5 days**, holds 2 cycles of nutrients, and produces a child.
- IT **Advanced Breeding Pod** (1000 SP): Berries + Extract per day, 5 days, produces an **adult**.

## Drought and storage sizing [derived]
- Water for P beavers over D drought days: **W = 2.12 × P × D × 1.3**.
  - 20 beavers × 3 d (cycle 1–2, Normal) ≈ 165 → 1 Medium Tank, or 6 Small Tanks.
  - 50 beavers × 9 d ≈ 1240 → 1 Large Tank, or 4–5 Medium.
  - 100 beavers × 9 d ≈ 2480.
  - Hard 30-day drought, 100 beavers ≈ 8300 (needs a reservoir plus pumps, not tanks).
- Food: **F = 2.67 × P × (D + regrow)**, where regrow ≈ crop growth time if the fields dry out (carrots 4 d, wheat 10 d). If the fields stay irrigated from a reservoir, use D only.
- Water in tanks doesn't spoil. Pumps idle in a drought once the river's dry, but a pump on a deep pool or reservoir keeps working while there's water at its intake depth.
- A **reservoir** (dammed water) also keeps fields irrigated. Evaporation is ~0.0001/tick normally and 0.001 when the depth is under 0.02 [bp WaterSimulator]. Deep pools lose little.

## Wellbeing [bp WellbeingTiers, Needs; code WellbeingTier]
- Wellbeing = sum of +points from satisfied needs, minus penalties from unsatisfied basic needs.
  - Hunger and Thirst: −10 each when unmet.
  - Contamination −10, Shelter −3, Injury −2, Sleep −1, Bee sting −1, Chipped teeth −1.
- Max ≈ 84 for either faction, including 30 from Awe monuments.
- Each tier gives an **additive bonus** (base 1.0 + bonus):
  - **Working speed:** wellbeing 5 → +20%, 10 → +40%, 15 → +60%, 20 → +80%, 25 → +100%, 30 → +120%, 40 → +160%, 50 → +200%, 60 → +240%, 70 → +260%, 80 → +280%, 100 → +300%. (Beyond the list, +0.1 per 10.)
  - **Life expectancy:** 7 → +20%, 17 → +40%, 27 → +60%, 37 → +80%, 47 → +100%, 97 → +150%.
  - **Movement:** 2 → +5%, 12 → +15%, 22 → +30%, 42 → +50%, 92 → +80%.
  - **Child growth:** 5 → +5% … 50 → +60%.
  - **Bots:** working ×0.65 / 1.1 / 1.7 at bot-wellbeing 0 / 1 / 2.
- Cheap early wellbeing:
  - Each basic need satisfied (food, water, sleep, shelter, wet fur) = +1.
  - Campfire (15 Log, 0 SP) +1. Rooftop Terrace (15 Log) +1.
  - Shrub (12 Log, 0 SP) +1, Lantern +1, Roof +1.
  - Food variety: each extra food type +1 to +3.
  - FT Shower (50 SP) or IT Double Shower (50 SP) = wet fur +1.
  - Teeth Grindstone (5 Log) fixes chipped teeth.
- Big ones:
  - FT: Dance Hall +5 (1200 SP), Agora +3, Carousel +3, Books +3, Maple Pastry +3.
  - IT: Motivatorium +5, Coffee +3, Exercise Plaza +3, Wind Tunnel +3, Mud Bath +3.
  - Monuments: Earth Recultivator/Repopulator +10 (the wonder, 20000 SP), Hall of Abundance / Arch of Progress +8.

## Power [bp]
| Building | Faction | Cost / SP | Output |
|---|---|---|---|
| Water Wheel | FT | 50 Log, 0 SP | **270**; needs flow ≥ 0.15 |
| Compact Water Wheel | IT | 25 Log, 0 SP | 120 |
| Large Water Wheel | IT | 70 Log 80 Plank, 200 SP | 540 |
| Power Wheel | FT | 20 Log, 1 worker | 50 |
| Large Power Wheel | IT | 50 Log, 4 workers | 300 |
| Wind Turbine | FT | 120 SP | 150; needs wind ≥ 0.3 |
| Large Wind Turbine | FT | 1400 SP | 300 |
| Steam Engine | IT | 400 SP | 400; burns 0.1 Log + 0.3 Water / h |
| Geothermal Engine | both | 160 SP | 400 |
| Gravity Battery | both | 400 SP | 2000 capacity per tile of height |

Consumers include: Lumber Mill 50, Gear Workshop 120, Smelter 200, Wood Workshop 250, Observatory 200, Numbercruncher 500, Mechanical Pump 500, Compact Mechanical Pump 700, Aquifer Drill 400.

## Science costs of key unlocks [bp BuildingSpec.ScienceCost]
**0 SP** (available at start): Lodge / Barrack, Water Pump / Deep Water Pump, Farmhouse, Lumber Mill, Inventor, Grill (FT), Fermenter (IT), Small/Medium Warehouse, Small Tank, piles, Dam, Water Wheel / Compact Water Wheel, Power Wheel / Large Power Wheel, Campfire, Rooftop Terrace, Shrub, Teeth Grindstone, Breeding Pod (IT), Barrack (IT), Hauling Post, Path, Power Shaft, Scavenger Flag (IT; FT 250).

| Unlock | SP |
|---|---|
| Forester | 30 |
| Lantern / Teeth Grindstone (0) / Shower / Double Shower | 100 / 0 / 50 / 50 |
| Mini Lodge | 50 |
| Lever | 50 |
| Stairs | 70 |
| Relay | 80 |
| Gear Workshop | 100 |
| Builders' Hut | 100 |
| Platform | 100 |
| Flow Sensor | 100 |
| Levee | 120 |
| Medium Tank | 120 |
| Wind Turbine | 120 |
| Floodgate | 150 |
| Double Lodge | 150 |
| Aquatic Farmhouse | 150 |
| Chronometer | 150 |
| Bakery | 160 |
| Geothermal Engine | 160 |
| Gristmill | 180 |
| Rowhouse | 180 |
| Depth Sensor | 200 |
| Population Counter | 200 |
| Gate | 200 |
| Hydroponic Garden | 200 |
| Large Water Wheel | 200 |
| Impermeable Floor | 200 |
| Triple Lodge | 250 |
| Double Floodgate | 250 |
| Large Warehouse | 250 |
| Resource Counter | 250 |
| Paper Mill | 250 |
| Discharge | 250 |
| Badwater Pump | 250 |
| Smelter | 300 |
| Fill Valve (ex-Sluice) | 300 |
| Weather Station | 300 |
| Herbalist | 300 |
| Food Factory | 300 |
| Airlock | 300 |
| Large Water Pump | 400 |
| Contamination Sensor | 400 |
| Contamination Barrier | 400 |
| Irrigation Barrier (IT) | 400 |
| Explosives Factory | 400 |
| Gravity Battery | 400 |
| Large Barrack | 400 |
| Refinery | 400 |
| Clutch | 400 |
| Indicator | 400 |
| Decontamination Pod | 400 |
| Aquifer Drill | 400 |
| Triple Floodgate | 500 |
| Throttling Valve | 500 |
| Tapper's Shack | 500 |
| Bot Part Factory | 500 |
| Timer | 600 |
| Dynamite | 600 |
| Centrifuge | 600 |
| Large Tank | 600 |
| Large Rowhouse | 600 |
| Bot Assembler | 750 |
| Wood Workshop | 800 |
| Double Dynamite | 900 |
| Memory | 1000 |
| Observatory | 1000 |
| Advanced Breeding Pod | 1000 |
| Terrain Block | 1000 |
| Underground Pile | 1000 |
| Triple Dynamite | 1200 |
| Dance Hall | 1200 |
| Motivatorium | 1200 |
| Detonator | 1400 |
| Numbercruncher | 1500 |
| Mud Pit / Mud Bath | 1800 |
| Badwater Dome | 2000 |
| Tunnel | 2000 |
| Dirt Excavator | 2000 |
| Mechanical Pump / Deep Mechanical Pump | 2000 |
| Grease Factory | 2000 |
| Mine (scrap metal) / Efficient Mine (IT) | 4000 |
| Compact Mechanical Pump | 4000 |
| Badwater Rig | 4000 |
| Badwater Pressurizer | 4000 |
| HTTP Lever / HTTP Adapter | 5000 / 7500 |
| Wonder | 20000 |

Bot workers in a building cost extra SP per building type (e.g. Grill 750, Lumber Mill 500, Hauling Post 250) [bp WorkerTypeUnlockCosts].

## Soil and water simulation constants [bp]
- Irrigation spread [bp SoilMoistureSimulator]: MoistureSpreadingRate 6.66, VerticalSpreadCost ×6, MaxClusterSaturation 8.
  - Practical irrigation radius is ~**6–8 tiles** from water on flat ground, shrinking with height difference (unverified exact radius).
- Soil contamination spreads up to 7 tiles from contaminated water (≥0.5 contamination) [bp SoilContaminationSimulator].
- Floodgate max heights 1/2/3 m. Dynamite depth 1/2/3. Throttling valve flow 0–2.0. Fill valve overflow limit 0.02 [bp].
- Mechanical pumps move 0.25 water-units/s [bp WaterMover].

---
Re-extract after a game update: unzip `StreamingAssets/Modding/Blueprints.zip` and `Localizations.zip` to a temp dir, then run `python -I _tools/extract_blueprints.py <bp_dir> <loc_dir>/enUS.csv out.txt`.
