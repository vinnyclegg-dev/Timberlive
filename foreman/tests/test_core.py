"""Offline tests: read-only client, the S2E1 end fixture, and lesson fixtures built from it."""

import copy
import inspect
import json
from pathlib import Path

import pytest

from foreman import bridge
from foreman.engine import analyse
from foreman.store import Store
from foreman.world import World

FIXTURE = Path(__file__).with_name("fixtures") / "s2e1-end.json"
WRITE_PATHS = ("/api/demolish", "/api/building/act", "/api/building/pause", "/api/building/priority",
               "/api/building/workers", "/api/speed", "/api/plant", "/api/unplant", "/api/unlock", "/api/cutting-area",
               "/api/map/demolish-resources", "/api/camera/layers", "/api/work-hours", "/api/save", "/api/load",
               "/api/new-game", "/api/dev/quit")


@pytest.fixture
def state():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def run(state, tmp_path):
    store = Store(tmp_path / "t.db")
    store.add_alerts(state.get("alerts_all", []))
    return analyse(store, state)


def rules_of(findings):
    return {f.rule for f in findings}


# ------------------------------------------------------------------ read-only

def test_client_has_no_write_endpoints():
    src = inspect.getsource(bridge)
    for p in WRITE_PATHS:
        assert f'"{p}"' not in src, p
    for p in ("/api/demolish", "/api/speed", "/api/building/pause", "/api/save"):
        with pytest.raises(bridge.ReadOnlyViolation):
            bridge._get(p)
        with pytest.raises(bridge.ReadOnlyViolation):
            bridge._post_read(p, {})


def test_place_only_as_check():
    with pytest.raises(bridge.ReadOnlyViolation):
        bridge._post_read("/api/place", {"template": "Path", "x": 1, "y": 1, "z": 1})
    with pytest.raises(bridge.ReadOnlyViolation):
        bridge._post_read("/api/place", {"template": "Path", "check": True, "placements": [{"x": 1}]})


# ------------------------------------------------------------------ S2E1 end (matches watch.py + audit there)

def test_s2e1_end_matches_harness(state, tmp_path):
    world, ctx, findings = run(state, tmp_path)
    r = rules_of(findings)
    # audit.py --no-fix on this save: three workshops marked for emptying, science 655 unspent.
    assert {"bld.emptying", "progress.science"} <= r
    assert sum(f.rule == "bld.emptying" for f in findings) == 3
    # monitor.py: PineResin, MetalBlock, Berries, CornRation FULL; Kohlrabi EMPTY; water reserve ok (2139 vs 2142).
    full = {f.entity for f in findings if f.rule == "storage.full"}
    assert full == {"PineResin", "MetalBlock", "Berries", "CornRation"}
    assert "water.reserve" not in r and "food.days" not in r
    # watch.py: critical needs (Hunger, Thirst) and POPULATION AT RISK (6 pods, want 9).
    assert {"pop.needs", "pop.ledger"} <= r
    # The game shows no "not connected" status: Foreman's own road flood fill must agree for every door.
    assert "bld.connected" not in r
    assert all(world.door_connected(b) for b in world.buildings if b.door and b.name != "DistrictCenter")


# ------------------------------------------------------------------ lessons (each past mistake -> a finding)

def building(state, name):
    return next(b for b in state["buildings"] if b["template"].split(".")[0] == name and b["finished"])


def test_tank_without_good(state, tmp_path):
    tank = building(state, "SmallTank")
    tank["setup"] = None
    _, _, findings = run(state, tmp_path)
    f = next(f for f in findings if f.rule == "bld.storage_assigned" and f.entity == tank["id"])
    assert '"Water"' in f.fix and tank["id"] in f.fix


def test_emptying_food_store_is_critical(state, tmp_path):
    wh = next(b for b in state["buildings"] if b["template"].startswith("SmallWarehouse")
              and (b.get("setup") or {}).get("good") == "Berries")
    wh["setup"]["emptying"] = True
    _, _, findings = run(state, tmp_path)
    f = next(f for f in findings if f.rule == "bld.emptying" and f.entity == wh["id"])
    assert f.severity == "critical" and "UnmarkForEmptying" in f.fix


