"""Forecasts and hazards: stock trends from the store history, time to empty or full, the hazard record
(start, length, usage, longest so far) and checks while a hazard runs (plan sections 4.1, 4.5).

The hazard record is Foreman's own: the game panel shows no schedule while temperate, so lengths come
from what Foreman saw. It never writes knowledge files; it hands the AI the line to add.
"""

from __future__ import annotations

import math

from ..findings import Finding, monitor
from . import EAT_PER_BEAVER, FOOD
from .supply import food_stock, reserves

WINDOW_DAYS = 1.0       # trend over the last game day
MIN_SPAN = 0.25         # need at least a quarter day of history
TRACKED = ("Water", "Log", "Plank", "Gear")
FARM_JOBS = ("FarmHouse", "GathererFlag")


def _food(goods: list | dict) -> int:
    items = goods.values() if isinstance(goods, dict) else goods
    return sum(g.get("available", 0) for g in items if g["id"] in FOOD)


def rates(world, ctx) -> dict:
    """Net change per game day for tracked goods and edible food (empty dict without history)."""
    if getattr(ctx, "_rates", None) is not None:
        return ctx._rates
    now = world.game_day()
    hist = [(day, data) for _ts, day, data in ctx.store.history("goods") if day is not None and day <= now]
    out = {}
    old = next(((d, g) for d, g in hist if d >= now - WINDOW_DAYS), None)
    if old and now - old[0] >= MIN_SPAN:
        span = now - old[0]
        then = {g["id"]: g.get("available", 0) for g in old[1]}
        for gid in TRACKED:
            out[gid] = (world.good(gid)["available"] - then.get(gid, 0)) / span
        out["food"] = (food_stock(world) - _food(old[1])) / span
        out["span"] = span
    ctx._rates = out
    return out


@monitor("forecast.stock", rules=["plan-ahead-demand", "full-output-stalls", "storage-with-producer"])
def stock_forecast(world, ctx):
    """Stock trends: water or food running out within 3 days, logs or planks within 2, stores filling in a day."""
    r = rates(world, ctx)
    if not r:
        return
    stock = {gid: world.good(gid)["available"] for gid in TRACKED}
    stock["food"] = food_stock(world)
    for gid, rate in r.items():
        if gid == "span":
            continue
        have = stock[gid]
        if rate < 0:
            days = have / -rate
            limit = 3 if gid in ("Water", "food") else 2
            if days < limit:
                yield Finding("forecast.stock", "critical" if gid in ("Water", "food") and days < 1.5 else "warn",
                              f"{gid} falling {rate:.0f}/day: empty in {days:.1f} days at this rate", f"{gid}-empty",
                              evidence={"rate": rate, "stock": have})
        elif rate > 0 and gid != "food":
            cap = world.good(gid).get("capacity") or 0
            if cap and (cap - have) / rate < 1:
                yield Finding("forecast.stock", "info", f"{gid} rising {rate:.0f}/day: storage full in "
                              f"{(cap - have) / rate:.1f} days (producers then stall)", f"{gid}-full",
                              evidence={"rate": rate, "stock": have, "capacity": cap})


@monitor("hazard.record", rules=["post-hazard-actions", "hazard-reserve-1.5x"])
def hazard_record(world, ctx):
    """Track each drought/badtide: start, length, water and food used; raise the longest-hazard figure."""
    w = world.colony.get("weather") or {}
    now = world.game_day()
    cur = ctx.store.get("hazard_now")
    water, food = world.good("Water")["available"], food_stock(world)
    if w.get("state") == "hazardous":
        left = w.get("daysRemaining") or 0
        if not cur:
            cur = {"hazard": w.get("hazard"), "start": now, "length": math.ceil(left), "water0": water, "food0": food,
                   "beavers": world.beavers}
        cur["length"] = max(cur["length"], math.ceil(now - cur["start"] + left))
        ctx.store.set("hazard_now", cur)
        if cur["length"] > ctx.longest_hazard_days:
            ctx.store.set("longest_hazard_days", cur["length"])
            ctx.longest_hazard_days = cur["length"]
            yield Finding("hazard.record", "warn", f"this {cur['hazard']} lasts {cur['length']} days, the longest so "
                          "far: reserves now scale to it", "longest")
        return
    if cur:
        days = max(1.0, now - cur["start"])
        rec = {**cur, "end": now, "days": round(days, 1), "water_used": cur["water0"] - water,
               "food_used": cur["food0"] - food}
        hist = ctx.store.get("hazards", [])
        hist.append(rec)
        ctx.store.set("hazards", hist)
        ctx.store.set("hazard_now", None)
        ctx.store.set("hazard_note_until", now + 1)
    note_until = ctx.store.get("hazard_note_until", 0)
    hist = ctx.store.get("hazards", [])
    if hist and now < note_until:
        h = hist[-1]
        line = (f"c{int(h['start'] // 100)}d{int(h['start'] % 100)} {h['hazard']} {h['length']} days, "
                f"{h['beavers']} beavers: water {h['water_used']:+.0f} net, food {h['food_used']:+.0f} net")
        yield Finding("hazard.record", "info", f"{h['hazard']} over: add to knowledge/goals.md: '{line}'; check "
                      "farmhouses replant, paused food jobs and pumps are back on", "over", evidence=h)


@monitor("hazard.during", rules=["pods-pause-only-if-run-out", "hazard-drought-priorities", "drought-pumps",
                                 "hazard-badtide-inlets"])
def hazard_during(world, ctx):
    """While a hazard runs: will water and food last until it ends, and are farms and gatherers at High."""
    w = world.colony.get("weather") or {}
    if w.get("state") != "hazardous":
        return
    left = w.get("daysRemaining") or 0
    res = reserves(world, ctx)
    r = rates(world, ctx)
    water_rate = r.get("Water") if r.get("Water", 0) < 0 else -res["water_use"]
    food_rate = r.get("food") if r.get("food", 0) < 0 else -EAT_PER_BEAVER * world.beavers
    for name, have, rate in (("water", res["water_stock"], water_rate), ("food", res["food_stock"], food_rate)):
        lasts = have / -rate if rate < 0 else math.inf
        if lasts < left:
            pods = [b for b in world.finished("BreedingPod") if not b.raw.get("paused")]
            yield Finding("hazard.during", "critical", f"{name} lasts {lasts:.1f} days but the {w.get('hazard')} has "
                          f"{left} left: cut {name} use now" + (f"; {len(pods)} pods running may pause" if pods else ""),
                          name, evidence={"stock": have, "rate": rate, "left": left},
                          fix="; ".join(f'set_paused(building_id="{b.id}", paused=True)' for b in pods[:3]))
    if "Drought" in str(w.get("hazard")):
        low = [b for b in world.finished(*FARM_JOBS) if b.raw.get("priority") not in ("High", "VeryHigh")
               and not b.raw.get("paused")]
        if low:
            yield Finding("hazard.during", "info", f"drought: {len(low)} farms/gatherers below High priority",
                          "priority", fix="; ".join(f'set_priority(building_id="{b.id}", priority="High")'
                                                    for b in low[:4]))
