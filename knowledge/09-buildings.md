# 09 - Building reference (Iron Teeth first)

Source: game blueprints and localization for v1.1.2.7 (`Blueprints.zip`), decompiled game code `[code]`, the live `list_blueprints` output, and the wiki `[web]`. Lines marked `[web]` are not confirmed by game data and may be out of date.

How to read an entry: `TemplateId` - what it does. Size is X x Y x Z (Z = height). `W` = max workers (default). `hp` = power used (a minus sign means produced). `SP` = science cost. Recipe times are in-game hours (1 day = 24 h ≈ 7.7 real min at 1x). Bot SP = the extra science needed to let bots work in that building type.
- Pass the template id as shown. The live game adds the faction suffix (`.IronTeeth`).
- `*` = locked in the current save (as of cycle 5).

## 1. Core rules

### Goods and storage type
Every good fits only one storage type, so build the right store next to its producer.
- **Pileable** goes in Industrial Piles: Log, Plank, TreatedPlank, MetalBlock, ScrapMetal, Dirt.
- **Liquid** goes in Tanks: Water, Badwater, Extract, CanolaOil, Coffee, Grease (FT: Antidote, Biofuel, Catalyst, MapleSyrup).
- **Box** goes in Warehouses:
  - all food and crops
  - Gear, MetalPart, PineResin, Explosives, Fireworks
  - bot parts (Chassis, Limb, Head)
  - (FT: Paper, Books, PunchCards)
- **Carry weight per unit:** Scrap 11, BotChassis 11, Dirt 7, Log 6, MetalBlock 5, TreatedPlank 4, Plank 3, Gear 3, MetalPart 3, Water 2, everything else 1. An adult carries 14 and a bot 20. Hauling Post and District Crossing workers get +100%.
- Set the good on each Warehouse and Tank (`building_action`). An empty or unset store takes nothing.

### Workers, bots and injury risk [bp]
- `Bot SP` is shown per building. Beaver-only workplaces: Inventor, Large Power Wheel, FT Power Wheel. Bots ignore working hours (they work 24 h).
- Workshop injury: some workplaces roll an Injury hit (shown as −points and a probability class). Classes per check: Low 0.003125, Medium 0.01, High 0.02. Other classes: area effects (Beehive stings) 0.025 / 0.1 / 0.3; harvest effects (lumberjack teeth, Succulent cutting) 0.05 / 0.1 / 0.3; demolition effects (Thorns) 0.025 / 0.05 / 0.1 [bp ProbabilityGroups].
  - −1 High: Dirt Excavator, Explosives Factory, Bot Assembler, Bot Part Factory.
  - −0.8 High: Efficient Mine / Mine, Centrifuge, Badwater Rig.
  - −0.6 Medium: Smelter, Grease Factory, Wood Workshop, Paper Mill, Printing Press, Refinery.
  - −0.4 Medium: Metalsmith, Gear Workshop. −0.1 Low: lumber mills.
  - Also: lumberjacks get ChippedTeeth (−1 Medium); cutting Succulents gives Injury (−1 Medium).
- One Medical Bed per cluster of high-risk workshops. See 10 §10.

### Main IT production chains
- **Wood:**
  - Forester plants trees, and a Lumberjack Flag cuts them (only inside marked cutting areas): Log.
  - Log -> Industrial Lumber Mill -> Plank -> Gear Workshop -> Gear.
  - Pine trees -> Tapper's Shack -> PineResin. Then Plank + PineResin -> Wood Workshop -> TreatedPlank.
- **Food:**
  - Blueberry bushes (Forester) -> Gatherer -> Berries. Breeding Pods need Berries.
  - Farmhouse crops:
    - Kohlrabi is eaten raw.
    - Cassava, Soybean (+Oil) and Mushroom go through the Fermenter.
    - Corn, Eggplant (+Oil) and Algae (+Oil) go through the Food Factory.
    - Canola -> Oil Press -> CanolaOil.
- **Metal:**
  - Ruins -> Scavenger Flag -> ScrapMetal. Late game: Efficient Mine on UndergroundRuins.
  - Scrap -> Metalsmith -> MetalPart (no power). Scrap -> Smelter -> MetalBlock.
- **Badwater:**
  - Badwater -> Centrifuge -> Extract.
  - Badwater -> Explosives Factory -> Explosives / Fireworks.
  - Extract feeds Advanced Breeding Pod, Detailer, Decontamination Pod, Grease, Memory, Tunnel and Dynamite.
- **Bots:** Bot Part Factory (Chassis, Limb, Head) -> Bot Assembler. Bots need a Charging Station (Energy). Grease and the Control Tower are optional boosts.

### Crops and trees (data)
Format: name - days to grow -> yield. All are planted by the IT Farmhouse unless the entry says Forester.
- Kohlrabi: 3 d -> 2
- Cassava: 5 d -> 1
- Soybean: 8 d -> 2
- Canola: 9 d -> 3 seeds
- Corn: 10 d -> 2
- Eggplant: 12 d -> 3
- BlueberryBush (Forester): 12 d, then 3 Berries every 12 d. Harvested by the Gatherer.
- CoffeeBush (Forester, IT): 9 d, then 1 bean every 3 d. Harvested by the Gatherer.
- Trees (Forester), giving Log when cut:
  - Birch: 7 d -> 1
  - Pine: 12 d -> 2, plus 2 PineResin every 7 d (Tapper)
  - Mangrove (IT): 10 d -> 2, plus 4 MangroveFruit every 10 d (Gatherer); tolerates 1 water depth
  - Oak: 30 d -> 8
- Succulent (common): 65 d -> 2 Water.

### Work ranges `[code NavigationDistance]`
- Lumberjack, Gatherer, Farmhouse, Forester, Scavenger and Tapper work only within about **20 tiles of walking distance** of their building.
- Beavers walk up to **10 tiles off-path** from the district road network.
- Roads longer than **70 tiles** from the District Center count as far (red) and slow everything. Build a second district (District Center plus a District Crossing) instead.

### Power
- **Producers:**
  - Compact Water Wheel 120 (no workers, needs flowing water)
  - Large Water Wheel 540
  - Large Power Wheel 300 (4 workers, about 75 each; scales with walking speed `[web]`)
  - Steam Engine 400 (burns Log + Water)
  - Geothermal Engine 400 (only on a geothermal field)
  - Gravity Battery stores 2000 per tile of height.
