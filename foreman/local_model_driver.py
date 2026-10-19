"""Phase 6 test driver: a local model (any OpenAI-compatible chat API with tool calling: Ollama, LM Studio, llama.cpp
server, vLLM) plays Timberborn through the harness, guided by Foreman briefings.

  runtime/python foreman/local_model_driver.py --base-url http://127.0.0.1:11434/v1 --model qwen3:14b
      dry run (default): the game is never changed or unpaused. Each game action the model asks for is only
      validated by Foreman and the verdict goes back to the model. Safe on any save.
  ... --live --test-save
      the model's actions run through the harness after Foreman finds no critical problem, and watch.py runs the
      game between turns. Use ONLY on a new game or a throwaway save: the driver never saves, but the game's own
      autosave will. Stops after cycle 2 (or --turns).

Each turn: briefing -> model (tool calls, up to --rounds) -> end_turn(thought). Food and water days are logged per
turn to foreman/data/localtest-<time>.jsonl; the run passes when both stay >= 3 through cycle 2 (plan section 11).
Docs: docs/foreman-local-model-test.md. The API key, if any, comes from OPENAI_API_KEY and is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
DATA = Path(__file__).resolve().parent / "data"
FOREMAN = os.environ.get("FOREMAN_URL", "http://127.0.0.1:8097")

SYSTEM = """You play Timberborn (Iron Teeth) through tools. A read-only advisor, Foreman, gives you a briefing each turn
with findings (each with a fix as an exact tool call) and NEXT steps from its masterplan, already validated.
Rules: water and food first (food days and water days never below 3); keep at least 3 Breeding Pods running from
day 5 and ~beavers/10 + 1 later, with free beds; every store gets a good set; every building's door on a Path joined
to the District Centre; powered buildings touch the power network; plant only moist, reachable tiles (use
safe_plant); reach a Forester early and never strip the only tree stand; unlock hazard-proofing (Stairs, Levee,
Discharge, Gear Workshop, Hydroponic Garden, Food Factory, Steam Engine) first with science.
Every game action is checked by Foreman before it runs; fix critical problems and try again. Prefer Foreman's
NEXT calls and finding fixes. Finish each turn with end_turn(thought) in one friendly sentence."""

I, S = {"type": "integer"}, {"type": "string"}


def fn(name, desc, props, req=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": req if req is not None else list(props)}}}


RECT = {"x0": I, "y0": I, "x1": I, "y1": I}
ACTIONS = {        # game actions: validated by Foreman first, executed only with --live
    "place_building": fn("place_building", "Place a building; (x, y) is the pivot corner, z the standing level.",
                         {"template": S, "x": I, "y": I, "z": I, "orientation": I}, ["template", "x", "y", "z"]),
    "place_line": fn("place_line", "Place a straight run (Path, Dam, Levee...).", {"template": S, **RECT, "z": I}),
    "place_area": fn("place_area", "Fill a rectangle (Platforms).", {"template": S, **RECT, "z": I}),
    "safe_plant": fn("safe_plant", "Mark crops or trees on moist, reachable tiles only. frm = planter doorstep [x,y,z].",
                     {"plant": S, **RECT, "frm": {"type": "array", "items": I}}),
    "mark_tree_cutting": fn("mark_tree_cutting", "Mark trees for lumberjacks.", RECT),
    "clear_planting": fn("clear_planting", "Remove planting marks.", RECT),
    "building_action": fn("building_action", "Panel action, e.g. SingleGoodAllower Allow [\"Water\"].",
                          {"building_id": S, "component": S, "action": S, "args": {"type": "array"}}),
    "set_priority": fn("set_priority", "VeryLow..VeryHigh.", {"building_id": S, "priority": S}),
    "set_workers": fn("set_workers", "Desired workers (min 1; pause instead of 0).", {"building_id": S, "workers": I}),
    "set_paused": fn("set_paused", "Pause or resume a building.", {"building_id": S, "paused": {"type": "boolean"}}),
    "unlock_building": fn("unlock_building", "Spend science.", {"template": S}),
    "demolish": fn("demolish", "Deconstruct a building.", {"building_id": S}),
}
READS = {
    "foreman_suggestions": fn("foreman_suggestions", "Next masterplan steps, validated now.", {"n": I}, []),
    "foreman_where": fn("foreman_where", "A clean spot near (x, y) plus the Path calls for its door.",
                        {"template": S, "x": I, "y": I, "radius": I, "good": S}, ["template"]),
    "foreman_plantable": fn("foreman_plantable", "Which tiles in a rectangle can grow a plant.", {**RECT, "plant": S},
                            ["x0", "y0", "x1", "y1"]),
    "foreman_findings": fn("foreman_findings", "All open findings with fixes.", {"severity": S}, []),
    "list_buildings": fn("list_buildings", "Buildings whose template contains the filter (ids, spots).",
                         {"filter": S}),
    "end_turn": fn("end_turn", "Finish this turn.", {"thought": S}),
}


def http(path, body=None, timeout=30):
    req = urllib.request.Request(FOREMAN + path, None if body is None else json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if r.headers.get("content-type", "").startswith("application/json") else raw


def chat(a, messages, tools):
    body = {"model": a.model, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0.2}
    head = {"Content-Type": "application/json"}
    if os.environ.get("OPENAI_API_KEY"):
        head["Authorization"] = "Bearer " + os.environ["OPENAI_API_KEY"]
    req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions", json.dumps(body).encode(), head)
    with urllib.request.urlopen(req, timeout=a.timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]


def metrics(brief: str) -> dict:
    m = {}
    t = re.search(r"FOREMAN c(\d+)d(\d+)", brief)
    if t:
        m["cycle"], m["day"] = int(t.group(1)), int(t.group(2))
    f = re.search(r"FOOD (\d+) = ([\d.]+) days", brief)
    if f:
        m["food"], m["food_days"] = int(f.group(1)), float(f.group(2))
    w = re.search(r"WATER (\d+)/\d+ \| use ([\d.]+)/day", brief)
    if w:
        m["water"] = int(w.group(1))
        m["water_days"] = round(int(w.group(1)) / max(0.1, float(w.group(2))), 1)
    p = re.search(r"POP (\d+)a\+(\d+)k", brief)
    if p:
        m["adults"], m["kits"] = int(p.group(1)), int(p.group(2))
    return m


class Game:
    """Executes the model's tool calls: reads always, game actions only with --live and no critical finding."""

    def __init__(self, live: bool):
        self.live = live
        sys.path.insert(0, str(HARNESS))
        import timberlive_mcp as t          # noqa: E402  (harness)
        import h                            # noqa: E402
        self.t, self.h = t, h

    def run(self, name: str, args: dict) -> str:
        if name == "foreman_suggestions":
            return http(f"/api/suggestions?n={int(args.get('n') or 3)}")["text"]
        if name == "foreman_where":
            q = "&".join(f"{k}={v}" for k, v in args.items() if v not in (None, ""))
            r = http(f"/api/where?{q}")
            return json.dumps({k: r.get(k) for k in ("found", "spot", "calls", "after", "text")})
        if name == "foreman_plantable":
            q = "&".join(f"{k}={v}" for k, v in args.items() if v not in (None, ""))
            return http(f"/api/plantable?{q}")["text"]
        if name == "foreman_findings":
            fs = [f for f in http("/api/findings")["open"] if not args.get("severity") or f["severity"] == args["severity"]]
            return "\n".join(f"[{f['severity']}] {f['message']}" + (f" | fix: {f['fix']}" if f.get("fix") else "")
                             for f in fs[:25]) or "none"
        if name == "list_buildings":
            rows = json.loads(self.t.list_buildings(args.get("filter", "")))
            rows = rows["buildings"] if isinstance(rows, dict) else rows
            return json.dumps([{k: b.get(k) for k in ("id", "template", "x", "y", "z", "finished", "pathTile")}
                               for b in rows[:40]])
        if name not in ACTIONS:
            return f"unknown tool {name}"
        v = http("/api/validate", {"actions": [{"call": name, **args}]})
        if v["critical"]:
            return "NOT RUN, Foreman found critical problems:\n" + v["text"]
        if not self.live:
            return "DRY RUN (not executed). Foreman: " + v["text"]
        if name == "safe_plant":
            out = self.h.safe_plant(args["plant"], args["x0"], args["y0"], args["x1"], args["y1"], tuple(args["frm"]))
            return f"planted; skipped {len(out)} tiles. Foreman: {v['text']}"
        return str(getattr(self.t, name)(**args))[:1500] + "\nForeman: " + v["text"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1"))
    ap.add_argument("--model", required=True)
    ap.add_argument("--turns", type=int, default=None, help="default 3 dry, 200 live")
    ap.add_argument("--rounds", type=int, default=12, help="tool-call rounds per turn")
    ap.add_argument("--chunk", type=int, default=110, help="watch.py seconds per turn (live)")
    ap.add_argument("--timeout", type=int, default=300, help="model request timeout (s)")
    ap.add_argument("--live", action="store_true", help="execute actions and run the game (test saves only)")
    ap.add_argument("--test-save", action="store_true", help="confirms --live runs on a new game or throwaway save")
    a = ap.parse_args()
    if a.live and not a.test_save:
        print("--live changes the game: add --test-save to confirm this is a new game or a throwaway save")
        return 2
    try:
        http("/api/status", timeout=3)
    except Exception:
        print("Foreman is not running: cd foreman && ../runtime/python -m foreman serve")
        return 2
    game = Game(a.live)
    tools = list(ACTIONS.values()) + list(READS.values())
    DATA.mkdir(exist_ok=True)
    log = DATA / f"localtest-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    notes: list[str] = []
    turns = a.turns or (200 if a.live else 3)
    low = {"food_days": None, "water_days": None}
    for turn in range(1, turns + 1):
        brief = http("/api/briefing")
        m = metrics(brief)
        for k in low:
            if k in m:
                low[k] = m[k] if low[k] is None else min(low[k], m[k])
        if a.live and m.get("cycle", 0) >= 3:
            break
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": ("Your last thoughts: " + " | ".join(notes[-5:]) + "\n\n" if notes else "")
                 + brief + ("\n\n(DRY RUN: actions are only validated.)" if not a.live else "")}]
        acted, thought = [], ""
        for _ in range(a.rounds):
            try:
                msg = chat(a, msgs, tools)
            except (urllib.error.URLError, OSError, KeyError) as e:
                print(f"model request failed: {type(e).__name__}: {e}")
                return 1
            calls = msg.get("tool_calls") or []
            msgs.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
            if not calls:
                thought = (msg.get("content") or "").strip()[:300]
                break
            done = False
            for c in calls:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                    if name == "end_turn":
                        thought, done, out = str(args.get("thought", ""))[:300], True, "ok"
                    else:
                        out = game.run(name, args)
                except Exception as e:          # bad arguments go back to the model as text
                    out = f"error: {type(e).__name__}: {e}"
                if name in ACTIONS:
                    acted.append({"call": name, "args": args if isinstance(args, dict) else {}, "result": out[:200]})
                msgs.append({"role": "tool", "tool_call_id": c.get("id", name), "content": out[:3000]})
            if done:
                break
        notes.append(thought)
        watch = ""
        if a.live:
            r = subprocess.run([sys.executable, str(HARNESS / "watch.py"), str(a.chunk), "3"], cwd=HARNESS,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            watch = "\n".join(l for l in r.stdout.splitlines() if l.startswith(("STOP", "TIME", "FOOD DAYS")))
        rec = {"turn": turn, **m, "actions": acted, "thought": thought, "watch": watch}
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"turn {turn}: c{m.get('cycle')}d{m.get('day')} food {m.get('food_days')} d, water "
              f"{m.get('water_days')} d, {len(acted)} action(s) | {thought[:120]}")
    ok = all(v is not None and v >= 3 for v in low.values())
    verdict = ("PASS" if ok else "FAIL") if a.live else "dry run, no verdict (the game did not move)"
    print(f"lowest food days {low['food_days']}, water days {low['water_days']}: {verdict} "
          f"(a live run passes when both stay >= 3 through cycle 2). Log: {log}")
    return 0 if ok or not a.live else 1


if __name__ == "__main__":
    sys.exit(main())
