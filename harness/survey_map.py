"""Whole-map survey: what the map is made of and what "map under control" means on it.

Usage: python survey_map.py [scan | summary | goals | overview | terraces | links | features | water |
                             badwater | farmland | resources] [--refresh]
  scan      rescan the live game (about 16 bridge calls plus nav checks; never moves the camera), then summary
  summary   short text map summary from the cache (rescans if there is no cache or --refresh)
  goals     "map under control" checklist (always rescans: water and buildings change)
  overview  coarse ASCII map, north at the top

The cache (harness/cache/map-survey.json) keeps history across scans of the same map: the deepest and
shallowest water and the worst contamination seen on every tile. Scan during a drought and a badtide
to learn where the river dries up and how far badwater reaches.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter, deque
from pathlib import Path

import timberlive_mcp as t

CACHE = Path(__file__).parent / "cache" / "map-survey.json"
SUMMARY_TXT = Path(__file__).parent / "cache" / "map-summary.txt"
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHUNK = 64

TREES = ("Pine", "Birch", "Oak", "Maple", "ChestnutTree", "Mangrove")
BUSHES = ("BlueberryBush", "CoffeeBush", "Dandelion")
CROPS = ("Kohlrabi", "Cassava", "Carrot", "Potato", "Wheat", "Sunflower", "Soybean", "Corn", "Eggplant",
         "Canola", "Spadderdock", "Cattail", "Succulent")
RUINS = ("RuinColumn", "UndergroundRuins")
GATES = ("Dam", "Levee", "Floodgate", "Sluice")
CONNECTORS = ("Slope", "Stairs", "SpiralStairs")
MIN_TERRACE = 20        # smaller flat patches are steps, not areas
MAX_CHOKE_WIDTH = 8
NEIGHBOURS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def dec(ch: str) -> int:
    return DIGITS.index(ch) if ch in DIGITS else 0


def base_name(name: str | None) -> str:
    if not name:
        return ""
    return name.replace(" (unfinished)", "").split(".")[0]


def kind(name: str | None) -> str:
    n = base_name(name)
    if not n:
        return ""
    if n.startswith(TREES):
        return "tree"
    if n.startswith(BUSHES):
        return "bush"
    if n.startswith(CROPS):
        return "crop"
    if n.startswith(RUINS):
        return "ruin"
    return "object"


# ---------------------------------------------------------------- scan

def fetch() -> dict:
    size = t._call("GET", "/api/map/size")
    width, height = size["width"], size["height"]
    grid = lambda value: [[value] * width for _ in range(height)]
    top, water, dirt, speed, obj = grid(-1), grid(0), grid(0), grid(0), grid(None)
    flow, moist = grid(" "), grid(" ")
    features, layered, seen = [], [], set()
    for cy in range(0, height, CHUNK):
        for cx in range(0, width, CHUNK):
            w, h = min(CHUNK, width - cx), min(CHUNK, height - cy)
            r = t.map_columns(cx, cy, w, h)
            legend = r["legend"]
            for j in range(h):
                y = cy + j
                for i in range(w):
                    x = cx + i
                    ch = r["top"][j][i]
                    if ch == ".":
                        continue
                    top[y][x] = dec(ch)
                    wc = r["water"][j][i]
                    if wc != " ":
                        water[y][x] = max(1, dec(wc))
                        dirt[y][x] = dec(r["contamination"][j][i])
                        speed[y][x] = dec(r["speed"][j][i])
                        flow[y][x] = r["flow"][j][i]
                    moist[y][x] = r["moist"][j][i]
                    oc = r["objects"][j][i]
                    obj[y][x] = legend.get(oc) if oc != " " else None
            for f in r["features"]:
                key = (f["name"], f["x"], f["y"], f["z"])
                if key not in seen:
                    seen.add(key)
                    features.append(f)
            layered += r["layered"]
    state = t._call("GET", "/api/state")
    buildings = json.loads(t.list_buildings())
    buildings = buildings["buildings"] if isinstance(buildings, dict) else buildings
    return {
        "width": width, "height": height, "top": top, "water": water, "dirt": dirt, "speed": speed,
        "flow": flow, "moist": moist, "obj": obj, "features": features, "layered": layered,
        "sources": t._call("GET", "/api/map/water-sources"),
        "time": state.get("time", {}), "weather": state.get("weather", {}),
        "districts": state.get("districts", []),
        "buildings": [{k: b.get(k) for k in ("template", "x", "y", "z", "orientation", "finished", "pathTile")}
                      for b in buildings],
        "scannedAt": time.strftime("%Y-%m-%d %H:%M"),
    }


def merge_history(data: dict, old: dict | None) -> None:
    """Keep the extremes seen on this map: max/min water depth and max contamination per tile."""
    same = (old and old.get("width") == data["width"] and old.get("height") == data["height"]
            and similarity(old["top"], data["top"]) > 0.9)
    if same:
        hist = old["history"]
        for y in range(data["height"]):
            for x in range(data["width"]):
                hist["maxWater"][y][x] = max(hist["maxWater"][y][x], data["water"][y][x])
                hist["minWater"][y][x] = min(hist["minWater"][y][x], data["water"][y][x])
                hist["maxDirt"][y][x] = max(hist["maxDirt"][y][x], data["dirt"][y][x])
        hist["scans"].append({"at": data["scannedAt"], "time": data["time"], "weather": data["weather"]})
        hist["scans"] = hist["scans"][-30:]
    else:
        hist = {"maxWater": [row[:] for row in data["water"]], "minWater": [row[:] for row in data["water"]],
                "maxDirt": [row[:] for row in data["dirt"]],
                "scans": [{"at": data["scannedAt"], "time": data["time"], "weather": data["weather"]}]}
    data["history"] = hist


def similarity(a, b) -> float:
    total = same = 0
    for ra, rb in zip(a, b):
        for va, vb in zip(ra, rb):
            total += 1
            same += va == vb
    return same / max(1, total)


# ---------------------------------------------------------------- analysis helpers

class Map:
    def __init__(self, d: dict):
        self.d = d
        self.W, self.H = d["width"], d["height"]
        self.top, self.water, self.dirt, self.obj = d["top"], d["water"], d["dirt"], d["obj"]

    def inside(self, x, y):
        return 0 <= x < self.W and 0 <= y < self.H and self.top[y][x] >= 0

    def wet(self, x, y):
        return self.inside(x, y) and self.water[y][x] > 0

    def land(self, x, y):
        return self.inside(x, y) and self.water[y][x] == 0

    def free(self, x, y):
        """Land a beaver can stand on: empty or only plants."""
        return self.land(x, y) and kind(self.obj[y][x]) in ("", "crop", "bush", "tree")

    def nearest_free(self, x, y, radius=8):
        for r in range(radius + 1):
            best = None
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    nx, ny = x + dx, y + dy
                    if self.free(nx, ny) and not self.obj[ny][nx]:
                        dist = dx * dx + dy * dy
                        if best is None or dist < best[0]:
                            best = (dist, nx, ny)
            if best:
                return best[1], best[2]
        return None


def components(m: Map, cells_ok, same) -> list[list[tuple[int, int]]]:
    seen = [[False] * m.W for _ in range(m.H)]
    out = []
    for y in range(m.H):
        for x in range(m.W):
            if seen[y][x] or not cells_ok(x, y):
                continue
            comp, queue = [], deque([(x, y)])
            seen[y][x] = True
            while queue:
                cx, cy = queue.popleft()
                comp.append((cx, cy))
                for dx, dy in NEIGHBOURS4:
                    nx, ny = cx + dx, cy + dy
                    if m.inside(nx, ny) and not seen[ny][nx] and cells_ok(nx, ny) and same(cx, cy, nx, ny):
                        seen[ny][nx] = True
                        queue.append((nx, ny))
            out.append(comp)
    return out


def bbox(cells):
    xs, ys = [c[0] for c in cells], [c[1] for c in cells]
    return [min(xs), min(ys), max(xs), max(ys)]


def centre_cell(cells):
    cx = sum(c[0] for c in cells) / len(cells)
    cy = sum(c[1] for c in cells) / len(cells)
    return min(cells, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)


def nav(start, targets):
    out = []
    for i in range(0, len(targets), 400):
        try:
            out += t.reachable(start, targets[i:i + 400])["distances"]
        except t.BridgeError:
            out += [None] * len(targets[i:i + 400])
    return out


def find_base(m: Map):
    for b in m.d["buildings"]:
        if base_name(b["template"]) == "DistrictCenter" and b.get("pathTile"):
            return b["pathTile"]
    if m.d["districts"]:
        dc = m.d["districts"][0]
        spot = m.nearest_free(dc["x"], dc["y"]) or (dc["x"], dc["y"])
        return [spot[0], spot[1], m.top[spot[1]][spot[0]]]
    x, y = m.nearest_free(m.W // 2, m.H // 2, 30) or (m.W // 2, m.H // 2)
    return [x, y, m.top[y][x]]


# ---------------------------------------------------------------- analysis

def analyse(d: dict, use_nav: bool = True) -> dict:
    m = Map(d)
    base = find_base(m)
    a = {"base": base}

    # Terraces: 4-connected dry tiles of equal height.
    comps = components(m, m.land, lambda x0, y0, x1, y1: m.top[y0][x0] == m.top[y1][x1])
    label = [[-1] * m.W for _ in range(m.H)]
    terraces = []
    for comp in sorted(comps, key=len, reverse=True):
        tid = len(terraces)
        for x, y in comp:
            label[y][x] = tid
        kinds = Counter(kind(m.obj[y][x]) for x, y in comp)
        moist_free = [(x, y) for x, y in comp
                      if d["moist"][y][x] == "#" and kind(m.obj[y][x]) in ("", "crop")]
        sample = centre_cell([c for c in comp if not m.obj[c[1]][c[0]]] or comp)
        terraces.append({
            "id": tid, "z": m.top[comp[0][1]][comp[0][0]], "tiles": len(comp), "bbox": bbox(comp),
            "sample": [sample[0], sample[1]], "moistFree": len(moist_free),
            "moistBbox": bbox(moist_free) if moist_free else None,
            "trees": kinds["tree"], "bushes": kinds["bush"], "crops": kinds["crop"], "ruins": kinds["ruin"],
            "buildings": kinds["object"],
        })
    big = [tr for tr in terraces if tr["tiles"] >= MIN_TERRACE]
    a["terraces"] = terraces

    # Reach from the base for every big terrace (one nav call per 400 terraces).
    if use_nav:
        dists = nav(base, [[tr["sample"][0], tr["sample"][1], tr["z"]] for tr in big])
        for tr, dist in zip(big, dists):
            tr["walk"] = dist

    # Links between neighbouring big terraces. Terrain is made of whole blocks: a height change can
    # only be walked through a natural Slope or a built Stairs/ramp/platform, so reach decides status:
    # both sides reachable = linked, one side = frontier (build stairs here), neither = not explored.
    big_ids = {tr["id"] for tr in big}
    boundary: dict[tuple[int, int], list] = {}
    for y in range(m.H):
        for x in range(m.W):
            ta = label[y][x]
            if ta not in big_ids:
                continue
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if not m.inside(nx, ny):
                    continue
                tb = label[ny][nx]
                if tb in big_ids and tb != ta:
                    key = (min(ta, tb), max(ta, tb))
                    pair = ((x, y), (nx, ny)) if ta < tb else ((nx, ny), (x, y))
                    boundary.setdefault(key, []).append(pair)
    connectors = {(f["x"], f["y"]): f for f in d["features"] if base_name(f["name"]).startswith(CONNECTORS)}
    links = []
    for (ta, tb), pairs in boundary.items():
        A, B = terraces[ta], terraces[tb]
        link = {"a": ta, "b": tb, "dz": abs(A["z"] - B["z"]), "border": len(pairs)}
        via = {(c["x"], c["y"]): c for pair in pairs for p in pair
               for c in [connectors.get((p[0] + dx, p[1] + dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1)] if c}
        if via:
            link["via"] = [{"name": base_name(v["name"]), "x": v["x"], "y": v["y"], "z": v["z"],
                            "orientation": v["orientation"]} for v in list(via.values())[:3]]
        ra, rb = A.get("walk") is not None, B.get("walk") is not None
        if "walk" in A or "walk" in B:
            link["status"] = "linked" if ra and rb else "frontier" if ra or rb else "unexplored"
        if link.get("status") != "linked" and not via:
            link["stairs"] = stairs_spot(m, label, pairs, ta, tb, A["z"], B["z"])
        links.append(link)
    a["links"] = links

    # Water bodies.
    bodies = components(m, m.wet, lambda *_: True)
    wlabel = [[-1] * m.W for _ in range(m.H)]
    water_bodies = []
    for comp in sorted(bodies, key=len, reverse=True):
        bid = len(water_bodies)
        for x, y in comp:
            wlabel[y][x] = bid
        depths = [m.water[y][x] for x, y in comp]
        dirty = sum(1 for x, y in comp if m.dirt[y][x] > 0)
        edge = [(x, y) for x, y in comp if x in (0, m.W - 1) or y in (0, m.H - 1)]
        moving = sum(1 for x, y in comp if d["flow"][y][x] not in ("o", " "))
        water_bodies.append({
            "id": bid, "tiles": len(comp), "bbox": bbox(comp), "maxDepth": max(depths) / 10,
            "avgDepth": round(sum(depths) / len(depths) / 10, 2), "dirtyTiles": dirty,
            "flowing": moving, "mapEdge": bbox(edge) if edge else None, "sources": [],
            "deepest": [comp[depths.index(max(depths))][0], comp[depths.index(max(depths))][1]],
        })
    for i, s in enumerate(d["sources"]):
        s["index"] = i
        bid = -1
        for y in range(s["minY"] - 1, s["maxY"] + 2):
            for x in range(s["minX"] - 1, s["maxX"] + 2):
                if m.inside(x, y) and wlabel[y][x] >= 0:
                    bid = wlabel[y][x]
        s["body"] = bid
        if bid >= 0:
            water_bodies[bid]["sources"].append(i)
    a["waterBodies"] = water_bodies
    a["sources"] = d["sources"]

    # River distance from the nearest source (lower = upstream). Clean sources lead, so a badwater
    # spring joining downstream doesn't flip the order of the clean river; badDist ranks badwater.
    def river_bfs(groups):
        dist = [[-1] * m.W for _ in range(m.H)]
        for seeds in groups:
            queue = deque()
            for s in seeds:
                for y in range(s["minY"] - 1, s["maxY"] + 2):
                    for x in range(s["minX"] - 1, s["maxX"] + 2):
                        if m.wet(x, y) and dist[y][x] < 0:
                            dist[y][x] = 0
                            queue.append((x, y))
            while queue:
                x, y = queue.popleft()
                for dx, dy in NEIGHBOURS4:
                    nx, ny = x + dx, y + dy
                    if m.wet(nx, ny) and dist[ny][nx] < 0:
                        dist[ny][nx] = dist[y][x] + 1
                        queue.append((nx, ny))
        return dist
    clean_src = [s for s in d["sources"] if s["contamination"] <= 0.5]
    bad_src = [s for s in d["sources"] if s["contamination"] > 0.5]
    rdist = river_bfs([clean_src, bad_src])
    a["_baddist"] = river_bfs([bad_src])
    a["_rdist"] = rdist
    a["_wlabel"] = wlabel
    a["_label"] = label

    # Choke points: narrow cross-sections of moving water with banks on both sides.
    chokes = []
    for horizontal in (True, False):
        outer = range(m.H) if horizontal else range(m.W)
        for o in outer:
            run = []
            length = m.W if horizontal else m.H
            for i in range(length + 1):
                x, y = (i, o) if horizontal else (o, i)
                if i < length and m.wet(x, y):
                    run.append((x, y))
                    continue
                if run and len(run) <= MAX_CHOKE_WIDTH:
                    choke = make_choke(m, d, run, horizontal, rdist, a["_baddist"], wlabel)
                    if choke:
                        chokes.append(choke)
                run = []
    for c in chokes:
        c["bodyTiles"] = water_bodies[c["body"]]["tiles"] if c["body"] >= 0 else 0
    chokes = [c for c in chokes if c["bodyTiles"] >= 30]
    chokes.sort(key=lambda c: (c["width"], -c["damHeight"], -c["bodyTiles"]))
    kept = []
    for c in chokes:
        if all(max(abs(c["mid"][0] - k["mid"][0]), abs(c["mid"][1] - k["mid"][1])) > 5 for k in kept):
            kept.append(c)
    kept.sort(key=lambda c: (-c["bodyTiles"], c["width"], -c["damHeight"]))
    per_body = Counter()
    a["chokes"] = [c for c in kept if (per_body.update([c["body"]]) or per_body[c["body"]] <= 30)]

    # Deep still pools (pumps, reservoirs).
    pools = components(m, lambda x, y: m.wet(x, y) and m.water[y][x] >= 8, lambda *_: True)
    a["pools"] = [{"tiles": len(p), "bbox": bbox(p), "maxDepth": max(m.water[y][x] for x, y in p) / 10,
                   "body": wlabel[p[0][1]][p[0][0]]} for p in sorted(pools, key=len, reverse=True)[:10]]

    # Badwater now and ever seen.
    hist = d.get("history", {})
    ever = hist.get("maxDirt", m.dirt)
    bad_now = [(x, y) for y in range(m.H) for x in range(m.W) if m.wet(x, y) and m.dirt[y][x] > 0]
    bad_ever = [(x, y) for y in range(m.H) for x in range(m.W) if ever[y][x] > 0]
    threatened = Counter()
    for x, y in bad_ever:
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                nx, ny = x + dx, y + dy
                if m.inside(nx, ny) and label[ny][nx] in big_ids:
                    threatened[label[ny][nx]] += 1
    a["badwater"] = {"now": len(bad_now), "nowBbox": bbox(bad_now) if bad_now else None,
                     "ever": len(bad_ever), "everBbox": bbox(bad_ever) if bad_ever else None,
                     "terracesNear": threatened.most_common(8)}

    # Drought behaviour from history: tiles that were wet but dried out.
    if hist:
        dried = sum(1 for y in range(m.H) for x in range(m.W)
                    if hist["maxWater"][y][x] > 0 and hist["minWater"][y][x] == 0)
        a["driesOut"] = dried

    # Resources: clusters with a gap of up to 2 tiles.
    resources = {}
    for k in ("tree", "bush", "ruin"):
        cells = {(x, y) for y in range(m.H) for x in range(m.W) if kind(m.obj[y][x]) == k}
        clusters = cluster(cells, 2)
        out = []
        for c in sorted(clusters, key=len, reverse=True)[:12]:
            cx, cy = centre_cell(c)
            species = Counter(base_name(m.obj[y][x]) for x, y in c)
            spot = m.nearest_free(cx, cy)
            out.append({"count": len(c), "bbox": bbox(c), "centre": [cx, cy], "species": dict(species.most_common(4)),
                        "standOn": [spot[0], spot[1], m.top[spot[1]][spot[0]]] if spot else None})
        resources[k] = out
    if use_nav:
        targets = [c["standOn"] for k in resources for c in resources[k] if c["standOn"]]
        dists = iter(nav(base, targets))
        for k in resources:
            for c in resources[k]:
                c["walk"] = next(dists) if c["standOn"] else None
    a["resources"] = resources
    return a


def cluster(cells: set, gap: int) -> list[list[tuple[int, int]]]:
    left, out = set(cells), []
    while left:
        start = left.pop()
        comp, queue = [start], deque([start])
        while queue:
            x, y = queue.popleft()
            for dy in range(-gap, gap + 1):
                for dx in range(-gap, gap + 1):
                    n = (x + dx, y + dy)
                    if n in left:
                        left.remove(n)
                        comp.append(n)
                        queue.append(n)
        out.append(comp)
    return out


def stairs_spot(m: Map, label, pairs, ta, tb, za, zb):
    """A boundary spot for Stairs: stand on the low tile, step up onto the high tile.
    The tile behind the stairs (entry) must be low ground too."""
    for (pa, pb) in pairs[len(pairs) // 3:] + pairs[:len(pairs) // 3]:
        low, high = (pa, pb) if za < zb else (pb, pa)
        dx, dy = high[0] - low[0], high[1] - low[1]
        entry = (low[0] - dx, low[1] - dy)
        if not (m.free(*low) and m.free(*high) and m.free(*entry)):
            continue
        if m.top[entry[1]][entry[0]] != m.top[low[1]][low[0]] or m.obj[low[1]][low[0]]:
            continue
        return {"stairsAt": [low[0], low[1], m.top[low[1]][low[0]]], "enterFrom": list(entry),
                "exitOnto": [high[0], high[1], m.top[high[1]][high[0]]], "levels": abs(za - zb)}
    return None


def make_choke(m: Map, d: dict, run, horizontal: bool, rdist, baddist, wlabel):
    # The run must cross the flow: a row-run blocks north/south flow, a column-run east/west flow.
    flows = Counter(d["flow"][y][x] for x, y in run)
    across = flows["^"] + flows["v"] if horizontal else flows["<"] + flows[">"]
    along = flows["<"] + flows[">"] if horizontal else flows["^"] + flows["v"]
    if across == 0 and along == 0:
        # Still (dammed) water: a choke if water carries on both sides of the run's middle.
        mx, my = run[len(run) // 2]
        side = [(mx, my - 1), (mx, my + 1)] if horizontal else [(mx - 1, my), (mx + 1, my)]
        if not all(m.wet(*c) for c in side):
            return None
    elif across < along:
        return None
    (x0, y0), (x1, y1) = run[0], run[-1]
    ends = [(x0 - 1, y0), (x1 + 1, y1)] if horizontal else [(x0, y0 - 1), (x1, y1 + 1)]
    if not all(m.land(*e) for e in ends):
        return None
    bed = min(m.top[y][x] for x, y in run)
    surface = max(m.top[y][x] + m.water[y][x] / 10 for x, y in run)
    banks = [m.top[e[1]][e[0]] for e in ends]
    if min(banks) < math.ceil(surface):
        return None
    body = wlabel[y0][x0]
    rd = [rdist[y][x] for x, y in run if rdist[y][x] >= 0]
    bd = [baddist[y][x] for x, y in run if baddist[y][x] >= 0]
    return {
        "from": [x0, y0], "to": [x1, y1], "mid": list(run[len(run) // 2]), "width": len(run),
        "line": "x" if horizontal else "y", "bed": bed, "surface": round(surface, 1), "banks": banks,
        "damHeight": min(banks) - bed, "body": body, "bodyTiles": 0 if body < 0 else 1,
        "riverDist": min(rd) if rd else -1, "badDist": min(bd) if bd else -1,
        "speed": round(sum(d["speed"][y][x] for x, y in run) / len(run) / 10, 2),
        "dirty": sum(m.dirt[y][x] for x, y in run) / len(run) >= 3,
    }


# ---------------------------------------------------------------- goals

def source_groups(sources) -> list[dict]:
    """Merge touching source tiles (maps often build one spring from several 1-tile sources)."""
    groups = []
    for s in sources:
        for g in groups:
            if (g["bad"] == (s["contamination"] > 0.5) and s["minX"] <= g["maxX"] + 1 and s["maxX"] >= g["minX"] - 1
                    and s["minY"] <= g["maxY"] + 1 and s["maxY"] >= g["minY"] - 1):
                g["minX"], g["maxX"] = min(g["minX"], s["minX"]), max(g["maxX"], s["maxX"])
                g["minY"], g["maxY"] = min(g["minY"], s["minY"]), max(g["maxY"], s["maxY"])
                g["tiles"] += s["tiles"]
                g["strength"] += s["currentStrength"] * s["tiles"]
                g["full"] += s["specifiedStrength"] * s["tiles"]
                g["members"].append(s)
                break
        else:
            groups.append({"minX": s["minX"], "maxX": s["maxX"], "minY": s["minY"], "maxY": s["maxY"],
                           "z": s["z"], "tiles": s["tiles"], "bad": s["contamination"] > 0.5,
                           "strength": s["currentStrength"] * s["tiles"], "full": s["specifiedStrength"] * s["tiles"],
                           "body": s["body"], "members": [s]})
    return groups


def area(b) -> str:
    return f"x{b[0]}-{b[2]} y{b[1]}-{b[3]}" if b[0] != b[2] or b[1] != b[3] else f"({b[0]},{b[1]})"


def straight(a, x, y) -> float:
    return math.hypot(a["base"][0] - x, a["base"][1] - y)


def tname(tr) -> str:
    return f"T{tr['id']} z{tr['z']} {area(tr['bbox'])}"


def frontier(a) -> list[dict]:
    """Links from a reachable terrace to one that isn't: the next stairs to build, nearest first."""
    out = []
    for ln in a["links"]:
        if ln.get("status") != "frontier":
            continue
        A, B = a["terraces"][ln["a"]], a["terraces"][ln["b"]]
        near, far = (A, B) if A.get("walk") is not None else (B, A)
        spot = ln.get("stairs")
        sx, sy = (spot["stairsAt"][0], spot["stairsAt"][1]) if spot else (far["sample"][0], far["sample"][1])
        out.append({**ln, "near": near, "far": far, "dist": straight(a, sx, sy)})
    out.sort(key=lambda f: (f["dist"] - min(f["far"]["tiles"], 600) / 20))
    return out


