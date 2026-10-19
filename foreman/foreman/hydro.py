"""Water engineering (phase 4): 3D water bodies, sources traced downhill, existing pools, and the dam,
badwater, reservoir, platform-deck, pump-site and wheel-site planners.

Plain Python on the collector's map snapshot (surface grids plus the bridge's layered columns). Nothing here
touches the game: every proposal comes back with the exact harness calls for the playing AI to run.
The bodies, sources, cores and barriers logic is ported from harness/underground.py.

Mechanics, each with its source next to the constant. The map edge drains: cells outside the terrain stay open
to water except next to a source [decompiled WaterSystem/WaterMapBoundaryService], so a pool touching the edge leaks.
"""

from __future__ import annotations

import heapq
import math
from collections import deque

import numpy as np

from .collector import base

WET = 0.05                   # a column counts as water above this depth (bridge columns, underground.py)
DAM_HOLD = 0.65              # Dam and NaturalDam hold 0.65 above their tile [bp FinishableWaterObstacle; knowledge/09 §4]
LEVEE_HOLD = 1.0             # Levee and Blockage are a full block [knowledge/10 §5]
GATE_HOLD = {"Floodgate": 1.0, "DoubleFloodgate": 2.0, "TripleFloodgate": 3.0}  # max setting; live setting not read [unverified]
EVAPORATION = 0.046          # depth per day from a still column (0.0001/s x 0.6 s/tick x 768 ticks) [decompiled WaterSimulator; knowledge/10 §5]
GOODS_PER_UNIT = 5           # 1 water good = 0.2 water units [web; knowledge/03]
DISCHARGE_PER_DAY = 3 * 24 / GOODS_PER_UNIT  # Discharge: 3 goods per worker-hour [knowledge/09]; x24 h is the upper bound
BAD = 0.5                    # soil contamination spreads from water at or above 0.5 [bp SoilContaminationSimulator]
CONTAM_REACH = 7             # ... up to 7 tiles; climbing +1 height costs 5 flat tiles [bp; knowledge/10 §6]
MOIST_REACH = 8              # fields within ~8 tiles of water and at most 1 above it [measured, knowledge/10 §6]
PLATFORM_DRY = 0.85          # a deck on a 1-high Platform stays dry while the water is under ~0.85 [derived: 1.0 minus margin]
DEEP_PUMP_REACH = 6          # a Deep Water Pump reaches 6 down [knowledge/09]
STACKS = (                   # (label, height, structures bottom-up, logs) per tile; Dam 20 logs, Levee 12 logs [knowledge/09]
    ("Dam", DAM_HOLD, ("Dam",)),
    ("Levee", 1.0, ("Levee",)),
    ("2 Levees", 2.0, ("Levee", "Levee")),          # stacked Levees [knowledge/10 §5 "stack Levees"]
    ("3 Levees", 3.0, ("Levee", "Levee", "Levee")),
)
MAX_WET_RUN = 10             # widest water cross-section considered a choke
MAX_LINE = 16                # longest dam line including bank extensions
FLOOD_LIMIT = 8000           # flood fills stop here (the proposal is then "unbounded")
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))
FLOW = {"v": (0, -1), "^": (0, 1), ">": (1, 0), "<": (-1, 0)}  # bridge flowKey: v south (-y), ^ north (+y)
CENTRE = {0: (1, 1), 1: (1, 0), 2: (0, 0), 3: (0, 1)}             # 2x2 core: pivot -> grid point at its middle
# Buildings that are meant to stand in water (a flood does not hurt them).
WATER_OK = ("Dam", "Levee", "Floodgate", "DoubleFloodgate", "TripleFloodgate", "Platform", "DoublePlatform",
            "TriplePlatform", "DeepWaterPump", "WaterPump", "MechanicalWaterPump", "DeepBadwaterPump", "BadwaterPump",
            "CompactWaterWheel", "WaterWheel", "LargeWaterWheel", "Sluice", "Stairs", "PowerShaft", "Path",
            "SuspensionBridge", "Bridge", "AquaticFarmhouse", "Discharge", "MetalPlatform3x3", "MetalPlatform5x5")
PUMPS = ("DeepWaterPump", "WaterPump", "MechanicalWaterPump", "DeepMechanicalPump")
CROPS = ("Kohlrabi", "Corn", "Cassava", "Soybean", "Eggplant", "Potato", "Carrot", "Wheat", "Sunflower", "Canola",
         "Cattail", "Spadderdock", "Mushroom", "Algae", "Grape")

_CACHE: dict = {}


def analysis(world) -> "Hydro | None":
    """Hydro for this map snapshot, cached while the terrain, water and obstacles are unchanged."""
    if not world.has_map:
        return None
    m = world.state["map"]
    obst = tuple(sorted((b.name, b.x, b.y, b.z) for b in world.buildings
                        if b.finished and (b.name in GATE_HOLD or b.name in ("Dam", "Levee"))))
    sig = (hash(tuple(m["top"])), hash(tuple(m["water"])), hash(tuple(m["contamination"])), obst, len(world.buildings))
    if sig not in _CACHE:
        _CACHE.clear()
        _CACHE[sig] = Hydro(world)
    return _CACHE[sig]


def dec(ch: str) -> int:
    from .world import dec as d
    return d(ch)


