"""Streaming kit setup: OBS scene collection, OBS names, and the YouTube key for vote counts.

The YouTube key is write-only from the app's point of view: it is saved to %LOCALAPPDATA%\\TimberLive\\youtube.json
for the poll counter, and the app only ever reports whether one is set, never its value."""
from __future__ import annotations

import json
import os
import subprocess

from . import paths

YOUTUBE = paths.USER_DIR / "youtube.json"
OBS = paths.USER_DIR / "obs.json"
OBS_COLLECTION = paths.OVERLAY / "obs" / "TimberLive.json"
SLATES = {"Starting soon": "soon&colony=off", "Be right back": "brb", "Game paused": "paused",
          "Technical difficulties": "tech", "Thanks for watching": "ending&colony=off"}


def _load(path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _obs_installed() -> bool:
    return any(os.path.exists(os.path.join(os.environ.get(v, ""), "obs-studio", "bin", "64bit", "obs64.exe"))
               for v in ("ProgramFiles", "ProgramFiles(x86)"))


def status() -> dict:
    yt = _load(YOUTUBE)
    obs = _load(OBS)
    return {
        "overlay_url": "http://127.0.0.1:8096/",
        "slates": {k: f"http://127.0.0.1:8096/slate.html?msg={v}" for k, v in SLATES.items()},
        "obs_installed": _obs_installed(),
        "obs_collection_file": str(OBS_COLLECTION) if OBS_COLLECTION.exists() else None,
        "obs_collection": obs.get("collection") or "TimberLive", "obs_profile": obs.get("profile") or "Untitled",
        "youtube_key_set": bool(yt.get("api_key")),
        "youtube_channel_id": yt.get("channel_id", ""), "youtube_video_id": yt.get("video_id", ""),
    }


def make_obs_collection() -> dict:
    r = subprocess.run([str(paths.PYTHON), str(paths.OVERLAY / "obs" / "make_scene_collection.py")],
                       capture_output=True, text=True, timeout=60, creationflags=0x08000000)
    if r.returncode != 0 or not OBS_COLLECTION.exists():
        return {"ok": False, "message": "Couldn't write the scene collection: " + (r.stderr.strip()[-300:] or "?")}
    subprocess.Popen(["explorer", "/select,", str(OBS_COLLECTION)])
    return {"ok": True, "message": "Scene collection written. In OBS: Scene Collection > Import, pick TimberLive.json."}


def save_obs(collection: str, profile: str) -> dict:
    paths.USER_DIR.mkdir(parents=True, exist_ok=True)
    OBS.write_text(json.dumps({"collection": collection.strip() or "TimberLive",
                               "profile": profile.strip() or "Untitled"}, indent=2), encoding="utf-8")
    return {"ok": True, "message": "OBS names saved."}


def save_youtube(api_key: str, channel_id: str, video_id: str) -> dict:
    """Blank fields keep their saved value (so the key never has to be shown again to keep it)."""
    cfg = _load(YOUTUBE)
    if api_key.strip():
        cfg["api_key"] = api_key.strip()
    cfg["channel_id"] = channel_id.strip()
    cfg["video_id"] = video_id.strip()
    if not cfg.get("api_key"):
        return {"ok": False, "message": "Enter a YouTube Data API key."}
    if not (cfg["channel_id"] or cfg["video_id"]):
        return {"ok": False, "message": "Enter your channel id (or a live video id)."}
    paths.USER_DIR.mkdir(parents=True, exist_ok=True)
    YOUTUBE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return {"ok": True, "message": "YouTube settings saved."}


def open_obs() -> dict:
    for v in ("ProgramFiles", "ProgramFiles(x86)"):
        exe = os.path.join(os.environ.get(v, ""), "obs-studio", "bin", "64bit", "obs64.exe")
        if os.path.exists(exe):
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
            return {"ok": True, "message": "Starting OBS..."}
    return {"ok": False, "message": "OBS Studio isn't installed (https://obsproject.com)."}