def goals(d: dict, a: dict) -> list[tuple[bool, str]]:
    m = Map(d)
    rdist, wlabel = a["_rdist"], a["_wlabel"]
    builds = [b for b in d["buildings"] if b.get("finished")]
    gate_cells = {(x, y) for y in range(m.H) for x in range(m.W) if base_name(m.obj[y][x]).startswith(GATES)}
    gate_cells |= {(b["x"], b["y"]) for b in builds if base_name(b["template"]).startswith(GATES)}
    out = []

    # 1. Badwater sources capped, or their badwater kept in its own channel (one line per water body).
    by_body = {}
    for g in source_groups(a["sources"]):
        if g["bad"]:
            by_body.setdefault(g["body"], []).append(g)
    for body, gs in by_body.items():
        spread = max(bad_spread(m, s) for g in gs for s in g["members"])
        live = [g for g in gs if g["strength"] > 0.01]
        tiles = sum(g["tiles"] for g in gs)
        ok = not live or spread <= max(12, 3 * tiles)
        where = ", ".join(f"{area([g['minX'], g['minY'], g['maxX'], g['maxY']])} z{g['z']}" for g in gs)
        out.append((ok, f"Badwater source{'s' if len(gs) > 1 else ''} {where} (W{body}): "
                        + ("capped" if not live else f"badwater covers {spread} tiles; cap it or levee it "
                                                     "into its own channel away from clean water")))

    # 2. Clean water by the base held from both sides: a gate downstream (keeps a pool in droughts)
    #    and one upstream (a reservoir, and a floodgate line against incoming badwater).
    gate_rd = []
    for x, y in gate_cells:
        near = [(wlabel[y + dy][x + dx], rdist[y + dy][x + dx]) for dy in range(-2, 3) for dx in range(-2, 3)
                if m.inside(x + dx, y + dy) and rdist[y + dy][x + dx] >= 0]
        if near:
            gate_rd.append(min(near, key=lambda n: n[1]))
    w = nearest_water(m, a["base"][0], a["base"][1], 25)
    if w:
        body, rd = wlabel[w[1]][w[0]], rdist[w[1]][w[0]]
        local = [c for c in a["chokes"] if c["body"] == body and not c["dirty"] and straight(a, *c["mid"]) <= 40]
        for side, test in (("downstream", lambda r: r > rd), ("upstream", lambda r: 0 <= r < rd)):
            ok = any(gb == body and test(grd) for gb, grd in gate_rd)
            best = sorted((c for c in local if test(c["riverDist"])), key=lambda c: (-c["damHeight"], c["width"]))
            tip = (f"best spot {best[0]['from']}-{best[0]['to']} width {best[0]['width']} holds {best[0]['damHeight']}"
                   if best else "no narrow spot within 40 tiles; use a levee line")
            out.append((ok, f"Base water W{body} gated {side}: " + ("yes" if ok else f"no ({tip})")))

    # 3. Every farm's water held by a gate upstream of it.
    farms = [b for b in builds if base_name(b["template"]) == "FarmHouse"]
    bad = []
    for f in farms:
        fw = nearest_water(m, f["x"], f["y"], 20)
        if not fw:
            bad.append(f"({f['x']},{f['y']}) has no water within 20")
        elif not any(gb == wlabel[fw[1]][fw[0]] and grd <= rdist[fw[1]][fw[0]] for gb, grd in gate_rd):
            bad.append(f"({f['x']},{f['y']}) water at {list(fw)}")
    if farms:
        out.append((not bad, f"Farm water held upstream for {len(farms) - len(bad)}/{len(farms)} FarmHouses"
                             + (": missing " + "; ".join(bad) if bad else "")))

    # 4. Valuable terraces walkable from the base (nearest 8 that have farmland, trees or ruins).
    worth = [tr for tr in a["terraces"] if "walk" in tr and tr["tiles"] >= 100
             and (tr["moistFree"] >= 50 or tr["trees"] >= 40 or tr["ruins"] or tr["bushes"] >= 20)]
    worth.sort(key=lambda tr: straight(a, *tr["sample"]))
    for tr in worth[:8]:
        ok = tr["walk"] is not None
        what = ", ".join(e for e in (f"{tr['moistFree']} moist" if tr["moistFree"] >= 50 else "",
                                     f"{tr['trees']} trees" if tr["trees"] >= 40 else "",
                                     f"{tr['bushes']} bushes" if tr["bushes"] >= 20 else "",
                                     "ruins" if tr["ruins"] else "") if e)
        out.append((ok, f"Reach {tname(tr)} ({what}): " + ("walkable" if ok else "not linked yet")))
    rest = [tr for tr in worth[8:] if tr["walk"] is None]
    if rest:
        out.append((False, f"... and {len(rest)} more valuable terraces not linked yet"))

    # 5. Ruins reachable with a Scavenger Flag in range.
    flags = [b for b in builds if base_name(b["template"]).startswith("ScavengerFlag")]
    for r in [r for r in a["resources"].get("ruin", []) if r["count"] >= 10]:
        cx, cy = r["centre"]
        flagged = any(abs(f["x"] - cx) + abs(f["y"] - cy) <= 12 for f in flags)
        ok = r.get("walk") is not None and flagged
        out.append((ok, f"Ruins {area(r['bbox'])} ({r['count']} columns): "
                        + ("reachable" if r.get("walk") is not None else "not reachable")
                        + (", Scavenger Flag in range" if flagged else ", no Scavenger Flag")))
    return out


