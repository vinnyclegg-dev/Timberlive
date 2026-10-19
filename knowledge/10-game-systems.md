# 10 — Game systems (v1.1.2.7)

Every non-building system in one place. Tags: `[bp]` = blueprint or config data from this install, `[code]` = game code, `[derived]` = calculated from those, `[web]` = wiki or guides (not checked in data). Building stats are in `09-buildings.md`. This file links to 00, 02 and 03 for tables that already exist and does not repeat them.

Sections:
1. Time and speed
2. Hazards and timing
3. Transport and paths
4. Landscaping
5. Water physics
6. Moisture and soil contamination
7. Natural resources
8. Needs and wellbeing
9. Life cycle: beavers and bots
10. Injuries, contamination, medicine
11. Districts and hauling
12. Storage
13. Power
14. Science
15. Faction differences
16. Natural map objects (slopes, natural dams, relics, ruins, sources)

---

## 1. Time and speed
- 1 tick = 0.6 s. 1 day = 768 ticks = 7.7 min at 1x. 1 hour = 19.2 s. Full table: 02 "Time".
- Sunrise and sunset each take 2 h, with 1 h transitions [bp DayStageCycle]. Working hours default to about 16 h; `set_work_hours` changes them.
- Above 30 characters, speeds above 1x are throttled. At 200 or more characters, the speed scale is 0.4, so 7x is about 3.4x [bp GameSpeedThrottler].
- Autosave: every 10 real minutes, 3 slots [bp Autosaver].
- Map size: default 128x128, up to 256. Terrain can be up to 22 high in game (16 in the editor). You can build up to 10 above the terrain [bp MapSize].

## 2. Hazards and timing
- A cycle is a temperate season followed by one hazard: a drought or a badtide. Lengths and ramps per difficulty are in 02 "Difficulty presets". Effects are in 00 "Cycles and hazards".
- **Drought:**
  - Sources stop. Rivers drain by flow and evaporation (§5).
  - Water wheels stop when the flow stops.
  - Unirrigated crops die after their "dies dry" time (§7).
- **Badtide:**
  - Every water source, seep and aquifer emits badwater. Water contamination reaches 100% over about 12 h (03).
  - Badwater gives no soil moisture above contamination 0.53 (§6). So crops on badwater-fed soil die dry. This is how badtide 2 killed every crop in the first playthrough (08).
  - Pump output = 1 − contamination.
- **Map hazards with timers** (§16):
  - The Unstable Core counts down from cycle 5 (10.5 days).
  - Delayed sources switch on from cycle 5 + 10 days.
  - Badtide Drains only flow during badtides.
- **Early warning:** the weather panel shows "approaching". A Weather Station can send an automation signal up to 3 days early (04).
- **Hazard reserve rule:** stock 1.5x the longest hazard so far at today's beaver count (02 "Drought and storage sizing").

## 3. Transport and paths

### Walking and carrying [bp Characters]
- Adults walk at 2.7. Children and slowed beavers walk at 1.35 (the slowed child speed is 0.65).
- Bots walk at 2.7 and carry 20. Adults carry 14.
- **Overburdened:** a load over the carry limit gives −50% movement.
- Carry weights: Scrap 11, BotChassis 11, Dirt 7, Log 6, MetalBlock 5, TreatedPlank 4, Plank 3, Gear 3, MetalPart 3, Water 2, everything else 1 (09 §1). So an adult carries 2 Logs, 4 Planks, or 7 Water per trip [derived].
- Wellbeing raises movement speed by up to +80% (§8).
- **Swimming:** beavers swim in water deeper than about 0.22–0.27. Wet beavers get the WetFur need. Swimming is slow, and walking through badwater can contaminate them (§10).

### Edge costs (lower = faster)
| Link | Cost | Notes |
|---|---|---|
| Path tile | 1.0 | Every building entrance must touch a path connected to the District Center. |
| Stairs / Spiral Stairs / natural **Slope** | 0.4 per vertical step, 1.0 flat | Climb 1 level. A Slope is free (§16). |
| Tubeway | 0.25 | +300% speed. Needs a Tubeway Station to get on (09). |
| Zipline cable (FT only) | 0.4 | +150% speed. Up to 30 tiles between stations or pylons, 2 connections each, slope up to 50 degrees [bp ZiplineConnectionService]. |

- **Ways to change level:** Stairs (70 SP), Spiral Stairs (350 SP), a natural Slope, a Platform reached by Stairs, a Vertical Tubeway, or a ramp of Dirt (Terrain Block). Beavers cannot climb a 1-high step without one.
- **Ways to cross water:**
  - a path on top of a Dam or Levee
  - a Suspension Bridge (an NxN bridge spans N+1 tiles)
  - Platforms and Overhangs
  - a natural Overhang (§16)
  - an Airlock (it blocks water in the middle)
  - swimming through shallow water, which is slow and makes fur wet
