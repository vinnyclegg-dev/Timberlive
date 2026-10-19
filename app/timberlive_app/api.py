"""The window's JavaScript API (window.pywebview.api.*). Every method returns plain JSON.

Nothing here plays the game: setup, status, service control and connecting an AI. The AI plays through the
MCP tools and harness scripts the app ships."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import __version__, connect, game, paths, stream
from .services import Services

NEW_CONSOLE = 0x00000010


class Api:
    def __init__(self, services: Services) -> None:
        self._services = services

    # --- overview -------------------------------------------------------------------------------------------
    def overview(self) -> dict:
        return {
            "version": __version__, "root": str(paths.ROOT), "python": str(paths.PYTHON),
            "game": game.find_game(), "mod": game.mod_status(), "bridge": game.bridge_status(),
            "services": self._services.status(),
            "claude_code": connect.claude_code_status(), "claude_desktop": connect.claude_desktop_status(),
            "stream": stream.status(),
        }

    def services(self) -> list:
        return self._services.status()

    def bridge(self) -> dict:
        return game.bridge_status()

    # --- game -----------------------------------------------------------------------------------------------
    def install_mod(self) -> dict:
        return game.install_mod()

    def launch_game(self) -> dict:
        return game.launch_game()

    # --- services -------------------------------------------------------------------------------------------
    def start_service(self, key: str) -> dict:
        if key == "polls" and not stream.status()["youtube_key_set"]:
            return {"state": "stopped", "error": "Add your YouTube settings first (Stream page)."}
        return self._services.start(key)

    def stop_service(self, key: str) -> dict:
        return self._services.stop(key)

    def service_log(self, key: str, lines: int = 60) -> str:
        log = paths.LOGS / f"{key}.log"
        try:
            return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
        except FileNotFoundError:
            return "(no log yet)"

    # --- connect an AI --------------------------------------------------------------------------------------
    def connect_claude_code(self) -> dict:
        return connect.connect_claude_code()

    def connect_claude_desktop(self) -> dict:
        return connect.connect_claude_desktop()

    def open_claude_code(self) -> dict:
        return connect.open_claude_code()

    def open_vscode(self) -> dict:
        return connect.open_vscode()

    def mcp_snippet(self) -> str:
        return connect.snippet()

    # --- stream ---------------------------------------------------------------------------------------------
    def stream_status(self) -> dict:
        return stream.status()

    def make_obs_collection(self) -> dict:
        return stream.make_obs_collection()

    def save_obs(self, collection: str, profile: str) -> dict:
        return stream.save_obs(collection, profile)

    def save_youtube(self, api_key: str, channel_id: str, video_id: str) -> dict:
        return stream.save_youtube(api_key, channel_id, video_id)

    def open_obs(self) -> dict:
        return stream.open_obs()

    # --- experimental: a local model plays through the same tools --------------------------------------------
    def run_local_model(self, base_url: str, model: str, live: bool) -> dict:
        if not model.strip():
            return {"ok": False, "message": "Enter a model name (e.g. qwen3:14b)."}
        args = [str(paths.PYTHON), str(paths.FOREMAN / "local_model_driver.py"),
                "--base-url", base_url.strip() or "http://127.0.0.1:11434/v1", "--model", model.strip()]
        if live:
            args += ["--live", "--test-save"]
        subprocess.Popen(args, cwd=paths.ROOT, creationflags=NEW_CONSOLE)
        return {"ok": True, "message": ("Live run started in a console window (test saves only)." if live
                                        else "Dry run started in a console window.")}

    # --- files ----------------------------------------------------------------------------------------------
    def open_path(self, what: str) -> dict:
        target = {
            "workspace": paths.ROOT, "agents": paths.ROOT / "AGENTS.md", "readme": paths.ROOT / "README.md",
            "knowledge": paths.ROOT / "knowledge", "logs": paths.LOGS, "mods": paths.mods_dir(),
            "userdata": paths.USER_DIR,
        }.get(what)
        if target is None:
            return {"ok": False, "message": f"unknown: {what}"}
        if not Path(target).exists():
            Path(target).mkdir(parents=True, exist_ok=True) if what in ("logs", "userdata") else None
        if not Path(target).exists():
            return {"ok": False, "message": f"{target} doesn't exist yet."}
        os.startfile(str(target))
        return {"ok": True, "message": f"Opened {target}"}

    def open_url(self, url: str) -> dict:
        if url.startswith(("https://", "http://127.0.0.1")):
            os.startfile(url)
            return {"ok": True}
        return {"ok": False}