def bad_spread(m: Map, s) -> int:
    queue = deque((x, y) for y in range(s["minY"] - 1, s["maxY"] + 2) for x in range(s["minX"] - 1, s["maxX"] + 2)
                  if m.wet(x, y) and m.dirt[y][x] > 0)
    seen = set(queue)
    while queue:
        x, y = queue.popleft()
        for dx, dy in NEIGHBOURS4:
            n = (x + dx, y + dy)
            if n not in seen and m.wet(*n) and m.dirt[n[1]][n[0]] > 0:
                seen.add(n)
                queue.append(n)
    return len(seen)


def line_cells(c):
    (x0, y0), (x1, y1) = c["from"], c["to"]
    return [(x, y0) for x in range(x0, x1 + 1)] if c["line"] == "x" else [(x0, y) for y in range(y0, y1 + 1)]


def nearest_water(m: Map, x, y, radius):
    best = None
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if m.wet(x + dx, y + dy):
                dist = dx * dx + dy * dy
                if best is None or dist < best[0]:
                    best = (dist, x + dx, y + dy)
    return (best[1], best[2]) if best else None


# ---------------------------------------------------------------- text output

def fmt_walk(v):
    return "not linked" if v is None else f"walk {v:.0f}"


def describe(tr) -> str:
    extra = [f"moist {tr['moistFree']}" if tr["moistFree"] else "", f"trees {tr['trees']}" if tr["trees"] else "",
             f"bushes {tr['bushes']}" if tr["bushes"] else "", f"ruins {tr['ruins']}" if tr["ruins"] else "",
             f"built {tr['buildings']}" if tr["buildings"] else ""]
    return f"{tname(tr)} {tr['tiles']} tiles, {fmt_walk(tr.get('walk'))}; " + ", ".join(e for e in extra if e)


