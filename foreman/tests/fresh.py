"""A fresh-start state built from the S2E1 end fixture: same terrain and water, only the District Centre,
no fields or marks, start goods (0 logs, 0 water, 130 berries: knowledge/08) and day-0 science."""

import copy
import json
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "s2e1-end.json"
CROPS = {"Kohlrabi", "Corn", "Canola", "Cassava", "Soybean", "Potato", "Wheat", "Carrot", "Sunflower", "Eggplant"}
START = {"Berries": 130, "Log": 0, "Water": 0}


def fresh_state(src: dict | None = None) -> dict:
    s = copy.deepcopy(src) if src else json.loads(FIXTURE.read_text(encoding="utf-8"))
    s["buildings"] = [b for b in s["buildings"] if b.get("name") == "DistrictCenter"
                      or str(b.get("template", "")).startswith("DistrictCenter")]
    m = s["map"]
    drop = {ch for ch, name in m["legend"].items() if "." in name or name in CROPS}
    m["objects"] = ["".join(" " if c in drop else c for c in row) for row in m["objects"]]
    for k in ("range", "power", "sites", "production", "stock", "beavers", "batches"):
        s[k] = [] if isinstance(s.get(k), list) else {}
    s["marks"], s["reach"] = {}, {}
    for g in s["goods"]:
        n = START.get(g["id"], 0)
        g.update(available=n, total=n, capacity=max(n, 0), fillRate=0.0)
    s["colony"]["science"] = 0
    s["colony"]["time"] = {**s["colony"].get("time", {}), "cycle": 1, "cycleDay": 1}
    s["game_day"] = 1.0
    for bp in s["blueprints"]:
        bp["unlocked"] = not bp.get("science")
    s["alerts_all"], s["pending"], s["new_alerts"] = [], [], []
    return s
