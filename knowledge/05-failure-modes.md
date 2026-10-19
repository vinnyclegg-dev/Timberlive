# 05 — Failure modes: detect early, prevent

Format: **cause → early signal (what to poll) → prevention or fix.** Tags: [bp]/[code] ground truth, [web] see sources.md.

Base facts:
- Need meters run from −3 to +1.
- **Hunger:** death ≈3.75 days after the "Starving" status (≈5 days from fully fed). Starving costs −50% work speed and −40% kit growth.
- **Thirst:** death ≈4.29 days after "Dehydrated" (≈5.7 days from full). Dehydration costs −25% movement.
- Both cost −10 wellbeing while unmet.
- **Lose** = all characters dead. An IT pod with nutrients for a full embryo prevents game over [code/bp/web].

## 1. Starvation spiral (the #1 killer, per players)
- **Cause:** food production below 2.67 × population. Or the drought dries the fields: crops die after 0.25–3 days dry and then need 3–12 days to regrow, so food lags far behind water recovery. Starving farmers work at half speed, which makes the gap worse.
- **Signals:**
  - Days of food = stock ÷ (2.67 × pop). Alert when < 5 in temperate, or < hazard days + regrow days before a hazard.
  - Ripe crops left unharvested (farmers are short).
  - "Starving" statuses. The 1.1 Statistics tab shows trends.
- **Prevent:**
  - Food buffer ≥ pop × 2.67 × (max drought + crop regrow).
  - Irrigate fields from a reservoir so they survive the drought.
  - Use 2+ crop types with different dry tolerance (FT sunflower 3.5 d, IT cassava 3 d).
  - Beavers don't eat unharvested crops, so staff farms before anything else.
- **Fix:**
  - Raise farmhouse and gatherer priority. Pause non-food workplaces to free workers.
  - Stop growth: no new beds (FT), pause pods (IT).
  - Plant the fastest crop (kohlrabi 3 d, carrot 4 d).

## 2. Dehydration
- **Cause:**
  - Too few pumps.
  - Pump intake runs dry. FT Water Pump reaches 2 m, Large 4 m; IT Deep 6 m.
  - Not enough stored water for the drought.
  - **Badtide:** pump output scales with (1 − contamination), so a 100% badtide river gives ~0 water [code].
- **Signals:**
  - Days of water = stock ÷ (2.12 × pop).
  - Pump "not functional" warnings (added in 1.0).
  - Depth Sensor at the pump intake.
  - Tank fill falling during temperate weather.
- **Prevent:**
  - One pump per ~20 beavers (≈48/day each at base speed).
  - Water stock ≥ 2.12 × pop × max hazard days × 1.3.
  - A reservoir 2+ m deep in front of the pumps, gated so it can't drain downstream.
  - Clean water isolated from badtide inflow (floodgates or valves).
- **Fix:**
  - Move or add pumps at the deepest water.
  - Pause water-using industry (Steam Engine, Breeding Pods, Domed Garden, Dance Pit).

## 3. Badtide contamination
- **Mechanics:**
  - Beavers in water with ≥5% contamination have a chance to get infected. Incubation is 3 days.
  - Then: −10 wellbeing, −70% movement, **refuse to work**, non-basic needs frozen.
  - **No natural recovery.** FT needs 8 antidotes over ~4 days (Herbalist, 300 SP). IT uses a Decontamination Pod (400 SP, 1 beaver per pod).
  - Bots are immune.
  - Soil gets contaminated within 7 tiles of >50% water, and plants there die in 0.2–0.3 days.
  - [code, bp, web]
- **Signals:**
  - Population Counter "Contaminated total" > 0.
  - Status "Beaver is unwell" during incubation. That's the window to fix paths.
  - Contamination Sensor > 0.05 on inlets.
  - Weather panel "Badtide approaching".
- **Prevent:**
  - Before cycle 5 (Normal), get gates or valves on every inlet, a bypass channel, and Contamination/Irrigation Barriers around fields.
  - Paths must not wade through rivers: use bridges, platforms or Airlocks, or close automated Gates during a badtide.
  - Have the Herbalist or Decontamination Pod built before the first badtide.

## 4. Overpopulation
- **Cause:**
  - FT lodges breed whenever a bed is free (18.75%/day per lodge with 2+ adults) [code].
  - IT pods breed regardless of housing, at 5 water + 5 berries per kit.
  - New mouths arrive just before a drought and the stock math breaks. Kits eat but don't work for 6 days.
- **Signals:**
  - Free beds > 0 (Population Counter "Free beds").
  - Pop growth faster than food/water production.
  - Homeless count > 0, which costs −3 shelter wellbeing.
- **Prevent:**
  - Build beds only when production has ~20% headroom.
  - IT: pods run only in temperate weather with surplus. Automate with Weather Station + Population Counter.
  - Births in waves cause waves of old-age deaths ~50 days later (lifespan 50 ±10%). Stagger housing.

