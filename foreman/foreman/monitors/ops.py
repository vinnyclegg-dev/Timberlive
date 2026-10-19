"""Daily operations discipline (plan section 5, job management): crisis mode, hoarding, growth gate, priority
tiers, work hours, power shortage order, steam engine feed, pre-hazard stock and checklist, game speed.

Every check reads only what the bridge already reports; each finding names the harness call that fixes it.
"""

from __future__ import annotations

import time

from ..findings import Finding, monitor
from . import EAT_PER_BEAVER, FOOD_JOBS, POWER_USE, bid
from .forecast import rates
from .population import pods_needed
from .supply import food_days, food_stock, reserves

CRISIS_DAYS = 1.5
HOARD_FACTOR = 2.0                  # food-hoard: aim for 2x the hazard need
WORKDAY_HOURS = 16
WOOD_BEFORE_DROUGHT = 60            # logs + planks (wood-pre-drought-stock)
CHECKLIST_DAYS = 3
# Leaf buildings to pause first when power is short, least needed first (rule power-shortage-order).
SHED_ORDER = ("TeethGrindstone", "Numbercruncher", "CoffeeBrewery", "GearWorkshop", "WoodWorkshop", "OilPress",
              "Smelter", "Metalsmith", "IndustrialLumberMill", "Centrifuge", "Fermenter", "FoodFactory")
# Never paused in a food crisis: food, water, power, homes, storage, science that is being spent.
CRISIS_KEEP = FOOD_JOBS + ("DistrictCenter", "BreedingPod", "Barrack", "Lodge", "Rowhouse", "WaterWheel",
                           "PowerWheel", "SteamEngine", "PowerShaft", "Tank", "Warehouse", "Pile", "HaulingPost",
                           "BuildersHut", "MedicalBed", "Campfire", "Path", "Stairs", "Platform", "Dam", "Levee",
                           "Floodgate", "Sluice")
GATHERER_PLANTS = ("BlueberryBush", "Bush")


def live(world) -> bool:
    return (world.colony["time"].get("speed") or 0) > 0


def workers(b) -> int:
    return (b.raw.get("workers") or {}).get("max", 0)


@monitor("ops.crisis", rules=["food-crisis-mode"])
def crisis(world, ctx):
    """Below 1.5 food days: only food, water and power jobs run; pause the rest so their workers move."""
    d = food_days(world)
    if d >= CRISIS_DAYS or not world.beavers:
        return
    others = [b for b in world.finished() if workers(b) and not b.raw.get("paused")
              and not any(k in b.name for k in CRISIS_KEEP)]
    others.sort(key=lambda b: -workers(b))
    yield Finding("ops.crisis", "critical", f"food crisis: {d:.1f} food days; pause {len(others)} non-food jobs "
                  f"({sum(workers(b) for b in others)} workers) so they farm, gather and process food", "crisis",
                  fix="; ".join(f'set_paused(building_id={bid(b)}, paused=True)' for b in others[:6]),
                  evidence={"pause": [b.id for b in others]})


@monitor("ops.hoard", rules=["food-hoard"])
def hoard(world, ctx):
    """Food above the 1.5x reserve but below 2x: keep farming hard; the cycle after a hazard is lean."""
    r = reserves(world, ctx)
    need2 = HOARD_FACTOR / 1.5 * r["food_need"]
    if r["food_need"] <= r["food_stock"] < need2:
        yield Finding("ops.hoard", "info", f"food {r['food_stock']} covers the reserve but not 2x ({need2:.0f}): "
                      "plant every moist tile and keep processors running", "food", evidence={"target": need2})


@monitor("ops.farm_flags", rules=["farm-flag-recheck"])
def farm_flags(world, ctx):
    """Food falling while farmhouses all plant first: harvest lags; switch most to harvest first."""
    r = rates(world, ctx)
    if not r or r.get("food", 0) >= 0:
        return
    farms = [b for b in world.finished("FarmHouse") if "plantingFirst" in (b.raw.get("setup") or {})]
    planting = [b for b in farms if b.raw["setup"]["plantingFirst"]]
    if farms and len(planting) == len(farms):
        yield Finding("ops.farm_flags", "warn", f"food falling {r['food']:.0f}/day and all {len(farms)} farmhouses "
                      "plant first: ripe crops wait", "farms",
                      fix="; ".join(f'building_action(building_id={bid(b)}, component="FarmHouse", '
                                    'action="UnprioritizePlanting", args=[])' for b in planting[1:4]))


@monitor("ops.gatherers", rules=["gatherers-3-plus"])
def gatherers(world, ctx):
    """Fewer than 3 gatherers running while ripe bushes wait."""
    ripe = sum(v.get("gatherableRipe", 0) for blk in world.plant_blocks or [] for k, v in blk["plants"].items()
               if any(p in k for p in GATHERER_PLANTS))
    flags = [b for b in world.finished("GathererFlag") if not b.raw.get("paused")]
    if ripe >= 20 and len(flags) < 3:
        yield Finding("ops.gatherers", "info", f"{ripe} ripe bushes and only {len(flags)} gatherers running: "
                      "aim for 3 or more", "gatherers", evidence={"ripe": ripe})


