"""Study saved games and map files without loading them (they are zip files holding world.json).

    save_study.py list                         newest save of every settlement, biggest first
    save_study.py study "<settlement>" [file]  one save in detail: hazards, population, buildings, ratios, layout
    save_study.py timeline "<settlement>"      every save of a settlement: when each building first appeared
    save_study.py maps                         every built-in and user map: size, sources, natural objects

Used to learn how an experienced player built a colony, and which maps hold the objects worth testing.
Read-only: never writes into the game folders.
"""
import base64
import collections
import glob
import io
import json
import os
import sys
import zipfile

GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Timberborn\Timberborn_Data\StreamingAssets"
DOCS = os.path.expanduser("~/Documents/Timberborn")
SAVE_ROOTS = [os.path.join(DOCS, "ExperimentalSaves"), os.path.join(DOCS, "Saves")]

# Ratios worth comparing per 100 beavers.
KEY = ["FarmHouse", "AquaticFarmhouse", "HydroponicGarden", "GathererFlag", "Fermenter", "FoodFactory", "Grill",
       "Gristmill", "Bakery", "DeepWaterPump", "WaterPump", "MechanicalWaterPump", "LargeTank", "MediumTank",
       "SmallTank", "LumberjackFlag", "Forester", "IndustrialLumberMill", "LumberMill", "GearWorkshop",
       "Barrack", "Rowhouse", "Lodge", "BreedingPod", "AdvancedBreedingPod", "LargeWarehouse", "MediumWarehouse",
       "SmallWarehouse", "LargeIndustrialPile", "SmallIndustrialPile", "BuildersHut", "HaulingPost",
       "DistrictCenter", "Dam", "Levee", "Floodgate", "Sluice", "ImpermeableFloor", "Tubeway", "TubewayStation",
       "Platform", "Stairs", "SpiralStairs", "LargeWaterWheel", "CompactWaterWheel", "SteamEngine",
       "LargePowerWheel", "PowerWheel", "WindTurbine", "LargeWindTurbine"]


def base(template: str) -> str:
    return template.split(".")[0]


def categories() -> dict:
    """Template base name -> category ("Buildings/Food", "NaturalResources/Crops", "MapEditor/Objects"...)."""
    out = {}
    with zipfile.ZipFile(os.path.join(GAME, "Modding", "Blueprints.zip")) as z:
        for p in z.namelist():
            if p.endswith(".blueprint.json") and p.startswith(("Buildings/", "NaturalResources/", "MapEditor/")):
                name = base(os.path.basename(p))
                out.setdefault(name, "/".join(p.split("/")[:2]))
    out.setdefault("BlueberryBush", "NaturalResources/Bushes")
    out.setdefault("ChestnutTree", "NaturalResources/Trees")
    return out


def read(path_or_bytes):
    z = zipfile.ZipFile(io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes)
    names = z.namelist()
    meta = json.loads(z.read("save_metadata.json")) if "save_metadata.json" in names else (
        json.loads(z.read("map_metadata.json")) if "map_metadata.json" in names else {})
    return json.loads(z.read("world.json")), meta


def settlements():
    for root in SAVE_ROOTS:
        if not os.path.isdir(root):
            continue
        for s in sorted(os.listdir(root)):
            files = sorted(glob.glob(os.path.join(root, s, "*.timber")), key=os.path.getmtime)
            if files:
                yield s, root, files


def finished(e) -> bool:
    return "ConstructionSite" not in e["Components"]


def counts(world, cat, only_finished=True):
    c = collections.Counter()
    for e in world["Entities"]:
        n = base(e["Template"])
        if cat.get(n, "").startswith("Buildings/") and (finished(e) or not only_finished):
            c[n] += 1
    return c


def population(world):
    c = collections.Counter(base(e["Template"]) for e in world["Entities"])
    return c["BeaverAdult"], c["BeaverChild"], c["Bot"]


