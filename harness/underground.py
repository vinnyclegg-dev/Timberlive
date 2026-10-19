"""First-assessment of hidden water and Unstable Cores (run on every new map, before placing anything).

Usage: python underground.py [--refresh] [--json]

1. WATER BODIES in 3D: every wet standing level (caves included) joined to its neighbours where the
   water overlaps. Each body: tiles, floor, head (surface height), contamination, cave share, and
   PRESSURISED tiles (water up to the roof: opening that roof lets the water out).
2. SOURCES CONFIRMED: each source/seep is matched to the body it sits in, then followed downhill
   (spill edges between bodies) so "is this lake fed?" is answered from the map, never guessed.
3. CORES: radius, timer, and what each blast would hit - bodies it would join (different heads or
   badwater), cave roofs it would open to the surface (and how far that water could flood), natural
   dams/blockages/sources/other cores (chain reaction) and buildings in range.
Cache: cache/underground.json (whole-map columns + features, with core/source state).
"""

import json
import math
import sys
from collections import deque
from pathlib import Path

import timberlive_mcp as t

CACHE = Path(__file__).parent / "cache" / "underground.json"
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHUNK = 64
WET = 0.05
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
CENTRE = {0: (1, 1), 1: (1, 0), 2: (0, 0), 3: (0, 1)}  # 2x2 core: pivot -> grid point at its middle


def dec(ch):
    return DIGITS.index(ch) if ch in DIGITS else 0


def fetch():
    size = t._call("GET", "/api/map/size")
    W, H = size["width"], size["height"]
    cols, features, seen = {}, [], set()
    for cy in range(0, H, CHUNK):
        for cx in range(0, W, CHUNK):
            w, h = min(CHUNK, W - cx), min(CHUNK, H - cy)
            r = t.map_columns(cx, cy, w, h)
            for j in range(h):
                for i in range(w):
                    ch = r["top"][j][i]
                    if ch == ".":
                        continue
                    wc = r["water"][j][i]
                    depth = dec(wc) / 10 if wc != " " else 0.0
                    dirt = dec(r["contamination"][j][i]) / 9 if wc != " " else 0.0
                    cols[f"{cx + i},{cy + j}"] = [[dec(ch), -1, depth, None, dirt]]
            for c in r["layered"]:
                cols[f"{c['x']},{c['y']}"] = c["levels"]
            for f in r["features"]:
                key = (f["name"], f["x"], f["y"], f["z"])
                if key not in seen:
                    seen.add(key)
                    features.append(f)
    buildings = json.loads(t.list_buildings())
    buildings = buildings["buildings"] if isinstance(buildings, dict) else buildings
    data = {"width": W, "height": H, "cols": cols, "features": features,
            "buildings": [{k: b.get(k) for k in ("template", "x", "y", "z")} for b in buildings]}
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(data))
    return data


def load(refresh=False):
    if not refresh and CACHE.exists():
        d = json.loads(CACHE.read_text())
        if "cols" in d:
            return d
    return fetch()


