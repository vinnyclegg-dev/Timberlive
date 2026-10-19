"""Short helpers for one-liners: `from h import *`.
find("FarmHouse", 74, 44) -> building dict; ids("Pump") -> list of (x, y, id).
safe_plant("Oak", x0, y0, x1, y1, (x, y, z)) -> plant only moist, reachable tiles."""
import json
import os
import urllib.request

import timberlive_mcp as t

FOREMAN = os.environ.get("FOREMAN_URL", "http://127.0.0.1:8097")


def foreman_check(actions, quiet_ok=True):
    """Advisory pre-check of harness calls by the Foreman service (python -m foreman serve); it never touches
    the game. Prints Foreman's summary when it finds problems; silent and returns None when Foreman is not
    running. actions: call strings or {"call": ..., ...} dicts, in the order they will run."""
    body = json.dumps({"actions": list(actions)}).encode()
    req = urllib.request.Request(FOREMAN + "/api/validate", body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1.5) as r:
            res = json.loads(r.read())
    except Exception:
        return None
    if not quiet_ok or res.get("critical") or res.get("warn"):
        print(res.get("text", ""))
    return res


def _place_call(template, x, y, z, o=0, good=None):
    a = {"call": "place_building", "template": template, "x": x, "y": y, "z": z, "orientation": o}
    return {**a, "good": good} if good else a


def buildings(filter=""):
    data = json.loads(t.list_buildings(filter))
    return data["buildings"] if isinstance(data, dict) else data


def find(name, x, y):
    return next(b for b in buildings(name) if b["x"] == x and b["y"] == y)


def ids(name):
    return [(b["x"], b["y"], b["id"]) for b in buildings(name)]


def safe_plant(plant, x0, y0, x1, y1, frm, skip_occupied=True):
    """plant_area, then unmark every tile that is not moist soil (water or dry) or that
    beavers can't walk to from frm=(x, y, z), e.g. the planter's doorstep. Returns the skipped tiles."""
    foreman_check([{"call": "safe_plant", "plant": plant, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "frm": list(frm)}])
    w, hgt = x1 - x0 + 1, y1 - y0 + 1
    lines = t.view_map(x0, y0, w, hgt).splitlines()
    h0 = lines.index("HEIGHTS:") + 1
    H = [list(map(int, l.split())) for l in lines[h0:h0 + hgt]]
    m0 = next(i for i, l in enumerate(lines) if l.startswith("MOISTURE")) + 1
    M = [l.strip("|") for l in lines[m0:m0 + hgt]]
    top = y0 + hgt - 1  # view_map rows run from the top y down
    tiles = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    moist = [(x, y) for x, y in tiles if M[top - y][x - x0] == "#"]
    bad = [(x, y, "not moist") for x, y in tiles if (x, y) not in moist]
    if skip_occupied:  # don't overwrite crops, trees, bushes or buildings already on the tile
        o0 = next(i for i, l in enumerate(lines) if l.startswith("OBJECTS")) + 1
        O = [l.strip("|") for l in lines[o0:o0 + hgt]]
        occ = [(x, y) for x, y in moist if O[top - y][x - x0] != " "]
        bad += [(x, y, "occupied") for x, y in occ]
        moist = [p for p in moist if p not in occ]
    # A dry riverbed after a drought looks like moist, walkable soil but floods again:
    # skip anything lower than the planter's own level.
    low = [(x, y) for x, y in moist if H[top - y][x - x0] < frm[2]]
    bad += [(x, y, "below planter level (riverbed?)") for x, y in low]
    moist = [p for p in moist if p not in low]
    d = json.loads(t.walk_distance(*frm, [[x, y, H[top - y][x - x0]] for x, y in moist]))["distances"]
    bad += [(x, y, "unreachable") for (x, y), dist in zip(moist, d) if dist is None]
    t.plant_area(plant, x0, y0, x1, y1)
    for x, y, _ in bad:
        t.clear_planting(x, y, x, y)
    return bad


def path_tiles():
    """Every (x, y) with a Path on it, from a single list_buildings call."""
    return {(b["x"], b["y"]) for b in json.loads(t.list_buildings()) if b["template"] == "Path"}


