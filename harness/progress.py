"""Building-collection progress: which placeable buildings exist in the colony yet.

Usage: python progress.py [--markdown]
Excludes decorations, paths and landscaping odds and ends, which don't count as "buildings".
"""

import json
import sys

import timberlive_mcp as t

SKIP_GROUPS = {"Decoration", "Paths"}


def main():
    blueprints = json.loads(t.list_blueprints())
    built = {}
    for b in json.loads(t.list_buildings()):
        built.setdefault(b["template"], [0, 0])[0 if b["finished"] else 1] += 1
    rows = []
    for bp in blueprints:
        if bp["group"] in SKIP_GROUPS:
            continue
        finished, sites = built.get(bp["template"], [0, 0])
        rows.append((bp["group"], bp["name"] or bp["template"], bp["template"], finished, sites,
                     bp["unlocked"], bp["science"]))
    done = sum(1 for r in rows if r[3] > 0)
    if "--markdown" in sys.argv:
        print(f"Buildings built: {done}/{len(rows)}\n")
        print("| Group | Building | Built | Unlocked | Science |")
        print("|---|---|---|---|---|")
        for group, name, _, finished, sites, unlocked, science in rows:
            mark = f"✅ {finished}" if finished else ("🚧" if sites else "—")
            print(f"| {group} | {name} | {mark} | {'yes' if unlocked else 'no'} | {science} |")
    else:
        print(f"BUILT {done}/{len(rows)}")
        missing = [(r[0], r[2], r[5], r[6]) for r in rows if r[3] == 0]
        print("NEXT UNLOCKED, NOT BUILT:", [m[1] for m in missing if m[2]])
        print("LOCKED (cheapest first):", sorted([(m[3], m[1]) for m in missing if not m[2]])[:12])


if __name__ == "__main__":
    main()
