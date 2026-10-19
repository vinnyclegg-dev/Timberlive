"""SQLite store: snapshots (only when they change), game alerts, findings history and a small key/value table."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import zlib
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DB = DATA / "foreman.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY, ts REAL, game_day REAL, kind TEXT, hash TEXT, data BLOB);
CREATE INDEX IF NOT EXISTS snapshots_kind ON snapshots(kind, ts);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY, cycle INTEGER, day INTEGER, text TEXT, kind TEXT, cause TEXT,
    UNIQUE(cycle, day, text));
CREATE TABLE IF NOT EXISTS findings (
    key TEXT PRIMARY KEY, rule TEXT, severity TEXT, entity TEXT, where_json TEXT, message TEXT,
    evidence TEXT, fix TEXT, first_ts REAL, first_day REAL, last_ts REAL, last_day REAL,
    runs INTEGER, cleared_ts REAL);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


def _plain(v):
    """numpy scalars and tuples from monitors -> plain JSON."""
    if isinstance(v, (set, frozenset)):
        return sorted(v, key=str)
    return v.item() if hasattr(v, "item") else str(v)


def dumps(v) -> str:
    return json.dumps(v, default=_plain)


class Store:
    def __init__(self, path: Path | str = DEFAULT_DB):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    # -------------------------------------------------------- snapshots
    def put_snapshot(self, kind: str, data: Any, game_day: float | None = None) -> bool:
        """Store a snapshot if it differs from the last one of this kind. Returns True if stored."""
        blob = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
        digest = hashlib.sha1(blob).hexdigest()
        last = self.db.execute("SELECT hash FROM snapshots WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
        if last and last[0] == digest:
            self.db.execute("UPDATE snapshots SET ts=?, game_day=? WHERE id=(SELECT MAX(id) FROM snapshots WHERE kind=?)",
                            (time.time(), game_day, kind))
            self.db.commit()
            return False
        self.db.execute("INSERT INTO snapshots(ts, game_day, kind, hash, data) VALUES (?,?,?,?,?)",
                        (time.time(), game_day, kind, digest, zlib.compress(blob)))
        self.db.commit()
        return True

    def latest(self, kind: str) -> tuple[float, Any] | None:
        row = self.db.execute("SELECT ts, data FROM snapshots WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
        return (row[0], json.loads(zlib.decompress(row[1]))) if row else None

    def history(self, kind: str, since_ts: float = 0) -> list[tuple[float, float, Any]]:
        rows = self.db.execute("SELECT ts, game_day, data FROM snapshots WHERE kind=? AND ts>=? ORDER BY id",
                               (kind, since_ts)).fetchall()
        return [(ts, day, json.loads(zlib.decompress(d))) for ts, day, d in rows]

    # -------------------------------------------------------- alerts (births, deaths, game notices)
    def add_alerts(self, alerts: list[dict]) -> int:
        added = 0
        for a in alerts:
            text = a.get("text", "")
            kind = "born" if "was born" in text else "died" if (" died" in text or "starved" in text) else "other"
            cause = ""
            if kind == "died":
                cause = "starvation" if "starved" in text else text.split(" died", 1)[1].strip(" .").removeprefix("of ")
            cur = self.db.execute("INSERT OR IGNORE INTO alerts(cycle, day, text, kind, cause) VALUES (?,?,?,?,?)",
                                  (a.get("cycle"), a.get("day"), text, kind, cause))
            added += cur.rowcount
        self.db.commit()
        return added

    def alerts(self, kinds: tuple[str, ...] = ("born", "died")) -> list[dict]:
        q = f"SELECT id, cycle, day, text, kind, cause FROM alerts WHERE kind IN ({','.join('?' * len(kinds))}) ORDER BY id"
        return [dict(zip(("seq", "cycle", "day", "text", "kind", "cause"), r)) for r in self.db.execute(q, kinds)]

    # -------------------------------------------------------- key/value (site ages, marks)
    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value: Any) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, dumps(value)))
        self.db.commit()

    # -------------------------------------------------------- findings history
    def record_findings(self, findings: list, game_day: float) -> None:
        """Upsert the current findings; findings no longer raised get cleared_ts set."""
        now = time.time()
        live = set()
        for f in findings:
            live.add(f.key)
            row = self.db.execute("SELECT runs, cleared_ts FROM findings WHERE key=?", (f.key,)).fetchone()
            if row and row[1] is None:
                self.db.execute("UPDATE findings SET severity=?, message=?, evidence=?, fix=?, where_json=?, last_ts=?, "
                                "last_day=?, runs=runs+1 WHERE key=?",
                                (f.severity, f.message, dumps(f.evidence), f.fix, dumps(f.where), now,
                                 game_day, f.key))
            else:
                self.db.execute("INSERT OR REPLACE INTO findings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
                                (f.key, f.rule, f.severity, f.entity, dumps(f.where), f.message,
                                 dumps(f.evidence), f.fix, now, game_day, now, game_day, 1))
        open_keys = [r[0] for r in self.db.execute("SELECT key FROM findings WHERE cleared_ts IS NULL")]
        for key in open_keys:
            if key not in live:
                self.db.execute("UPDATE findings SET cleared_ts=? WHERE key=?", (now, key))
        self.db.commit()

    def finding_age(self, key: str) -> tuple[int, float | None]:
        """(runs seen in a row, first game day) for an open finding."""
        row = self.db.execute("SELECT runs, first_day FROM findings WHERE key=? AND cleared_ts IS NULL", (key,)).fetchone()
        return (row[0], row[1]) if row else (0, None)

    def reset(self) -> None:
        """New game: drop everything."""
        for table in ("snapshots", "alerts", "findings", "kv"):
            self.db.execute(f"DELETE FROM {table}")
        self.db.commit()
