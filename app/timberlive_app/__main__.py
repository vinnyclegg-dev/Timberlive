"""TimberLive app.

    runtime/pythonw -m timberlive_app                 the window (starts Foreman and the overlay while open)
    runtime/python  -m timberlive_app status          what's installed, connected and running (text)
    runtime/python  -m timberlive_app install-mod     copy the bundled bridge mod into Timberborn's Mods folder
    runtime/python  -m timberlive_app connect claude-code|claude-desktop|show
    runtime/python  -m timberlive_app services        run Foreman + overlay without the window (Ctrl+C stops)
"""
from __future__ import annotations

import argparse
import json
import sys
import time


def _cli(argv: list[str]) -> int:
    from . import connect, game
    from .api import Api
    from .services import Services

    ap = argparse.ArgumentParser(prog="timberlive_app", description="TimberLive app (no arguments: open the window)")
    ap.add_argument("command", choices=["window", "status", "install-mod", "connect", "services"])
    ap.add_argument("target", nargs="?", choices=["claude-code", "claude-desktop", "show"])
    a = ap.parse_args(argv)

    if a.command == "window":
        from .main import run
        return run()
    if a.command == "status":
        print(json.dumps(Api(Services()).overview(), indent=2))
        return 0
    if a.command == "install-mod":
        r = game.install_mod()
        print(r["message"])
        return 0 if r["ok"] else 1
    if a.command == "connect":
        if a.target == "claude-code":
            print(connect.connect_claude_code()["message"])
        elif a.target == "claude-desktop":
            print(connect.connect_claude_desktop()["message"])
        else:
            print(connect.snippet())
        return 0
    if a.command == "services":
        s = Services()
        for key in ("foreman", "overlay"):
            print(s.start(key))
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            s.stop_all()
        return 0
    return 1


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if x != "--debug"]       # --debug: WebView dev tools (read in main.run)
    sys.exit(_cli(args or ["window"]))
