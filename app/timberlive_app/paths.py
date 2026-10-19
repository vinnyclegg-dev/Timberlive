"""Where everything lives. The installed app has the same layout as the repo, so one set of paths serves both."""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # app/timberlive_app/paths.py -> install (or repo) root
APP = ROOT / "app" / "timberlive_app"
UI = APP / "ui"
ICON = UI / "icon.ico"
RUNTIME = ROOT / "runtime"
LOGS = ROOT / "logs"
HARNESS = ROOT / "harness"
FOREMAN = ROOT / "foreman"
OVERLAY = ROOT / "overlay"
CHATPOLL = ROOT / "chatpoll"
MOD_SOURCE = ROOT / "mod-dist" / "TimberLive.Bridge"   # prebuilt mod shipped with the app
USER_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TimberLive"   # bridge.json, youtube.json, obs.json


def _python(windowed: bool) -> Path:
    """The private runtime's interpreter, or the one running now (a dev venv) if there is no runtime/."""
    name = "pythonw.exe" if windowed else "python.exe"
    if (RUNTIME / name).exists():
        return RUNTIME / name
    exe = Path(sys.executable)
    other = exe.with_name(name)
    return other if other.exists() else exe


PYTHON = _python(windowed=False)
PYTHONW = _python(windowed=True)


def documents_dir() -> Path:
    """The real Documents folder (it may be redirected to OneDrive)."""
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]
    # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
    fid = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
    out = ctypes.c_wchar_p()
    try:
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) == 0:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except (AttributeError, OSError):
        pass
    return Path.home() / "Documents"


def mods_dir() -> Path:
    return documents_dir() / "Timberborn" / "Mods"