- **Transfer:**
  - Power Shafts (1 Log) join generators and consumers into one network.
  - Buildings that touch at a power connection point also pass power to each other, so consumers can be chained.
  - Water wheels connect only at the middle of their long side, at mid height.
  - The Steam Engine connects through the central block of each side that has no entrance `[web]`.
  - Vertical Power Shafts change level. A Clutch switches part of the network off (automation).
- If supply is below demand, **every** consumer on that network slows proportionally `[web]`.
- IT's only lumber mill (75 hp) and the Fermenter (50 hp) need power, so IT needs a wheel on day 1.

### Wellbeing: which building meets which need
IT need groups. Points are given while the need is satisfied.
- **Basic needs:**
  - Hunger: food (−10 if unmet)
  - Thirst: water (−10)
  - Sleep: a bed (−1)
  - Shelter: housing (−3)
  - WetFur: Double Shower, Swimming Pool, Dance Pit (+1)
- **Penalties to cure:**
  - ChippedTeeth (−1): Teeth Grindstone
  - Injury (−2): Medical Bed
  - BadwaterContamination (−10): Decontamination Pod
- **Social life:** Campfire +1, Rooftop Terrace +1, Dance Pit +2.
- **Fun:** Scratcher +1, Massager +1, Detailer +1, Swimming Pool +1, Exercise Plaza +3, Wind Tunnel +3, Mud Bath +3, Motivatorium +5.
- **Nutrition (variety, needs a food type in stock):**
  - +2 each: Fermented Cassava, Fermented Soybean, Fermented Mushroom, Corn Ration, Eggplant Ration, Algae Ration
  - +1 each: Kohlrabi, MangroveFruit
  - Coffee +3
  - Berries satisfy Hunger only, with no variety point.
- **Aesthetics (work by area; the beaver must pass within the radius):**
  - Shrub +1 (r1), Lantern +1 (r1), Roofs +1 (r1)
  - Brazier +1 (r2), Beaver Bust +1 (r2)
  - Bell +1 (r3), Decorative Clock +2 (r3), Beaver Statue +2 (r3)
- **Awe (monuments, by area):** Laborer Monument +2 (r7), Flame of Unity +4 (r10), Tribute to Ingenuity +6 (r20), Arch of Progress +8 (r30), Earth Repopulator +10 (r40).
- **Bots:** Energy from a Charging Station (basic). Grease +1 and Control Tower +1 are boosts.

### Unlock and dependency notes
- Science comes from the Inventor (1 SP/h per worker, 0 SP to build). Later the Numbercruncher gives 10 SP/h, 24 h/day `[code]`, needs 500 hp and no workers.
- **Metal:** the Scavenger Flag needs Ruins on the map. MetalPart (Metalsmith) is needed by:
  - the Oil Press and Hydroponic Garden
  - the Steam Engine and Explosives Factory
  - the Charging Station and Dance Pit
  - the Population and Resource Counters, Metal Fence and Beaver Bust
- **TreatedPlank** needs the Tapper's Shack (500 SP) plus Pine trees, then the Wood Workshop (800 SP). It gates:
  - Coffee, Mud Bath, Motivatorium, Detailer, Grease
  - the Deep Mechanical Pump, Spiral Stairs and Efficient Mine
  - the Throttling Valve, Irrigation Barrier, Weather Station and Timer
- **Extract** needs Badwater: a Deep Badwater Pump or a badwater source, then the Centrifuge (600 SP). It gates Dynamite, Tunnel, Advanced Breeding Pod, Detailer, Decontamination Pod and Grease.
- **Explosives** need the Explosives Factory (400 SP). They gate Dynamite, Tunnel and the Badwater Pressurizer (50 Explosives).
- **Placement requirements:**
  - Geothermal Engine: a GeothermalField
  - Aquifer Drill: an Aquifer
  - Efficient Mine: UndergroundRuins
  - Badwater Pressurizer: a BadwaterSource
  - Detonator: on top of placed dynamite
- **Every building with an entrance needs its entrance tile on a path.**

## 2. Iron Teeth buildings by toolbar group

### Wood
- `LumberjackFlag` - 1x1, free, 0 SP, W1, output 20. Cuts trees only inside marked cutting areas (`mark_tree_cutting`). Chipped teeth: −1 at Medium probability (0.1 per cut), after a minimum of 75 cut attempts (`MinimumAttemptsThreshold`; exact meaning unconfirmed). Chipped teeth cut cutting success by 75%. Never mark your only stand.
- `IndustrialLumberMill` - 2x3x3, 20 Log, 0 SP, W2, **75 hp**. 1 Log -> 1 Plank / 1.25 h (about 38 planks/day at 2 workers over 24 h; about 25 on a 16 h shift). Injury −0.1 Low. Put a pile for logs and one for planks beside it.
- `Forester` - 2x2x4, 10 Log 7 Plank, 30 SP, W1 (bot 500 SP). Plants trees and bushes (Blueberry, Coffee, Pine, Birch, Oak, Mangrove) inside its planting area within range. Unlock it early so wood is renewable.
- `GearWorkshop` - 2x3x2, 15 Log 25 Plank, 100 SP, W1 (bot 1000 SP), 120 hp. 1 Plank -> 1 Gear / 3 h. Injury −0.4 Medium. Gears are needed for almost everything mid-game, so run two.
- `TappersShack`* - 2x2x2, 20 Log 20 Plank 10 Gear, 500 SP, W1 (bot 750 SP). Collects PineResin from grown Pine trees within range (output 50). It works the "Tappable" group (Pine resin; FT Maple syrup too). Plant a Pine block next to it.
- `WoodWorkshop`* - 2x4x4, 20 Log 40 Plank 40 Gear, 800 SP, W1 (bot 2000 SP), 250 hp. Injury −0.6 Medium. 1 Plank + 1 PineResin -> 1 TreatedPlank / 3 h. This is the key mid-game gate.

