"""Foreman web service on http://127.0.0.1:8097 (plan sections 8 and 9): JSON views and the static UI.

Read-only for the game like the rest of Foreman: the collector thread polls the bridge's read endpoints,
and every route here is a GET that reads the latest analysis. There is no apply endpoint.

  python -m foreman serve                      collect live (tiers 5 s / 30 s / 3 min) and serve
  python -m foreman serve --fixture FILE.json  serve a recorded state (no game needed)
"""

from __future__ import annotations

import dataclasses
import functools
import json
import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import bridge, collector, hydro, paused
from .briefing import briefing
from .engine import analyse
from .findings import MONITORS
from .monitors import DRINK_PER_BEAVER, POWER_USE
from .monitors.buildings import power_state
from .monitors.forecast import TRACKED, rates
from .monitors.population import ledger
from .monitors.progress import tally
from .monitors.supply import food_days, reserves
from .monitors import FOOD
from .store import Store, _plain

UI = Path(__file__).with_name("ui")
PORT = 8097
HISTORY_POINTS = 240


class Events:
    """Analysis passes as a sequence for /api/events: each pass lists findings that opened (critical/warn)
    and ones that cleared since the last pass."""

    def __init__(self):
        self.cond = threading.Condition()
        self.seq = 0
        self.items: list = []
        self.open: dict = {}

    def push(self, findings, world) -> None:
        now = {f.key: f for f in findings if f.severity in ("critical", "warn")}
        t = (world.colony.get("time") or {}) if world else {}
        with self.cond:
            self.seq += 1
            new = [{"seq": self.seq, "kind": "opened", "severity": f.severity, "rule": f.rule, "message": f.message,
                    "fix": f.fix, "entity": f.entity} for k, f in now.items() if k not in self.open]
            gone = [{"seq": self.seq, "kind": "cleared", "rule": f.rule, "message": f.message, "entity": f.entity}
                    for k, f in self.open.items() if k not in now]
            tick = {"seq": self.seq, "kind": "pass", "day": f"c{t.get('cycle', '?')}d{t.get('cycleDay', '?')}",
                    "critical": sum(f.severity == "critical" for f in now.values()), "warn":
                        sum(f.severity == "warn" for f in now.values())}
            self.items = (self.items + new + gone + [tick])[-500:]
            self.open = now
            self.cond.notify_all()


EVENTS = Events()


class Live:
    """The latest analysis, swapped in whole by the collector thread."""

    def __init__(self):
        self.world = self.ctx = None
        self.findings: list = []
        self.at = 0.0
        self.error = ""
        self.db_path: Path | None = None
        self.source = "live"

    def set(self, world, ctx, findings):
        self.world, self.ctx, self.findings, self.at, self.error = world, ctx, findings, time.time(), ""
        EVENTS.push(findings, world)

    def need(self):
        """(world, ctx, findings); ctx gets this request thread's own store connection."""
        if self.world is None:
            raise HTTPException(503, self.error or "no data yet: the collector is starting")
        return self.world, dataclasses.replace(self.ctx, store=self.store()), self.findings

    def store(self) -> Store:
        """A store connection for this request thread (SQLite connections stay in their thread)."""
        return Store(self.db_path) if self.db_path else Store()


class Json(JSONResponse):
    """JSON that also takes numpy numbers (grids and evidence come from numpy)."""

    def render(self, content) -> bytes:
        return json.dumps(content, default=_plain, separators=(",", ":")).encode()


def as_json(fn):
    """Route returns go straight to Json (FastAPI's own encoder rejects numpy numbers)."""
    @functools.wraps(fn)
    def wrap(*a, **kw):
        out = fn(*a, **kw)
        return out if isinstance(out, Response) else Json(out)
    return wrap


LIVE = Live()
app = FastAPI(title="Foreman", description="Read-only advisor for an AI playing Timberborn", default_response_class=Json)


def fdict(f, store: Store | None = None) -> dict:
    d = dict(f.__dict__)
    if store:
        d["first_day"] = store.finding_age(f.key)[1]
    return d


