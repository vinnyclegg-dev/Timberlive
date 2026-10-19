"""Masterplan (plan section 5.1): analyse the map, zone it, lay the road skeleton, reserve the key spots and write
the build order, so nothing is placed somewhere that blocks a later need.

The plan is advice. Every opening placement is found with the checker's guards (geometry.Sim, checker.Checker)
on a simulated copy of the map, in build order, so later spots see earlier ones and their roads. Later stages
name the template, the zone and the gate (science, goods); their exact spot is found when they come up
(suggestions()), against the live map. Saved as foreman/data/masterplan.json (versioned); zones can be accepted,
rejected or regenerated from the CLI (`python -m foreman plan --accept farm-1`).

Sources: knowledge/07-game-plan-v4.md stages 0-6 (opening batch, then the hazard-first science path),
harness/openings/waterfalls.json (the S2E1 opening), knowledge/08 lessons. Work range 20 tiles from the door is
measured on S2E1 (every FarmHouse/Lumberjack/Gatherer/Forester reach tile is within Chebyshev 20 of a door).
"""

from __future__ import annotations

import json
import math
import time
from collections import deque

import numpy as np

from . import hydro as hydro_mod
from .checker import Checker, G_DOOR, G_COST, G_RANGE, G_UNLOCK, call_text, validate
from .collector import base
from .geometry import N4, TREES, line_calls
from .store import DATA

PLAN_FILE = DATA / "masterplan.json"
WORK = 20                       # work range (Chebyshev, from the door) measured on S2E1
FIELD = 18                      # plots counted for a farmhouse: a little inside WORK
PLOTS_PER_FARMHOUSE = 55        # operator rule: maximise-planting
WALK_LIMIT = 90                 # district reach in road tiles (S2E1 roads reach 105)
MAX_ROUTE = 16
BUSHES = ("BlueberryBush",)
RUINS = ("Ruin", "UndergroundRuins")
# What each opening step leaves standing (cumulative counts, any state): met = the step is done, also mid-game.
NEED = {"open-water-1": {"DeepWaterPump": 1, "SmallTank": 1}, "open-farm-1": {"FarmHouse": 1},
        "open-wood": {"LumberjackFlag": 2, "SmallIndustrialPile": 1}, "open-berries": {"GathererFlag": 2,
                                                                                    "SmallWarehouse": 1},
        "open-water-2": {"DeepWaterPump": 2, "SmallTank": 2}, "open-pods": {"BreedingPod": 3},
        "open-barrack": {"Barrack": 1}, "open-inventor": {"Inventor": 1}, "open-dam": {"Dam": 1}}
# Stage 2-6 build order after the opening (07-game-plan-v4: hazard-first science path).
LATER = [
    # stage, template, count, zone, good, science gate note, why, rules
    (2, "Forester", 1, "forest", None, "Inventor running", "renewable wood: replant every cut tile, Oak for wood",
     ["wood-forester-early", "wood-forester-oak"]),
    (2, "CompactWaterWheel", 1, "industry", None, "", "power below the dam spill, where the flow is fastest",
     ["power-wheel-siting"]),
    (2, "IndustrialLumberMill", 1, "industry", None, "", "planks, touching the wheel", ["power-consumer-at-wheel"]),
    (2, "SmallIndustrialPile", 1, "industry", "Plank", "", "plank store beside the mill", ["storage-with-producer"]),
    (3, "Levee", 0, "dam", None, "", "levees and the 1-tile irrigation ponds", ["science-hazard-first"]),
    (3, "Stairs", 0, "core", None, "", "level changes the skeleton needs", ["natural-slopes-first"]),
    (4, "GearWorkshop", 1, "industry", None, "", "gears for pumps, floodgates and the food chain",
     ["science-hazard-first"]),
    (3, "Discharge", 0, "farm-1", None, "", "irrigation ponds keep fields moist in a drought", ["science-hazard-first"]),
    (4, "MediumTank", 1, "water", "Water", "", "water reserve for the longest hazard x1.5", ["hazard-reserve-1.5x"]),
    (4, "HydroponicGarden", 1, "core", None, "", "indoor food that ignores drought and badtide",
     ["drought-proof-food", "science-hazard-first"]),
    (4, "ScavengerFlag", 1, "ruins", None, "", "scrap metal for the smelter", []),
    (4, "Smelter", 1, "industry", None, "", "metal blocks", ["power-consumer-at-wheel"]),
    (4, "FoodFactory", 1, "industry", None, "", "corn rations on drought-proof power", ["corn-chain-early"]),
    (4, "SteamEngine", 1, "industry", None, "", "drought-proof power for the food network", ["drought-proof-food"]),
    (4, "LargeWarehouse", 1, "core", "CornRation", "", "food reserve for the longest hazard x1.5",
     ["hazard-reserve-1.5x"]),
]


