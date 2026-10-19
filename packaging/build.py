"""Build the TimberLive Windows installer.

    py -3.11 packaging/build.py            # runtime (if missing), mod, stage, installer
    py -3.11 packaging/build.py --no-iss   # stop after staging (packaging/stage/TimberLive)

The install folder mirrors this repo (app/, harness/, foreman/, ...) so every script's repo-relative paths keep
working, plus runtime/ (private Python) and mod-dist/ (the built bridge mod the app installs). Personal files stay
out: run notes, checkpoints, secrets, caches, the decompiled game code and the operator's own CLAUDE.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "packaging"
STAGE = PKG / "stage" / "TimberLive"
DIST = PKG / "dist"
RUNTIME = REPO / "runtime"
ISCC = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe"]

ALWAYS_SKIP = {"__pycache__", ".pytest_cache", ".venv", "bin", "obj"}
# Top-level folders and files copied as they are (minus SKIP below).
TREES = ["app", "harness", "foreman", "overlay", "chatpoll", "knowledge", "docs",
         ".claude/agents", ".claude/skills", ".claude/hooks"]
FILES = ["AGENTS.md", "LICENSE"]
SKIP = {
    "harness": {"cache", "pending.txt", "pause_ids.txt"},
    "foreman": {"data", "tests"},
    "overlay": {"state.json", "poll_counts.json", "userscript_seen.json"},
    "knowledge": {"goals.md", "run2-stream-notes.md"},
    "docs": {"images", "foreman-plan.md", "foreman-inventory.md"},   # images: GitHub only; design notes: neither
}
SKIP_GLOBS = {"harness": ["*.tmp.py", "*.pkl", "*.png"], "app": ["*.bak"]}
# The operator's own extras (git-ignored): {"skip": {"harness": ["file", ...]}, "words": ["text that must not ship"]}
_PRIVATE_FILE = REPO / ".secrets" / "build-private.json"
PRIVATE = json.loads(_PRIVATE_FILE.read_text(encoding="utf-8")) if _PRIVATE_FILE.exists() else {}
for _top, _names in PRIVATE.get("skip", {}).items():
    SKIP.setdefault(_top, set()).update(_names)


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def run(cmd: list, **kw) -> None:
    log(" ".join(map(str, cmd)))
    subprocess.run(cmd, check=True, **kw)


def ensure_runtime() -> None:
    if (RUNTIME / "python.exe").exists():
        return
    run([sys.executable, str(PKG / "make_runtime.py")])


def build_mod(dest: Path) -> None:
    """Build both mod projects straight into dest (the mod folder the app copies into Documents\\Timberborn\\Mods)."""
    dest.mkdir(parents=True, exist_ok=True)
    try:
        run(["dotnet", "build", str(REPO / "TimberLive.sln"), "-c", "Release", "-nologo", "-v:q",
             f"-p:ModDeployDir={dest}"])
    except (OSError, subprocess.CalledProcessError) as e:
        sys.path.insert(0, str(REPO / "app"))
        from timberlive_app import paths
        installed = paths.mods_dir() / "TimberLive.Bridge"
        if not installed.exists():
            raise SystemExit(f"mod build failed ({e}) and no installed copy to fall back on")
        log(f"mod build failed ({e}); copying the installed mod from {installed}")
        shutil.rmtree(dest)
        shutil.copytree(installed, dest)
    for need in ("manifest.json", "Scripts/TimberLive.Bridge.dll", "Logic/TimberLive.Bridge.Logic.bin"):
        if not (dest / need).exists():
            raise SystemExit(f"mod is missing {need}")


def copy_tree(rel: str) -> None:
    top = rel.split("/")[0]
    skip = SKIP.get(top, set())
    globs = SKIP_GLOBS.get(top, [])

    def ignore(folder: str, names: list[str]) -> set[str]:
        out = {n for n in names if n in ALWAYS_SKIP}
        if Path(folder) == REPO / top:
            out |= {n for n in names if n in skip}
        for g in globs:
            out |= {n for n in names if Path(n).match(g)}
        return out

    shutil.copytree(REPO / rel, STAGE / rel, ignore=ignore)


def copy_runtime() -> None:
    def ignore(folder: str, names: list[str]) -> set[str]:
        out = {n for n in names if n == "__pycache__"}
        if os.path.normpath(folder) == os.path.normpath(RUNTIME):
            out.add("Scripts")   # pip's .exe launchers hard-code the build machine's python.exe path; unused

        if folder.endswith(os.path.join("googleapiclient", "discovery_cache", "documents")):
            out |= {n for n in names if n != "youtube.v3.json"}
        return out
    shutil.copytree(RUNTIME, STAGE / "runtime", ignore=ignore)


def make_generic() -> None:
    """Swap the operator's personal bits for neutral ones."""
    shutil.copy2(PKG / "workspace" / "CLAUDE.md", STAGE / "CLAUDE.md")
    shutil.copy2(PKG / "workspace" / "goals.md", STAGE / "knowledge" / "goals.md")
    shutil.copy2(PKG / "workspace" / "README.md", STAGE / "README.md")
    (STAGE / "harness" / "pending.txt").write_text("", encoding="utf-8")
    # The ticker's intro line names this run's colony and map.
    js = STAGE / "overlay" / "web" / "app.js"
    s = js.read_text(encoding="utf-8")
    s2 = re.sub(r'\n  "Season 2![^\n]*\n', '\n  "My goal: survive every drought and badtide and build one of everything.",\n', s)
    if s2 == s:
        log("warning: ticker intro line not found in overlay/web/app.js")
    js.write_text(s2, encoding="utf-8")


