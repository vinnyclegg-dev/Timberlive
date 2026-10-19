# Packaging

The TimberLive app (`app/timberlive_app`) is a pywebview window on a private Python runtime (`runtime/`). It runs Foreman and the overlay, installs the mod and connects the user's AI. It never calls the game tools itself.

| Step | Command (from the repo root) |
|---|---|
| Make the runtime (once, or after changing `requirements.txt`) | `py -3.11 packaging/make_runtime.py [--clean]` |
| Redraw the icon | `runtime/python packaging/make_icon.py` |
| Run the app from the checkout | `runtime/python -m timberlive_app [--debug]` (or `status`, `connect claude-code`, `install-mod`) |
| Build the installer | `runtime/python packaging/build.py` → `packaging/dist/TimberLive-Setup-<version>.exe` |

`build.py` builds the mod (`dotnet build -c Release` into the stage, so your installed mod is left alone) and stages the repo layout into `packaging/stage/TimberLive`. It leaves out personal files and swaps in the generic `workspace/CLAUDE.md`, `goals.md` and `README.md`. Then it runs Inno Setup 6 (`installer.iss`: per-user install, no admin prompt).

Bump `app/timberlive_app/__init__.py` `__version__` for each release.