@monitor("ops.fermenters", rules=["fermenter-per-gardens"])
def fermenters(world, ctx):
    """About 1 Fermenter per 2-3 Hydroponic Gardens (one Fermenter takes 16 mushrooms at a time)."""
    gardens = len(world.finished("HydroponicGarden"))
    ferm = len(world.finished("Fermenter"))
    if gardens >= 2 and ferm * 3 < gardens:
        yield Finding("ops.fermenters", "info", f"{gardens} hydroponic gardens and {ferm} fermenters: "
                      f"add {-(-gardens // 3) - ferm} fermenter(s) so mushrooms become food", "fermenters")


@monitor("ops.growth_gate", rules=["growth-gate"])
def growth_gate(world, ctx):
    """More pods than replacement needs while food falls or the reserve is short: stop adding growth."""
    pods = [b for b in world.finished("BreedingPod") if not b.raw.get("paused")]
    extra = len(pods) - pods_needed(world.beavers)
    if extra <= 0:
        return
    r = rates(world, ctx)
    res = reserves(world, ctx)
    why = []
    if r and r.get("food", 0) < 0:
        why.append(f"food falling {r['food']:.0f}/day")
    if res["food_stock"] < res["food_need"] or res["water_stock"] < res["water_need"]:
        why.append("hazard reserve short")
    if why:
        yield Finding("ops.growth_gate", "info", f"{len(pods)} pods running, {extra} above replacement, but "
                      f"{' and '.join(why)}: build no new pods or homes until food trends up", "growth",
                      evidence={"pods": len(pods), "extra": extra})


@monitor("ops.priority_tiers", rules=["priority-tiers"])
def priority_tiers(world, ctx):
    """Pumps VeryHigh when water days are short; farmhouses and food workshops at High or above."""
    res = reserves(world, ctx)
    low = []
    if res["water_stock"] < res["water_need"]:
        low += [(b, "VeryHigh") for b in world.finished() if "WaterPump" in b.name and not b.raw.get("paused")
                and b.raw.get("priority") != "VeryHigh"]
    if food_days(world) < 5:
        low += [(b, "High") for b in world.finished("FarmHouse", "FoodFactory", "Fermenter") if not b.raw.get("paused")
                and b.raw.get("priority") not in ("High", "VeryHigh")]
    if low:
        yield Finding("ops.priority_tiers", "info", f"{len(low)} food/water jobs below their tier: "
                      f"{[b.label for b, _ in low[:5]]}", "tiers",
                      fix="; ".join(f'set_priority(building_id={bid(b)}, priority="{p}")' for b, p in low[:5]))


@monitor("ops.workday", rules=["workday-16h"])
def workday(world, ctx):
    """Workday longer than 16 h while needs are critical (long days caused hunger and thirst crises)."""
    h = world.hours
    if not h or h.get("hours", WORKDAY_HOURS) <= WORKDAY_HOURS:
        return
    crit = sum(n.get("critical", 0) for n in world.needs if n.get("need") in ("Hunger", "Thirst", "Sleep"))
    yield Finding("ops.workday", "warn" if crit else "info", f"workday is {h['hours']:.0f} h"
                  + (f" with {crit} beavers critical on hunger/thirst/sleep" if crit else "")
                  + ": back to 16 h; use more workers instead", "hours", fix=f"set_work_hours(hours={WORKDAY_HOURS})")


@monitor("ops.power_shed", rules=["power-shortage-order"])
def power_shed(world, ctx):
    """Power short on a network: pause the least needed leaf buildings first."""
    for i, n in enumerate(world.networks):
        if not n.get("demand") or n["supply"] >= n["demand"]:
            continue
        members = [world.by_id[m["id"]] for m in n["members"] if m["id"] in world.by_id]
        leaves = [b for b in members if b.name in SHED_ORDER and not b.raw.get("paused")]
        leaves.sort(key=lambda b: SHED_ORDER.index(b.name))
        short = n["demand"] - n["supply"]
        pick, freed = [], 0
        for b in leaves:
            if freed >= short:
                break
            pick.append(b)
            freed += POWER_USE.get(b.name, 0)
        if pick:
            yield Finding("ops.power_shed", "warn", f"network {n['id']} short {short} hp: pause "
                          f"{[b.label for b in pick]} first", f"net-{n['id']}",
                          fix="; ".join(f'set_paused(building_id={bid(b)}, paused=True)' for b in pick))


