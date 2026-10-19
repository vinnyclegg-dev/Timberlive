"""Plan-kind rules from live state (plan section 5.4): the opening order, wood, science order, food spread, crops,
spare hands and buffer stores. Sources: knowledge/07-game-plan-v4.md stages 1-4, knowledge/08 lessons.

Each check only fires while its rule is still live (cycle 1 for the opening ones) so a mid-game colony that met
them once is not nagged forever.
"""

from __future__ import annotations

from ..findings import Finding, monitor
from ..geometry import TREES

HAZARD = ("Stairs", "Levee", "Discharge", "GearWorkshop", "HydroponicGarden", "FoodFactory", "SteamEngine")
WORKSHOPS = ("IndustrialLumberMill", "LumberMill", "GearWorkshop", "Smelter", "Metalsmith", "FoodFactory", "OilPress",
             "WoodWorkshop", "Fermenter", "Grill", "Bakery", "Centrifuge", "ExplosivesFactory")
STORES = ("Warehouse", "IndustrialPile", "Tank")


def _day(world) -> tuple[int, int]:
    t = world.colony.get("time") or {}
    return int(t.get("cycle", 1)), int(t.get("cycleDay", 1))


def _count(world, name: str, finished: bool = False) -> int:
    return sum(1 for b in world.buildings if b.name == name and (b.finished or not finished))


def _bp(world, name: str) -> dict | None:
    return next((bp for bp in world.blueprints or [] if bp["template"].split(".")[0] == name), None)


def _unlock_fix(world, name: str) -> str:
    bp = _bp(world, name)
    if bp and not bp.get("unlocked") and bp.get("science", 0) <= world.colony.get("science", 0):
        return f'unlock_building(template="{bp["template"]}")'
    return ""


@monitor("plan.opening", rules=["pods-by-day-5", "opening-pumps-tanks", "opening-farmhouse-first",
                                "opening-extra-jobs-last", "opening-scout", "opening-batch-one-run"])
def opening(world, ctx):
    """Cycle 1: pumps + tanks first, FarmHouse and crops by day 2, 3 pods by day 5, the Inventor after the pumps."""
    cycle, day = _day(world)
    if cycle != 1:
        return
    from .. import masterplan
    if day <= 2 and not masterplan.PLAN_FILE.exists():
        yield Finding("plan.opening", "info", "no masterplan yet: scout and work out the whole opening batch in one "
                      "run before placing anything", "masterplan", fix="python -m foreman plan  (or GET /api/masterplan)")
    pumps, tanks = _count(world, "DeepWaterPump"), _count(world, "SmallTank") + _count(world, "MediumTank")
    if day >= 2 and (pumps < 2 or tanks < 2):
        yield Finding("plan.opening", "warn", f"day {day}: {pumps} pump(s) and {tanks} tank(s); the opening needs 2-3 "
                      "of each (start water is 0)", "pumps", evidence={"pumps": pumps, "tanks": tanks},
                      fix="python -m foreman plan  (open-water steps)")
    farms = [b for b in world.buildings if b.name == "FarmHouse"]
    if day >= 2 and not farms:
        yield Finding("plan.opening", "warn", f"day {day}: no FarmHouse; 130 start berries last about 3 days, so crops "
                      "go in on day 1-2", "farmhouse", fix="python -m foreman plan  (open-farm-1)")
    elif farms and world.planting is not None and day >= 2:
        for f in farms:
            if f.finished and not any(max(abs(x - f.x), abs(y - f.y)) <= 20 for (x, y) in world.planting):
                yield Finding("plan.opening", "warn", f"{f.label} has no planting marks in range", f.id,
                              [f.x, f.y, f.z], fix=f"h.safe_plant(\"Kohlrabi\", {f.x - 18}, {f.y - 18}, {f.x + 18}, "
                                                   f"{f.y + 18}, {tuple(f.door) if f.door else (f.x, f.y, f.z)})")
    pods = _count(world, "BreedingPod")
    if day >= 5 and pods < 3:
        yield Finding("plan.opening", "critical", f"day {day}: {pods} Breeding Pod(s); 3 by day 5 keep births ahead of "
                      "the founders' deaths", "pods", evidence={"pods": pods},
                      fix="python -m foreman plan  (open-pods; 10 logs each)")
    working = [b for b in world.finished("DeepWaterPump")]
    inv = [b for b in world.buildings if b.name == "Inventor" and not b.raw.get("paused")]
    if inv and not working:
        yield Finding("plan.opening", "warn", "the Inventor takes a worker before any pump runs: extra jobs come last",
                      inv[0].id, [inv[0].x, inv[0].y, inv[0].z],
                      fix=f'set_paused(building_id="{inv[0].id}", paused=true)')


