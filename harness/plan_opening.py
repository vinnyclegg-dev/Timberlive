"""Opening planner: works out the whole opening batch in one read-only run while the game is paused.

Usage: python plan_opening.py <spec.json> [--apply]
  (no flag)  read-only: start facts, every road tile and building spot checked in one scan call per
             template, coverage (trees / bushes / plots in work range), log budget. Writes
             cache/start-facts.json and cache/opening-plan.json.
  --apply    on the go-ahead: place the saved plan in its order (roads first), mark cutting areas,
             plant the plot rectangles with h.safe_plant, set storage goods. Re-checks each spot first.

Spec (openings/<map>.json):
  roads:     [[x0,y0,x1,y1,z], ...] straight runs of Path
  buildings: [{"template":"FarmHouse","count":1,"near":[x,y],"radius":10,"z":5,"water":false,"priority":"VeryHigh",
               "range":"plots"|"trees"|"bushes", "good":"Berries", "note":"..."}, ...] in build order
  cut:       [[x0,y0,x1,y1], ...] tree-cutting rectangles
  plant:     [{"plant":"Kohlrabi","rect":[x0,y0,x1,y1],"from":"FarmHouse"}]
  lines:     [{"template":"Dam","tiles":[[x,y],...],"z":4,"note":"..."}] (dams, levees)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import timberlive_mcp as t

HERE = Path(__file__).parent
FACTS = HERE / "cache" / "start-facts.json"
PLAN = HERE / "cache" / "opening-plan.json"
WORK_RANGE = 20           # knowledge/09 "Work ranges": ~20 tiles walking distance
TREES = ("Pine", "Birch", "Oak", "Maple", "ChestnutTree", "Mangrove")
BUSHES = ("BlueberryBush",)


def full(name: str) -> str:
    return name if "." in name or name in ("Path",) else name + ".IronTeeth"


def start_facts() -> dict:
    """Everything a new map needs that I used to look up by hand: templates, sizes, doors, costs."""
    bps = t.list_blueprints()
    bps = json.loads(bps) if isinstance(bps, str) else bps
    bps = bps if isinstance(bps, list) else bps.get("blueprints", bps)
    colony = json.loads(t.get_colony())
    goods = {g["id"]: g["total"] for g in json.loads(t.get_goods(include_empty=True))}
    dc = json.loads(t.list_buildings("DistrictCenter"))[0]
    facts = {
        "blueprints": {b["template"]: {k: b.get(k) for k in ("size", "entrance", "waterInput", "cost",
                                                              "science", "unlocked", "group")} for b in bps},
        "start_goods": {k: v for k, v in goods.items() if v},
        "population": colony.get("population"),
        "time": colony.get("time"),
        "district_center": {"x": dc["x"], "y": dc["y"], "z": dc["z"], "door": dc["pathTile"]},
    }
    FACTS.write_text(json.dumps(facts, indent=1))
    return facts


def load_grid(x0: int, y0: int, x1: int, y1: int) -> dict:
    """(x, y) -> {top, water (tenths), moist, obj} from map_columns (64x64 per call, no camera move)."""
    grid = {}
    for cy in range(y0, y1 + 1, 64):
        for cx in range(x0, x1 + 1, 64):
            w, h = min(64, x1 - cx + 1), min(64, y1 - cy + 1)
            r = t.map_columns(cx, cy, w, h)
            legend = r.get("legend", {})
            for j in range(h):
                for i in range(w):
                    o = r["objects"][j][i]
                    wc = r["water"][j][i]
                    grid[(cx + i, cy + j)] = {
                        "top": int(r["top"][j][i], 36) if r["top"][j][i] != "." else -1,
                        "water": 0 if wc in " ." else int(wc, 36),
                        "moist": r["moist"][j][i],
                        "obj": legend.get(o, "") if o != " " else "",
                    }
    return grid


def road_tiles(roads) -> list[tuple[int, int, int]]:
    tiles = []
    for x0, y0, x1, y1, z in roads:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                if (x, y, z) not in tiles:
                    tiles.append((x, y, z))
    return tiles


def plan(spec: dict) -> dict:
    facts = start_facts()
    dc = facts["district_center"]
    door0 = dc["door"]
    xs = [r[0] for r in spec["roads"]] + [r[2] for r in spec["roads"]] + [b["near"][0] for b in spec["buildings"]]
    ys = [r[1] for r in spec["roads"]] + [r[3] for r in spec["roads"]] + [b["near"][1] for b in spec["buildings"]]
    bx0, by0 = max(0, min(xs) - 30), max(0, min(ys) - 30)
    grid = load_grid(bx0, by0, max(xs) + 30, max(ys) + 30)
    out = {"facts": {k: facts[k] for k in ("start_goods", "population", "time", "district_center")},
           "roads": [], "buildings": [], "problems": [], "lines": [], "cut": spec.get("cut", []),
           "plant": spec.get("plant", [])}

    # Roads: one scan call for every tile; trees/bushes on a road need clearing first.
    roads = road_tiles(spec["roads"])
    road_xy = {(x, y) for x, y, _ in roads}
    by_z = {}
    for x, y, z in roads:
        by_z.setdefault(z, []).append([x, y, 0])
    ok_road = set()
    for z, cands in by_z.items():
        ok_road |= {(b["x"], b["y"]) for b in t.scan_spots("Path", z, candidates=cands)["buildable"]}
    for x, y, z in roads:
        obj = grid.get((x, y), {}).get("obj", "")
        if (x, y) not in ok_road:
            out["problems"].append(f"road tile ({x},{y},{z}) not buildable ({obj or 'terrain/water'})")
        elif obj:
            out["problems"].append(f"road tile ({x},{y}) has {obj}: clear it first")
    out["roads"] = spec["roads"]

    reserved = set(road_xy)
    for item in spec["buildings"]:
        tpl = full(item["template"])
        z = item.get("z", dc["z"])
        nx, ny = item["near"]
        rad = item.get("radius", 10)
        found = t.scan_spots(tpl, z, nx - rad, ny - rad, nx + rad, ny + rad)["buildable"]
        picks = []
        for s in sorted(found, key=lambda s: abs(s["x"] - nx) + abs(s["y"] - ny) if not s["door"]
                        else abs(s["door"][0] - nx) + abs(s["door"][1] - ny)):
            tiles = {tuple(p) for p in s["tiles"]}
            if tiles & reserved:
                continue
            if any(grid.get(p, {}).get("obj") and not grid[p]["obj"].startswith("Path") for p in tiles):
                continue  # don't build on trees, bushes or ruins
            if s["door"] and tuple(s["door"][:2]) not in road_xy:
                continue
            if item.get("water") and not (s["water"] and s["water"]["underwater"]
                                          and s["water"]["contamination"] < 0.1):
                continue
            picks.append(s)
            reserved |= tiles
            if len(picks) >= item.get("count", 1):
                break
        if len(picks) < item.get("count", 1):
            out["problems"].append(f"{tpl}: only {len(picks)}/{item.get('count', 1)} spots near {item['near']}")
        doors = [s["door"] for s in picks if s["door"]]
        dist = json.loads(t.walk_distance(*door0, doors))["distances"] if doors else []
        di = iter(dist)
        for s in picks:
            entry = {"template": tpl, "x": s["x"], "y": s["y"], "z": z, "orientation": s["orientation"],
                     "door": s["door"], "walk_from_dc": next(di) if s["door"] else None,
                     "note": item.get("note", ""), "good": item.get("good"), "priority": item.get("priority")}
            if s.get("water"):
                entry["intake"] = s["water"]
            if item.get("range") and s["door"]:
                entry["in_range"] = coverage(grid, s["door"], item["range"], reserved)
            cost = facts["blueprints"].get(tpl, {}).get("cost") or {}
            entry["cost"] = cost
            out["buildings"].append(entry)

    for ln in spec.get("lines", []):
        tpl = full(ln["template"])
        res = t.scan_spots(tpl, ln["z"], candidates=[[x, y, ln.get("orientation", 0)] for x, y in ln["tiles"]])
        okt = {(b["x"], b["y"]) for b in res["buildable"]}
        bad = [p for p in ln["tiles"] if tuple(p) not in okt]
        cost = facts["blueprints"].get(tpl, {}).get("cost") or {}
        out["lines"].append({"template": tpl, "z": ln["z"], "tiles": ln["tiles"], "not_buildable": bad,
                             "cost_each": cost, "note": ln.get("note", "")})
        if bad:
            out["problems"].append(f"{tpl} line: tiles {bad} not buildable")

    for pl in out["plant"]:
        x0, y0, x1, y1 = pl["rect"]
        pl["moist_free"] = sum(1 for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)
                               if grid.get((x, y), {}).get("moist") == "#" and not grid[(x, y)]["obj"]
                               and (x, y) not in reserved)
    total = {}
    for b in out["buildings"]:
        for g, n in (b["cost"] or {}).items():
            total[g] = total.get(g, 0) + n
    out["cost_buildings"] = total
    out["cost_lines"] = {g: n * len(ln["tiles"]) for ln in out["lines"] for g, n in ln["cost_each"].items()}
    PLAN.write_text(json.dumps(out, indent=1))
    return out


def coverage(grid, door, what, reserved) -> int:
    """How many trees / bushes / free moist tiles are within WORK_RANGE walking tiles of the door."""
    dx, dy, dz = door
    cand = []
    for (x, y), c in grid.items():
        if abs(x - dx) + abs(y - dy) > WORK_RANGE:
            continue
        o = c["obj"]
        if (what == "trees" and o.startswith(TREES)) or (what == "bushes" and o.startswith(BUSHES)) or \
           (what == "plots" and c["moist"] == "#" and not o and (x, y) not in reserved):
            cand.append([x, y, c["top"]])
    n = 0
    for i in range(0, len(cand), 400):
        d = json.loads(t.walk_distance(dx, dy, dz, cand[i:i + 400]))["distances"]
        n += sum(1 for v in d if v is not None and v <= WORK_RANGE)
    return n


def apply() -> None:
    """Place the saved plan (go-ahead only). Roads, then buildings in spec order, then lines."""
    import h
    p = json.loads(PLAN.read_text())
    foreman_batch(p)
    for x0, y0, x1, y1, z in p["roads"]:
        print("road", t.place_line("Path", x0, y0, x1, y1, z))
    for b in p["buildings"]:
        r = json.loads(t.place_building(b["template"], b["x"], b["y"], b["z"], orientation=b["orientation"]))
        print(b["template"], b["x"], b["y"], "ok" if r["ok"] else r)
        if r["ok"] and (b.get("good") or b.get("priority")):
            got = [g for g in h.buildings(b["template"].split(".")[0]) if (g["x"], g["y"]) == (b["x"], b["y"])]
            if got and b.get("good"):
                t.building_action(got[0]["id"], "SingleGoodAllower", "Allow", [b["good"]])
            if got and b.get("priority"):
                t.set_priority(got[0]["id"], b["priority"])
    for x0, y0, x1, y1 in p["cut"]:
        t.mark_tree_cutting(x0, y0, x1, y1)
    for pl in p["plant"]:
        src = next((b for b in p["buildings"] if b["template"].startswith(pl["from"])), None)
        if src:
            print("plant", pl["plant"], len(h.safe_plant(pl["plant"], *pl["rect"], tuple(src["door"]))), "skipped")
    for ln in p["lines"]:
        for x, y in ln["tiles"]:
            t.place_building(ln["template"], x, y, ln["z"])


def foreman_batch(p: dict) -> None:
    """The whole opening batch through Foreman's guards in one call (advisory; silent if Foreman is down)."""
    import h
    acts = [{"call": "place_line", "template": "Path", "x0": x0, "y0": y0, "x1": x1, "y1": y1, "z": z}
            for x0, y0, x1, y1, z in p["roads"]]
    acts += [{"call": "place_building", "template": b["template"], "x": b["x"], "y": b["y"], "z": b["z"],
              "orientation": b["orientation"], **({"good": b["good"]} if b.get("good") else {})} for b in p["buildings"]]
    acts += [{"call": "mark_tree_cutting", "x0": x0, "y0": y0, "x1": x1, "y1": y1} for x0, y0, x1, y1 in p["cut"]]
    acts += [{"call": "place_building", "template": ln["template"], "x": x, "y": y, "z": ln["z"]}
             for ln in p["lines"] for x, y in ln["tiles"]]
    res = h.foreman_check(acts, quiet_ok=False)
    if res is None:
        print("FOREMAN not running: batch not pre-checked (python -m foreman serve)")