class World:
    def __init__(self, d):
        self.d = d
        self.W, self.H = d["width"], d["height"]
        self.cols = {tuple(map(int, k.split(","))): v for k, v in d["cols"].items()}
        # wet cells: (x, y, z) -> (headroom, depth, dirt)
        self.cells = {}
        for (x, y), levels in self.cols.items():
            for z, head, depth, _, dirt in levels:
                if depth > WET:
                    self.cells[(x, y, z)] = (head, depth, dirt or 0.0)
        self.body_of, self.bodies = {}, []
        self._bodies()
        self._spills()

    def top(self, x, y):
        levels = self.cols.get((x, y))
        return levels[-1][0] if levels else None

    def surface(self, cell):
        return cell[2] + self.cells[cell][1]

    def _neighbours(self, cell):
        x, y, z = cell
        for dx, dy in N4:
            for lv in self.cols.get((x + dx, y + dy), ()):
                yield (x + dx, y + dy, lv[0]), lv

    def _bodies(self):
        for start in self.cells:
            if start in self.body_of:
                continue
            bid, queue, members = len(self.bodies), deque([start]), []
            self.body_of[start] = bid
            while queue:
                c = queue.popleft()
                members.append(c)
                z0, z1 = c[2], self.surface(c)
                for n, lv in self._neighbours(c):
                    if n in self.cells and n not in self.body_of:
                        if n[2] < z1 and z0 < self.surface(n):
                            self.body_of[n] = bid
                            queue.append(n)
            self.bodies.append(self._summary(bid, members))

    def _summary(self, bid, members):
        xs, ys = [c[0] for c in members], [c[1] for c in members]
        heads = [self.surface(c) for c in members]
        cave = [c for c in members if self.cells[c][0] != -1]
        full = [c for c in cave if self.cells[c][1] >= self.cells[c][0] - 0.05]
        return {"id": bid, "cells": members, "tiles": len(members), "floor": min(c[2] for c in members),
                "head": round(max(heads), 2), "low": round(min(heads), 2),
                "dirt": round(sum(self.cells[c][2] >= 0.5 for c in members) / len(members), 2),  # share of badwater tiles
                "volume": round(sum(self.cells[c][1] for c in members), 1),
                "cave": len(cave), "full": full, "bbox": (min(xs), min(ys), max(xs), max(ys)),
                "spillsTo": set(), "fedBy": set(), "sources": []}

    def _spills(self):
        """Body A spills into body B where A's water reaches the open space of a lower B cell."""
        for c, (head, depth, _) in self.cells.items():
            a, top_a = self.body_of[c], c[2] + depth
            for n, lv in self._neighbours(c):
                if n not in self.cells:
                    continue
                b = self.body_of[n]
                if b == a:
                    continue
                open_top = n[2] + lv[1] if lv[1] != -1 else 1e9
                if c[2] < open_top and n[2] < top_a and top_a > self.surface(n) + 0.05:
                    self.bodies[a]["spillsTo"].add(b)

    def downstream(self, bid):
        seen, queue = {bid}, deque([bid])
        while queue:
            for b in self.bodies[queue.popleft()]["spillsTo"]:
                if b not in seen:
                    seen.add(b)
                    queue.append(b)
        return seen

    def body_near(self, x, y, z, reach=2):
        best = None
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                for lv in self.cols.get((x + dx, y + dy), ()):
                    c = (x + dx, y + dy, lv[0])
                    if c in self.cells and z - 1 <= c[2] <= z + 3:
                        d = abs(dx) + abs(dy) + abs(c[2] - z)
                        if best is None or d < best[0]:
                            best = (d, self.body_of[c])
        return None if best is None else best[1]


def fmt_body(b):
    x0, y0, x1, y1 = b["bbox"]
    kind = "cave" if b["cave"] == b["tiles"] else (f"surface+cave {b['cave']}" if b["cave"] else "surface")
    bad = f", {b['dirt']:.0%} of tiles BADWATER" if b["dirt"] > 0 else ", clean"
    full = f", {len(b['full'])} PRESSURISED (full to the roof)" if b["full"] else ""
    return (f"W{b['id']}: {b['tiles']} tiles x{x0}-{x1} y{y0}-{y1}, {kind}, floor z{b['floor']}, "
            f"surface z{b['low']}-{b['head']}, volume {b['volume']}{bad}{full}")