def section_terraces(d, a):
    big = [tr for tr in a["terraces"] if tr["tiles"] >= MIN_TERRACE]
    reach = [tr for tr in big if tr.get("walk") is not None]
    lines = [f"TERRACES (flat dry areas of one height z; {len(big)} of {MIN_TERRACE}+ tiles, {len(reach)} walkable "
             "from base):", "  Walkable now:"]
    lines += [f"    {describe(tr)}" for tr in sorted(reach, key=lambda tr: tr["walk"])[:10]]
    others = sorted((tr for tr in big if tr.get("walk") is None and tr["tiles"] >= 100),
                    key=lambda tr: straight(a, *tr["sample"]))
    lines.append("  Not linked yet, nearest first:")
    lines += [f"    {describe(tr)}" for tr in others[:10]]
    zs = [tr["z"] for tr in big]
    lines.append(f"  Heights z{min(zs)}-{max(zs)}; +{len(a['terraces']) - len(big)} patches under {MIN_TERRACE} tiles")
    return lines


def section_links(d, a):
    links = a["links"]
    linked = [ln for ln in links if ln.get("status") == "linked"]
    lines = ["LINKS (block terrain: height changes need a natural Slope or built Stairs; dams/levees cross water):",
             f"  {len(linked)} links already walkable, {sum(1 for ln in links if ln.get('status') == 'frontier')} "
             "frontier edges. Next stairs to open new ground (nearest first):"]
    for f in frontier(a)[:8]:
        s = f"    {tname(f['near'])} -> {tname(f['far'])} ({f['far']['tiles']} tiles), {f['dz']} level(s): "
        st = f.get("stairs")
        if f.get("via"):
            v = f["via"][0]
            s += f"{v['name']} at ({v['x']},{v['y']},{v['z']}) is on this edge but not walkable yet (path it?)"
        elif st:
            s += f"Stairs on {st['stairsAt']}, walk on from {st['enterFrom']}, step off onto {st['exitOnto']}"
            if st["levels"] > 1:
                s += f" ({st['levels']} levels: stack stairs on platforms)"
        else:
            s += "no clean stairs spot on this border"
        lines.append(s)
    slopes = [ln for ln in links if ln.get("via") and any(v["name"] == "Slope" for v in ln["via"])]
    if slopes:
        lines.append("  Natural Slopes join: " + "; ".join(
            f"T{ln['a']} z{a['terraces'][ln['a']]['z']}-T{ln['b']} z{a['terraces'][ln['b']]['z']} at "
            + ",".join(f"({v['x']},{v['y']})" for v in ln["via"] if v["name"] == "Slope")
            + f" [{ln.get('status', '?')}]" for ln in slopes[:10]))
    return lines


