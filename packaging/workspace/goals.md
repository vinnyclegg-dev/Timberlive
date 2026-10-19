# Colony goals

## Standing task
1. **Grow the population steadily, and only on a sustainable base.**
   - Expand food and water production first. Add population (Breeding Pods, or homes for Folktails) only when the surplus can support it, through the next hazard.
   - Keep pods running whenever the projected stock covers them. Pause them only when water or food would run out before the hazard ends.
2. **Get at least one of every building.** Some will need several copies to keep their materials supplied.
   - Track progress with `harness/progress.py`, or `--markdown` for a table.

## Water-engineering goals (keep these in mind every cycle)
1. **Hold water in the river with dams.** Before each drought, dam the river downstream of the pumps and fields so a reservoir survives.
2. **Keep badwater out of the fresh water during badtides.** Use levees and floodgates (automated with a Contamination Sensor) to divert a contaminated inflow away from the pumps, reservoir and fields.
3. **Cap or divert badwater sources off the map to reclaim contaminated land.** Find each source with `harness/underground.py` and either block it or route it off-map.

## How growth is gated
For each step up in population, check these first:
- **Water:** storage of at least beavers × 2.12 × (longest hazard so far + 2 days), plus building water (`monitor.py production` WATER BUDGET). Pump output must exceed consumption by at least 20% in temperate weather.
- **Food:** storage of at least beavers × 3 × 1.5 × longest hazard so far, using irrigated fields where possible.
- **Housing:** free beds for the next kits.
- **Workers:** every new building needs staff.

## Hazard log
Record each drought and badtide here: start date, length, beavers, water and food at the start and the end. Size the next reserve on the **longest** hazard so far.

| Hazard | Days | Beavers | Water used | Food used | Next target (1.5x) |
|---|---|---|---|---|---|
