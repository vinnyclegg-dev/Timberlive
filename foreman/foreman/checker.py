"""Checker (plan section 7): validate proposed harness actions before the AI runs them, verify them after.

Foreman never acts. validate() simulates a batch (roads first, then buildings, as the plan says) on a copy of
the world and returns, per action, the guard checks that failed with the exact harness call that would fix
each one. A failed check is a warning to the AI, not a block. The game's own placement check is the authority:
confirm a spot with place_building(..., check=True) or scan_spots, which never place anything.

Severity: critical = the game will refuse it or it repeats a known disaster; warn = it breaks a play rule;
info = worth knowing.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import math
from collections import Counter

from .collector import base
from .geometry import (CONNECTORS, CROSSINGS, N4, PLANTS, SUPPORTS, TREES, WATER_OK, Catalog, Sim, good_fits,
                       line_calls, store_kind)
from .monitors import POWER_USE

# Harness/MCP actions a player has on the toolbar or building panels (player-tools-only), with their
# positional parameters (harness/timberlive_mcp.py signatures).
CALLS = {
    "place_building": ["template", "x", "y", "z", "orientation", "flip"],
    "place_line": ["template", "x0", "y0", "x1", "y1", "z", "orientation"],
    "place_area": ["template", "x0", "y0", "x1", "y1", "z"],
    "plant_area": ["plant", "x0", "y0", "x1", "y1"],
    "safe_plant": ["plant", "x0", "y0", "x1", "y1", "frm"],
    "clear_planting": ["x0", "y0", "x1", "y1"],
    "demolish_resources": ["x0", "y0", "x1", "y1", "unmark"],
    "mark_tree_cutting": ["x0", "y0", "x1", "y1", "remove"],
    "unlock_building": ["template"],
    "building_action": ["building_id", "component", "action", "args"],
    "demolish": ["building_id"],
    "set_priority": ["building_id", "priority"],
    "set_workers": ["building_id", "workers"],
    "set_paused": ["building_id", "paused"],
    "set_work_hours": ["hours"],
    "set_speed": ["speed"],
    "place_on_path": ["template", "cands", "z", "good"],
    "place_near": ["template", "near", "radius", "z", "good"],
    "place_scan": ["template", "near", "radius", "z", "good", "limit"],
    "place_with_route": ["template", "cands", "z", "max_len"],
}
# Read-only or overlay calls: always fine, nothing to check.
FREE = {"ping", "get_colony", "get_goods", "list_blueprints", "list_buildings", "map_size", "view_map", "inspect_tile",
        "inspect_building", "screenshot", "list_plantables", "get_needs", "get_alerts", "list_automation", "get_camera",
        "set_camera", "working_beavers", "set_layers", "narrate", "set_plan", "add_todo", "check_todo", "start_poll",
        "poll_results", "close_poll", "announce", "map_columns", "scan_spots", "reachable", "walk_distance",
        "map_summary", "list_saves"}
# Never from the playing AI: session control that can lose the stream save, or anything outside the toolbar.
FORBIDDEN = ("dev", "cheat", "instant", "add_goods", "give", "spawn", "teleport", "set_goods", "kill", "load_save",
             "new_game", "save_and_quit", "restart_game", "reload_bridge")
GUARDS: dict[str, tuple[str, ...]] = {}
ROADS = ("Path", "Stairs", "SpiralStairs")
HEADROOM_SPEED = 0.3          # wheel sites: flow speed >= 0.3 (hydro.wheel_sites)


def guard(gid: str, rules=()):
    """Register a guard id with the rules.yaml ids it enforces (rules coverage counts these)."""
    GUARDS[gid] = tuple(rules)
    return gid


G_TOOLS = guard("guard.tools", ["player-tools-only"])
G_TEMPLATE = guard("guard.template", ["template-ids-check"])
G_UNLOCK = guard("guard.unlock", ["science-hazard-first"])
G_FREE = guard("guard.footprint", ["building-footprint-dry", "probe-without-placing"])
G_SUPPORT = guard("guard.support", ["platforms-over-water"])
G_FLOOD = guard("guard.flood", ["building-footprint-dry", "flood-key-buildings-high"])
G_DOOR = guard("guard.door", ["doors-by-blueprint", "door-on-connected-path", "path-after-placement"])
G_ONLY = guard("guard.only_link", ["path-keep-doors"])
G_RANGE = guard("guard.range", ["district-range"])
G_INTAKE = guard("guard.intake", ["pump-clean-intake", "pump-pool-separate"])
G_POWER = guard("guard.power", ["power-link-check", "power-consumer-at-wheel", "power-enough"])
G_WHEEL = guard("guard.wheel", ["power-wheel-siting"])
G_STORE = guard("guard.storage", ["storage-good-set", "storage-right-type"])
G_COST = guard("guard.cost", [])
G_DCDOOR = guard("guard.dc_door", ["dc-door-path-first"])
G_SLOPE = guard("guard.slopes", ["natural-slopes-first"])
G_BRIDGE = guard("guard.bridge", ["bridges-both-ends"])
G_GATE = guard("guard.floodgate_order", ["floodgate-build-order"])
G_PLANT = guard("guard.plant", ["plant-use-safe-plant", "plant-no-water-tiles", "plant-no-contaminated-soil",
                                "plant-no-high-ledge", "plant-reachable-only", "corridors-before-planting"])
G_CUT = guard("guard.cutting", ["wood-replant-not-wait", "wood-cutting-area-trees"])
G_DEMOLISH = guard("guard.demolish", ["demolish-resources-care"])
G_PROBE = guard("guard.probe", ["probe-without-placing"])


# ------------------------------------------------------------------ parsing
def parse(action) -> dict:
    """An action as a dict ({"call": "place_building", "template": ..., ...}) or a call string
    ('place_building(template="Path", x=1, y=2, z=5)', 't.place_line("Path", 1, 2, 9, 2, 5)')."""
    if isinstance(action, dict):
        a = dict(action)
        a["call"] = str(a.get("call") or a.get("tool") or "").split(".")[-1]
        return a
    text = str(action).strip()
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError as e:
        raise ValueError(f"not a call: {text[:80]} ({e.msg})") from None
    if not isinstance(node, ast.Call):
        raise ValueError(f"not a call: {text[:80]}")
    fn = node.func
    name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
    a = {"call": name}
    params = CALLS.get(name, [])
    for i, arg in enumerate(node.args):
        a[params[i] if i < len(params) else f"arg{i}"] = ast.literal_eval(arg)
    for kw in node.keywords:
        a[kw.arg] = ast.literal_eval(kw.value)
    return a


def call_text(a: dict) -> str:
    keys = [k for k in CALLS.get(a["call"], []) if k in a] + [k for k in a if k not in CALLS.get(a["call"], [])
                                                               and k not in ("call", "note", "id")]
    return f'{a["call"]}(' + ", ".join(f"{k}={json.dumps(a[k])}" for k in keys) + ")"


def _chk(gid, severity, message, fix="", **evidence):
    return {"guard": gid, "rules": list(GUARDS.get(gid, ())), "severity": severity, "message": message, "fix": fix,
            **({"evidence": evidence} if evidence else {})}


# ------------------------------------------------------------------ the batch
class Checker:
    def __init__(self, world, reservations: dict | None = None, skip=()):
        self.world = world
        self.cat = Catalog(world.blueprints)
        self.skip = set(skip)
        self.sim = Sim(world, self.cat, skip)
        self.reserved = reservations or {}           # (x, y) -> (reservation id, template name)
        self.goods = Counter({g: v.get("available", 0) for g, v in world.goods.items()})
        self.spent: Counter = Counter()
        self.science = int(world.colony.get("science") or 0)
        self.unlocked_now: set = set()
        self._nets = None
        self._hydro = None

    # ---------------------------------------------------------- helpers
    def hydro(self):
        if self._hydro is None:
            from . import hydro
            self._hydro = hydro.analysis(self.world) or False
        return self._hydro or None

    def template_check(self, tpl: str) -> list:
        if tpl == "Path" or self.cat.known(tpl):
            return []
        name = base(tpl)
        if self.cat.get(name):
            return [_chk(G_TEMPLATE, "critical", f"template id {tpl!r} is not exact: use {self.cat.tpl(name)!r}",
                         f'list_blueprints() -> "{self.cat.tpl(name)}"')]
        close = difflib.get_close_matches(tpl, list(self.cat.full), n=3, cutoff=0.5)
        return [_chk(G_TEMPLATE, "critical", f"unknown template {tpl!r}" + (f"; did you mean {close}?" if close else ""),
                     'list_blueprints(group="...")')]

    def nominal_spare(self, net: dict) -> float:
        nets = self.world.power_networks()
        use = sum(POWER_USE.get(b.name, 0) for b in nets.get(net["id"], []) if not b.raw.get("paused"))
        return net["supply"] - max(use, net["demand"])

    # ---------------------------------------------------------- one placement
    def place(self, a: dict, tpl: str, x: int, y: int, z: int, o: int, batch_paths: set, commit: bool = True) -> list:
        """Guard checks for one building; commit=False only looks (spot search), commit=True adds it to the sim."""
        out = []
        name = base(tpl)
        cat, sim, w = self.cat, self.sim, self.world
        tiles = cat.footprint(name, x, y, o) if name != "Path" else [(x, y)]
        height = cat.size(name)[2] if name != "Path" else 1
        label = f"{name}({x},{y})"
        intake = cat.intake(name, x, y, o)
        # unlock
        if cat.unlocked(name) is False and name not in self.unlocked_now:
            need = cat.science(name)
            if self.science >= need:
                out.append(_chk(G_UNLOCK, "warn", f"{name} is locked: unlock it first ({need} science, have {self.science})",
                                f'unlock_building(template="{tpl}")'))
                if commit:
                    self.science -= need
                    self.unlocked_now.add(name)
            else:
                out.append(_chk(G_UNLOCK, "critical", f"{name} is locked and needs {need} science (have {self.science})"))
        # footprint inside the map, free, not on ruins
        off = [t for t in tiles if not w.in_map(*t)]
        if off:
            return out + [_chk(G_FREE, "critical", f"footprint runs off the map at {off[:3]}")]
        hit = sim.blocked(tiles, z, height)
        hang = cat.overhang(name, x, y, o)
        # A pump's intake row is a pipe in the air: a Path may run under or beside it (S2E1 DeepWaterPump(44,79)
        # stands over Path(46,78,5) on a Platform).
        hit = {t: lab for t, lab in hit.items() if not (t in hang and lab.startswith("Path("))}
        if hit:
            same = all(lab.startswith(f"{name}(") for lab in hit.values())
            if name == "Path" and same:
                out.append(_chk(G_FREE, "info", f"already a Path at ({x},{y},{z})"))
            else:
                paths = {t: lab for t, lab in hit.items() if lab.startswith("Path(")}
                other = {t: lab for t, lab in hit.items() if t not in paths}
                if other:
                    out.append(_chk(G_FREE, "critical", f"footprint overlaps {sorted(set(other.values()))[:4]}",
                                    "pick another spot: scan_spots(template, z, x0, y0, x1, y1)"))
                if paths:
                    only = [t for t in paths if any((t[0], t[1], z + dz) in w.only_links for dz in (-1, 0, 1))]
                    if only:
                        out.append(_chk(G_ONLY, "critical", f"builds over road tiles {only[:3]} that are the only link "
                                                            f"to buildings beyond them", "move it off the road"))
                    else:
                        out.append(_chk(G_ONLY, "warn", f"builds over {len(paths)} road tile(s) {sorted(paths)[:3]}: "
                                                        "check nothing else uses that road"))
        objs = {t: sim.object(*t) for t in tiles}
        ruins = {t: o_ for t, o_ in objs.items() if o_ and o_.startswith(("Ruin", "Underground", "Relic"))}
        plants = {t: o_ for t, o_ in objs.items() if o_ and o_ in PLANTS}
        if ruins:
            out.append(_chk(G_FREE, "critical", f"ruins on the footprint {sorted(set(ruins.values()))[:3]}: scavenge first"))
        if plants and name not in ("LumberjackFlag", "GathererFlag", "ScavengerFlag"):
            x0, y0 = min(t[0] for t in plants), min(t[1] for t in plants)
            x1, y1 = max(t[0] for t in plants), max(t[1] for t in plants)
            out.append(_chk(G_FREE, "warn", f"{len(plants)} plant(s) on the footprint ({sorted(set(plants.values()))[:3]})",
                            f"demolish_resources(x0={x0}, y0={y0}, x1={x1}, y1={y1})"))
        res = {self.reserved[t] for t in tiles if t in self.reserved and self.reserved[t][1] != name}
        if res and name != "Path":
            out.append(_chk(G_FREE, "warn", f"footprint is reserved by the masterplan for {sorted(r[1] for r in res)[:3]} "
                                            f"({sorted(r[0] for r in res)[:3]})", "foreman plan (pick the reserved spot "
                                                                                    "for this building)"))
        # support, water, flooding
        water_ok = name in WATER_OK
        unsupported, wet = [], []
        for t in tiles:
            if t in hang:
                if sim.top(*t) > z:
                    unsupported.append(t)
                continue
            on = sim.stands_at(*t, z)
            if name in ("Platform", "DoublePlatform", "TriplePlatform", "Dam", "Levee", "Floodgate", "DoubleFloodgate",
                        "TripleFloodgate", "CompactWaterWheel", "LargeWaterWheel"):
                if sim.top(*t) > z:
                    unsupported.append(t)
            elif on is None:
                unsupported.append(t)
            if sim.depth(*t) > 0.05 and on == "terrain" and not water_ok:
                wet.append(t)
        if unsupported:
            levels = sorted({sim.top(*t) for t in unsupported})
            low = [t for t in unsupported if sim.top(*t) < z]
            fix = "use the ground level from view_map HEIGHTS (z = standing level)"
            if low:
                fix = f"raise the low tiles with Platforms (standing level becomes z{z}) or pick level ground"
                h = self.hydro()
                if h and any(sim.depth(*t) > 0.05 for t in low):
                    near = [d for d in h.decks() if d["bbox"][0] - 2 <= x <= d["bbox"][2] + 2
                            and d["bbox"][1] - 2 <= y <= d["bbox"][3] + 2]
                    if near:
                        fix = near[0]["calls"][0] + f"; then build on the deck at z={near[0]['deckZ']}"
            out.append(_chk(G_SUPPORT, "critical", f"{len(unsupported)} footprint tile(s) not at standing level z{z} "
                                                   f"(ground there is z{levels[:4]})", fix))
        if wet:
            out.append(_chk(G_FLOOD, "critical", f"{len(wet)} footprint tile(s) under water (up to "
                                                 f"{max(sim.depth(*t) for t in wet):.2f}); water-film tiles flood",
                            "move it to dry ground or onto a Platform deck"))
        # intake (pumps)
        if intake:
            ix, iy = intake
            d, bad = sim.depth(ix, iy), float(w.dirt[iy, ix])
            pump_bad = "Badwater" in name
            if d <= 0.05:
                out.append(_chk(G_INTAKE, "critical", f"intake ({ix},{iy}) is dry: the pump will pump nothing",
                                "pick a spot whose intake is over water: scan_spots(...) water.underwater"))
            elif not pump_bad and bad >= 0.05:
                out.append(_chk(G_INTAKE, "critical", f"intake ({ix},{iy}) is {bad:.0%} badwater"))
            elif d < 0.3:
                out.append(_chk(G_INTAKE, "warn", f"intake ({ix},{iy}) is only {d:.2f} deep: it runs dry in a drought "
                                                  "unless the water is held by a dam"))
            if sim.top(ix, iy) >= z:
                out.append(_chk(G_INTAKE, "critical", f"intake tile ({ix},{iy}) is not below the pump (ground z{sim.top(ix, iy)})"))
        # door
        door = cat.door(name, x, y, o, z)
        if door:
            dx, dy, dz = door
            if (dx, dy, dz) not in sim.nodes:
                fix = f'place_building(template="Path", x={dx}, y={dy}, z={dz})'
                if sim.stands_at(dx, dy, dz) is None:
                    fix = f"the door tile ({dx},{dy}) is not at z{dz} (ground z{sim.top(dx, dy)}): turn or move it"
                    sev = "critical"
                else:
                    sev = "warn"
                    r = sim.route((dx, dy, dz))
                    if r and len(r) > 1:
                        fix = "; ".join(line_calls("Path", r))
                out.append(_chk(G_DOOR, sev, f"door ({dx},{dy},{dz}) is not on a Path", fix, door=door))
            elif not sim.connected(dx, dy, dz):
                r = sim.route((dx, dy, dz))
                out.append(_chk(G_DOOR, "warn", f"door path ({dx},{dy},{dz}) is not joined to the District Centre",
                                "; ".join(line_calls("Path", r)) if r else "run a Path from the door to the road network "
                                                                           "(same z, orthogonal)", door=door))
        # range
        probe = door or (x, y, z)
        ok, how = sim.in_range(*probe[:2], probe[2])
        if not ok and name not in ("Path",):
            out.append(_chk(G_RANGE, "critical", f"outside the district build range ({how}): builders won't come",
                            "run a Path toward it first (range follows roads)"))
        elif not ok and name == "Path" and not any(n in batch_paths or n in sim.component()
                                                   for n in self._around(x, y, z)):
            out.append(_chk(G_RANGE, "warn", f"Path ({x},{y},{z}) is beyond the build range ({how}): build it from "
                                             "the connected end outwards"))
        # power
        if name in POWER_USE:
            out += self.power(name, tiles, z, label)
        if name in ("CompactWaterWheel", "LargeWaterWheel"):
            out += self.wheel(tiles)
        # storage good
        kind = store_kind(name)
        if kind:
            good = a.get("good")
            if not good:
                out.append(_chk(G_STORE, "warn", f"{name} has no good chosen: it stores nothing until one is set",
                                f'after placing: building_action(building_id="<new id>", component="SingleGoodAllower", '
                                f'action="Allow", args=["<Good>"])'))
            elif not good_fits(name, good):
                out.append(_chk(G_STORE, "critical", f"{name} cannot hold {good} (a {kind} adds 0 capacity for it)",
                                "use a Warehouse for Gear, MetalPart and food, a Pile for logs/planks/metal, a Tank for liquids"))
        # cost
        cost = cat.cost(name) if name != "Path" else {}
        short = {g: n - (self.goods[g] - self.spent[g]) for g, n in cost.items() if self.goods[g] - self.spent[g] < n}
        if commit:
            self.spent.update(cost)
        if short:
            out.append(_chk(G_COST, "info", "builders will wait for " + ", ".join(f"{n} {g}" for g, n in short.items())))
        # stairs vs natural slopes
        if name in ("Stairs", "SpiralStairs"):
            out += self.slopes(x, y, z)
        if not commit:
            return out
        sim.add(name, tiles, z, label)
        if name in ROADS:
            batch_paths.add((x, y, z))
        self.sim.placed.append({"name": name, "x": x, "y": y, "z": z, "o": o, "tiles": tiles})
        return out

    @staticmethod
    def _around(x, y, z):
        return [(x + dx, y + dy, z + dz) for dx, dy in N4 for dz in (-1, 0, 1)]

    def power(self, name: str, tiles, z: int, label: str) -> list:
        """A new powered building links if an existing shaft/generator/machine has an open power point inside its
        footprint (bridge powerConnections); then the network needs spare hp for it."""
        foot = set(tiles)
        hits = []
        for b in self.world.buildings:
            if b.id in self.skip:
                continue
            for p in b.raw.get("powerConnections") or []:
                if (p["x"], p["y"]) in foot and z <= p["z"] < z + self.cat.size(name)[2]:
                    hits.append(b)
        need = POWER_USE[name]
        if not hits:
            shafts = [b for b in self.world.buildings if b.raw.get("powerConnections") and b.id not in self.skip]
            near = min(shafts, key=lambda b: min(abs(b.x - t[0]) + abs(b.y - t[1]) for t in tiles), default=None)
            msg = f"{label} touches no shaft, wheel or powered building: it gets no power ({need} hp)"
            fix = ""
            if near:
                d = min(abs(near.x - t[0]) + abs(near.y - t[1]) for t in tiles)
                msg += f"; nearest power is {near.label}, {d} tiles away"
                fix = "site it touching the shaft line, or run PowerShafts from " + near.label
            return [_chk(G_POWER, "warn", msg, fix)]
        nets = [self.world.network_of.get(b.id) for b in hits if b.finished]
        nets = [n for n in nets if n]
        if not nets:
            return [_chk(G_POWER, "info", f"{label} links to unfinished power ({hits[0].label}): no power until it is built")]
        best = max(nets, key=self.nominal_spare)
        spare = self.nominal_spare(best)
        if spare < need:
            return [_chk(G_POWER, "warn", f"{label} needs {need} hp but its network has {spare:.0f} hp spare "
                                          f"({best['supply']} supply)", "add a wheel/engine or move it to another network")]
        return []

    def wheel(self, tiles) -> list:
        speeds = []
        for x, y in tiles:
            c = (self.world.state.get("map") or {}).get("speed", [""] * (y + 1))[y][x:x + 1]
            if c and c not in " .":
                speeds.append(int(c, 36) / 10)
        best = max(speeds, default=0.0)
        if best < HEADROOM_SPEED:
            h = self.hydro()
            sites = h.wheel_sites(3) if h else []
            fix = "; ".join(f"({s['x']},{s['y']},z{s['z']}) flow {s['speed']}" for s in sites)
            return [_chk(G_WHEEL, "warn", f"water here flows at {best:.1f}: a wheel in still water makes little power",
                         ("faster water at " + fix) if fix else "place below a dam, drop or narrow choke")]
        return []

    def slopes(self, x: int, y: int, z: int) -> list:
        feats = [f for f in (self.world.features if self.world.has_map else []) if base(f["name"]) == "Slope"]
        near = [f for f in feats if abs(f["x"] - x) + abs(f["y"] - y) <= 8 and f["z"] == z]
        if near:
            f = min(near, key=lambda f: abs(f["x"] - x) + abs(f["y"] - y))
            return [_chk(G_SLOPE, "warn", f"a natural Slope at ({f['x']},{f['y']},{f['z']}) already joins these levels "
                                          f"{abs(f['x'] - x) + abs(f['y'] - y)} tiles away: route to it before building Stairs")]
        return []

    # ---------------------------------------------------------- plants and cutting
    def plant(self, a: dict) -> list:
        x0, x1 = sorted((int(a["x0"]), int(a["x1"])))
        y0, y1 = sorted((int(a["y0"]), int(a["y1"])))
        w, sim = self.world, self.sim
        frm = a.get("frm")
        why = Counter()
        bad_tiles = []
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                if not w.in_map(x, y):
                    why["off map"] += 1
                    continue
                m, z = str(w.moist[y, x]), int(w.top[y, x])
                r = None
                if m == "w" or w.depth[y, x] > 0.05:
                    r = "water"
                elif m == "x":
                    r = "contaminated"
                elif m != "#":
                    r = "dry"
                elif any((x, y, z + k) in sim.vox for k in (0, 1)):
                    r = "building or path"
                elif frm and z < int(frm[2]):
                    r = "below the planter (riverbed?)"
                else:
                    nb = [int(w.top[y + dy, x + dx]) for dx, dy in N4 if w.in_map(x + dx, y + dy)]
                    if nb and z - max(nb) >= 2:
                        r = "ledge 2+ above its neighbours"
                    elif w.reaches(("FarmHouse", "Forester"), x, y, z) is False and not sim.in_range(x, y, z)[0]:
                        r = "unreachable"
                if r:
                    why[r] += 1
                    bad_tiles.append((x, y))
        total = (x1 - x0 + 1) * (y1 - y0 + 1)
        out = []
        if why:
            sev = "info" if a["call"] == "safe_plant" else "warn"
            fix = "" if a["call"] == "safe_plant" else (
                f'h.safe_plant("{a["plant"]}", {x0}, {y0}, {x1}, {y1}, (door x, door y, z)) skips them')
            out.append(_chk(G_PLANT, sev, f"{sum(why.values())}/{total} tiles can't grow {a['plant']}: "
                                          + ", ".join(f"{n} {k}" for k, n in why.most_common()), fix))
        roads_through = [n for n in sim.component() if x0 < n[0] < x1 and y0 < n[1] < y1]
        if total >= 60 and not roads_through and min(x1 - x0, y1 - y0) >= 8:
            out.append(_chk(G_PLANT, "info", f"a {x1 - x0 + 1}x{y1 - y0 + 1} field with no path through it: leave a "
                                             "corridor before planting"))
        if a["plant"] in TREES and not w.finished("Forester"):
            out.append(_chk(G_PLANT, "info", "no finished Forester yet: tree marks wait for one"))
        return out

    def cutting(self, a: dict) -> list:
        if a.get("remove"):
            return []
        x0, x1 = sorted((int(a["x0"]), int(a["x1"])))
        y0, y1 = sorted((int(a["y0"]), int(a["y1"])))
        w = self.world
        trees = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if (self.sim.object(x, y) or "") in TREES]
        out = []
        if not trees:
            out.append(_chk(G_CUT, "warn", "no trees in this rectangle: lumberjacks will idle"))
            return out
        planted = sum(1 for t in trees if (w.planting or {}).get(t))
        foresters = w.finished("Forester")
        if not foresters:
            out.append(_chk(G_CUT, "info", f"{len(trees)} trees marked and no Forester yet: plan replanting "
                                           "(Forester, 30 science) before the stand is gone"))
        elif w.planting is not None and planted < len(trees) // 2:
            out.append(_chk(G_CUT, "warn", f"only {planted}/{len(trees)} of these tree tiles have a planting mark: "
                                           "replant what you cut", f'plant_area(plant="Oak", x0={x0}, y0={y0}, x1={x1}, y1={y1})'))
        all_trees = sum(1 for y in range(w.h) for x in range(w.w) if (self.sim.object(x, y) or "") in TREES) \
            if w.has_map else 0
        if all_trees and len(trees) >= 0.9 * all_trees and not foresters:
            out.append(_chk(G_CUT, "warn", "this marks almost every tree on the map: never cut the only stand"))
        return out

    # ---------------------------------------------------------- one action
    def check(self, a: dict, batch_paths: set) -> list:
        call = a["call"]
        low = call.lower()
        if any(f in low for f in FORBIDDEN):
            return [_chk(G_TOOLS, "critical", f"{call} is not a player toolbar action (or ends the session): never "
                                              "from the playing AI")]
        if call in FREE:
            return []
        if call not in CALLS:
            return [_chk(G_TOOLS, "critical", f"unknown action {call!r}: only toolbar actions (timberlive MCP tools)")]
        if call in ("place_building", "place_line", "place_area"):
            tpl = a.get("template", "")
            bad = self.template_check(tpl)
            if bad:
                return bad
            z, o = int(a["z"]), int(a.get("orientation", 0) or 0)
            if call == "place_building":
                spots = [(int(a["x"]), int(a["y"]))]
            elif call == "place_line":
                spots = _line(int(a["x0"]), int(a["y0"]), int(a["x1"]), int(a["y1"]))
            else:
                spots = [(x, y) for x in range(min(a["x0"], a["x1"]), max(a["x0"], a["x1"]) + 1)
                         for y in range(min(a["y0"], a["y1"]), max(a["y0"], a["y1"]) + 1)]
            out = []
            for x, y in spots:
                for c in self.place(a, tpl, x, y, z, o, batch_paths):
                    c["at"] = [x, y, z]
                    out.append(c)
            if base(tpl) in CROSSINGS and len(spots) > 1:
                out += self.bridge(spots, z, batch_paths)
            return _merge(out)
        if call == "unlock_building":
            name = base(a["template"])
            bad = self.template_check(a["template"])
            if bad:
                return bad
            need = self.cat.science(name)
            if self.cat.unlocked(name):
                return [_chk(G_UNLOCK, "info", f"{name} is already unlocked")]
            if need > self.science:
                return [_chk(G_UNLOCK, "critical", f"{name} needs {need} science (have {self.science})")]
            self.science -= need
            self.unlocked_now.add(name)
            return []
        if call in ("plant_area", "safe_plant"):
            return self.plant(a)
        if call == "mark_tree_cutting":
            return self.cutting(a)
        if call == "building_action" and a.get("component") == "SingleGoodAllower":
            b = self.world.by_id.get(a.get("building_id"))
            good = (a.get("args") or [None])[0]
            if b and good and not good_fits(b.name, good):
                return [_chk(G_STORE, "critical", f"{b.label} cannot hold {good}")]
            return []
        if call == "demolish":
            b = self.world.by_id.get(a.get("building_id"))
            if not b:
                return [_chk(G_DEMOLISH, "warn", "no building with that id")]
            if b.name == "Path" and any((b.x, b.y, b.z + dz) in self.world.only_links for dz in (0, 1)):
                return [_chk(G_ONLY, "critical", f"{b.label} is the only road link to the buildings beyond it")]
            if b.name in ("DistrictCenter",):
                return [_chk(G_DEMOLISH, "critical", "never demolish the District Centre")]
            return [_chk(G_DEMOLISH, "info", f"demolishes {b.label}")]
        if call == "demolish_resources":
            return [_chk(G_DEMOLISH, "info", "builders clear the plants in the rectangle (crops and trees too)")]
        return []

    def bridge(self, spots, z: int, batch_paths: set) -> list:
        """A dam or levee line across water: a Path on top (z+1) makes it a district link; both ends need roads."""
        wet = [t for t in spots if self.sim.depth(*t) > 0.05]
        if len(wet) < 2:
            return []
        tops = [(x, y, z + 1) for x, y in spots]
        missing = [t for t in tops if t not in self.sim.nodes or self.sim.nodes[t] != "road"]
        out = []
        if missing:
            out.append(_chk(G_BRIDGE, "warn", f"{len(missing)} tile(s) of the line have no Path on top (z{z + 1}): a dam "
                                              "alone is not a district link",
                            "; ".join(line_calls("Path", missing))))
        ends = [tops[0], tops[-1]]
        for e in ends:
            if not any(n in self.sim.nodes and n not in tops for n in self._around(*e)):
                out.append(_chk(G_BRIDGE, "warn", f"bridge end ({e[0]},{e[1]},z{e[2]}) is not joined to a road "
                                                  "(add a Path, or Stairs where the bank is a level higher)"))
        return out


def _line(x0, y0, x1, y1):
    if x0 == x1:
        return [(x0, y) for y in range(min(y0, y1), max(y0, y1) + 1)]
    if y0 == y1:
        return [(x, y0) for x in range(min(x0, x1), max(x0, x1) + 1)]
    xs = range(min(x0, x1), max(x0, x1) + 1)
    return [(x, y0) for x in xs] + [(x1, y) for y in range(min(y0, y1), max(y0, y1) + 1) if y != y0]


def _merge(checks: list) -> list:
    """Same guard and message on many tiles of a line -> one check listing the tiles."""
    out, seen = [], {}
    for c in checks:
        k = (c["guard"], c["severity"], c["message"].split(":")[0] if c.get("at") else c["message"])
        if k in seen and c.get("at"):
            seen[k].setdefault("tiles", [seen[k]["at"]]).append(c["at"])
            continue
        seen[k] = c
        out.append(c)
    return out


def _order(actions: list[dict]) -> list[int]:
    """Roads first (Paths, Stairs), then everything else, keeping the AI's order inside each group."""
    def road(a):
        return a["call"] in ("place_building", "place_line", "place_area") and base(a.get("template", "")) in ROADS
    return [i for i, a in enumerate(actions) if road(a)] + [i for i, a in enumerate(actions) if not road(a)]