def section_features(d, a):
    groups = {}
    for f in d["features"]:
        n = base_name(f["name"])
        if n.startswith(("DistrictCenter", "Dam", "Levee", "Floodgate", "Platform", "Stairs", "Tubeway", "Zipline",
                         "WaterSource", "BadwaterSource")):
            continue
        spot = f"({f['x']},{f['y']},{f['z']}" + (f" o{f['orientation']})" if n == "Slope" else ")")
        groups.setdefault("RuinColumn" if n.startswith("RuinColumn") else n, []).append(spot)
    lines = ["NATURAL MAP OBJECTS (water sources are under WATER, ruin clusters under RESOURCES):"]
    for n, spots in sorted(groups.items()):
        if n == "RuinColumn":
            lines.append(f"  RuinColumn x{len(spots)} (scrap metal; see RESOURCES)")
            continue
        lines.append(f"  {n} x{len(spots)}: " + " ".join(spots[:10]) + (" ..." if len(spots) > 10 else ""))
    multi = d["layered"]
    if multi:
        near = sorted(multi, key=lambda c: straight(a, c["x"], c["y"]))[:3]
        lines.append(f"  Multi-level columns (overhangs/caves/ground under ledges): {len(multi)}; nearest "
                     + " ".join(f"({c['x']},{c['y']}) levels {[lv[0] for lv in c['levels']]}" for c in near))
    return lines