@monitor("plan.wood", rules=["wood-forester-early", "wood-whole-stand-day1"])
def wood(world, ctx):
    """A Forester by cycle 1 day 8, and the whole grown stand marked in the first days."""
    cycle, day = _day(world)
    if _count(world, "Forester") == 0 and (cycle > 1 or day >= 8):
        fix = _unlock_fix(world, "Forester") or "python -m foreman plan  (s2-forester)"
        yield Finding("plan.wood", "warn", "no Forester yet: lumberjacks will strip the only stand", "forester", fix=fix)
    if cycle == 1 and day <= 4 and world.cutting is not None and world.has_map:
        flags = [b for b in world.buildings if b.name == "LumberjackFlag"]
        loose = []
        for f in flags:
            for y in range(max(0, f.y - 20), min(world.h, f.y + 21)):
                for x in range(max(0, f.x - 20), min(world.w, f.x + 21)):
                    o = world.object_at(x, y)
                    if o and o.split(".")[0] in TREES and (x, y) not in world.cutting:
                        loose.append((x, y))
        if len(set(loose)) >= 10:
            xs, ys = [t[0] for t in loose], [t[1] for t in loose]
            yield Finding("plan.wood", "info", f"{len(set(loose))} trees in lumberjack range are not marked for "
                          "cutting: mark the whole stand on day 1", "cutting",
                          fix=f"mark_tree_cutting(x0={min(xs)}, y0={min(ys)}, x1={max(xs)}, y1={max(ys)})")


@monitor("plan.science", rules=["science-hazard-first"])
def science(world, ctx):
    """Hazard-proofing unlocks (Stairs, Levee, Discharge, Gear Workshop, Hydroponics, Food Factory, Steam Engine)
    come before anything else science can buy."""
    sci = world.colony.get("science", 0)
    afford = [bp for name in HAZARD for bp in [_bp(world, name)]
              if bp and not bp.get("unlocked") and bp.get("science", 0) <= sci]
    if afford:
        bp = min(afford, key=lambda b: b["science"])
        yield Finding("plan.science", "warn", f"science {sci} buys hazard-proofing still locked: "
                      f"{[(b['name'], b['science']) for b in afford]}", "science",
                      evidence={"afford": [b["template"] for b in afford]},
                      fix=f'unlock_building(template="{bp["template"]}")')


@monitor("plan.food", rules=["food-spread-failure-modes", "corn-chain-early", "kohlrabi-phase-out"])
def food(world, ctx):
    """Food spread over field, pond/reservoir and indoor modes by cycle 4; corn only with its Food Factory; kohlrabi
    phased out once rations flow."""
    cycle, _ = _day(world)
    plant = world.planting or {}
    crops: dict = {}
    for _, (_, p) in plant.items():
        crops[p] = crops.get(p, 0) + 1
    modes = {"fields": bool(_count(world, "FarmHouse") and plant),
             "ponds/reservoir": bool(_count(world, "Levee") or _count(world, "Discharge")),
             "indoor": bool(_count(world, "HydroponicGarden"))}
    if cycle >= 4 and sum(modes.values()) < 2:
        missing = [k for k, v in modes.items() if not v]
        yield Finding("plan.food", "warn", f"cycle {cycle}: food rests on {[k for k, v in modes.items() if v]}; "
                      f"add {missing} before the next hazard", "food-modes", evidence=modes,
                      fix=_unlock_fix(world, "HydroponicGarden") or _unlock_fix(world, "Levee") or
                      "python -m foreman plan")
    if crops.get("Corn") and not _count(world, "FoodFactory"):
        yield Finding("plan.food", "warn", f"{crops['Corn']} corn plots but no Food Factory: raw corn is not food",
                      "corn", fix=_unlock_fix(world, "FoodFactory") or "python -m foreman plan  (s4-foodfactory)")
    rations = world.good("CornRation").get("available", 0)
    if rations > 0 and _count(world, "FoodFactory", finished=True) and crops.get("Kohlrabi", 0) > crops.get("Corn", 0):
        yield Finding("plan.food", "info", f"rations flow but kohlrabi still has {crops['Kohlrabi']} plots vs corn "
                      f"{crops.get('Corn', 0)}: switch one field block at a time to Corn while food days hold",
                      "kohlrabi", fix="clear_planting(x0, y0, x1, y1) on one kohlrabi block, then "
                                      "h.safe_plant(\"Corn\", x0, y0, x1, y1, farmhouse_door)")


@monitor("plan.jobs", rules=["spare-hands-low-priority", "storage-buffer-obtain"])
def jobs(world, ctx):
    """Spare beavers go to builders and haulers on low priority; each workshop gets a buffer store by its door."""
    idle = world.colony.get("population", {}).get("unemployed", 0)
    if idle >= 3:
        yield Finding("plan.jobs", "info", f"{idle} unemployed: add a Builders' Hut or Hauling Post on the lowest "
                      "priority so food factories never wait for haulers", "spare-hands",
                      fix="python -m foreman plan  (or GET /api/where?template=HaulingPost)")
    stores = [b for b in world.buildings if any(k in b.name for k in STORES)]
    for b in world.finished(*WORKSHOPS):
        d = b.door
        if not d:
            continue
        if not any(max(abs(s.x - d[0]), abs(s.y - d[1])) <= 3 for s in stores):
            yield Finding("plan.jobs", "info", f"{b.label} has no buffer store within 3 tiles of its door", b.id,
                          [b.x, b.y, b.z], fix=f"GET /api/where?template=SmallWarehouse&x={d[0]}&y={d[1]}&radius=4")
