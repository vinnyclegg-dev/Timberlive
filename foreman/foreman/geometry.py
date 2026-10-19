"""Blueprint geometry and a simulated occupancy model, shared by the checker and the masterplan.

Rotation follows the harness (h.door_tile) and World.footprint: (x, y) is the pivot corner and a local offset
(i, j) turns to (x+i, y+j), (x+j, y-i), (x-i, y-j), (x-j, y+i) for orientation 0..3 (knowledge/06).
District range: road tiles joined to the District Centre plus terrain within NavigationDistance.DistrictTerrain
= 10 of them [decompiled Timberborn.Navigation/NavigationDistance.cs]; measured on S2E1 every spill tile is
within Chebyshev distance 9 of a road, so SPILL = 9 when the bridge's own range is not available.
"""

from __future__ import annotations

from collections import deque

from .collector import base

SPILL = 9
CROSSINGS = ("Dam", "Levee")                       # walkable tops (a Path on top makes it a district link)
CONNECTORS = ("Stairs", "SpiralStairs", "Slope")
SUPPORTS = ("Platform", "DoublePlatform", "TriplePlatform", "MetalPlatform3x3", "MetalPlatform5x5", "Dam", "Levee",
            "Overhang2x1", "Overhang3x1", "Overhang4x1", "Overhang5x1", "Overhang6x1")
WATER_OK = ("Dam", "Levee", "Floodgate", "DoubleFloodgate", "TripleFloodgate", "Platform", "DoublePlatform",
            "TriplePlatform", "CompactWaterWheel", "LargeWaterWheel", "IrrigationBarrier", "ImpermeableFloor",
            "PowerShaft", "ImpermeablePowerShaft", "Stairs", "Path", "SuspensionBridge1x1", "SuspensionBridge2x1",
            "SuspensionBridge3x1", "SuspensionBridge4x1", "SuspensionBridge5x1", "SuspensionBridge6x1",
            "FillValve", "ThrottlingValve", "Discharge")
PLANTS = ("Birch", "Pine", "Oak", "Maple", "ChestnutTree", "Mangrove", "BlueberryBush", "Kohlrabi", "Corn", "Canola",
          "Cassava", "Soybean", "Eggplant", "Potato", "Carrot", "Wheat", "Sunflower", "Dandelion", "Spadderdock",
          "CoffeeBush", "CattailCrop", "Succulent", "Thorns")
TREES = ("Birch", "Pine", "Oak", "Maple", "ChestnutTree", "Mangrove")
# Store types (knowledge/09 and lessons 08 c3d7, S2 c7d21): piles hold only these, tanks only liquids.
PILE_GOODS = {"Log", "Plank", "TreatedPlank", "ScrapMetal", "MetalBlock", "Dirt"}
LIQUIDS = {"Water", "Badwater", "Extract", "CanolaOil", "Coffee", "Grease", "Antidote", "Biofuel", "Catalyst",
           "MapleSyrup", "Syrup"}
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def rot(x: int, y: int, o: int, i: int, j: int) -> tuple[int, int]:
    return [(x + i, y + j), (x + j, y - i), (x - i, y - j), (x - j, y + i)][o % 4]


def store_kind(name: str) -> str | None:
    return "pile" if "IndustrialPile" in name else "tank" if name.endswith("Tank") else \
        "warehouse" if "Warehouse" in name else None


def good_fits(name: str, good: str) -> bool:
    kind = store_kind(name)
    if kind == "pile":
        return good in PILE_GOODS
    if kind == "tank":
        return good in LIQUIDS
    if kind == "warehouse":
        return good not in LIQUIDS and good not in ("Dirt",)
    return True


