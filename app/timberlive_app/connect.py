"""Connect the user's AI to the tools the app ships. The app never calls these tools itself: it only writes the
config that lets Claude Code, Claude Desktop or any other MCP client start them.

Two MCP servers, both on the app's private Python:
  timberlive  harness/timberlive_mcp.py  every game action and observation (through the bridge mod)
  foreman     foreman/mcp_server.py      the read-only advisor (needs the app open: it serves Foreman)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import paths

SERVERS = ("timberlive", "foreman")


def servers() -> dict:
    py = str(paths.PYTHON)
    return {
        "timberlive": {"command": py, "args": [str(paths.HARNESS / "timberlive_mcp.py")]},
        "foreman": {"command": py, "args": [str(paths.FOREMAN / "mcp_server.py")]},
    }


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _write(path: Path, data: dict, backup: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        shutil.copy2(path, path.with_name(path.name + f".{time.strftime('%Y%m%d-%H%M%S')}.bak"))
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _has(cfg: dict) -> bool:
    want = servers()
    have = cfg.get("mcpServers", {})
    return all(have.get(k, {}).get("command") == want[k]["command"] and have.get(k, {}).get("args") == want[k]["args"]
               for k in SERVERS)


# --- Claude Code: the app folder is the AI's workspace (AGENTS.md, CLAUDE.md, knowledge/, harness/) ---------------

MCP_JSON = paths.ROOT / ".mcp.json"
CLAUDE_SETTINGS = paths.ROOT / ".claude" / "settings.json"


def _hook() -> dict:
    return {"matcher": "compact", "hooks": [{
        "type": "command", "command": "powershell",
        "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 str(paths.ROOT / ".claude" / "hooks" / "post-compact.ps1")],
        "timeout": 15}]}


def claude_code_status() -> dict:
    return {"configured": _has(_read(MCP_JSON)), "workspace": str(paths.ROOT),
            "cli": shutil.which("claude") is not None, "vscode": shutil.which("code") is not None}


def connect_claude_code() -> dict:
    cfg = _read(MCP_JSON)
    cfg.setdefault("mcpServers", {}).update({k: {"type": "stdio", **v} for k, v in servers().items()})
    _write(MCP_JSON, cfg, backup=False)
    # Re-inject the latest checkpoint after a context compaction (keeps long games on track).
    settings = _read(CLAUDE_SETTINGS)
    starts = settings.setdefault("hooks", {}).setdefault("SessionStart", [])
    starts[:] = [h for h in starts if h.get("matcher") != "compact"] + [_hook()]
    _write(CLAUDE_SETTINGS, settings, backup=False)
    return {"ok": True, "message": f"Claude Code is set up in {paths.ROOT}. Open that folder in Claude Code "
                                   "and approve the two project MCP servers when asked."}


def open_claude_code() -> dict:
    if not shutil.which("claude"):
        return {"ok": False, "message": "Claude Code isn't on PATH. Install it (https://claude.com/claude-code), "
                                        "or open the workspace folder in VS Code with the Claude Code extension."}
    subprocess.Popen(["cmd", "/c", "start", "TimberLive - Claude Code", "cmd", "/k", "claude"], cwd=paths.ROOT)
    return {"ok": True, "message": "Opened Claude Code in the TimberLive workspace."}


def open_vscode() -> dict:
    code = shutil.which("code")
    if not code:
        return {"ok": False, "message": "VS Code isn't on PATH."}
    subprocess.Popen([code, str(paths.ROOT)], creationflags=0x08000000)
    return {"ok": True, "message": "Opened the workspace in VS Code."}


# --- Claude Desktop (MCP tools only: it can't run the harness scripts, so it plays with the tools alone) ----------

def _desktop_config() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "Claude" / "claude_desktop_config.json"


def claude_desktop_status() -> dict:
    path = _desktop_config()
    return {"installed": path.parent.exists(), "configured": _has(_read(path)), "config": str(path)}


def connect_claude_desktop() -> dict:
    path = _desktop_config()
    try:
        cfg = _read(path)
    except ValueError:
        return {"ok": False, "message": f"{path} isn't valid JSON; fix or delete it first."}
    cfg.setdefault("mcpServers", {}).update(servers())
    _write(path, cfg, backup=True)
    return {"ok": True, "message": "Added to Claude Desktop (old config backed up). Restart Claude Desktop."}


# --- Anything else that speaks MCP ------------------------------------------------------------------------------

def snippet() -> str:
    return json.dumps({"mcpServers": servers()}, indent=2)
