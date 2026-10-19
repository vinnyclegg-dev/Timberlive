"""Water and food totals, reserves, storage and hazard countdown (plan section 4.1, 4.5)."""

from __future__ import annotations

from collections import Counter

from ..findings import Finding, monitor
from . import BUILDING_WATER, DRINK_PER_BEAVER, EAT_PER_BEAVER, FOOD, INPUTS


def food_stock(world) -> int:
    return sum(world.good(g)["available"] for g in FOOD)


def food_days(world) -> float:
    return food_stock(world) / max(1, EAT_PER_BEAVER * world.beavers)


def water_use(world) -> tuple[float, dict]:
    per = Counter(b.name for b in world.finished() if not b.raw.get("paused"))
    build = {k: round(v * per[k], 1) for k, v in BUILDING_WATER.items() if per[k]}
    return DRINK_PER_BEAVER * world.beavers + sum(build.values()), build


def reserves(world, ctx) -> dict:
    days = ctx.longest_hazard_days
    use, build = water_use(world)
    return {"water_use": use, "water_build": build, "water_need": 1.5 * days * use,
            "water_stock": world.good("Water")["available"], "water_cap": world.good("Water").get("capacity", 0),
            "food_need": 1.5 * days * EAT_PER_BEAVER * world.beavers, "food_stock": food_stock(world),
            "hazard_days": days}


def hazard_soon(world) -> bool:
    w = world.colony.get("weather") or {}
    return w.get("state") in ("approaching", "hazardous")


@monitor("food.days", rules=["food-days-min-3", "pods-only-on-food-target"])
def food_days_check(world, ctx):
    """Food days (edible stock / 3 per beaver) never below 3."""
    d = food_days(world)
    if d < 3:
        pods = [b for b in world.finished("BreedingPod") if "Paused." not in (b.raw.get("statuses") or [])]
        yield Finding("food.days", "critical", f"food days {d:.1f} < 3: staff farms and food jobs first"
                      + (f"; {len(pods)} pods running" if pods else ""), "food",
                      evidence={"food": food_stock(world), "beavers": world.beavers})


@monitor("water.low", rules=["water-low-stop"])
def water_low(world, ctx):
    """Water stock below 2 per beaver (watch.py stop condition)."""
    w = world.good("Water")["available"]
    if w < 2 * world.beavers:
        yield Finding("water.low", "critical", f"water {w} < 2 per beaver ({2 * world.beavers})", "Water")


@monitor("water.reserve", rules=["hazard-reserve-1.5x", "building-water-counted"])
def water_reserve(world, ctx):
    """Water stock vs 1.5 x longest hazard x daily use (beavers + pods, hydroponics, steam engines, brewery)."""
    r = reserves(world, ctx)
    if r["water_stock"] < r["water_need"]:
        short = int(r["water_need"] - r["water_stock"])
        sev = "critical" if hazard_soon(world) else "warn"
        cap_note = ""
        if r["water_cap"] < r["water_need"]:
            cap_note = f"; capacity {r['water_cap']} is below the reserve: build tanks for {int(r['water_need'] - r['water_cap'])} more"
        yield Finding("water.reserve", sev, f"water {r['water_stock']} vs hazard reserve {r['water_need']:.0f} "
                      f"(use {r['water_use']:.0f}/day): short {short}{cap_note}", "Water", evidence=r)


@monitor("food.reserve", rules=["hazard-reserve-1.5x"])
def food_reserve(world, ctx):
    """Edible food vs 1.5 x longest hazard x 3 per beaver per day."""
    r = reserves(world, ctx)
    if r["food_stock"] < r["food_need"]:
        sev = "critical" if hazard_soon(world) else "warn"
        yield Finding("food.reserve", sev, f"food {r['food_stock']} vs hazard reserve {r['food_need']:.0f}: "
                      f"short {int(r['food_need'] - r['food_stock'])}", "food", evidence=r)


@monitor("storage.full", rules=["full-output-stalls", "storage-full-warn"])
def storage_full(world, ctx):
    """A good at 95 %+ of its capacity: its producer stops (full output stalls production)."""
    for gid, g in world.goods.items():
        cap = g.get("capacity") or 0
        have = max(g.get("available", 0), g.get("total", 0))
        if cap and have >= 0.95 * cap:
            kind = ("Industrial Pile" if gid in ("Log", "Plank", "ScrapMetal", "MetalBlock", "MetalPart", "Gear",
                                                 "TreatedPlank", "PineResin") else
                    "Tank" if gid in ("Water", "Badwater", "CanolaOil", "Extract") else "Warehouse")
            yield Finding("storage.full", "warn", f"{gid} {have}/{cap}: producers stall; add {'an' if kind[0] in 'AEIOU' else 'a'} {kind} set to {gid} "
                          "or use it", gid)


@monitor("goods.empty_input", rules=["empty-input-starves"])
def empty_inputs(world, ctx):
    """A good at 0 that a running workshop needs."""
    for gid, users in INPUTS.items():
        if world.good(gid)["available"] > 0:
            continue
        starved = [b.label for b in world.finished(*users) if not b.raw.get("paused")]
        if starved:
            yield Finding("goods.empty_input", "warn", f"{gid} is at 0; starved: {starved[:5]}", gid)


@monitor("water.pumps_per_pop", rules=["overbuild-water-pumps"])
def pumps_per_pop(world, ctx):
    """About 1 water pump per 5 beavers (user: overbuild food and water)."""
    pumps = [b for b in world.finished() if "Pump" in b.name and "Badwater" not in b.name and not b.raw.get("paused")]
    want = -(-world.beavers // 5)
    if pumps and len(pumps) < want:
        yield Finding("water.pumps_per_pop", "info", f"{len(pumps)} pumps running for {world.beavers} beavers; "
                      f"rule of thumb ~{want}", "pumps")


@monitor("hazard.countdown", rules=["hazard-reserve-1.5x"])
def hazard_countdown(world, ctx):
    """Drought/badtide approaching or under way, with the reserve status."""
    w = world.colony.get("weather") or {}
    if w.get("state") not in ("approaching", "hazardous"):
        return
    r = reserves(world, ctx)
    ok = r["water_stock"] >= r["water_need"] and r["food_stock"] >= r["food_need"]
    when = (f"in {w.get('daysUntil')} days" if w["state"] == "approaching" else f"{w.get('daysRemaining')} days left")
    playbook = ("close floodgates on badwater links, keep pumps off badwater" if "Badtide" in str(w.get("hazard"))
                else "pause pumps once tanks are full, keep the river high for crops")
    yield Finding("hazard.countdown", "warn" if ok else "critical",
                  f"{w.get('hazard')} {when}; reserve {'ok' if ok else 'SHORT'}; {playbook}", "hazard", evidence=w)


@monitor("goods.empty", rules=["food-variety"])
def empty_goods(world, ctx):
    """Goods with storage set aside but none in stock (an empty food line costs wellbeing)."""
    empty = [g for g, v in world.goods.items() if v.get("capacity") and not v.get("available") and g not in INPUTS]
    if empty:
        yield Finding("goods.empty", "info", f"stored goods at 0: {empty}", "empty")