def batch_id(actions: list[dict]) -> str:
    return hashlib.sha1(json.dumps(actions, sort_keys=True, default=str).encode()).hexdigest()[:12]


def validate(world, actions, reservations: dict | None = None, skip=()) -> dict:
    """Validate one action or a batch. Returns per-action checks, batch checks, and an id for verify().
    skip: building ids to leave out of the simulated map (a planned demolish, or a move)."""
    if not isinstance(actions, list):
        actions = [actions]
    parsed, errors = [], []
    for i, a in enumerate(actions):
        try:
            parsed.append(parse(a))
        except (ValueError, TypeError) as e:
            parsed.append({"call": "?", "raw": str(a)})
            errors.append((i, str(e)))
    ck = Checker(world, reservations, skip)
    results = [None] * len(parsed)
    batch_paths: set = set()
    for i in _order(parsed):
        a = parsed[i]
        if any(i == j for j, _ in errors):
            checks = [_chk(G_TOOLS, "critical", next(e for j, e in errors if j == i))]
        else:
            try:
                checks = ck.check(a, batch_paths)
            except (KeyError, ValueError, TypeError) as e:
                checks = [_chk(G_TOOLS, "critical", f"missing or bad argument: {e}")]
        results[i] = {"index": i, "call": call_text(a) if a["call"] != "?" else a.get("raw"), "action": a,
                      "ok": not any(c["severity"] == "critical" for c in checks), "checks": checks}
    batch = batch_checks(world, parsed, ck)
    n = Counter(c["severity"] for r in results for c in r["checks"]) + Counter(c["severity"] for c in batch)
    return {"id": batch_id(parsed), "ok": n["critical"] == 0, "critical": n["critical"], "warn": n["warn"],
            "info": n["info"], "order": _order(parsed), "results": results, "batch": batch,
            "note": "Foreman approximates the game's placement rules; confirm spots with place_building(..., "
                    "check=True) or scan_spots, which never place anything. Nothing here was run in the game."}