def section_water(d, a):
    lines = ["WATER:"]
    for g in source_groups(a["sources"]):
        lines.append(f"  {'BADWATER' if g['bad'] else 'Water'} source {area([g['minX'], g['minY'], g['maxX'], g['maxY']])}"
                     f" z{g['z']} ({g['tiles']} tiles) output {g['strength']:.1f}/{g['full']:.1f} -> W{g['body']}")
    for b in a["waterBodies"][:5]:
        lines.append(f"  W{b['id']} {b['tiles']} tiles {area(b['bbox'])} depth max {b['maxDepth']} avg {b['avgDepth']}, "
                     f"{b['dirtyTiles']} badwater tiles" + (f", leaves map at {area(b['mapEdge'])}" if b["mapEdge"] else ""))
    if a["pools"]:
        lines.append("  Deep water (0.8+, pump spots): " + "; ".join(
            f"{area(p['bbox'])} max {p['maxDepth']}"
            for p in sorted(a["pools"], key=lambda p: straight(a, p["bbox"][0], p["bbox"][1]))[:4]))
    clean = sorted((c for c in a["chokes"] if not c["dirty"]), key=lambda c: straight(a, *c["mid"]))[:6]
    dirty = sorted((c for c in a["chokes"] if c["dirty"]), key=lambda c: c["badDist"] if c["badDist"] >= 0 else 9999)[:4]
    lines.append("  Clean river chokes, nearest base first (dam/levee/floodgate lines; 'holds' = bank height above bed):")
    lines += [f"    {c['from']}-{c['to']} width {c['width']} bed z{c['bed']} banks {c['banks']} holds {c['damHeight']} "
              f"flow {c['speed']} ({straight(a, *c['mid']):.0f} from base)" for c in clean] or ["    none"]
    lines.append("  Badwater chokes nearest their source (to contain or divert badwater):")
    lines += [f"    {c['from']}-{c['to']} width {c['width']} bed z{c['bed']} banks {c['banks']} holds {c['damHeight']}"
              for c in dirty] or ["    none"]
    if a.get("driesOut"):
        lines.append(f"  {a['driesOut']} tiles were wet in one scan and dry in another (drought losses)")
    return lines


