"""Water engineering monitors (plan sections 5-7): dams, pumps, badwater, fields by held water, reservoirs,
power that survives a drought, cores and the per-cycle water review.

All numbers come from foreman/hydro.py (plain Python on the map snapshot). Fixes are the planner's exact
harness calls; the playing AI decides whether to run them.
"""

from __future__ import annotations

import math
from collections import deque

from ..findings import Finding, monitor
from .. import hydro
from .land import CROPS, TREES

KEY = ("DistrictCenter", "Barrack", "Lodge", "BreedingPod", "FoodFactory", "Fermenter", "GearWorkshop", "Smelter",
       "Metalsmith", "IndustrialLumberMill", "LumberMill", "Inventor", "MediumWarehouse", "LargeWarehouse",
       "SmallWarehouse", "MediumTank", "LargeTank", "SmallTank", "HydroponicGarden", "OilPress", "WoodWorkshop")
FLOW_GENERATORS = ("WaterWheel", "CompactWaterWheel", "LargeWaterWheel")
STEADY_GENERATORS = ("SteamEngine", "GravityBattery", "GeothermalEngine", "WindTurbine", "LargeWindTurbine",
                     "LargePowerWheel", "PowerWheel")
FOOD_POWER = ("FoodFactory", "Fermenter", "Grill", "Bakery")
FOOD_POWER_HP = 170          # Fermenter 50 + Food Factory 120 (rule power-drought-proof-backup)
FLOOD_MARGIN = 0.2           # a key building less than this above the water at its own level is at flood risk
NEAR_NETWORK = 6             # two networks this close can be joined with a few shafts
FIRST_DAM_DAY = 5            # rule dam-early: first dam in cycle 1 day 2-5


def _cycle(world) -> tuple[int, int]:
    tm = world.colony["time"]
    return tm["cycle"], tm["cycleDay"]


def _h(world):
    return hydro.analysis(world)


@monitor("water.underground", rules=["underground-assess", "hazard-unstable-core"])
def underground(world, ctx):
    """Unstable Cores (blast cycle and effects), pressurised cave water, and the new-map assessment."""
    h = _h(world)
    if not h:
        return
    cycle, day = _cycle(world)
    if cycle == 1 and day <= 2:
        fed = "; ".join(f"{g['name']} z{g['z']} -> {len(g['downstream'])} bodies" for g in h.source_groups[:6])
        yield Finding("water.underground", "warn", f"new map: trace every source before the opening plan ({fed})",
                      "assess", fix="cd harness && ../runtime/python underground.py --refresh")
    for c in h.cores():
        cyc = c["countdownCycle"]
        soon = isinstance(cyc, (int, float)) and cyc <= cycle + 1
        bad = any("BASE" in e or "BADWATER" in e or "buildings" in e for e in c["effects"])
        sev = "critical" if soon and bad else "warn" if soon or bad else "info"
        yield Finding("water.underground", sev, f"Unstable Core ({c['x']},{c['y']},z{c['z']}) countdown cycle {cyc} "
                      f"(+{c['daysAfter']} days), sphere r{c['sphere']}, {c['fromBase']} tiles from the DC: "
                      + "; ".join(c["effects"]), f"core-{c['x']}-{c['y']}", [c["x"], c["y"], c["z"]], c,
                      fix="" if not bad else "plan a Levee/Dam line outside the sphere before its cycle (see /api/water dams)")
    for b in h.bodies:
        if len(b["full"]) >= 4:
            x0, y0, x1, y1 = b["bbox"]
            yield Finding("water.underground", "info", f"W{b['id']}: {len(b['full'])} pressurised cave tiles in "
                          f"x{x0}-{x1} y{y0}-{y1} (head z{b['head']}): digging or a blast there releases it",
                          f"pressure-{b['id']}", [x0, y0, b["floor"]])


def _held_pumps(h) -> set:
    held = h.held_tiles()
    out = set()
    for b, tiles in h.footprints():
        if b.name in hydro.PUMPS and any((x + dx, y + dy) in held for x, y in tiles for dx, dy in hydro.N8):
            out.add(b.id)
    return out


