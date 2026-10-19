"""Phase 5: the pre-checker on real placements, the masterplan from a fresh start and mid-game, the plan monitors,
the planning routes and the custom dam line. The masterplan file goes to tmp_path (never foreman/data)."""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foreman import checker, hydro, masterplan, server
from foreman.engine import analyse
from foreman.geometry import Catalog
from foreman.store import Store
from foreman.world import World

from fresh import fresh_state

FIXTURE = Path(__file__).with_name("fixtures") / "late-game.json"
LAND = ("SmallWarehouse", "BreedingPod", "FarmHouse", "Barrack", "SmallTank", "Inventor", "MediumWarehouse",
        "LumberjackFlag", "GathererFlag", "Forester", "Campfire")


@pytest.fixture(scope="module")
def state():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def plan_file(tmp_path, monkeypatch):
    monkeypatch.setattr(masterplan, "PLAN_FILE", tmp_path / "masterplan.json")
    return tmp_path / "masterplan.json"


@pytest.fixture(scope="module")
def fresh_plan(state):
    return masterplan.generate(World(fresh_state(state)))


def _run(state, tmp_path):
    return analyse(Store(tmp_path / "f.db"), copy.deepcopy(state))[2]


# ------------------------------------------------------------------ checker
def test_blueprint_doors_match_the_game(state):
    """Catalog rotation + entrance gives the same doorstep the game reports for every placed building."""
    w = World(state)
    cat = Catalog(w.blueprints)
    checked = 0
    for b in w.buildings:
        d = cat.door(b.name, b.x, b.y, b.raw.get("orientation", 0), b.z)
        if d and b.raw.get("pathTile"):
            assert list(d) == list(b.raw["pathTile"]), b.label
            checked += 1
    assert checked > 50


def test_replacing_fixture_buildings_is_clean(state):
    """Taking a placed building out of the map and placing it again where it stands: no critical guard fires."""
    w = World(state)
    done = set()
    for b in w.buildings:
        if b.name not in LAND or b.name in done or not b.finished:
            continue
        a = {"call": "place_building", "template": b.raw["template"], "x": b.x, "y": b.y, "z": b.z,
             "orientation": b.raw.get("orientation", 0)}
        if (b.raw.get("setup") or {}).get("good"):
            a["good"] = b.raw["setup"]["good"]
        res = checker.validate(w, [a], skip=(b.id,))
        assert res["critical"] == 0, (b.label, checker.summary(res))
        done.add(b.name)
    assert len(done) >= 6


def test_negative_placements(state):
    w = World(state)
    dc = next(b for b in w.buildings if b.name == "DistrictCenter")
    on_top = checker.validate(w, [f'place_building(template="SmallWarehouse.IronTeeth", x={dc.x}, y={dc.y}, '
                                  f'z={dc.z}, orientation=0)'])
    assert on_top["critical"] and any(c["guard"] == checker.G_FREE for c in on_top["results"][0]["checks"])
    locked = next(bp["template"] for bp in w.blueprints if not bp.get("unlocked") and bp.get("science"))
    res = checker.validate(w, [{"call": "place_building", "template": locked, "x": 10, "y": 10, "z": 5}])
    assert any(c["guard"] == checker.G_UNLOCK for c in res["results"][0]["checks"])
    bad = checker.validate(w, ["place_building(template=)"])
    assert bad["critical"] and bad["results"][0]["checks"][0]["guard"] == checker.G_TOOLS


def test_planting_in_water_is_flagged(state):
    w = World(state)
    res = checker.validate(w, [{"call": "plant_area", "plant": "Corn", "x0": 60, "y0": 40, "x1": 70, "y1": 50}])
    assert any(c["guard"] == checker.G_PLANT and c["severity"] != "info" for c in res["results"][0]["checks"])


