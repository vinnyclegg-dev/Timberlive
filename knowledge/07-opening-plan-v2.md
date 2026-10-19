# Opening plan v2 (written after game "d")

**Superseded by `07-opening-plan-v3.md`** (map-independent). Keep this file for its timings from game "d" only.

**Top priority: get to planting trees fast.** In game "d", wood ran out by cycle 2 and stalled everything.

The chain to tree planting (Iron Teeth):
1. Logs, from lumberjacks
2. Inventor, to earn 30 science
3. Unlock the Forester
4. Planks: an Industrial Lumber Mill powered by a Compact Water Wheel on the river
5. Build the Forester (10 logs + 7 planks) and mark birch and pine to plant beside the lumberjacks

## Day 0: scout, place the opening batch, unpause within about a minute
1. **Scout.**
   - water sources and flow arrows (`view_map`, `/api/map/water-sources`)
   - the nearest large tree stand
   - berries, slopes and badwater
   - where the river flows fastest (for the water wheel)
2. **Wood:**
   - 3 lumberjack flags right next to the biggest stand, with a path
   - mark the cutting area over the whole stand
   - a log warehouse beside them
3. **Water:** a Deep Water Pump at the deepest spot upstream of any badwater, with a path. Set it to VeryHigh, because Normal difficulty starts with 0 water.
4. **Food:** a gatherer flag on the berries.
5. **Farm:** a farmhouse and about 50 kohlrabi tiles on low ground beside the river.
6. **Storage:** 2 small tanks, set to Water at once.

## Days 1–5: get to tree planting
7. **Inventor** (12 logs), priority High. About 20 science a day, so 30 takes about 1.5 days.
8. **Compact Water Wheel** (25 logs, no workers, 120 power) on flowing river, linked by power shafts to an **Industrial Lumber Mill** (20 logs, 2 workers, 75 power).
   - Avoid the Large Power Wheel early: its 4 walkers are too many workers.
9. **Unlock the Forester** (30 science), then build it.
   - Mark **Birch** (the fastest grower) and Pine to plant in the cutting area as it's cleared, so the forest replants itself.
   - **Target: tree planting running by about day 6.**
10. **Barrack** (40 logs).
11. **First 1–2 Breeding Pods** once water and food are both positive, about day 5.
    - The starting beavers are old and begin dying of age around cycle 2.
    - Keep pods running unless stock would truly run out.

## Days 5–12: prepare the first drought (game "d": it arrived on day 16 and lasted 3 days)
12. **Second farmhouse and fields.**
    - Food storage target: beavers × 2.67 × 6, covering 3 drought days plus 3 days of regrowth. That's about 210 for 13 beavers.
    - Add warehouses for kohlrabi.
13. **Water:**
    - a second pump
    - tanks up to at least 150
    - a **dam line downstream of the pumps** (about 4 Dams, 20 logs each), so a reservoir survives. In game "d" the river dried out completely.
14. **More wood:** a second Forester or more lumberjacks if logs stay near 0.
15. **Ongoing:** a second barrack and more pods as the surplus allows. Population grows only on a sustainable base.

## Cycle 2 onward
16. **Science unlocks:**
    - Levee (120), Floodgate, Medium Tank (120)
    - Builders' Hut (100), Gear Workshop (100)
    - Lever and Relay, then the Weather Station, to start automation
17. **Badwater:**
    - map the badwater sources
    - divert or cap them with levees and floodgates
    - add a contamination sensor to close floodgates during badtides
18. **Wellbeing:** Campfire, Rooftop Terrace, Teeth Grindstone, then Scratcher, Double Shower and so on.
19. **Metal:** Scavenger Flag, then Metalsmith, then everything else, working toward one of every building (115).

## Stream habits
- Narrate every decision and keep the overlay plan current.
- The camera follows every action. No pausing except in emergencies.
- After every placement batch, check `pathTile`, statuses, and storage goods.
- Never set workers to 0. Use pause instead.