def test_pump_next_to_badwater(state, tmp_path):
    pump = building(state, "DeepWaterPump")
    x, y = pump["x"], pump["y"]
    row = list(state["map"]["water"][y])
    crow = list(state["map"]["contamination"][y])
    row[x + 1], crow[x + 1] = "5", "9"
    state["map"]["water"][y], state["map"]["contamination"][y] = "".join(row), "".join(crow)
    _, _, findings = run(state, tmp_path)
    assert any(f.rule == "bld.pump_badwater" and f.entity == pump["id"] for f in findings)


def test_power_short(state, tmp_path):
    for b in state["buildings"]:
        if b.get("power"):
            b["power"]["networkSupply"] = 100
    _, _, findings = run(state, tmp_path)
    assert any(f.rule == "bld.power" and f.severity == "warn" for f in findings)


def test_unlinked_power(state, tmp_path):
    smelter = building(state, "Smelter")
    for p in smelter["powerConnections"]:
        p["connected"] = False
    _, _, findings = run(state, tmp_path)
    assert any(f.rule == "bld.power_link" and f.entity == smelter["id"] for f in findings)


def test_food_days_below_3(state, tmp_path):
    for g in state["goods"]:
        if g["id"] in ("Berries", "CornRation"):
            g["available"] = 50
    _, _, findings = run(state, tmp_path)
    assert next(f for f in findings if f.rule == "food.days").severity == "critical"


def test_cut_road_disconnects_door(state, tmp_path):
    world = World(copy.deepcopy(state))
    # Remove every path: only the district centre's own door can be connected.
    state["buildings"] = [b for b in state["buildings"] if b["template"] != "Path"]
    _, _, findings = run(state, tmp_path)
    assert any(f.rule == "bld.connected" for f in findings)
    assert world.only_links  # the live network has single-link tiles (phase 2 road.only_link uses them)


# ------------------------------------------------------------------ phase 2 lessons

def set_char(state, key, x, y, ch):
    row = list(state["map"][key][y])
    row[x] = ch
    state["map"][key][y] = "".join(row)


def test_building_on_water_film(state, tmp_path):
    # Lesson: buildings set on a thin water film (0.17) stop working while flooded.
    wh = building(state, "MediumWarehouse")
    set_char(state, "water", wh["x"], wh["y"], "2")
    _, _, findings = run(state, tmp_path)
    assert any(f.rule == "bld.flooded" and f.entity == wh["id"] for f in findings)


def test_single_road_link_reported(state, tmp_path):
    _, _, findings = run(state, tmp_path)
    links = [f for f in findings if f.rule == "road.only_link"]
    assert links and all(len(f.evidence["cut"]) >= 3 for f in links)
    # One tile per chain of single links.
    assert len({tuple(f.where[:2]) for f in links}) == len(links)


def test_corn_on_contaminated_soil(state, tmp_path):
    (x, y), (z, _) = next(((xy, v) for xy, v in
                           ((tuple(p[:2]), (p[2], p[3])) for p in state["marks"]["planting"])
                           if v[1] == "Corn" and int(state["map"]["top"][xy[1]][xy[0]], 36) == v[0]))
    set_char(state, "moist", x, y, "x")
    _, _, findings = run(state, tmp_path)
    f = next(f for f in findings if f.rule == "land.plants_wrong" and "contaminated" in f.message)
    assert f"clear_planting({x}, {y}, {x}, {y})" in f.fix


def test_plantable_land_found(state, tmp_path):
    _, _, findings = run(state, tmp_path)
    f = next(f for f in findings if f.rule == "land.plantable")
    assert f.fix.startswith("h.safe_plant(")


def test_stale_plan_item(state, tmp_path):
    state["colony"]["time"]["speed"] = 3
    state["overlay"]["todos"] = [{"text": "Build the oil press beside the smelter", "done": False}]
    full = copy.deepcopy(state)
    state["buildings"] = [b for b in state["buildings"] if not b["template"].startswith("OilPress")]
    store = Store(tmp_path / "t.db")
    analyse(store, state)
    _, _, findings = analyse(store, full)
    assert any(f.rule == "stream.plan_stale" and "OilPress" in f.message for f in findings)


def test_not_producing_with_reason(state, tmp_path):
    state["colony"]["time"]["speed"] = 3
    p = next(p for p in state["production"] if p["recipe"] == "Plank")
    p["ingredients"] = False
    store = Store(tmp_path / "t.db")
    for _ in range(7):
        _, _, findings = analyse(store, state)
    f = next(f for f in findings if f.rule == "bld.producing" and f.entity == p["id"])
    assert "no inputs" in f.message