def sources(w, feats):
    out, groups = [], {}
    for f in feats:
        st = f.get("state") or {}
        if "WaterSource.CurrentStrength" not in st:
            continue
        name = f["name"].split(".")[0]
        bid = w.body_near(f["x"], f["y"], f["z"])
        g = groups.setdefault((name, bid, f["z"], f["x"] // 6, f["y"] // 6),
                              {"name": name, "body": bid, "strength": 0, "xs": [], "ys": [], "z": f["z"],
                               "dirt": st.get("WaterSource.Contamination", 0)})
        g["strength"] += st["WaterSource.CurrentStrength"]
        g["xs"].append(f["x"])
        g["ys"].append(f["y"])
    for g in groups.values():
        where = f"({min(g['xs'])}-{max(g['xs'])}, {min(g['ys'])}-{max(g['ys'])}, z{g['z']})"
        if g["body"] is None:
            out.append(f"{g['name']} {where} strength {g['strength']:.2f}: NO WATER AT IT - check (blocked/dry)")
            continue
        down = w.downstream(g["body"])
        for b in down:
            w.bodies[b]["fedBy"].add(f"{g['name']}{where}")
        w.bodies[g["body"]]["sources"].append(g["name"])
        chain = sorted(down - {g["body"]}, key=lambda b: -w.bodies[b]["tiles"])
        out.append(f"{g['name']} {where} strength {g['strength']:.2f} -> W{g['body']}"
                   + (f", spills on to {', '.join(f'W{b}' for b in chain[:8])}" if chain else ", no outflow"))
    return out


def sphere(cx, cy, cz, r):
    for vz in range(int(cz - r) - 1, int(cz + r) + 2):
        for vy in range(int(cy - r) - 1, int(cy + r) + 2):
            for vx in range(int(cx - r) - 1, int(cx + r) + 2):
                if math.dist((vx + 0.5, vy + 0.5, vz + 0.5), (cx, cy, cz)) <= r:
                    yield vx, vy, vz


def flood_area(w, starts, head, newtop=None, limit=4000):
    """Surface tiles lower than `head` reachable from the crater: where escaping water could go.
    An upper bound - the real spread is limited by volume and source strength."""
    newtop = newtop or {}
    height = lambda p: newtop.get(p, w.top(*p))
    seen, queue = set(starts), deque(starts)
    while queue and len(seen) < limit:
        cx, cy = queue.popleft()
        for dx, dy in N4:
            n = (cx + dx, cy + dy)
            if n not in seen and n in w.cols and height(n) < head:
                seen.add(n)
                queue.append(n)
    return seen


def cores(w, feats, base):
    out = []
    items = [f for f in feats if f["name"].startswith("UnstableCore")]
    items.sort(key=lambda f: (f.get("state") or {}).get("TimedComponentActivator.CyclesUntilCountdownActivation", 99))
    others = [f for f in feats if f["name"].split(".")[0] in
              ("NaturalDam", "Blockage", "WaterSource", "BadwaterSource", "WaterSeep", "UnstableCore", "Dynamite")]
    for f in items:
        st = f.get("state") or {}
        rad = st.get("UnstableCore.ExplosionRadius", 3)
        r = rad + st.get("UnstableCore.InnerRadius", 1.0)  # game code: ExplosionRadius + InnerRadius
        ox, oy = CENTRE.get(f["orientation"], (1, 1))
        cx, cy, cz = f["x"] + ox, f["y"] + oy, f["z"]  # GridCenterGrounded: footprint centre at the core's z
        cyc = st.get("TimedComponentActivator.CyclesUntilCountdownActivation", "?")
        days = st.get("TimedComponentActivator.DaysUntilActivation", "?")
        lines = [f"CORE ({f['x']},{f['y']},z{f['z']}) radius {rad} (crater sphere r{r}, z{cz - r:.0f}-{cz + r:.0f}): "
                 f"countdown starts cycle {cyc} day 1, explodes {days} days later (about cycle {cyc} day {1 + float(days):.1f}"
                 f" or early in cycle {cyc + 1 if isinstance(cyc, int) else '?'} if the cycle is shorter). "
                 f"{round(math.dist((cx, cy), base))} tiles from the DC"]
        removed = set(sphere(cx, cy, cz, r))
        # bodies touched: wet cells inside or next to the crater
        hit = {}
        for (vx, vy, vz) in removed:
            for dx, dy, dz in ((0, 0, 0), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, -1), (0, 0, 1)):
                for lv in w.cols.get((vx + dx, vy + dy), ()):
                    c = (vx + dx, vy + dy, lv[0])
                    if c in w.cells and c[2] <= vz + dz < w.surface(c) + 1:
                        hit.setdefault(w.body_of[c], set()).add(c)
        for bid in sorted(hit, key=lambda b: -w.bodies[b]["head"]):
            b = w.bodies[bid]
            opened = [c for c in b["full"] if any((c[0], c[1], z) in removed for z in range(c[2], c[2] + 3))]
            lines.append(f"  hits {fmt_body(b)}" + (f"; roof opened over {len(opened)} full tiles" if opened else ""))
        if len(hit) > 1:
            hs = [w.bodies[b] for b in hit]
            dz = max(b["head"] for b in hs) - min(b["head"] for b in hs)
            bad = [b for b in hs if b["dirt"] > 0.05]
            lines.append(f"  JOINS {len(hit)} bodies: head difference {dz:.1f}"
                         + (", BADWATER mixes into clean water" if bad and len(bad) < len(hs) else ""))
        # New ground inside the crater (columns cut down from the top), then where water could run from it.
        cut = {}
        for (vx, vy, vz) in removed:
            top = w.top(vx, vy)
            if top is not None and vz < top:
                cut.setdefault((vx, vy), []).append(vz)
        newtop = {k: min(v) for k, v in cut.items() if max(v) + 1 >= w.top(*k)}
        for bid in hit:
            b = w.bodies[bid]
            opened = [c for c in hit[bid] if c in set(b["full"])]
            head = b["head"] if opened else max(w.surface(c) for c in hit[bid])
            start = [k for k, v in newtop.items() if v < head - 0.2]
            if not start:
                continue
            area = flood_area(w, start, head, newtop)
            outside = [a for a in area if a not in newtop]
            if not outside:
                lines.append(f"  W{bid} fills the crater (z{min(newtop.values())}) up to z{head:.1f}: water stays in the crater")
                continue
            bx, by = [a[0] for a in area], [a[1] for a in area]
            reached = {w.body_of[(x, y, w.top(x, y))] for x, y in area if (x, y, w.top(x, y)) in w.cells} - {bid}
            fed = [s for s in b["fedBy"]]
            lines.append(f"  NEW OUTLET: W{bid} ({'pressurised cave' if opened else 'pool'}, head z{head:.1f}"
                         + (f", BADWATER" if b["dirt"] > 0.5 else "") + f") runs out of the crater over "
                         f"{len(outside)} lower tiles (up to {len(area)}) x{min(bx)}-{max(bx)} y{min(by)}-{max(by)}"
                         + (" - REACHES THE BASE" if any(math.dist(a, base) < 12 for a in area) else "")
                         + (f"; joins {', '.join(f'W{r2}' for r2 in sorted(reached))}" if reached else "")
                         + (f"; fed continuously by {', '.join(fed)}" if fed else f"; one-off volume {b['volume']}"))
        nearby = [o for o in others if o is not f and math.dist((o["x"] + 0.5, o["y"] + 0.5, o["z"] + 0.5),
                                                                 (cx, cy, cz)) <= r + 1.5]
        if nearby:
            names = {}
            for o in nearby:
                names.setdefault(o["name"].split(".")[0], []).append(f"({o['x']},{o['y']},z{o['z']})")
            lines.append("  in range: " + "; ".join(f"{k} {' '.join(v[:6])}" for k, v in names.items()))
            if "UnstableCore" in names or "Dynamite" in names:
                lines.append("  CHAIN REACTION possible")
        blds = [b for b in w.d.get("buildings", []) if b.get("z") is not None
                and math.dist((b["x"] + 0.5, b["y"] + 0.5, b["z"] + 0.5), (cx, cy, cz)) <= r + 1]
        if blds:
            lines.append(f"  buildings in range: {[b['template'].split('.')[0] for b in blds]}")
        if len(lines) == 1:
            lines.append("  no water, dams, sources or buildings in range: crater only")
        out += lines
    return out


