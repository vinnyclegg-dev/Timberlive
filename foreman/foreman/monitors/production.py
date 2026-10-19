"""Production, flooding, build range, road single links and stuck sites with their reason (plan section 4.2).

Uses the bridge's ForemanModule views (production, sites, range); each check skips when its view is missing.
"""

from __future__ import annotations

import networkx as nx

from ..findings import Finding, monitor
from . import FOOD, bid

# Buildings meant to stand in or over water (no flood check). Source: knowledge/09-buildings.md.
WATER_BUILDINGS = ("Pump", "WaterWheel", "Dam", "Levee", "Floodgate", "Sluice", "Platform", "PowerShaft", "Valve",
                   "IrrigationBarrier", "ImpermeableFloor", "Stairs", "Path", "Bridge", "Weir", "Overhang",
                   "WaterSource", "Gauge", "Sensor", "Barrier", "Shaft")
# Stores and food/water jobs matter most when a road is cut.
KEY_DOORS = ("Warehouse", "Pile", "Tank", "FarmHouse", "Pump", "FoodFactory", "Fermenter", "Grill", "Bakery",
             "HydroponicGarden", "BreedingPod", "Barrack", "Lodge", "Rowhouse", "DistrictCenter")
STALL_POLLS = 6     # medium polls (~30 s each) with no progress before "not producing" (3 real minutes)


@monitor("bld.producing", rules=["full-output-stalls", "empty-input-starves", "tune-workers"])
def producing(world, ctx):
    """Manufactories whose batch progress has not moved for several polls, with the reason."""
    if not world.production or (world.colony["time"].get("speed") or 0) == 0:
        return
    last = ctx.store.get("production_last", {})
    now = {}
    for pid, p in world.production.items():
        b = world.by_id.get(pid)
        if not b or b.raw.get("paused"):
            continue
        prev = last.get(pid) or {"progress": -1, "still": 0}
        still = prev["still"] + 1 if abs(p["progress"] - prev["progress"]) < 1e-4 else 0
        now[pid] = {"progress": p["progress"], "still": still}
        if still < STALL_POLLS:
            continue
        w = b.raw.get("workers") or {}
        net = world.network_of.get(pid)
        if not p.get("recipe"):
            why, fix = "no recipe", f'building_action(building_id={bid(b)}, component="Manufactory", action="SetRecipe", args=["<recipe>"])'
        elif w and not w.get("assigned"):
            why, fix = "no workers", f'set_priority(building_id={bid(b)}, priority="High")'
        elif not p["ingredients"]:
            why, fix = f"no inputs (has {p.get('stock') or {}})", "bring or make the inputs"
        elif not p["outputSpace"]:
            why, fix = "output full", "add storage for its product or use it"
        elif net and net["supply"] < net["demand"]:
            why, fix = f"power short ({net['supply']}/{net['demand']} hp)", "add generators on its network"
        elif not p.get("fuel", True):
            why, fix = "no fuel", "deliver fuel"
        else:
            why, fix = "idle (outside work hours, or workers busy elsewhere)", ""
        food = p.get("recipe") in FOOD or p.get("recipe") == "Water"
        yield Finding("bld.producing", "warn" if food else "info", f"{b.label} {p.get('recipe')}: no progress "
                      f"for {still} polls: {why}", b.id, [b.x, b.y, b.z], fix=fix)
    ctx.store.set("production_last", now)


@monitor("food.processing", rules=["food-edible-only", "food-drought-proof-chain"])
def food_processing(world, ctx):
    """Raw crops waiting with no running processor (Corn needs a Food Factory, Cassava a Fermenter)."""
    chains = {"Corn": ("FoodFactory", "CornRation"), "Cassava": ("Fermenter", "FermentedCassava"),
              "Soybean": ("Fermenter", "FermentedSoybean"), "Eggplant": ("FoodFactory", "EggplantRation")}
    for raw, (maker, product) in chains.items():
        have = world.good(raw)["available"]
        if have < 50:
            continue
        makers = [b for b in world.finished(maker) if not b.raw.get("paused")]
        running = [b for b in makers if (world.production.get(b.id) or {}).get("ready")]
        if not makers:
            yield Finding("food.processing", "warn", f"{have} {raw} stored but no {maker} running: it is not food "
                          f"until processed into {product}", raw)
        elif world.production and not running:
            yield Finding("food.processing", "warn", f"{have} {raw} waiting; no {maker} is ready to produce "
                          f"({[b.label for b in makers]}): check workers, power and inputs", raw)


