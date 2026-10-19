"""Buildings, jobs, power, storage settings and sites (plan section 4.2; ported from harness/audit.py,
monitor.py and watch.py). Every fix is a suggestion: Foreman never changes the game."""

from __future__ import annotations

from ..findings import Finding, monitor
from . import BATCH_MAKERS, FOOD_JOBS, FOOD_STORE_GOODS, POWER_USE, bid

STORE_SUFFIX = ("Warehouse", "Pile", "Tank")


@monitor("jobs.unemployed", rules=["jobs-0-2-unemployed"])
def unemployed(world, ctx):
    """More than 2 unemployed beavers."""
    n = world.colony["population"].get("unemployed", 0)
    if n > 2:
        yield Finding("jobs.unemployed", "warn", f"{n} unemployed: add a needed workplace or a Low-priority "
                      "builders' hut / hauling post", "jobs")


@monitor("jobs.short_staffed", rules=["food-jobs-staffed-first", "tune-workers"])
def short_staffed(world, ctx):
    """Unpaused buildings with fewer workers than desired; food and water jobs first."""
    short = [b for b in world.finished() if b.raw.get("workers") and not b.raw.get("paused")
             and b.raw["workers"]["assigned"] < b.raw["workers"]["desired"]]
    key = [b for b in short if b.name.startswith(FOOD_JOBS)]
    if key:
        yield Finding("jobs.short_staffed", "critical" if world.colony["population"].get("unemployed", 0) == 0 else "warn",
                      f"food/water jobs short of workers: {[b.label for b in key][:8]}", "food-jobs",
                      fix=f'set_priority(building_id={bid(key[0])}, priority="VeryHigh")  # or free workers elsewhere')
    rest = [b for b in short if b not in key]
    if rest:
        yield Finding("jobs.short_staffed", "info", f"short of workers: {[b.label for b in rest][:8]}", "other-jobs")


@monitor("jobs.paused_food", rules=["paused-register", "drought-pumps"])
def paused_food(world, ctx):
    """Paused food/water buildings (check their resume condition)."""
    paused = [b for b in world.finished() if b.raw.get("paused") and b.name.startswith(FOOD_JOBS)]
    if paused:
        yield Finding("jobs.paused_food", "warn", f"paused food/water: {[b.label for b in paused][:8]}; resume when "
                      "the reason is gone", "paused-food",
                      fix=f"set_paused(building_id={bid(paused[0])}, paused=False)")


@monitor("bld.storage_assigned", rules=["storage-good-set"])
def storage_assigned(world, ctx):
    """Every store and tank has a good set."""
    for b in world.finished():
        setup = b.raw.get("setup") or {}
        is_store = b.name.endswith(STORE_SUFFIX)
        if setup.get("good") == "" or (is_store and not setup.get("good")):
            good = "Water" if "Tank" in b.name else "<good>"
            yield Finding("bld.storage_assigned", "warn", f"{b.label} has no good set", b.id, [b.x, b.y, b.z],
                          fix=f'building_action(building_id={bid(b)}, component="SingleGoodAllower", action="Allow", '
                              f'args=["{good}"])')


@monitor("bld.recipe", rules=["recipe-set"])
def recipe(world, ctx):
    """Every recipe building has a recipe."""
    for b in world.finished():
        if (b.raw.get("setup") or {}).get("recipe") == "":
            yield Finding("bld.recipe", "warn", f"{b.label} has no recipe", b.id, [b.x, b.y, b.z],
                          fix=f'building_action(building_id={bid(b)}, component="Manufactory", action="SetRecipe", '
                              'args=["<recipe>"])  # inspect_building lists the recipes')


@monitor("bld.emptying", rules=["no-emptying-food"])
def emptying(world, ctx):
    """Stores marked for emptying (emptying a food/water store starts a famine)."""
    for b in world.finished():
        setup = b.raw.get("setup") or {}
        if not setup.get("emptying") or "Flag" in b.name:
            continue
        food = setup.get("good") in FOOD_STORE_GOODS
        yield Finding("bld.emptying", "critical" if food else "info",
                      f"{b.label} is being emptied ({setup.get('good') or '?'})", b.id, [b.x, b.y, b.z],
                      fix=f'building_action(building_id={bid(b)}, component="Emptiable", action="UnmarkForEmptying", '
                          'args=[])' if food else "")


