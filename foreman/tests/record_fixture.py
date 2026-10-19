"""Record the live collector state (read-only) as an offline test fixture.

Usage: ../runtime/python tests/record_fixture.py <name>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from foreman import collector  # noqa: E402
from foreman.store import Store  # noqa: E402

name = sys.argv[1]
store = Store()
state = collector.collect(store, map_max_age=0)
state["alerts_all"] = store.alerts()
state.pop("collected_at", None)
out = Path(__file__).with_name("fixtures") / f"{name}.json"
out.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
print(out, out.stat().st_size // 1024, "KB")
