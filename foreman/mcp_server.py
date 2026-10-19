"""Foreman as MCP tools for any AI (plan section 8): a stdio JSON-RPC server, standard library only, that is a thin
client of the Foreman web service (python -m foreman serve, http://127.0.0.1:8097).

Read-only like the rest of Foreman: every tool reads the latest analysis or runs a pure computation (validate,
where, plantable, dam). Nothing here changes the game; the AI acts with the harness (the timberlive MCP tools).

  python foreman/mcp_server.py            (any Python 3.9+; FOREMAN_URL overrides the service address)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

URL = os.environ.get("FOREMAN_URL", "http://127.0.0.1:8097")
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
DOWN = ("Foreman is not running. Open the TimberLive app (it runs Foreman), or: cd foreman && ../runtime/python -m foreman serve "
        "(it only reads the game).")

S, I, A, O = {"type": "string"}, {"type": "integer"}, {"type": "array"}, {"type": "object"}
TOOLS = [
    ("foreman_briefing", "About 30 lines to play from: time, weather and hazard countdown, food/water days and "
     "reserves, population ledger, stock, needs, power, top findings with the exact harness call to fix each, open "
     "requests, and the NEXT validated masterplan steps. Call it after every watch chunk.",
     {"top": {**I, "description": "how many findings to list (default 8)"}}, []),
    ("foreman_findings", "Open findings (rule, severity, message, where, fix = exact harness call), most severe "
     "first. Filter by severity or a rule prefix such as 'water.' or 'bld.'.",
     {"severity": {**S, "enum": ["critical", "warn", "info"]}, "rule": {**S, "description": "rule id prefix"},
      "limit": I}, []),
    ("foreman_validate", "Pre-check harness calls BEFORE running them (footprint, support, door on a connected "
     "Path, build range, pump intake, power link, storage good, unlock, cost, safe planting, masterplan "
     "reservations). Give the whole batch in the order you will run it. Returns an id for foreman_verify.",
     {"actions": {**A, "items": {}, "description": "call strings like 'place_building(template=\"Path\", x=1, "
                                                   "y=2, z=5)' or {\"call\": ..., ...} objects"},
      "skip": {**A, "items": S, "description": "building ids to leave out (a planned demolish or move)"}},
     ["actions"]),
    ("foreman_verify", "After running a validated batch: was each placement made, is its door on the road, is it "
     "powered, is the storage good set?", {"id": {**S, "description": "id from foreman_validate"}}, ["id"]),
    ("foreman_masterplan", "The settlement masterplan: zones (core, farms, forest, berries, industry, reservoirs, "
     "decks), reserved tiles and the staged build order. Generated on first call.", {}, []),
    ("foreman_suggestions", "The next n masterplan steps, each validated against the live map now, as exact "
     "harness calls to run in order (plus the calls to run after placing: storage good, priority, pause).",
     {"n": {**I, "description": "1-8 (default 3)"}}, []),
    ("foreman_where", "A clean spot for a building near (x, y) (default: the District Centre), plus the Path "
     "calls that join its door, validated together.",
     {"template": {**S, "description": "e.g. SmallWarehouse or SmallWarehouse.IronTeeth"}, "x": I, "y": I,
      "radius": {**I, "description": "default 10, max 30"}, "good": {**S, "description": "storage good"}},
     ["template"]),
    ("foreman_plantable", "Which tiles in a rectangle a crop or tree can go on (moist, clean soil, reachable, not "
     "water, not a ledge, free) and the h.safe_plant call for it.",
     {"x0": I, "y0": I, "x1": I, "y1": I, "plant": {**S, "description": "default Kohlrabi"},
      "fx": {**I, "description": "planter doorstep x"}, "fy": I, "fz": I}, ["x0", "y0", "x1", "y1"]),
    ("foreman_dam", "Test your own straight dam/levee line: per structure height, the pool it holds, volume, "
     "what it floods, whether it leaks round the ends, and the place_line calls.",
     {"x0": I, "y0": I, "x1": I, "y1": I}, ["x0", "y0", "x1", "y1"]),
    ("foreman_water", "Water engineering summary: best dam proposals, badwater diversions, reservoirs, irrigation "
     "ponds, platform decks over water, pump and wheel sites, each with why and harness calls.",
     {"limit": {**I, "description": "items per section (default 4)"}}, []),
    ("foreman_supply", "Stock, capacity and daily rate per tracked good, and the hazard reserve targets.", {}, []),
    ("foreman_events", "Wait (long-poll, up to timeout seconds) for the next analysis pass and return the "
     "findings that opened or cleared since `since`. Use the returned seq as the next since.",
     {"since": I, "timeout": {**I, "description": "seconds, default 25, max 60"}}, []),
]


class Down(Exception):
    pass


def http(path: str, body=None, timeout: float = 30.0):
    req = urllib.request.Request(URL + path, None if body is None else json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if r.headers.get("content-type", "").startswith("application/json") else raw
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from None
    except (urllib.error.URLError, OSError):
        raise Down(DOWN) from None


def q(**kw) -> str:
    kw = {k: v for k, v in kw.items() if v is not None and v != ""}
    return "?" + urllib.parse.urlencode(kw) if kw else ""


def short(obj, n: int = 6000) -> str:
    text = obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"))
    return text if len(text) <= n else text[:n] + f" ... ({len(text) - n} more characters)"


def run(name: str, a: dict) -> str:
    if name == "foreman_briefing":
        return http("/api/briefing" + q(top=a.get("top")))
    if name == "foreman_findings":
        fs = http("/api/findings")["open"]
        fs = [f for f in fs if (not a.get("severity") or f["severity"] == a["severity"])
              and f["rule"].startswith(a.get("rule") or "")]
        lines = [f"[{f['severity'].upper()}] {f['rule']}: {f['message']}" + (f"\n    fix: {f['fix']}" if f.get("fix")
                                                                            else "") for f in fs[:a.get("limit") or 20]]
        return f"{len(fs)} open finding(s)\n" + "\n".join(lines)
    if name == "foreman_validate":
        r = http("/api/validate", {"actions": a.get("actions") or [], "skip": a.get("skip") or []})
        return f"{r['text']}\nid {r['id']} (foreman_verify after running the batch)"
    if name == "foreman_verify":
        r = http(f"/api/verify/{urllib.parse.quote(str(a['id']))}")
        rows = [f"  {row['state']}: {row['call']}" + "".join(f"\n    [{c['severity']}] {c['message']}"
                                                           for c in row.get("checks") or []) for row in r["rows"]]
        return f"verify {r['id']}: {'OK' if r['ok'] else 'PROBLEMS'}\n" + "\n".join(rows)
    if name == "foreman_masterplan":
        return http("/api/masterplan")["text"]
    if name == "foreman_suggestions":
        return http("/api/suggestions" + q(n=a.get("n") or 3))["text"]
    if name == "foreman_where":
        r = http("/api/where" + q(template=a["template"], x=a.get("x"), y=a.get("y"), radius=a.get("radius"),
                                  good=a.get("good")))
        if not r.get("found"):
            return r["text"]
        return "\n".join([f"spot {r['spot']['template']} ({r['spot']['x']},{r['spot']['y']},z{r['spot']['z']}) "
                          f"o{r['spot']['o']} door {r['spot']['door']}", "run in order:", *r["calls"],
                          *(["then:", *r["after"]] if r["after"] else []), r["text"]])
    if name == "foreman_plantable":
        return http("/api/plantable" + q(**{k: a.get(k) for k in ("x0", "y0", "x1", "y1", "plant", "fx", "fy", "fz")}))["text"]
    if name == "foreman_dam":
        r = http("/api/dam" + q(**{k: a[k] for k in ("x0", "y0", "x1", "y1")}))
        if r.get("error"):
            return r["error"]
        out = [f"line {r['line'][0]}-{r['line'][-1]} along {r['axis']}"]
        for o in r["options"]:
            out.append(f"- {'OK  ' if o['ok'] else 'NO  '}{o['why']}" + (f" | leaks: {'; '.join(o['leaks'])}" if o["leaks"] else "")
                       + (f" | floods {', '.join(o['flooded'][:5])}" if o.get("flooded") else ""))
            out += [f"    {c}" for c in o["calls"]]
        return "\n".join(out)
    if name == "foreman_water":
        w, n = http("/api/water"), a.get("limit") or 4
        out = [f"held behind dams now: {w['heldVolume']} units"]
        for title, items in (("DAMS", w["dams"]["proposals"]), ("BADWATER", w["badwater"]["diversions"]),
                             ("RESERVOIRS", w["reservoirs"]), ("PONDS", w["ponds"]), ("DECKS", w["decks"])):
            out.append(f"{title} ({len(items)})")
            for p in items[:n]:
                out.append(f"  - {p.get('why') or p}")
                out += [f"      {c}" for c in (p.get("calls") or [])[:6]]
        out.append("PUMP SITES " + "; ".join(f"bank {s['bank']} depth {s['depth']}" for s in w["pumps"]["sites"][:n]))
        out.append("WHEEL SITES " + "; ".join(f"({s['x']},{s['y']},z{s['z']}) flow {s['speed']}" for s in w["wheels"][:n]))
        out += [f"[{f['severity'].upper()}] {f['message']}" for f in w["findings"]]
        return "\n".join(out)
    if name == "foreman_supply":
        s = http("/api/supply")
        rows = [f"{g['id']}: {g.get('available', 0)}/{g.get('capacity', 0)}" +
                (f" ({s['rates'][g['id']]:+.0f}/day)" if isinstance(s["rates"].get(g["id"]), (int, float)) else "")
                for g in s["goods"] if g.get("available") or g.get("capacity")]
        return "STOCK " + ", ".join(rows) + "\nRESERVE " + short(s["reserve"], 1500)
    if name == "foreman_events":
        r = http("/api/events" + q(since=a.get("since") or 0, timeout=a.get("timeout")), timeout=70)
        lines = [f"seq {r['seq']}"]
        for e in r["events"]:
            lines.append(f"  {e['kind']}" + (f" [{e['severity']}] {e['rule']}: {e['message']}" if e["kind"] == "opened" else
                                             f" {e['rule']}: {e['message']}" if e["kind"] == "cleared" else
                                             f" {e['day']}: {e['critical']} critical, {e['warn']} warn"))
            if e.get("fix"):
                lines.append(f"      fix: {e['fix']}")
        return "\n".join(lines)
    raise KeyError(name)


def handle(msg: dict) -> dict | None:
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:                       # notifications (initialized, cancelled) need no answer
        return None
    if method == "initialize":
        want = params.get("protocolVersion")
        res = {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0], "capabilities": {"tools": {}},
               "serverInfo": {"name": "foreman", "version": "0.6"},
               "instructions": "Read-only advisor for Timberborn. Call foreman_briefing after each watch chunk, "
                               "foreman_validate before every placement batch, foreman_verify after it. Act with "
                               "the timberlive tools; Foreman never changes the game."}
    elif method == "ping":
        res = {}
    elif method == "tools/list":
        res = {"tools": [{"name": n, "description": d,
                          "inputSchema": {"type": "object", "properties": p, "required": r}} for n, d, p, r in TOOLS]}
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in {t[0] for t in TOOLS}:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
        try:
            res = {"content": [{"type": "text", "text": short(run(name, args), 12000)}], "isError": False}
        except Down as e:
            res = {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except Exception as e:            # a bad argument or a Foreman error goes back to the AI as text
            res = {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            out = handle(msg)
        if out is not None:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