@monitor("water.dams", rules=["dam-early", "dam-siting", "dam-bank-and-reach"])
def dams(world, ctx):
    """Dams: is any water held yet, are the pumps behind a dam, and can builders reach dam sites."""
    h = _h(world)
    if not h:
        return
    cycle, day = _cycle(world)
    plan = h.dams()
    best = plan["proposals"][0] if plan["proposals"] else None
    held = [p for p in h.pools() if p["full"] and p["region"]]
    if not held and (cycle > 1 or day >= FIRST_DAM_DAY):
        yield Finding("water.dams", "warn" if cycle <= 2 else "critical",
                      "no dam is holding water yet" + (f": best line {best['why']}" if best else ""), "first",
                      list(best["line"][0]) + [int(h.top[best["line"][0][1], best["line"][0][0]])] if best else None,
                      fix="; ".join(best["calls"]) if best else "")
    served = _held_pumps(h)
    for b in world.finished(*hydro.PUMPS):
        if b.id in served:
            continue
        pick = next((p for p in plan["proposals"] if b.label in p["pumps"]), None)
        yield Finding("water.dams", "warn", f"{b.label} draws from water no dam holds: it stops when the river drops"
                      + (f"; {pick['why']}" if pick else "; no clean choke found below it, consider a deck/pond pump"),
                      b.id, [b.x, b.y, b.z], fix="; ".join(pick["calls"]) if pick else "")
    for b in world.buildings:
        if b.finished or b.name not in ("Dam", "Levee", "Floodgate"):
            continue
        tiles = world.footprint(b)
        dry = [(x + dx, y + dy) for x, y in tiles for dx, dy in hydro.N4
               if world.in_map(x + dx, y + dy) and not h.wet[y + dy, x + dx] and (x + dx, y + dy) not in tiles]
        reach = [t for t in dry if world.in_range(t[0], t[1], int(h.top[t[1], t[0]])) is not False]
        if not reach:
            yield Finding("water.dams", "warn", f"{b.label} site has no dry, in-range tile next to it: builders can't "
                          "reach it (extend the line from the bank, or build Stairs/a Platform to it)", b.id, [b.x, b.y, b.z])
    if best:
        yield Finding("water.dams", "info", f"best dam: {best['why']}", "best",
                      [best["line"][0][0], best["line"][0][1], int(best["level"])],
                      {k: best[k] for k in ("kind", "level", "logs", "added", "tiles", "pumps", "builderReach")},
                      fix="; ".join(best["calls"]))


@monitor("water.pumps", rules=["pump-pool-separate", "pump-sites-final-population"])
def pumps(world, ctx):
    """Pump intakes deep and held, and enough clean pump sites for the final population."""
    h = _h(world)
    if not h:
        return
    for b, tiles in h.footprints():
        if b.name not in hydro.PUMPS:
            continue
        depths = [float(h.depth[y + dy, x + dx]) for x, y in tiles for dx, dy in hydro.N8
                  if world.in_map(x + dx, y + dy) and h.wet[y + dy, x + dx]]
        if depths and max(depths) < 0.3:
            yield Finding("water.pumps", "warn", f"{b.label} intake water is only {max(depths):.1f} deep: hold it "
                          "deeper with a dam, apart from the water fields draw on", b.id, [b.x, b.y, b.z])
    sites = h.pump_sites()
    target = math.ceil(1.5 * world.beavers / 5)          # 1 pump per 5 beavers, for 1.5x today's colony
    have = sites["pumps"] + sites["count"]
    if have < target:
        yield Finding("water.pumps", "warn", f"{sites['pumps']} pumps + {sites['count']} free clean pump sites in build range < "
                      f"{target} needed for {math.ceil(world.beavers * 1.5)} beavers: plan Platform decks or a dam pond",
                      "sites", evidence={"target": target, "sites": sites["sites"][:5]})


@monitor("water.power", rules=["power-one-network", "power-drought-proof-backup"])
def power(world, ctx):
    """Power networks that could merge, and food-chain power that stops in a drought."""
    nets = world.power_networks()
    groups = [(k, v) for k, v in nets.items() if v]
    for i, (ka, a) in enumerate(groups):
        for kb, b in groups[i + 1:]:
            d = min(abs(p.x - q.x) + abs(p.y - q.y) for p in a for q in b)
            if d <= NEAR_NETWORK:
                pa = min(a, key=lambda p: min(abs(p.x - q.x) + abs(p.y - q.y) for q in b))
                yield Finding("water.power", "warn", f"two power networks only {d} tiles apart ({pa.label} side and "
                              f"{b[0].label} side): join them with PowerShafts so wheels share the load",
                              f"join-{min(ka, kb)}-{max(ka, kb)}", [pa.x, pa.y, pa.z])
    for k, members in groups:
        food = [b for b in members if b.name in FOOD_POWER]
        if not food:
            continue
        steady = [b for b in members if b.name in STEADY_GENERATORS]
        if not steady:
            yield Finding("water.power", "critical", f"the network feeding {', '.join(b.label for b in food)} runs only on "
                          f"water wheels: it stops when the river dries; add a Steam Engine / Gravity Battery / "
                          f"Geothermal Engine (>= {FOOD_POWER_HP} hp)", f"steady-{k}", [food[0].x, food[0].y, food[0].z])