- **Range:** paths more than about 70 tiles from the District Center turn red and work slows down (09 §1 "Roads"). For far areas, build a second district (§11).

### Tools
- `walk_distance(x,y,z,targets)` returns null when a target can't be reached. Fix it with a Slope, Stairs, a dam crossing or a path.
- `map_summary(section="links")` lists natural slopes and where Stairs are needed.

## 4. Landscaping
What you can change, and with what:

| Tool | Effect | Unlock | Notes |
|---|---|---|---|
| Dynamite / Double / Triple | Lowers terrain by 1 / 2 / 3 | 600 / 900 / 1200 SP | Needs Explosives (Explosives Factory, from Badwater). A blast sets off adjacent dynamite. |
| Detonator | Fires the dynamite it sits on when it gets a signal | 1400 SP | For a timed or remote blast. |
| Tunnel | Bores through terrain and leaves a walkable floor | 2000 SP | 1 Explosives 1 Extract 6 Plank. Use `set_layers` to see inside. |
| Dirt Excavator | Makes Dirt (4 per 6 h). It digs out the 5x5 area under it | 2000 SP | 200 power. Keeps producing after it reaches bedrock. |
| Terrain Block | Adds a 1x1 block of terrain (4 Dirt) | 1000 SP | Must attach to the side of existing terrain. Use it to raise ground, fill gaps or build ramps. |
| Levee / Dam / Floodgate / Sluice | Hold or route water without changing terrain | see 09 | See 03 for the layouts. |
| Platforms, Overhangs, Metal Platforms | Build floors over gaps | see 09 | Buildings can go on top. |
| Impermeable Floor, Irrigation Barrier, Contamination Barrier | Control what spreads through the soil | see 09 | See §6. |

- **What you cannot change:**
  - Bedrock. Dynamite and the excavator stop there.
  - Heights above 22.
  - Map objects marked "not demolishable": the Unstable Core, Badtide Drains and water sources (§16).
- **Clearing plants:** use `demolish_resources`. Builders do the work; stumps also need clearing before you build or plant.
- **Natural objects you can remove** (§16):
  - Blockages, Natural Dams and natural Overhangs: 4 h each.
  - Thorns: 10 h, with an injury risk.
  - Relics: they give science.
  - Ruin Columns: the Scavenger salvages them for scrap.
- **Order of preference to change height:** natural Slope (free) > Stairs > Platform plus Stairs > dynamite or Terrain Block.

## 5. Water physics
Base model: 03 "Water model basics" (1 water good = 0.2 water units [web], evaporation, flow). Config values [bp WaterSimulator, WaterStrength]:
- **Flow:**
  - Flow factor 2.25.
  - Water spills over an edge only when it is more than 0.1 above it.
  - Soft and hard dam offsets are both 0.1. Water stops about 0.1 short of an obstacle's top.
- **Evaporation:** 0.0001 per second of game time from each water column, or 0.001 when the column is shallower than 0.02 (times a per-tile modifier). A tick is 0.6 s and a day is 768 ticks, so **about 0.046 depth per day** (0.46 per day for thin sheets). This matches 03's 0.045 m/day. A still pool loses about 0.4 depth in a 9-day drought, so a pool 1+ deep survives it; seepage into moist soil and pumps take more. Thin sheets dry fast and deep pools last [confirmed: decompiled WaterSimulator].
- **Sources:**
  - Strength is the outflow rate. The game allows up to 8.
  - A change in strength (drought start or end) ramps at up to 0.0058/s.
  - Map sources have strength 1 or 3 (§16).
- **Contamination:**
  - Each water column carries a contamination value from 0 to 1. It mixes at a diffusion rate of 0.45.
  - Clean and bad water mix where they meet. A clean source downstream dilutes a badwater stream.
- **Obstacle heights:**
  - Dam and Natural Dam hold 0.65 (09 §4).
  - Levee and Blockage hold 1.0 (a full block).
  - A Floodgate holds an adjustable height.
  - For anything bigger, stack Levees, or build on Platforms.
- **Pumps:**
  - Water pumps fill tanks at a rate scaled by (1 − contamination).
  - A Deep Water Pump reaches 6 down (09).
  - A Discharge (250 SP) releases stored water or badwater as flowing water. Use it to refill a dry channel or a field moat.
- **Draining and flooding:**
  - Water flows to the lowest connected tile.
  - A dam across a river mouth holds water only up to 0.65 above the river bed. Upstream of it, the pool keeps evaporating.
  - Deep, narrow reservoirs lose the least to evaporation [derived].
