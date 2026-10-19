"""Retry pending path tiles (blocked by crops/trees being cleared). Edit TILES as needed."""
import json
import timberlive_mcp as t
import h

TILES = [(89, 45, 5), (90, 45, 5)]
left = [p for p in TILES if not h.is_path(p[0], p[1]) and not json.loads(t.place_building("Path", *p)).get("ok")]
print("still blocked:", left)
