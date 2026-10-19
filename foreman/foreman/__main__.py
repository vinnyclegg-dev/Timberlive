"""foreman CLI (read-only advisor; never changes the game).

  python -m foreman brief [--top N] [--map-age SECS]   collect once, print the ~30-line briefing
  python -m foreman findings [--json]                   every current finding with its suggested harness call
  python -m foreman collect                             run the collector loop (tiers 5 s / 30 s / 3 min)
  python -m foreman serve [--fixture FILE] [--port 8097]  collector + web UI and JSON API (use instead of collect)
  python -m foreman rules                               rulebook coverage report
  python -m foreman reset                               new game: clear the store
  python -m foreman pause-reason ID "REASON" [--until "Log > 100"]   log why a building is paused
  python -m foreman plan [--regenerate [ZONE]] [--accept ZONE] [--reject ZONE] [--next N] [--json] [--fixture FILE]
                                                        the masterplan: zones, build order, next validated steps
  python -m foreman check 'place_building(template="Path", x=1, y=2, z=5)' ...   validate harness calls (no game change)
"""

from __future__ import annotations

import argparse
import json
import sys

from . import bridge, collector
from .store import Store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="foreman")
    ap.add_argument("command", choices=["brief", "findings", "collect", "serve", "rules", "reset", "pause-reason",
                                           "plan", "check"])
    ap.add_argument("args", nargs="*", help="pause-reason: building id and reason; check: harness calls")
    ap.add_argument("--regenerate", nargs="?", const="", default=None, help="plan: rebuild the plan, or move ZONE")
    ap.add_argument("--accept", default=None, help="plan: mark a zone accepted")
    ap.add_argument("--reject", default=None, help="plan: mark a zone rejected (its steps are skipped)")
    ap.add_argument("--next", type=int, default=3, help="plan: how many next steps to validate")
    ap.add_argument("--until", default="", help='pause-reason resume condition, e.g. "Log > 100 and weather == temperate"')
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--map-age", type=float, default=collector.TIERS["slow"],
                    help="reuse the stored map scan if younger than this many seconds")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--db", default=None)
    ap.add_argument("--fixture", default=None, help="serve: a recorded state instead of the live game")
    ap.add_argument("--port", type=int, default=8097)
    a = ap.parse_intermixed_args(argv)
    store = Store(a.db) if a.db else Store()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if a.command == "reset":
        store.reset()
        print("store cleared")
        return 0
    if a.command == "pause-reason":
        from . import paused
        if len(a.args) != 2:
            print('usage: python -m foreman pause-reason <building id> "<reason>" [--until "<metric op value>"]')
            return 2
        try:
            print(json.dumps(paused.add(a.args[0], a.args[1], a.until)))
        except ValueError as e:
            print(f"FOREMAN: {e}")
            return 2
        return 0
    if a.command == "serve":
        from .server import serve
        store.db.close()
        serve(fixture=a.fixture, db=a.db, port=a.port)
        return 0
    if a.command == "rules":
        from .rules import coverage_report
        print(coverage_report())
        return 0
    if a.command in ("plan", "check"):
        return plan_cmd(a, store)
    try:
        if a.command == "collect":
            from .engine import analyse

            def on_state(state):
                world, _, findings = analyse(store, state)
                crit = [f for f in findings if f.severity == "critical"]
                print(f"c{world.colony['time']['cycle']}d{world.colony['time']['cycleDay']} "
                      f"{len(findings)} findings, {len(crit)} critical", flush=True)
            collector.run(store, on_state)
            return 0
        from .engine import snapshot
        world, ctx, findings = snapshot(store, map_max_age=a.map_age)
    except bridge.BridgeError as e:
        print(f"FOREMAN: {e}")
        return 2
    if a.command == "brief":
        from .briefing import briefing
        print(briefing(world, ctx, findings, top=a.top))
    elif a.json:
        print(json.dumps([f.__dict__ for f in findings], indent=1))
    else:
        for f in findings:
            print(f.line())
    return 0


def load_world(a, store):
    from .world import World
    if a.fixture:
        return World(json.loads(open(a.fixture, encoding="utf-8").read()))
    from .engine import snapshot
    return snapshot(store, map_max_age=a.map_age)[0]


def plan_cmd(a, store) -> int:
    from . import masterplan
    try:
        if a.accept or a.reject:
            plan = masterplan.set_status(a.accept or a.reject, "accepted" if a.accept else "rejected")
            print(f"zone {a.accept or a.reject} {'accepted' if a.accept else 'rejected'} (plan v{plan.get('version')})")
            return 0
        world = load_world(a, store)
    except (bridge.BridgeError, ValueError) as e:
        print(f"FOREMAN: {e}")
        return 2
    if a.command == "check":
        from . import checker
        if not a.args:
            print("usage: python -m foreman check '<harness call>' ['<call>' ...]")
            return 2
        res = checker.validate(world, a.args, masterplan.reservations(masterplan.load(world), world))
        print(json.dumps(res, indent=1, default=str) if a.json else checker.summary(res))
        return 0 if res["ok"] else 1
    plan = masterplan.load(world)
    if a.regenerate is not None or not plan:
        plan = masterplan.regenerate(world, a.regenerate or None)
    nxt = masterplan.suggestions(world, plan, a.next)
    if a.json:
        print(json.dumps({"plan": plan, "next": nxt}, indent=1, default=str))
        return 0
    print(masterplan.summary(plan))
    print(masterplan.next_text(nxt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
