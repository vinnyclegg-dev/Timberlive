"""Monitor event feed: one line each time the newest overlay thought gets older than LIMIT seconds, and a
PLAN CHECK line every PLAN_EVERY seconds (run the narration-coach agent, then fix the on-stream plan).
Usage: python thought_watchdog.py [limit_secs=100] [plan_every_secs=420]"""
import json, sys, time, urllib.request

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 100
PLAN_EVERY = int(sys.argv[2]) if len(sys.argv) > 2 else 420
warned_for = None
next_plan = time.time() + PLAN_EVERY
while True:
    try:
        s = json.loads(urllib.request.urlopen("http://127.0.0.1:8096/state.json", timeout=5).read())
        th = (s.get("thoughts") or [{}])[-1]
        at = th.get("at", 0)
        age = time.time() - at
        if age > LIMIT and warned_for != at:
            print(f"THOUGHT DUE: last overlay thought {int(age)}s ago - narrate now", flush=True)
            warned_for = at
        if time.time() > next_plan:
            todos = [x.get("text") for x in (s.get("todos") or []) if not x.get("done")]
            print(f"PLAN CHECK: run narration-coach; open plan items: {todos}", flush=True)
            next_plan = time.time() + PLAN_EVERY
    except Exception as e:
        print(f"watchdog error {e}", flush=True)
        time.sleep(60)
    time.sleep(15)
