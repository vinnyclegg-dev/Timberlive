"""The web service on the recorded late-game save: every route answers and stays read-only."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foreman import server

FIXTURE = Path(__file__).parent / "fixtures" / "late-game.json"


@pytest.fixture(scope="module")
def client():
    server.load_fixture(str(FIXTURE))
    return TestClient(server.app)


@pytest.mark.parametrize("path", ["/api/status", "/api/overview", "/api/findings", "/api/buildings",
                                  "/api/supply", "/api/requests", "/api/map", "/api/rules", "/api/tile?x=72&y=70",
                                  "/api/water", "/api/map3d"])
def test_routes_answer(client, path):
    r = client.get(path)
    assert r.status_code == 200, r.text[:300]
    assert r.json()


def test_briefing_text(client):
    r = client.get("/api/briefing")
    assert r.status_code == 200 and "food" in r.text.lower()


def test_index_and_static(client):
    assert "Foreman" in client.get("/").text
    assert client.get("/ui/app.js").status_code == 200


def test_no_write_routes(client):
    """Read-only: no route accepts POST/PUT/DELETE except pure computations listed here."""
    compute_only = {"/api/validate"}
    for route in server.app.routes:
        methods = getattr(route, "methods", set()) or set()
        if methods - {"GET", "HEAD"}:
            assert route.path in compute_only, route.path


def test_map_shapes(client):
    m = client.get("/api/map").json()
    W, H = m["size"]["width"], m["size"]["height"]
    assert len(m["grids"]["top"]) == H and len(m["grids"]["top"][0]) == W
    assert m["buildings"] and all(b["tiles"] for b in m["buildings"])


def test_water_payload(client):
    w = client.get("/api/water").json()
    assert w["dams"]["proposals"] and all("_region" not in p for p in w["dams"]["proposals"])
    assert any(p["kinds"] == ["Dam"] and p["full"] for p in w["pools"])
    assert w["sources"] and w["bodies"]
    m = client.get("/api/map").json()
    assert all("height" in b for b in m["buildings"])