class Hydro:
    def __init__(self, world):
        self.world = world
        self.m = world.state["map"]
        self.W, self.H = world.w, world.h
        self.top = world.top.astype(np.float32)
        self.depth = world.depth
        self.dirt = world.dirt
        self.surface = self.top + self.depth
        self.wet = self.depth > WET
        self.flow = self.m.get("flow") or [" " * self.W] * self.H
        self.speed = self.m.get("speed") or [" " * self.W] * self.H
        self.templates = {base(bp["template"]): bp for bp in world.blueprints or []}
        self._obstacles()
        self._columns()
        self._bodies()
        self._spills()
        self._sources()
        self._cache: dict = {}

    # ------------------------------------------------------------------ inputs
    def tpl(self, name: str) -> str:
        """Faction template id for a building name (Dam -> Dam.IronTeeth)."""
        bp = self.templates.get(name)
        return bp["template"] if bp else name

    def unlocked(self, name: str) -> bool | None:
        bp = self.templates.get(name)
        return None if bp is None else bool(bp.get("unlocked", True))

    def logs(self, name: str) -> int:
        bp = self.templates.get(name) or {}
        return int((bp.get("cost") or {}).get("Log", {"Dam": 20, "Levee": 12}.get(name, 0)))

    def in_map(self, x: int, y: int) -> bool:
        return 0 <= x < self.W and 0 <= y < self.H and self.top[y, x] >= 0

    def _obstacles(self) -> None:
        """Crest grid: the level water must pass to cross each tile (terrain top, or an obstacle's top)."""
        self.crest = self.top.copy()
        self.obstacle: dict[tuple[int, int], tuple[str, int, float]] = {}

        def add(name, x, y, z, hold):
            if 0 <= x < self.W and 0 <= y < self.H:
                c = z + hold
                if c > self.crest[y, x]:
                    self.crest[y, x] = c
                self.obstacle[(x, y)] = (name, z, hold)
        for b in self.world.buildings:
            if not b.finished:
                continue
            hold = DAM_HOLD if b.name == "Dam" else LEVEE_HOLD if b.name == "Levee" else GATE_HOLD.get(b.name)
            if hold:
                for x, y in self.world.footprint(b):
                    # stacked levees: the top one sets the crest
                    prev = self.obstacle.get((x, y))
                    z0 = min(prev[1], b.z) if prev else b.z
                    add(b.name, x, y, b.z, hold)
                    self.obstacle[(x, y)] = (b.name, z0, b.z + hold - z0)
        for f in self.world.features or []:
            n = base(f["name"])
            if n in ("NaturalDam", "Blockage"):
                add(n, f["x"], f["y"], f["z"], DAM_HOLD if n == "NaturalDam" else LEVEE_HOLD)
        self.crest_l = self.crest.tolist()

    # ------------------------------------------------------------------ 3D water (underground.py)
    def _columns(self) -> None:
        """(x, y) -> [[z, headroom, depth, _, dirt], ...] standing levels; caves and overhangs from `layered`."""
        cols = {}
        for y in range(self.H):
            for x in range(self.W):
                if self.top[y, x] >= 0:
                    cols[(x, y)] = [[int(self.top[y, x]), -1, float(self.depth[y, x]), None,
                                     float(self.dirt[y, x]) if self.depth[y, x] > 0 else 0.0]]
        for c in self.m.get("layered") or []:
            cols[(c["x"], c["y"])] = c["levels"]
        self.cols = cols
        self.cells = {}
        for (x, y), levels in cols.items():
            for z, head, depth, _, dirt in levels:
                if depth > WET:
                    self.cells[(x, y, z)] = (head, depth, dirt or 0.0)

    def cell_surface(self, c) -> float:
        return c[2] + self.cells[c][1]

    def _neighbours(self, cell):
        x, y, _ = cell
        for dx, dy in N4:
            for lv in self.cols.get((x + dx, y + dy), ()):
                yield (x + dx, y + dy, lv[0]), lv

    def _bodies(self) -> None:
        self.body_of: dict = {}
        self.bodies: list[dict] = []
        for start in self.cells:
            if start in self.body_of:
                continue
            bid, queue, members = len(self.bodies), deque([start]), []
            self.body_of[start] = bid
            while queue:
                c = queue.popleft()
                members.append(c)
                z0, z1 = c[2], self.cell_surface(c)
                for n, _ in self._neighbours(c):
                    if n in self.cells and n not in self.body_of and n[2] < z1 and z0 < self.cell_surface(n):
                        self.body_of[n] = bid
                        queue.append(n)
            xs, ys = [c[0] for c in members], [c[1] for c in members]
            heads = [self.cell_surface(c) for c in members]
            cave = [c for c in members if self.cells[c][0] != -1]
            full = [c for c in cave if self.cells[c][1] >= self.cells[c][0] - 0.05]
            self.bodies.append({
                "id": bid, "cells": members, "tiles": len(members), "floor": min(c[2] for c in members),
                "head": round(max(heads), 2), "low": round(min(heads), 2),
                "dirt": round(sum(self.cells[c][2] >= BAD for c in members) / len(members), 2),
                "volume": round(sum(self.cells[c][1] for c in members), 1),
                "cave": len(cave), "full": full, "bbox": (min(xs), min(ys), max(xs), max(ys)),
                "spillsTo": set(), "fedBy": set(), "sources": []})

    def _spills(self) -> None:
        """Body A spills into body B where A's water reaches the open space of a lower B cell."""
        for c, (_, depth, _) in self.cells.items():
            a, top_a = self.body_of[c], c[2] + depth
            for n, lv in self._neighbours(c):
                if n not in self.cells:
                    continue
                b = self.body_of[n]
                if b == a:
                    continue
                open_top = n[2] + lv[1] if lv[1] != -1 else 1e9
                if c[2] < open_top and n[2] < top_a and top_a > self.cell_surface(n) + 0.05:
                    self.bodies[a]["spillsTo"].add(b)

    def downstream(self, bid: int) -> set:
        seen, queue = {bid}, deque([bid])
        while queue:
            for b in self.bodies[queue.popleft()]["spillsTo"]:
                if b not in seen:
                    seen.add(b)
                    queue.append(b)
        return seen

    def body_near(self, x: int, y: int, z: int, reach: int = 2) -> int | None:
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

    def surface_body(self, x: int, y: int) -> int | None:
        c = (x, y, int(self.top[y, x]))
        return self.body_of.get(c)

    def _sources(self) -> None:
        """Group the bridge's source tiles, attach each group to its body and follow it downhill."""
        groups: list[dict] = []
        for s in self.world.sources or []:
            bad = (s.get("contamination") or 0) >= BAD
            g = next((g for g in groups if g["bad"] == bad and g["z"] == s["z"]
                      and any(abs(s["x"] - x) <= 1 and abs(s["y"] - y) <= 1 for x, y in g["tiles"])), None)
            if not g:
                g = {"bad": bad, "z": s["z"], "tiles": [], "strength": 0.0, "specified": 0.0}
                groups.append(g)
            g["tiles"].append((s["x"], s["y"]))
            g["strength"] += s.get("currentStrength") or 0
            g["specified"] += s.get("specifiedStrength") or 0
        feats = [f for f in self.world.features or [] if "WaterSource.CurrentStrength" in (f.get("state") or {})]
        for g in groups:
            xs, ys = [t[0] for t in g["tiles"]], [t[1] for t in g["tiles"]]
            g["bbox"] = (min(xs), min(ys), max(xs), max(ys))
            g["name"] = "BadwaterSource" if g["bad"] else "WaterSource"
            # features are keyed by their pivot, the bridge lists water tiles: take the nearest feature
            near = [f for f in feats if abs(f["z"] - g["z"]) <= 1 and min(abs(f["x"] - x) + abs(f["y"] - y) for x, y in g["tiles"]) <= 3]
            if near:
                st = near[0]["state"]
                g["name"] = base(near[0]["name"])
                if st.get("TimedComponentActivator.IsEnabled") and not st.get("TimedComponentActivator.IsPastActivationTime"):
                    g["activates"] = {"cycles": st.get("TimedComponentActivator.CyclesUntilCountdownActivation"),
                                      "days": st.get("TimedComponentActivator.DaysLeftUntilActivation"),
                                      "countdown": bool(st.get("TimedComponentActivator.CountdownIsActive"))}
            g["strength"] = round(g["strength"], 2)
            bid = self.body_near(g["tiles"][0][0], g["tiles"][0][1], g["z"])
            g["body"] = bid
            g["downstream"] = []
            if bid is not None:
                down = self.downstream(bid)
                label = f"{g['name']}({g['bbox'][0]}-{g['bbox'][2]},{g['bbox'][1]}-{g['bbox'][3]},z{g['z']})"
                for b in down:
                    self.bodies[b]["fedBy"].add(label)
                self.bodies[bid]["sources"].append(g["name"])
                g["downstream"] = sorted(down - {bid}, key=lambda b: -self.bodies[b]["tiles"])
        self.source_groups = groups

    # ------------------------------------------------------------------ flood fill on the surface
    def flood(self, level: float, starts, blocked=frozenset(), limit: int = FLOOD_LIMIT):
        """Surface tiles water at `level` reaches from `starts` (4-neighbour, over every crest below it)."""
        crest, W, H = self.crest_l, self.W, self.H
        seen, queue = set(), deque()
        for s in starts:
            if s not in blocked and 0 <= s[0] < W and 0 <= s[1] < H and crest[s[1]][s[0]] < level:
                seen.add(s)
                queue.append(s)
        while queue and len(seen) < limit:
            x, y = queue.popleft()
            for dx, dy in N4:
                nx_, ny_ = x + dx, y + dy
                n = (nx_, ny_)
                if 0 <= nx_ < W and 0 <= ny_ < H and n not in seen and n not in blocked and -1 < crest[ny_][nx_] < level:
                    seen.add(n)
                    queue.append(n)
        return seen, len(seen) >= limit

    def footprints(self):
        if "fp" not in self._cache:
            self._cache["fp"] = [(b, self.world.footprint(b)) for b in self.world.buildings if b.finished]
        return self._cache["fp"]

    def effects(self, region: set, level: float) -> dict:
        """What a pool at `level` over `region` does: volume, newly wet tiles, buildings and crops it floods."""
        total = added = 0.0
        new_wet = 0
        for x, y in region:
            t = float(self.top[y, x])
            total += level - t
            added += max(0.0, level - max(t, float(self.surface[y, x])))
            new_wet += not self.wet[y, x]
        flooded, pumps = [], []
        for b, tiles in self.footprints():
            if b.name in PUMPS and any((x + dx, y + dy) in region for x, y in tiles for dx, dy in N8):
                pumps.append(b.label)
            if b.name in WATER_OK or b.z >= level - 0.05:
                continue
            if any(t in region for t in tiles):
                flooded.append(b.label)
        crops = 0
        if self.world.planting:
            crops = sum(1 for t, (_, plant) in self.world.planting.items()
                        if t in region and not self.wet[t[1], t[0]] and plant in CROPS)
        n = max(1, len(region))
        return {"tiles": len(region), "volume": round(total, 1), "added": round(added, 1),
                "goods": round(added * GOODS_PER_UNIT), "newWet": new_wet, "meanDepth": round(total / n, 2),
                "droughtDays": round(total / n / EVAPORATION, 1), "flooded": flooded, "pumps": pumps, "crops": crops}

    # ------------------------------------------------------------------ existing pools (validation + "held" water)
    def pools(self) -> list[dict]:
        """Every existing dam/levee/natural-dam line: the pool it should hold vs the water standing there now."""
        if "pools" in self._cache:
            return self._cache["pools"]
        tiles = set(self.obstacle)
        out, seen = [], set()
        for start in sorted(tiles):
            if start in seen:
                continue
            group, queue = [], deque([start])
            seen.add(start)
            while queue:
                t = queue.popleft()
                group.append(t)
                for dx, dy in N8:
                    n = (t[0] + dx, t[1] + dy)
                    if n in tiles and n not in seen and abs(self.obstacle[n][1] - self.obstacle[t][1]) <= 1:
                        seen.add(n)
                        queue.append(n)
            level = min(self.crest[y, x] for x, y in group)
            starts = []
            for x, y in group:
                d = FLOW.get(self.flow[y][x])
                if d:                                   # water on the line flows d: the pool is the other side
                    starts.append((x - d[0], y - d[1]))
            if not starts:                              # still water: the wet side standing highest
                nb = [(x + dx, y + dy) for x, y in group for dx, dy in N4
                      if (x + dx, y + dy) not in tiles and self.in_map(x + dx, y + dy) and self.wet[y + dy, x + dx]]
                if nb:
                    hi = max(self.surface[y, x] for x, y in nb)
                    starts = [(x, y) for x, y in nb if self.surface[y, x] >= hi - 0.05]
            crest = level
            wet_up = [float(self.surface[y, x]) for x, y in starts if self.in_map(x, y) and self.wet[y, x]]
            full = bool(wet_up) and max(wet_up) >= crest - 0.1
            # Only a full line holds a flat pool; below its crest the water is just flowing past (a single-level
            # flood fill would spread it over the whole lowland), so report the line without a region.
            region, capped = self.flood(level, starts, blocked=tiles) if full else (set(), False)
            region = {t for t in region if self.top[t[1], t[0]] < level}
            predicted = sum(level - float(self.top[y, x]) for x, y in region)
            observed = sum(float(self.depth[y, x]) for x, y in region)
            names = sorted({self.obstacle[t][0] for t in group})
            xs, ys = [t[0] for t in group], [t[1] for t in group]
            out.append({"id": len(out), "kinds": names, "tiles": group, "bbox": (min(xs), min(ys), max(xs), max(ys)),
                        "crest": round(float(crest), 2), "level": round(float(level), 2), "full": full,
                        "region": sorted(region), "capped": capped,
                        "predicted": round(predicted, 1), "observed": round(observed, 1),
                        "error": round(predicted / observed - 1, 3) if observed > 0 and full and not capped else None})
        self._cache["pools"] = out
        return out

    def held_tiles(self) -> set:
        if "held" not in self._cache:
            self._cache["held"] = set().union(*(set(p["region"]) for p in self.pools())) if self.pools() else set()
        return self._cache["held"]

    # ------------------------------------------------------------------ dam planner
    def _runs(self):
        """Wet cross-sections: (axis, fixed, a0, a1) runs of water along rows (axis x) and columns (axis y)."""
        runs = []
        for axis in ("x", "y"):
            n_fixed, n_along = (self.H, self.W) if axis == "x" else (self.W, self.H)
            for f in range(n_fixed):
                a = 0
                while a < n_along:
                    x, y = (a, f) if axis == "x" else (f, a)
                    if self.wet[y, x] and (x, y) not in self.obstacle:
                        a0 = a
                        while a < n_along:
                            x, y = (a, f) if axis == "x" else (f, a)
                            if not self.wet[y, x] or (x, y) in self.obstacle:
                                break
                            a += 1
                        if a - a0 <= MAX_WET_RUN:
                            runs.append((axis, f, a0, a - 1))
                    else:
                        a += 1
        return runs

    def _line(self, axis, f, a0, a1, level):
        """Extend a wet run along its axis until both ends meet a bank at or above `level`."""
        at = (lambda a: (a, f)) if axis == "x" else (lambda a: (f, a))
        lo, hi = a0, a1
        while True:
            x, y = at(lo - 1)
            if not self.in_map(x, y):
                return None
            if self.crest[y, x] >= level:
                break
            lo -= 1
            if hi - lo + 1 > MAX_LINE:
                return None
        while True:
            x, y = at(hi + 1)
            if not self.in_map(x, y):
                return None
            if self.crest[y, x] >= level:
                break
            hi += 1
            if hi - lo + 1 > MAX_LINE:
                return None
        return [at(a) for a in range(lo, hi + 1)], at(lo - 1), at(hi + 1)

    def _upstream(self, axis, line):
        """+1 if the pool side is +y (axis x) / +x (axis y), -1 for the other side, None if it can't tell."""
        nx_, ny_ = (0, 1) if axis == "x" else (1, 0)
        side = {}
        for s in (1, -1):
            vals = [float(self.surface[y + s * ny_, x + s * nx_]) for x, y in line
                    if self.in_map(x + s * nx_, y + s * ny_) and self.wet[y + s * ny_, x + s * nx_]]
            side[s] = sum(vals) / len(vals) if vals else None
        if side[1] is not None and side[-1] is not None and abs(side[1] - side[-1]) > 0.05:
            return 1 if side[1] > side[-1] else -1
        vote = 0
        for x, y in line:
            d = FLOW.get(self.flow[y][x])
            if d:
                vote -= d[0] * nx_ + d[1] * ny_       # flowing towards +side means the pool is on -side
        if vote:
            return 1 if vote > 0 else -1
        if side[1] is not None and side[-1] is None:
            return 1
        if side[-1] is not None and side[1] is None:
            return -1
        return None

    def _stack(self, top: float, level: float):
        need = level - top
        if need <= 1e-6:
            return None
        for label, h, parts in STACKS:
            if h + 1e-6 >= need:
                return label, h, parts
        return None

    def _drop(self, axis, line, s) -> float:
        """How far the water falls within 4 tiles downstream of the line (a dam just above a drop holds most)."""
        nx_, ny_ = (0, 1) if axis == "x" else (1, 0)
        up = [float(self.surface[y + s * ny_, x + s * nx_]) for x, y in line
              if self.in_map(x + s * nx_, y + s * ny_) and self.wet[y + s * ny_, x + s * nx_]]
        down = [float(self.surface[y - k * s * ny_, x - k * s * nx_]) for x, y in line for k in range(1, 5)
                if self.in_map(x - k * s * nx_, y - k * s * ny_) and self.wet[y - k * s * ny_, x - k * s * nx_]]
        if not up or not down:
            return 0.0
        return round(max(up) - min(down), 2)

    def custom_line(self, x0: int, y0: int, x1: int, y1: int) -> dict:
        """The AI's own dam/levee line (straight, along x or y): for each structure height, the pool it holds,
        what it floods, whether it leaks round the ends, and the place_line calls."""
        if x0 != x1 and y0 != y1:
            return {"error": "the line must be straight along x or along y"}
        axis = "x" if y0 == y1 else "y"
        if axis == "x":
            line = [(x, y0) for x in range(min(x0, x1), max(x0, x1) + 1)]
        else:
            line = [(x0, y) for y in range(min(y0, y1), max(y0, y1) + 1)]
        if not all(self.in_map(x, y) for x, y in line):
            return {"error": "the line leaves the map"}
        s = self._upstream(axis, line)
        if s is None:
            return {"error": "no water on either side of the line, or the flow direction is unclear"}
        nx_, ny_ = (0, 1) if axis == "x" else (1, 0)
        a = (lambda t, d: (t[0] + d, t[1])) if axis == "x" else (lambda t, d: (t[0], t[1] + d))
        end0, end1 = a(line[0], -1), a(line[-1], 1)
        bed = min(float(self.top[y, x]) for x, y in line)
        out = []
        for label, h, _ in STACKS:
            level = bed + h
            up = [(x + s * nx_, y + s * ny_) for x, y in line]
            down = {(x - s * nx_, y - s * ny_) for x, y in line} | {
                (e[0] - s * nx_, e[1] - s * ny_) for e in (end0, end1) if self.in_map(*e)}
            region, capped = self.flood(level, up, blocked=set(line))
            leaks = []
            if region & down:
                leaks.append("water goes round the ends")
            if any(x in (0, self.W - 1) or y in (0, self.H - 1) for x, y in region):
                leaks.append("the pool runs off the map edge")
            for e in (end0, end1):
                if self.in_map(*e) and float(self.crest[e[1], e[0]]) < level:
                    leaks.append(f"bank ({e[0]},{e[1]}) is below the level z{level:.2f}: extend the line")
            p = self._proposal(axis, line, end0, end1, level, label, region, capped, s)
            out.append({**{k: v for k, v in p.items() if not k.startswith("_")}, "leaks": leaks,
                        "ok": not leaks and not p["flooded"] and not capped and p["added"] > 0})
        return {"line": line, "axis": axis, "options": out}

    def dams(self, top_n: int = 8) -> dict:
        """Choke lines across water with the pool each would hold at each height, best first."""
        if ("dams", top_n) in self._cache:
            return self._cache[("dams", top_n)]
        runs = self._runs()
        width = {(r[0], r[1], a): r[3] - r[2] + 1 for r in runs for a in range(r[2], r[3] + 1)}
        cands, seen = [], set()
        for axis, f, a0, a1 in runs:
            w = a1 - a0 + 1
            near = [width.get((axis, f + d, a)) for d in (-2, -1, 1, 2) for a in range(a0, a1 + 1)]
            if any(v is not None and v < w for v in near):
                continue                                         # not a choke: a narrower cross-section is next to it
            at = (lambda a: (a, f)) if axis == "x" else (lambda a: (f, a))
            bed = min(float(self.top[at(a)[1], at(a)[0]]) for a in range(a0, a1 + 1))
            for label, h, _ in STACKS:
                level = bed + h
                ln = self._line(axis, f, a0, a1, level)
                if not ln:
                    continue
                line, end0, end1 = ln
                key = (axis, f, line[0], line[-1], round(level, 2))
                if key in seen:
                    continue
                seen.add(key)
                s = self._upstream(axis, line)
                if s is None:
                    continue
                nx_, ny_ = (0, 1) if axis == "x" else (1, 0)
                up = [(x + s * nx_, y + s * ny_) for x, y in line]
                down = {(x - s * nx_, y - s * ny_) for x, y in line} | {
                    (e[0] - s * nx_, e[1] - s * ny_) for e in (end0, end1)}
                region, capped = self.flood(level, up, blocked=set(line))
                if region & down:
                    continue                                     # leaks round the ends
                if any(x in (0, self.W - 1) or y in (0, self.H - 1) for x, y in region):
                    continue                                     # runs off the map edge (the edge drains)
                cands.append(self._proposal(axis, line, end0, end1, level, label, region, capped, s))
        ok = [c for c in cands if not c["flooded"] and not c["capped"] and c["added"] > 0]
        ok.sort(key=lambda c: -c["score"])
        kept: list[dict] = []
        for c in ok:
            reg = c["_region"]
            if all(len(reg & k["_region"]) < 0.5 * min(len(reg), len(k["_region"])) for k in kept):
                kept.append(c)
            if len(kept) >= top_n:
                break
        rejected = sorted([c for c in cands if c["flooded"] or c["capped"]], key=lambda c: -c["added"])[:5]
        out = {"proposals": kept, "rejected": rejected, "candidates": len(cands)}
        self._cache[("dams", top_n)] = out
        return out

    def _proposal(self, axis, line, end0, end1, level, label, region, capped, s) -> dict:
        eff = self.effects(region, level)
        parts, logs, unlock = [], 0, set()
        for x, y in line:
            st = self._stack(float(self.top[y, x]), level)
            if st:
                parts.append((x, y, int(self.top[y, x]), st))
                for p in st[2]:
                    logs += self.logs(p)
                    if self.unlocked(p) is False:
                        unlock.add(p)
        calls = self._line_calls(parts)
        reach = None
        if self.world.range_tiles is not None:
            reach = any(self.world.in_range(x, y, int(self.top[y, x])) for x, y in (end0, end1))
        drop = self._drop(axis, line, s)
        held = len(region & self.held_tiles())
        score = eff["added"] * GOODS_PER_UNIT / max(1, logs) * (1 + 0.5 * len(eff["pumps"])) \
            * (1.3 if drop >= 0.5 else 1.0) * (0.5 if eff["crops"] else 1.0) * (1.0 if reach is not False else 0.6)
        xs, ys = [t[0] for t in line], [t[1] for t in line]
        return {"kind": label, "axis": axis, "line": line, "bbox": (min(xs), min(ys), max(xs), max(ys)),
                "level": round(level, 2), "logs": logs, "needsUnlock": sorted(unlock), "builderReach": reach,
                "dropBelow": drop, "alreadyHeld": held, "capped": capped, **eff,
                "region": sorted(region), "_region": region, "calls": calls, "score": round(score, 2),
                "why": (f"{label} line x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)} holds water to z{level:.2f}: "
                        f"+{eff['added']} units (~{eff['goods']} water) over {eff['tiles']} tiles, mean depth "
                        f"{eff['meanDepth']} (~{eff['droughtDays']} days of evaporation), {logs} logs"
                        + (f", serves pumps {', '.join(eff['pumps'])}" if eff["pumps"] else "")
                        + (f", {drop} drop below it" if drop >= 0.3 else "")
                        + (f", floods {eff['crops']} crop plots" if eff["crops"] else "")
                        + (", NO builder access from the district" if reach is False else "")
                        + (f"; needs {', '.join(sorted(unlock))} unlocked" if unlock else ""))}

    def _line_calls(self, parts) -> list[str]:
        """place_line calls for a line, one per straight run of the same structure at the same height."""
        layers: dict = {}
        for x, y, z, (_, _, stack) in parts:
            for i, name in enumerate(stack):
                layers.setdefault((name, z + i), []).append((x, y))
        calls = []
        for (name, z), tiles in sorted(layers.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            tiles.sort()
            run = [tiles[0]]
            for t in tiles[1:] + [None]:
                if t and abs(t[0] - run[-1][0]) + abs(t[1] - run[-1][1]) == 1 and (t[0] == run[0][0] or t[1] == run[0][1]):
                    run.append(t)
                    continue
                (x0, y0), (x1, y1) = run[0], run[-1]
                calls.append(f'place_line(template="{self.tpl(name)}", x0={x0}, y0={y0}, x1={x1}, y1={y1}, z={z})')
                run = [t] if t else []
        return calls

    # ------------------------------------------------------------------ badwater planner
    def badwater(self) -> dict:
        """Where badwater goes, what clean water and land it reaches, and the lines that would stop it."""
        if "bad" in self._cache:
            return self._cache["bad"]
        bad_bodies = [b for b in self.bodies if b["dirt"] >= 0.5]
        reaches = []
        for b in bad_bodies:
            clean = [d for d in self.downstream(b["id"]) - {b["id"]} if self.bodies[d]["dirt"] < 0.5]
            junction = []
            for c in b["cells"]:
                for n, _ in self._neighbours(c):
                    if n in self.cells and self.body_of[n] in clean:
                        junction.append(n[:2])
            if clean:
                reaches.append({"bad": b["id"], "clean": clean[:6], "junction": sorted(set(junction))[:20],
                                "cleanTiles": sum(self.bodies[d]["tiles"] for d in clean)})
        mixing = []
        for b in self.bodies:
            fed = b["fedBy"]
            if any(f.startswith("Bad") for f in fed) and any(not f.startswith("Bad") for f in fed):
                xs, ys = [c[0] for c in b["cells"]], [c[1] for c in b["cells"]]
                mixing.append({"body": b["id"], "tiles": b["tiles"], "dirt": b["dirt"], "fedBy": sorted(fed),
                               "bbox": (min(xs), min(ys), max(xs), max(ys))})
        # Soil at risk: Dijkstra from bad surface water, +1 step per tile, +5 per height climbed, up to 7.
        dist: dict = {}
        heap = []
        for y in range(self.H):
            for x in range(self.W):
                if self.wet[y, x] and self.dirt[y, x] >= BAD:
                    dist[(x, y)] = 0
                    heap.append((0, x, y))
        heapq.heapify(heap)
        while heap:
            d, x, y = heapq.heappop(heap)
            if d > dist.get((x, y), 99):
                continue
            for dx, dy in N4:
                nx_, ny_ = x + dx, y + dy
                if not self.in_map(nx_, ny_):
                    continue
                nd = d + 1 + 5 * max(0, int(self.top[ny_, nx_] - self.top[y, x]))
                if nd <= CONTAM_REACH and nd < dist.get((nx_, ny_), 99):
                    dist[(nx_, ny_)] = nd
                    heapq.heappush(heap, (nd, nx_, ny_))
        risk = {t for t, d in dist.items() if d > 0}
        crops = sorted(t for t, (_, plant) in (self.world.planting or {}).items() if t in risk and plant in CROPS)
        bank = sorted(t for t in risk if dist[t] == 1 and any(
            abs(t[0] - c[0]) + abs(t[1] - c[1]) <= CONTAM_REACH for c in crops)) if crops else []
        barrier = "IrrigationBarrier" if "IrrigationBarrier" in self.templates else "ContaminationBarrier"
        pumps = []
        for b, tiles in self.footprints():
            if b.name in PUMPS and any(self.in_map(x + dx, y + dy) and self.wet[y + dy, x + dx]
                                       and self.dirt[y + dy, x + dx] >= 0.05 for x, y in tiles for dx, dy in N8):
                pumps.append(b.label)
        upcoming = [g for g in self.source_groups if g["bad"] or g["name"] in ("BadwaterSource", "BadtideDrain")]
        diversions = []
        for r in reaches[:4]:
            for jx, jy in r["junction"][:3]:
                for axis in ("x", "y"):
                    for label, h, _ in STACKS[1:3]:
                        level = float(self.top[jy, jx]) + h
                        ln = self._line(axis, jy if axis == "x" else jx, jx if axis == "x" else jy,
                                        jx if axis == "x" else jy, level)
                        if not ln:
                            continue
                        line, e0, e1 = ln
                        s = self._upstream(axis, line)
                        if s is None:
                            continue
                        nx_, ny_ = (0, 1) if axis == "x" else (1, 0)
                        up = [(x + s * nx_, y + s * ny_) for x, y in line]
                        region, capped = self.flood(level, up, blocked=set(line))
                        p = self._proposal(axis, line, e0, e1, level, label, region, capped, s)
                        p["blocks"] = f"badwater W{r['bad']} into clean {', '.join(f'W{c}' for c in r['clean'][:3])}"
                        diversions.append(p)
                        break
        seen_lines = set()
        diversions = [p for p in diversions if not (tuple(map(tuple, p["line"])) in seen_lines
                                                    or seen_lines.add(tuple(map(tuple, p["line"]))))]
        diversions.sort(key=lambda p: (len(p["flooded"]), p["logs"]))
        out = {"bodies": [b["id"] for b in bad_bodies], "reaches": reaches, "mixing": mixing, "riskTiles": len(risk),
               "cropsAtRisk": crops, "barrierTemplate": self.tpl(barrier),
               "barrierLine": bank[:60], "badPumps": pumps, "sources": upcoming, "diversions": diversions[:4],
               "riskSet": risk}
        self._cache["bad"] = out
        return out

    # ------------------------------------------------------------------ reservoirs, ponds, decks, pumps, wheels
    def reservoirs(self, top_n: int = 8) -> list[dict]:
        """Dry bowls and craters (priority-flood depressions): volume, depth, evaporation and fill time."""
        if ("res", top_n) in self._cache:
            return self._cache[("res", top_n)]
        W, H = self.W, self.H
        level = np.full((H, W), np.inf, dtype=np.float32)
        heap, done = [], np.zeros((H, W), bool)
        lift = np.maximum(self.surface, self.crest)
        for y in range(H):
            for x in range(W):
                if (x in (0, W - 1) or y in (0, H - 1)) and self.top[y, x] >= 0:
                    level[y, x] = lift[y, x]
                    heap.append((float(lift[y, x]), x, y))
                    done[y, x] = True
        heapq.heapify(heap)
        while heap:
            h, x, y = heapq.heappop(heap)
            for dx, dy in N4:
                nx_, ny_ = x + dx, y + dy
                if 0 <= nx_ < W and 0 <= ny_ < H and not done[ny_, nx_] and self.top[ny_, nx_] >= 0:
                    done[ny_, nx_] = True
                    level[ny_, nx_] = max(h, float(lift[ny_, nx_]))
                    heapq.heappush(heap, (float(level[ny_, nx_]), nx_, ny_))
        fill = level - self.top
        mask = (fill >= 1.0) & ~self.wet
        seen = np.zeros((H, W), bool)
        out = []
        dc = self.world.dc
        for y in range(H):
            for x in range(W):
                if not mask[y, x] or seen[y, x]:
                    continue
                comp, queue = [], deque([(x, y)])
                seen[y, x] = True
                while queue:
                    cx, cy = queue.popleft()
                    comp.append((cx, cy))
                    for dx, dy in N4:
                        nx_, ny_ = cx + dx, cy + dy
                        if 0 <= nx_ < W and 0 <= ny_ < H and mask[ny_, nx_] and not seen[ny_, nx_]:
                            seen[ny_, nx_] = True
                            queue.append((nx_, ny_))
                if len(comp) < 4:
                    continue
                lvl = float(max(level[cy, cx] for cx, cy in comp))
                eff = self.effects(set(comp), lvl)
                xs, ys = [c[0] for c in comp], [c[1] for c in comp]
                near_water = any(self.in_map(cx + dx, cy + dy) and self.wet[cy + dy, cx + dx]
                                 for cx, cy in comp for dx, dy in N8)
                above_base = round(lvl - dc.z, 1) if dc else None
                fill_days = round(eff["volume"] / DISCHARGE_PER_DAY, 1)
                evap = round(len(comp) * EVAPORATION, 1)
                out.append({"kind": "bowl", "cells": comp, "bbox": (min(xs), min(ys), max(xs), max(ys)),
                            "level": round(lvl, 2), **eff, "aboveBase": above_base, "nextToWater": near_water,
                            "dischargeFillDays": fill_days, "evaporationPerDay": evap,
                            "why": (f"bowl x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)}: {len(comp)} tiles fill to "
                                    f"z{lvl:.1f} (mean depth {eff['meanDepth']}), {eff['volume']} units (~"
                                    f"{round(eff['volume'] * GOODS_PER_UNIT)} water), loses ~{evap}/day to "
                                    f"evaporation; one Discharge fills it in >= {fill_days} days"
                                    + (f"; floods {', '.join(eff['flooded'][:4])}" if eff["flooded"] else "")
                                    + (f"; {above_base:+} vs the DC" if above_base is not None else "")
                                    + ("" if near_water else "; sealed: no water next to it (check with underground.py)"))})
        out.sort(key=lambda r: (bool(r["flooded"]), -r["volume"]))
        self._cache[("res", top_n)] = out[:top_n]
        return self._cache[("res", top_n)]

    def dry_farmland(self, min_tiles: int = 20) -> list[dict]:
        """Dry, clean, flat ground in the district range far from water: where a Discharge pond would help."""
        if "dry" in self._cache:
            return self._cache["dry"]
        rng = self.world.range_tiles
        mo = self.world.moist
        built = {t for _, tiles in self.footprints() for t in tiles}
        ok = np.zeros((self.H, self.W), bool)
        for y in range(self.H):
            for x in range(self.W):
                if mo[y, x] == " " and not self.wet[y, x] and (x, y) not in built and self.top[y, x] >= 0 \
                        and (rng is None or self.world.in_range(x, y, int(self.top[y, x]))):
                    ok[y, x] = True
        seen = np.zeros_like(ok)
        out = []
        for y in range(self.H):
            for x in range(self.W):
                if not ok[y, x] or seen[y, x]:
                    continue
                z = self.top[y, x]
                comp, queue = [], deque([(x, y)])
                seen[y, x] = True
                while queue:
                    cx, cy = queue.popleft()
                    comp.append((cx, cy))
                    for dx, dy in N4:
                        nx_, ny_ = cx + dx, cy + dy
                        if 0 <= nx_ < self.W and 0 <= ny_ < self.H and ok[ny_, nx_] and not seen[ny_, nx_] \
                                and self.top[ny_, nx_] == z:
                            seen[ny_, nx_] = True
                            queue.append((nx_, ny_))
                if len(comp) < min_tiles:
                    continue
                cx = round(sum(c[0] for c in comp) / len(comp))
                cy = round(sum(c[1] for c in comp) / len(comp))
                px, py = min(comp, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
                xs, ys = [c[0] for c in comp], [c[1] for c in comp]
                out.append({"tiles": len(comp), "z": int(z), "bbox": (min(xs), min(ys), max(xs), max(ys)),
                            "pond": (px, py, int(z)),
                            "why": (f"{len(comp)} dry tiles at z{int(z)} x{min(xs)}-{max(xs)} y{min(ys)}-{max(ys)}: "
                                    f"a 3x3 Levee pond + Discharge near ({px},{py}) would moisten them "
                                    f"(knowledge/03 3c; reach of a small pond is unverified, check the moisture grid after)")})
        out.sort(key=lambda d: -d["tiles"])
        self._cache["dry"] = out[:8]
        return self._cache["dry"]

    def decks(self, top_n: int = 8) -> list[dict]:
        """Shallow clean water next to the district where a Platform deck adds build space."""
        if ("decks", top_n) in self._cache:
            return self._cache[("decks", top_n)]
        built = {t for _, tiles in self.footprints() for t in tiles}
        ok = (self.wet & (self.dirt < 0.05) & (self.depth <= PLATFORM_DRY)).copy()
        for x, y in list(built) + list(self.obstacle):
            if 0 <= x < self.W and 0 <= y < self.H:
                ok[y, x] = False
        rng = self.world.range_tiles
        if rng is not None:
            near = np.zeros_like(ok)
            for x, y, _ in rng:
                if 0 <= x < self.W and 0 <= y < self.H:
                    near[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = True
            ok &= near
        out, used = [], np.zeros_like(ok)
        for _ in range(top_n):
            best = _max_rect(ok & ~used, self.top)
            if not best or best[0] < 4:
                break
            area, x0, y0, x1, y1 = best
            used[y0:y1 + 1, x0:x1 + 1] = True
            z = int(self.top[y0, x0])
            depth = float(self.depth[y0:y1 + 1, x0:x1 + 1].max())
            out.append({"bbox": (x0, y0, x1, y1), "tiles": area, "z": z, "deckZ": z + 1, "maxDepth": round(depth, 2),
                        "calls": [f'place_area(template="{self.tpl("Platform")}", x0={x0}, y0={y0}, x1={x1}, y1={y1}, z={z})'],
                        "why": (f"{x1 - x0 + 1}x{y1 - y0 + 1} clean water x{x0}-{x1} y{y0}-{y1} (bed z{z}, depth <= "
                                f"{depth:.2f}): Platforms make a deck at z{z + 1}; put a Path on it and build there "
                                f"(a dam raising this water over z{z + 0.85:.2f} would flood the deck)")})
        self._cache[("decks", top_n)] = out
        return out

    def pump_sites(self) -> dict:
        """Clean water deep enough for a pump intake beside dry, reachable bank (or a deck)."""
        if "pumps" in self._cache:
            return self._cache["pumps"]
        built = {t for _, tiles in self.footprints() for t in tiles}
        held = self.held_tiles()
        sites = []
        taken: list = []
        for y in range(self.H):
            for x in range(self.W):
                if not (self.wet[y, x] and self.dirt[y, x] < 0.05 and self.depth[y, x] >= 0.5):
                    continue
                for dx, dy in N4:
                    bx, by = x + dx, y + dy
                    if not self.in_map(bx, by) or self.wet[by, bx] or (bx, by) in built:
                        continue
                    z = int(self.top[by, bx])
                    if z - self.surface[y, x] > DEEP_PUMP_REACH:
                        continue
                    if self.world.in_range(bx, by, z) is False:
                        continue
                    if any(abs(bx - tx) + abs(by - ty) < 4 for tx, ty in taken):
                        continue
                    taken.append((bx, by))
                    sites.append({"bank": (bx, by, z), "water": (x, y), "depth": round(float(self.depth[y, x]), 2),
                                  "held": (x, y) in held})
                    break
        sites.sort(key=lambda s: (not s["held"], -s["depth"]))
        pumps = [b for b in self.world.buildings if b.name in PUMPS]
        out = {"sites": sites[:30], "count": len(sites), "pumps": len(pumps)}
        self._cache["pumps"] = out
        return out

    def wheel_sites(self, top_n: int = 10) -> list[dict]:
        """Fastest-flowing water (bridge flow speed x10): where water wheels turn best."""
        out = []
        built = {t for _, tiles in self.footprints() for t in tiles}
        for y in range(self.H):
            row = self.speed[y]
            for x in range(self.W):
                c = row[x]
                if c in " .":
                    continue
                v = dec(c) / 10
                if v >= 0.3 and (x, y) not in built and self.world.in_range(x, y, int(self.top[y, x])) is not False:
                    out.append({"x": x, "y": y, "z": int(self.top[y, x]), "speed": v, "dir": self.flow[y][x],
                                "bad": bool(self.dirt[y, x] >= BAD)})
        out.sort(key=lambda s: -s["speed"])
        picked = []
        for s in out:
            if all(abs(s["x"] - p["x"]) + abs(s["y"] - p["y"]) >= 4 for p in picked):
                picked.append(s)
            if len(picked) >= top_n:
                break
        return picked

    # ------------------------------------------------------------------ cores and barriers (underground.py)
    def cores(self) -> list[dict]:
        out = []
        dc = self.world.dc
        basexy = (dc.x + 1.5, dc.y + 1.5) if dc else (self.W / 2, self.H / 2)
        feats = self.world.features or []
        others = [f for f in feats if base(f["name"]) in ("NaturalDam", "Blockage", "WaterSource", "BadwaterSource",
                                                         "WaterSeep", "UnstableCore", "Dynamite")]
        for f in feats:
            if not f["name"].startswith("UnstableCore"):
                continue
            st = f.get("state") or {}
            rad = st.get("UnstableCore.ExplosionRadius", 3)
            r = rad + st.get("UnstableCore.InnerRadius", 1.0)       # game code: ExplosionRadius + InnerRadius
            ox, oy = CENTRE.get(f.get("orientation", 0), (1, 1))
            cx, cy, cz = f["x"] + ox, f["y"] + oy, f["z"]
            cyc = st.get("TimedComponentActivator.CyclesUntilCountdownActivation")
            days = st.get("TimedComponentActivator.DaysUntilActivation")
            removed = set(_sphere(cx, cy, cz, r))
            hit: dict = {}
            for vx, vy, vz in removed:
                for dx, dy, dz in ((0, 0, 0), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, -1), (0, 0, 1)):
                    for lv in self.cols.get((vx + dx, vy + dy), ()):
                        c = (vx + dx, vy + dy, lv[0])
                        if c in self.cells and c[2] <= vz + dz < self.cell_surface(c) + 1:
                            hit.setdefault(self.body_of[c], set()).add(c)
            effects = []
            for bid in hit:
                b = self.bodies[bid]
                opened = [c for c in b["full"] if any((c[0], c[1], z) in removed for z in range(c[2], c[2] + 3))]
                effects.append(f"hits W{bid} ({b['tiles']} tiles, head z{b['head']}, "
                               f"{'badwater' if b['dirt'] >= 0.5 else 'clean'})"
                               + (f", opens the roof over {len(opened)} pressurised tiles" if opened else ""))
            if len(hit) > 1:
                hs = [self.bodies[b] for b in hit]
                bad = [b for b in hs if b["dirt"] >= 0.05]
                effects.append(f"joins {len(hit)} bodies (head difference "
                               f"{max(b['head'] for b in hs) - min(b['head'] for b in hs):.1f})"
                               + ("; BADWATER mixes into clean water" if bad and len(bad) < len(hs) else ""))
            cut: dict = {}
            for vx, vy, vz in removed:
                top = self.cols.get((vx, vy))
                if top and vz < top[-1][0]:
                    cut.setdefault((vx, vy), []).append(vz)
            newtop = {k: min(v) for k, v in cut.items() if max(v) + 1 >= self.cols[k][-1][0]}
            for bid in hit:
                b = self.bodies[bid]
                head = max(self.cell_surface(c) for c in hit[bid])
                start = [k for k, v in newtop.items() if v < head - 0.2]
                if not start:
                    continue
                area = _flood_area(self, start, head, newtop)
                outside = [a for a in area if a not in newtop]
                if outside:
                    effects.append(f"NEW OUTLET: W{bid} runs out over {len(outside)} lower tiles"
                                   + (" - REACHES THE BASE" if any(math.dist(a, basexy) < 12 for a in area) else "")
                                   + (f"; fed by {', '.join(sorted(b['fedBy']))}" if b["fedBy"] else
                                      f"; one-off volume {b['volume']}"))
            near = [o for o in others if o is not f and math.dist((o["x"] + .5, o["y"] + .5, o["z"] + .5), (cx, cy, cz)) <= r + 1.5]
            if any(base(o["name"]) in ("UnstableCore", "Dynamite") for o in near):
                effects.append("CHAIN REACTION possible")
            blds = [b.label for b in self.world.buildings
                    if math.dist((b.x + .5, b.y + .5, b.z + .5), (cx, cy, cz)) <= r + 1]
            if blds:
                effects.append(f"buildings in range: {', '.join(blds[:8])}")
            out.append({"x": f["x"], "y": f["y"], "z": f["z"], "radius": rad, "sphere": r, "countdownCycle": cyc,
                        "daysAfter": days, "fromBase": round(math.dist((cx, cy), basexy)),
                        "effects": effects or ["no water, dams, sources or buildings in range: crater only"]})
        out.sort(key=lambda c: (c["countdownCycle"] if isinstance(c["countdownCycle"], (int, float)) else 99))
        return out

    def barriers(self) -> list[dict]:
        groups: dict = {}
        for f in self.world.features or []:
            name = base(f["name"])
            if name not in ("NaturalDam", "Blockage"):
                continue
            sides = {}
            for dx, dy in N4:
                for lv in self.cols.get((f["x"] + dx, f["y"] + dy), ()):
                    c = (f["x"] + dx, f["y"] + dy, lv[0])
                    if c in self.cells and f["z"] - 2 <= c[2] <= f["z"] + 2:
                        bid = self.body_of[c]
                        sides[bid] = max(sides.get(bid, 0), self.cell_surface(c))
            g = groups.setdefault((name, f["z"], f["x"] // 4, f["y"] // 4),
                                  {"name": name, "z": f["z"], "tiles": [], "sides": {}})
            g["tiles"].append((f["x"], f["y"]))
            for bid, h in sides.items():
                g["sides"][bid] = max(g["sides"].get(bid, 0), h)
        out = []
        for g in groups.values():
            hs = list(g["sides"].values())
            verdict = ("dry on all sides (holds nothing now)" if not hs else
                       f"holds a {max(hs) - min(hs):.1f} drop" if len(hs) > 1 else
                       f"water on one side only (z{hs[0]:.1f}): removing it lets that water out over z{g['z']}")
            xs, ys = [t[0] for t in g["tiles"]], [t[1] for t in g["tiles"]]
            out.append({"name": g["name"], "z": g["z"], "bbox": (min(xs), min(ys), max(xs), max(ys)),
                        "sides": {f"W{b}": round(h, 2) for b, h in g["sides"].items()}, "verdict": verdict})
        return out

    # ------------------------------------------------------------------ summaries
    def body_rows(self, n: int = 30) -> list[dict]:
        rows = []
        for b in sorted(self.bodies, key=lambda b: -b["tiles"])[:n]:
            rows.append({k: (sorted(v) if isinstance(v, set) else v) for k, v in b.items() if k not in ("cells", "full")}
                        | {"pressurised": len(b["full"])})
        return rows

    def held_volume(self) -> float:
        return round(sum(max(0.0, p["observed"]) for p in self.pools()), 1)


def _sphere(cx, cy, cz, r):
    for vz in range(int(cz - r) - 1, int(cz + r) + 2):
        for vy in range(int(cy - r) - 1, int(cy + r) + 2):
            for vx in range(int(cx - r) - 1, int(cx + r) + 2):
                if math.dist((vx + 0.5, vy + 0.5, vz + 0.5), (cx, cy, cz)) <= r:
                    yield vx, vy, vz


def _flood_area(h: Hydro, starts, head, newtop, limit=4000):
    height = lambda p: newtop.get(p, h.cols[p][-1][0] if p in h.cols else 1e9)
    seen, queue = set(starts), deque(starts)
    while queue and len(seen) < limit:
        cx, cy = queue.popleft()
        for dx, dy in N4:
            n = (cx + dx, cy + dy)
            if n not in seen and n in h.cols and height(n) < head:
                seen.add(n)
                queue.append(n)
    return seen


def _max_rect(mask: np.ndarray, top: np.ndarray):
    """Largest all-True rectangle on one bed height (histogram method). (area, x0, y0, x1, y1) or None."""
    H, W = mask.shape
    best = None
    for z in np.unique(top[mask]) if mask.any() else []:
        m = mask & (top == z)
        heights = np.zeros(W, int)
        for y in range(H):
            heights = np.where(m[y], heights + 1, 0)
            stack: list = []
            for x in range(W + 1):
                hgt = heights[x] if x < W else 0
                start = x
                while stack and stack[-1][1] >= hgt:
                    s, sh = stack.pop()
                    area = sh * (x - s)
                    if sh and (best is None or area > best[0]):
                        best = (int(area), s, y - sh + 1, x - 1, y)
                    start = s
                stack.append((start, hgt))
    return best