class Catalog:
    """Blueprints from the bridge: size, entrance, water input, cost, science, unlocked."""

    def __init__(self, blueprints: list | None):
        self.bp = {base(b["template"]): b for b in blueprints or []}
        self.full = {b["template"]: b for b in blueprints or []}
        fac = [t.split(".", 1)[1] for t in self.full if "." in t]
        self.faction = max(set(fac), key=fac.count) if fac else ""

    def known(self, template: str) -> bool:
        return template in self.full

    def tpl(self, name: str) -> str:
        name = base(name)
        b = self.bp.get(name)
        return b["template"] if b else (f"{name}.{self.faction}" if self.faction and name != "Path" else name)

    def get(self, name: str) -> dict:
        return self.bp.get(base(name)) or {}

    def size(self, name: str) -> tuple[int, int, int]:
        return tuple(self.get(name).get("size") or (1, 1, 1))

    def footprint(self, name: str, x: int, y: int, o: int = 0) -> list[tuple[int, int]]:
        sx, sy, _ = self.size(name)
        return [rot(x, y, o, i, j) for i in range(sx) for j in range(sy)]

    def door(self, name: str, x: int, y: int, o: int, z: int) -> tuple[int, int, int] | None:
        e = self.get(name).get("entrance")
        return (*rot(x, y, o, *e), z) if e else None

    def intake(self, name: str, x: int, y: int, o: int) -> tuple[int, int] | None:
        wi = self.get(name).get("waterInput")
        return rot(x, y, o, *wi) if wi else None

    def overhang(self, name: str, x: int, y: int, o: int) -> set:
        """Footprint tiles in the water-input row: a pump's intake row hangs over water (knowledge/06)."""
        wi = self.get(name).get("waterInput")
        if not wi:
            return set()
        sx = self.size(name)[0]
        return {rot(x, y, o, i, wi[1]) for i in range(sx)}

    def cost(self, name: str) -> dict:
        return dict(self.get(name).get("cost") or {})

    def science(self, name: str) -> int:
        return int(self.get(name).get("science") or 0)

    def unlocked(self, name: str) -> bool | None:
        b = self.get(name)
        return None if not b else bool(b.get("unlocked", True))


