"""Sleep until a local clock time, then exit. Run it in the background so Claude is woken at that time.

    ../runtime/python wait_until.py 18:45 prepare-for-stream
    ../runtime/python wait_until.py +15m start-stream

The second argument is a label that is printed on exit, so the wake-up says what to run.
"""
import datetime as dt
import sys
import time


def target_time(spec: str) -> dt.datetime:
    now = dt.datetime.now()
    if spec.startswith("+"):
        n, unit = int(spec[1:-1]), spec[-1]
        return now + (dt.timedelta(minutes=n) if unit == "m" else dt.timedelta(hours=n))
    t = dt.datetime.strptime(spec, "%H:%M").time()
    when = dt.datetime.combine(now.date(), t)
    if when <= now:
        sys.exit(f"{spec} has already passed today ({now:%H:%M}); give a later time.")
    return when


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    when = target_time(sys.argv[1])
    label = sys.argv[2] if len(sys.argv) > 2 else "timer"
    print(f"waiting until {when:%H:%M:%S} for {label}", flush=True)
    while (left := (when - dt.datetime.now()).total_seconds()) > 0:
        time.sleep(min(left, 30))
    print(f"TIME UP {when:%H:%M} -> run {label} now", flush=True)


if __name__ == "__main__":
    main()
