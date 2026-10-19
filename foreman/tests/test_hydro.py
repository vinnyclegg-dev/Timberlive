"""Water engineering on the late-game fixture: existing pools, bodies and sources, the dam planner, decks,
badwater, and the water monitors."""

import copy
import json
from pathlib import Path

import pytest

from foreman import hydro
from foreman.engine import analyse
from foreman.store import Store
from foreman.world import World

FIXTURE = Path(__file__).with_name("fixtures") / "late-game.json"


@pytest.fixture(scope="module")
def state():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def h(state):
    return hydro.Hydro(World(state))


def test_existing_dam_pools_match_the_water(h):
    """The three Dam lines hold 0.65 over a z4 bed; the grid shows 0.7 (0.1 steps), so about -7%."""
    dams = [p for p in h.pools() if p["kinds"] == ["Dam"]]
    assert len(dams) == 3
    for p in dams:
        assert p["full"] and not p["capped"] and p["region"]
        assert abs(p["error"]) <= 0.10, p


def test_pools_below_their_crest_have_no_region(h):
    for p in h.pools():
        if not p["full"]:
            assert p["region"] == [] and p["error"] is None


def test_bodies_and_sources_traced(h):
    river = next(g for g in h.source_groups if g["name"] == "WaterSource")
    assert river["body"] is not None and river["downstream"]
    labels = {f for b in h.bodies for f in b["fedBy"]}
    assert any(label.startswith("WaterSource(39-43,127-127") for label in labels)
    drain = next(g for g in h.source_groups if g["name"] == "BadtideDrain")
    assert drain["strength"] == 0                      # not flowing yet
    assert h.cores() == []                             # this map has no Unstable Cores


def test_dam_planner_proposals_hold_and_do_not_leak(h):
    plan = h.dams()
    assert plan["proposals"]
    for p in plan["proposals"]:
        assert not p["flooded"] and not p["capped"] and p["added"] > 0
        region = set(map(tuple, p["region"]))
        assert not region & set(map(tuple, p["line"]))
        assert all(0 < x < h.W - 1 and 0 < y < h.H - 1 for x, y in region)   # the map edge drains
        assert p["calls"] and all(c.startswith("place_line(") for c in p["calls"])
        for x, y in region:
            assert h.top[y, x] < p["level"]


def test_flood_fill_respects_crests(h):
    region, capped = h.flood(4.65, [(50, 71)], blocked=set())
    assert not capped
    assert all(h.crest[y, x] < 4.65 for x, y in region)


def test_decks_on_clean_shallow_water(h):
    decks = h.decks()
    assert decks
    for d in decks:
        x0, y0, x1, y1 = d["bbox"]
        assert d["tiles"] == (x1 - x0 + 1) * (y1 - y0 + 1) >= 4
        assert (h.dirt[y0:y1 + 1, x0:x1 + 1] < 0.05).all() and h.wet[y0:y1 + 1, x0:x1 + 1].all()
        assert d["calls"][0].startswith("place_area(template=\"Platform.")


def test_badwater_mixing_and_soil_risk(h):
    bad = h.badwater()
    assert bad["mixing"]                               # the lower river takes both badwater sources
    assert bad["riskTiles"] > 0
    assert bad["badPumps"] == []


def test_reservoirs_are_dry_bowls(h):
    for r in h.reservoirs():
        assert r["tiles"] == len(r["cells"]) >= 4
        assert all(not h.wet[y, x] for x, y in r["cells"])
        assert r["meanDepth"] >= 1.0


def test_cache_reuses_analysis(state):
    w = World(state)
    assert hydro.analysis(w) is hydro.analysis(World(state))


def test_water_monitors_fire(state, tmp_path):
    _, _, findings = analyse(Store(tmp_path / "t.db"), state)
    rules = {f.rule for f in findings}
    assert {"water.dams", "water.fields", "water.badwater", "water.reservoir"} <= rules
    assert "foreman.error" not in rules


def test_no_dam_yet_is_flagged(state, tmp_path):
    s = copy.deepcopy(state)
    s["buildings"] = [b for b in s["buildings"] if not b["template"].startswith(("Dam.", "Levee."))]
    _, _, findings = analyse(Store(tmp_path / "t.db"), s)
    first = [f for f in findings if f.rule == "water.dams" and f.entity == "first"]
    assert first and first[0].severity == "critical" and first[0].fix.startswith("place_line(")


def test_food_network_without_steady_power(state, tmp_path):
    s = copy.deepcopy(state)
    s["buildings"] = [b for b in s["buildings"] if not b["template"].startswith("SteamEngine.")]
    _, _, findings = analyse(Store(tmp_path / "t.db"), s)
    assert any(f.rule == "water.power" and f.severity == "critical" for f in findings)