def batch_checks(world, actions: list[dict], ck: Checker) -> list:
    out = []
    dc = ck.sim.dc
    places = [a for a in actions if a["call"] in ("place_building", "place_line", "place_area")]
    if dc and dc.door and places:
        door = tuple(dc.door)
        had = any(b.name == "Path" and (b.x, b.y, b.z) == door for b in world.buildings)
        first_path = next((a for a in places if base(a.get("template", "")) == "Path"), None)
        covers = first_path and door[:2] in (
            [(first_path["x"], first_path["y"])] if first_path["call"] == "place_building" else
            _line(first_path["x0"], first_path["y0"], first_path["x1"], first_path["y1"]) if first_path["call"] == "place_line"
            else [door[:2]] if min(first_path["x0"], first_path["x1"]) <= door[0] <= max(first_path["x0"], first_path["x1"])
            and min(first_path["y0"], first_path["y1"]) <= door[1] <= max(first_path["y0"], first_path["y1"]) else [])
        if not had and not covers:
            out.append(_chk(G_DCDOOR, "critical", f"the District Centre door ({door[0]},{door[1]},{door[2]}) has no Path and "
                                                  "the batch's first Path doesn't cover it: nothing will connect",
                            f'place_building(template="Path", x={door[0]}, y={door[1]}, z={door[2]})  (first)'))
    # place then demolish the same spot in one batch = a trial placement
    placed = {(a.get("x"), a.get("y")) for a in places if a["call"] == "place_building"}
    demo = [a for a in actions if a["call"] == "demolish"]
    for a in demo:
        b = world.by_id.get(a.get("building_id"))
        if b and (b.x, b.y) in placed:
            out.append(_chk(G_PROBE, "warn", f"places and demolishes at ({b.x},{b.y}) in one batch: probe with "
                                             "check=True or scan_spots instead"))
    if len(demo) >= 2 and len(placed) >= 2 and len(places) == len(demo):
        out.append(_chk(G_PROBE, "warn", "the batch looks like trial placements (as many demolishes as placements)"))
    # floodgates last in a crossing
    lines = [a for a in places if base(a.get("template", "")) in ("Dam", "Levee", "Floodgate", "DoubleFloodgate",
                                                                    "TripleFloodgate")]
    gates = [i for i, a in enumerate(lines) if "Floodgate" in a["template"]]
    if gates and any(i > gates[0] and "Floodgate" not in a["template"] for i, a in enumerate(lines)):
        out.append(_chk(G_GATE, "warn", "a Floodgate comes before other dam tiles of the crossing: floodgates are not "
                                        "walkable and strand the rest; place it last"))
    return out