# ------------------------------------------------------------------ masterplan
def test_fresh_opening_is_clean(fresh_plan):
    op = fresh_plan["opening"]
    assert op["ok"] and op["critical"] == 0 and op["warn"] == 0, op["problems"]
    ids = [s["id"] for s in fresh_plan["steps"]]
    for sid in ("open-dc-door", "open-water-1", "open-farm-1", "open-wood", "open-pods"):
        assert sid in ids
    assert ids.index("open-water-1") < ids.index("open-pods")      # pumps and tanks before pods
    calls = [c for s in fresh_plan["steps"] if s["stage"] == 1 for c in s["calls"]]
    assert any("safe_plant" in c for c in calls) and any("mark_tree_cutting" in c for c in calls)


def test_fresh_plan_saves_and_reloads(fresh_plan, plan_file):
    masterplan.save(copy.deepcopy(fresh_plan))
    assert plan_file.exists()
    p = masterplan.load()
    assert p["version"] == 1 and p["opening"]["ok"]
    zone = p["zones"][0]["id"]
    assert next(z for z in masterplan.set_status(zone, "accepted")["zones"] if z["id"] == zone)["status"] == "accepted"


def test_end_state_suggests_discharge(state):
    w = World(state)
    plan = masterplan.generate(w)
    assert all(masterplan.step_done(w, s) for s in plan["steps"] if s["stage"] == 1)
    nxt = masterplan.suggestions(w, plan, 3)
    assert nxt and "Discharge" in nxt[0]["title"] and nxt[0]["ready"]
    assert "unlock_building" in masterplan.next_text(nxt)


# ------------------------------------------------------------------ plan monitors
def test_plan_science_on_end(state, tmp_path):
    fs = [f for f in _run(state, tmp_path) if f.rule == "plan.science"]
    assert fs and "Discharge" in fs[0].fix


def test_pods_by_day_5(state, tmp_path):
    s = fresh_state(state)
    s["colony"]["time"]["cycleDay"] = 5
    fs = [f for f in _run(s, tmp_path) if f.rule == "plan.opening"]
    assert any(f.severity == "critical" and "Breeding Pod" in f.message for f in fs)
    assert any("pump" in f.message for f in fs)


def test_opening_farm_is_one_farmhouse_of_plots(fresh_plan):
    import re
    s = next(s for s in fresh_plan["steps"] if s["id"] == "open-farm-1")
    n, total = map(int, re.search(r"\((\d+) of the zone's (\d+) plots\)", s["title"]).groups())
    assert n <= total and (n >= masterplan.PLOTS_PER_FARMHOUSE or n == total)
    assert n < masterplan.PLOTS_PER_FARMHOUSE * 1.3 or n == total     # land.farm_plots would warn above 1.3x


def test_ledger_is_a_warning_before_day_5(state, tmp_path):
    s = fresh_state(state)
    assert {f.severity for f in _run(s, tmp_path) if f.rule == "pop.ledger"} == {"warn"}
    s["colony"]["time"]["cycleDay"] = 5
    assert {f.severity for f in _run(s, tmp_path / "b") if f.rule == "pop.ledger"} == {"critical"}


# ------------------------------------------------------------------ routes
@pytest.fixture(scope="module")
def client():
    server.load_fixture(str(FIXTURE))
    return TestClient(server.app)


def test_validate_and_verify_routes(client):
    r = client.post("/api/validate", json={"actions": ['place_building(template="SmallWarehouse.IronTeeth", '
                                                       'x=68, y=81, z=5, orientation=0)']})
    j = r.json()
    assert r.status_code == 200 and j["ok"] and "FOREMAN validate" in j["text"]
    v = client.get(f"/api/verify/{j['id']}").json()
    assert v["rows"][0]["state"] == "not placed"
    assert client.get("/api/verify/nope").status_code == 404


@pytest.mark.parametrize("path", ["/api/masterplan", "/api/suggestions?n=2", "/api/where?template=SmallWarehouse&radius=20",
                                  "/api/plantable?x0=60&y0=40&x1=70&y1=50&plant=Corn",
                                  "/api/dam?x0=68&y0=36&x1=73&y1=36", "/api/events?since=0&timeout=0"])
