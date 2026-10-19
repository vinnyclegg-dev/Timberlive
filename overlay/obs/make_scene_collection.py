"""Writes TimberLive.json, an OBS scene collection to import
(OBS: Scene Collection > Import).

Scene "TimberLive - Game": Timberborn game capture fitted into a 1440x810 box at
(24,24) (keeps aspect ratio, so any game resolution scales cleanly), with the
overlay browser source (1920x1080, transparent) on top.

Message slates ("Starting soon", "Be right back", ...) sit *below* the game in
the same frame, hidden by default. Hide the game and show a slate (eye icons,
or assign hotkeys in OBS settings) to put a message in the frame.
"""

import json
import uuid
from pathlib import Path

OUT = Path(__file__).with_name("TimberLive.json")

SLATES = [
    ("Slate: Starting soon", "soon&colony=off"),
    ("Slate: Be right back", "brb"),
    ("Slate: Game paused", "paused"),
    ("Slate: Technical difficulties", "tech"),
    ("Slate: Thanks for watching", "ending&colony=off"),
]


def item(name, source_uuid, item_id, pos=(0, 0), bounds=None, visible=True):
    entry = {
        "name": name, "source_uuid": source_uuid, "visible": visible, "locked": True, "rot": 0.0,
        "pos": {"x": float(pos[0]), "y": float(pos[1])}, "scale": {"x": 1.0, "y": 1.0},
        "align": 5, "bounds_type": 0, "bounds_align": 0, "bounds_crop": False,
        "bounds": {"x": 0.0, "y": 0.0},
        "crop_left": 0, "crop_top": 0, "crop_right": 0, "crop_bottom": 0,
        "id": item_id, "group_item_backup": False, "scale_filter": "bicubic",
        "blend_method": "default", "blend_type": "normal",
        "show_transition": {"duration": 0}, "hide_transition": {"duration": 0}, "private_settings": {},
    }
    if bounds:
        # Scale to inner bounds: fit inside the box, keep aspect ratio, centred.
        entry.update({"bounds_type": 2, "bounds_align": 0, "bounds": {"x": float(bounds[0]), "y": float(bounds[1])}})
    return entry


def source(source_id, name, settings, source_uuid):
    return {
        "prev_ver": 503447555, "name": name, "uuid": source_uuid, "id": source_id, "versioned_id": source_id,
        "settings": settings, "mixers": 255, "sync": 0, "flags": 0, "volume": 1.0, "balance": 0.5,
        "enabled": True, "muted": False, "push-to-mute": False, "push-to-mute-delay": 0,
        "push-to-talk": False, "push-to-talk-delay": 0, "hotkeys": {}, "deinterlace_mode": 0,
        "deinterlace_field_order": 0, "monitoring_type": 0, "private_settings": {},
    }


def main():
    game_uuid, overlay_uuid, scene_uuid = (str(uuid.uuid4()) for _ in range(3))
    game = source("game_capture", "Timberborn (game)", {
        "capture_mode": "window",
        "window": "Timberborn:UnityWndClass:Timberborn.exe",
        "priority": 2,
        "capture_cursor": True,
        "allow_transparency": False,
        "capture_audio": True,  # game sound only; no desktop audio, so notifications stay off stream
    }, game_uuid)
    overlay = source("browser_source", "TimberLive overlay", {
        "url": "http://127.0.0.1:8096/",
        "width": 1920, "height": 1080, "fps": 30,
        "shutdown": False, "restart_when_active": False, "reroute_audio": False,
        "css": "body { background-color: rgba(0, 0, 0, 0); margin: 0px auto; overflow: hidden; }",
    }, overlay_uuid)
    slate_sources = []
    slate_items = []
    for index, (name, query) in enumerate(SLATES, start=1):
        slate_uuid = str(uuid.uuid4())
        slate_sources.append(source("browser_source", name, {
            "url": f"http://127.0.0.1:8096/slate.html?msg={query}",
            "width": 1440, "height": 810, "fps": 30,
            # Reload when shown, so countdowns restart from the full time.
            "shutdown": True, "restart_when_active": True, "reroute_audio": False,
            "css": "body { margin: 0px auto; overflow: hidden; }",
        }, slate_uuid))
        slate_items.append(item(name, slate_uuid, 10 + index, pos=(24, 24), visible=False))
    # Items are listed bottom to top: slates, then the game, then the overlay.
    scene = source("scene", "TimberLive - Game", {
        "id_counter": 20, "custom_size": False,
        "items": slate_items + [
            item("Timberborn (game)", game_uuid, 1, pos=(24, 24), bounds=(1440, 810)),
            item("TimberLive overlay", overlay_uuid, 2),
        ],
    }, scene_uuid)
    collection = {
        "name": "TimberLive",
        "current_scene": "TimberLive - Game",
        "current_program_scene": "TimberLive - Game",
        "scene_order": [{"name": "TimberLive - Game"}],
        "sources": [scene, game, overlay] + slate_sources,
        "groups": [], "quick_transitions": [], "transitions": [], "saved_projectors": [],
        "current_transition": "Fade", "transition_duration": 300,
        "preview_locked": False, "scaling_enabled": False, "scaling_level": 0,
        "scaling_off_x": 0.0, "scaling_off_y": 0.0, "modules": {},
        "resolution": {"x": 1920, "y": 1080},
    }
    OUT.write_text(json.dumps(collection, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