### Food
- `GathererFlag` - 1x1, free, 0 SP, W1, output 20. Harvests Berries, CoffeeBeans and MangroveFruit from grown bushes and trees in range. Pair it with a Forester planting blueberries.
- `FarmHouse` - 2x2x2, 20 Log, 0 SP, W2 (bot 500 SP), output 50. Plants and harvests Farmhouse crops on `plant_area` tiles within about 20 tiles. Only moist tiles grow crops.
- `Fermenter` - 3x1x3, 25 Log, 0 SP, W1 (bot 750 SP), **50 hp**. Recipes:
  - 4 Cassava -> 10 FermentedCassava / 2 h
  - 6 Soybean + 1 CanolaOil -> 20 FermentedSoybean / 3 h
  - 4 Mushroom -> 16 FermentedMushroom / 2 h
  - Cassava multiplies food by 2.5x, so it is the main IT staple.
- `OilPress`* - 2x2x3, 40 Log 10 MetalPart, 120 SP, W1 (bot 750 SP), 50 hp. 1 CanolaSeeds -> 1 CanolaOil / 1.25 h. Needs a tank for the oil.
- `HydroponicGarden`* - 3x3x1, 20 Plank 10 Gear 10 MetalPart, 200 SP, W1 (bot 750 SP), no power. Recipes:
  - 40 Water -> 45 Mushroom / 192 h
  - 60 Water -> 70 Algae / 288 h
  - Grows indoors and ignores drought.
  - Progress resets after 24 h halted (no worker or no water) [bp]. `[web]` It stops while its output is full, so keep it emptied.
- `FoodFactory`* - 3x3x3, 40 Plank 15 Gear 10 MetalBlock, 300 SP, W1 (bot 750 SP), 120 hp. Fuel: 1 Log per 10 cycles. Recipes:
  - 1 Corn -> 5 CornRation / 0.5 h
  - 1 Eggplant + 1 Oil -> 6 EggplantRation / 0.5 h
  - 1 Algae + 1 Oil -> 6 AlgaeRation / 0.25 h
  - Very fast, so one factory feeds a large colony.
- `CoffeeBrewery`* - 2x3x3, 10 Gear 25 TreatedPlank 15 MetalBlock, 500 SP, W1 (bot 750 SP), 200 hp. 1 CoffeeBean + 1 Water -> 4 Coffee / 1 h. Fuel: 1 Log per 10 cycles. Coffee gives Nutrition +3; store it in a tank.