def header(world, meta):
    S = world["Singletons"]
    cyc = S.get("GameCycleService", {})
    a, k, b = population(world)
    mapname = S.get("MapNameService", {}).get("Name") or meta.get("MapName")
    size = S.get("MapSize", {}).get("Size", {})
    # Easy refunds 90% on demolish, Normal and Hard 75%; Hard droughts are 15-30 days.
    rate = S.get("GoodRecoveryRateService", {}).get("DemolishableRecoveryRate")
    longest = max([h["Duration"] for h in S.get("HazardousWeatherHistory", {}).get("HistoryData", [])] or [0])
    mode = "Easy" if rate == 0.9 else ("Hard" if longest > 12 else "Normal") if rate == 0.75 else f"rate {rate}"
    return (f"map {mapname} {size.get('X')}x{size.get('Y')}, {mode}, faction {S.get('FactionService', {}).get('Id')}, "
            f"cycle {cyc.get('Cycle')} day {cyc.get('CycleDay')}, beavers {a}+{k} kits, bots {b}, "
            f"mods {[m.get('Id', m) if isinstance(m, dict) else m for m in meta.get('Mods', [])]}")


def cmd_list():
    cat = categories()
    rows = []
    for s, root, files in settlements():
        try:
            w, meta = read(files[-1])
        except Exception as ex:  # noqa: BLE001
            print(f"{s}: unreadable ({ex})")
            continue
        a, k, b = population(w)
        rows.append((a + k, s, os.path.basename(root), len(files), header(w, meta), len(counts(w, cat))))
    for pop, s, root, n, head, kinds in sorted(rows, reverse=True):
        print(f"{s} [{root}, {n} saves]: {head}; {kinds} building kinds")


def hazards(world):
    hist = world["Singletons"].get("HazardousWeatherHistory", {}).get("HistoryData", [])
    out = collections.defaultdict(list)
    for h in hist:
        out[h["HazardousWeatherId"].replace("Weather", "")].append(h["Duration"])
    return dict(out)


def cmd_study(name, file=None):
    cat = categories()
    files = next((f for s, _, f in settlements() if s == name), None)
    if not files:
        sys.exit(f"no settlement {name!r}")
    path = next((f for f in files if file and file in os.path.basename(f)), files[-1])
    if file and file[0] == "c" and file[1:].isdigit():  # "c4" = the earliest save from cycle 4 on
        dated = []
        for f in files:
            with zipfile.ZipFile(f) as z:
                cyc = json.loads(z.read("save_metadata.json")) if "save_metadata.json" in z.namelist() else {}
            dated.append(((cyc.get("Cycle", 0), cyc.get("Day", 0)), f))
        path = min((d for d in dated if d[0][0] >= int(file[1:])), default=max(dated))[1]
    w, meta = read(path)
    S = w["Singletons"]
    a, k, b = population(w)
    pop = max(1, a + k + b)
    print(f"{name}: {os.path.basename(path)}")
    print("  " + header(w, meta))
    hz = hazards(w)
    print("  hazards so far: " + "; ".join(f"{h} x{len(v)} lengths {v}" for h, v in hz.items()))
    print(f"  work hours {S.get('WorkingHoursManager', {}).get('WorkedPartOfDay', 0) * 24:.0f} h, science "
          f"{S.get('ScienceService', {}).get('SciencePoints')}, trees planted {S.get('TreePlantingCounter', {}).get('PlantedCount')}")
    built = counts(w, cat)
    unfinished = counts(w, cat, False) - built
    bycat = collections.defaultdict(list)
    for n, v in built.most_common():
        bycat[cat[n].split("/")[1]].append(f"{n} {v}")
    print(f"  buildings ({sum(built.values())} finished, {sum(unfinished.values())} under construction):")
    for c in sorted(bycat):
        print(f"    {c}: " + ", ".join(bycat[c]))
    print("  per 100 beavers: " + ", ".join(f"{n} {built[n] * 100 / pop:.1f}" for n in KEY if built[n]))
    nat = collections.Counter(base(e["Template"]) for e in w["Entities"]
                              if cat.get(base(e["Template"]), "").startswith("NaturalResources/"))
    crops = {n: v for n, v in nat.items() if cat[n].endswith("Crops")}
    print(f"  crops {crops}; per beaver {sum(crops.values()) / pop:.1f} plots")
    print("  trees " + str({n: v for n, v in nat.items() if cat[n].endswith("Trees")})
          + "; bushes " + str({n: v for n, v in nat.items() if cat[n].endswith("Bushes")}))
    # Settings players choose: workplace priorities, farmhouse planting first, worker counts.
    prio = collections.Counter()
    plant_first = 0
    for e in w["Entities"]:
        comp = e["Components"]
        if "WorkplacePriority" in comp:
            prio[(base(e["Template"]), comp["WorkplacePriority"].get("Priority"))] += 1
        if comp.get("FarmHouse", {}).get("PlantingPrioritized"):
            plant_first += 1
    print("  non-normal workplace priorities: " + ", ".join(f"{n} {p} x{v}" for (n, p), v in sorted(prio.items())))
    print(f"  farmhouses set to plant first: {plant_first}")
    layout(w, cat)