def test_site_outside_build_range(state, tmp_path):
    site = copy.deepcopy(building(state, "SmallTank"))
    site.update(id="site-far", finished=False, x=2, y=2, z=30, pathTile=[2, 1, 30])
    state["buildings"].append(site)
    _, _, findings = run(state, tmp_path)
    f = next(f for f in findings if f.rule == "bld.build_range")
    assert "site-far" in f.evidence["ids"]


def test_old_age_wave(state, tmp_path):
    _, _, findings = run(state, tmp_path)
    assert any(f.rule == "pop.age_wave" for f in findings)


def test_hazard_record_and_longest(state, tmp_path):
    store = Store(tmp_path / "t.db")
    state["colony"]["weather"] = {"state": "hazardous", "hazard": "Drought", "daysRemaining": 9}
    _, ctx, findings = analyse(store, state)
    assert any(f.rule == "hazard.record" and f.entity == "longest" for f in findings)
    assert store.get("longest_hazard_days") == 9
    later = copy.deepcopy(state)
    later["colony"]["weather"] = {"state": "temperate"}
    later["colony"]["time"]["cycleDay"] += 9
    _, _, findings = analyse(store, later)
    f = next(f for f in findings if f.rule == "hazard.record" and f.entity == "over")
    assert "knowledge/goals.md" in f.message and store.get("hazards")[-1]["length"] == 9


def test_water_falling_forecast(state, tmp_path):
    store = Store(tmp_path / "t.db")
    old = copy.deepcopy(state["goods"])
    for g in old:
        if g["id"] == "Water":
            g["available"] += 1000
    store.put_snapshot("goods", old, state["game_day"] - 1)
    _, _, findings = analyse(store, state)
    f = next(f for f in findings if f.rule == "forecast.stock" and f.entity == "Water-empty")
    assert "-1000/day" in f.message


def test_paused_register_resume(state, tmp_path, monkeypatch):
    from foreman import paused
    monkeypatch.setattr(paused, "PATH", tmp_path / "paused.json")
    jack = next(b for b in state["buildings"] if b["template"].startswith("LumberjackFlag") and b.get("paused"))
    paused.add(jack["id"], "protect young oaks", "Log > 10 and weather == temperate")
    _, _, findings = run(state, tmp_path)
    f = next(f for f in findings if f.rule == "bld.paused" and f.entity == jack["id"])
    assert "paused=False" in f.fix
    with pytest.raises(ValueError):
        paused.add(jack["id"], "x", "Log is big")


# ------------------------------------------------------------------ operations discipline

def test_food_crisis_pauses_non_food(state, tmp_path):
    for g in state["goods"]:
        if g["id"] in ("Berries", "CornRation", "Kohlrabi"):
            g["available"] = 50
    _, _, findings = run(state, tmp_path)
    f = next(f for f in findings if f.rule == "ops.crisis")
    assert f.severity == "critical" and "set_paused(" in f.fix
    assert not any(k in f.fix for k in ("FarmHouse",))


def test_long_workday_flagged(state, tmp_path):
    state["hours"] = {"hours": 20, "endsAt": 20, "now": 10, "working": True}
    _, _, findings = run(state, tmp_path)
    f = next(f for f in findings if f.rule == "ops.workday")
    assert f.fix == "set_work_hours(hours=16)" and f.severity == "warn"    # fixture has critical hunger


def test_power_shed_order(state, tmp_path):
    net = max(state["power"], key=lambda n: n["supply"])
    net["demand"] = net["supply"] + 100
    _, _, findings = run(state, tmp_path)
    f = next(f for f in findings if f.rule == "ops.power_shed")
    assert "set_paused(" in f.fix


def test_pre_hazard_checklist(state, tmp_path):
    state["colony"]["weather"] = {"state": "approaching", "hazard": "Drought", "daysUntil": 2}
    _, _, findings = run(state, tmp_path)
    f = next(f for f in findings if f.rule == "ops.pre_hazard")
    assert "checklist" in f.message and "wood" in f.message


def test_paused_on_stream(state, tmp_path):
    import time as _t
    state["overlay"]["thoughts"] = [{"text": "hi", "at": _t.time() - 30}]
    state["colony"]["time"]["speed"] = 0
    _, _, findings = run(state, tmp_path)
    assert any(f.rule == "ops.speed" and f.severity == "warn" for f in findings)