@monitor("water.flood", rules=["flood-key-buildings-high"])
def flood(world, ctx):
    """Key buildings that sit barely above the water beside them."""
    h = _h(world)
    if not h:
        return
    low = []
    for b, tiles in h.footprints():
        if b.name not in KEY:
            continue
        near = [float(h.surface[y + dy, x + dx]) for x, y in tiles for dx, dy in hydro.N8
                if world.in_map(x + dx, y + dy) and h.wet[y + dy, x + dx] and h.top[y + dy, x + dx] <= b.z]
        if near and b.z - max(near) < FLOOD_MARGIN:
            low.append((b, max(near)))
    for b, s in low[:8]:
        yield Finding("water.flood", "warn", f"{b.label} stands at z{b.z}, only {b.z - s:.2f} above the water beside it: any "
                      "rise (a new dam, a flood) reaches it; keep key buildings higher or behind a levee", b.id, [b.x, b.y, b.z])


def _distance_from(world, seeds, limit) -> dict:
    """Walk distance over the surface from seed tiles (4-neighbour), up to `limit`."""
    dist = {s: 0 for s in seeds}
    queue = deque(seeds)
    while queue:
        x, y = queue.popleft()
        d = dist[(x, y)]
        if d >= limit:
            continue
        for dx, dy in hydro.N4:
            n = (x + dx, y + dy)
            if n not in dist and world.in_map(*n):
                dist[n] = d + 1
                queue.append(n)
    return dist


@monitor("water.fields", rules=["fields-near-held-water", "irrigation-pond", "plant-use-safe-plant",
                                "forester-area-vs-field"])
def fields(world, ctx):
    """Crops on land a drought dries, dry farmland a pond would wet, and tree marks inside fields."""
    h = _h(world)
    if not h or world.planting is None:
        return
    crops = {t: (z, p) for t, (z, p) in world.planting.items() if p in CROPS}
    held = h.held_tiles()
    if crops and held:
        near = _distance_from(world, list(held), hydro.MOIST_REACH)
        exposed = [t for t, (z, _) in crops.items() if t not in near]
        if len(exposed) > 0.3 * len(crops):
            xs, ys = [t[0] for t in exposed], [t[1] for t in exposed]
            yield Finding("water.fields", "warn", f"{len(exposed)} of {len(crops)} crop plots are more than "
                          f"{hydro.MOIST_REACH} tiles from dam-held water (x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)}): "
                          "they dry out in a drought longer than ~3 days; hold the water by them or add a pond",
                          "exposed", [exposed[0][0], exposed[0][1], crops[exposed[0]][0]], {"plots": len(exposed)})
    elif crops and not held:
        yield Finding("water.fields", "warn", f"none of the {len(crops)} crop plots has dam-held water: they die in a "
                      "drought longer than ~3 days", "exposed")
    for d in h.dry_farmland()[:3]:
        px, py, pz = d["pond"]
        yield Finding("water.fields", "info", d["why"], f"pond-{px}-{py}", [px, py, pz], {"tiles": d["tiles"]})
    dry = [(t, z, p) for t, (z, p) in world.planting.items() if world.in_map(*t) and world.moist[t[1], t[0]] == " "]
    if len(dry) >= 5:
        (x, y), z, p = dry[0]
        yield Finding("water.fields", "warn", f"{len(dry)} planting marks on dry soil (first {p} at {x},{y}): plant only "
                      "with h.safe_plant, which skips dry, wet and unreachable tiles", "dry-marks", [x, y, z],
                      fix=f'clear_planting(x0={x}, y0={y}, x1={x}, y1={y}, z={z})  then h.safe_plant("{p}", ...)')
    inside = []
    for t, (z, p) in world.planting.items():
        if p in TREES and sum((t[0] + dx, t[1] + dy) in crops for dx, dy in hydro.N4) >= 2:
            inside.append((t, z))
    if inside:
        (x, y), z = inside[0]
        yield Finding("water.fields", "warn", f"{len(inside)} tree marks inside crop fields (first {x},{y}): the "
                      "Forester will replant saplings there", "trees-in-field", [x, y, z],
                      fix=f"clear_planting(x0={x}, y0={y}, x1={x}, y1={y}, z={z})")


