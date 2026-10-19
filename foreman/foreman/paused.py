"""The paused register (rule paused-register): why each building is paused and when to resume it.

The AI logs a pause with `python -m foreman pause-reason <id> "<reason>" --until "<condition>"`.
Conditions: "<metric> <op> <value>" joined by " and ", e.g. "Log > 100", "food_days >= 5 and weather == temperate".
Metrics: any good id (available stock), food_days, water_days, beavers, cycle, day, weather.
This file is Foreman's own data; it never touches the game.
"""

from __future__ import annotations

import json
import operator
import re
import time

from .store import DATA

PATH = DATA / "paused.json"
OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq, "!=": operator.ne}
TERM = re.compile(r"^\s*(\w+)\s*(<=|>=|==|!=|<|>)\s*([\w.]+)\s*$")


def load(path=None) -> dict:
    try:
        return json.loads((path or PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(reg: dict, path=None) -> None:
    path = path or PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, indent=1), encoding="utf-8")


def add(building_id: str, reason: str, until: str = "", path=None) -> dict:
    if until:
        parse(until)            # raises ValueError on a bad condition
    reg = load(path)
    reg[building_id] = {"reason": reason, "until": until, "at": time.time()}
    save(reg, path)
    return reg[building_id]


def parse(cond: str) -> list[tuple[str, str, str]]:
    terms = []
    for part in re.split(r"\s+and\s+", cond.strip()):
        m = TERM.match(part)
        if not m:
            raise ValueError(f"bad condition term '{part}' (want '<metric> <op> <value>')")
        terms.append(m.groups())
    return terms


def metric(world, name: str):
    from .monitors.supply import food_days, water_use
    tm = world.colony["time"]
    if name == "food_days":
        return food_days(world)
    if name == "water_days":
        return world.good("Water")["available"] / max(1.0, water_use(world)[0])
    if name == "beavers":
        return world.beavers
    if name == "cycle":
        return tm["cycle"]
    if name == "day":
        return tm["cycleDay"]
    if name == "weather":
        return (world.colony.get("weather") or {}).get("state")
    if name in world.goods:
        return world.good(name)["available"]
    raise ValueError(f"unknown metric '{name}'")


def met(world, cond: str) -> bool | None:
    """True when every term holds; None if the condition can't be evaluated."""
    try:
        for name, op, value in parse(cond):
            have = metric(world, name)
            want = value if isinstance(have, str) or have is None else float(value)
            if not OPS[op](have, want):
                return False
        return True
    except (ValueError, TypeError):
        return None
