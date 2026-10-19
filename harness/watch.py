"""Run the game until something needs a decision, then print a compact report.
The game is left running (stream rule) at the given speed.

Usage: python watch.py [max_seconds] [speed] [ignore] [--say "thought"]
--say posts an overlay thought before running (saves a separate narrate call).
While waiting, every 30 s the camera checks its view: if beavers are working or
something is being built in view, it stays put; otherwise it pans to the nearest
building site or working beaver.
Stops early on: new game alert, weather change, any critical need, a building
finishing, or a key stock (water/food) falling below its threshold.
"""

import json
import math
import sys
import time
from pathlib import Path

import timberlive_mcp as t
from audit import audit
from pollguard import poll_line

# Edible goods only. Raw Cassava, Soybean, Corn, Eggplant and Potato are ingredients:
# they count as food only after the Fermenter / Food Factory / Grill has processed them.
FOOD = ("Berries", "Kohlrabi", "FermentedCassava", "FermentedSoybean", "FermentedMushroom",
        "CornRation", "EggplantRation", "AlgaeRation", "Carrot", "GrilledPotato", "Bread")


def snapshot():
    colony = json.loads(t.get_colony())
    goods = {g["id"]: g for g in json.loads(t.get_goods())}
    needs = json.loads(t.get_needs())["needs"]
    buildings = json.loads(t.list_buildings())
    return colony, goods, needs, buildings


# Camera tour while waiting (stream rule: always something to watch; a still camera is fine
# while there is action in view). Stops are building sites plus beavers doing their job.
# No constant rotation. Slow, short pans only: quick back-and-forth jumps make viewers motion sick.
CAMERA_EVERY = 30
SHOTS = [(1.7, 135, 38), (2.4, 90, 30), (1.9, 180, 42), (2.9, 135, 28)]  # zoom, horizontal, vertical
IN_VIEW = 6  # tiles from the camera target that count as "on screen"


