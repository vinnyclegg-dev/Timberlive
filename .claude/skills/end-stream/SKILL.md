---
name: end-stream
description: TimberLive stream command "end stream" / "time to stop" (optionally "give it a minute"). Pauses Timberborn, shows the "Thanks for watching" slate, saves and exits the game, waits, ends the YouTube stream and closes OBS. Use whenever the user asks to wrap up, end or stop the stream, or types /end-stream.
---

# End stream

All commands run from `harness/` with `../runtime/python`. The user's request is the permission to end; never end a stream otherwise.

## 1. Pause and say goodbye
- `set_speed(0)`.
- `narrate` one friendly closing line: what got done, what's next time, thanks for watching.
- `checkpoint.py "..."` with the state, key coordinates and the opening plan for next time.

## 2. Thanks slate
`obs.py thanks`. Check that `showing` has `Slate: Thanks for watching` and `TimberLive overlay` (the main overlay always stays on) and not `Timberborn (game)`.

## 3. Save and exit the game
`python -c "import timberlive_mcp as t; print(t.save_and_quit('epN-end'))"` (N = episode). It saves, closes Timberborn and waits until the process is gone; it raises an error if the game doesn't exit.

## 4. Wait, end the stream, close OBS
- Wait as long as the user asked (default 1 minute): `wait_until.py +1m end-stream` in the background, then end the turn; the timer wakes you.
- `obs.py end-stream`; `live` must be false.
- `obs.py quit`; it must print `{"obsRunning": false}`. It refuses while live, so step order matters.

## 5. Report
One or two lines: saved as `epN-end`, game closed, stream ended after <liveFor>, OBS closed.
