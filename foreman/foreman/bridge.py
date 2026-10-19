"""Read-only client for the TimberLive bridge.

Foreman never plays, so this client has no write methods: every request goes through `_get` or
`_post_read`, and both refuse any path that is not on the read allowlist below. The token is read
from %LOCALAPPDATA%\\TimberLive\\bridge.json on each call and is never logged or returned.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

CONNECTION_FILE = Path(os.environ.get("LOCALAPPDATA", "")) / "TimberLive" / "bridge.json"

READ_GET = {
    "/api/ping", "/api/state", "/api/goods", "/api/buildings", "/api/building/inspect", "/api/needs",
    "/api/alerts", "/api/automation", "/api/blueprints", "/api/plantables", "/api/map", "/api/map/size",
    "/api/map/tile", "/api/map/columns", "/api/map/water-sources", "/api/map/plants", "/api/camera",
    "/api/camera/working-beavers", "/api/saves", "/api/new-game/options",
    # Foreman's own read views (mod/TimberLive.Bridge.Logic/Modules/ForemanModule.cs)
    "/api/foreman/power", "/api/foreman/production", "/api/foreman/stock", "/api/foreman/sites",
    "/api/foreman/range", "/api/foreman/marks", "/api/foreman/beavers", "/api/foreman/reach", "/api/foreman/hours",
}
# POSTs that only read: placement scan, nav-mesh distances, and a placement *check* (check=true only).
READ_POST = {"/api/place/scan", "/api/map/reachable", "/api/place"}


class BridgeError(Exception):
    pass


class ReadOnlyViolation(BridgeError):
    pass


def _connection() -> tuple[str, str]:
    try:
        data = json.loads(CONNECTION_FILE.read_text())
    except FileNotFoundError as e:
        raise BridgeError("bridge not running (no bridge.json): start Timberborn with the TimberLive mod") from e
    return f"http://127.0.0.1:{data['port']}", data["token"]


def _request(method: str, path: str, params: dict | None = None, body: dict | None = None,
             timeout: float = 30) -> Any:
    base, token = _connection()
    try:
        r = httpx.request(method, base + path, params=params, json=body,
                          headers={"X-TimberLive-Token": token}, timeout=timeout)
    except httpx.HTTPError as e:
        raise BridgeError(f"bridge unreachable ({e.__class__.__name__}); is the game running?") from e
    if r.status_code != 200:
        try:
            msg = r.json().get("error", r.text)
        except ValueError:
            msg = r.text
        raise BridgeError(f"{r.status_code} {path}: {msg}")
    return r.json()


def _get(path: str, **params) -> Any:
    if path not in READ_GET:
        raise ReadOnlyViolation(f"{path} is not a read endpoint")
    return _request("GET", path, params={k: v for k, v in params.items() if v is not None} or None)


def _post_read(path: str, body: dict) -> Any:
    if path not in READ_POST:
        raise ReadOnlyViolation(f"{path} is not a read endpoint")
    if path == "/api/place" and (body.get("check") is not True or "placements" in body):
        raise ReadOnlyViolation("/api/place is only allowed as a single check=true test")
    return _request("POST", path, body=body, timeout=60)


# ---------------------------------------------------------------- reads

def ping() -> dict:
    return _get("/api/ping")


def colony() -> dict:
    return _get("/api/state")


def goods(include_empty: bool = False) -> list[dict]:
    return _get("/api/goods", all=str(include_empty).lower())


def buildings(template: str | None = None) -> list[dict]:
    return _get("/api/buildings", template=template)


def inspect(building_id: str, all: bool = False) -> dict:
    return _get("/api/building/inspect", id=building_id, all="true" if all else None)


def needs() -> dict:
    return _get("/api/needs")


def alerts(since: int = 0) -> dict:
    return _get("/api/alerts", since=since)


def map_size() -> dict:
    return _get("/api/map/size")


def map_view(x: int, y: int, w: int, h: int) -> dict:
    return _get("/api/map", x=x, y=y, w=w, h=h)


def map_columns(x: int, y: int, w: int = 64, h: int = 64) -> dict:
    return _get("/api/map/columns", x=x, y=y, w=w, h=h)


def water_sources() -> Any:
    return _get("/api/map/water-sources")


def plants(x: int, y: int, w: int, h: int) -> Any:
    return _get("/api/map/plants", x=x, y=y, w=w, h=h)


def blueprints(**params) -> Any:
    return _get("/api/blueprints", **params)


def working_beavers() -> Any:
    return _get("/api/camera/working-beavers")


def reachable(start: list[int], targets: list[list[int]]) -> dict:
    return _post_read("/api/map/reachable", {"from": start, "targets": targets})


def scan_spots(body: dict) -> dict:
    return _post_read("/api/place/scan", body)


def check_place(template: str, x: int, y: int, z: int, orientation: int = 0, flip: bool = False) -> dict:
    return _post_read("/api/place", {"template": template, "x": x, "y": y, "z": z,
                                     "orientation": orientation, "flip": flip, "check": True})


def foreman_view(name: str, **params) -> Any:
    """GET /api/foreman/<name>: power, production, stock, sites, range, marks, beavers."""
    return _get(f"/api/foreman/{name}", **params)