def day_label(day: float | None) -> str:
    return f"c{int(day // 100)}d{int(day % 100)}" if day else "?"


# ------------------------------------------------------------------ routes
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(UI / "index.html")


@app.get("/api/status")
@as_json
def status():
    from .masterplan import dc_pos
    return {"source": LIVE.source, "at": LIVE.at, "age": time.time() - LIVE.at if LIVE.at else None,
            "error": LIVE.error, "ready": LIVE.world is not None,
            "game": dc_pos(LIVE.world.colony) if LIVE.world is not None else None}


@app.get("/api/briefing", response_class=PlainTextResponse)
def get_briefing(top: int = 8):
    world, ctx, findings = LIVE.need()
    return briefing(world, ctx, findings, top=top)


@app.get("/api/overview")
@as_json
def overview():
    world, ctx, findings = LIVE.need()
    c = world.colony
    r = reserves(world, ctx)
    lg = ledger(world, ctx)
    nets = world.power_networks()
    t = tally(world)
    problems = [f for f in findings if f.rule != "stream.requests"]
    return {
        "time": c["time"], "weather": c.get("weather") or {}, "population": c["population"],
        "science": c.get("science"), "wellbeing": c.get("wellbeing"), "beavers": world.beavers,
        "food": {"stock": r["food_stock"], "days": round(food_days(world), 1), "need": round(r["food_need"])},
        "water": {"stock": r["water_stock"], "cap": r["water_cap"], "use": round(r["water_use"], 1),
                  "drink": round(DRINK_PER_BEAVER * world.beavers, 1), "build": r["water_build"],
                  "need": round(r["water_need"]), "days": round(r["water_stock"] / max(1, r["water_use"]), 1)},
        "hazard_days": r["hazard_days"], "ledger": lg,
        "power": [{"id": n["id"], "supply": n["supply"], "demand": n["demand"], "generators": n["generators"],
                   "machines": len(nets.get(n["id"], [])),
                   "nominal": sum(POWER_USE.get(b.name, 0) for b in nets.get(n["id"], []) if not b.raw.get("paused")),
                   "battery": [n.get("batteryCharge"), n.get("batteryCapacity")]}
                  for n in sorted(world.networks, key=lambda n: -n["supply"])],
        "progress": {"done": t["done"], "total": t["total"], "ready": [bp["name"] for bp in t["ready"]],
                     "locked": [(bp["name"], bp["science"]) for bp in t["locked"][:6]]} if t else None,
        "needs": world.needs,
        "counts": {s: sum(f.severity == s for f in problems) for s in ("critical", "warn", "info")},
        "top": [fdict(f) for f in problems[:8]],
        "trend": rates(world, ctx), "health": world.health, "hours": world.hours,
        "map_age": world.state.get("map_age"), "collected_at": world.state.get("collected_at"),
    }


@app.get("/api/findings")
@as_json
def get_findings(cleared: int = 30):
    world, ctx, findings = LIVE.need()
    store = ctx.store
    rows = store.db.execute("SELECT rule, severity, entity, message, fix, first_day, last_day, runs, cleared_ts "
                            "FROM findings WHERE cleared_ts IS NOT NULL ORDER BY cleared_ts DESC LIMIT ?",
                            (cleared,)).fetchall()
    keys = ("rule", "severity", "entity", "message", "fix", "first_day", "last_day", "runs", "cleared_ts")
    return {"open": [fdict(f, store) for f in findings if f.rule != "stream.requests"],
            "cleared": [dict(zip(keys, r)) for r in rows], "now_day": world.game_day()}


