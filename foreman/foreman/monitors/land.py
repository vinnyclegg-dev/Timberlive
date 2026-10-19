"""Land and wood: plantable land left empty, marks on bad tiles, crop plots per farmhouse, trees and logs,
dead trees (plan section 4.3).

Uses the map grids, the bridge's planting/cutting marks and district range, and the plant growth blocks.
"""

from __future__ import annotations

import numpy as np

from ..findings import Finding, monitor

# Field crops (FarmHouse) vs trees and bushes (Forester). Source: knowledge/09-buildings.md, /api/plantables.
CROPS = ("Corn", "Kohlrabi", "Canola", "Cassava", "Soybean", "Eggplant", "Potato", "Carrot", "Wheat", "Sunflower",
         "Spadderdock", "Cattail")
TREES = ("Oak", "Pine", "Birch", "Maple", "Chestnut", "Mangrove")
WORK_RANGE = 20       # knowledge/09 "Work ranges": planters work within ~20 tiles of walking distance
PLOTS_PER_HOUSE = 55  # rule farm-plots-per-house (operator rule maximise-planting)
MIN_CLUSTER = 6       # smallest empty moist patch worth a plant_area call
LOG_FLOOR = 50        # rule wood-log-floor
TREE_FLOOR = 15       # trees left in the cutting area before the next stand must open
PLANTERS = ("FarmHouse", "Forester")


def planter_for(plant: str) -> str:
    return "FarmHouse" if plant in CROPS else "Forester"


def ledge(world, x: int, y: int) -> bool:
    """Tile 2+ higher than every neighbour on the map (rule plant-no-high-ledge)."""
    z = world.top[y, x]
    nb = [world.top[j, i] for i, j in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if world.in_map(i, j)]
    return bool(nb) and all(z - n >= 2 for n in nb)


def near_planter(world, x: int, y: int, names: tuple[str, ...]) -> bool:
    """A finished planter's door within WORK_RANGE tiles (Manhattan; the game measures walking distance)."""
    for b in world.finished(*names):
        if b.door and abs(b.door[0] - x) + abs(b.door[1] - y) <= WORK_RANGE:
            return True
    return False


def empty_moist(world) -> np.ndarray:
    """Moist, clean, empty, unmarked tiles at the surface that a FarmHouse or Forester works, not on a road."""
    if not world.has_map or world.planting is None or world.reach_union is None:
        return np.zeros((0, 0), bool)
    ok = world.moist == "#"
    objects = np.array([[c not in " ." for c in row] for row in world.objects], bool)
    ok &= ~objects
    for (x, y) in list(world.planting) + list(world.cutting or {}):
        ok[y, x] = False
    for (x, y, _z) in world.road.nodes:
        ok[y, x] = False
    for b in world.buildings:    # paths and some buildings are not the bottom object in the map
        if 0 <= b.y < world.h and 0 <= b.x < world.w:
            ok[b.y, b.x] = False
    ys, xs = np.nonzero(ok)
    for y, x in zip(ys, xs):
        if not world.reaches(PLANTERS, int(x), int(y), int(world.top[y, x])) or ledge(world, x, y):
            ok[y, x] = False
    return ok


