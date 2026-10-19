"""Progress toward one of every building, and the material chains that gate the rest (plan section 4.6).

Counting matches harness/progress.py: Decoration and Paths groups don't count as buildings.
"""

from __future__ import annotations

from ..findings import Finding, monitor

SKIP_GROUPS = {"Decoration", "Paths"}
# Who makes each building material: (any of these makes it, and these feed it). knowledge/09 production chains.
MAKERS = {"Log": (("LumberjackFlag",), ()), "Plank": (("IndustrialLumberMill", "LumberMill"), ()),
          "Gear": (("GearWorkshop",), ()), "MetalBlock": (("Smelter",), ("ScavengerFlag",)),
          "MetalPart": (("Metalsmith",), ("ScavengerFlag",)), "ScrapMetal": (("ScavengerFlag",), ()),
          "PineResin": (("TappersShack",), ()), "TreatedPlank": (("WoodWorkshop",), ("TappersShack",)),
          "Extract": (("Centrifuge",), ("DeepBadwaterPump",)), "Explosives": (("ExplosivesFactory",), ("DeepBadwaterPump",)),
          "Dirt": (("DirtExcavator",), ())}


def key(bp: dict) -> str:
    """Template without the faction suffix: the same name World uses for buildings."""
    return bp["template"].split(".")[0]


def built_names(world) -> tuple[set, set]:
    finished = {b.name for b in world.buildings if b.finished}
    sites = {b.name for b in world.buildings if not b.finished}
    return finished, sites


def tally(world) -> dict | None:
    if not world.blueprints:
        return None
    finished, sites = built_names(world)
    rows = [bp for bp in world.blueprints if bp["group"] not in SKIP_GROUPS]
    missing = [bp for bp in rows if key(bp) not in finished]
    return {"done": len(rows) - len(missing), "total": len(rows), "missing": missing,
            "ready": [bp for bp in missing if bp["unlocked"] and key(bp) not in sites],
            "building": [bp for bp in missing if key(bp) in sites],
            "locked": sorted((bp for bp in missing if not bp["unlocked"]), key=lambda bp: bp["science"])}


@monitor("progress.buildings", rules=["progress-every-building"])
def buildings(world, ctx):
    """One of every building: unlocked ones not yet placed, and the cheapest locked ones science can buy."""
    t = tally(world)
    if not t:
        return
    sci = world.colony.get("science", 0)
    afford = [bp for bp in t["locked"] if bp["science"] <= sci]
    msg = f"{t['done']}/{t['total']} buildings built"
    if t["ready"]:
        msg += f"; unlocked, not placed: {[bp['name'] for bp in t['ready'][:6]]}"
    if afford:
        msg += f"; science {sci} buys: {[(bp['name'], bp['science']) for bp in afford[:5]]}"
    yield Finding("progress.buildings", "info", msg, "progress",
                  evidence={"ready": [bp["name"] for bp in t["ready"]], "afford": [bp["name"] for bp in afford]})


@monitor("progress.tech_path", rules=["progress-every-building", "irrigation-barrier-chain"])
def tech_path(world, ctx):
    """Materials that unbuilt buildings need but nothing makes yet (e.g. TreatedPlank -> Wood Workshop)."""
    t = tally(world)
    if not t:
        return
    finished, _ = built_names(world)
    by_name = {key(bp): bp for bp in world.blueprints}
    gated: dict[str, list] = {}
    for bp in t["missing"]:
        for good in bp["cost"]:
            makers = MAKERS.get(good, ((), ()))[0]
            if world.good(good)["available"] < bp["cost"][good] and not any(m in finished for m in makers):
                gated.setdefault(good, []).append(bp["name"])
    for good, names in sorted(gated.items(), key=lambda kv: -len(kv[1])):
        chain = []
        makers, feeders = MAKERS.get(good, ((), ()))
        for m in makers[:1] + feeders:
            bp = by_name.get(m)
            if bp and m not in finished:
                chain.append(f"{m} ({'unlocked' if bp['unlocked'] else str(bp['science']) + ' SP'})")
        yield Finding("progress.tech_path", "info", f"{good}: nothing makes it yet; it gates {len(names)} buildings "
                      f"({names[:5]}); next: {', '.join(chain) or 'see knowledge/09'}", good,
                      evidence={"gates": names})