def is_path(x, y):
    return any(o["template"] == "Path" for o in json.loads(t.inspect_tile(x, y))["objects"])


_ENTRANCES = {}


def door_tile(template, x, y, o):
    """Doorstep of a building placed at pivot (x, y) with orientation o, worked out without placing it."""
    if not _ENTRANCES:
        d = t.list_blueprints()
        d = json.loads(d) if isinstance(d, str) else d
        for b in (d if isinstance(d, list) else d.get("blueprints", d)):
            _ENTRANCES[b["template"]] = b.get("entrance")
    e = _ENTRANCES.get(template)
    if not e:
        return None
    lx, ly = e
    return [(x + lx, y + ly), (x + ly, y - lx), (x - lx, y - ly), (x - ly, y + lx)][o % 4]


def place_on_path(template, cands, z=15, good=None):
    """Place once at the first (x, y, ori) that passes check AND whose doorstep is already a Path.
    No trial placements (viewers saw buildings appear and vanish)."""
    short = template.split(".")[0]
    paths = path_tiles()  # one call instead of inspect_tile per candidate
    for x, y, o in cands:
        door = door_tile(template, x, y, o)
        if not door or tuple(door) not in paths:
            continue
        if not json.loads(t.place_building(template, x, y, z, orientation=o, check=True))["ok"]:
            continue
        foreman_check([_place_call(template, x, y, z, o, good)])
        t.place_building(template, x, y, z, orientation=o)
        b = [b for b in buildings(short) if (b["x"], b["y"]) == (x, y)]
        if b and good:
            t.building_action(b[0]["id"], "SingleGoodAllower", "Allow", [good])
        return b[0] if b else None
    return None


def road_spots(x0=66, x1=100):
    """Candidate spots along the main road y153 (south side ori0, north side ori2)."""
    return [(x, 154, 0) for x in range(x0, x1)] + [(x, 152, 2) for x in range(x0, x1)] + \
           [(x, 155, 0) for x in range(x0, x1)] + [(x, 151, 2) for x in range(x0, x1)]


def door_spots(template, near, radius=12):
    """Every (x, y, ori) whose doorstep lands on an existing Path within radius of near, nearest first."""
    door_tile(template, 0, 0, 0)  # loads entrances
    e = _ENTRANCES.get(template)
    if not e:
        return []
    lx, ly = e
    offs = [(lx, ly), (ly, -lx), (-lx, -ly), (-ly, lx)]
    paths = [p for p in path_tiles() if abs(p[0] - near[0]) + abs(p[1] - near[1]) <= radius]
    paths.sort(key=lambda p: abs(p[0] - near[0]) + abs(p[1] - near[1]))
    return [(px - dx, py - dy, o) for px, py in paths for o, (dx, dy) in enumerate(offs)]


def place_near(template, near, radius=10, z=15, good=None):
    """Place once with its doorstep one tile off an existing Path; adds that one Path tile.
    Checks only (no trial placements). Returns the building or None."""
    door_tile(template, 0, 0, 0)
    e = _ENTRANCES.get(template)
    if not e:
        return None
    lx, ly = e
    offs = [(lx, ly), (ly, -lx), (-lx, -ly), (-ly, lx)]
    paths = path_tiles()
    doors = {(px + dx, py + dy) for px, py in paths for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
             if abs(px - near[0]) + abs(py - near[1]) <= radius} - paths
    ok = lambda tp, x, y, o=0: json.loads(t.place_building(tp, x, y, z, orientation=o, check=True))["ok"]
    for dx_, dy_ in sorted(doors, key=lambda d: abs(d[0] - near[0]) + abs(d[1] - near[1])):
        if not ok("Path", dx_, dy_):
            continue
        for o, (ox, oy) in enumerate(offs):
            x, y = dx_ - ox, dy_ - oy
            if ok(template, x, y, o):
                foreman_check([_place_call("Path", dx_, dy_, z), _place_call(template, x, y, z, o, good)])
                t.place_building(template, x, y, z, orientation=o)
                t.place_building("Path", dx_, dy_, z)
                b = [b for b in buildings(template.split(".")[0]) if (b["x"], b["y"]) == (x, y)]
                if b and good:
                    t.building_action(b[0]["id"], "SingleGoodAllower", "Allow", [good])
                return b[0] if b else None
    return None


