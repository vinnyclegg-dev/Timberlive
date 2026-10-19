"""Build runtime/: a private, relocatable Python 3.11 with every package the app needs.

    py -3.11 packaging/make_runtime.py [--clean]

The app, Foreman, the harness tools, the overlay and the poll counter all run on this one
interpreter, in a dev checkout and in the installed app alike (the installer copies runtime/).
It is a trimmed copy of a normal Python install (not a venv, not the embeddable zip), so it can
move anywhere: Python finds its home from Lib/os.py next to python.exe, and scripts behave
exactly as with a normal install (the script's folder is on sys.path, `python -c` works).

A timberlive.pth in site-packages puts app/ and foreman/ on sys.path, so `-m timberlive_app`
and `-m foreman` work from any folder. harness/ is not added: harness scripts import their
siblings from their own folder, as before.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
REQUIREMENTS = Path(__file__).with_name("requirements.txt")

# Parts of the standard library the app never uses (saves ~40 MB in the installer).
SKIP_LIB = {"test", "idlelib", "tkinter", "turtledemo", "site-packages", "__pycache__"}
SKIP_DLLS = ("_tkinter", "tcl", "tk")


def copy_base(base: Path) -> None:
    RUNTIME.mkdir(parents=True)
    for f in base.iterdir():
        if f.is_file() and f.suffix.lower() in (".exe", ".dll", ".txt"):
            shutil.copy2(f, RUNTIME / f.name)
    shutil.copytree(base / "DLLs", RUNTIME / "DLLs",
                    ignore=lambda d, names: [n for n in names if n.lower().startswith(SKIP_DLLS)])
    (RUNTIME / "Lib").mkdir()
    for item in (base / "Lib").iterdir():
        if item.name in SKIP_LIB:
            continue
        if item.is_dir():
            shutil.copytree(item, RUNTIME / "Lib" / item.name,
                            ignore=shutil.ignore_patterns("__pycache__", "test", "tests"))
        else:
            shutil.copy2(item, RUNTIME / "Lib" / item.name)
    (RUNTIME / "Lib" / "site-packages").mkdir()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clean", action="store_true", help="delete runtime/ first")
    ap.add_argument("--python", default=sys.executable, help="a Python 3.11 to copy (default: this one)")
    a = ap.parse_args()

    base = Path(subprocess.check_output([a.python, "-c", "import sys; print(sys.base_prefix)"], text=True).strip())
    if (base / "pyvenv.cfg").exists() or not (base / "Lib" / "os.py").exists():
        print(f"not a normal Python install: {base}")
        return 1
    if a.clean and RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    if not RUNTIME.exists():
        print(f"copying Python from {base}")
        copy_base(base)

    py = str(RUNTIME / "python.exe")
    subprocess.check_call([py, "-m", "ensurepip", "--default-pip"])
    subprocess.check_call([py, "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location",
                           "-r", str(REQUIREMENTS)])
    site = RUNTIME / "Lib" / "site-packages"
    # .pth lines are relative to site-packages: runtime/Lib/site-packages -> repo root is ../../..
    (site / "timberlive.pth").write_text("../../../app\n../../../foreman\n", encoding="utf-8")
    subprocess.check_call([py, "-c", "import timberlive_app, foreman, mcp, fastapi, numpy, webview; print('runtime ok')"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