@monitor("bld.pump_badwater", rules=["pump-clean-intake"])
def pump_badwater(world, ctx):
    """Water pumps within 2 tiles of badwater (skipped during a badtide, when all water is bad)."""
    w = world.colony.get("weather") or {}
    if w.get("hazard") == "BadtideWeather" and w.get("state") == "hazardous":
        return
    for b in world.finished():
        if "Pump" in b.name and "Badwater" not in b.name and world.badwater_near(b.x, b.y):
            yield Finding("bld.pump_badwater", "warn", f"{b.label} is within 2 tiles of badwater: move it to "
                          "clean water or wall the badwater off", b.id, [b.x, b.y, b.z])


@monitor("bld.power", rules=["power-enough", "no-beaver-power"])
def power(world, ctx):
    """Per network: nominal machine demand vs supply (networks grouped by live supply)."""
    nets, planned = {}, []
    for b in world.buildings:
        if b.name not in POWER_USE or b.raw.get("paused"):
            continue
        if not b.finished:
            planned.append(b)
        elif b.raw.get("power"):
            nets.setdefault(b.raw["power"].get("networkSupply", 0), []).append(b)
    for supply, users in nets.items():
        need = sum(POWER_USE[b.name] for b in users)
        if need > supply:
            yield Finding("bld.power", "warn", f"network gives {supply} hp, machines need {need} "
                          f"({', '.join(b.label for b in users)}): they run at ~{supply * 100 // max(1, need)}%; "
                          "add water wheels on this network", f"net-{supply}", evidence={"supply": supply, "need": need})
    if planned:
        yield Finding("bld.power", "info", f"{sum(POWER_USE[b.name] for b in planned)} hp more needed when "
                      f"{[b.label for b in planned]} finish", "planned")


def power_state(b, world) -> str | None:
    """'linked', 'waiting: <site>' or 'unlinked' (harness/watch.py power_state); None if no power points."""
    links = b.raw.get("powerConnections")
    if not links:
        return None
    if any(link.get("connected") for link in links):
        return "linked"
    mine = {(lk["x"], lk["y"], lk["z"]): tuple(lk["from"]) for lk in links}
    for s in world.buildings:
        if s.finished or s.id == b.id:
            continue
        for p in s.raw.get("powerConnections") or []:
            if tuple(p["from"]) in mine and mine[tuple(p["from"])] == (p["x"], p["y"], p["z"]):
                return f"waiting: {s.label} {int((s.raw.get('buildProgress') or 0) * 100)}%"
    return "unlinked"


@monitor("bld.power_link", rules=["power-link-check"])
def power_link(world, ctx):
    """Finished powered buildings with no power link and no site coming to meet them."""
    for b in world.finished():
        if power_state(b, world) == "unlinked":
            yield Finding("bld.power_link", "warn", f"{b.label} has no power link: nothing built at its power points",
                          b.id, [b.x, b.y, b.z], fix="place a PowerShaft at one of its powerConnections points")


@monitor("bld.status", rules=["building-statuses"])
def statuses(world, ctx):
    """Game status icons other than Paused, grouped (no workers, no power, full output, nothing to cut...)."""
    groups = {}
    for b in world.finished():
        for s in b.raw.get("statuses") or []:
            if s != "Paused.":
                groups.setdefault(s, []).append(b)
    for s, where in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        sev = "critical" if "connected" in s.lower() else "warn"
        more = f" +{len(where) - 6}" if len(where) > 6 else ""
        yield Finding("bld.status", sev, f"'{s}': {[b.label for b in where[:6]]}{more}", s)


