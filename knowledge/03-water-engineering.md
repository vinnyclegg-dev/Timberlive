# 03 — Water engineering

Tags: [bp] blueprints, [code] decompiled code, [web] see sources.md.

## Water model basics
- Water is a per-tile column with a height (in blocks) and a contamination value 0–1 [code ThreadSafeWaterMap].
- **1 Water good = 0.2 water units in the map** [code WaterGoodToWaterAmountConverter]. One tile × 1 m depth ≈ **5 water goods**.
  - Pumps *remove* water from the map, and Discharge buildings put it back (3 goods/h → 0.6 units/h).
- Reservoir sizing: **tiles × depth(m) × 5 ≈ drinkable goods**.
  - 50 beavers × 9-day drought × 2.12 ≈ 954 goods ≈ 191 tile·m, so a 10×10 basin 2 m deep (before evaporation and irrigation losses).
  - Only water **above the pump's intake depth** counts. Water Pump reaches 2 m, Large Water Pump 4 m, IT Deep Water Pump 6 m [bp pipeMaxDepth].
- **Evaporation is ≈0.045–0.046 m of depth per exposed tile per day** [web W-EVAP: 0.04608 × evaporation value; Steam player measurement 0.045/day]. 1 m of depth lasts ~22 days on evaporation alone. The raw constant is 0.0001 per tick, 10× faster when depth < 0.02 [bp WaterSimulator].
  - Examples: a 1×10 channel loses 0.21 m/day; a 3×10 channel loses 0.063 m/day [W-EVAP].
  - Go deep, not wide. Covering water with floors doesn't stop evaporation [W-EVAP].
  - Example: 180 m³ stored 6 deep loses ~1.35 m³/day; the same volume 2 deep loses ~4.05 m³/day.
- Source strength is in m³/s; most map sources are strength 1 [W-WS].
- 1.0 map objects [W-V1]:
  - Water Seep: spills only up to 0.8 m.
  - Natural Dam: holds 0.65 [bp] (the wiki says 0.5).
  - **Badtide Drain:** emits badwater only during badtides; indestructible [W-BTD].
  - **Aquifer:** underground source, active in temperate weather; needs an Aquifer Drill.
- **Water sources** (map springs) emit continuously in temperate weather and **stop in drought**. In **badtide** they emit badwater (contaminated) [web; code HazardousWeather].
- **Pump efficiency = 1 − contamination at the intake** [code WaterInputManufactoryLimiter]. 50% contaminated water halves output, and pure badwater gives ~0. Pumps always deliver clean drinking water; they "filter", but slow down.
- **Irrigation range** = 2 × adjacency score (score cap 8).
  - Up to **16 tiles** from the edge of a 3-wide channel or a 3×3 pool. A single river gives ~10 tiles in practice.
  - **Each +1 block of elevation costs 6 tiles of range.** Downhill costs nothing.
  - The route goes through terrain; it doesn't need line of sight.
  - [W-IRR, W-EVAP, STEAM-IRR; bp SoilMoistureSimulator VerticalSpreadCost 6, MaxClusterSaturation 8]
- Water below 50% contamination still irrigates. Exactly 50% neither irrigates nor contaminates. Above 50% it contaminates soil [W-BADTIDE].
  - Crops die after their "dies dry" days (carrots 2, wheat 0.5, potato 1, kohlrabi 2, cassava 3, berry bush 9, pine 13) [bp].
- Soil contamination spreads up to **7 tiles** from water with contamination > 0.5 (each +1 elevation costs 5 tiles) and decays slowly [bp SoilContaminationSimulator; W-BARRIERS]. Plants on badly contaminated soil die in 0.2–0.3 days [W-PLANTS].
- **Badtide water ramps up:** it starts at 50% contamination and rises to 100% over 12 h. It falls back to 50% in the last 12 h, then goes to 0% at sources when temperate weather returns [W-BADTIDE]. Contaminated water already in pools and reservoirs lingers and mixes.
- Barriers (Contamination Barrier FT / Irrigation Barrier IT) must form an **unbroken perimeter, including diagonals** [W-BARRIERS].