def clusters(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """4-connected patches as (size, x0, y0, x1, y1), biggest first."""
    seen = np.zeros_like(mask)
    out = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack, tiles = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            tiles.append((x, y))
            for j, i in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= j < mask.shape[0] and 0 <= i < mask.shape[1] and mask[j, i] and not seen[j, i]:
                    seen[j, i] = True
                    stack.append((j, i))
        xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
        out.append((len(tiles), min(xs), min(ys), max(xs), max(ys)))
    return sorted(out, reverse=True)


@monitor("land.plantable", rules=["plant-every-moist-tile", "replant-cleared-land", "moist-land-shortage"])
def plantable(world, ctx):
    """Moist, clean, reachable tiles with nothing on them and no planting mark: plant them."""
    mask = empty_moist(world)
    if not mask.size:
        return
    patches = [c for c in clusters(mask) if c[0] >= MIN_CLUSTER]
    if not patches:
        return
    total = sum(c[0] for c in patches)
    for n, x0, y0, x1, y1 in patches[:4]:
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        z = int(world.top[cy, cx])
        crop = world.reaches(("FarmHouse",), cx, cy, z) or near_planter(world, cx, cy, ("FarmHouse",))
        tree = world.reaches(("Forester",), cx, cy, z) or near_planter(world, cx, cy, ("Forester",))
        planter = "FarmHouse" if crop else "Forester" if tree else None
        house = next((b for b in world.finished(planter) if b.door
                      and abs(b.door[0] - cx) + abs(b.door[1] - cy) <= WORK_RANGE), None) if planter else None
        what = '"Corn"' if crop else '"Oak"'
        fix = (f"h.safe_plant({what}, {x0}, {y0}, {x1}, {y1}, {list(house.door)})" if house else
               "build a FarmHouse (crops) or Forester (trees) within ~20 tiles first")
        yield Finding("land.plantable", "info", f"{n} empty moist tiles in x{x0}-{x1} y{y0}-{y1} "
                      f"({'near ' + house.label if house else 'no planter in range'}); {total} in all",
                      f"{x0},{y0}", [cx, cy, int(world.top[cy, cx])], fix=fix,
                      evidence={"tiles": n, "total": total})


@monitor("land.plants_wrong", rules=["plant-no-water-tiles", "plant-no-contaminated-soil", "plant-no-high-ledge",
                                     "plant-reachable-only", "plant-check-marked"])
def plants_wrong(world, ctx):
    """Planting marks on water, contaminated soil, dry soil, a high ledge or outside the district range."""
    if not world.has_map or not world.planting:
        return
    bad: dict[str, list] = {}
    for (x, y), (z, plant) in world.planting.items():
        if not world.in_map(x, y) or z != world.top[y, x]:
            continue            # an upper level (platform, overhang): the surface grid can't judge it
        m = world.moist[y, x]
        why = ("on water" if m == "w" else "on contaminated soil" if m == "x" else "on dry soil" if m == " " else
               "on a high ledge" if ledge(world, x, y) else
               f"with no {planter_for(plant)} in range" if world.reaches((planter_for(plant),), x, y, z) is False
               else None)
        if why:
            bad.setdefault(why, []).append((x, y, plant))
    for why, tiles in bad.items():
        sev = "info" if why == "on dry soil" else "warn"
        xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
        plants = sorted({t[2] for t in tiles})
        yield Finding("land.plants_wrong", sev, f"{len(tiles)} {'/'.join(plants)} marks {why} "
                      f"(x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)}): nothing grows there",
                      why.replace(" ", "-"), [tiles[0][0], tiles[0][1], int(world.top[tiles[0][1], tiles[0][0]])],
                      fix="; ".join(f"clear_planting({x}, {y}, {x}, {y})" for x, y, _ in tiles[:6])
                      + (" ..." if len(tiles) > 6 else ""), evidence={"tiles": tiles[:200]})


@monitor("food.pipeline", rules=["farm-plots-per-house", "plant-every-moist-tile"])
def pipeline(world, ctx):
    """Crop plots each FarmHouse works (~55 each), from the game's work ranges."""
    if not world.reach or world.planting is None:
        return
    houses = [b for b in world.finished("FarmHouse") if b.id in world.reach]
    crops = sum(1 for _z, p in world.planting.values() if p in CROPS)
    if houses and crops / len(houses) > PLOTS_PER_HOUSE * 1.3:
        yield Finding("food.pipeline", "info", f"{crops} crop plots for {len(houses)} farmhouses "
                      f"(~{crops / len(houses):.0f} each, rule ~{PLOTS_PER_HOUSE}): add a FarmHouse by the biggest field "
                      "or staff them fully", "farm-load")
    for b in houses:
        n = sum(v for k, v in (world.reach[b.id].get("plots") or {}).items() if k in CROPS)
        if n < 10:
            yield Finding("food.pipeline", "info", f"{b.label} reaches only {n} crop plots: plant moist land in its "
                          "range or move it", b.id, [b.x, b.y, b.z])


@monitor("wood.trees", rules=["wood-cutting-area-trees", "wood-log-floor", "wood-forester-oak",
                              "wood-building-caps", "wood-grown-trees-check"])
def trees(world, ctx):
    """Trees left in the cutting area, logs vs the floor, lumberjacks per tree, Oak in the forester marks."""
    logs = world.good("Log")["available"]
    jacks = [b for b in world.finished("LumberjackFlag") if not b.raw.get("paused")]
    if logs < LOG_FLOOR:
        yield Finding("wood.trees", "warn", f"Log {logs} < {LOG_FLOOR}: wood jobs to High, hold log-hungry builds",
                      "Log", fix='set_priority(building_id="<LumberjackFlag id>", priority="High")')
    if world.cutting is not None:
        with_tree = [(x, y) for (x, y), (_z, t) in world.cutting.items() if t]
        if len(with_tree) < TREE_FLOOR and jacks:
            yield Finding("wood.trees", "warn", f"only {len(with_tree)} trees left in the cutting area for "
                          f"{len(jacks)} lumberjacks: mark the next grown stand", "cutting",
                          fix="mark_tree_cutting(x0, y0, x1, y1)  # a stand of grown trees near a lumberjack")
        if world.reach:
            idle = [b for b in jacks if (world.reach.get(b.id) or {}).get("hasYielders") is False]
        else:
            idle = [b for b in jacks if b.door and not any(abs(b.door[0] - x) + abs(b.door[1] - y) <= WORK_RANGE
                                                           for x, y in with_tree)]
        if idle:
            yield Finding("wood.trees", "info", f"{len(idle)} lumberjacks have no marked grown tree in range: "
                          f"{[b.label for b in idle[:5]]}: mark trees near them or move the flags", "idle-jacks")
    gath = [b for b in world.finished("GathererFlag") if not b.raw.get("paused")
            and (world.reach.get(b.id) or {}).get("hasYielders") is False]
    if gath:
        yield Finding("wood.trees", "info", f"{len(gath)} gatherers have nothing ripe in range: "
                      f"{[b.label for b in gath[:5]]}", "idle-gatherers")
    if world.planting is not None and world.finished("Forester"):
        marks = [p for _z, p in world.planting.values() if p in TREES]
        if marks and "Oak" not in marks:
            yield Finding("wood.trees", "info", f"{len(marks)} tree marks and none are Oak (most wood per tile)",
                          "oak", fix='plant_area("Oak", x0, y0, x1, y1)  # via h.safe_plant')


@monitor("land.dead_trees", rules=["replant-cleared-land", "demolish-resources-care"])
def dead_trees(world, ctx):
    """Dead trees and bushes blocking land inside the district range (clear, then replant)."""
    if not world.plant_blocks:
        return
    rows = []
    for blk in world.plant_blocks:
        dead = sum(v.get("dead", 0) for k, v in (blk.get("plants") or {}).items() if k in TREES or "Bush" in k)
        dying = sum(v.get("dying", 0) for v in (blk.get("plants") or {}).values())
        if world.range_tiles is not None and not any(
                blk["x"] <= x < blk["x"] + blk["w"] and blk["y"] <= y < blk["y"] + blk["h"]
                for x, y, _z in world.range_tiles):
            continue
        if dead or dying:
            rows.append((dead, dying, blk))
    rows.sort(key=lambda r: -r[0])
    total = sum(r[0] for r in rows)
    if total >= 20:
        top = ", ".join(f"x{b['x']}-{b['x'] + b['w'] - 1} y{b['y']}-{b['y'] + b['h'] - 1}: {d}" for d, _, b in rows[:3])
        yield Finding("land.dead_trees", "info", f"{total} dead trees/bushes in reach ({top}): clear the ones on "
                      "moist land and replant", "dead",
                      fix="demolish_resources(x0, y0, x1, y1)  # then h.safe_plant on the cleared moist tiles")
    dying = sum(r[1] for r in rows)
    if dying:
        yield Finding("land.dying", "warn", f"{dying} plants dying in reach (dry or flooded): water them or "
                      "harvest early", "dying", evidence={"blocks": [(b["x"], b["y"], dy) for _, dy, b in rows if dy]})