def stage() -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    for rel in TREES:
        copy_tree(rel)
    for rel in FILES:
        shutil.copy2(REPO / rel, STAGE / rel)
    make_generic()
    build_mod(STAGE / "mod-dist" / "TimberLive.Bridge")
    copy_runtime()
    home = str(REPO.parent)
    personal = "|".join([r"Timbelligence", r"\b(?:\+?44|0)7\d{9}\b"] + [re.escape(w) for w in PRIVATE.get("words", [])]
                        + [re.escape(home), re.escape(home.replace("\\", "/")), re.escape(home.replace("\\", "\\\\"))])
    leaks = [p for p in STAGE.rglob("*") if p.is_file() and p.suffix in (".md", ".py", ".js", ".yaml", ".json", ".cmd", ".ps1")
             and "runtime" not in p.relative_to(STAGE).parts
             and re.search(personal, p.read_text(encoding="utf-8", errors="ignore"), re.I)]
    paths = re.compile("|".join(re.escape(h) for h in {home, home.replace("\\", "/"), home.replace("\\", "\\\\")}).encode(), re.I)
    leaks += [p for p in STAGE.rglob("*") if p.is_file() and p not in leaks and paths.search(p.read_bytes())]
    for p in leaks:
        log(f"note: personal reference left in {p.relative_to(STAGE)}")
    if any(paths.search(p.read_bytes()) for p in leaks):
        sys.exit("stopped: the build machine's folder path is inside the staged files (see notes above)")
    size = sum(p.stat().st_size for p in STAGE.rglob("*") if p.is_file())
    log(f"staged {STAGE} ({size / 2**20:.0f} MB)")


def installer() -> Path:
    iscc = next((p for p in ISCC if p.exists()), None)
    if not iscc:
        raise SystemExit("Inno Setup 6 not found (https://jrsoftware.org/isdl.php)")
    sys.path.insert(0, str(REPO / "app"))
    from timberlive_app import __version__
    DIST.mkdir(exist_ok=True)
    run([str(iscc), "/Q", f"/DAppVersion={__version__}", f"/DStage={STAGE}", f"/O{DIST}",
         str(PKG / "installer.iss")])
    out = DIST / f"TimberLive-Setup-{__version__}.exe"
    log(f"installer: {out} ({out.stat().st_size / 2**20:.0f} MB)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-iss", action="store_true", help="stage only")
    a = ap.parse_args()
    ensure_runtime()
    stage()
    if not a.no_iss:
        installer()