@monitor("ops.steam_feed", rules=["steam-engine-feed"])
def steam_feed(world, ctx):
    """Steam Engines burn logs and water: low logs, or no hauling post within 10 tiles."""
    engines = [b for b in world.finished("SteamEngine") if not b.raw.get("paused")]
    if not engines:
        return
    logs = world.good("Log")["available"]
    posts = world.finished("HaulingPost")
    far = [e for e in engines if not any(abs(p.x - e.x) + abs(p.y - e.y) <= 10 for p in posts)]
    if logs < 20 * len(engines):
        yield Finding("ops.steam_feed", "warn", f"{logs} logs for {len(engines)} steam engine(s): they stop "
                      "without fuel", "steam-logs")
    if far:
        yield Finding("ops.steam_feed", "info", f"no hauling post within 10 tiles of {[e.label for e in far]}: "
                      "fuel arrives slowly", "steam-post", [far[0].x, far[0].y, far[0].z])


@monitor("ops.pre_hazard", rules=["wood-pre-drought-stock", "hazard-checklist-3-days"])
def pre_hazard(world, ctx):
    """Hazard due within 3 days: the checklist (food, water, storage, wood, pods, pumps) in one line."""
    w = world.colony.get("weather") or {}
    until = w.get("daysUntil")
    if w.get("state") != "approaching" or until is None or until > CHECKLIST_DAYS:
        return
    res = reserves(world, ctx)
    wood = world.good("Log")["available"] + world.good("Plank")["available"]
    checks = {"food": res["food_stock"] >= res["food_need"], "water": res["water_stock"] >= res["water_need"],
              "tanks": res["water_cap"] >= res["water_need"], "wood": wood >= WOOD_BEFORE_DROUGHT,
              "food days": food_days(world) >= 3}
    bad = [k for k, ok in checks.items() if not ok]
    msg = f"{w.get('hazard')} in {until} days: checklist " + ", ".join(f"{k} {'ok' if ok else 'SHORT'}"
                                                                      for k, ok in checks.items())
    if "Drought" in str(w.get("hazard")):
        msg += "; then pause pumps once tanks are full and raise farms to High"
    yield Finding("ops.pre_hazard", "warn" if bad else "info", msg, "checklist", evidence={"short": bad})


@monitor("ops.speed", rules=["speed-3-while-waiting", "dont-pause"])
def speed(world, ctx):
    """On stream (a thought in the last 10 minutes): paused with no emergency, or slower than 3 while stable."""
    thoughts = (world.state.get("overlay") or {}).get("thoughts") or []
    last = max((t.get("at") or 0 for t in thoughts), default=0)
    if not last or time.time() - last > 600:
        return      # no stream running (prep, or the go-ahead gate): speed 0 is right
    s = world.colony["time"].get("speed") or 0
    w = (world.colony.get("weather") or {}).get("state")
    calm = w == "temperate" and food_days(world) >= 3 and world.good("Water")["available"] >= 2 * world.beavers
    if s == 0 and calm:
        yield Finding("ops.speed", "warn", "game paused on stream with no emergency: viewers see nothing move",
                      "speed", fix="set_speed(speed=3)")
    elif 0 < s < 3 and calm:
        yield Finding("ops.speed", "info", f"speed {s:g} while stable: play at 3", "speed", fix="set_speed(speed=3)")


@monitor("ops.tank_capacity", rules=["reserve-storage-capacity"])
def tank_capacity(world, ctx):
    """Tank capacity below the hazard water reserve: build tanks a cycle ahead (Medium Tank = 300)."""
    r = reserves(world, ctx)
    gap = r["water_need"] - r["water_cap"]
    if r["water_cap"] and gap > 0:
        yield Finding("ops.tank_capacity", "warn", f"tanks hold {r['water_cap']} but the reserve needs "
                      f"{r['water_need']:.0f}: build {-(-int(gap) // 300)} Medium Tank(s) (300 each) now", "tanks",
                      evidence={"gap": gap})


@monitor("ops.support_caps", rules=["building-caps-support"])
def support_caps(world, ctx):
    """Support buildings beyond need: idle Builders' Huts, Inventors with nothing left to unlock; extras on Low."""
    sites = [b for b in world.buildings if not b.finished and b.name != "Path"]
    huts = [b for b in world.finished("BuildersHut") if not b.raw.get("paused")]
    if len(huts) > 1 and len(sites) < 3 * (len(huts) - 1):
        extra = [b for b in huts[1:] if b.raw.get("priority") not in ("Low", "VeryLow")]
        if extra:
            yield Finding("ops.support_caps", "info", f"{len(huts)} builders' huts for {len(sites)} sites: "
                          "put the extras on Low", "huts",
                          fix="; ".join(f'set_priority(building_id={bid(b)}, priority="Low")' for b in extra[:3]))
    locked = [bp for bp in world.blueprints or [] if not bp["unlocked"]]
    inventors = [b for b in world.finished("Inventor") if not b.raw.get("paused")]
    if world.blueprints and not locked and inventors:
        yield Finding("ops.support_caps", "info", f"everything is unlocked; {len(inventors)} inventors still work",
                      "inventors", fix="; ".join(f'set_paused(building_id={bid(b)}, paused=True)' for b in inventors))