def section_badwater(d, a):
    bw = a["badwater"]
    lines = [f"BADWATER: {bw['now']} tiles now" + (f" ({area(bw['nowBbox'])})" if bw["nowBbox"] else "")
             + f"; {bw['ever']} tiles ever seen"]
    for b in [b for b in a["waterBodies"] if 0 < b["dirtyTiles"] < b["tiles"]][:3]:
        lines.append(f"  W{b['id']} is mixed: {b['dirtyTiles']} of {b['tiles']} tiles carry badwater")
    if bw["terracesNear"]:
        lines.append("  Land within 2 tiles of badwater: " + ", ".join(
            tname(a["terraces"][i]) for i, _ in bw["terracesNear"][:5]))
    scans = d.get("history", {}).get("scans", [])
    hazards = sorted({s["weather"].get("hazard") or "" for s in scans if s.get("weather", {}).get("state") == "hazardous"})
    lines.append(f"  Scans: {len(scans)}; during hazards: {', '.join(h for h in hazards if h) or 'none yet'} "
                 "(rescan in a badtide to learn its reach)")
    return lines


def section_farmland(d, a):
    rows = sorted((tr for tr in a["terraces"] if tr["moistFree"] >= 20),
                  key=lambda tr: (tr.get("walk") is None, straight(a, *tr["sample"])))[:8]
    lines = ["FARMLAND (moist, flat, free or crops), walkable first:"]
    lines += [f"  {tname(tr)}: {tr['moistFree']} tiles in {area(tr['moistBbox'])} ({fmt_walk(tr.get('walk'))})"
              for tr in rows] or ["  none moist yet: hold water beside flat land with a dam or levee"]
    return lines