- **Badwater** behaves like water but contaminates the soil (§6) and beavers (§10). Ways to manage it:
  - Divert it with Levees or Floodgates.
  - Cap it with a Badwater Pressurizer (4000 SP, 09).
  - Pump it out for industry (a Deep Badwater Pump feeds Explosives and Extract).

## 6. Moisture and soil contamination
Detail and irrigation layouts: 03. Constants [bp SoilMoistureSimulator, SoilContaminationSimulator]:
- **Moisture:**
  - Spreads from water tiles. Range is about 2 per adjacent water tile, capped at saturation 8. Climbing +1 height costs the same as 6 flat tiles (03 says up to about 16 tiles).
  - Spreading rate 6.66, decay 1.25. Once the water goes, crops survive only their "dies dry" time (§7).
  - **Water with contamination at or above 0.53 gives no moisture.** Badwater fields go dry.
  - Moist soil also makes the water body evaporate more. The effect grows with the irrigated area, up to saturation 10 [bp quadratic evaporation coefficients; derived].
  - SoilMoistureMap has a desert threshold of 5 (used for the dry-ground look; exact meaning unconfirmed).
- **Soil contamination:**
  - Spreads from water with contamination at or above 0.5, up to 7 tiles. Climbing +1 height costs the same as 5 flat tiles.
  - Spreading rate 0.066, decay 0.033. So it clears about half as fast as it builds.
  - A tile counts as contaminated at 0.2 or more, and plants on it die [bp threshold; effect inferred]. Map contamination is capped at 0.9 [bp SoilContaminationMap].
- **Barriers:** each of these is a SoilBarrier [bp]:

| Barrier | Blocks moisture above | Blocks all moisture | Blocks contamination |
|---|---|---|---|
| Levee | yes | – | – |
| Impermeable Floor | yes | – | – |
| Impermeable Power Shaft | yes | – | – |
| Compact Mechanical Pump | yes | – | – |
| Irrigation Barrier (IT) | – | yes | yes |
| Contamination Barrier (FT) | – | – | yes |
| Thorns (§16) | blocks moisture and contamination | | |

- **Reading the map:**
  - `view_map` MOISTURE: `#` = moist; `w` = water.
  - The WATER grid shows depth and contamination.
  - `map_summary(section="farmland")` lists moist land.
  - Plant only on moist land that beavers can reach, never on water tiles, and never on a ledge 2 or more above its neighbours.

### Measured irrigation reach (5 maps, clean water, start of game)
Tiles counted along the ground (4-neighbour steps) from the nearest water tile. "Level" = ground height compared with the water surface.