class Sim:
    """What the map would look like with a batch of actions applied: occupied voxels, road graph, range."""

    def __init__(self, world, catalog: Catalog | None = None, skip=()):
        self.world = world
        self.cat = catalog or Catalog(world.blueprints)
        self.vox: dict[tuple[int, int, int], str] = {}
        self.stand: dict[tuple[int, int], set] = {}           # extra standing levels from platforms, dams
        self.nodes: dict[tuple[int, int, int], str] = {}       # road nodes: road | crossing | connector
        self.placed: list[dict] = []
        for b in world.buildings:
            if b.id not in skip:
                self.add(b.name, world.footprint(b), b.z, b.label)
        for f in world.features if world.has_map else []:
            if base(f["name"]) == "Slope":
                self.nodes.setdefault((f["x"], f["y"], f["z"]), "connector")
        self.dc = world.dc or next((b for b in world.buildings if b.name == "DistrictCenter" and b.door), None)
        self._comp = None

    # ---------------------------------------------------------------- terrain
    def top(self, x: int, y: int) -> int:
        return int(self.world.top[y, x]) if self.world.in_map(x, y) else -1

    def depth(self, x: int, y: int) -> float:
        return float(self.world.depth[y, x]) if self.world.in_map(x, y) else 0.0

    def stands_at(self, x: int, y: int, z: int) -> str | None:
        """'terrain' or the structure a building at standing level z rests on at (x, y); None if unsupported."""
        if self.top(x, y) == z:
            return "terrain"
        return "structure" if z in self.stand.get((x, y), ()) else None

    # ---------------------------------------------------------------- occupancy
    def add(self, name: str, tiles, z: int, label: str) -> None:
        h = self.cat.size(name)[2] if name != "Path" else 1
        for x, y in tiles:
            if name == "Path":
                self.vox.setdefault((x, y, z), label)
                self.nodes[(x, y, z)] = "road"
                continue
            for k in range(h):
                self.vox[(x, y, z + k)] = label
            if name in SUPPORTS:
                self.stand.setdefault((x, y), set()).add(z + h)
            if name in CROSSINGS:
                self.nodes.setdefault((x, y, z + 1), "crossing")
            if name in CONNECTORS:
                self.nodes[(x, y, z)] = "connector"
        self._comp = None

    def blocked(self, tiles, z: int, height: int) -> dict:
        """(x, y) -> what already fills the volume a new building needs."""
        out = {}
        for x, y in tiles:
            for k in range(height):
                lab = self.vox.get((x, y, z + k))
                if lab:
                    out[(x, y)] = lab
                    break
        return out

    def object(self, x: int, y: int) -> str | None:
        o = self.world.object_at(x, y)
        return base(o) if o else None

    # ---------------------------------------------------------------- roads and range
    def component(self) -> set:
        """Road nodes joined to the District Centre door (World._roads edge rule, plus planned paths)."""
        if self._comp is not None:
            return self._comp
        comp: set = set()
        if self.dc and self.dc.door:
            start = [n for n in (tuple(self.dc.door),) if n in self.nodes]
            comp = set(start)
            q = deque(start)
            while q:
                x, y, z = q.popleft()
                k = self.nodes[(x, y, z)]
                for dx, dy in N4:
                    for dz in (-1, 0, 1):
                        n = (x + dx, y + dy, z + dz)
                        if n in comp or n not in self.nodes:
                            continue
                        if dz == 0 or "connector" in (k, self.nodes[n]):
                            comp.add(n)
                            q.append(n)
        self._comp = comp
        return comp

    def connected(self, x: int, y: int, z: int) -> bool:
        comp = self.component()
        return any((x, y, z + dz) in comp for dz in (0, -1, 1)) if (x, y, z) not in self.nodes else (x, y, z) in comp

    def in_range(self, x: int, y: int, z: int) -> tuple[bool, str]:
        """(in range, how it was decided): the bridge's district range, else roads + Chebyshev spill."""
        live = self.world.in_range(x, y, z)
        if live:
            return True, "district range"
        comp = set(self.component())
        if self.dc and self.dc.door:
            comp.add(tuple(self.dc.door))          # the District Centre's own range, before any road
        for (rx, ry, rz) in comp:
            if max(abs(rx - x), abs(ry - y)) <= SPILL:
                return True, "estimated (planned roads + 9 spill)"
        if live is False:
            return False, "district range"
        return False, "estimated (planned roads + 9 spill)"

    def route(self, start: tuple[int, int, int], max_len: int = 14) -> list[tuple[int, int, int]] | None:
        """Shortest run of new Path tiles on free, dry, level ground from start to the connected network."""
        comp = self.component()
        if not comp:
            return None
        sx, sy, sz = start
        prev = {(sx, sy): None}
        q = deque([(sx, sy, 0)])
        while q:
            x, y, d = q.popleft()
            for dx, dy in N4:
                nx, ny = x + dx, y + dy
                if any((nx, ny, sz + dz) in comp for dz in (0,)):
                    out = [(x, y, sz)]
                    p = prev[(x, y)]
                    while p:
                        out.append((*p, sz))
                        p = prev[p]
                    return list(reversed(out))
                if (nx, ny) in prev or d + 1 >= max_len or not self.world.in_map(nx, ny):
                    continue
                if self.stands_at(nx, ny, sz) is None or self.depth(nx, ny) > 0.05 or (nx, ny, sz) in self.vox:
                    continue
                if self.object(nx, ny):             # trees, bushes, ruins, slopes: a Path needs a clear tile
                    continue
                prev[(nx, ny)] = (x, y)
                q.append((nx, ny, d + 1))
        return None


def line_calls(template: str, tiles) -> list[str]:
    """place_line calls for (x, y, z) tiles: one call per straight run at one height."""
    tiles = sorted(dict.fromkeys(tiles), key=lambda t: (t[2], t[0], t[1]))
    out, used = [], set()
    for t in tiles:
        if t in used:
            continue
        x, y, z = t
        best = [t]
        for dx, dy in ((1, 0), (0, 1)):
            run = [t]
            k = 1
            while (x + k * dx, y + k * dy, z) in tiles and (x + k * dx, y + k * dy, z) not in used:
                run.append((x + k * dx, y + k * dy, z))
                k += 1
            if len(run) > len(best):
                best = run
        used.update(best)
        (x0, y0, _), (x1, y1, _) = best[0], best[-1]
        out.append(f'place_building(template="{template}", x={x0}, y={y0}, z={z})' if len(best) == 1 else
                   f'place_line(template="{template}", x0={x0}, y0={y0}, x1={x1}, y1={y1}, z={z})')
    return out
