"""Population: births vs deaths, pods, beds, needs (plan section 4.4; ported from watch.py ledger)."""

from __future__ import annotations

import math

from ..findings import Finding, monitor


def pods_needed(beavers: int) -> int:
    # Iron Teeth live ~50 days and a pod makes a kit every 5 days: ~beavers/10 pods hold steady, +1 to grow,
    # never fewer than 3 (the founders die of old age in cycles 1-3). CLAUDE.md "A stable population comes first".
    return max(3, math.ceil(beavers / 10) + 1)


def ledger(world, ctx) -> dict:
    cycle = world.colony["time"]["cycle"]
    events = ctx.store.alerts()

    def tally(evs):
        died = [e["cause"] or "?" for e in evs if e["kind"] == "died"]
        return {"born": sum(e["kind"] == "born" for e in evs), "died": len(died),
                "causes": {c: died.count(c) for c in sorted(set(died))}}
    pods = world.finished("BreedingPod")
    running = sum(1 for b in pods if "Paused." not in (b.raw.get("statuses") or []) and not b.raw.get("paused"))
    return {"cycle": tally([e for e in events if e["cycle"] == cycle]),
            "previous": tally([e for e in events if e["cycle"] == cycle - 1]),
            "recent": tally([e for e in events if e["cycle"] >= cycle - 1]),
            "run": tally(events), "pods": len(pods), "running": running, "need": pods_needed(world.beavers)}


@monitor("pop.ledger", rules=["births-keep-up", "pods-min-3"])
def pop_ledger(world, ctx):
    """Births must keep up with deaths; pods running >= max(3, beavers/10 + 1)."""
    lg = ledger(world, ctx)
    r = lg["recent"]
    if r["died"] > r["born"] or lg["running"] < lg["need"]:
        t = world.colony.get("time") or {}
        early = t.get("cycle", 1) == 1 and t.get("cycleDay", 1) < 5 and not r["died"]
        # cycle 1 before day 5 with no deaths: plan.opening's pods-by-day-5 owns the deadline
        yield Finding("pop.ledger", "warn" if early else "critical", f"population at risk: {r['born']} born vs {r['died']} died since "
                      f"last cycle; {lg['running']} pods running, want >= {lg['need']}: a pod (10 logs) and beds "
                      "come before any build except water and food", "population", evidence=lg)


@monitor("pop.beds", rules=["beds-for-kits"])
def beds(world, ctx):
    """Homeless beavers, or no free bed for the next kit while pods run."""
    p = world.colony["population"]
    if p.get("homeless", 0) > 0:
        yield Finding("pop.beds", "warn", f"{p['homeless']} homeless: build a Barrack", "beds")
    elif p.get("freeBeds", 0) == 0 and world.finished("BreedingPod"):
        yield Finding("pop.beds", "info", "no free beds for the next kits: queue a Barrack", "beds")


@monitor("pop.needs", rules=["critical-needs", "wellbeing"])
def needs(world, ctx):
    """Any beaver in a critical need state (thirst, hunger, injury...)."""
    crit = [n for n in world.needs if n.get("critical", 0) > 0]
    if crit:
        yield Finding("pop.needs", "critical", "critical needs: " + ", ".join(f"{n['need']} x{n['critical']}"
                                                                              for n in crit), "needs")


KIT_EVERY_DAYS = 5      # CLAUDE.md: a pod makes a kit every 5 days
AGE_HORIZON = 10        # days ahead for the old-age wave


@monitor("pop.age_wave", rules=["births-keep-up", "pods-min-3", "beds-for-kits"])
def age_wave(world, ctx):
    """Beavers dying of old age in the next 10 days vs kits the running pods make in that time."""
    if not world.beaver_list:
        return
    adults = [b for b in world.beaver_list if not b["child"] and not b["bot"] and b.get("daysLeft") is not None]
    dying = [b for b in adults if b["daysLeft"] <= AGE_HORIZON]
    running = ledger(world, ctx)["running"]
    kits = running * AGE_HORIZON / KIT_EVERY_DAYS
    if dying and len(dying) > kits:
        extra = math.ceil((len(dying) - kits) * KIT_EVERY_DAYS / AGE_HORIZON)
        soonest = sorted(b["daysLeft"] for b in dying)[:3]
        yield Finding("pop.age_wave", "warn", f"{len(dying)} beavers reach old age within {AGE_HORIZON} days "
                      f"(soonest {soonest} days); {running} pods make ~{kits:.0f} kits: add {extra} pods and beds",
                      "age", evidence={"dying": len(dying), "kits": kits, "pods": running})


@monitor("pop.medical", rules=["medical-beds"])
def medical(world, ctx):
    """Injured beavers (Injury need below zero or critical) and no Medical Bed."""
    inj = next((n for n in world.needs if "Injur" in n.get("need", "")), None)
    if inj and ((inj.get("average") or 0) < 0 or inj.get("critical")) and not world.finished("MedicalBed"):
        yield Finding("pop.medical", "warn", f"injuries (avg {inj.get('average')}, critical {inj.get('critical')}) "
                      "and no Medical Bed: build one near the workshops", "medical")