@app.get("/api/buildings")
@as_json
def get_buildings():
    world, ctx, findings = LIVE.need()
    reg = paused.load()
    by_entity: dict[str, list] = {}
    for f in findings:
        by_entity.setdefault(f.entity, []).append({"rule": f.rule, "severity": f.severity, "message": f.message})
    rows = []
    for b in world.buildings:
        if b.name in ("Path",) or (b.finished and b.name in ("Platform", "PowerShaft", "Dam", "Levee", "Stairs")
                                   and b.id not in by_entity):
            continue
        p = world.production.get(b.id) or {}
        w = b.raw.get("workers") or {}
        n = world.network_of.get(b.id)
        rows.append({
            "id": b.id, "name": b.name, "x": b.x, "y": b.y, "z": b.z, "finished": b.finished,
            "progress": b.raw.get("buildProgress"), "paused": bool(b.raw.get("paused")),
            "priority": b.raw.get("priority"), "workers": [w.get("assigned"), w.get("max")] if w else None,
            "statuses": b.raw.get("statuses") or [], "connected": world.door_connected(b),
            "power": power_state(b, world), "network": [n["supply"], n["demand"]] if n else None,
            "recipe": p.get("recipe"), "batch": p.get("progress"), "ready": p.get("ready"),
            "setup": b.raw.get("setup"), "reason": reg.get(b.id), "findings": by_entity.get(b.id, []),
        })
    return {"buildings": rows}


@app.get("/api/supply")
@as_json
def supply():
    world, ctx, findings = LIVE.need()
    store = ctx.store
    hist = store.history("goods")[-HISTORY_POINTS:]
    keep = set(TRACKED) | set(FOOD) | {g for g, v in world.goods.items() if v.get("capacity")}
    series: dict[str, list] = {}
    for _ts, day, goods in hist:
        if day is None:
            continue
        food = 0
        for g in goods:
            if g["id"] in keep:
                series.setdefault(g["id"], []).append([day, g.get("available", 0)])
            if g["id"] in FOOD:
                food += g.get("available", 0)
        series.setdefault("food", []).append([day, food])
    r = reserves(world, ctx)
    farms = []
    for b in world.finished("FarmHouse", "Forester"):
        rc = world.reach.get(b.id) or {}
        farms.append({"id": b.id, "label": b.label, "plots": rc.get("plots") or {}, "tiles": rc.get("tiles"),
                      "workers": (b.raw.get("workers") or {}).get("assigned"),
                      "plantingFirst": (b.raw.get("setup") or {}).get("plantingFirst")})
    return {"goods": sorted(world.goods.values(), key=lambda g: g["id"]), "series": series,
            "rates": rates(world, ctx), "reserve": r, "farms": farms}


@app.get("/api/requests")
@as_json
def requests():
    world, ctx, findings = LIVE.need()
    return {"requests": [{"text": f.message, "open_days": f.evidence.get("open_days")}
                         for f in findings if f.rule == "stream.requests"]}


@app.get("/api/map")
@as_json
def get_map():
    world, ctx, findings = LIVE.need()
    m = world.state.get("map")
    if not m:
        raise HTTPException(404, "no map scan yet")
    blds = [{"id": b.id, "name": b.name, "finished": b.finished, "paused": bool(b.raw.get("paused")),
             "x": b.x, "y": b.y, "z": b.z, "height": world.size_of(b)[2], "tiles": world.footprint(b), "door": b.door}
            for b in world.buildings if b.name != "Path"]
    return {
        "size": m["size"], "grids": {k: m[k] for k in ("top", "water", "contamination", "moist", "flow", "objects")},
        "legend": m["legend"], "sources": m.get("sources"),
        "roads": [list(n) for n in world.road.nodes], "connected": [list(n) for n in world.road_component],
        "only_links": [list(n) for n in world.only_links],
        "range": sorted({(t[0], t[1]) for t in world.range_tiles}) if world.range_tiles else None,
        "planting": [[x, y, v[1]] for (x, y), v in (world.planting or {}).items()],
        "cutting": [[x, y] for (x, y) in (world.cutting or {})],
        "reach": {k: sorted({(t[0], t[1]) for t in v}) for k, v in (world.reach_union or {}).items()},
        "buildings": blds,
        "findings": [{"rule": f.rule, "severity": f.severity, "message": f.message, "where": f.where}
                     for f in findings if f.where],
    }