def section_resources(d, a):
    lines = ["RESOURCES (clusters, nearest base first):"]
    for k, title, cut in (("tree", "Trees", 20), ("bush", "Bushes", 10), ("ruin", "Ruins", 10)):
        items = sorted((c for c in a["resources"].get(k, []) if c["count"] >= cut),
                       key=lambda c: straight(a, *c["centre"]))[:5]
        for c in items:
            sp = ", ".join(f"{n.replace('RuinColumn', 'H')} {v}" for n, v in c["species"].items())
            lines.append(f"  {title}: {c['count']} at {area(c['bbox'])} ({sp}) {fmt_walk(c.get('walk'))}, "
                         f"{straight(a, *c['centre']):.0f} from base")
    return lines


def section_goals(d, a):
    items = goals(d, a)
    done = sum(1 for ok, _ in items if ok)
    return [f"MAP UNDER CONTROL {done}/{len(items)}:"] + [f"  [{'x' if ok else ' '}] {text}" for ok, text in items]


def section_overview(d, a):
    m = Map(d)
    f = max(1, math.ceil(max(m.W, m.H) / 64))
    bx, by = a["base"][0], a["base"][1]
    lines = [f"OVERVIEW 1 char = {f}x{f} tiles, north (high y) at top. digits/letters = height, ~ water, "
             "! badwater, T forest, R ruins, S natural slope, B base"]
    slopes = {(f["x"], f["y"]) for f in d["features"] if base_name(f["name"]) == "Slope"}
    for yb in range((m.H - 1) // f, -1, -1):
        row = []
        for xb in range(0, (m.W + f - 1) // f):
            cells = [(x, y) for y in range(yb * f, min(m.H, yb * f + f)) for x in range(xb * f, min(m.W, xb * f + f))
                     if m.inside(x, y)]
            if not cells:
                row.append(" ")
                continue
            if any(x == bx and y == by for x, y in cells):
                row.append("B")
            elif any(c in slopes for c in cells):
                row.append("S")
            elif sum(m.wet(x, y) for x, y in cells) * 2 >= len(cells):
                dirty = sum(m.wet(x, y) and m.dirt[y][x] >= 3 for x, y in cells)
                row.append("!" if dirty * 2 >= sum(m.wet(x, y) for x, y in cells) else "~")
            elif any(kind(m.obj[y][x]) == "ruin" for x, y in cells):
                row.append("R")
            elif sum(kind(m.obj[y][x]) == "tree" for x, y in cells) * 2 >= len(cells):
                row.append("T")
            else:
                hs = sorted(m.top[y][x] for x, y in cells)
                row.append(DIGITS[hs[len(hs) // 2]])
        lines.append("".join(row))
    return lines


SECTIONS = {
    "terraces": section_terraces, "links": section_links, "features": section_features, "water": section_water,
    "badwater": section_badwater, "farmland": section_farmland, "resources": section_resources,
    "goals": section_goals, "overview": section_overview,
}
SUMMARY = ("terraces", "links", "features", "water", "badwater", "farmland", "resources", "goals")


# ---------------------------------------------------------------- entry points

def load(refresh: bool = False) -> tuple[dict, dict]:
    old = json.loads(CACHE.read_text()) if CACHE.exists() else None
    if refresh or old is None:
        data = fetch()
        merge_history(data, old)
        analysis = analyse(data)
        data["analysis"] = {k: v for k, v in analysis.items() if not k.startswith("_")}
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(data, separators=(",", ":")))
        return data, analysis
    # Cached: recompute the grids-only parts, reuse nav results.
    analysis = analyse(old, use_nav=False)
    cached = old.get("analysis", {})
    for tr, ctr in zip(analysis["terraces"], cached.get("terraces", [])):
        if "walk" in ctr:
            tr["walk"] = ctr["walk"]
    analysis["links"] = cached.get("links", analysis["links"])
    for k in analysis["resources"]:
        for c, cc in zip(analysis["resources"][k], cached.get("resources", {}).get(k, [])):
            c["walk"] = cc.get("walk")
    return old, analysis


def report(refresh: bool = False, section: str = "") -> str:
    data, analysis = load(refresh or section == "goals")
    head = [f"MAP {data['width']}x{data['height']}, scanned {data['scannedAt']} (cycle {data['time'].get('cycle')} "
            f"day {data['time'].get('cycleDay')}, {data['weather'].get('state')}); base path tile {analysis['base']}"]
    names = [section] if section else list(SUMMARY)
    lines = head
    for n in names:
        if n not in SECTIONS:
            return f"Unknown section '{n}'. Use one of: {', '.join(SECTIONS)}"
        lines += SECTIONS[n](data, analysis)
    text = "\n".join(lines)
    if not section:
        SUMMARY_TXT.write_text(text, encoding="utf-8")
    return text


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    refresh = "--refresh" in sys.argv
    cmd = args[0] if args else "summary"
    if cmd == "scan":
        print(report(refresh=True))
    elif cmd == "summary":
        print(report(refresh=refresh))
    else:
        print(report(refresh=refresh, section=cmd))


if __name__ == "__main__":
    main()