def place_with_route(template, cands, z=15, max_len=4):
    """Place at the first (x, y, ori) that checks OK and whose doorstep can be joined to the nearest
    Path by a straight/L run of at most max_len new Path tiles (all checked first). Places once."""
    paths = path_tiles()
    ok = lambda tp, x, y, o=0: json.loads(t.place_building(tp, x, y, z, orientation=o, check=True))["ok"]
    for x, y, o in cands:
        d = door_tile(template, x, y, o)
        if not d or not ok(template, x, y, o):
            continue
        p = min(paths, key=lambda p: abs(p[0] - d[0]) + abs(p[1] - d[1]))
        xs = range(min(d[0], p[0]), max(d[0], p[0]) + 1)
        ys = range(min(d[1], p[1]), max(d[1], p[1]) + 1)
        for route in ([(i, d[1]) for i in xs] + [(p[0], j) for j in ys], [(d[0], j) for j in ys] + [(i, p[1]) for i in xs]):
            route = [r for r in dict.fromkeys(route) if r not in paths]
            if len(route) <= max_len and all(ok("Path", *r) for r in route):
                foreman_check([_place_call("Path", r[0], r[1], z) for r in reversed(route)] +
                              [_place_call(template, x, y, z, o)])
                t.place_building(template, x, y, z, orientation=o)
                for r in route:
                    t.place_building("Path", r[0], r[1], z)
                b = [b for b in buildings(template.split(".")[0]) if (b["x"], b["y"]) == (x, y)]
                return b[0] if b else None
    return None


def path_check(start=(73, 69)):
    """Path tiles (built or planned) not linked to the district doorstep `start` by other path tiles.
    Run after every path placement; a gap (e.g. a tile still blocked by a tree) leaves the far end cut off."""
    P = set(map(tuple, path_tiles()))
    seen, st = {tuple(start)}, [tuple(start)]
    while st:
        x, y = st.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in P and n not in seen:
                seen.add(n)
                st.append(n)
    return sorted(P - seen)


def place_scan(template, near, radius=10, z=5, good=None, limit=40):
    """One scan_spots call around `near`; place at the closest spot whose door is on a Path, or one tile
    off a Path (that door tile gets a Path). Sets the storage good. Returns the building or None."""
    paths = {(p[0], p[1]) for p in path_tiles()}
    adj = lambda x, y: any((x + dx, y + dy) in paths for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    x0, y0 = near
    spots = t.scan_spots(template, z, x0 - radius, y0 - radius, x0 + radius, y0 + radius)["buildable"]
    spots = [s for s in spots if s.get("door") and (tuple(s["door"][:2]) in paths or adj(*s["door"][:2]))]
    if spots:  # drop doors beavers can't walk to (a door on an isolated path or pit; S2E1 c8)
        dist = json.loads(t.walk_distance(73, 69, 5, [s["door"] for s in spots]))["distances"]
        spots = [s for s, d in zip(spots, dist) if d]
    spots.sort(key=lambda s: (tuple(s["door"][:2]) not in paths, abs(s["x"] - x0) + abs(s["y"] - y0)))
    for s in spots[:limit]:
        d = s["door"]
        on_path = tuple(d[:2]) in paths
        if not on_path and not json.loads(t.place_building("Path", d[0], d[1], d[2], check=True))["ok"]:
            continue
        foreman_check(([] if on_path else [_place_call("Path", *d)]) +
                      [_place_call(template, s["x"], s["y"], z, s["orientation"], good)])
        r = json.loads(t.place_building(template, s["x"], s["y"], z, orientation=s["orientation"]))
        if not r.get("ok"):
            continue
        if not on_path:
            t.place_building("Path", d[0], d[1], d[2])
        b = next((b for b in buildings() if b["template"] == template and b["x"] == s["x"] and b["y"] == s["y"]), None)
        if b and good:
            t.building_action(b["id"], "SingleGoodAllower", "Allow", [good])
        return b
    return None