def _public(d):
    """Drop internal keys (sets kept for overlap tests) so a proposal serialises."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


@app.get("/api/water")
@as_json
def get_water():
    """Water engineering (hydro.py): bodies, sources, existing pools, dam/badwater/reservoir/deck/pump/wheel plans."""
    world, ctx, findings = LIVE.need()
    h = hydro.analysis(world)
    if not h:
        raise HTTPException(404, "no map scan yet")
    bad = h.badwater()
    dams = h.dams()
    return {
        "bodies": h.body_rows(40), "sources": h.source_groups, "cores": h.cores(), "barriers": h.barriers(),
        "pools": h.pools(), "heldVolume": h.held_volume(),
        "dams": {"proposals": [_public(p) for p in dams["proposals"]],
                 "rejected": [_public(p) for p in dams["rejected"]], "candidates": dams["candidates"]},
        "badwater": {**{k: v for k, v in bad.items() if k not in ("riskSet", "diversions")},
                     "risk": sorted(bad["riskSet"]), "diversions": [_public(p) for p in bad["diversions"]]},
        "reservoirs": h.reservoirs(), "ponds": h.dry_farmland(), "decks": h.decks(), "pumps": h.pump_sites(),
        "wheels": h.wheel_sites(),
        "constants": {"damHold": hydro.DAM_HOLD, "leveeHold": hydro.LEVEE_HOLD, "evaporation": hydro.EVAPORATION,
                      "goodsPerUnit": hydro.GOODS_PER_UNIT, "contaminationReach": hydro.CONTAM_REACH},
        "findings": [fdict(f) for f in findings if f.rule.startswith("water.")],
    }


@app.get("/api/map3d")
@as_json
def get_map3d():
    """Caves and overhangs for the 3D view: the bridge's layered columns plus the flow speed grid."""
    world, ctx, findings = LIVE.need()
    m = world.state.get("map")
    if not m:
        raise HTTPException(404, "no map scan yet")
    return {"layered": m.get("layered") or [], "speed": m.get("speed")}


@app.get("/api/tile")
@as_json
def tile(x: int, y: int):
    world, ctx, findings = LIVE.need()
    if not world.has_map or not world.in_map(x, y):
        raise HTTPException(404, "off the map or no map scan")
    z = int(world.top[y, x])
    on = [b for b in world.buildings if (x, y) in world.footprint(b)]
    return {"x": x, "y": y, "top": z, "water": float(world.depth[y, x]), "badwater": float(world.dirt[y, x]),
            "moist": str(world.moist[y, x]), "object": world.object_at(x, y),
            "road": any((x, y, z + dz) in world.road.nodes for dz in (-1, 0, 1)),
            "only_link": any(n[:2] == (x, y) for n in world.only_links), "in_range": world.in_range(x, y, z),
            "planting": (world.planting or {}).get((x, y)), "cutting": (x, y) in (world.cutting or {}),
            "worked_by": sorted(k for k, v in (world.reach_union or {}).items() if (x, y, z) in v),
            "buildings": [{"id": b.id, "label": b.label, "finished": b.finished} for b in on],
            "findings": [fdict(f) for f in findings if f.where and tuple(f.where[:2]) == (x, y)]}


@app.get("/api/rules")
@as_json
def get_rules():
    from .rules import coverage
    rules, checked, unknown = coverage()
    store = LIVE.store()
    last = dict(store.db.execute("SELECT rule, MAX(last_day) FROM findings GROUP BY rule").fetchall())
    out = []
    for r in rules:
        mons = checked.get(r["id"], [])
        lday = max((last.get(m) or 0 for m in mons), default=0)
        out.append({**r, "monitors": mons, "last_day": lday or None,
                    "status": "checked" if mons else ("conduct" if r.get("kind") == "conduct" else "manual")})
    return {"rules": out, "unknown": unknown,
            "monitors": [{"id": m.id, "rules": m.rules, "doc": m.doc} for m in MONITORS.values()]}