def tour_stops(buildings):
    sites = [(b["x"], b["y"]) for b in buildings if not b["finished"] and not b["template"].startswith("Path")]
    # Builders waiting at the District Center aren't interesting; everyone else at work is.
    workers = [(w["x"], w["y"]) for w in json.loads(t.working_beavers())
               if not w["workplace"].startswith("DistrictCenter")]
    # One stop per 5x5 patch, so the camera doesn't hop between beavers standing side by side.
    return list({(x // 5 * 5 + 2, y // 5 * 5 + 2) for x, y in sites + workers})


def next_stop(stops, here, shown):
    """Nearest stop not yet shown this round; start a new round when all have been shown."""
    fresh = [s for s in stops if s not in shown] or stops
    if len(fresh) == len(stops):
        shown.clear()
    stop = min(fresh, key=lambda s: abs(s[0] - here[0]) + abs(s[1] - here[1]))
    shown.add(stop)
    return stop


# Population ledger: every birth and death, kept across runs (delete the file on a new game).
# Iron Teeth only grow through pods (5 days per kit) and live ~50 days, so holding steady
# takes about beavers/10 running pods; the founders die young, so the early game needs more.
LEDGER = Path(__file__).with_name("cache") / "pop-ledger.json"


def update_ledger(alerts):
    events = json.loads(LEDGER.read_text()) if LEDGER.exists() else []
    known = {(e["cycle"], e["day"], e["text"]) for e in events}
    for a in alerts:
        text = a["text"]
        kind = "born" if "was born" in text else "died" if (" died" in text or "starved" in text) else None
        if kind and (a["cycle"], a["day"], text) not in known:
            cause = "" if kind != "died" else "starvation" if "starved" in text else \
                text.split(" died", 1)[1].strip(" .").removeprefix("of ")
            events.append({"cycle": a["cycle"], "day": a["day"], "kind": kind, "cause": cause, "text": text})
            known.add((a["cycle"], a["day"], text))
    LEDGER.parent.mkdir(exist_ok=True)
    LEDGER.write_text(json.dumps(events, indent=0))
    return events


def ledger_report(events, cycle, beavers, buildings):
    def tally(evs):
        born = sum(e["kind"] == "born" for e in evs)
        died = [e["cause"] or "?" for e in evs if e["kind"] == "died"]
        causes = {c: died.count(c) for c in set(died)}
        return born, len(died), causes
    lines = []
    for label, evs in ((f"c{cycle}", [e for e in events if e["cycle"] == cycle]),
                       (f"c{cycle - 1}", [e for e in events if e["cycle"] == cycle - 1]),
                       ("run", events)):
        born, died, causes = tally(evs)
        lines.append(f"{label}: +{born} -{died} {causes if causes else ''}".strip())
    pods = [b for b in buildings if b["template"].startswith("BreedingPod") and b["finished"]]
    running = sum(1 for b in pods if "Paused." not in (b.get("statuses") or []))
    need = max(3, math.ceil(beavers / 10) + 1)  # never below 3: old founders die off in the first cycles
    print("LEDGER", " | ".join(lines), f"| pods {running}/{len(pods)} running, break-even+growth ~{need}")
    recent = [e for e in events if e["cycle"] >= cycle - 1]
    born, died, _ = tally(recent)
    if died > born or running < need:
        print(f"POPULATION AT RISK: {born} born vs {died} died since c{cycle - 1}; "
              f"{running} pods running, want >= {need}. Add pods (10 logs) + beds before other builds.")


def power_state(b, buildings):
    """'linked', 'waiting' (a construction site will meet one of its power points) or 'unlinked'.
    None for buildings without power points. Mutual test: my point is their tile and theirs is mine."""
    links = b.get("powerConnections")
    if not links:
        return None
    if any(l.get("connected") for l in links):
        return "linked"
    mine = {(l["x"], l["y"], l["z"]): tuple(l["from"]) for l in links}
    for s in buildings:
        if s["finished"] or s["id"] == b["id"]:
            continue
        for p in s.get("powerConnections") or []:
            if tuple(p["from"]) in mine and mine[tuple(p["from"])] == (p["x"], p["y"], p["z"]):
                return f"{s['template']} at ({s['x']},{s['y']}) {int((s.get('buildProgress') or 0) * 100)}%"
    return "unlinked"


def food_total(goods):
    return sum(goods[g]["available"] for g in FOOD if g in goods)


def main():
    if "--say" in sys.argv:
        i = sys.argv.index("--say")
        note = t.narrate(sys.argv[i + 1])
        if note != "shown":
            print("SAY:", note)
        del sys.argv[i:i + 2]
    max_seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 90
    speed = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    # Optional: comma-separated checks to ignore this run, e.g. "food,water" while a known shortage plays out.
    ignore = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else set()
    colony, goods, needs, buildings = snapshot()
    alerts = json.loads(t.get_alerts())
    last_alert = alerts["latest"]
    events = update_ledger(alerts["alerts"])
    births = []  # with "births" ignored, newborns are listed in the report instead of stopping
    weather = colony["weather"]["state"]
    unfinished = {b["id"] for b in buildings if not b["finished"]}
    # Finished power buildings not yet linked, re-checked every loop until their partner is built.
    power_watch = {b["id"] for b in buildings if b["finished"] and power_state(b, buildings) not in (None, "linked", "unlinked")}
    power_waiting = set()
    beavers = colony["population"]["adults"] + colony["population"]["children"]
    t.set_speed(speed)
    start = time.time()
    reasons = []
    last_pan, shown = time.time(), set()
    camera = json.loads(t.get_camera())
    here = (camera["x"], camera["y"])
    while time.time() - start < max_seconds and not reasons:
        time.sleep(2)
        colony, goods, needs, buildings = snapshot()
        new_alerts = json.loads(t.get_alerts(last_alert))
        if new_alerts["alerts"]:
            last_alert = new_alerts["latest"]
            events = update_ledger(new_alerts["alerts"])
            for a in new_alerts["alerts"]:
                text = a["text"]
                if "was born" in text and "births" in ignore:
                    births.append(text.split(" was born")[0])
                elif "grew up" not in text:
                    reasons.append(f"alert: {text}")
        if colony["weather"]["state"] != weather:
            reasons.append(f"weather -> {colony['weather']}")
        crit = [n["need"] for n in needs if n["critical"] > 0]
        if crit and "critical" not in ignore:
            reasons.append(f"critical needs: {crit}")
        finished_now = [b["template"] for b in buildings if b["id"] in unfinished and b["finished"]
                        and not b["template"].startswith(("Path", "GathererFlag", "LumberjackFlag", "PowerShaft",
                                                          "Shrub", "Stairs", "Platform", "Levee"))]
        for b in buildings:
            # Housekeeping: new tanks only ever hold water in this colony.
            if b["id"] in unfinished and b["finished"] and b["template"].startswith(("SmallTank", "MediumTank")):
                t.building_action(b["id"], "SingleGoodAllower", "Allow", ["Water"])
                print("auto: tank at", b["x"], b["y"], "-> Water")
            # Farmers default to planting first, which leaves ripe crops unharvested.
            if b["id"] in unfinished and b["finished"] and b["template"].startswith("FarmHouse"):
                t.building_action(b["id"], "FarmHouse", "UnprioritizePlanting", [])
                print("auto: farmhouse at", b["x"], b["y"], "-> harvest first")
            # Power users must touch the network; a Fermenter once sat with no power source.
            if b["id"] in unfinished and b["finished"] and power_state(b, buildings) not in (None, "linked"):
                power_watch.add(b["id"])
        for b in buildings:
            if b["id"] not in power_watch:
                continue
            state = power_state(b, buildings)
            if state == "linked":
                power_watch.discard(b["id"])
                print("power: linked", b["template"], b["x"], b["y"])
            elif state == "unlinked":
                power_watch.discard(b["id"])
                reasons.append(f"NO POWER LINK: {b['template']} at ({b['x']},{b['y']},{b['z']}), "
                               "nothing built or being built at its power points")
            elif b["id"] not in power_waiting:
                power_waiting.add(b["id"])
                print("power: waiting on a site", b["template"], b["x"], b["y"], "->", state)
        power_watch &= {b["id"] for b in buildings}
        unfinished = {b["id"] for b in buildings if not b["finished"]}
        stops = tour_stops(buildings)
        if stops and time.time() - last_pan >= CAMERA_EVERY:
            last_pan = time.time()
            camera = json.loads(t.get_camera())
            here = (camera["x"], camera["y"])
            if not any(abs(s[0] - here[0]) <= IN_VIEW and abs(s[1] - here[1]) <= IN_VIEW for s in stops):
                here = next_stop(stops, here, shown)
                # Vary the shot per pan (user: use zoom and angle), fixed until the next pan.
                zoom, h_angle, v_angle = SHOTS[len(shown) % len(SHOTS)]
                t.set_camera(x=here[0], y=here[1], zoom=zoom, horizontal_angle=h_angle, vertical_angle=v_angle)
        if finished_now:
            reasons.append(f"finished: {finished_now}")
        beavers = colony["population"]["adults"] + colony["population"]["children"]
        water = goods.get("Water", {}).get("available", 0)
        if water < beavers * 2 and "water" not in ignore:
            reasons.append(f"low water {water}")
        if food_total(goods) < beavers * 2 and "food" not in ignore:
            reasons.append(f"low food {food_total(goods)}")
    # Stream rule: the game keeps running while I decide; pause only for real emergencies.
    print("STOP:", "; ".join(reasons) or f"time limit {max_seconds}s")
    print("TIME", colony["time"], "WEATHER", colony["weather"])
    if births:
        print("BORN", births)
    ledger_report(events, colony["time"]["cycle"], beavers, buildings)
    p = colony["population"]
    print("POP", f"{p['adults']}a {p['children']}k homeless={p['homeless']} unemployed={p['unemployed']} "
                 f"freeJobs={p['freeWorkslots']} freeBeds={p['freeBeds']} sci={colony['science']} wb={colony['wellbeing']}")
    print("GOODS", {k: f"{v['available']}/{v['capacity']}" for k, v in goods.items()})
    # Food in days of eating (~3 per beaver per day). Under 3 days is an emergency at any time.
    days = food_total(goods) / max(1, 3 * beavers)
    print(f"FOOD DAYS {days:.1f}" + ("  <-- BELOW 3: pause pods, staff farms, food first" if days < 3 else ""))
    # Production stalls silently when a good has nowhere to go (e.g. planks before a Plank pile exists).
    full = [k for k, v in goods.items() if v["total"] >= v["capacity"] * 0.95]
    if full:
        print("STORAGE FULL (add storage or it stalls):", full)
    print("NEEDS", {n["need"]: (n["average"], n["critical"], n["warning"]) for n in needs})
    sites = [(b["template"].split(".")[0], b.get("buildProgress"), b.get("statuses")) for b in buildings
             if not b["finished"]]
    if sites:
        print("SITES", sites)
    line = poll_line()
    if line:
        print(line)
    # Open user requests (harness/pending.txt, one per line; delete a line when it's done) so none get dropped.
    pending = Path(__file__).with_name("pending.txt")
    if pending.exists():
        for req in filter(None, map(str.strip, pending.read_text(encoding="utf-8").splitlines())):
            print("PENDING", req)
    # Daily job/building checklist (plan v4 section 5), incl. building statuses; only always-safe fixes.
    for line in audit(colony, buildings):
        print("AUDIT", line)
    # Foreman (python -m foreman serve), when running: its findings and the next validated masterplan steps.
    # Printed after AUDIT, never instead of it.
    for line in foreman_lines():
        print("FOREMAN", line)


def foreman_lines(top=6):
    """Findings and NEXT sections of Foreman's briefing; nothing if the service is not running (read-only)."""
    import os
    import urllib.request
    url = os.environ.get("FOREMAN_URL", "http://127.0.0.1:8097") + f"/api/briefing?top={top}"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            text = r.read().decode("utf-8")
    except Exception:
        return []
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("FINDINGS")), len(lines))
    return lines[start:]


if __name__ == "__main__":
    main()
