"""Write a compact stream checkpoint to .claude/stream-state.md.

Usage: python checkpoint.py "free-text notes: decisions, layout facts, what's next"

The file is re-injected into context after every compaction by the project's
SessionStart(compact) hook, so it must stay short (~60 lines) and current.
Run it once per in-game day and before any planned break or /compact.
"""

import json
import sys
import time
from pathlib import Path

import timberlive_mcp as t

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / ".claude" / "stream-state.md"
OVERLAY_STATE = ROOT / "overlay" / "state.json"
NOTES_FILE = ROOT / ".claude" / "stream-notes.md"


def safe(call, default):
    try:
        return call()
    except Exception as e:  # game loading or closed
        return default if default is not None else f"unavailable ({type(e).__name__})"


def main():
    notes = " ".join(sys.argv[1:]).strip()
    if notes:
        # Rolling notes log: newest last, capped so the checkpoint stays small.
        lines = NOTES_FILE.read_text(encoding="utf-8").splitlines() if NOTES_FILE.exists() else []
        lines.append(f"- [{time.strftime('%H:%M')}] {notes}")
        NOTES_FILE.write_text("\n".join(lines[-15:]) + "\n", encoding="utf-8")

    colony = safe(lambda: json.loads(t.get_colony()), {})
    goods = safe(lambda: {g["id"]: g["available"] for g in json.loads(t.get_goods())}, {})
    needs = safe(lambda: json.loads(t.get_needs())["needs"], [])
    buildings = safe(lambda: json.loads(t.list_buildings()), [])
    blueprints = safe(lambda: json.loads(t.list_blueprints()), [])
    overlay = json.loads(OVERLAY_STATE.read_text(encoding="utf-8")) if OVERLAY_STATE.exists() else {}

    counts = {}
    for b in buildings:
        if b["template"] != "Path":
            key = b["template"].split(".")[0] + ("" if b["finished"] else "*")
            counts[key] = counts.get(key, 0) + 1
    built_types = {b["template"] for b in buildings if b["finished"]}
    countable = [bp for bp in blueprints if bp["group"] not in ("Decoration", "Paths")]
    built = sum(1 for bp in countable if bp["template"] in built_types)

    out = [f"# Stream checkpoint - {time.strftime('%Y-%m-%d %H:%M')}", ""]
    if colony:
        p = colony["population"]
        out += [
            f"**Game:** cycle {colony['time']['cycle']} day {colony['time']['cycleDay']}, "
            f"speed {colony['time']['speed']}, weather {colony['weather']}",
            f"**Pop:** {p['adults']} adults + {p['children']} kits, homeless {p['homeless']}, "
            f"unemployed {p['unemployed']}, free jobs {p['freeWorkslots']}, science {colony['science']}, "
            f"wellbeing {colony['wellbeing']}",
        ]
    else:
        out.append("**Game:** not reachable when this was written")
    out += [
        f"**Goods:** {goods}",
        f"**Needs (avg, critical):** " + ", ".join(f"{n['need']} {n['average']}/{n['critical']}" for n in needs),
        f"**Buildings** (* = under construction): {counts}",
        f"**Every-building goal:** {built}/{len(countable)}",
        "",
        "**On-stream plan:** " + "; ".join(("[x] " if x.get("done") else "[ ] ") + x["text"]
                                          for x in overlay.get("todos", [])),
        "**Last thoughts shown:** " + " | ".join(x["text"] for x in overlay.get("thoughts", [])[-3:]),
        "",
        "## Notes (newest last)",
        NOTES_FILE.read_text(encoding="utf-8").strip() if NOTES_FILE.exists() else "(none)",
    ]
    STATE_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"checkpoint written ({len(out)} lines)")


if __name__ == "__main__":
    main()
