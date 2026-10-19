# How an experienced player builds (from a benchmark player's saves)
Read with `07-opening-plan-v3.md`. Source: `harness/save_study.py` over a benchmark player's saves (read-only zip reads, no game load).
Use it as a benchmark: compare our counts per 100 beavers with these at the same stage.

## The colonies studied
| Save | Mode | Faction, map | Cycle | Beavers | Hazards (longest) |
|---|---|---|---|---|---|
| beaverton on river | Easy | Iron Teeth, Beavers Riverland 256² | 33 | 283 | drought 4, badtide 2 |
| 1 | Easy | Iron Teeth, Architect's Dream 255² | 35 | 737 | drought 4, badtide 3 |
| EEasyStreet | Easy | Iron Teeth, Oasis 256² | 71 | 464 | drought 4, badtide 3 |
| Hotville (newest) | Normal | Emberpelts (mod), Architect's Dream | 56 | 520 | drought 9, badtide 8 |
| New Beaverville | Normal | Iron Teeth, Terraces 256² | 63 | 502 | drought 9, badtide 8 |

**Difficulty matters:** the three Iron Teeth colonies are Easy (save shows a 90% demolish refund; hazards 2–4 days). Easy beavers eat and drink only 0.4× as much. So on Normal (our game: 1.0×, droughts 5–9, badtides 4–8) scale their food, water and storage ratios up about 2.5×. Hotville and New Beaverville are Normal; **New Beaverville (Iron Teeth, Normal) is the closest benchmark for our game.**

Emberpelts and Leaf Coats are installed faction mods; 09 and 10 don't cover them.

## Habits common to every colony
- **One District Center** for the whole map, even at 700 beavers. Range comes from Tubeways (stations), platforms and many Builders' Huts and Hauling Posts, not new districts.
- **Work hours 18 h** in every late save (16 h at cycle 4).
- **Priorities:** Foresters VeryHigh; Hauling Posts and most Builders' Huts VeryLow; key pumps and GearWorkshop VeryHigh; a few FarmHouses/Food Factories VeryHigh. All FarmHouses left on "plant first".
- **Water engineering from day one.** By cycle 4 (32 beavers) beaverton had 11 Dams and 16 Levees. Late game: Levees 170–865 per 100 beavers, plus Fill Valves, Impermeable Floors, Floodgates, Throttling Valves, Dynamite.
- **Big levee reservoirs.** Hotville holds water in a levee-walled basin (x144-198 y0-33) stacked up to z30, watched by a Depth Sensor. "1" and EEasyStreet use 45–53 Large Tanks.
- **Oak forests:** Oak is 75–90% of all trees. Foresters about 1.5–2.4 per 100 beavers, 10–33k trees planted.
- **Built vertically:** platforms (170–340 per 100 beavers), overhangs and stairs; 400–700 tiles with two or more buildings stacked.
- **Storage is huge:** about 19 Large Warehouses, 28–33 Large Industrial Piles and 7–10 Large Tanks per 100 beavers (Iron Teeth).
- **Power is water wheels:** 10–13 Large Water Wheels per 100 beavers, plus Steam Engines (15–17) and 11–13 Gravity Batteries to bridge droughts. Geothermal and Aquifer Drills where the map has them.
- **Food mix:** blueberry bushes (800–2,400) with only 2–8 gatherers; FarmHouses about 2.3 per 100 beavers on big Corn and Canola fields (3–4 plots per beaver); Food Factories (about 2.7 per 100), Fermenters, Oil Presses; Hydroponic Gardens late (20–56).
- **Housing (Iron Teeth):** Large Barracks plus many pods: "1" had 52 Breeding Pods and 20 Advanced pods.

## New Beaverville: the Normal Iron Teeth benchmark (502 beavers, cycle 63)
Per 100 beavers:
- **Water:** 8 Deep Water Pumps (most set High/VeryHigh); 12.4 Large + 6.2 Medium + 3.6 Small Tanks = about **168 water stored per beaver** (84k total) for 9-day droughts. Deep Badwater Pumps 2.4 (High) with 4 Centrifuges.
- **Food:** 3.2 FarmHouses, 3.2 Food Factories, 3.2 Hydroponic Gardens; **5.3 crop plots per beaver** (mostly Corn, plus Canola for Oil Press and some Kohlrabi); only 361 bushes.
- **Wood:** 6.8 Lumberjack Flags, 2.8 Foresters (VeryHigh/High); mixed Oak, Pine, Birch.
- **Storage:** 21.5 Large Warehouses, 22 Large Industrial Piles.
- **Housing:** 37 Large Barracks, 23 Breeding Pods, 15 Advanced pods.
- **Terrain:** 4,110 Levees, 544 Impermeable Floors, 38 Dams, 62 Irrigation Barriers, 2,921 Platforms, 1,634 Vertical Tubeways with 56 stations. Built from z3 to z30 on the terraces.
- **Priorities are tuned everywhere:** pumps High/VeryHigh, farms and Food Factories High, lumberjacks and mills mixed High/Low, Smelters split, Hauling Posts and Explosives Factories VeryLow.

## Opening order (beaverton timeline, Easy mode)
- **Cycle 4, 32 beavers:**
  - 1 FarmHouse on 132 kohlrabi, 3 gatherers on 1,707 bushes
  - 4 Deep Water Pumps (one VeryHigh), 5 Small + 1 Medium Tank
  - 6 Lumberjacks, 2 Foresters, an Industrial Lumber Mill, a Gear Workshop
  - 4 Barracks, 5 pods
  - 11 Dams, 16 Levees, 9 Stairs
  - 3 Compact Water Wheels, 3 Inventors, 2 Scavenger Flags (early scrap)
  - 6 Large Industrial Piles, 2 Medical Beds
- **By cycle 14 (110):** Food Factories, Large Tanks (9), Large Warehouses, about 100 Levees, Large Water Wheels, Metalsmith, Smelter, Numbercruncher, Badwater Pressurizer, Centrifuge, Deep Badwater Pump.
- **By cycle 19:** Steam Engines, Advanced Breeding Pods, overhangs.
- **By cycle 27–28:** Tubeways, Discharge, Throttling Valve, Impermeable Floor, Airlock.

## Compared with our first playthrough (Normal, cycle 9, 26 beavers)
- We had 4 Dams and 0 Levees; the benchmark player had 11 and 16 by cycle 4. Water engineering first.
- We had 2 Foresters, 1 Inventor running and no Scavenger; the benchmark player had 3 Inventors and 2 Scavengers by cycle 4.
- Their early food rested on a big bush patch plus one big field, not many small fields.