def barriers(w, feats):
    out, groups = [], {}
    for f in feats:
        name = f["name"].split(".")[0]
        if name not in ("NaturalDam", "Blockage"):
            continue
        sides = {}
        for dx, dy in N4:
            for lv in w.cols.get((f["x"] + dx, f["y"] + dy), ()):
                c = (f["x"] + dx, f["y"] + dy, lv[0])
                if c in w.cells and f["z"] - 2 <= c[2] <= f["z"] + 2:
                    bid = w.body_of[c]
                    sides[bid] = max(sides.get(bid, 0), w.surface(c))
        key = (name, f["z"], f["x"] // 4, f["y"] // 4)
        g = groups.setdefault(key, {"name": name, "z": f["z"], "tiles": [], "sides": {}})
        g["tiles"].append((f["x"], f["y"]))
        for bid, h in sides.items():
            g["sides"][bid] = max(g["sides"].get(bid, 0), h)
    for g in groups.values():
        xs, ys = [t[0] for t in g["tiles"]], [t[1] for t in g["tiles"]]
        where = f"{g['name']} x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)} z{g['z']}"
        if not g["sides"]:
            out.append(f"{where}: dry on all sides (holds nothing now)")
            continue
        parts = [f"W{b} at z{h:.1f} ({'bad' if w.bodies[b]['dirt'] >= 0.5 else 'clean'})" for b, h in
                 sorted(g["sides"].items(), key=lambda kv: -kv[1])]
        hs = list(g["sides"].values())
        verdict = (f"holds a {max(hs) - min(hs):.1f} drop" if len(hs) > 1 else
                   f"water on one side only (z{hs[0]:.1f}): removing it lets that water out over z{g['z']}")
        out.append(f"{where}: {', '.join(parts)} - {verdict}")
    return out


def report(refresh=False):
    d = load(refresh)
    w = World(d)
    feats = d["features"]
    dc = next((b for b in d.get("buildings", []) if b["template"].startswith("DistrictCenter")), None)
    base = (dc["x"] + 1.5, dc["y"] + 1.5) if dc else (d["width"] / 2, d["height"] / 2)
    src = sources(w, feats)
    big = sorted(w.bodies, key=lambda b: -b["tiles"])
    print("== SOURCES (traced through the 3D water, not guessed)")
    for line in src:
        print(" ", line)
    print("== WATER BODIES (largest 20; caves and pressurised ones flagged)")
    for b in big[:20]:
        fed = f" fed by {', '.join(sorted(b['fedBy']))}" if b["fedBy"] else " NOT FED BY ANY SOURCE (still water: drains/evaporates)"
        print(" ", fmt_body(b) + ";" + fed)
    print("== BASE: water under and beside the DC")
    near = sorted({w.body_of[c] for c in w.cells if math.dist(c[:2], base) < 15}, key=lambda b: -w.bodies[b]["tiles"])
    for bid in near:
        b = w.bodies[bid]
        print(f"  W{bid}: {'cave' if b['cave'] else 'surface'} {b['tiles']} tiles, head z{b['head']}, "
              + (f"fed by {', '.join(sorted(b['fedBy']))}" if b["fedBy"] else "NOT FED"))
    print("== NATURAL DAMS / BLOCKAGES (what removing one would release)")
    for line in barriers(w, feats):
        print(" ", line)
    print("== UNSTABLE CORES (earliest first)")
    for line in cores(w, feats, base):
        print(line)


if __name__ == "__main__":
    report(refresh="--refresh" in sys.argv)