@monitor("bld.connected", rules=["door-on-connected-path"])
def connected(world, ctx):
    """Doors not on the district's road network (own flood fill; the game status is the authority)."""
    if not world.dc:
        return
    off = [b for b in world.buildings if b.door and b.name not in ("DistrictCenter",)
           and world.door_connected(b) is False]
    if off:
        yield Finding("bld.connected", "info", f"{len(off)} doors not on Foreman's road graph (model check, "
                      f"phase 1): {[b.label for b in off[:6]]}", "roads", evidence={"ids": [b.id for b in off]})


@monitor("bld.batch", rules=["batch-visible"])
def batch(world, ctx):
    """Long-cycle makers (Hydroponic Garden, Oil Press, Fermenter, Coffee Brewery): inputs missing."""
    for b in world.finished(*BATCH_MAKERS):
        st = (world.state.get("batches") or {}).get(b.id)
        if st and not st["inputs_ok"] and not b.raw.get("paused"):
            yield Finding("bld.batch", "warn", f"{b.label} {st['recipe']} at {st['progress']:.0%}: inputs missing "
                          f"(stock {st['stock']})", b.id, [b.x, b.y, b.z])


@monitor("farm.split", rules=["farmhouse-split"])
def farm_split(world, ctx):
    """Farmhouses: harvest first; with 2+, about 1 in 3 plants first."""
    farms = [b for b in world.finished() if "plantingFirst" in (b.raw.get("setup") or {})]
    planting = [b for b in farms if b.raw["setup"]["plantingFirst"]]
    if farms and (len(planting) > max(1, round(len(farms) / 3)) or (len(farms) == 1 and planting)):
        yield Finding("farm.split", "info", f"{len(planting)}/{len(farms)} farmhouses plant first: set the rest to "
                      "harvest first", "farms",
                      fix=f'building_action(building_id={bid(planting[-1])}, component="FarmHouse", '
                          'action="UnprioritizePlanting", args=[])')


@monitor("sites.stuck", rules=["sites-progress"])
def sites_stuck(world, ctx):
    """Construction sites at 0 % for a game day or more (usually the door is not on a linked path)."""
    now = world.game_day()
    seen = ctx.store.get("site_zero_since", {})
    sites = {b.id: b for b in world.buildings if not b.finished}
    seen = {i: d for i, d in seen.items() if i in sites and not sites[i].raw.get("buildProgress")}
    for i, b in sites.items():
        if not b.raw.get("buildProgress"):
            seen.setdefault(i, now)
    ctx.store.set("site_zero_since", seen)
    stuck = [sites[i] for i, d in seen.items() if now - d >= 1]
    if stuck:
        yield Finding("sites.stuck", "warn", f"sites at 0% for 1+ day: {[b.label for b in stuck[:8]]}: check the "
                      "door is on a path linked to the district, materials and builders", "sites")


@monitor("progress.science", rules=["science-running"])
def science(world, ctx):
    """Science piling up unspent."""
    sci = world.colony.get("science", 0)
    if sci > 500:
        yield Finding("progress.science", "info", f"science {sci} unspent: unlock the next building on the plan",
                      "science", fix='unlock_building(template="<Template>")')


@monitor("bld.paused", rules=["paused-register", "paused-wood-resume"])
def paused(world, ctx):
    """Every paused building against the paused register: no reason logged, or its resume condition is met."""
    from .. import paused as register
    reg = register.load()
    ps = [b for b in world.finished() if b.raw.get("paused") and not b.name.startswith(FOOD_JOBS)]
    unlogged = [b for b in ps if b.id not in reg]
    for b in ps:
        e = reg.get(b.id)
        if e and e.get("until") and register.met(world, e["until"]):
            yield Finding("bld.paused", "warn", f"{b.label} paused for '{e['reason']}': resume condition "
                          f"'{e['until']}' is met", b.id, [b.x, b.y, b.z],
                          fix=f'set_paused(building_id={bid(b)}, paused=False)')
    if unlogged:
        yield Finding("bld.paused", "info", f"{len(unlogged)} paused with no reason logged: "
                      f"{[b.label for b in unlogged][:8]}", "paused",
                      fix=f'python -m foreman pause-reason {unlogged[0].id} "<reason>" --until "<metric op value>"')