# ------------------------------------------------------------------ planning and pre-checks (phase 5)
VALIDATIONS: dict = {}          # id -> record, also kept in the store (kv "validate:<id>") for verify()


@app.post("/api/validate")
@as_json
def post_validate(body: dict):
    """Pure computation: run the guards over harness calls before the AI sends them. Body: {"actions": [call text
    or {call, ...} dicts], "skip": [building ids to leave out (planned demolish/move)]}. Nothing reaches the game."""
    from . import checker, masterplan
    world, ctx, findings = LIVE.need()
    actions = body.get("actions") or body.get("calls") or []
    if isinstance(actions, (str, dict)):
        actions = [actions]
    res = checker.validate(world, actions, masterplan.reservations(masterplan.load(world), world), body.get("skip") or ())
    VALIDATIONS[res["id"]] = res
    try:
        LIVE.store().set(f"validate:{res['id']}", res)
    except Exception:
        pass
    return {**res, "text": checker.summary(res)}


@app.get("/api/verify/{vid}")
@as_json
def get_verify(vid: str):
    """After the AI ran a validated batch: was each placement made, door on the road, power linked, good set?"""
    from . import checker
    world, ctx, findings = LIVE.need()
    rec = VALIDATIONS.get(vid) or LIVE.store().get(f"validate:{vid}")
    if not rec:
        raise HTTPException(404, f"no validation {vid}")
    res = checker.verify(world, rec)
    if any(r["state"] == "not placed" for r in res["rows"]) and LIVE.source == "live":
        # The building list refreshes every 30 s: read it now rather than report a fresh placement as missing.
        asked = time.time()
        collector.FORCE.add("medium")
        while time.time() - asked < 15 and collector.TIER_AT.get("medium", 0) < asked:
            time.sleep(0.25)
        res = checker.verify(LIVE.need()[0], rec)
    return res


@app.get("/api/masterplan")
@as_json
def get_masterplan():
    """The saved masterplan (zones, reservations, build order); generated on first request. Accept, reject or
    regenerate zones with `python -m foreman plan --accept/--reject/--regenerate ZONE`."""
    from . import masterplan
    world, ctx, findings = LIVE.need()
    plan = masterplan.load(world) or masterplan.save(masterplan.generate(world))
    done = {s["id"]: masterplan.step_done(world, s) for s in plan["steps"]}
    return {**plan, "done": done, "text": masterplan.summary(plan)}


@app.get("/api/suggestions")
@as_json
def get_suggestions(n: int = 3):
    """The next n masterplan steps, each validated against the live map now (exact harness calls)."""
    from . import masterplan
    world, ctx, findings = LIVE.need()
    plan = masterplan.load(world)
    if not plan:
        return {"next": [], "text": "no masterplan yet: call foreman_masterplan once (it makes one), or GET /api/masterplan"}
    nxt = masterplan.suggestions(world, plan, max(1, min(n, 8)))
    return {"next": nxt, "text": masterplan.next_text(nxt)}


@app.get("/api/where")
@as_json
def get_where(template: str, x: int | None = None, y: int | None = None, radius: int = 10, good: str = ""):
    """A clean spot for a building near (x, y) (default: the District Centre): guards pass, plus the Path calls
    that join its door, validated together."""
    from . import checker, masterplan
    world, ctx, findings = LIVE.need()
    pl = masterplan.Planner(world)
    if not pl.cat.get(template):
        raise HTTPException(404, f"unknown template {template!r}")
    near = (x, y) if x is not None and y is not None else (pl.dc_door[:2] if pl.dc_door else None)
    if not near:
        raise HTTPException(400, "give x and y (no District Centre door found)")
    sp = pl.find_spot(template, near, max(1, min(radius, 30)), good=good or None)
    if not sp:
        return {"found": False, "text": f"no clean {template} spot within {radius} of {near}: widen the radius, "
                                        "or check the Water page for water-sited buildings"}
    step = {"id": "where", "calls": [], "actions": [], "after": [], "spots": []}
    pl.commit(step, sp, collector.base(template))
    v = checker.validate(world, step["actions"], masterplan.reservations(masterplan.load(world), world))
    VALIDATIONS[v["id"]] = v
    return {"found": True, "spot": step["spots"][0], "calls": step["calls"], "after": step["after"],
            "validation": {k: v[k] for k in ("id", "ok", "critical", "warn")}, "text": checker.summary(v)}