def layout(w, cat):
    """Where things are: building heights (how vertical the base is) and the main clusters."""
    zs = collections.Counter()
    pts = []
    for e in w["Entities"]:
        n = base(e["Template"])
        bo = e["Components"].get("BlockObject")
        if not bo or not cat.get(n, "").startswith("Buildings/"):
            continue
        c = bo["Coordinates"]
        if cat[n] not in ("Buildings/Paths",):
            zs[c["Z"]] += 1
        pts.append((c["X"], c["Y"], c["Z"], n))
    if not pts:
        return
    print("  building heights z:count " + " ".join(f"{z}:{v}" for z, v in sorted(zs.items())))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    print(f"  built area x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)}")
    stacked = collections.Counter((p[0], p[1]) for p in pts if cat.get(p[3]) != "Buildings/Paths")
    print(f"  tiles with 2+ buildings stacked: {sum(1 for v in stacked.values() if v > 1)}")


def cmd_timeline(name):
    cat = categories()
    files = next((f for s, _, f in settlements() if s == name), None)
    if not files:
        sys.exit(f"no settlement {name!r}")
    seen = {}
    rows = []
    for f in files:
        try:
            w, _ = read(f)
        except Exception:  # noqa: BLE001
            continue
        cyc = w["Singletons"].get("GameCycleService", {})
        when = (cyc.get("Cycle", 0), cyc.get("CycleDay", 0))
        built = counts(w, cat)
        a, k, b = population(w)
        rows.append((when, a + k, built))
    rows.sort(key=lambda r: r[0])
    for when, pop, built in rows:
        new = [n for n in built if n not in seen]
        for n in new:
            seen[n] = when
        key = ", ".join(f"{n} {built[n]}" for n in KEY if built[n])
        print(f"c{when[0]}d{when[1]} beavers {pop}: {key}")
        if new:
            print(f"   new: {', '.join(sorted(new))}")


def cmd_maps():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import timberlive_mcp as t  # noqa: E402
    cat = categories()
    opts = json.loads(t.new_game_options())
    maps = [(m, True) for m in opts["builtinMaps"] if not m.startswith("_")] + [(m, False) for m in opts["userMaps"]]
    for name, builtin in maps:
        try:
            raw = t._call("GET", "/api/maps/file", params={"name": name, "builtin": str(builtin).lower()})
            w, meta = read(base64.b64decode(raw["base64"]))
        except Exception as ex:  # noqa: BLE001
            print(f"{name}: unreadable ({ex})")
            continue
        size = w["Singletons"].get("MapSize", {}).get("Size", {})
        c = collections.Counter(base(e["Template"]) for e in w["Entities"])
        objs = {n: v for n, v in c.items() if cat.get(n, "").startswith("MapEditor/") and not n.startswith("RuinColumn")}
        ruins = sum(v for n, v in c.items() if n.startswith("RuinColumn"))
        trees = sum(v for n, v in c.items() if cat.get(n, "").endswith("Trees"))
        print(f"{name}{'' if builtin else ' (user)'} {size.get('X')}x{size.get('Y')}: trees {trees}, ruin columns {ruins}, "
              + ", ".join(f"{n} {v}" for n, v in sorted(objs.items())))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "list":
        cmd_list()
    elif args[0] == "study":
        cmd_study(args[1], args[2] if len(args) > 2 else None)
    elif args[0] == "timeline":
        cmd_timeline(args[1])
    elif args[0] == "maps":
        cmd_maps()
    else:
        print(__doc__)
