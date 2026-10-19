"""Reset the stream overlay texts: empty "What I'm thinking", empty "The plan", no poll,
no ticker announcements or pending welcome.

    ../runtime/python overlay_reset.py
"""
from timberlive_mcp import OVERLAY_STATE, POLL_COUNTS, _overlay_save

_overlay_save({"thoughts": [], "todos": []})
POLL_COUNTS.unlink(missing_ok=True)
(OVERLAY_STATE.parent / "welcome.json").unlink(missing_ok=True)
print("overlay reset: thoughts, plan, poll and ticker cleared")
