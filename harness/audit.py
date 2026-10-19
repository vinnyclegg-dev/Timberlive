"""Daily building/job audit (plan v4 section 5) - zero tokens, safe fixes only.

Usage: python audit.py [--no-fix]
watch.py also calls audit() at the end of every report.
Safe fixes: unmark emptying on food/water stores (emptying them starts famines).
Everything else is only reported; decisions stay with the player.
"""

import json
import sys
from pathlib import Path

import timberlive_mcp as t

FOOD_JOBS = ("FarmHouse", "GathererFlag", "Fermenter", "FoodFactory", "HydroponicGarden", "Grill",
             "Bakery", "DeepWaterPump", "WaterPump", "MechanicalWaterPump", "AquaticFarmhouse")
FOOD_STORE_GOODS = {"Water", "Berries", "Kohlrabi", "Corn", "Mushroom", "Cassava", "Soybean", "Eggplant",
                    "Potato", "Carrot", "Wheat", "Algae", "FermentedCassava", "FermentedSoybean",
                    "FermentedMushroom", "CornRation", "EggplantRation", "AlgaeRation", "GrilledPotato", "Bread"}
# Nominal power use (hp) from knowledge/09-buildings.md (game blueprints). Demand reads 0 outside work hours,
# so the audit compares supply with these figures instead of the live demand.
POWER_USE = {"IndustrialLumberMill": 75, "GearWorkshop": 120, "Smelter": 200, "FoodFactory": 120, "Fermenter": 50,
             "OilPress": 50, "WoodWorkshop": 250, "CoffeeBrewery": 200, "Centrifuge": 200, "DeepMechanicalPump": 500,
             "AquiferDrill": 400, "Numbercruncher": 500, "CompactMechanicalPump": 700}
SITE_AGE = Path(__file__).parent / "cache" / "site-age.json"


def short(b):
    return f"{b['template'].split('.')[0]}({b['x']},{b['y']})"


def game_day(colony):
    tm = colony["time"]
    return tm["cycle"] * 100 + tm["cycleDay"] + tm.get("dayProgress", 0)


