"""World model, 2.5D (phase 1): surface grids, building registry, road graph and power networks.

Built from one collector state. Heights are standing levels (same z as view_map and building z).
The full voxel model with caves and overhangs comes in phase 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from .collector import base

DIGITS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
# Tiles beavers walk on that join the district road network.
ROAD = ("Path",)
CROSSINGS = ("Dam", "Levee", "Floodgate")      # walkable tops (observed: beavers cross dams)
CONNECTORS = ("Stairs", "SpiralStairs", "Slope")  # join z and z+1
STORES = ("Warehouse", "Pile", "Tank")


def dec(ch: str) -> int:
    i = DIGITS.find(ch)
    return i if i >= 0 else -1


@dataclass
class Building:
    id: str
    name: str            # template without faction suffix
    template: str
    x: int
    y: int
    z: int
    finished: bool
    raw: dict = field(repr=False)

    @property
    def label(self) -> str:
        return f"{self.name}({self.x},{self.y})"

    @property
    def door(self) -> tuple[int, int, int] | None:
        p = self.raw.get("pathTile")
        return tuple(p) if p else None


class World:
    def __init__(self, state: dict):
        self.state = state
        self.colony = state["colony"]
        self.goods = {g["id"]: g for g in state["goods"]}
        self.needs = state.get("needs") or []
        self.buildings = [Building(b["id"], base(b["template"]), b["template"], b["x"], b["y"], b["z"],
                                   b["finished"], b) for b in state.get("buildings") or []]
        self.by_id = {b.id: b for b in self.buildings}
        pop = self.colony["population"]
        self.beavers = pop.get("adults", 0) + pop.get("children", 0)
        self._grids(state.get("map"))
        self._roads()
        self._views(state)

    # ------------------------------------------------------------ grids
    def _grids(self, m: dict | None) -> None:
        self.has_map = bool(m)
        if not m:
            self.w = self.h = 0
            return
        self.w, self.h = m["size"]["width"], m["size"]["height"]

        def grid(key, fn, dtype):
            return np.array([[fn(c) for c in row] for row in m[key]], dtype=dtype)
        self.top = grid("top", dec, np.int16)                                     # standing level, -1 off map
        self.depth = grid("water", lambda c: 0.0 if c == " " else dec(c) / 10, np.float32)
        self.dirt = grid("contamination", lambda c: 0.0 if c == " " else dec(c) / 9, np.float32)
        self.moist = grid("moist", lambda c: c, "U1")                              # '#' moist, 'x' contaminated, 'w' water, ' ' dry
        self.objects = m["objects"]
        self.legend = m["legend"]
        self.features = m["features"]
        self.sources = m.get("sources")

    def object_at(self, x: int, y: int) -> str | None:
        if not self.has_map or not (0 <= x < self.w and 0 <= y < self.h):
            return None
        c = self.objects[y][x]
        return self.legend.get(c) if c not in " ." else None

    def in_map(self, x: int, y: int) -> bool:
        return self.has_map and 0 <= x < self.w and 0 <= y < self.h

    def badwater_near(self, x: int, y: int, r: int = 2, share: float = 0.05) -> bool:
        if not self.has_map:
            return False
        y0, y1, x0, x1 = max(0, y - r), min(self.h, y + r + 2), max(0, x - r), min(self.w, x + r + 2)  # audit.py: x-2..x+3
        sub_d, sub_c = self.depth[y0:y1, x0:x1], self.dirt[y0:y1, x0:x1]
        return bool(((sub_d > 0) & (sub_c >= share)).any())

    # ------------------------------------------------------------ roads
    def _roads(self) -> None:
        """Road graph over (x, y, z) standing tiles: paths, crossings, stairs/slopes (z <-> z+1)."""
        g = nx.Graph()
        kind = {}
        for b in self.buildings:
            if not b.finished:
                continue
            if b.name in ROAD or b.name in CROSSINGS:
                kind[(b.x, b.y, b.z)] = "road" if b.name in ROAD else "crossing"
            elif b.name in CONNECTORS:
                kind[(b.x, b.y, b.z)] = "connector"
        for f in self.features if self.has_map else []:
            if base(f["name"]) == "Slope":
                kind.setdefault((f["x"], f["y"], f["z"]), "connector")
        # Dams/levees stand on z and their walkable top is z+1; the tile's road level is one up.
        nodes = {}
        for (x, y, z), k in kind.items():
            nodes[(x, y, z + 1 if k == "crossing" else z)] = k
        for n, k in nodes.items():
            g.add_node(n, kind=k)
        for (x, y, z), k in nodes.items():
            for dx, dy in ((1, 0), (0, 1)):
                for dz in (-1, 0, 1):
                    other = (x + dx, y + dy, z + dz)
                    if other not in nodes:
                        continue
                    if dz == 0 or "connector" in (k, nodes[other]):
                        g.add_edge((x, y, z), other)
        self.road = g
        self.dc = next((b for b in self.buildings if b.name == "DistrictCenter" and b.finished and b.door), None)
        self.road_component: set = set()
        if self.dc and self.dc.door in g:
            self.road_component = nx.node_connected_component(g, self.dc.door)
        sub = g.subgraph(self.road_component)
        self.only_links = set(nx.articulation_points(sub)) if sub.number_of_nodes() > 2 else set()

    def door_connected(self, b: Building) -> bool | None:
        """True if the building's door tile is on the district's road component (own flood fill)."""
        if not b.door or not self.dc:
            return None
        x, y, z = b.door
        return any((x, y, z + dz) in self.road_component for dz in (0, -1, 1))

    # ------------------------------------------------------------ Foreman bridge views
    def _views(self, state: dict) -> None:
        """Optional reads from the bridge's ForemanModule (None on an older bridge: monitors skip)."""
        self.production = {p["id"]: p for p in state.get("production") or []}
        self.sites = {s["id"]: s for s in state.get("sites") or []} if state.get("sites") is not None else None
        self.stock: dict[str, list] = {}
        for inv in state.get("stock") or []:
            self.stock.setdefault(inv["id"], []).append(inv)
        # Power: keep networks with a generator or a consumer (lone transput nodes are noise).
        self.networks = [n for n in state.get("power") or []
                         if n["generators"] or any(m["role"] == "consumer" for m in n["members"])]
        self.network_of = {m["id"]: n for n in self.networks for m in n["members"]}
        rng = state.get("range")
        self.range_roads: dict | None = None
        self.range_tiles: set | None = None
        if rng:
            self.range_roads = {tuple(r[:3]): r[3] for d in rng for r in d.get("roads", [])}
            self.range_tiles = set(self.range_roads) | {tuple(t) for d in rng for t in d.get("spill", [])}
        marks = state.get("marks")
        self.cutting = {(c[0], c[1]): (c[2], bool(c[3])) for c in marks["cutting"]} if marks else None
        self.planting = {(p[0], p[1]): (p[2], p[3]) for p in marks["planting"]} if marks else None
        self.beaver_list = state.get("beavers")
        self.blueprints = state.get("blueprints")
        self._sizes = None
        self.plant_blocks = state.get("plants")
        reach = state.get("reach")
        # Work range per template (the game's BuildingTerrainRange: walking distance from each door).
        self.reach_union = {base(k): {tuple(t) for t in v} for k, v in reach["union"].items()} if reach else None
        self.reach = {r["id"]: r for r in reach["buildings"]} if reach else {}
        self.health = state.get("health")
        self.hours = state.get("hours")          # {hours, endsAt, now, working} or None (older bridge)

    def in_range(self, x: int, y: int, z: int) -> bool | None:
        """True if (x, y, z) is in the district range (roads plus terrain spill); None if unknown."""
        if self.range_tiles is None:
            return None
        return any((x, y, z + dz) in self.range_tiles for dz in (0, -1, 1))

    def reaches(self, names: tuple[str, ...], x: int, y: int, z: int) -> bool | None:
        """True if any finished building of these templates works the tile; None if unknown (older bridge)."""
        if self.reach_union is None:
            return None
        return any((x, y, z) in self.reach_union.get(n, ()) for n in names)

    # ------------------------------------------------------------ power
    def power_networks(self) -> dict:
        """Finished powered buildings per network: keyed by network id when the bridge gives it,
        else by live network supply (networks with equal supply then merge)."""
        nets: dict = {}
        for b in self.buildings:
            pw = b.raw.get("power")
            if b.finished and pw:
                n = self.network_of.get(b.id)
                nets.setdefault(n["id"] if n else pw.get("networkSupply"), []).append(b)
        return nets

    # ------------------------------------------------------------ helpers
    def good(self, gid: str) -> dict:
        return self.goods.get(gid, {"id": gid, "available": 0, "total": 0, "capacity": 0})

    def size_of(self, b: Building) -> tuple[int, int, int]:
        """Blueprint size (x, y, height) before rotation; (1, 1, 1) when unknown."""
        if self._sizes is None:
            self._sizes = {base(bp["template"]): tuple(bp.get("size") or (1, 1, 1)) for bp in self.blueprints or []}
        return self._sizes.get(b.name, (1, 1, 1))

    def footprint(self, b: Building) -> list[tuple[int, int]]:
        """Tiles a building covers. (x, y) is the pivot corner; rotation turns the local offsets the same
        way h.door_tile turns the entrance (knowledge/06: a Barrack at (75,46) ori 2 covers x73-75 y45-46)."""
        sx, sy, _ = self.size_of(b)
        o = (b.raw.get("orientation") or 0) % 4
        out = []
        for i in range(sx):
            for j in range(sy):
                out.append([(b.x + i, b.y + j), (b.x + j, b.y - i), (b.x - i, b.y - j), (b.x - j, b.y + i)][o])
        return out

    def finished(self, *names: str) -> list[Building]:
        return [b for b in self.buildings if b.finished and (not names or b.name in names)]

    def game_day(self) -> float:
        tm = self.colony["time"]
        return tm["cycle"] * 100 + tm["cycleDay"] + tm.get("dayProgress", 0)
