"""Keeps the viewer-poll vote counter running and reports the totals (numbers only).

The counter is chatpoll/poll_service.py (YouTube API, counts only). It idles between polls,
so it can run all stream. ensure_service() starts it if no copy is running.
"""
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "overlay" / "state.json"
COUNTS = ROOT / "overlay" / "poll_counts.json"
START = ROOT / "chatpoll" / "start-chatpoll.cmd"


def service_running() -> bool:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
         "Where-Object { $_.CommandLine -like '*poll_service.py*' }).Count"],
        capture_output=True, text=True, timeout=20).stdout.strip()
    return out.isdigit() and int(out) > 0


def ensure_service() -> str:
    if service_running():
        return "running"
    subprocess.run(["cmd", "/c", str(START)], timeout=20)
    return "started"


def poll_line() -> str | None:
    """One report line while a poll is open (or just closed), restarting the counter if needed."""
    try:
        poll = json.loads(STATE.read_text(encoding="utf-8")).get("poll")
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not poll:
        return None
    open_ = not poll.get("closed") and time.time() < poll["closes"]
    try:
        counts = json.loads(COUNTS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        counts = {}
    same = counts.get("id") == poll["id"]
    numbers = counts.get("counts") if same else [0] * len(poll["options"])
    status = counts.get("status", "not_running") if same else "not_running"
    note = ""
    if open_ and status != "counting":
        note = f"  <-- counter {ensure_service()}"
    left = max(0, round(poll["closes"] - time.time()))
    tag = f"open {left}s left" if open_ else ("CLOSED: read result, narrate, close_poll" if not poll.get("closed") else "closed")
    return f"POLL {dict(zip(poll['options'], numbers))} [{status}] {tag}{note}"


if __name__ == "__main__":
    print(ensure_service())
    print(poll_line())
