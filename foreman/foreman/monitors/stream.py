"""Stream and AI discipline, no LLM (plan section 4.7): thought age, plan, poll, user requests, checkpoint."""

from __future__ import annotations

import re
import time

from ..findings import Finding, monitor

THOUGHT_MAX_AGE = 120   # CLAUDE.md: narrate at least every 2 real minutes (the watchdog pings at 100 s)


def live(world) -> bool:
    """Only nag about stream discipline while the game runs (speed > 0): a paused prep session has no stream."""
    return (world.colony["time"].get("speed") or 0) > 0


@monitor("stream.thought_age", rules=["narrate-every-2-min"])
def thought_age(world, ctx):
    """Last overlay thought older than 2 real minutes while the game runs."""
    if not live(world):
        return
    thoughts = (world.state.get("overlay") or {}).get("thoughts") or []
    last = max((t.get("at") or 0 for t in thoughts), default=0)
    age = time.time() - last if last else None
    if age is None or age > THOUGHT_MAX_AGE:
        yield Finding("stream.thought_age", "warn", "no overlay thought yet" if age is None else
                      f"last thought {int(age)} s ago: narrate what is happening now", "thought",
                      fix='narrate(thought="<1-2 friendly sentences about the current state>")')


@monitor("stream.plan", rules=["plan-max-8", "plan-fresh"])
def plan(world, ctx):
    """On-stream plan: empty, more than 8 items, or every item done."""
    if not live(world):
        return
    todos = (world.state.get("overlay") or {}).get("todos") or []
    if not todos:
        yield Finding("stream.plan", "warn", "the on-stream plan is empty", "plan", fix='set_plan(items=[...])')
    elif len(todos) > 8:
        yield Finding("stream.plan", "info", f"plan has {len(todos)} items (max 8)", "plan")
    elif all(t.get("done") for t in todos):
        yield Finding("stream.plan", "warn", "every plan item is done: set the next plan", "plan")


@monitor("stream.poll", rules=["poll-counter-running", "poll-close-and-act"])
def poll(world, ctx):
    """Open poll whose counter isn't counting, or a poll past its close time that is not closed."""
    p = (world.state.get("overlay") or {}).get("poll")
    if not p:
        return
    counts = world.state.get("poll_counts") or {}
    now = time.time()
    is_open = not p.get("closed") and now < p.get("closes", 0)
    status = counts.get("status") if counts.get("id") == p.get("id") else "not_running"
    if is_open and status != "counting":
        yield Finding("stream.poll", "warn", f"poll open but the counter is '{status}': votes are not counted",
                      "poll", fix="cd harness && ../runtime/python pollguard.py")
    elif not p.get("closed") and now >= p.get("closes", 0):
        yield Finding("stream.poll", "warn", "poll time is up: read the result, narrate it, close it, act on it",
                      "poll", fix="poll_results(); close_poll()")


@monitor("stream.requests", rules=["user-requests-ledger"])
def requests(world, ctx):
    """Open user requests from harness/pending.txt (none get dropped)."""
    seen = ctx.store.get("requests_seen", {})
    now = world.game_day()
    current = {}
    for i, req in enumerate(world.state.get("pending") or []):
        current[req] = seen.get(req, now)
        age = now - current[req]
        yield Finding("stream.requests", "info", req, f"req-{i}", evidence={"open_days": round(age, 1)})
    ctx.store.set("requests_seen", current)


@monitor("stream.checkpoint", rules=["checkpoint-daily"])
def checkpoint(world, ctx):
    """No checkpoint for over a game day (reads the timestamp checkpoint.py writes)."""
    from pathlib import Path
    path = Path(__file__).resolve().parents[3] / ".claude" / "stream-state.md"
    if not live(world) or not path.exists():
        return
    age_h = (time.time() - path.stat().st_mtime) / 3600
    # ~1 game day is about 6-8 real minutes at speed 3; flag after 15 real minutes.
    if age_h > 0.25:
        yield Finding("stream.checkpoint", "info", f"last checkpoint {int(age_h * 60)} min ago",
                      "checkpoint", fix='cd harness && ../runtime/python checkpoint.py "<what changed, next>"')


@monitor("stream.plan_stale", rules=["plan-fresh", "narrate-matches-state"])
def plan_stale(world, ctx):
    """Plan items naming a building that has been finished since the item first appeared."""
    todos = [t for t in (world.state.get("overlay") or {}).get("todos") or [] if not t.get("done")]
    if not todos or not world.blueprints:
        return
    from .progress import key
    bps = [bp for bp in world.blueprints if bp["group"] != "Paths"]    # paths, stairs, platforms: built all the time
    # Buildings are matched by template base ("OilPress"); plan text uses the display name ("Oil Press").
    words = {key(bp): bp["name"].lower() for bp in bps}
    names = set(words)
    counts = {n: 0 for n in names}
    for b in world.finished():
        if b.name in counts:
            counts[b.name] += 1
    seen = ctx.store.get("plan_seen", {})
    now_seen = {}
    for t in todos:
        text = t.get("text", "")
        low = text.lower()
        named = [n for n in names if re.search(rf"\b({re.escape(words[n])}|{n.lower()})s?\b", low)]
        first = seen.get(text) or {n: counts[n] for n in named}
        now_seen[text] = first
        done = [n for n in named if counts[n] > first.get(n, 0)]
        if done:
            yield Finding("stream.plan_stale", "warn", f"plan item '{text[:70]}' may be done: {done} finished since "
                          "it was posted", text[:40], fix=f'check_todo(item="{text[:30]}")  # or set_plan with the next step')
    ctx.store.set("plan_seen", now_seen)


@monitor("stream.health", rules=["session-start-checks", "poll-counter-running"])
def stream_health(world, ctx):
    """Overlay server and OBS while the game runs (collector checks them every medium poll)."""
    h = world.health
    if not h or not live(world):
        return
    if not h.get("overlay"):
        yield Finding("stream.health", "warn", "overlay server :8096 is not answering: viewers see no thoughts",
                      "overlay", fix="overlay/start-overlay.cmd")
    if h.get("obs") is False:
        yield Finding("stream.health", "info", "OBS is not running", "obs",
                      fix="cd harness && ../runtime/python obs.py status")
