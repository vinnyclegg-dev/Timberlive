"""Findings framework: monitors are plain functions that read the World and yield Findings.

A finding never changes the game. `fix` is the exact harness call the playing AI can choose to run
(MCP tool syntax, which is also the `timberlive_mcp` function name: `t.<call>` in python).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

SEVERITY_ORDER = {"critical": 0, "warn": 1, "info": 2}


@dataclass
class Finding:
    rule: str                       # monitor id, e.g. "water.reserve"
    severity: str                   # critical | warn | info
    message: str                    # one line for the briefing
    entity: str = ""                # building id, good id or "" for colony-wide
    where: list | None = None       # [x, y, z] when it has a place
    evidence: dict = field(default_factory=dict)
    fix: str = ""                   # exact harness call(s), or "" when it needs a decision
    runs: int = 1                   # consecutive collections it has been open (from the store)

    @property
    def key(self) -> str:
        return f"{self.rule}|{self.entity}"

    def line(self) -> str:
        age = f" (x{self.runs})" if self.runs > 1 else ""
        fix = f"  -> {self.fix}" if self.fix else ""
        return f"[{self.severity.upper()}] {self.rule}: {self.message}{age}{fix}"


@dataclass
class Monitor:
    id: str
    fn: Callable
    rules: tuple[str, ...]          # rules.yaml ids this monitor enforces
    doc: str


MONITORS: dict[str, Monitor] = {}


def monitor(mid: str, rules: Iterable[str] = ()):
    def wrap(fn):
        MONITORS[mid] = Monitor(mid, fn, tuple(rules), (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else "")
        return fn
    return wrap


def run_all(world, ctx, only: Iterable[str] | None = None) -> list[Finding]:
    """Run every monitor; a crashing monitor becomes a finding instead of stopping the rest."""
    from . import monitors  # noqa: F401  (registers the monitors)
    out: list[Finding] = []
    for mid, m in MONITORS.items():
        if only and mid not in only:
            continue
        try:
            out.extend(m.fn(world, ctx) or [])
        except Exception as e:  # pragma: no cover - surfaced to the AI, not hidden
            out.append(Finding("foreman.error", "warn", f"monitor {mid} failed: {e.__class__.__name__}: {e}", mid))
    return out


def rank(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 3), -f.runs, f.rule))