def test_planning_routes(client, path):
    r = client.get(path)
    assert r.status_code == 200, r.text[:300]
    assert r.json()


def test_where_unknown_template(client):
    assert client.get("/api/where?template=NoSuchThing").status_code == 404


def test_events_long_poll_times_out(client):
    seq = client.get("/api/events?since=0&timeout=0").json()["seq"]
    j = client.get(f"/api/events?since={seq}&timeout=0.2").json()
    assert j["seq"] == seq and j["events"] == []


def test_briefing_has_next(client):
    client.get("/api/masterplan")                   # makes the plan file (tmp_path)
    assert "NEXT" in client.get("/api/briefing").text


# ------------------------------------------------------------------ custom dam line
def test_custom_line_existing_levee(state):
    h = hydro.Hydro(World(state))
    out = h.custom_line(68, 36, 73, 36)
    assert out["axis"] == "x" and len(out["line"]) == 6 and out["options"]
    assert all("leaks" in o and "calls" in o for o in out["options"])
    assert h.custom_line(1, 1, 5, 5)["error"].startswith("the line must be straight")


# ------------------------------------------------------------------ rulebook
def test_every_rule_is_checked_or_conduct():
    """Every rule in the rulebook is either checked by a monitor/guard or is AI conduct, and every rule id a
    monitor or guard names exists in the rulebook."""
    from foreman.rules import coverage
    rules, checked, unknown = coverage()
    assert rules and not unknown
    missing = [r["id"] for r in rules if r["id"] not in checked and r.get("kind") != "conduct"]
    assert not missing


def test_driver_reads_briefing(client):
    """The local-model driver parses the live briefing's header for its food/water log."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("driver", Path(__file__).parents[1] / "local_model_driver.py")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    m = driver.metrics(client.get("/api/briefing").text)
    assert {"cycle", "day", "food_days", "water_days", "adults", "kits"} <= set(m)
    assert m["cycle"] == 9 and m["food_days"] > 3 and m["water_days"] > 3
    assert set(driver.ACTIONS) >= {"place_building", "safe_plant", "building_action"}


def test_new_game_clears_old_game(state, tmp_path, monkeypatch, plan_file):
    """Another game (District Centre moved) clears the store, the plan and the paused register."""
    from foreman import collector, paused
    monkeypatch.setattr(paused, "PATH", tmp_path / "paused.json")
    store = Store(tmp_path / "t.db")
    old = copy.deepcopy(state["colony"])
    store.put_snapshot("colony", old, 900)
    masterplan.save(masterplan.generate(World(state)))
    paused.PATH.write_text("{}")
    assert not collector.new_game(store, old)                       # same game: nothing cleared
    assert masterplan.load(World(state)) is not None
    new = copy.deepcopy(old)
    new["districts"][0].update(x=20, y=30)
    assert collector.new_game(store, new)
    assert store.latest("colony") is None and store.get("ledger_imported")
    assert not plan_file.exists() and not paused.PATH.exists()
    assert not collector.new_game(store, new)


def test_plan_from_another_map_is_ignored(state, plan_file):
    masterplan.save(masterplan.generate(World(state)))
    other = copy.deepcopy(state)
    other["colony"]["districts"][0].update(x=20, y=30)
    assert masterplan.load(World(state)) is not None
    assert masterplan.load(World(other)) is None
    assert masterplan.load() is not None                            # without a world: the file as saved


def test_ledger_from_another_game_is_skipped(tmp_path):
    from foreman.engine import import_harness_ledger
    led = tmp_path / "pop-ledger.json"
    led.write_text(json.dumps([{"cycle": 1, "day": 3, "text": "born"}, {"cycle": 9, "day": 2, "text": "died"}]))
    new = Store(tmp_path / "a.db")
    assert import_harness_ledger(new, 101.2, led) == 0 and new.get("ledger_imported")
    same = Store(tmp_path / "b.db")
    assert import_harness_ledger(same, 914.5, led) == 2