| Ground | Moist reliably | Patchy until |
|---|---|---|
| Just above the water surface (bank level) | about 10 tiles (17 by Oasis' deep pool) | about 12–16 |
| 1 block higher | about 5 tiles | about 10 |
| 2 blocks higher | about 4 tiles | 5 |
| 3+ blocks higher | 0–1 tiles | – |

- Deeper, bigger water bodies reach further (config `MaxClusterSaturation` 8; climbing a block costs 6× a flat step, `VerticalSpreadCostMultiplier`).
- Rule for fields: keep them within about 8 tiles of the water and at most 1 block above it, or bring water closer with a channel or levee pool.
- Measured with `harness/survey_map.py scan` grids on Oasis, Plains, Lakes, Meander and Terraces (Meander's clean river gave the clearest numbers).

## 7. Natural resources
Food yield per tile and per worker: 02 "Crops and trees". Survival rules [bp NaturalResources]:

| Plant | Faction | Grows (d) | Yield | Dies dry (d) | Dies flooded (d) | Notes |
|---|---|---|---|---|---|---|
| Blueberry bush | both | 12 | 3 Berries every 12 d | 9 | 7 | Gatherer; spreads 0.02 |
| Coffee bush | IT | 9 | 1 bean every 3 d | 8 | 4 | Coffee Brewery |
| Dandelion | FT | 3 | 1 every 3 d | 8 | 4 | Antidote input; spreads |
| Canola | IT | 9 | 3 seeds | 0.5 | 0.5 | Oil Press |
| Carrot | FT | 4 | 3 | 2 | 2 | Edible raw |
| Cassava | IT | 5 | 1 | 3 | 2 | **Not edible raw** (Fermenter) |
| Corn | IT | 10 | 2 | 2 | 2 | Not edible raw (Food Factory) |
| Eggplant | IT | 12 | 3 | 1 | 1 | Not edible raw (Food Factory) |
| Kohlrabi | IT | 3 | 2 | 2 | 1 | Edible raw; IT's fastest crop |
| Potato | FT | 6 | 1 | 1 | 1 | Grill |
| Soybean | IT | 8 | 2 | 0.25 | 0.25 | Not edible raw; very fragile |
| Sunflower | FT | 5 | 2 seeds | 3.5 | 0.66 | |
| Wheat | FT | 10 | 3 | 0.5 | 0.5 | Gristmill |
| Cattail | FT | 8 | 3 roots | 1 | 1 | **Aquatic** |
| Spadderdock | FT | 12 | 3 | 0.3 | 1 | **Aquatic** |
| Birch | both | 7 | 1 log | 11 | 14 | Spreads 0.03 |
| Pine | both | 12 | 2 logs; 2 resin every 7 d | 13 | 12 | Tapper; spreads 0.03 |
| Oak | both | 30 | **8 logs** | 15 | 10 | Best wood per tile; spreads 0.01 |
| Chestnut | FT | 23 | 4 logs; 3 nuts every 8 d | 8 | 10 | |
| Maple | FT | 28 | 6 logs; 3 syrup every 12 d | 12 | 10 | Tapper |
| Mangrove | IT | 10 | 2 logs; 4 fruit every 10 d | 6 | 16 | **Aquatic** |
| Succulent | both | 65 | 2 Water when cut | – | 4 | Arid; dies after 8 d wet; cutting it gives Injury |

- **Aquatic plants** (Cattail, Spadderdock, Mangrove) need standing water exactly 1 deep on the tile (MinWaterHeight = MaxWaterHeight = 1). Other plants need dry, moist soil (water height 0) and die "flooded" if water stands on them.
- **Timing:**
  - Crops take 0.2 h to plant and 1.2 h to harvest.
  - Oak and Maple take 1.0–1.1 h to plant and 2 h to cut. Blueberries take 0.8 h to gather.
- **Dies dry / dies flooded** are the days a plant survives without moisture, or under the wrong water level. Growth pauses meanwhile.
- **Contamination:** every plant can be contaminated; it dies on contaminated soil (§6).
- **Spreading:** the "spreads" chance is natural reproduction onto nearby free tiles. Bushes and trees spread; crops don't.
- **Uses:**
  - Lumberjacks cut only trees inside a marked cutting area (`mark_tree_cutting`).
  - Gatherers collect bush and tree products (berries, nuts, fruit) without killing the plant.
  - Tappers take resin and syrup.
- **What is edible [bp goods with a Hunger effect]:**
  - Raw: Berries, Kohlrabi, Mangrove Fruit (IT); Carrot, Sunflower Seeds (FT).
  - IT processed: Fermented Cassava / Soybean / Mushroom (Fermenter); Corn, Eggplant and Algae Rations (Food Factory; Algae Ration also needs Canola Oil).
  - FT processed: Bread, Cattail Cracker, Maple Pastry, Grilled Potato / Chestnut / Spadderdock.
  - Raw Cassava, Corn, Soybean, Eggplant, Canola, Wheat, Potato, Cattail and Spadderdock are **not** food.

## 8. Needs and wellbeing
Wellbeing tiers and bonus tables: 02 "Wellbeing". Daily consumption: 02 "Per-beaver consumption". Need groups [bp Needs]:

| Group | Needs (wellbeing when satisfied / when unmet) |
|---|---|
| Basic | Hunger −0.8/day (+1 / −10), Thirst −0.7/day (+1 / −10), Sleep −0.6/day (+1 / −1), Shelter −0.3/day (+1 / −3), WetFur −0.3/day (+1) |
| Basic, conditions | BadwaterContamination −10, Injury −2, ChippedTeeth −1, BeeSting −1 (heals 0.75/day) |
| Social life | Campfire +1, Rooftop Terrace +1, Contemplation Spot +1; Agora +3, Dance Pit +2, Domed Garden +2, Dance Hall +5 |
| Fun | +3: Books, Carousel, Exercise Plaza, Mud Bath, Mud Pit, Wind Tunnel; +5: Motivatorium; +1: Detailer, Lido, Massager, Sauna, Scratcher, Swimming Pool |
| Nutrition (−0.05/day each) | Each food type eaten +2 (Kohlrabi, Carrots, Mangrove Fruit and Sunflower Seeds +1; Coffee and Maple Pastry +3) |
| Aesthetics (−0.4/day) | Decorations +1, Beaver Statue +2, Bulletin Pole and Decorative Clock +2 (−0.3/day) |
| Awe (−0.3/day) | Farmer/Laborer statues +2, Flame/Brazier of Bonding +4, Tribute/Fountain +6, Arch/Hall +8, wonders +10 (they decay at only −0.01/day) |

- **Wellbeing** = the sum over the satisfied needs, minus the penalties. It raises:
  - working speed: up to +200% at 50 and +300% at 100
  - movement: up to +80%
  - life expectancy: up to +50% at 97
  - child growth
- **Variety is the cheapest wellbeing:** each extra food type is +1 to +3. Eating one food type gives only the Hunger point.
- **Decorations and attractions:**
  - Attractions serve a set number of beavers at a time and fill the need at a rate per hour (see 09).
  - Decorations work over an area.
  - Needs decay daily, so a beaver must revisit.
- **Critical needs:** Hunger or Thirst at 0 starts the death clock (about 3.75–4.3 days, 02). A beaver with BadwaterContamination or Injury **refuses to work** [bp NeedPreventingWork].
- **Tools:**
  - `get_needs` shows averages and the critical count per need.
  - Wellbeing is in `get_colony`.

## 9. Life cycle: beavers and bots
- **Lifespan:** about 50 days on average, scaled by the wellbeing life-expectancy bonus (0.2 at wellbeing 7, up to 1.5 at 97). Childhood lasts 6 days [bp LifeService].
- **Children:**
  - walk at half speed and don't work
  - need food and water
  - grow faster with wellbeing
- **Births:**
  - **FT:** lodges breed when there is a free bed and food and water stock (00: 18.75% chance per day per lodge). The Mini Lodge does not breed.
  - **IT:** a Breeding Pod uses 1 Water + 1 Berries per day for 5 days and makes a child. The Advanced pod uses Extract and makes an adult (02).
  - **Migration:** beavers can move between districts automatically, up to 100 [bp MigrationCoordinator].
- **Death:** from old age, starvation, dehydration, or "tragic" deaths (drowning, explosions). After a death, the beaver's home and job become free.
- **Bots:**
  - carry 20, walk 2.7, work 24 h (they ignore working hours)
  - break down after 70 days
  - have no food, water or sleep needs; their wellbeing comes only from bot needs (below)
- **Bot needs:**
  - IT bots: Energy at −0.58/day; with none, wellbeing −3 and they refuse work. Charging Station.
  - FT bots: Biofuel at −0.58/day, from the Refinery.
  - Upkeep goods (+1 each, −0.2/day): Catalyst, Grease, Punch Card. Control Tower +1.
  - Bot wellbeing tiers:
    - work speed: 0.65 at 0, 1.1 at 1, 1.7 at 2
    - movement: 0.3 / 0.6 / 0.8
  - So a bot with no upkeep goods works slowly.
- **Building bots:**
  - Bot Assembler, 72 h per bot. Parts come from the Bot Part Factory (09).
  - Bots fill workplaces only where `WorkerTypeUnlockCosts` allows them, and only after that bot SP is paid. The cost is listed per building in 09.

## 10. Injuries, contamination, medicine
- **Injury** (−2 wellbeing; the beaver can't work):
  - Comes from workshop accidents, lumberjacking (as ChippedTeeth), cutting Succulents, Beehive stings, demolishing Thorns, and explosions.
  - Chance per check:

| Group | Low | Medium | High |
|---|---|---|---|
| Workshop | 0.003125 | 0.01 | 0.02 |
| Area and yield removal | 0.025 | 0.1 | 0.3 |
| Demolishing | 0.025 | 0.05 | 0.1 |

  - Which buildings use which group: 09 §1 "Workers, bots and injury risk".
  - Healing: the need runs from −1 to 0 and heals at +0.1/day on its own (10 days from full injury). A Medical Bed adds +0.015/h (0.36/day), so about 2–3 days in bed [derived].
- **ChippedTeeth** (−1; lumberjacks):
  - Cutting success −75%. **It never heals on its own** (daily change 0).
  - Cure: the Teeth Grindstone (5 Log, 0.5/h).
  - IT: build one near the lumberjack flags.
- **BeeSting** (−1, from FT Beehives): heals at 0.75/day on its own.
- **BadwaterContamination** (−10; can't work; −70% movement):
  - Caught by wading in contaminated water (05 §3, about 5% contamination or more), followed by 3 days of incubation (00).
  - No natural recovery. Cures:
    - FT: Antidote, made by the Herbalist from Paper, Dandelions and Berries. One dose = +0.125.
    - IT: Decontamination Pod: 50 power, uses Extract, +0.068/h.
  - Prevention: keep paths out of badwater (bridges or dams), and don't route beavers through flooded tiles during a badtide.
- **Tools:**
  - `get_needs` shows Injury and BadwaterContamination critical counts.
  - `get_alerts` shows the "can't work" alerts.

## 11. Districts and hauling
- **District:** one District Center plus every building path-connected to it. Each district has its own stock, workers and builders.
  - Goods do not move between districts unless a **District Crossing** links them (600 SP, 3x1x2, up to 10 workers; it balances stock both ways, +100% carry).
  - Beavers can migrate between districts automatically (§9). Manual migration is set at the District Center.
- **Why split:**
  - Past about 70 tiles from the District Center, everything is slow (red paths).
  - A second District Center near distant fields or a mine shortens every trip.
- **Hauling:**
  - Every worker carries their own inputs and outputs when idle. Haulers (Hauling Post, +100% carry) move goods between storage and workshops.
  - Builders (District Center, Builders' Hut) deliver construction materials.
  - Set work and construction priority with `set_priority`.
- **Distance matters most:** every trip walks to the nearest storage that holds or accepts the good. Put a small store beside each producer and consumer (08 "Storage").
- **Tools:**
  - `inspect_building` statuses: "Lacks resources", "No storage", "Unreachable".
  - `walk_distance` tells you whether a site can be reached.

## 12. Storage
- **Storage types** [bp]:
  - **Pileable:** Logs, Planks, Treated Planks, Scrap, Metal Blocks, Dirt. They go in Piles (IT Industrial Piles).
  - **Box:** food, gears, paper, goods. They go in Warehouses.
  - **Liquid:** Water, Badwater, Extract, Syrup, Oil. They go in Tanks.
  - A building stores only its own type.
- **Setting goods:**
  - Each warehouse or tank is set to one or more goods with `building_action`. New tanks are set to Water by `watch.py`.
  - An unset store accepts nothing useful. A store set to a good no one produces stays empty.
- **District Center:** holds a small buffer of starting goods.
- **Sizes:** see the capacities in 02 "Storage and housing".
- **Every good needs storage space.** A producer with nowhere to put its output stops ("No storage").
- **Fixed stockpiles on the map:** Reserve Pile, Reserve Tank and Reserve Warehouse are pre-placed stores (§16). Connect them with a path and use them.
- **Demolish refund:** deconstructing a building returns its construction materials and the goods inside it × the mode's recovery rate: **75% on Normal and Hard, 90% on Easy** (GameMode `DemolishableRecoveryRate`).

## 13. Power
- **Generators and consumers:** 02 "Power" and 09.
- **Network:**
  - Power travels through shafts and through powered buildings that touch each other.
  - Vertical shafts carry it up and down.
  - Connect a shaft at the middle of a wheel.
  - One network's supply is shared by all its consumers. If demand is higher than supply, every building on it runs at reduced speed.
- **Water wheels:**
  - need flowing water: about 0.15 flow or more for the FT Water Wheel
  - stop in droughts
  - turn in badwater as well (confirmed by play). A badwater channel can drive wheels.
  - output grows with flow speed [web]
  - Build them in a spillway or over a dam outflow.
- **Wind** changes every 5–12 h, at strength 0–1 [bp WindService]. FT Wind Turbines need 0.3 or more.
- **Geothermal Engine:** must sit on a Geothermal Field (§16). Constant 400 power.
- **Gravity Battery:** stores power to cover droughts and still days (2000 per tile of height).
- **Beaver-powered wheels** are a stopgap only (user rule): use water wheels and shafts for industry.

## 14. Science
- **Sources:**
  - Inventor: 1/h per worker; beaver-only.
  - Numbercruncher (IT): 10/h, 24 h a day, needs power, no workers.
  - Observatory (FT): 12 SP per 4 worker-hours, about 12 SP/h fully staffed with 4 [derived, 09].
  - **Relics** on the map give 200 / 800 / 3000 SP when demolished (§16).
- **Spending:** science unlocks buildings, and unlocks bots per workplace. Costs are in 09 and 02 "Science costs".
- Science is shared across the settlement and does not decay.
- **Planning:** scout Relics early. A Large Relic (3000 SP) is worth more than a month of Inventors.

## 15. Faction differences
The full table is in 00 "Factions" and 09 §3. Points that affect systems:
- **Births:**
  - FT: lodges breed on their own.
  - IT: Breeding Pods (Water + Berries). Plan their inputs.
- **Food:**
  - IT: Kohlrabi is fast and edible raw. Cassava, Corn and Soybean need processing. Mangrove is aquatic.
  - FT: Carrots raw; Wheat, Potato, Cattail, Spadderdock, Chestnut and Maple processed.
- **Housing:** IT has Barracks and Rowhouses. FT has Lodges (the Mini Lodge doesn't breed).
- **Wood:**
  - Both factions have Oak, Birch and Pine.
  - FT adds Chestnut and Maple. IT adds Mangrove.
- **Power:**
  - FT: Water Wheel 270, wind, Power Wheel.
  - IT: Compact 120 and Large 540 water wheels, Steam Engine, Large Power Wheel.
- **Transport:** Ziplines are FT only. Tubeways are shared.
- **Medicine:**
  - FT: Antidote from the Herbalist.
  - IT: Decontamination Pod.
  - Both: Teeth Grindstone, Medical Bed.
- **Bots:** FT runs on Biofuel, IT on Energy. Both also need Catalyst, Grease and Punch Cards for upkeep.
- **Water:** IT has Deep pumps, the Badwater Pressurizer and Irrigation Barriers. FT has the Contamination Barrier.

## 16. Natural map objects
Map makers place these objects; you can't build any of them [bp MapEditor/Objects, Ruins, Water]. **Scout for them at game start:**
- Run `map_summary(section="features")` and `map_summary(section="links")`.
- Use `inspect_tile` for detail and the `view_map` OBJECTS grid for position.
- The first playthrough missed the natural Slopes and spent planks on Stairs.

### Slope (free natural stairs)
- **What it is:** a 1x1x2 path object that works like Stairs. Two-way; climbing costs 0.4.
- **Flavour text:** "Whoever put it here, beavers are grateful."
- **Orientation:** unrotated, you step on from the +Y neighbour at the base level and step off onto the −Y neighbour one level higher. So the high side is −Y. With rotation, the high side turns with it. `map_summary` shows orientation as `o#`.
- **Use:** connect paths to both ends. It saves 1 Log + 4 Planks + 70 SP per level crossing.
- **Don't demolish it.** It can be demolished (4 h), but it can't be rebuilt.
- **Example from the first playthrough:** a Slope at (59,37) joined h2 to h3.

### Water blockers and natural platforms
- **Blockage** (1x1): a natural barrier that holds water to height 1.0. Demolish it (4 h, from the top) to release or redirect water. Check what floods downstream first.
- **Natural Dam:** holds 0.65, the same as a built Dam. Demolish it in 4 h.
  - Keep it if it stores water for droughts.
  - Remove it only to drain land or to open a channel.
- **Natural Overhang** (2x1, 3x1, 4x1): a watertight rock bridge. Water passes under it, and you can walk and build on top. Demolish in 4 h.
  - Use it as a free bridge or a foundation over water.
- **Thorns** (1x1):
  - Block movement, moisture and contamination.
  - Demolishing takes 10 h, and each check has a 0.1 chance of Injury −1.
  - Remove them only when they block a route or farmland. A Medical Bed should be nearby.
  - Leaving them along a field edge can stop contamination spreading in.

### Relics (science)
| Object | Size | Science | Demolish time |
|---|---|---|---|
| Small Relic | 2x1 | 200 SP | 2 h |
| Medium Relic | 3x2 | 800 SP | 4 h |
| Large Relic | 3x3x2 | 3000 SP | 8 h |
- Demolish relics from the top. Builders must be able to reach them.
- A high-value early target, often worth a path detour.

### Hazard: Unstable Core
- A 2x2 object. It can't be demolished or disarmed.
- Each map sets its own timer and radius. The blueprint default is radius 5. Built-in maps use 2–3, with the countdown starting after 3–13 cycles and lasting 10.5 days (status "Explodes soon") [map files].
- **Read it in game:** `inspect_tile` gives the core's `id`; `GET /api/building/inspect?id=...&all=true` shows `UnstableCore.ExplosionRadius` and `TimedComponentActivator` (`CyclesUntilCountdownActivation`, `DaysLeftUntilActivation`, `CountdownIsActive`). In the game UI, clicking the core shows the radius too.
- **The blast (game code):** a sphere of radius ExplosionRadius + 1 around the core's ground centre. It removes the terrain blocks inside it, deletes every building and plant inside it and anything left unsupported above, and kills beavers in it. It spreads outwards over a few ticks.
- **Timer (game code, TimedComponentActivator):** the countdown starts on cycle N (`CyclesUntilCountdownActivation`) day 1; the blast comes when 10.5 days have passed (about day 11.5, or into cycle N+1 if that cycle is shorter). Before then, `ActivationProgress`/`DaysLeftUntilActivation` only reflect today's day progress and mean nothing.
- **Chain reactions (game code):** a blast reaching a tile next to another core sets it off. A detonating Dynamite on a tile next to a core (4 neighbours, same z) activates it at once (Dynamite.TriggerNeighbors; the wiki says the same). That is the one player tool for setting a core off early, on your own timing, once counter-measures are in. Nothing in the player's tools defuses it (only the map editor blocks it).
- **Effects on water:** use `harness/underground.py`: it rebuilds the crater, then reports new outlets (pools or pressurised caves running out of the crater), bodies joined (badwater meeting clean water) and whether it reaches the base.
- **Plan with it:** keep buildings, paths and beavers more than radius + 1 tiles away (3D, so also above and below). The crater is free excavation: it can become a reservoir or channel once the core has gone off.

### Ground features that unlock buildings
- **Geothermal Field** (3x3, floodable): "constant, free power". A Geothermal Engine (400 power) must sit on it.
- **Underground Ruins** (5x5): a Mine or Efficient Mine must sit on them. This is the endless scrap source.
- **Ruin Columns H1–H8:** 15 Scrap per height level (up to 120 Scrap). The Scavenger removes one level in 1.8 h. This is the early Scrap for Metalsmith, Smelter and Gate.
- **Aquifer** (3x3, underground, strength 1):
  - An Aquifer Drill reaches it. It turns bad in badtides.
  - Map files store it at CurrentStrength 0 and SpecifiedStrength 1, so it may need a drill before it gives anything.
  - Built-in maps with aquifers: Oasis (10, plus 2 Ancient Aquifer Drills) and Pillars (1). The benchmark player's Oasis colony ran 2 Aquifer Drills.
- **Ancient Aquifer Drill** (3x3x5): a free, pre-placed drill on an Aquifer. It needs 200 power (a built Aquifer Drill needs 400, plus 40 Plank, 25 Gear, 15 Metal Block and 400 SP) and **no workers** (confirmed in game on Oasis). Its power connectors are on the front middle tile (1,0), at ground level and one level up. Just bring a power shaft.

### Reserve stores
These are fixed stockpiles, pre-placed on some maps:

| Store | Size | Capacity |
|---|---|---|
| Reserve Pile | 2x2x2 | 160 Pileable |
| Reserve Tank | 2x2x3 | 300 Liquid |
| Reserve Warehouse | 2x2x1 | 200 Box |

- Entrance at (1,−1,0) from the pivot. It needs a path connection.
- In the editor they cost 10 Scrap.
- They come pre-filled with one fixed good (confirmed from map files): Reserve Warehouses with Explosives (40–200), Reserve Tanks with Water (300). Haul from them; check with `inspect_building`.
- Found on: Nomads (4 Reserve Warehouses) and the user map "The sanctuary" (warehouse and tank).
- **Demolishing** (game code and in-game check on Nomads): blocked while goods are inside ("Stockpile not empty"). Use the `Emptiable` action `MarkForEmptyingWithStatus` (needs a path to a district) and haulers carry the goods to your storage. Then it can be deconstructed for 75% of its 10 Scrap Metal on Normal.

### Water and badwater sources
| Object | Size | Strength | Notes |
|---|---|---|---|
| Water Source | 1x1 | 1 | Turns bad in a badtide; stops in a drought |
| Water Seep | 2x2 | – | Fills only to 0.8 deep |
| Badwater Source | 3x3 | 3 | Always bad. Cap it with a Badwater Pressurizer, or divert it |
| Badwater Seep | 2x2 | 1 | Fills only to 0.8 |
| Badtide Drain | 1x3 | 1, contamination 1 | **Flows only during badtides.** Directional; can sit in a cliff side; not demolishable |
| Aquifer | 3x3 | 1 | Underground; needs a drill |

- Some sources have **delayed activation**: they switch on later (status "Activates soon"). Badtide Drains in built-in maps wait 5 cycles + 10 days; Seeps are time-activated too and their flow drops as the water over them gets deeper. Plan levees before then.
- Every source except a Badtide Drain turns bad during a badtide.

### Which built-in maps have what (for testing)
From `harness/save_study.py maps` (reads every map file through the bridge):

| Object | Maps (count) |
|---|---|
| Unstable Core | Nomads 6, Spillage 8, Pressure 9 |
| Aquifer / Ancient Aquifer Drill | Oasis 10 / 2, Pillars 1 |
| Reserve stores | Nomads (4 warehouses), user map The sanctuary (warehouse and tank) |
| Badtide Drain | Oasis 18, Spillage 18, Pillars 15, Canyon 3, Meander 3 |
| Water and Badwater Seeps | Spillage (8 and 5), Pillars, Craters |
| Geothermal Field | Spillage 7, Pillars 6 |
| Relics | Spillage, Pillars, Meander |
| Thorns | Pillars (1,473) |
| Natural Dam | Spillage 14, Pressure 9, Lakes 8, The sanctuary 78 |
| Slope | every map (Plains 23, Lakes 17, Terraces 16) |

### Other
- **Starting Location** (3x3x5): the editor's start marker. Not a building.
