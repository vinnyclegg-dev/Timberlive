"""The game side: find Timberborn, install the TimberLive Bridge mod, check the bridge answers, launch the game.
None of this plays the game; it only gets it ready for the AI."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path

from . import paths

GAME_FOLDER = "Timberborn"
MOD_NAME = "TimberLive.Bridge"


def _steam_root() -> Path | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        default = Path(r"C:\Program Files (x86)\Steam")
        return default if default.exists() else None


def _libraries(steam: Path) -> list[Path]:
    libs = [steam]
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return libs
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        p = Path(m.group(1).replace("\\\\", "\\"))
        if p not in libs:
            libs.append(p)
    return libs


def find_game() -> dict:
    """{found, path, appid}: the Steam install of Timberborn, if any."""
    steam = _steam_root()
    if steam:
        for lib in _libraries(steam):
            apps = lib / "steamapps"
            for acf in apps.glob("appmanifest_*.acf"):
                try:
                    text = acf.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                m = re.search(r'"installdir"\s+"([^"]+)"', text)
                if m and m.group(1) == GAME_FOLDER:
                    appid = re.search(r'"appid"\s+"(\d+)"', text)
                    game = apps / "common" / GAME_FOLDER
                    if (game / "Timberborn.exe").exists():
                        return {"found": True, "path": str(game), "appid": appid.group(1) if appid else None}
    return {"found": False, "path": None, "appid": None}


def launch_game() -> dict:
    g = find_game()
    if not g["found"]:
        return {"ok": False, "message": "Timberborn isn't installed through Steam on this PC."}
    if g["appid"]:
        os.startfile(f"steam://rungameid/{g['appid']}")
    else:
        os.startfile(str(Path(g["path"]) / "Timberborn.exe"))
    return {"ok": True, "message": "Starting Timberborn..."}


def _digest(folder: Path) -> str | None:
    if not folder.exists():
        return None
    h = hashlib.sha256()
    for f in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(f.relative_to(folder).as_posix().encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def _version(folder: Path) -> str | None:
    try:
        return json.loads((folder / "manifest.json").read_text(encoding="utf-8-sig")).get("Version")
    except (OSError, ValueError):
        return None


def mod_status() -> dict:
    target = paths.mods_dir() / MOD_NAME
    bundled, installed = _digest(paths.MOD_SOURCE), _digest(target)
    return {
        "bundled": bundled is not None, "installed": installed is not None,
        "up_to_date": bundled is not None and bundled == installed,
        "bundled_version": _version(paths.MOD_SOURCE), "installed_version": _version(target),
        "target": str(target),
    }


def install_mod() -> dict:
    if not paths.MOD_SOURCE.exists():
        return {"ok": False, "message": "This copy of the app has no prebuilt mod (run packaging/build.py)."}
    target = paths.mods_dir() / MOD_NAME
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(paths.MOD_SOURCE, target, dirs_exist_ok=True)
    except PermissionError:
        return {"ok": False, "message": "The mod files are in use: close Timberborn, then install again."}
    except OSError as e:
        return {"ok": False, "message": f"Couldn't copy the mod: {e}"}
    return {"ok": True, "message": "Mod installed. In Timberborn's Mod manager, make sure TimberLive Bridge is ticked."}


def bridge_status() -> dict:
    """Ping the bridge with the per-launch token the mod writes (the token never leaves this function)."""
    try:
        conn = json.loads((paths.USER_DIR / "bridge.json").read_text(encoding="utf-8"))
        req = urllib.request.Request(f"http://127.0.0.1:{conn['port']}/api/ping",
                                     headers={"X-TimberLive-Token": conn["token"]})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            data = json.loads(r.read())
    except (OSError, ValueError, KeyError):
        return {"connected": False}
    out = {"connected": True}
    for k in ("game", "scene", "settlement", "speed", "version", "faction"):
        if isinstance(data, dict) and k in data:
            out[k] = data[k]
    return out