## Building toolbox [bp, loc]
| Building | Cost / SP | What it does |
|---|---|---|
| **Dam** | 20 Log / 0 | Holds water to **0.65 m**; excess spills over. You can put a path on top. A 1-deep dammed channel dries in ~14 days from evaporation alone [W-DAM, STEAM-IRR]. On Hard, prefer Levee + Floodgate to save logs. |
| **Levee** | 12 Log / 120 | Blocks water completely (1 block). Stackable. Also blocks moisture above. Use it for reservoir walls and to keep floods out. |
| **Floodgate** (1 m) / **Double** (2 m) / **Triple** (3 m) | 10 Log 5 Plank / 150; 20 Log 10 Plank / 250; 30 Log 15 Plank / 500 | Holds the **upstream** level at an adjustable height (0…max, 0.05 steps); water above it spills over. "Synchronize with adjacent floodgates" is on by default. No path on top. Automatable: On → Automation height, Off → normal height [W-FG, code]. |
| **Fill Valve** (was Sluice) | 5 Plank 5 MetalBlock / 300 | One-way outlet. Fills the downstream side up to a **target height** (default floor + 0.5; can be Unlimited), then closes. Automatable: On → automation target (default = closed). |
| **Throttling Valve** (was Valve) | 5 TPlank 5 MetalBlock / 500 | One-way outlet with a **flow limit** 0–2.0 (default 1.0) and a reaction-speed setting. Automatable: On → automation limit (default 0 = closed). |
| **Impermeable Floor** | 1 MetalBlock / 200 | Floor panel that stops water leaking through it (and moisture above). |
| **Airlock** | 15 Log 8 Gear 4 MetalBlock / 300 | Lets beavers through a wall while blocking water. |
| **Contamination Barrier** (FT) / **Irrigation Barrier** (IT) | 400 SP | Blocks soil contamination spread underneath (the IT one also blocks irrigation). Ring fields next to badwater with these. |
| **Mechanical Pump** (FT 2000 SP, 500 power) / Deep (IT, depth 8) / **Compact Mechanical Pump** (4000 SP, 700 power) | — | Moves map water (or badwater) uphill at 0.25 units/s (≈ 1.25 goods/s). |
| **Discharge** (old "Fluid Dump") | 10 Log 10 Plank / 250, 1 worker | Dumps stored Water or Badwater goods onto the map (recipe: 3 goods per worker-hour). Stops when the outlet tile is ~0.9 m full. A **3×3 levee pond fed by a Discharge** is the most area-efficient irrigator: it covers ~16 tiles each way [W-DUMP, W-IRR]. |
| **Aquifer Drill** | 40 Plank 25 Gear 15 MetalBlock / 400, 400 power | Pulls water from an underground aquifer. A drought-proof source on maps that have aquifers. |
| **Badwater Dome** (FT: 100 Plank 200 Gear 100 MetalBlock, 2000 SP [bp]; the wiki's 1000 SP is stale) / **Badwater Pressurizer** (IT, 4000 SP; was "Badwater Discharge" before 1.1) | — | Seals a badwater source. Open, Closed or Automated. A source sealed by the Dome also stops in drought. The Pressurizer keeps producing in drought [W-DOME, W-V11]. |
| **Badwater Rig** (FT, 4000 SP) | 10 workers | Seals a source *and* extracts 40 badwater per 10 h. |
| **Tanks** | 30 / 300 / 1200 | Stored water goods; immune to evaporation and contamination. |
| **Water Wheel** (FT 270, IT Compact 120 / Large 540) | | Power from flowing water. Needs outflow ≥ 0.15 in the expected direction. Stops in drought unless a reservoir releases through it. |

## Terrain modification [bp]
- **Dynamite** depth 1 (600 SP), **Double** 2 (900 SP), **Triple** 3 (1200 SP).
  - Destroys the terrain under it and **triggers adjacent dynamites**.
  - Cost: Explosives (Explosives Factory: 5 badwater → 1 explosive / 3 h, 400 SP, 150 power) plus Extract for double/triple.
  - Can't go below the map's lowest level. Kills beavers in the blast [loc].
  - Detonate from the building panel or with a **Detonator** (1400 SP; automation-triggered).
- **Tunnel** (2000 SP: 1 Explosives 1 Extract 6 Plank) carves through terrain and leaves a Platform.
- **Terrain Block** (1000 SP, 4 Dirt) adds terrain. Dirt comes from the **Dirt Excavator** (2000 SP; 4 workers, 200 power; 4 dirt / 6 h; high injury risk).
- Use cases:
  - Blast a pit below river level for a deep reservoir. Deeper means less surface per volume (less evaporation) and lets deep pumps keep pulling.
  - Cut channels to redirect a river.
  - Lower a field next to a channel so it stays irrigated.

## Practical layouts
1. **Starter pool (cycle 1, 0 SP).**
   - Put a row of **Dams** across the river just downstream of the pumps. The pool behind them stays wet for a while into the drought and keeps nearby farms irrigated.
   - Pumps go on the upstream (deep) side.
2. **Reservoir with a controlled outlet.**
   - Build a Levee wall around a basin beside the river. Fill it through a Floodgate (or Fill Valve) from upstream.
   - Close the inlet before the drought (Weather Station → floodgate) so the river doesn't drain it back.
   - Feed fields through a **Fill Valve** set to the field channel height, or a Throttling Valve set to a small flow.
3. **Badtide protection.**
   - Close every inlet from the river during badtide: Weather Station (Badtide) OR Contamination Sensor (> 0.05) → floodgates up / valves closed. See 04-automation.md.
   - Keep the clean reservoir sealed until the river is clean again. Contamination lingers after the badtide ends, so add a Timer Delay of 12–24 h before reopening.
   - Don't let beavers path *through* water deeper than ankle depth during badtide. Use bridges, platforms or Airlocks. Wading in water with ≥5% contamination risks infection (3-day incubation, can't work until cured).
   - Keep fields 7+ tiles from contaminated water, or behind Contamination/Irrigation Barriers.