def show(out: dict) -> None:
    f = out["facts"]
    print("START", f["start_goods"], f["population"], "DC", f["district_center"])
    print("ROADS", out["roads"])
    for b in out["buildings"]:
        extra = f" intake {b['intake']['x']},{b['intake']['y']} depth {b['intake']['depth']}" if b.get("intake") else ""
        rng = f" in range {b['in_range']}" if "in_range" in b else ""
        print(f"  {b['template'].split('.')[0]:<20} ({b['x']},{b['y']},{b['z']}) o{b['orientation']} door {b['door']}"
              f" walk {b['walk_from_dc']}{extra}{rng} {b['note']}")
    for ln in out["lines"]:
        print(f"  LINE {ln['template']} x{len(ln['tiles'])} z{ln['z']} not buildable {ln['not_buildable']} {ln['note']}")
    for pl in out["plant"]:
        print(f"  PLANT {pl['plant']} {pl['rect']} free moist {pl['moist_free']}")
    print("CUT", out["cut"])
    print("COST buildings", out["cost_buildings"], "lines", out["cost_lines"])
    for pr in out["problems"]:
        print("PROBLEM", pr)


if __name__ == "__main__":
    if "--apply" in sys.argv:
        apply()
    else:
        out = plan(json.loads(Path(sys.argv[1]).read_text()))
    show(out)
    if PLAN.exists():
        foreman_batch(json.loads(PLAN.read_text()))