@monitor("bld.flooded", rules=["building-footprint-dry"])
def flooded(world, ctx):
    """Buildings standing in water (water surface above their base), apart from water buildings."""
    if not world.has_map:
        return
    for b in world.finished():
        if any(k in b.name for k in WATER_BUILDINGS):
            continue
        if not world.in_map(b.x, b.y):
            continue
        top, depth = int(world.top[b.y, b.x]), float(world.depth[b.y, b.x])
        if depth > 0 and top + depth > b.z:
            yield Finding("bld.flooded", "warn", f"{b.label} stands in {top + depth - b.z:.1f} of water: it stops "
                          "working while flooded; move it or wall the water out", b.id, [b.x, b.y, b.z])


@monitor("bld.build_range", rules=["district-range"])
def build_range(world, ctx):
    """Construction sites whose door is outside the district range (builders never reach them)."""
    if world.range_tiles is None:
        return
    out = [b for b in world.buildings if not b.finished and b.door and world.in_range(*b.door) is False
           and b.name != "Path"]
    if out:
        yield Finding("bld.build_range", "warn", f"{len(out)} sites outside the district range: "
                      f"{[b.label for b in out[:6]]}: extend a road toward them or demolish", "range",
                      evidence={"ids": [b.id for b in out]})


@monitor("road.only_link", rules=["path-keep-doors", "corridors-before-planting"])
def only_link(world, ctx):
    """Road tiles whose loss would cut key buildings (stores, food, water, homes) off the district."""
    if not world.dc or not world.only_links:
        return
    doors = {}
    for b in world.finished():
        if b.door and b.name.endswith(KEY_DOORS) and b.name != "DistrictCenter":
            x, y, z = b.door
            node = next(((x, y, z + dz) for dz in (0, -1, 1) if (x, y, z + dz) in world.road_component), None)
            if node:
                doors.setdefault(node, []).append(b)
    if not doors:
        return
    sub = world.road.subgraph(world.road_component).copy()
    risky = []
    for ap in world.only_links:
        if ap == world.dc.door:
            continue
        nbrs = list(sub.neighbors(ap))
        sub.remove_node(ap)
        reach = nx.node_connected_component(sub, world.dc.door) if world.dc.door in sub else set()
        cut = [b for node, bs in doors.items() if node != ap and node not in reach for b in bs]
        cut += doors.get(ap, [])
        sub.add_node(ap)
        sub.add_edges_from((ap, n) for n in nbrs)
        if len(cut) >= 3:
            risky.append((len(cut), ap, cut))
    risky.sort(key=lambda r: -r[0])
    shown = []
    for n, ap, cut in risky:
        # A chain of single-link tiles cuts the same buildings: report one tile per chain.
        if any(abs(ap[0] - s[0]) + abs(ap[1] - s[1]) <= 3 for s in shown):
            continue
        shown.append(ap)
        if len(shown) > 3:
            break
        yield Finding("road.only_link", "info", f"road tile {ap} is the only link for {n} key buildings "
                      f"({[b.label for b in cut[:4]]}{' ...' if n > 4 else ''}): never build on it; add a second "
                      "road link", f"{ap[0]},{ap[1]},{ap[2]}", list(ap),
                      evidence={"cut": [b.id for b in cut]})


@monitor("sites.reason", rules=["sites-progress"])
def site_reasons(world, ctx):
    """Construction sites waiting on materials (goods missing and none in stock)."""
    if not world.sites:
        return
    short = {}
    for sid, s in world.sites.items():
        b = world.by_id.get(sid)
        if not b or s.get("hasMaterials") or not s.get("missing"):
            continue
        for good, n in s["missing"].items():
            if world.good(good)["available"] < n:
                short.setdefault(good, []).append(b)
    for good, bs in short.items():
        yield Finding("sites.reason", "warn", f"{len(bs)} sites need {good} but stock is {world.good(good)['available']}: "
                      f"{[b.label for b in bs[:5]]}", f"materials-{good}")