# ------------------------------------------------------------------ verify (after the AI acted)
def verify(world, record: dict) -> dict:
    """Post-checks for a validated batch: was each placement made, is its door on the district road, its
    statuses clean, its power linked (or a partner still being built), its storage good set?"""
    from .monitors.buildings import power_state
    rows = []
    for r in record.get("results", []):
        a = r["action"]
        if a.get("call") != "place_building":
            continue
        name = base(a["template"])
        b = next((b for b in world.buildings if b.name == name and (b.x, b.y) == (a["x"], a["y"])), None)
        if not b:
            rows.append({"call": r["call"], "state": "not placed", "checks": []})
            continue
        checks = []
        if name != "Path" and b.door is None and Catalog(world.blueprints).get(name).get("entrance"):
            checks.append(_chk(G_DOOR, "warn", "no pathTile reported"))
        if b.door and world.door_connected(b) is False:
            checks.append(_chk(G_DOOR, "warn", f"door {b.door} is not on the District Centre's road network",
                               "h.path_check() for gaps; join it orthogonally at its own z"))
        bad = [s for s in b.raw.get("statuses") or [] if s not in ("Paused.",)]
        if any("connect" in s.lower() for s in bad):
            checks.append(_chk(G_DOOR, "critical", f"status: {bad}"))
        elif bad and b.finished:
            checks.append(_chk(G_DOOR, "info", f"status: {bad}"))
        ps = power_state(b, world)
        if ps == "unlinked" and name in POWER_USE:
            checks.append(_chk(G_POWER, "warn", "no power link: nothing built at its power points"))
        elif ps and ps.startswith("waiting"):
            checks.append(_chk(G_POWER, "info", f"power {ps}"))
        if store_kind(name) and not (b.raw.get("setup") or {}).get("good"):
            checks.append(_chk(G_STORE, "warn", "no good set", f'building_action(building_id="{b.id}", '
                                                             'component="SingleGoodAllower", action="Allow", args=["<Good>"])'))
        rows.append({"call": r["call"], "id": b.id, "state": "finished" if b.finished else
                     f"site {int((b.raw.get('buildProgress') or 0) * 100)}%", "checks": checks})
    n = Counter(c["severity"] for r in rows for c in r["checks"])
    return {"id": record.get("id"), "ok": n["critical"] == 0 and not any(r["state"] == "not placed" for r in rows),
            "critical": n["critical"], "warn": n["warn"], "rows": rows}


def summary(res: dict, limit: int = 12) -> str:
    """Short text for the harness helpers and the briefing."""
    head = (f"FOREMAN validate {res['id']}: {'OK' if res['ok'] else 'PROBLEMS'} "
            f"({res['critical']} critical, {res['warn']} warn, {res['info']} info)")
    lines = [head]
    for r in res["results"]:
        for c in r["checks"]:
            if c["severity"] == "info" and len(lines) > limit:
                continue
            lines.append(f"  [{c['severity'].upper()}] {r['call'][:70]}: {c['message']}" + (f"  -> {c['fix']}" if c["fix"] else ""))
    for c in res["batch"]:
        lines.append(f"  [{c['severity'].upper()}] batch: {c['message']}" + (f"  -> {c['fix']}" if c["fix"] else ""))
    return "\n".join(lines[:limit + 1] + ([f"  ... {len(lines) - limit - 1} more"] if len(lines) > limit + 1 else []))


_ = (math, CONNECTORS, SUPPORTS)