3b. **Sluice replacements (Sluice was removed in 1.0; 1.1 converts old ones to Fill Valves, which then need reconfiguring)** [W-SLUICE, W-FV, W-V11]:
   - *Basic sluice:* Fill Valve at 0.75 m. It can drain the upstream side, so put a Dam (0.65) next to it.
   - *Improved sluice:* Depth Sensor upstream "> 0.70 m" → Fill Valve, with On = 0.75 m and Off = 0.00 m. This protects the upstream reserve.
   - *Contamination close:* Contamination Sensor "> 0.05" (old sluice default 5%; players use 1–5%) → valve. Hold it closed with a Delay timer.
   - The Fill Valve has its own level control loop, so it flaps less than an automated floodgate [STEAM-DELAY].
3c. **Auto-irrigation pond (hysteresis)** [HAMATTI]: 3×3 levee pond (12 levees) + Discharge + 2 Depth Sensors + Memory (Set-Reset). The sensor reading "< 0.30 m" sets the memory, the one reading "> 0.85 m" resets it, and the memory drives the Discharge. It irrigates ~16 tiles each way and draws on tank water only when needed.
4. **Irrigation channel.** A 1-wide channel fed by a Fill Valve at a fixed target height irrigates both banks. Valves are one-way, so the field channel can't back-drain the reservoir.
5. **Floodgate stair for level control.** Use Floodgates rather than Dams where you want to adjust levels later. Set the height to the water level you want to hold. In drought, raise them to max to stop all outflow (or automate it).
6. **Deep pump pit (IT).** The Deep Water Pump reaches 6 m. Blasting a 3–6 m pit at the river bed gives a drought-proof pump intake.

## Common water mistakes
- Pump intake on a shallow edge. When the river drops, the pump is above the water. Put intakes in the deepest spot, or inside the reservoir.
- Reservoir connected to the river with no gate. In a drought the reservoir drains back out downstream.
- Fields higher than the water. Irrigation barely climbs (vertical cost ×6).
- Damming so high that the town floods. Floodable buildings stop working and plants drown ("dies flooded" times in [bp]: carrots 2 d, trees 10–16 d).
- Forgetting that badwater flows *in* through the same inlets as water. Every inlet needs a closable gate or valve.
- Water wheels on the reservoir outlet. They waste stored water during drought unless you mean to spend it.
- Water wheels: narrow channels upstream of a wheel back up and overflow, so widen them or blast them deeper. Cascade several drops with a wheel at each one [STEAM-WHEEL, GP]. FT wheel = 270 hp per m³/s of flow and needs flowing water 2 wide [W-WHEEL].
- Wide shallow pools, no spillway (a full reservoir overtops onto farms), and spending logs on giant levees before pumps, tanks and food [WOTH-DAM, low confidence].
- Using levees as long flow guides hurts performance. The wiki suggests terrain blocks instead when you can [W-LEVEE].
- Drinking water and irrigation water should be separate systems [STEAM-IRR].
- Players blast irrigation trenches ~20 tiles apart to cover farmland [STEAM-IRR]. Detonate at night (Chronometer 2–3 am → Detonator) so beavers aren't nearby [W-DET].
