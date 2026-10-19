---
name: start-stream
description: TimberLive stream command "start stream" (optionally "at 19:00" / "in 10 minutes"). Shows the game view and overlay in OBS, hides the "Starting soon" slate, unpauses Timberborn and starts playing. This is the go-ahead from CLAUDE.md's go-ahead gate. Use whenever the user types "start stream" or /start-stream.
---

# Start stream

All commands run from `harness/` with `../runtime/python`.

## 0. Timing (if the user gave a time)
Use the same rules as `prepare-for-stream` step 0:
- If both commands are in one message: prepare comes first, start is at least 5 minutes later, otherwise schedule neither and ask.
- "N minutes after going live": the timer is started by prepare-for-stream once it is live and paused (see its step 0), not now.
- Run `wait_until.py <time> start-stream` in the background, reply in one line, and end the turn. The timer wakes you.
- If the prepare timer fires first, finish preparing before you start.

## 1. Check that we're prepared
- `ping` must say `Game`, and `get_colony` should show speed 0. If the game isn't loaded, run prepare-for-stream steps 3-4 now.
- `obs.py status`. If `"live"` is false, run `obs.py go-live`: the user asked to start the stream.

## 2. Frame the first shot
Point the camera at the colony with `set_camera` (the district centre or the current build site, follow on), so the first thing viewers see is the town.

## 3. Swap OBS to the game
`obs.py game-view`. This shows `Timberborn (game)` and `TimberLive overlay` first, then hides every slate. Check that `showing` has the game and overlay and no `Slate:` items.

## 4. Go-ahead: unpause and play
This is the go-ahead from CLAUDE.md:
1. `set_plan` (8 items or fewer).
2. Narrate a friendly opening line (what's happening, what's first).
3. `set_speed(3)`, or 1 if something needs watching.
4. Run the play loop (`watch.py`) and never stop playing until the user says stop.
