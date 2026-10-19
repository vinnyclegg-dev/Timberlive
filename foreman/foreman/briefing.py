"""The briefing: about 30 lines an AI with a small context window can play from (plan section 8)."""

from __future__ import annotations

from .monitors import POWER_USE
from .monitors.forecast import rates
from .monitors.population import ledger
from .monitors.progress import tally
from .monitors.supply import food_days, reserves

TOP = 8


def briefing(world, ctx, findings, top: int = TOP) -> str:
    c = world.colony
    tm, w, p = c["time"], c.get("weather") or {}, c["population"]
    r = reserves(world, ctx)
    lg = ledger(world, ctx)
    weather = w.get("state", "?")
    if weather == "approaching":
        weather = f"{w.get('hazard')} in {w.get('daysUntil')} days"
    elif weather == "hazardous":
        weather = f"{w.get('hazard')} {w.get('daysRemaining')} days left"
    lines = [
        f"FOREMAN c{tm['cycle']}d{tm['cycleDay']} ({tm.get('dayProgress', 0):.0%}) speed {tm.get('speed')} | {weather}",
        f"POP {p.get('adults')}a+{p.get('children')}k homeless {p.get('homeless')} unemployed {p.get('unemployed')} "
        f"freeJobs {p.get('freeWorkslots')} freeBeds {p.get('freeBeds')} | sci {c.get('science')} "
        f"wb {round(c.get('wellbeing') or 0, 1)}",
        f"FOOD {r['food_stock']} = {food_days(world):.1f} days | reserve {r['food_need']:.0f} "
        f"({'ok' if r['food_stock'] >= r['food_need'] else 'SHORT ' + str(int(r['food_need'] - r['food_stock']))})",
        f"WATER {r['water_stock']}/{r['water_cap']} | use {r['water_use']:.0f}/day "
        f"(beavers {2.6 * world.beavers:.0f} + buildings {r['water_build']}) | reserve {r['water_need']:.0f} "
        f"({'ok' if r['water_stock'] >= r['water_need'] else 'SHORT ' + str(int(r['water_need'] - r['water_stock']))})",
        f"LEDGER c{tm['cycle']} +{lg['cycle']['born']} -{lg['cycle']['died']} | c{tm['cycle'] - 1} "
        f"+{lg['previous']['born']} -{lg['previous']['died']} | run +{lg['run']['born']} -{lg['run']['died']} "
        f"{lg['run']['causes'] or ''}| pods {lg['running']}/{lg['pods']} running, want >= {lg['need']}",
    ]
    stock = {g: v["available"] for g, v in world.goods.items() if v.get("available") or v.get("capacity")}
    lines.append("STOCK " + ", ".join(f"{g} {n}" for g, n in stock.items()))
    low = [n for n in world.needs if n.get("critical") or n.get("warning") or (n.get("average") or 1) < 0.5]
    lines.append("NEEDS " + (", ".join(f"{n['need']} avg {n['average']} crit {n['critical']} warn {n['warning']}"
                                       for n in low) or "all fine"))
    if world.networks:
        nets = world.power_networks()
        lines.append("POWER " + " | ".join(
            f"net {i + 1}: {n['supply']}/{n['demand']} hp, {n['generators']} generators, "
            f"{len(nets.get(n['id'], []))} machines (nominal {sum(POWER_USE.get(b.name, 0) for b in nets.get(n['id'], []) if not b.raw.get('paused'))})"
            + (f", battery {n['batteryCharge']:.0f}/{n['batteryCapacity']:.0f}" if n.get("batteryCapacity") else "")
            for i, n in enumerate(sorted(world.networks, key=lambda n: -n["supply"]))))
    r_ = rates(world, ctx)
    if r_:
        lines.append(f"TREND over {r_['span']:.1f} days: " + ", ".join(f"{k} {v:+.0f}/day" for k, v in r_.items()
                                                                     if k != "span"))
    t = tally(world)
    if t:
        lines.append(f"PROGRESS {t['done']}/{t['total']} buildings | ready to place: "
                     f"{[bp['name'] for bp in t['ready'][:4]]} | next locked: "
                     f"{[(bp['name'], bp['science']) for bp in t['locked'][:3]]}")
    batches = world.state.get("batches") or {}
    if batches:
        lines.append("BATCH " + " | ".join(
            f"{world.by_id[i].label} {st['recipe']} {st['progress']:.0%}{'' if st['inputs_ok'] else ' INPUTS MISSING'}"
            for i, st in batches.items() if i in world.by_id))
    sites = [b for b in world.buildings if not b.finished and not b.name.startswith("Path")]
    if sites:
        lines.append(f"SITES {len(sites)}: " + ", ".join(f"{b.label} {int((b.raw.get('buildProgress') or 0) * 100)}%"
                                                         for b in sites[:6]) + (" ..." if len(sites) > 6 else ""))
    reqs = [f for f in findings if f.rule == "stream.requests"]
    problems = [f for f in findings if f.rule != "stream.requests"]
    counts = {s: sum(f.severity == s for f in problems) for s in ("critical", "warn", "info")}
    lines.append(f"FINDINGS {counts['critical']} critical, {counts['warn']} warn, {counts['info']} info"
                 + ("" if problems else ": all clear"))
    lines += [f"  {f.line()}" for f in problems[:top]]
    if len(problems) > top:
        lines.append(f"  ... {len(problems) - top} more: foreman findings")
    if reqs:
        lines.append(f"REQUESTS {len(reqs)} open:")
        lines += [f"  - {f.message[:150]}" for f in reqs[:6]]
    if world.state.get("map_age") is None:
        lines.append("NOTE no map scan yet: map checks (badwater near pumps, roads) are skipped")
    lines += _next(world)
    return "\n".join(lines)


def _next(world) -> list[str]:
    """The next masterplan steps, validated now; nothing if no plan was made yet (making one takes a second)."""
    from . import masterplan
    try:
        plan = masterplan.load(world)
        if not plan:
            return ["NEXT no masterplan yet: call foreman_masterplan once (it makes one), then foreman_suggestions"]
        return masterplan.next_text(masterplan.suggestions(world, plan, 3)).splitlines()
    except Exception as e:                       # the briefing must never fail because of the planner
        return [f"NEXT unavailable ({type(e).__name__}: {e})"]