## 5. FT growth stalls (the opposite)
- **Cause:**
  - No vacant bed.
  - Fewer than 2 adults in the home.
  - 24 h work hours, so beavers never go home and births happen at night [web].
- **Fix:** add a lodge and keep working hours < 24.

## 6. Wood collapse
- **Cause:** the starting forest is cut out by cycle 1–2. Lumber mills and planks drain logs. No Forester.
- **Signals:** log stock trend negative for 2+ days. Lumberjack flags idle or "nothing to cut".
- **Prevent:**
  - Forester (30 SP) in the first days, with many planted tiles ("you're never planting enough").
  - Birch for speed, oak and maple for volume, pine for resin.
  - Resource Counter → pause the Lumber Mill when planks > target.

## 7. Worker shortage, idle builders, hauling gridlock
- **Cause:**
  - Only 4 DC builders.
  - Long walks.
  - Too many workplaces for the adult count. Kits don't work and injured or contaminated beavers refuse to work.
- **Signals:**
  - Population Counter "Vacancies" > 0 on critical buildings.
  - Construction sites waiting for materials.
  - Goods piling up at producers.
- **Fix:**
  - Hauling Post (×2 carry; keep one at high priority).
  - Builders' Hut.
  - "Prioritize by haulers" on construction sites.
  - Lowest priority on inventors so they soak up idle beavers.
  - Pause non-essential workplaces (automation: Weather Station → NOT → pause list).

## 8. Injuries
- **Cause:**
  - Risky workplaces: Dirt Excavator, Explosives Factory, Bot Assembler and Centrifuge (high); Smelter, Paper Mill and Wood Workshop (medium); Lumber Mill (low).
  - Lumberjacks get chipped teeth (−75% cutting).
- **Signals:** "Injured" statuses; Population Counter "Unhealthy workers".
- **Fix:**
  - Medical Bed (80 SP): heals in ~2.2 days instead of ~10.
  - Teeth Grindstone (5 Log, 0 SP).
  - Bots in risky jobs.
  - [bp WorkshopRandomNeedApplier, web]

## 9. Wellbeing collapse
- **Cause:** unmet basic needs (−10 each for hunger and thirst), no variety, no attractions.
- **Effect:** work speed falls back to base. You lose +20%/+40%/… (wellbeing 5/10/…) and the lifespan bonus [bp].
- **Signals:** average wellbeing trend. Alert if it drops by 3+.
- **Prevent:**
  - Cover the basics first.
  - Then cheap +1s: Campfire, Rooftop Terrace, Shrub, Lantern, Roof, Shower, food variety.
- **Note:** IT may be locked until FT reaches average wellbeing 15 [web: wiki Folktails page]. Relevant if a fresh profile has IT locked.

## 10. Flooding your own town
- **Cause:**
  - Dams overflow at 0.65 m.
  - Raising a reservoir floods the plateau.
  - A badtide or the post-drought surge (water has momentum) floods low buildings.
  - Floodable buildings stop, and plants drown (carrots 2 d).
- **Signals:** Depth Sensor near town > 0. "Flooded entrance" warnings (1.0).
- **Prevent:**
  - Spillway and overflow route on every reservoir.
  - Floodgates instead of dams where the level matters.
  - Build the town ≥1 level above the river.

## 11. Hazard-length underestimate
- **Cause:** durations ramp. Normal starts at ×0.38 and reaches full 5–9 days by cycle 6. Hard reaches 15–30 days by cycle 13. Badtides on Normal ramp toward 4–8 days.
- **Prevent:** always size for the **max of the full range** (Normal 9 days, Hard 30), not the last hazard's length.

## 12. 1.0 map hazards
- **Unstable Cores:** explode with up to a 5-tile radius once triggered; you can't disarm them.
- **Badtide Drains:** spew badwater only in badtides; indestructible.
- **Thorns:** injure beavers that demolish them.
- Survey the map for these at game start [web 1.0 notes].

## 13. Automation pitfalls
- A Resource Counter not on a district path reads Off, so everything it drives **pauses**.
- A deleted transmitter disconnects inputs, so paused buildings **resume**.
- The HTTP API stops on every load; press Start API again.
- See 04-automation.md §5.

## Monitoring dashboard for the agent (poll every in-game hour)
- days_water = water ÷ (2.12 × pop)
- days_food = food ÷ (2.67 × pop)
- Days until the hazard, and its type
- Max hazard days for this cycle (from the difficulty table)
- Free beds, homeless, vacancies, unemployed
- Contaminated count, injured count
- Log and plank trend over the last 2 days
- Average wellbeing trend
- Pump intake depths (Depth Sensors), reservoir depth

**Alarms:**
- days_water or days_food < max hazard days + 2
- contaminated > 0
- log trend < 0
- free beds > 0 within 3 days of a hazard