def audit(colony, buildings, fix=True):
    lines = []
    done = [b for b in buildings if b["finished"]]
    pop = colony["population"]

    # Jobs: 0-2 unemployed is the target; key jobs must be staffed first.
    if pop["unemployed"] > 2:
        lines.append(f"JOBS: {pop['unemployed']} unemployed - add a Low-priority builders' hut/hauling post "
                     "or a needed workplace")
    short_staffed = [b for b in done if b.get("workers") and not b.get("paused")
                     and b["workers"]["assigned"] < b["workers"]["desired"]]
    key_short = [short(b) for b in short_staffed if b["template"].startswith(FOOD_JOBS)]
    if key_short:
        lines.append(f"FOOD/WATER JOBS SHORT OF WORKERS: {key_short[:8]}")
    elif short_staffed:
        lines.append(f"short of workers: {[short(b) for b in short_staffed][:8]}")
    paused_food = [short(b) for b in done if b.get("paused") and b["template"].startswith(FOOD_JOBS)]
    if paused_food:
        lines.append(f"PAUSED FOOD/WATER: {paused_food} - check the pause register resume condition")

    # Panel settings: every store needs a good, every recipe building a recipe.
    no_good = [short(b) for b in done if (b.get("setup") or {}).get("good") == ""]
    if no_good:
        lines.append(f"STORE WITH NO GOOD SET: {no_good[:8]}")
    # Tanks report no "good" key at all when unset, so check stores by template too.
    unset = [short(b) for b in done if b["template"].split(".")[0].endswith(("Warehouse", "Pile", "Tank"))
             and not (b.get("setup") or {}).get("good") and short(b) not in no_good]
    if unset:
        lines.append(f"STORE WITH NO GOOD SET: {unset[:8]}")
    # Pumps next to badwater pump badwater (or nothing): flag any contaminated water within 2 tiles.
    badtide = (colony.get("weather") or {}).get("hazard") == "BadtideWeather" and         (colony.get("weather") or {}).get("state") == "hazardous"
    for b in ([] if badtide else done):
        if "Pump" not in b["template"] or "Badwater" in b["template"]:
            continue
        m = t._call("GET", "/api/map", params={"x": b["x"] - 2, "y": b["y"] - 2, "w": 6, "h": 6})
        if any(c in "abcdefghi" for row in m.get("water", []) for c in row):
            lines.append(f"PUMP NEAR BADWATER: {short(b)} - move it to clean water")
    # Power: networks (grouped by live supply) whose consumers need more than the generators give.
    nets = {}
    for b in buildings:
        name = b["template"].split(".")[0]
        if name in POWER_USE and not b.get("paused") and (b.get("power") or not b["finished"]):
            supply = (b.get("power") or {}).get("networkSupply", 0)
            key = supply if b["finished"] else "site"
            nets.setdefault(key, []).append((name, POWER_USE[name], b["finished"]))
    for supply, users in nets.items():
        if supply == "site":
            continue
        need = sum(hp for _, hp, _ in users)
        if need > supply:
            lines.append(f"POWER SHORT: network gives {supply} hp, its machines need {need} hp "
                         f"({', '.join(n for n, _, _ in users)}) - they run at ~{supply * 100 // need}% speed; "
                         "add water wheels")
    planned = sum(hp for _, hp, _ in nets.get("site", []))
    if planned:
        lines.append(f"power: {planned} hp more needed when {[n for n, _, _ in nets['site']]} finish")
    no_recipe = [short(b) for b in done if (b.get("setup") or {}).get("recipe") == ""]
    if no_recipe:
        lines.append(f"NO RECIPE: {no_recipe}")
    for b in done:
        setup = b.get("setup") or {}
        if not setup.get("emptying") or "Flag" in b["template"]:
            continue
        if fix and setup.get("good") in FOOD_STORE_GOODS:
            t.building_action(b["id"], "Emptiable", "UnmarkForEmptying", [])
            lines.append(f"auto: stopped emptying {short(b)} ({setup['good']})")
        else:
            lines.append(f"marked for emptying: {short(b)} ({setup.get('good') or '?'})")

    # Farmhouses: harvest first; with 2+, about 1 in 3 plants first.
    farms = [b for b in done if "plantingFirst" in (b.get("setup") or {})]
    planting = sum(1 for b in farms if b["setup"]["plantingFirst"])
    if farms and (planting > max(1, round(len(farms) / 3)) or (len(farms) == 1 and planting)):
        lines.append(f"farmhouses: {planting}/{len(farms)} planting first - set the rest to harvest first")

    # Status problems grouped (full output, no power, nothing to cut, ...).
    groups = {}
    for b in done:
        for s in b.get("statuses") or []:
            if s != "Paused.":
                groups.setdefault(s, []).append(short(b))
    for s, where in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"status '{s}': {where[:6]}" + (f" +{len(where) - 6}" if len(where) > 6 else ""))

    # Sites stuck at 0% for over a day: almost always a site not on a properly connected path.
    now = game_day(colony)
    try:
        seen = json.loads(SITE_AGE.read_text())
    except (OSError, ValueError):
        seen = {}
    sites = {b["id"]: b for b in buildings if not b["finished"]}
    seen = {i: d for i, d in seen.items() if i in sites and not sites[i].get("buildProgress")}
    for i, b in sites.items():
        if not b.get("buildProgress"):
            seen.setdefault(i, now)
    SITE_AGE.parent.mkdir(exist_ok=True)
    SITE_AGE.write_text(json.dumps(seen))
    stuck = [short(sites[i]) for i, d in seen.items() if now - d >= 1]
    if stuck:
        lines.append(f"SITES AT 0% FOR 1+ DAY: {stuck[:8]} - check the door is on a path linked to the district")

    if colony.get("science", 0) > 500:
        lines.append(f"science {colony['science']} unspent - unlock the next building on the plan")
    return lines


if __name__ == "__main__":
    colony = json.loads(t.get_colony())
    buildings = json.loads(t.list_buildings())
    out = audit(colony, buildings, fix="--no-fix" not in sys.argv)
    print("AUDIT", "ok" if not out else "")
    for line in out:
        print(" -", line)
