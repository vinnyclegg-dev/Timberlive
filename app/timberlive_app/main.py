"""The app window: a native window (WebView2) over the app's own pages. Foreman and the overlay start with it
and stop with it (copies that were already running are left alone)."""
from __future__ import annotations

import ctypes
import sys

from . import paths
from .api import Api
from .services import Services

TITLE = "TimberLive"
APP_ID = "TimberLive.App"            # matches the installer's shortcut, so the taskbar shows our icon


def _single_instance() -> bool:
    """True if this is the only copy; otherwise bring the open window to the front."""
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW(None, False, "Local\\TimberLive.App")
    if k32.GetLastError() != 183:      # ERROR_ALREADY_EXISTS
        return True
    hwnd = ctypes.windll.user32.FindWindowW(None, TITLE)
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    return False


def _set_icon() -> None:
    u32 = ctypes.windll.user32
    hwnd = u32.FindWindowW(None, TITLE)
    if not hwnd or not paths.ICON.exists():
        return
    u32.LoadImageW.restype = ctypes.c_void_p
    for size, which in ((16, 0), (32, 1)):                # ICON_SMALL, ICON_BIG
        icon = u32.LoadImageW(None, str(paths.ICON), 1, size * 2 if which else size, size * 2 if which else size,
                              0x10)                         # IMAGE_ICON, LR_LOADFROMFILE
        if icon:
            u32.SendMessageW(hwnd, 0x80, which, ctypes.c_void_p(icon))   # WM_SETICON


def run() -> int:
    if not _single_instance():
        return 0
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass

    import webview

    services = Services()
    for key in ("foreman", "overlay"):
        services.start(key)

    window = webview.create_window(
        TITLE, url=str(paths.UI / "index.html"), js_api=Api(services),
        width=1360, height=880, min_size=(980, 640), background_color="#15181c", text_select=True)
    window.events.shown += _set_icon
    try:
        webview.start(gui="edgechromium", http_server=True, private_mode=False,
                      storage_path=str(paths.USER_DIR / "webview"), debug="--debug" in sys.argv)
    finally:
        services.stop_all()
    return 0
