"""One analysis pass: state -> World -> findings (with history from the store)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import collector
from .findings import rank, run_all
from .monitors import LONGEST_HAZARD_DAYS
from .store import Store
from .world import World

LEDGER = collector.ROOT / "harness" / "cache" / "pop-ledger.json"


@dataclass
class Ctx:
    store: Store
    longest_hazard_days: float


def import_harness_ledger(store: Store, game_day: float | None = None, path: Path = LEDGER) -> int:
    """Seed births/deaths from the harness ledger (alerts before this bridge load are gone from the game).
    A ledger with events after today belongs to another game (a new map before the harness reset it): skipped."""
    if store.get("ledger_imported") or not path.exists():
        return 0
    events = json.loads(path.read_text())
    if game_day is not None and any(e["cycle"] * 100 + e["day"] > game_day + 1 for e in events):
        store.set("ledger_imported", True)
        return 0
    n = store.add_alerts([{"cycle": e["cycle"], "day": e["day"], "text": e["text"]} for e in events])
    store.set("ledger_imported", True)
    return n


def analyse(store: Store, state: dict, record: bool = True):
    world = World(state)
    ctx = Ctx(store, store.get("longest_hazard_days", LONGEST_HAZARD_DAYS))
    findings = run_all(world, ctx)
    if record:
        store.record_findings(findings, world.game_day())
        for f in findings:
            f.runs = store.finding_age(f.key)[0] or 1
    return world, ctx, rank(findings)


def snapshot(store: Store, tiers=("fast", "medium", "slow"), map_max_age: float = collector.TIERS["slow"]):
    state = collector.collect(store, tiers=tiers, map_max_age=map_max_age)
    return analyse(store, state)