class Planner:
    def __init__(self, world, avoid: set | None = None):
        self.w = world
        self.ck = Checker(world)
        self.cat, self.sim = self.ck.cat, self.ck.sim
        self.h = hydro_mod.analysis(world)
        self.avoid = set(avoid or ())
        self.reserved: dict = {}            # (x, y) -> (step id, template)
        self.claimed: set = set()           # farmland, stand and berry tiles promised to a zone
        dc = self.sim.dc
        self.dc_door = tuple(dc.door) if dc and dc.door else None

    def count(self, name: str) -> int:
        return sum(1 for b in self.w.buildings if b.name == name)

    # ------------------------------------------------------------------ analysis
    def walk(self) -> dict:
        """Walking distance over terrain from the District Centre door: level ground, natural slopes, existing
        stairs and crossings; deep water blocks. (x, y) -> (distance, z)."""
        if not self.dc_door or not self.w.has_map:
            return {}
        sx, sy, sz = self.dc_door
        dist = {(sx, sy): (0, sz)}
        q = deque([(sx, sy)])
        conn = {(x, y) for (x, y, z), k in self.sim.nodes.items() if k == "connector"}
        while q:
            x, y = q.popleft()
            d, z = dist[(x, y)]
            if d >= WALK_LIMIT:
                continue
            for dx, dy in N4:
                nx, ny = x + dx, y + dy
                if (nx, ny) in dist or not self.w.in_map(nx, ny) or self.sim.depth(nx, ny) > 0.05:
                    continue
                nz = self.sim.top(nx, ny)
                if nz != z and not (abs(nz - z) == 1 and ((x, y) in conn or (nx, ny) in conn)):
                    continue
                dist[(nx, ny)] = (d + 1, nz)
                q.append((nx, ny))
        return dist

    def masks(self, walk: dict) -> dict:
        w = self.w
        H, W = w.h, w.w
        reach = np.zeros((H, W), bool)
        for (x, y) in walk:
            reach[y, x] = True
        obj = np.full((H, W), "", object)
        for y in range(H):
            for x in range(W):
                o = self.sim.object(x, y)
                if o:
                    obj[y, x] = o
        trees = np.vectorize(lambda o: o in TREES)(obj) & reach
        bushes = np.vectorize(lambda o: o in BUSHES)(obj)
        ruins = np.vectorize(lambda o: o.startswith(RUINS))(obj)
        built = np.zeros((H, W), bool)
        for (x, y, z) in self.sim.vox:
            if w.in_map(x, y):
                built[y, x] = True
        top = w.top.astype(int)
        pad = np.pad(top, 1, mode="edge")
        nbmax = np.max([pad[1:-1, 2:], pad[1:-1, :-2], pad[2:, 1:-1], pad[:-2, 1:-1]], axis=0)
        ledge = top - nbmax >= 2
        farm = (w.moist == "#") & (w.depth <= 0.05) & (w.dirt < 0.05) & reach & ~built & ~ledge & (obj == "")
        return {"reach": reach, "trees": trees, "bushes": bushes, "ruins": ruins, "farm": farm, "built": built}

    @staticmethod
    def window(mask: np.ndarray, r: int) -> np.ndarray:
        """Count of mask tiles in the (2r+1)^2 square around each tile (integral image)."""
        H, W = mask.shape
        ii = np.zeros((H + 1, W + 1), int)
        ii[1:, 1:] = mask.astype(int).cumsum(0).cumsum(1)
        ys, xs = np.mgrid[0:H, 0:W]
        y0, y1 = np.clip(ys - r, 0, H), np.clip(ys + r + 1, 0, H)
        x0, x1 = np.clip(xs - r, 0, W), np.clip(xs + r + 1, 0, W)
        return ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]

    def best_anchor(self, mask, r, reach, near=None, far_cost=0.0):
        cnt = self.window(mask, r).astype(float)
        cnt[~reach] = -1
        if near is not None and far_cost:
            ys, xs = np.mgrid[0:cnt.shape[0], 0:cnt.shape[1]]
            cnt -= far_cost * np.maximum(abs(xs - near[0]), abs(ys - near[1]))
        y, x = np.unravel_index(int(np.argmax(cnt)), cnt.shape)
        return (int(x), int(y)), int(self.window(mask, r)[y, x])

    # ------------------------------------------------------------------ spots
    def orientations(self, name: str):
        sx, sy, _ = self.cat.size(name)
        return (0,) if sx == sy == 1 and not self.cat.get(name).get("entrance") else (0, 1, 2, 3)

    def find_spot(self, name: str, near, radius: int, good=None, pre=None, prefer=None, max_route=MAX_ROUTE,
                  z=None, tries: int = 40):
        """Best (x, y, z, o, route) near `near` whose guard checks are clean (no critical, no warn except a door
        that a short new Path joins to the road network). prefer(x, y, o, route) -> lower is better."""
        tpl = self.cat.tpl(name)
        cands = []
        nx0, ny0 = near
        for x in range(nx0 - radius, nx0 + radius + 1):
            for y in range(ny0 - radius, ny0 + radius + 1):
                if not self.w.in_map(x, y) or (x, y) in self.avoid:
                    continue
                for o in self.orientations(name):
                    if pre and not pre(x, y, o):
                        continue
                    cands.append((max(abs(x - nx0), abs(y - ny0)) + 0.1 * o, x, y, o))
        cands.sort()
        found = []
        for _, x, y, o in cands:
            zz = z if z is not None else self.sim.top(x, y)
            tiles = self.cat.footprint(name, x, y, o)
            if any(t in self.reserved or t in self.avoid for t in tiles):
                continue
            a = {"call": "place_building", "template": tpl, "x": x, "y": y, "z": zz, "orientation": o}
            if good:
                a["good"] = good
            checks = self.ck.place(a, tpl, x, y, zz, o, set(), commit=False)
            door = self.cat.door(name, x, y, o, zz)
            # a door off the road, or out of range, is fine when a short new Path joins it (range follows roads)
            fixable = (G_DOOR, G_UNLOCK, G_RANGE) if door else (G_UNLOCK,)
            bad = [c for c in checks if c["severity"] in ("critical", "warn") and c["guard"] not in fixable]
            if bad:
                continue
            route = []
            if door and any(c["guard"] in (G_DOOR, G_RANGE) for c in checks):
                if self.sim.object(door[0], door[1]):
                    continue                        # a tree or bush on the doorstep: the Path can't go there
                r = self.sim.route(door, max_route)
                if not r or set((t[0], t[1]) for t in r) & set(tiles) or any((t[0], t[1]) in self.reserved for t in r):
                    continue
                route = [t for t in r if t not in self.sim.nodes]
            score = (prefer(x, y, o, route) if prefer else 0) + len(route) * 0.7 + \
                max(abs(x - nx0), abs(y - ny0))
            found.append((score, x, y, zz, o, route, a))
            if len(found) >= tries:
                break
        if not found:
            return None
        found.sort(key=lambda f: f[0])
        _, x, y, zz, o, route, a = found[0]
        return {"x": x, "y": y, "z": zz, "o": o, "route": route, "action": a}

    def commit(self, step: dict, spot: dict, name: str, priority=None, paused=False) -> None:
        """Add the route Paths and the building to the simulated map and to the step's calls."""
        spot["route"] = list(reversed(spot["route"]))     # from the connected end outwards (range follows roads)
        for t in spot["route"]:
            self.ck.place({"call": "place_building", "template": "Path"}, "Path", *t, 0, set())
        if spot["route"]:
            step["calls"] += line_calls("Path", spot["route"])
            step["actions"] += [{"call": "place_building", "template": "Path", "x": t[0], "y": t[1], "z": t[2]}
                                for t in spot["route"]]
        a = spot["action"]
        self.ck.place(a, a["template"], a["x"], a["y"], a["z"], a["orientation"], set())
        step["calls"].append(call_text({k: v for k, v in a.items() if k != "good"}))
        step["actions"].append(a)
        tiles = self.cat.footprint(name, a["x"], a["y"], a["orientation"])
        for t in tiles:
            self.reserved[t] = (step["id"], name)
        after = []
        if a.get("good"):
            after.append(f'building_action(building_id="<new {name} id>", component="SingleGoodAllower", '
                         f'action="Allow", args=["{a["good"]}"])')
        if priority:
            after.append(f'set_priority(building_id="<new {name} id>", priority="{priority}")')
        if paused:
            after.append(f'set_paused(building_id="<new {name} id>", paused=true)')
        step["after"] += after
        step["spots"].append({"template": name, "x": a["x"], "y": a["y"], "z": a["z"], "o": a["orientation"],
                              "door": list(self.cat.door(name, a["x"], a["y"], a["orientation"], a["z"]) or []),
                              "tiles": tiles})

    # ------------------------------------------------------------------ the plan
    def plan(self) -> dict:
        w = self.w
        if not self.dc_door:
            return {"error": "no District Centre with a door on the map"}
        walk = self.walk()
        m = self.masks(walk)
        reach = m["reach"]
        zones, steps = [], []
        notes = []

        def step(sid, stage, title, why, rules, zone):
            s = {"id": sid, "stage": stage, "title": title, "why": why, "rules": rules, "zone": zone,
                 "calls": [], "actions": [], "after": [], "spots": [], "need": NEED.get(sid, {})}
            steps.append(s)
            return s

        def met(sid):
            if all(self.count(t) >= n for t, n in NEED.get(sid, {}).items()):
                steps.append({"id": sid, "stage": 1, "title": f"{sid}: already built", "why": "", "rules": [],
                              "zone": None, "calls": [], "actions": [], "after": [], "spots": [],
                              "need": NEED.get(sid, {}), "done": True})
                return True
            return False

        dcx, dcy, dcz = self.dc_door
        zones.append({"id": "core", "kind": "core", "anchor": [dcx, dcy], "bbox": [dcx - 8, dcy - 8, dcx + 8, dcy + 8],
                      "why": "District Centre, housing, pods, the Inventor and small stores within a short walk"})
        # 0. the doorstep
        s0 = step("open-dc-door", 1, "Path on the District Centre doorstep", "first Path of every opening batch",
                  ["dc-door-path-first"], "core")
        if self.dc_door not in self.sim.nodes:
            self.ck.place({"call": "place_building", "template": "Path"}, "Path", *self.dc_door, 0, set())
            s0["calls"].append(f'place_building(template="Path", x={dcx}, y={dcy}, z={dcz})')
            s0["actions"].append({"call": "place_building", "template": "Path", "x": dcx, "y": dcy, "z": dcz})

        # 1. water: pumps on the deepest clean water near the centre, a tank each
        pump_zone = None if met("open-water-1") else self._pumps(step, zones, notes, 1, "open-water-1", "VeryHigh")
        first_pump = pump_zone["spots"][0] if pump_zone else next(
            ({"x": b.x, "y": b.y} for b in w.buildings if b.name == "DeepWaterPump"), None)
        # 2. farm: the best block of moist reachable land, FarmHouse on its edge, kohlrabi everywhere in range
        farms = self._farms(m, zones)
        if met("open-farm-1"):
            pass
        elif farms:
            self._farmhouse(step, farms[0], m, "open-farm-1", 1)
        else:
            notes.append("no moist reachable farmland: work down 07-game-plan-v4 stage 0 (move the farmhouse, dam "
                         "for moisture, gatherers, Levee + Discharge ponds, then Hydroponics)")
        # 3. wood: lumberjacks on the whole stand + log pile
        if not met("open-wood"):
            self._forest(step, m, zones, notes)
        # 4. berries: gatherers + warehouse
        if not met("open-berries"):
            self._berries(step, m, zones, notes)
        # 5. second pump and tank
        if first_pump and not met("open-water-2"):
            self._pumps(step, zones, notes, 1, "open-water-2", None, second=first_pump)
        # 6. pods (3) and a barrack
        s = None if met("open-pods") else step("open-pods", 1, "3 Breeding Pods", "births must keep up with the "
                                               "founders' deaths: 3 pods by day 5",
                                               ["pods-by-day-5", "population-stable"], "core")
        for _ in range(3 - self.count("BreedingPod") if s else 0):
            sp = self.find_spot("BreedingPod", (dcx, dcy), 9, prefer=self._dry_pref(m))
            if sp:
                self.commit(s, sp, "BreedingPod")
        if not met("open-barrack"):
            s = step("open-barrack", 1, "Barrack", "beds for the kits", ["beds-for-kits"], "core")
            sp = self.find_spot("Barrack", (dcx, dcy), 10, prefer=self._dry_pref(m))
            if sp:
                self.commit(s, sp, "Barrack")
        # 7. inventor last, paused until food and water run
        if not met("open-inventor"):
            s = step("open-inventor", 1, "Inventor (last, paused)", "science starts once food and water run; "
                     "Forester is the first unlock", ["opening-extra-jobs-last", "wood-forester-early"], "core")
            sp = self.find_spot("Inventor", (dcx, dcy), 10, prefer=self._dry_pref(m))
            if sp:
                self.commit(s, sp, "Inventor", paused=True)
        # 8. the dam at the last choke
        if not met("open-dam"):
            self._dam(step, zones, notes)
        # zones without opening steps: industry (wheels), ruins, reserves
        self._reserve_zones(m, zones, walk)
        # later stages
        for i, (stage, tpl, count, zone, good, gate, why, rules) in enumerate(sorted(LATER, key=lambda t: t[0])):
            sci = self.cat.science(tpl)
            if count == 0 and any(a.get("call") == "unlock_building" and base(a["template"]) == tpl
                                  for st in steps for a in st["actions"]):
                continue
            s = step(f"s{stage}-{base(tpl).lower()}", stage, f"{'unlock ' if sci and not self.cat.unlocked(tpl) else ''}"
                     f"{tpl}" + (f" x{count}" if count > 1 else ""), why, rules, zone)
            s.update({"template": tpl, "count": count, "good": good, "science": sci, "gate": gate})
            if sci and not self.cat.unlocked(tpl):
                s["calls"].append(f'unlock_building(template="{self.cat.tpl(tpl)}")')
                s["actions"].append({"call": "unlock_building", "template": self.cat.tpl(tpl)})
        steps.sort(key=lambda s: s["stage"])
        # whole opening batch through the checker, from the real map (roads first, as the game builds)
        opening = [a for s in steps if s["stage"] == 1 and not s.get("done") for a in s["actions"]]
        res = validate(w, opening)
        bad = [(r["call"], c) for r in res["results"] for c in r["checks"] if c["severity"] in ("critical", "warn")] + \
            [("batch", c) for c in res["batch"] if c["severity"] in ("critical", "warn")]
        cost: dict = {}
        for a in opening:
            if a["call"] == "place_building":
                for g, n in self.cat.cost(base(a["template"])).items():
                    cost[g] = cost.get(g, 0) + n
        return {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "map": self._map_sig(),
                "dc": list(self.dc_door), "zones": zones, "steps": steps, "notes": notes,
                "opening": {"actions": len(opening), "id": res["id"], "ok": res["ok"], "critical": res["critical"],
                            "warn": res["warn"], "problems": [{"call": c, **chk} for c, chk in bad][:20],
                            "cost": cost, "have": {g: int(w.good(g).get("available", 0)) for g in cost}},
                "reservations": [{"x": x, "y": y, "step": sid, "template": t} for (x, y), (sid, t) in
                                 sorted(self.reserved.items())]}

    # ------------------------------------------------------------------ pieces
    def _dry_pref(self, m):
        farm = m["farm"]
        return lambda x, y, o, route, name=None: 0.0

    def _pref_off_farm(self, m, name):
        farm = m["farm"]

        def pref(x, y, o, route):
            tiles = self.cat.footprint(name, x, y, o)
            on = sum(1 for tx, ty in tiles if self.w.in_map(tx, ty) and farm[ty, tx])
            on += sum(1 for t in route if farm[t[1], t[0]])
            return on * 2.0
        return pref

    def _pumps(self, step, zones, notes, n, sid, priority, second=False):
        """Deep Water Pump with its intake over the deepest clean water near the centre, plus a Small Tank."""
        dcx, dcy, dcz = self.dc_door
        w = self.w

        def pre(depth):
            def ok(x, y, o):
                it = self.cat.intake("DeepWaterPump", x, y, o)
                if not it or not w.in_map(*it):
                    return False
                ix, iy = it
                return w.depth[iy, ix] >= depth and w.dirt[iy, ix] < 0.05 and self.sim.top(x, y) > self.sim.top(ix, iy)
            return ok

        def pref(x, y, o, route):
            ix, iy = self.cat.intake("DeepWaterPump", x, y, o)
            return -2.0 * float(w.depth[iy, ix]) - (3.0 if self.h and (ix, iy) in self.h.held_tiles() else 0)

        sp = None
        centre = (second["x"], second["y"]) if second else (dcx, dcy)
        tries = [(r, 0.5) for r in ((6, 12, 20) if second else (12, 20, 30, 45, 60))]
        if not second:
            tries.append((60, 0.25))            # last resort: shallow water dries first in a drought
        for radius, depth in tries:
            sp = self.find_spot("DeepWaterPump", centre, radius, pre=pre(depth), prefer=pref, max_route=radius + 12)
            if sp:
                break
        if not sp:
            notes.append("no second clean pump site within 20 tiles of the first: add pumps beside it on the Water "
                         "page (pump sites, decks)" if second else
                         "CRITICAL: no clean water a Deep Water Pump can reach within 60 tiles of the centre: start "
                         "water is 0, so check survey_map.py water and the Water page (pump sites, decks) first")
            return None
        it = self.cat.intake("DeepWaterPump", sp["x"], sp["y"], sp["o"])
        far = max(abs(sp["x"] - centre[0]), abs(sp["y"] - centre[1]))
        s = step(sid, 1, ("Second" if second else "First") + " Deep Water Pump + Small Tank (Water)",
                 f"intake ({it[0]},{it[1]}) over {float(w.depth[it[1], it[0]]):.1f}-deep clean water"
                 + ("; 0 water at the start, so it goes first" if not second else "")
                 + (f"; {far} tiles from the centre: the nearest clean water, so carry water early and put a "
                    "District Centre by it later" if far > 30 else "")
                 + ("; shallow (no clean water 0.5 deep in reach): it dries first in a drought, so fill the tanks "
                    "early and dam this water" if float(w.depth[it[1], it[0]]) < 0.5 else ""),
                 ["opening-pumps-tanks", "pump-clean-intake", "storage-with-producer"], "water")
        self.commit(s, sp, "DeepWaterPump", priority=priority)
        tk = self.find_spot("SmallTank", (sp["x"], sp["y"]), 6, good="Water")
        if tk:
            self.commit(s, tk, "SmallTank", priority=priority)
        if not second:
            zones.append({"id": "water", "kind": "water", "anchor": [sp["x"], sp["y"]],
                          "bbox": [sp["x"] - 6, sp["y"] - 6, sp["x"] + 6, sp["y"] + 6],
                          "why": "pumps and tanks on the deepest clean water near the centre; keep the bank row free "
                                 "for more pumps (about 1 per 5 beavers)"})
        return s

    def _farms(self, m, zones):
        farm = m["farm"].copy()
        out = []
        for k in range(4):
            (ax, ay), n = self.best_anchor(farm, FIELD, m["reach"], near=self.dc_door[:2], far_cost=0.3)
            if n < (40 if k else 20):
                break
            x0, y0, x1, y1 = max(0, ax - FIELD), max(0, ay - FIELD), min(self.w.w - 1, ax + FIELD), min(self.w.h - 1, ay + FIELD)
            tiles = int(farm[y0:y1 + 1, x0:x1 + 1].sum())
            ys, xs = np.nonzero(farm[y0:y1 + 1, x0:x1 + 1])
            bbox = [int(x0 + xs.min()), int(y0 + ys.min()), int(x0 + xs.max()), int(y0 + ys.max())]
            farm[y0:y1 + 1, x0:x1 + 1] = False
            z = {"id": f"farm-{k + 1}", "kind": "farm", "anchor": [ax, ay], "bbox": bbox, "plots": tiles,
                 "farmhouses": max(1, round(tiles / PLOTS_PER_FARMHOUSE / 2)),
                 "why": f"{tiles} moist, clean, reachable plots within {FIELD} tiles of ({ax},{ay})"}
            zones.append(z)
            out.append(z)
        return out

    @staticmethod
    def _plot_rect(farm, door, bbox):
        """The tightest rectangle round the door (inside bbox and FIELD) with one farmhouse's plots: the fewest plots
        >= PLOTS_PER_FARMHOUSE, then the most compact. All plots in reach when there are fewer."""
        dx, dy = door
        bx0, by0, bx1, by1 = max(bbox[0], dx - FIELD), max(bbox[1], dy - FIELD), min(bbox[2], dx + FIELD), min(bbox[3], dy + FIELD)
        sub = farm[by0:by1 + 1, bx0:bx1 + 1].astype(np.int32)
        if int(sub.sum()) <= PLOTS_PER_FARMHOUSE:
            return bx0, by0, bx1, by1, int(sub.sum())
        ii = np.zeros((sub.shape[0] + 1, sub.shape[1] + 1), np.int32)
        ii[1:, 1:] = sub.cumsum(0).cumsum(1)
        cx, cy = min(max(dx, bx0), bx1) - bx0, min(max(dy, by0), by1) - by0
        X0, X1 = np.arange(0, cx + 1), np.arange(cx, sub.shape[1])
        Y0, Y1 = np.arange(0, cy + 1), np.arange(cy, sub.shape[0])
        a, b, c, d = np.meshgrid(X0, X1, Y0, Y1, indexing="ij")
        n = ii[d + 1, b + 1] - ii[c, b + 1] - ii[d + 1, a] + ii[c, a]
        side = np.maximum(b - a, d - c)
        key = np.where(n >= PLOTS_PER_FARMHOUSE, n * 1000 + side, 1 << 30)
        i = np.unravel_index(int(key.argmin()), key.shape)
        return (int(bx0 + a[i]), int(by0 + c[i]), int(bx0 + b[i]), int(by0 + d[i]), int(n[i]))

    def _farmhouse(self, step, zone, m, sid, stage):
        ax, ay = zone["anchor"]
        s = step(sid, stage, "FarmHouse + kohlrabi on the nearest moist plots",
                 "130 start berries last about 3 days: crops go in on day 1-2", ["opening-farmhouse-first",
                                                                              "plant-every-moist-tile",
                                                                              "farm-plots-per-house"], zone["id"])
        sp = None
        for r in (6, 10, 14):
            sp = self.find_spot("FarmHouse", (ax, ay), r, prefer=self._pref_off_farm(m, "FarmHouse"))
            if sp:
                break
        if not sp:
            s["note"] = "no FarmHouse spot with a clean door near the field; check with scan_spots"
            return
        self.commit(s, sp, "FarmHouse", priority="High")
        door = self.cat.door("FarmHouse", sp["x"], sp["y"], sp["o"], sp["z"])
        dx, dy, dz = door
        bx0, by0, bx1, by1 = zone["bbox"]
        x0, y0, x1, y1, n = self._plot_rect(m["farm"], (dx, dy), (bx0, by0, bx1, by1))
        s["title"] += f" ({n} of the zone's {zone['plots']} plots)"
        if zone["plots"] > n:
            s["why"] += f"; one FarmHouse works ~{PLOTS_PER_FARMHOUSE} plots, so the rest wait for more farmhouses"
        a = {"call": "safe_plant", "plant": "Kohlrabi", "x0": x0, "y0": y0, "x1": x1, "y1": y1, "frm": [dx, dy, dz]}
        s["calls"].append(f'h.safe_plant("Kohlrabi", {x0}, {y0}, {x1}, {y1}, ({dx}, {dy}, {dz}))')
        s["actions"].append(a)

    def _forest(self, step, m, zones, notes):
        trees = m["trees"]
        if not trees.any():
            notes.append("no reachable trees: wood comes from a Forester only (unlock it first)")
            return
        (ax, ay), n = self.best_anchor(trees, 10, m["reach"], near=self.dc_door[:2], far_cost=0.4)
        s = step("open-wood", 1, "2 Lumberjacks on the whole stand + Log pile",
                 f"{n} trees around ({ax},{ay}); mark the whole grown stand on day 1", ["wood-whole-stand-day1",
                                                                                     "storage-with-producer"], "forest")
        notrees = lambda x, y, o: not trees[y, x]  # noqa: E731
        flags = []
        for _ in range(2):
            sp = self.find_spot("LumberjackFlag", (ax, ay), 10, pre=notrees, prefer=self._pref_off_farm(m, "LumberjackFlag"))
            if sp:
                self.commit(s, sp, "LumberjackFlag")
                flags.append(sp)
        if not flags:
            s["note"] = "no flag spot by the stand"
            return
        fx = [f["x"] for f in flags]
        fy = [f["y"] for f in flags]
        cx, cy = sum(fx) // len(fx), sum(fy) // len(fy)
        ys, xs = np.nonzero(trees)
        near = [(int(x), int(y)) for x, y in zip(xs, ys) if max(abs(x - cx), abs(y - cy)) <= WORK - 2]
        if near:
            x0, y0 = min(t[0] for t in near), min(t[1] for t in near)
            x1, y1 = max(t[0] for t in near), max(t[1] for t in near)
            s["calls"].append(f"mark_tree_cutting(x0={x0}, y0={y0}, x1={x1}, y1={y1})")
            s["actions"].append({"call": "mark_tree_cutting", "x0": x0, "y0": y0, "x1": x1, "y1": y1})
            zones.append({"id": "forest", "kind": "forest", "anchor": [ax, ay], "bbox": [x0, y0, x1, y1],
                          "trees": len(near), "why": f"{len(near)} trees in lumberjack range; the Forester replants "
                                                    "them (Oak) once unlocked"})
        pile = self.find_spot("SmallIndustrialPile", (cx, cy), 6, good="Log", pre=notrees)
        if pile:
            self.commit(s, pile, "SmallIndustrialPile")

    def _berries(self, step, m, zones, notes):
        bushes = m["bushes"] & m["reach"] | (m["bushes"] & np.roll(m["reach"], 1, 0))
        if not m["bushes"].any():
            notes.append("no berry bushes: food rests on the first crops; plant kohlrabi on day 1")
            return
        (ax, ay), n = self.best_anchor(m["bushes"], 8, m["reach"], near=self.dc_door[:2], far_cost=0.4)
        if n < 8:
            return
        count = 3 if n >= 60 else 2
        s = step("open-berries", 1, f"{count} Gatherers + berry warehouse", f"{n} bushes around ({ax},{ay})",
                 ["food-days-3"], "berries")
        nob = lambda x, y, o: not m["bushes"][y, x] and not m["trees"][y, x]  # noqa: E731
        flags = []
        for _ in range(count):
            sp = self.find_spot("GathererFlag", (ax, ay), 9, pre=nob)
            if sp:
                self.commit(s, sp, "GathererFlag")
                flags.append(sp)
        wh = self.find_spot("SmallWarehouse", (ax, ay), 9, good="Berries", pre=nob)
        if wh:
            self.commit(s, wh, "SmallWarehouse")
        zones.append({"id": "berries", "kind": "berries", "anchor": [ax, ay], "bbox": [ax - 8, ay - 8, ax + 8, ay + 8],
                      "bushes": n, "why": f"{n} wild bushes: food until the first crops ripen"})
        _ = bushes

    def _dam(self, step, zones, notes):
        if not self.h:
            return
        dcx, dcy = self.dc_door[:2]
        near = lambda p: min(max(abs(x - dcx), abs(y - dcy)) for x, y in p["line"]) <= 40  # noqa: E731
        allp = self.h.dams(16).get("proposals", [])
        allp = [p for p in allp if near(p)] or allp
        props = [p for p in allp if not p.get("needsUnlock")]
        if not props:
            if not allp:
                notes.append("no dam proposal on this map: see the Water page")
                return
            p = allp[0]
            zones.append({"id": "dam", "kind": "reserve", "anchor": list(p["line"][len(p["line"]) // 2]),
                          "bbox": list(p["bbox"]), "line": [list(t) for t in p["line"]], "why": p["why"],
                          "keep": "no buildings on the line or in the pool it raises"})
            for t in p["line"]:
                self.reserved[tuple(t)] = ("s3-dam", p["kind"])
            s = step("s3-dam", 3, f"{p['kind']} at the best choke ({p['logs']} logs, unlock {', '.join(p['needsUnlock'])})",
                     p["why"] + "; no plain Dam holds water here (the river is already at dam height)",
                     ["dam-cycle-1", "dam-siting", "science-hazard-first"], "dam")
            for u in p["needsUnlock"]:
                if self.cat.unlocked(u) is False:
                    s["calls"].append(f'unlock_building(template="{self.cat.tpl(u)}")')
                    s["actions"].append({"call": "unlock_building", "template": self.cat.tpl(u)})
            s["calls"] += p["calls"]
            s["template"], s["count"], s["line"] = None, 0, [list(t) for t in p["line"]]
            notes.append("no Dam-only choke: the first water step is a Levee line (stage 3, 120 science)")
            return
        p = props[0]
        line = [tuple(t) for t in p["line"]]
        zones.append({"id": "dam", "kind": "reserve", "anchor": list(line[len(line) // 2]), "bbox": list(p["bbox"]),
                      "line": [list(t) for t in line], "why": p["why"], "keep": "no buildings on the line or in the "
                      "pool it raises"})
        for t in line:
            self.reserved[t] = ("open-dam", "Dam")
        s = step("open-dam", 1, f"Dam at the choke ({p['logs']} logs)", p["why"], ["dam-cycle-1", "dam-siting",
                                                                                "bridges-both-ends"], "dam")
        acts = [self._parse_call(c) for c in p["calls"]]
        # the Path on top makes it a bridge; the near end needs a route to the network
        stack_z = max(a["z"] for a in acts if a) + 1 if acts and all(acts) else None
        if stack_z is None:
            s["calls"] += p["calls"]
            s["note"] = "dam calls could not be parsed for the bridge check"
            return
        tops = [(x, y, stack_z) for x, y in line if self.sim.top(x, y) < stack_z]
        ends = []
        for e in (line[0], line[-1]):
            ax = (line[-1][0] - line[0][0], line[-1][1] - line[0][1])
            ax = (int(math.copysign(1, ax[0])) if ax[0] else 0, int(math.copysign(1, ax[1])) if ax[1] else 0)
            sign = -1 if e == line[0] else 1
            b = (e[0] + sign * ax[0], e[1] + sign * ax[1])
            ends.append(b)
        joined, route = False, []
        for b in ends:
            if self.w.in_map(*b) and self.sim.top(*b) == stack_z and self.sim.depth(*b) <= 0.05:
                r = self.sim.route((b[0], b[1], stack_z), 40)
                if r and not any((t[0], t[1]) in self.reserved for t in r[1:]):
                    joined, route = True, r
                    break
        if not joined:
            s["stage"] = 3
            s["calls"] += p["calls"]
            s["note"] = ("the banks at the dam ends are not at the dam-top level or have no road within 40 tiles: "
                         "plan Stairs or a natural Slope to reach it (stage 3)")
            for a in acts:
                s["actions"].append(a)
            return
        for t in route:
            if t not in self.sim.nodes:
                self.ck.place({"call": "place_building", "template": "Path"}, "Path", *t, 0, set())
        new = [t for t in route if t]
        s["calls"] += line_calls("Path", new)
        s["actions"] += [{"call": "place_building", "template": "Path", "x": t[0], "y": t[1], "z": t[2]} for t in new]
        for a in acts:
            s["actions"].append(a)
        s["calls"] += p["calls"]
        other = [b for b in ends if (b[0], b[1], stack_z) not in route]
        top_tiles = tops + [(b[0], b[1], stack_z) for b in other if self.w.in_map(*b) and self.sim.top(*b) == stack_z]
        s["calls"] += line_calls("Path", top_tiles)
        s["actions"] += [{"call": "place_building", "template": "Path", "x": t[0], "y": t[1], "z": t[2]} for t in top_tiles]

    def _parse_call(self, text):
        from .checker import parse
        try:
            return parse(text)
        except ValueError:
            return None

    def _reserve_zones(self, m, zones, walk):
        h = self.h
        if h:
            wheels = [s for s in h.wheel_sites(6) if not s["bad"] and (s["x"], s["y"]) in walk or
                      any((s["x"] + dx, s["y"] + dy) in walk for dx, dy in N4)]
            if wheels:
                s = min(wheels[:4], key=lambda s: max(abs(s["x"] - self.dc_door[0]), abs(s["y"] - self.dc_door[1])))
                zones.append({"id": "industry", "kind": "industry", "anchor": [s["x"], s["y"]],
                              "bbox": [s["x"] - 8, s["y"] - 8, s["x"] + 8, s["y"] + 8],
                              "why": f"fastest clean flow near the centre ({s['speed']}) for wheels; mill, gear "
                                     "workshop, smelter and food factory touch the shaft line"})
            for i, r in enumerate(h.reservoirs(2)):
                zones.append({"id": f"reservoir-{i + 1}", "kind": "reserve", "anchor": list(r["cells"][0]) if r.get("cells") else None,
                              "bbox": list(r.get("bbox") or []), "why": r.get("why", ""), "keep": "keep it free of "
                              "buildings until the reservoir is built"})
            for i, d in enumerate(h.decks(2)):
                zones.append({"id": f"deck-{i + 1}", "kind": "reserve", "anchor": [d["bbox"][0], d["bbox"][1]],
                              "bbox": list(d["bbox"]), "why": d["why"], "keep": "Platform deck site for when the bank "
                                                                                "is packed"})
        ruins = m["ruins"]
        if ruins.any():
            (ax, ay), n = self.best_anchor(ruins, 10, np.ones_like(ruins), near=self.dc_door[:2], far_cost=0.5)
            if n:
                zones.append({"id": "ruins", "kind": "ruins", "anchor": [ax, ay], "bbox": [ax - 10, ay - 10, ax + 10, ay + 10],
                              "why": f"{n} ruin tiles: scrap metal for the Smelter and Metalsmith (Scavenger Flag)"})

    def _map_sig(self) -> dict:
        w = self.w
        return {"size": [w.w, w.h], "dc": list(self.dc_door or []), "dcpos": dc_pos(w.colony),
                "settlement": (w.colony.get("districts") or [{}])[0]
                .get("name") if isinstance(w.colony.get("districts"), list) else None}


def dc_pos(colony: dict) -> list | None:
    """The first District Centre's (x, y, z): a new game or another map moves it."""
    d = colony.get("districts") if isinstance(colony, dict) else None
    if not isinstance(d, list) or not d or d[0].get("x") is None:
        return None
    return [d[0]["x"], d[0]["y"], d[0].get("z")]


def same_map(plan: dict, world) -> bool:
    """False when the plan was made for another map or game (its size or District Centre differs)."""
    sig = plan.get("map") or {}
    if sig.get("size") and sig["size"] != [world.w, world.h]:
        return False
    return not sig.get("dcpos") or sig["dcpos"] == dc_pos(world.colony)


# ---------------------------------------------------------------------- persistence and status
def load(world=None) -> dict | None:
    """The saved plan; with `world`, None when it belongs to another map or game (a new one gets generated)."""
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8")) if PLAN_FILE.exists() else None
    return plan if plan and (world is None or same_map(plan, world)) else None


def forget() -> None:
    """New game: drop the plan (kept as masterplan.prev.json)."""
    if PLAN_FILE.exists():
        PLAN_FILE.replace(PLAN_FILE.with_name("masterplan.prev.json"))


def save(plan: dict) -> dict:
    prev = load()
    if prev and (prev.get("map") or {}).get("dcpos") != (plan.get("map") or {}).get("dcpos"):
        prev = None                              # another game: start the versions and zone statuses afresh
    plan["version"] = (prev or {}).get("version", 0) + 1
    if prev:
        status = {z["id"]: z.get("status") for z in prev.get("zones", [])}
        for z in plan["zones"]:
            z["status"] = status.get(z["id"]) or z.get("status") or "proposed"
        PLAN_FILE.with_name("masterplan.prev.json").write_text(json.dumps(prev, indent=1), encoding="utf-8")
    for z in plan["zones"]:
        z.setdefault("status", "proposed")
    PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLAN_FILE.write_text(json.dumps(plan, indent=1, default=_plain), encoding="utf-8")
    return plan


def _plain(v):
    if isinstance(v, (set, frozenset, tuple)):
        return list(v)
    return v.item() if hasattr(v, "item") else str(v)


def generate(world, avoid=None) -> dict:
    plan = Planner(world, avoid).plan()
    for z in plan.get("zones", []):
        z.setdefault("status", "proposed")
    return json.loads(json.dumps(plan, default=_plain))


def set_status(zone: str, status: str) -> dict:
    plan = load()
    if not plan:
        raise ValueError("no masterplan yet: run `python -m foreman plan`")
    z = next((z for z in plan["zones"] if z["id"] == zone), None)
    if not z:
        raise ValueError(f"no zone {zone!r}; zones: {[z['id'] for z in plan['zones']]}")
    z["status"] = status
    PLAN_FILE.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    return plan


def regenerate(world, zone: str | None = None) -> dict:
    """Whole plan, or one zone moved: its spots and reserved tiles are avoided so another site is proposed."""
    prev = load()
    avoid = set()
    if zone and prev:
        avoid = {(r["x"], r["y"]) for r in prev.get("reservations", [])
                 if next((s for s in prev["steps"] if s["id"] == r["step"]), {}).get("zone") == zone}
        z = next((z for z in prev["zones"] if z["id"] == zone), None)
        if z and z.get("anchor"):
            ax, ay = z["anchor"]
            avoid |= {(x, y) for x in range(ax - 3, ax + 4) for y in range(ay - 3, ay + 4)}
    return save(generate(world, avoid))


def reservations(plan: dict | None, world=None) -> dict:
    """(x, y) -> (step id, template) for steps not done yet (the checker warns on building over them)."""
    if not plan:
        return {}
    done = {s["id"] for s in plan["steps"] if world is not None and step_done(world, s)}
    rejected = {z["id"] for z in plan["zones"] if z.get("status") == "rejected"}
    keep = {s["id"] for s in plan["steps"] if s["id"] not in done and s.get("zone") not in rejected}
    return {(r["x"], r["y"]): (r["step"], r["template"]) for r in plan.get("reservations", []) if r["step"] in keep}


def step_done(world, s: dict) -> bool:
    """A step is done when the buildings it adds stand anywhere (opening counts, any state), its unlock happened,
    or its Paths and dam pieces exist."""
    if s.get("done"):
        return True
    if s.get("need"):
        have: dict = {}
        for b in world.buildings:
            have[b.name] = have.get(b.name, 0) + 1
        return all(have.get(t, 0) >= n for t, n in s["need"].items())
    if s["id"] == "open-dc-door":
        return all(any(b.name == "Path" and (b.x, b.y, b.z) == (a["x"], a["y"], a["z"]) for b in world.buildings)
                   for a in s.get("actions", []))
    spots = s.get("spots") or []
    if spots:
        have = {(b.name, b.x, b.y) for b in world.buildings}
        near = [b for b in world.buildings]
        ok = 0
        for p in spots:
            if (p["template"], p["x"], p["y"]) in have or any(
                    b.name == p["template"] and abs(b.x - p["x"]) <= 3 and abs(b.y - p["y"]) <= 3 for b in near):
                ok += 1
        return ok >= len(spots)
    tpl = s.get("template")
    if tpl:
        cat_unlocked = next((bp.get("unlocked") for bp in world.blueprints or [] if base(bp["template"]) == base(tpl)), None)
        if s.get("count", 0) == 0:
            return bool(cat_unlocked)
        return len([b for b in world.buildings if b.name == base(tpl)]) >= s["count"]
    acts = s.get("actions") or []
    if acts and all(a["call"] == "place_building" and a.get("template", "").startswith(("Dam", "Path")) or
                    a["call"].startswith("place_line") for a in acts):
        have = {(b.x, b.y) for b in world.buildings if b.name == "Dam"}
        dams = [a for a in acts if a.get("template", "").startswith("Dam")]
        return bool(dams) and all((a.get("x0"), a.get("y0")) in have for a in dams if "x0" in a)
    return False


def suggestions(world, plan: dict | None, n: int = 3) -> list[dict]:
    """The next n steps not done yet (accepted or proposed zones), each validated against the live map now.
    Later-stage steps get a spot found on the live map (unlock first if science allows)."""
    if not plan:
        return []
    rejected = {z["id"] for z in plan["zones"] if z.get("status") == "rejected"}
    zones = {z["id"]: z for z in plan["zones"]}
    res = reservations(plan, world)
    out, prior = [], []
    planner = None
    for s in plan["steps"]:
        if s.get("zone") in rejected or step_done(world, s):
            continue
        actions = list(s.get("actions") or [])
        calls = list(s.get("calls") or [])
        note = s.get("note", "")
        tpl = s.get("template")
        if tpl and s.get("count", 0) > 0:
            have = len([b for b in world.buildings if b.name == base(tpl)])
            planner = planner or Planner(world)
            z = zones.get(s.get("zone")) or zones.get("core")
            near = tuple(z["anchor"]) if z and z.get("anchor") else planner.dc_door[:2]
            sp = None
            for r in (8, 14):
                sp = planner.find_spot(tpl, near, r, good=s.get("good"))
                if sp:
                    break
            if sp:
                tmp = {"id": s["id"], "calls": [], "actions": [], "after": [], "spots": []}
                planner.commit(tmp, sp, base(tpl))
                calls += tmp["calls"]
                actions += tmp["actions"]
                s = {**s, "after": tmp["after"], "spots": tmp["spots"]}
                note = note or f"{have}/{s['count']} built"
            else:
                note = f"no clean spot near the {s.get('zone')} zone yet; widen the search with scan_spots"
        v = None
        if actions:
            # validated after the earlier suggestions, as the AI would run them in order
            full = validate(world, prior + actions, {k: v for k, v in res.items() if v[0] != s["id"]})
            mine = [r for r in full["results"] if r["index"] >= len(prior)]
            checks = [c for r in mine for c in r["checks"]] + full["batch"]
            v = {"id": full["id"], "critical": sum(c["severity"] == "critical" for c in checks),
                 "warn": sum(c["severity"] == "warn" for c in checks), "results": mine}
            v["ok"] = not v["critical"]
            prior += actions
        sci = s.get("science") or 0
        blocked = ""
        if tpl and sci and next((bp.get("unlocked") for bp in world.blueprints or []
                                 if base(bp["template"]) == base(tpl)), True) is False and world.colony.get("science", 0) < sci:
            blocked = f"needs {sci} science (have {world.colony.get('science', 0)})"
        out.append({"id": s["id"], "stage": s["stage"], "title": s["title"], "why": s["why"], "zone": s.get("zone"),
                    "calls": calls, "after": s.get("after", []), "note": note, "blocked": blocked,
                    "ready": bool(not blocked and (v is None or (v["ok"] and not v["warn"])) and calls),
                    "validation": None if not v else {"id": v["id"], "ok": v["ok"], "critical": v["critical"],
                                                      "warn": v["warn"], "problems": [
                                                          {"call": r["call"], **c} for r in v["results"] for c in r["checks"]
                                                          if c["severity"] != "info" and c["guard"] != G_COST][:6]}})
        if len(out) >= n:
            break
    if len(out) < n:
        out += every_building(world, n - len(out), planner, prior)
    return out


WATER_SITED = ("Pump", "WaterWheel", "Floodgate", "Dam", "Levee", "Platform", "Stairs", "Slope", "Valve", "Barrier",
               "Discharge", "Overhang", "Bridge", "Sluice", "Shaft", "Fluid", "Impermeable")


def every_building(world, n: int, planner=None, prior=None) -> list[dict]:
    """Stage 6 (07-game-plan-v4): one of every building. Unlocked ones not placed get a spot near the centre;
    water-sited ones point at the Water page; then the cheapest unlock science can buy now."""
    from .monitors.progress import key, tally
    t = tally(world)
    if not t:
        return []
    out = []
    sci = world.colony.get("science", 0)
    for bp in t["ready"]:
        if len(out) >= n:
            return out
        name = key(bp)
        item = {"id": f"s6-{name.lower()}", "stage": 6, "title": f"{bp['name']} (one of every building)",
                "why": "goal: at least one of every building", "zone": "core", "calls": [], "after": [], "note": "",
                "blocked": "", "validation": None, "ready": False}
        if any(k in name for k in WATER_SITED):
            item["note"] = "water-sited: pick the spot on the Water page or GET /api/where?template=" + name
            out.append(item)
            continue
        planner = planner or Planner(world)
        if not planner.dc_door:
            return out
        sp = planner.find_spot(name, planner.dc_door[:2], 14, tries=12)
        if not sp:
            item["note"] = "no clean spot within 14 of the centre; GET /api/where?template=" + name
            out.append(item)
            continue
        tmp = {"id": item["id"], "calls": [], "actions": [], "after": [], "spots": []}
        planner.commit(tmp, sp, name)
        v = validate(world, (prior or []) + tmp["actions"])
        mine = [r for r in v["results"] if r["index"] >= len(prior or [])]
        crit = sum(c["severity"] == "critical" for r in mine for c in r["checks"])
        warn = sum(c["severity"] == "warn" for r in mine for c in r["checks"])
        item.update(calls=tmp["calls"], after=tmp["after"], ready=not crit and not warn,
                    validation={"id": v["id"], "ok": not crit, "critical": crit, "warn": warn, "problems": [
                        {"call": r["call"], **c} for r in mine for c in r["checks"]
                        if c["severity"] != "info" and c["guard"] != G_COST][:6]})
        if prior is not None:
            prior += tmp["actions"]
        out.append(item)
    for bp in t["locked"]:
        if len(out) >= n:
            break
        out.append({"id": f"s6-unlock-{key(bp).lower()}", "stage": 6, "title": f"unlock {bp['name']} ({bp['science']})",
                    "why": "cheapest locked building toward one of every building", "zone": None,
                    "calls": [f'unlock_building(template="{bp["template"]}")'], "after": [], "note": "",
                    "blocked": "" if bp["science"] <= sci else f"needs {bp['science']} science (have {sci})",
                    "validation": None, "ready": bp["science"] <= sci})
    return out


def summary(plan: dict) -> str:
    if plan.get("error"):
        return f"MASTERPLAN: {plan['error']}"
    o = plan["opening"]
    lines = [f"MASTERPLAN v{plan.get('version', '-')} ({plan['generated']}): {len(plan['zones'])} zones, "
             f"{len(plan['steps'])} steps; opening batch {o['actions']} actions: "
             f"{'OK' if o['ok'] and not o['warn'] else 'PROBLEMS'} ({o['critical']} critical, {o['warn']} warn); "
             f"cost {o['cost']} (have {o['have']})"]
    for z in plan["zones"]:
        lines.append(f"  zone {z['id']:<12} {z.get('status', 'proposed'):<9} {z['why'][:110]}")
    for s in plan["steps"]:
        lines.append(f"  [{s['stage']}] {s['id']:<22} {s['title']}")
        for c in s["calls"][:8]:
            lines.append(f"        {c}")
        if len(s["calls"]) > 8:
            lines.append(f"        ... {len(s['calls']) - 8} more")
        for c in s.get("after", []):
            lines.append(f"        then {c}")
        if s.get("note"):
            lines.append(f"        note: {s['note']}")
    for p in o["problems"]:
        lines.append(f"  [{p['severity'].upper()}] {p['call'][:60]}: {p['message']}")
    for n in plan["notes"]:
        lines.append(f"  NOTE {n}")
    return "\n".join(lines)


def next_text(nxt: list[dict]) -> str:
    """NEXT section: the next validated steps as ready-to-run harness calls."""
    if not nxt:
        return "NEXT: nothing left in the masterplan"
    lines = ["NEXT (validated against the live map now; run in order):"]
    for s in nxt:
        v = s.get("validation")
        state = "READY" if s.get("ready") else ("BLOCKED: " + s["blocked"]) if s.get("blocked") else (
            "FIX FIRST" if v and not v["ok"] else "CHECK" if v and v["warn"] else "SPOT NEEDED" if not s["calls"] else "READY")
        lines.append(f"  [{s['stage']}] {s['title']} -- {state}" + (f" ({s['note']})" if s.get("note") else ""))
        for c in s["calls"][:10]:
            lines.append(f"      {c}")
        if len(s["calls"]) > 10:
            lines.append(f"      ... {len(s['calls']) - 10} more (python -m foreman plan --json)")
        for c in s.get("after", []):
            lines.append(f"      then {c}")
        for p in (v or {}).get("problems", [])[:3]:
            lines.append(f"      ! {p['severity']}: {p['message']}" + (f" -> {p['fix']}" if p.get("fix") else ""))
    return "\n".join(lines)
