"""Rulebook (rules.yaml) and its coverage: which rules have an automated check (a monitor or a checker guard
that lists the rule id)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

RULES = Path(__file__).with_name("rules.yaml")


def load() -> list[dict]:
    return yaml.safe_load(RULES.read_text(encoding="utf-8")) or [] if RULES.exists() else []


def coverage() -> tuple[list[dict], dict[str, list[str]], list[str]]:
    """(rules, rule id -> monitor/guard ids checking it, rule ids used in code but missing from rules.yaml)."""
    from . import monitors  # noqa: F401  (registers the monitors)
    from .checker import GUARDS
    from .findings import MONITORS
    rules = load()
    checked: dict[str, list[str]] = {}
    for m in MONITORS.values():
        for rid in m.rules:
            checked.setdefault(rid, []).append(m.id)
    for gid, rids in GUARDS.items():
        for rid in rids:
            checked.setdefault(rid, []).append(gid)
    ids = {r["id"] for r in rules}
    return rules, checked, sorted(set(checked) - ids)


def coverage_report() -> str:
    rules, checked, unknown = coverage()
    auto = [r for r in rules if r["id"] in checked]
    conduct = [r for r in rules if r.get("kind") == "conduct"]
    manual = [r for r in rules if r["id"] not in checked and r.get("kind") != "conduct"]
    lines = [f"RULES {len(rules)}: {len(auto)} checked by monitors or guards, {len(manual)} not yet automated, "
             f"{len(conduct)} conduct (AI behaviour, manual by design)"]
    by_phase = Counter(r.get("phase") for r in manual)
    lines.append("not yet automated, by planned phase: " + ", ".join(f"phase {p}: {n}" for p, n in sorted(by_phase.items(), key=lambda kv: str(kv[0]))))
    if unknown:
        lines.append(f"rule ids missing from rules.yaml: {unknown}")
    lines.append("")
    for r in rules:
        tag = ", ".join(checked[r["id"]]) if r["id"] in checked else ("conduct" if r.get("kind") == "conduct"
                                                                        else f"manual (phase {r.get('phase')})")
        lines.append(f"{r['id']:<34} {tag:<40} {r['text'][:90]}")
    return "\n".join(lines)