@app.get("/api/plantable")
@as_json
def get_plantable(x0: int, y0: int, x1: int, y1: int, plant: str = "Kohlrabi", fx: int | None = None,
                  fy: int | None = None, fz: int | None = None):
    """Which tiles in the rectangle a crop or tree can go on (moist, dry, clean, reachable, not a ledge, free),
    and the h.safe_plant call for it. (fx, fy, fz) = the planter's doorstep."""
    from . import checker
    world, ctx, findings = LIVE.need()
    a = {"call": "safe_plant", "plant": plant, "x0": x0, "y0": y0, "x1": x1, "y1": y1}
    if fx is not None and fy is not None and fz is not None:
        a["frm"] = [fx, fy, fz]
    res = checker.validate(world, [a])
    return {**res, "text": checker.summary(res)}


@app.get("/api/dam")
@as_json
def get_dam(x0: int, y0: int, x1: int, y1: int):
    """The AI's own straight dam/levee line: pool held, volume, what it floods, leaks, and place_line calls."""
    world, ctx, findings = LIVE.need()
    h = hydro.analysis(world)
    if not h:
        raise HTTPException(404, "no map scan yet")
    return h.custom_line(x0, y0, x1, y1)


@app.get("/api/events")
def get_events(since: int = 0, timeout: float = 25.0):
    """Long-poll: waits (up to timeout s) until the analysis is newer than `since`, then returns the new critical
    and warn findings. Use the returned `seq` as the next `since`."""
    end = time.time() + max(0.0, min(timeout, 60.0))
    with EVENTS.cond:
        while EVENTS.seq <= since and time.time() < end:
            EVENTS.cond.wait(max(0.05, end - time.time()))
        seq, items = EVENTS.seq, [e for e in EVENTS.items if e["seq"] > since]
    return Json({"seq": seq, "events": items[-50:]})


app.mount("/ui", StaticFiles(directory=UI), name="ui")


# ------------------------------------------------------------------ data sources
def start_live(db: str | None = None) -> None:
    """Collector thread: every pass re-runs the monitors and swaps the result into LIVE."""
    LIVE.db_path = Path(db) if db else None
    LIVE.source = "live"

    def loop():
        store = LIVE.store()

        def on_state(state):
            LIVE.set(*analyse(store, state))
        while True:
            try:
                collector.run(store, on_state)
            except bridge.BridgeError as e:     # game closed: keep serving the last state, retry
                LIVE.error = str(e)
                time.sleep(5)
            except Exception as e:              # a monitor bug must not kill the service
                LIVE.error = f"{type(e).__name__}: {e}"
                time.sleep(5)

    threading.Thread(target=loop, name="foreman-collector", daemon=True).start()


def load_fixture(path: str) -> None:
    """Serve one recorded state (tests/record_fixture.py) on a throwaway store."""
    LIVE.db_path = Path(tempfile.mkdtemp(prefix="foreman-")) / "fixture.db"
    LIVE.source = f"fixture {Path(path).name}"
    state = json.loads(Path(path).read_text())
    store = LIVE.store()
    store.put_snapshot("goods", state["goods"], state.get("game_day"))
    LIVE.set(*analyse(store, state))


def serve(fixture: str | None = None, db: str | None = None, port: int = PORT) -> None:
    import uvicorn
    if fixture:
        load_fixture(fixture)
    else:
        start_live(db)
    print(f"Foreman UI: http://127.0.0.1:{port}/  ({LIVE.source})", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