### Housing
- `BreedingPod` - 1x1x1, 10 Log, 0 SP. Takes 1 Water + 1 Berries per day for 5 days, then a kit is born. Holds 2 days of nutrients. IT grows population only this way (Barracks don't breed). `[web]` Haulers, idle beavers and off-shift workers fill it.
- `AdvancedBreedingPod`* - 5 TreatedPlank 2 MetalBlock, 1000 SP. Berries + Extract per day; produces an adult. Both pods hold 2 days of nutrients (capacity 2).
- `Barrack` - 3x2x2, 40 Log, 0 SP, 10 beds.
- `LargeBarrack`* - 3x3x2, 70 Log, 400 SP, 16 beds. The best beds per tile early.
- `Rowhouse`* - 1x2x3, 20 Log, 180 SP, 5 beds. Narrow; stacks along roads.
- `LargeRowhouse`* - 1x2x4, 35 Log, 600 SP, 8 beds.

### Storage
- `SmallIndustrialPile` - 1x1, 4 Log, 0 SP, 20 Pileable.
- `LargeIndustrialPile` - 3x3, 12 Log, 0 SP, 180 Pileable. Use it for bulk logs and planks.
- `SmallWarehouse` - 1x1, 3 Log, 0 SP, 30 Box.
- `MediumWarehouse` - 3x2, 15 Log, 0 SP, 200 Box. The best early food store.
- `LargeWarehouse`* - 3x3x2, 60 Log 80 Plank, 250 SP, 1200 Box.
- `SmallTank` - 1x1x2, 15 Log, 0 SP, 30 Liquid.
- `MediumTank` - 2x2x3, 30 Plank 20 Gear, 120 SP, 300 Liquid. The main drought water store.
- `LargeTank`* - 3x3x3, 80 Plank 60 Gear 30 MetalBlock, 600 SP, 1200 Liquid.

### Water
- `DeepWaterPump` - 2x3x3, 12 Log, 0 SP, W1 (no bot unlock cost listed). 1 Water / 0.33 h (about 48/day over 16 h). The pipe reaches 6 deep. Badwater in the column slows or blocks it. Put it over the deepest water.
- `DeepBadwaterPump`* - 20 Log 10 Gear 10 MetalPart, 250 SP, W1 (bot 800 SP). 1 Badwater / 0.33 h, depth 6. Feeds the Centrifuge and Explosives Factory.
- `Discharge`* - 1x2, 10 Log 10 Plank, 250 SP, W1 (bot 250 SP). Recipes FlowingWater / FlowingBadwater: 3 goods per hour, switchable. Takes stored Water or Badwater and releases it onto the map. Holds 15 of each `[web]`. Uses: irrigate dry land far from rivers, or top up a reservoir. It stops when the tile below is about 0.9 full `[web]`.
- `DeepMechanicalPump`* - 3x3x4, 50 Gear 15 TreatedPlank, 2000 SP, no workers, 500 hp. Moves 0.25 water units/s continuously; pipe depth 8. The body is a water obstacle.
- `CompactMechanicalPump`* - 1x3x1, 50 Gear 25 TreatedPlank 25 MetalBlock, 4000 SP, 700 hp. A compact powered pump: input on one end, output on the other (0.25 units/s). Blocks moisture above it.
- `Centrifuge`* - 3x3x3, 60 Plank 40 Gear 30 MetalBlock, 600 SP, W2 (bot 1500 SP), 200 hp. 4 Badwater -> 1 Extract / 1.5 h. Fuel: 1 Log per 10 cycles. Injury −0.8 High, so keep a Medical Bed nearby.
- `BadwaterPressurizer`* - 3x3x1, 300 Gear 200 MetalBlock 50 Explosives, 4000 SP. Placed on a badwater source; it can be opened or closed. When open, it flows even during droughts. Use it to cap badwater and reclaim land.
- `AquiferDrill`* - 3x3x4, 40 Plank 25 Gear 15 MetalBlock, 400 SP, 400 hp. Must sit on an Aquifer and makes fresh water flow. It is a drought-proof river source.

### Power
- `CompactWaterWheel` - 3x1x3, 25 Log, 0 SP, -120 hp, no workers. Needs water flowing through it in its +X direction (outflow at least 0.15). It connects at the middle of its long side, at mid height. Output scales with flow `[web]`. Turns in badwater too (confirmed). Put it in a spillway below a dam.
- `LargeWaterWheel`* - 5x3x5, 70 Log 80 Plank, 200 SP, -540 hp. Same flow rule as the compact wheel. The main mid-game power source.
- `LargePowerWheel` - 3x3x2, 50 Log, 0 SP, W4 (beavers only), -300 hp (75 per worker). Works only while staffed (work hours). Use it as a stopgap; it costs 4 workers.
- `PowerShaft` - 1x1x1, 1 Log, 0 SP. Joins power buildings.
- `VerticalPowerShaft`* - 2 Log 2 Plank 1 Gear, 40 SP. Carries power up and down.
- `Clutch`* - 2 Gear 6 MetalBlock, 400 SP. Disconnects part of a network on a signal (automation).
- `ImpermeablePowerShaft`* - 12 Log 6 Gear 10 MetalBlock, 300 SP. A shaft that also blocks water.
- `SteamEngine`* - 3x3x3, 20 Log 25 Gear 40 MetalPart, 400 SP, -400 hp. Burns 0.1 Log + 0.3 Water per hour (holds 50 work-hours of each), and only when there is demand `[web]`. Drought-proof power.
- `GravityBattery`* - 2x2x4, 40 Plank 40 Gear 10 MetalBlock, 400 SP. Stores 2000 per tile of height. It evens out power from water wheels that slow in droughts.
- `GeothermalEngine`* - 3x3x2, 50 Log 30 Plank, 160 SP, -400 hp. Only on a GeothermalField map feature.

### Science
- `Inventor` - 2x2x3, 12 Log, 0 SP, W1 (beavers only). +1 SP per worked hour. The only early science source.
- `Numbercruncher`* - 4x4x3, 30 Plank 100 Gear 50 MetalPart, 1500 SP, no workers, 500 hp. +10 SP/h, 24 h/day (about 240 SP/day) `[code]`. It does not need a worker.
- `BotPartFactory`* - 50 Plank 25 Gear 15 MetalBlock, 500 SP, W1 (bot 5000 SP), 150 hp. Injury −1 High. Recipes:
  - Chassis = 5 Plank + 1 MetalBlock / 18 h
  - Limb = 1 Plank + 3 Gear / 4.5 h
  - Head = 1 Plank + 3 Gear + 1 MetalBlock / 18 h
- `BotAssembler`* - 3x3x1, 100 Plank 50 Gear 50 MetalBlock, 750 SP, W2 (bot 10000 SP), 250 hp. Injury −1 High. 1 Chassis + 4 Limbs + 1 Head -> 1 bot / 72 h.
- `ChargingStation`* - 1x1, 5 Plank 15 Gear 10 MetalPart, 200 SP, 50 hp. Recharges bot Energy at +0.6/h up to full (an IT bot uses about 0.58/day). `[web]` One bot at a time.
- `ControlTower`* - 1x1x7, 20 Plank 15 Gear 20 MetalBlock, 1000 SP. Bot boost +1 within radius 10. **Uses 3 SP/h (72 SP/day).**
- `GreaseFactory`* - 2x3x3, 30 Gear 20 TreatedPlank 10 MetalBlock, 2000 SP, W2 (bot 2500 SP), 200 hp. Injury −0.6 Medium. 1 Extract + 1 CanolaOil -> 2 Grease / 4 h (a bot boost; store it in a tank).

### Metal
- `ScavengerFlag` - 1x1, free, 0 SP (FT 250), W1 (bot 500 SP). Collects ScrapMetal from Ruins within range. Ruins run out.
- `Metalsmith`* - 2x2x3, 30 Plank 10 Scrap, 150 SP, W1 (bot 1000 SP), **no power**. Injury −0.4 Medium. 1 Scrap -> 1 MetalPart / 3 h. Fuel: 1 Log per 5 cycles.
- `Smelter`* - 2x4x3, 50 Plank 20 Gear 30 Scrap, 300 SP, W1, NEEDS POWER (bot 1000 SP), 200 hp. Injury −0.6 Medium. 2 Scrap -> 1 MetalBlock / 2 h. Fuel: 1 Log per 5 cycles.
- `EfficientMine`* - 5x5x4, 300 Log 450 Gear 300 TreatedPlank, 4000 SP, W10 (bot 1000 SP). Injury −0.8 High. Must sit on UndergroundRuins (a 5x5 map feature, see 10 §16). Recipes:
  - 1 TreatedPlank -> 5 Scrap / 18 h
  - 1 TreatedPlank + 2 Extract -> 10 Scrap / 18 h
  - It is the renewable scrap source once surface ruins are gone.

### Landscaping
- `Dam` - 1x1, 20 Log, 0 SP. Holds water to 0.65 height (same as a map NaturalDam) and spills over the top. Beavers can walk on it. Use it for drought reservoirs and water-wheel spillways.
- `Levee`* - 12 Log, 120 SP. A full 1-high water block. Also stops moisture spreading above it.
- `Floodgate`* / `DoubleFloodgate`* / `TripleFloodgate`* - 10 Log 5 Plank / 20 Log 10 Plank / 30 Log 15 Plank; 150 / 250 / 500 SP. An adjustable gate up to 1 / 2 / 3 high. Use it to divert badwater during badtides.
- `FillValve`* - 1x2, 5 Plank 5 MetalBlock, 300 SP. One-way; keeps the downstream level at a set height (default floor + 0.5; overflow limit 0.02).
- `ThrottlingValve`* - 5 TreatedPlank 5 MetalBlock, 500 SP. Limits flow from 0 to 2.0 (default 1.0, step 0.01).
- `ImpermeableFloor`* - 1 MetalBlock, 200 SP. A water-tight floor tile; also blocks moisture above.
- `IrrigationBarrier`* - 10 Log 5 TreatedPlank, 400 SP. Stops moisture (fully) and contamination from spreading through the soil. Use it to keep badwater from poisoning fields.
- `ExplosivesFactory`* - 2x4x3, 30 Plank 30 Gear 60 MetalPart, 400 SP, W1 (bot 2000 SP), 150 hp. Injury −1 High. Recipes:
  - 5 Badwater -> 1 Explosives / 3 h
  - 1 Badwater -> 10 Fireworks / 3 h
- `Dynamite`* / `DoubleDynamite`* / `TripleDynamite`* - 1 Explosives (+1 / +2 Extract); 600 / 900 / 1200 SP. Lowers terrain by 1 / 2 / 3. A blast sets off adjacent dynamite. Use it to dig canals and reservoirs.
- `Tunnel`* - 1 Explosives 1 Extract 6 Plank, 2000 SP. Bores through terrain and leaves a walkable Platform. Use `set_layers` to see inside.
- `DirtExcavator`* - 5x6x3, 100 Gear 100 TreatedPlank 50 MetalBlock, 2000 SP, W4 (bot 4000 SP), 200 hp. 4 Dirt / 6 h. Digs a 5x5 area under itself and keeps producing after it reaches bedrock. Injury −1 High.
- `TerrainBlock`* - 4 Dirt, 1000 SP. Places a 1x1 block of new terrain; it must attach to the side of existing terrain.

### Paths
- `Path` - free. Every entrance needs one.
- `Stairs` - 1 Log 4 Plank, 70 SP. Up or down 1 level. Check for a free natural `Slope` first (10 §16).
- `SpiralStairs`* - 1 Log 4 TreatedPlank, 350 SP.
- `Platform` / `DoublePlatform`* / `TriplePlatform`* - 6 / 8 / 10 Plank; 100 / 150 / 200 SP. Raised floors you can build on top of. The Rooftop Terrace and buildings on upper levels need them.
- `TubewayStation`* - 3x2x2, 40 Plank 20 Gear 20 MetalBlock, 700 SP. The entry point to tubeways.
- `Tubeway`* - 2 Plank 1 MetalBlock, 500 SP. +300% move speed (edge cost 0.25 vs path 1.0). `[web]` Segments auto-connect; beavers stay dry and clean; builders can work from inside.
- `VerticalTubeway`* - 4 Plank 1 MetalBlock, 600 SP.
- `ImpermeableTubeway`* - 4 Plank 2 Gear 2 MetalBlock, 800 SP. Also blocks water.
- `Gate`* - 6 Plank 4 Gear 4 Scrap, 200 SP. A path tile that closes on an automation signal.
- `Airlock`* - 1x3, 15 Log 8 Gear 4 MetalBlock, 300 SP. A walkable passage; the middle tile blocks water.
- `SuspensionBridge1x1`* .. `SuspensionBridge6x1`* - 4 Log 4 Plank per span; 150 / 250 / 400 / 600 / 1000 / 1800 SP. An NxN bridge spans N+1 tiles. Crosses rivers without dams.
- `Overhang2x1`* .. `Overhang6x1`* - 350 / 550 / 1000 / 1800 / 3000 SP. Cantilever platforms; Log/Plank plus 2 MetalBlock per span.
- `MetalPlatform3x3`* / `MetalPlatform5x5`* - 30 / 90 MetalBlock; 1000 / 2000 SP.
- `Ladder`* - 4 Log 6 Plank, 250 SP. **This comes from a Workshop mod (Tobbert.Ladder), not the base game.**

### District management
- `DistrictCenter` - 3x3x5, free, W4 builders (default 2), output 20. Bots can work here. The district's heart. Roads count distance from here.
- `HaulingPost` - 3x2x3, 20 Log 10 Plank, 0 SP, W10 (default 5; bot 250 SP). Haulers with +100% carry. They move goods between stores and deliver to construction and pods. Needed for "obtain" stores.
- `BuildersHut`* - 3x2x2, 20 Log 10 Plank, 100 SP, W4 (bot 250 SP). Extra builders near a big construction area.
- `DistrictCrossing`* - 3x1x2, 30 Log 15 Plank, 600 SP, W10 (default 4; bot 250 SP). Links two districts and balances goods between them (+100% carry).

### Wellbeing
- `Campfire` - 3x3x1, 15 Log, 0 SP. SocialLife +1, 5 at a time.
- `RooftopTerrace` - 3x2x1, 15 Log, 0 SP. SocialLife +1, 10 at a time (FT 8). It must stand on top of something (a building roof or a Platform) and be reachable by Stairs or a Platform.
- `TeethGrindstone` - 1x1, 5 Log, 0 SP. Cures ChippedTeeth (−1, which comes from lumberjacking) at 0.5/h, up to full.
- `DoubleShower`* - 1x2x2, 10 Log 1 Plank, 50 SP. WetFur at 1.0/h, 2 at a time. Needs water under its pipe, at most 6 deep.
- `MedicalBed` - 1x1, 5 Log 1 Plank, 80 SP. Heals Injury (−2) at +0.015/h; the patient sleeps there instead of at home. Place it near high-injury workshops.
- `DecontaminationPod`* - 1x2, 20 Plank 5 Gear 5 MetalBlock, 400 SP, 50 hp. Uses 0.1 Extract/h. Cures badwater contamination (−10) at +0.068/h; the patient sleeps there.
- `Scratcher`* - 5 Log 5 Plank, 100 SP. Fun +1, 1 at a time.
- `Massager`* - 10 Plank 5 Gear, 150 SP. Fun +1.
- `SwimmingPool`* - 3x4x2, 40 Log 30 Plank, 250 SP. Fun +1 and WetFur +1, 8 at a time. Needs water at least 0.2 deep at its tile.
- `ExercisePlaza`* - 5x5x2, 50 Log 50 Plank 20 Scrap, 400 SP. Fun +3, 13 at a time. The cheapest big Fun point.
- `DancePit`* - 5x5x3, 60 Plank 20 Gear 30 MetalPart, 1800 SP. SocialLife +2 and WetFur; uses 0.2 Water/h.
- `WindTunnel`* - 5x5x4, 100 Plank 50 Gear 50 MetalBlock, 800 SP, 400 hp. Fun +3, 12 at a time.
- `Detailer`* - 15 Gear 5 TreatedPlank 10 MetalBlock, 1000 SP. Fun +1; uses 0.25 Extract/h.
- `Motivatorium`* - 5x5x3, 75 Log 100 Gear 20 TreatedPlank, 1200 SP, 200 hp. Fun +5, 18 at a time. The best IT Fun building.
- `MudBath`* - 2x2x2, 40 Log 20 Gear 50 TreatedPlank, 1800 SP, 50 hp. Attractions give 0.6 points/h. Fun +3, 8 at a time; uses 0.5 Dirt/h (from the Dirt Excavator).

### Decoration (Aesthetics; must be within radius r of where beavers walk)
- `Shrub` - 12 Log, 0 SP, +1, r1. The cheap early decoration.
- `Lantern`* - 2 Log 4 Plank, 100 SP, +1, r1.
- `Roof1x1`*, `Roof1x2`*, `Roof2x2`*, `Roof2x3`*, `Roof3x2`* - small Log + Plank cost; 60 / 80 / 120 / 150 / 150 SP; +1, r1.
- `Brazier`* - 12 Plank 4 Scrap, 150 SP, +1, r2. Goes out if flooded.
- `BeaverBust`* - 4 Scrap 2 MetalPart, 200 SP, +1, r2.
- `BeaverStatue`* - 20 MetalBlock, 500 SP, +2, r3.
- `Bell`* - 20 Plank 5 MetalBlock, 500 SP, +1, r3. Rings at the start and end of the workday.
- `DecorativeClock`* - 10 Plank 8 Gear 2 MetalBlock, 600 SP, +2, r3.
- `Bench`* - 6 Log 2 Plank, 80 SP. A rest place for 2.
- `WoodFence`* (3 Plank) / `MetalFence`* (6 MetalPart) - 150 SP each. Looks only; no effect.
- `StreamGauge`* - 2 Log 4 Plank, 150 SP. Shows water depth, flow and contamination; also an automation input.
- `PoleBanner`* / `SquareBanner`* - Log + Plank + 1 Extract, 700 SP. No effect.

### Monuments (Awe; area effect)
- `LaborerMonument`* - 2x2x4, 200 Log, 1000 SP, +2, r7. The cheapest Awe.
- `FlameOfUnity`* - 300 Plank 100 MetalPart, 3000 SP, +4, r10.
- `TributeToIngenuity`* - 3x3x8, 400 Gear 100 Plank 300 MetalBlock, 9000 SP, needs 600 hp, +6, r20.
- `ArchOfProgress`* - 600 Plank 300 TreatedPlank 600 MetalBlock, 15000 SP, +8, r30.
- `EarthRepopulator`* - 7x7x10, 1500 Gear 2000 TreatedPlank 2000 MetalBlock, 20000 SP, W8, +10, r40. The wonder.
  - Launching it also needs 500 TreatedPlank + 500 Berries.
  - It takes about 15000 build-hours, with up to 40 builders.

### Automation (same stats for both factions; signals are wireless with no range limit)
- `Lever`* - 1 Plank 2 Gear, 50 SP. A manual on/off switch.
- `Relay`* - 1 Plank 1 Gear, 80 SP. Logic (AND/OR/NOT and similar) on signals.
- `FlowSensor`* - 1x2, 6 Plank 4 Gear, 100 SP. Signals on water flow (0-2.0).
- `DepthSensor`* - 4 Gear 8 Scrap, 200 SP. Signals on water depth. Use it to close floodgates in a drought.
- `ContaminationSensor`* - 8 Gear 8 MetalBlock, 400 SP. Signals on badwater share. Use it to auto-divert badtides.
- `Chronometer`* - 8 Plank 6 Gear, 150 SP. A time-of-day signal.
- `WeatherStation`* - 3x1, 10 Gear 8 TreatedPlank, 300 SP. Signals a coming drought or badtide up to 72 h early.
- `PowerMeter`* - 10 Gear 6 MetalBlock, 600 SP. Signals on network power or battery charge.
- `PopulationCounter`* - 2 Plank 2 Gear 1 MetalPart, 200 SP. Needs a path at its entrance.
- `ResourceCounter`* - 4 Plank 4 Gear 1 MetalPart, 250 SP. Signals on a good's stock in its district. Needs a path.
- `ScienceCounter`* - 6 Gear 4 Scrap 6 MetalPart, 300 SP.
- `Indicator`* - 2 Scrap 1 PineResin, 400 SP. A light that shows a signal.
- `Speaker`* - 4 Plank 2 Gear 4 MetalBlock, 500 SP. Plays a sound on a signal.
- `Timer`* - 1 TreatedPlank 1 MetalBlock, 600 SP. Delays or pulses a signal.
- `Memory`* - 1 MetalBlock 1 Extract, 1000 SP. Latch or flip-flop.
- `FireworkLauncher`* - 1 Gear 2 TreatedPlank, 700 SP. Uses 20 Fireworks per show.
- `Detonator`* - 1 MetalBlock 1 Explosives 1 Extract, 1400 SP. Placed on dynamite; sets it off on a signal.
- `HttpLever`* / `HttpAdapter`* - 2 Gear 2 Scrap / 2 Gear 4 Scrap; 5000 / 7500 SP. Signals to or from an external HTTP API.

## 3. Folktails buildings
FT uses every shared building in section 2 with the same stats. Shared: automation, Path/Stairs/Platforms/Overhangs/Bridges/Gate/Airlock, District Center/Crossing, Hauling Post, Builders' Hut, Gatherer, Lumberjack, Forester, Tapper's Shack, Gear and Wood Workshops, Dam, Levee, Floodgates, valves, Impermeable Floor, Dynamite, Tunnel, Terrain Block, Dirt Excavator, Explosives Factory, Scavenger, Smelter, power shafts, Clutch, Gravity Battery, Geothermal Engine, Inventor, Bot Part Factory, Bot Assembler, Warehouses, Tanks, Aquifer Drill, Centrifuge, Discharge, Compact Mechanical Pump, Campfire, Rooftop Terrace (8 users), Teeth Grindstone, Medical Bed, Detailer (FT size 1x2x1), Shrub, Lantern, Roofs, Bench, Wood Fence, Stream Gauge, Banners, Beaver Statue.
- **FT cost differences:** Explosives Factory 30 Plank 30 Gear 30 MetalBlock (IT uses 60 MetalPart). Scavenger Flag 250 SP. Population/Resource/Science Counters use Paper instead of MetalPart. Beaver Statue 50 Log 10 Plank.
- **FT does not have:** any building listed in section 2 that is IT-only (Breeding Pods, Barracks, Rowhouses, Industrial Piles, Industrial Lumber Mill, Farmhouse, Fermenter, Food Factory, Oil Press, Hydroponic Garden, Coffee Brewery, Deep pumps, Badwater Pressurizer, Irrigation Barrier, Compact/Large Water Wheel, Large Power Wheel, Steam Engine, Numbercruncher, Charging Station, Control Tower, Grease Factory, Metalsmith, Efficient Mine, Tubeways, IT wellbeing, IT decorations Bell/Brazier/Bust/Clock/Metal Fence, IT monuments).

### Wood
- `LumberMill` - 2x3x3, 15 Log, 0 SP, W1 (bot 500 SP), 50 hp. 1 Log -> 1 Plank / 1.25 h. Injury −0.1 Low.
- `PaperMill` - 3x2x2, 40 Log 40 Plank 15 Gear, 250 SP, W1 (bot 1000 SP), 80 hp. 1 Log -> 2 Paper / 1.56 h. Injury −0.6 Medium. Paper is a Box good.
- `PrintingPress` - 2x4x2, 50 Plank 30 Gear 30 MetalBlock, 400 SP, W2 (bot 1000 SP), 150 hp. Injury −0.6 Medium. Recipes:
  - 1 Paper -> 1 Book / 3 h (Books = Fun +3; each read gives +0.4)
  - 2 Paper + 1 Plank -> 2 PunchCard / 1.5 h (bot boost)

### Food
- `EfficientFarmHouse` - 2x3x2, 25 Log, 0 SP, W3, output 50. Plants and harvests Farmhouse crops (Carrot, Potato, Wheat, Sunflower).
- `AquaticFarmhouse` - 3x2x2, 30 Log 10 Plank, 150 SP, W2 (bot 500 SP), output 50. Plants Cattail and Spadderdock in water exactly 1 deep.
- `Grill` - 2x2x3, 25 Log, 0 SP, W1 (bot 750 SP). Fuel: 1 Log per 10 cycles. Recipes:
  - 1 Potato -> 4 GrilledPotato / 0.52 h
  - 1 Chestnut -> 2 GrilledChestnut / 0.33 h
  - 1 Spadderdock -> 3 GrilledSpadderdock / 0.4 h
- `Gristmill` - 3x2x3, 40 Log 20 Plank 20 Gear, 180 SP, W1 (bot 750 SP), 60 hp. 1 Wheat -> 1 WheatFlour / 0.5 h; 1 CattailRoot -> 1 CattailFlour / 0.25 h.
- `Bakery` - 2x3x4, 15 Log 15 Plank 10 Gear, 160 SP, W1 (bot 750 SP). No power. Fuel: 1 Log per 10 cycles. Recipes:
  - 1 WheatFlour -> 5 Bread / 1 h
  - 1 CattailFlour -> 4 CattailCracker / 0.5 h
  - 1 WheatFlour + 1 MapleSyrup -> 3 MaplePastry / 1.5 h (Nutrition +3)
- `Beehive` - 1x1, 10 Log 15 Plank 20 Paper, 400 SP. Every 2 h it pollinates 3 plants within radius 3, cutting their growth time by 30%. Bee stings: −1 at Medium probability to beavers within 3 tiles (BeeSting recovers at 0.75/day). Keep hives away from paths and homes.
- FT crops and trees: see 10 §7.

### Housing (Lodges breed kits; see 00 for the birth rule)
- `Lodge` - 2x2x1, 12 Log, 0 SP, 3 beds.
- `MiniLodge` - 1x2x1, 5 Log, 50 SP, 1 bed. **Does not breed** (no procreation spec). Use it to house adults without adding births.
- `DoubleLodge` - 2x2x2, 20 Log, 150 SP, 6 beds. Entrance at level 1 (needs a path up there or Stairs).
- `TripleLodge` - 3x2x2, 35 Log, 250 SP, 9 beds. Entrance at level 1.
- All homes: Sleep +0.2/h and Shelter +0.3/h while inside.

### Storage
- `SmallPile` - 1x1, 2 Log, 20 Pileable. `LargePile` - 3x3, 6 Log, 180 Pileable.
- `UndergroundPile` - 3x3x2, 20 Log 40 Plank 20 Gear, 1000 SP, 1000 Pileable. Entrance at level 1.

### Water
- `WaterPump` - 2x3x3, 12 Log, 0 SP, W1. 1 Water / 0.33 h. Pipe depth 2. Output × (1 − contamination).
- `LargeWaterPump` - 3x4x4, 20 Log 5 Gear 10 TreatedPlank, 400 SP, W3 (bot 400 SP). 5 Water / 1 h. Pipe depth 4.
- `MechanicalPump` - 3x3x4, 50 Gear 15 TreatedPlank, 2000 SP, 500 hp, no workers. Moves 0.25 water units/s. Pipe depth 5.
- `BadwaterPump` - 2x3x3, 20 Log 10 Gear 5 MetalBlock, 250 SP, W1 (bot 800 SP). 1 Badwater / 0.33 h, pipe depth 2.
- `BadwaterDome` - 3x3x3, 100 Plank 200 Gear 100 MetalBlock, 2000 SP. Sits on a badwater source and seals it (open/closed/automated). A sealed source also stops in drought.
- `BadwaterRig` - 3x3x4, 400 Gear 200 TreatedPlank 150 MetalBlock, 4000 SP, W10 (default 5; bot 2000 SP). Sits on a badwater source, seals it and extracts 40 Badwater / 10 h. Injury −0.8 High.
- `ContaminationBarrier` - 1x1, 5 Plank 1 MetalBlock, 400 SP. Blocks soil contamination only (moisture still passes, unlike the IT Irrigation Barrier). The ring must be unbroken, diagonals included.

### Power
- `PowerWheel` - 3x1x2, 20 Log, 0 SP, W1 (beavers only), -50 hp. Works only while staffed.
- `WaterWheel` - 3x2x3, 50 Log, 0 SP, -270 hp at full flow. Needs flowing water.
- `WindTurbine` - 3x3x4, 20 Log 20 Plank, 120 SP, -150 hp. Needs wind strength 0.3+.
- `LargeWindTurbine` - 3x3x5, 40 Plank 20 Gear 30 Paper, 1400 SP, -300 hp. Needs wind 0.2+.
- Wind changes every 5-12 h, strength 0-1 (10 §13). Wind works in droughts; pair turbines with a Gravity Battery.

### Science
- `Observatory` - 3x3x5, 80 Plank 30 Gear 10 PineResin, 1000 SP, W4 (bot 7500 SP), 200 hp. 12 SP per 4 worker-hours, so about 3 SP/h per worker and 12 SP/h fully staffed [derived].
- `Refinery` - 3x2x4, 30 Plank 10 Gear 10 MetalBlock, 400 SP, W2 (bot 2500 SP). Injury −0.6 Medium. Recipes (6 h, 2 crop + 2 Water): Carrot -> 5 Biofuel, Potato -> 30 Biofuel, Spadderdock -> 25 Biofuel. MapleSyrup + Extract -> 3 Catalyst / 3 h. Biofuel is the FT bot "food"; store it in a tank.
- FT bot chassis also needs 1 Biofuel (5 Plank 1 MetalBlock 1 Biofuel / 18 h).

### Metal
- `Mine` - 5x5x3, 250 Log 350 Gear 200 TreatedPlank, 4000 SP, W10 (bot 1000 SP). Injury −0.8 High. Must sit on UndergroundRuins. 1 TreatedPlank -> 5 Scrap / 18 h (no Extract recipe, unlike the IT Efficient Mine).

### Paths (Ziplines, +150% move speed)
- `ZiplineStation` - 3x2x4, 20 Log 40 Plank 20 MetalBlock, 700 SP. Where beavers get on and off.
- `ZiplinePylon` - 1x1x4, 20 Plank 10 Gear 10 MetalBlock, 500 SP. A mid-route tower.
- `ZiplineBeam` - 1x3x1, 20 Plank 10 Gear 10 MetalBlock, 600 SP. A cable anchor on a beam (for cliffs and platforms).
- Each tower links to at most 2 others, up to 30 tiles apart. The cable needs a clear line.

### Wellbeing (attractions give 0.6 points/h unless noted)
- `Shower` - 1x2x3, 10 Log 1 Plank, 50 SP. WetFur 1.0/h. Needs water under its pipe, at most 3 deep.
- `ContemplationSpot` - 1x1, 10 Log, 100 SP. SocialLife +1.
- `Lido` - 4x3x2, 40 Log 30 Plank, 250 SP. Fun +1 and WetFur 0.5/h. Needs water at least 0.2 deep at its pool tile.
- `Sauna` - 2x2x1, 10 Log 10 Plank 5 Gear, 300 SP. Fun +1. Uses 0.2 Log/h.
- `Herbalist` - 2x2x3, 10 Plank 20 Gear, 300 SP, W1 (bot 750 SP). 1 Paper + 2 Dandelion + 2 Berries -> 2 Antidote / 2 h. Antidote cures badwater contamination (+0.125 per dose). Store it in a tank.
- `Agora` - 5x5x4, 150 Log 60 Plank, 400 SP. Social +3. Uses 0.2 Extract/h.
- `Carousel` - 5x5x3, 50 Plank 50 Gear 40 MetalBlock, 600 SP, 400 hp. Fun +3.
- `DomedGarden` - 5x5x5, 60 Plank 40 Gear 20 TreatedPlank, 800 SP. SocialLife +2 and WetFur 0.4/h. Uses 0.2 Water/h.
- `DanceHall` - 5x5x2, 100 Log 50 TreatedPlank 20 MetalBlock, 1200 SP. Social +5.
- `MudPit` - 3x3x1, 60 Log 40 TreatedPlank 20 Wheat, 1800 SP. Fun +3. Uses 0.5 Dirt/h.

### Decoration (Aesthetics by area)
- `Scarecrow` - 5 Log 10 Paper, 200 SP, +1, r2.
- `Weathervane` - 5 Log 1 Plank, 250 SP, +1, r3.
- `BulletinPole` - 20 Plank 2 MetalBlock, 600 SP, +2, r3.
- `Hammock` - 2 Log 2 Plank, 120 SP. A rest place.
- `Hedge` - 3 Log, 150 SP. Looks only.

### Monuments (Awe; area effect)
- `FarmerMonument` - 2x2x4, 200 Log, 1000 SP, +2, r7.
- `BrazierOfBonding` - 2x2x5, 400 Plank, 3000 SP, +4, r10.
- `FountainOfJoy` - 5x5x5, 400 Plank 200 TreatedPlank, 9000 SP, +6, r20.
- `HallOfAbundance` - 5x5x3, 700 Plank 300 TreatedPlank 500 MetalBlock, 15000 SP, +8, r30.
- `EarthRecultivator` - 7x7x8, 2000 Gear 2000 TreatedPlank 1500 MetalBlock, 20000 SP, W10 (bot 5000 SP), up to 40 builders, +10, r40. The FT wonder. Launching it needs 500 Extract + 500 Paper.

### Not player buildings
`DevPowerGenerator`, `DevWaterSource`, `BlockOccupier`, `ModularShaftParts` and `EarthRepopulator.Plane` are dev tools or model helpers. Map-editor objects (Slope, Natural Dam, Relics...) are not buildable; see 10 §16.

## 4. Conflicts and corrections vs `02-numbers.md`
- **Numbercruncher:** 02 left "16 h vs 24 h" open. Code says it adds progress every tick while finished, so **24 h/day, about 240 SP/day**. It is unconfirmed whether output scales down at partial power.
- **Rooftop Terrace capacity:** IT 10, FT 8 (02 gives no per-faction number).
- **Lumber mill output:** 02 gives "25.6 planks/day" for the IT mill, which assumes a 16 h shift with 2 workers. That matches if work hours are 16; at 24 h it would be about 38.
- **Large Power Wheel:** `[web]` says "does not transmit power". In practice it feeds shafts it touches (it works in the current save). Do not rely on chaining other consumers through it.
- **Natural Dam height:** `03-water-engineering.md` cites the wiki's 0.5. The blueprint says **0.65** (FinishableWaterObstacle), the same as a built Dam. Use 0.65.
- **Discharge:** both factions, W1, bot 250 SP. Its recipes are FlowingWater and FlowingBadwater, 3 goods per hour each.
- **Mini Lodge does not breed** (no procreation component), unlike the other lodges.
- Everything else checked in 02 matches the game data: storage capacities, housing, power values, Breeding Pod, crop times, and SP costs for the Lantern, Medium Tank, Scavenger Flag and Hydroponic Garden.
