"""Background services the app keeps running while it is open: Foreman (advisor), the overlay server and the
viewer-poll counter. Each runs as its own process on the private runtime, so one crashing never takes the window
down, and a copy already running (started by hand or by an AI) is reused instead of doubled."""
from __future__ import annotations

import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

NO_WINDOW = 0x08000000      # CREATE_NO_WINDOW


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class Service:
    key: str
    title: str
    args: list[str]
    cwd: Path
    port: int | None = None                 # None: no port, judged by our own process only
    url: str = ""
    proc: subprocess.Popen | None = field(default=None, repr=False)
    started_at: float = 0.0
    last_error: str = ""
    _ext: tuple[float, bool] = (0.0, False)  # (checked at, running elsewhere) for port-less services

    def external(self) -> bool:
        """Port-less service: is a copy we didn't start running? (Process scan, cached 30 s.)"""
        if time.time() - self._ext[0] > 30:
            script = Path(self.args[-1]).name
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                 f"Where-Object {{ $_.CommandLine -like '*{script}*' }}).Count"],
                capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW).stdout.strip()
            self._ext = (time.time(), out.isdigit() and int(out) > 0)
        return self._ext[1]

    @property
    def log(self) -> Path:
        return paths.LOGS / f"{self.key}.log"

    def ours(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def status(self) -> dict:
        if self.ours():
            state = "running" if self.port is None or port_open(self.port) else "starting"
        elif self.port is not None and port_open(self.port) or self.port is None and self.external():
            state = "external"               # running, but not started by this app
        elif self.proc is not None:
            state = "crashed"
        else:
            state = "stopped"
        return {"key": self.key, "title": self.title, "state": state, "url": self.url,
                "log": str(self.log), "error": self.last_error}

    def start(self) -> dict:
        self._ext = (0.0, False)
        if self.ours() or (self.port is not None and port_open(self.port)) or (self.port is None and self.external()):
            return self.status()
        paths.LOGS.mkdir(parents=True, exist_ok=True)
        log = open(self.log, "a", encoding="utf-8", errors="replace")
        log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} start: {' '.join(self.args[1:])}\n")
        log.flush()
        try:
            self.proc = subprocess.Popen(self.args, cwd=self.cwd, stdout=log, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
            self.started_at = time.time()
            self.last_error = ""
        except OSError as e:
            self.last_error = str(e)
        finally:
            log.close()
        return self.status()

    def stop(self) -> dict:
        if self.ours():
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self._ext = (0.0, False)
        return self.status()


class Services:
    def __init__(self) -> None:
        py = str(paths.PYTHON)
        self.items: dict[str, Service] = {s.key: s for s in [
            Service("foreman", "Foreman advisor", [py, "-m", "foreman", "serve"], paths.FOREMAN, 8097,
                    "http://127.0.0.1:8097/"),
            Service("overlay", "Stream overlay", [py, str(paths.OVERLAY / "server.py")], paths.OVERLAY, 8096,
                    "http://127.0.0.1:8096/"),
            Service("polls", "Viewer-poll counter", [py, str(paths.CHATPOLL / "poll_service.py")], paths.CHATPOLL),
        ]}
        self._lock = threading.Lock()

    def status(self) -> list[dict]:
        return [s.status() for s in self.items.values()]

    def start(self, key: str) -> dict:
        with self._lock:
            return self.items[key].start()

    def stop(self, key: str) -> dict:
        with self._lock:
            return self.items[key].stop()

    def stop_all(self) -> None:
        for s in self.items.values():
            s.stop()
