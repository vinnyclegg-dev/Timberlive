"""Compact read-only facts for the monitor sub-agents (no game changes).

Usage: python monitor.py production | narration | layout
  production: stocks vs capacity (full/empty), buildings not producing (statuses), power per network.
  narration:  age and text of the last overlay thoughts, the plan, and the live colony state to compare.
  layout:     unfinished sites, free beds/jobs, buildings per template and the cached map survey goals.
"""

import json
import sys
import time
import urllib.request
from collections import Counter

import timberlive_mcp as t


def short(b):
    return f"{b['template'].split('.')[0]}({b['x']},{b['y']})"


def colony_line(c):
    p = c["population"]
    return (f"TIME {c['time']} WEATHER {c.get('weather')} POP adults={p.get('adults')} kits={p.get('children')} "
            f"unemployed={p.get('unemployed')} homeless={p.get('homeless')} sci={c.get('science')}")


# Water used per day by buildings (knowledge/09): pods 1/day; Hydroponic Mushroom 40 per 192 work-h,
# Algae 60 per 288 work-h (~16 work-h/day -> ~3.3/day); Steam Engine 0.3/h (~7.2/day when running);
# Coffee Brewery 1 per 4 coffee/h. Beavers: 2.6/day (measured over droughts 9 and 10).
BUILDING_WATER = {"BreedingPod": 1.0, "HydroponicGarden": 3.3, "SteamEngine": 7.2, "CoffeeBrewery": 12.0}
LONGEST_HAZARD_DAYS = 7


def water_budget(beavers, goods, bs):
    drink = 2.6 * beavers
    per = Counter(b["template"].split(".")[0] for b in bs if b["finished"] and not b.get("paused"))
    build = {k: v * per[k] for k, v in BUILDING_WATER.items() if per[k]}
    use = drink + sum(build.values())
    need = 1.5 * LONGEST_HAZARD_DAYS * use
    w = next((g for g in goods if g["id"] == "Water"), {"available": 0, "capacity": 0})
    print(f"WATER BUDGET {use:.0f}/day = beavers {drink:.0f} + buildings {sum(build.values()):.0f} {build}; "
          f"hazard reserve {need:.0f} vs stock {w['available']}/{w.get('capacity')}"
          f"{' SHORT ' + str(int(need - w['available'])) if w['available'] < need else ' ok'}")


def production():
    c = json.loads(t.get_colony())
    goods = json.loads(t.get_goods())
    bs = json.loads(t.list_buildings())
    print(colony_line(c))
    beavers = c["population"].get("adults", 0) + c["population"].get("children", 0)
    edible = sum(g["available"] for g in goods if g["id"] in ("Berries", "CornRation", "FermentedCassava",
                 "FermentedSoybean", "FermentedMushroom", "GrilledPotato", "Bread", "Kohlrabi", "EggplantRation"))
    print(f"FOOD DAYS {edible / max(1, 3 * beavers):.1f}  water/beaver {next((g['available'] for g in goods if g['id'] == 'Water'), 0) / max(1, beavers):.1f}")
    water_budget(beavers, goods, bs)
    for g in goods:
        cap = g.get("capacity") or 0
        tag = "FULL" if cap and g["available"] >= cap * 0.95 else "EMPTY" if g["available"] == 0 else ""
        print(f"GOOD {g['id']}: {g['available']}/{cap} {tag}")
    done = [b for b in bs if b["finished"]]
    problems = [(short(b), b.get("statuses")) for b in done if [s for s in (b.get("statuses") or []) if s != "Paused."]]
    print("NOT PRODUCING / STATUS:", problems[:25])
    print("PAUSED:", [short(b) for b in done if b.get("paused")])
    nets = {}
    for b in done:
        pw = b.get("power")
        if pw:
            nets.setdefault(pw["networkSupply"], []).append(
                f"{short(b)} out={pw['output']} in={pw['input']} eff={pw['efficiency']}")
    for supply, members in nets.items():
        print(f"POWER NETWORK supply={supply}: {members}")
    print("SITES:", [(short(b), b.get("buildProgress"), b.get("statuses")) for b in bs if not b["finished"]][:20])
    # Long-cycle makers show no status while working; print their batch progress so a silent one is visible
    # (S2E1 c8: user asked why the Hydroponic Garden had produced nothing; it was 76% through a 288 h batch).
    for b in done:
        if b["template"].split(".")[0] in ("HydroponicGarden", "OilPress", "Fermenter", "CoffeeBrewery"):
            comps = json.loads(t.inspect_building(b["id"]))["components"]
            m = next((x["state"] for x in comps if x["component"] == "Manufactory"), {})
            inv = next((x["stock"] for x in comps if x["component"] == "Inventory" and x.get("name") == "Manufactory"), [])
            print(f"BATCH {short(b)} {m.get('CurrentRecipe')} {m.get('ProductionProgress', 0):.0%} "
                  f"inputs={'ok' if m.get('HasAllIngredients') else 'MISSING'} stock={[(i['good'], i['amount']) for i in inv]}")


def narration():
    c = json.loads(t.get_colony())
    state = json.loads(urllib.request.urlopen("http://127.0.0.1:8096/state.json", timeout=5).read())
    now = time.time()
    print(colony_line(c))
    for th in (state.get("thoughts") or [])[-3:]:
        print(f"THOUGHT {int(now - th.get('at', now))}s ago: {th.get('text')}")
    print("PLAN:", [(x.get("text"), x.get("done")) for x in state.get("todos") or []])
    poll = state.get("poll") or {}
    if poll:
        print(f"POLL question={poll.get('question')} closed={poll.get('closed')} "
              f"closes_in={int(poll.get('closes', now) - now)}s")
    goods = json.loads(t.get_goods())
    print("GOODS", {g["id"]: g["available"] for g in goods})
    bs = json.loads(t.list_buildings())
    print("SITES:", [(short(b), b.get("buildProgress")) for b in bs if not b["finished"]][:15])


def layout():
    c = json.loads(t.get_colony())
    bs = json.loads(t.list_buildings())
    print(colony_line(c))
    print("BUILT:", dict(Counter(b["template"].split(".")[0] for b in bs if b["finished"]
                                 and b["template"].split(".")[0] not in ("Path", "Dam", "PowerShaft"))))
    print("SITES:", [short(b) for b in bs if not b["finished"] and not b["template"].startswith("Path")][:25])
    key = [short(b) for b in bs if b["template"].split(".")[0] in ("DistrictCenter", "FarmHouse", "Barrack", "BreedingPod",
           "DeepWaterPump", "IndustrialLumberMill", "GearWorkshop", "Smelter", "FoodFactory", "Metalsmith",
           "LargePowerWheel", "CompactWaterWheel", "Inventor", "Forester", "MediumWarehouse")]
    print("KEY BUILDINGS:", key)


if __name__ == "__main__":
    {"production": production, "narration": narration, "layout": layout}[sys.argv[1] if len(sys.argv) > 1 else "production"]()