@monitor("water.reservoir", rules=["reservoir-upstream"])
def reservoir(world, ctx):
    """From cycle 3: a reservoir above the base for gravity-fed water."""
    h = _h(world)
    if not h or not world.dc:
        return
    cycle, _ = _cycle(world)
    if cycle < 3:
        return
    if any(p["full"] and p["region"] and p["level"] >= world.dc.z + 1 for p in h.pools()):
        return
    up = sorted((p for p in h.dams()["proposals"] if p["level"] >= world.dc.z + 1),
                key=lambda p: (p["builderReach"] is False, -p["score"]))
    bowls = [r for r in h.reservoirs() if (r["aboveBase"] or 0) >= 1 and not r["flooded"]]
    best = up[0] if up else None
    msg = "no reservoir holds water above the base"
    if best:
        msg += f"; best: {best['why']}"
    elif bowls:
        msg += f"; best: {bowls[0]['why']}"
    yield Finding("water.reservoir", "info", msg, "upstream",
                  [best["line"][0][0], best["line"][0][1], int(best["level"])] if best else None,
                  fix="; ".join(best["calls"]) if best else "")


@monitor("water.badwater", rules=["water-goals-each-cycle"])
def badwater(world, ctx):
    """Badwater mixing into clean water near the base, crops in its soil reach, and the cycle water review."""
    h = _h(world)
    if not h:
        return
    bad = h.badwater()
    dc = world.dc
    for m in bad["mixing"]:
        x0, y0, x1, y1 = m["bbox"]
        close = dc and x0 - 25 <= dc.x <= x1 + 25 and y0 - 25 <= dc.y <= y1 + 25
        yield Finding("water.badwater", "warn" if close else "info", f"W{m['body']} ({m['tiles']} tiles, "
                      f"x{x0}-{x1} y{y0}-{y1}) mixes clean and badwater ({', '.join(m['fedBy'])}): pump only from its clean tiles, "
                      "away from the badwater inflow, and stop those pumps in a badtide",
                      f"mix-{m['body']}", [x0, y0, 0])
    if bad["cropsAtRisk"]:
        (x, y) = bad["cropsAtRisk"][0]
        line = bad["barrierLine"]
        yield Finding("water.badwater", "warn", f"{len(bad['cropsAtRisk'])} crop plots within the soil-contamination "
                      f"reach of badwater (first {x},{y}): put {bad['barrierTemplate']} along the bad bank "
                      f"({len(line)} tiles)", "crops", [x, y, int(h.top[y, x])], {"bank": line[:20]})
    for d in bad["diversions"][:2]:
        yield Finding("water.badwater", "info", f"diversion for {d['blocks']}: {d['why']}", f"divert-{d['line'][0]}",
                      [d["line"][0][0], d["line"][0][1], int(d["level"])], fix="; ".join(d["calls"]))
    for s in bad["sources"]:
        if s.get("activates"):
            a = s["activates"]
            yield Finding("water.badwater", "warn", f"{s['name']} at {s['bbox'][:2]} z{s['z']} switches on in "
                          f"{a['cycles']} cycles + {a['days']} days: levee its outlet before then", f"timer-{s['bbox'][:2]}",
                          [s["bbox"][0], s["bbox"][1], s["z"]])
    cycle, day = _cycle(world)
    if day <= 2:
        best = h.dams()["proposals"][:1]
        yield Finding("water.badwater", "info", f"cycle {cycle} water review: {h.held_volume()} units held behind "
                      f"{sum(1 for p in h.pools() if p['full'] and p['region'])} dam lines; "
                      f"{len(bad['mixing'])} mixed bodies, {len(bad['cropsAtRisk'])} crop plots at badwater risk"
                      + (f"; next dam: {best[0]['why']}" if best else ""), f"review-{cycle}")
