---
name: prepare-for-stream
description: TimberLive stream command "prepare for stream" (optionally "at 18:45" / "in 10 minutes"). Puts the OBS "Starting soon" slate up with the game hidden, goes live in OBS, reloads the current Timberborn save and leaves it paused, resets the overlay texts, then waits for "start stream". Use whenever the user types "prepare for stream" or /prepare-for-stream, alone or together with "start stream".
---

# Prepare for stream

Goal: viewers see "Starting soon" while the game is reloaded and paused behind it. Nothing is played yet: the go-ahead gate in CLAUDE.md still applies (no narrate, set_plan, add_todo or speed above 0).

All commands run from `harness/` with `../runtime/python`.

## 0. Timing (if the user gave a time)
- Convert the time to `HH:MM` (24 h, local) or `+Nm` / `+Nh`.
- **If "start stream" was given in the same message,** both need times, prepare must come first, and start must be at least 5 minutes after prepare (a reload can take a few minutes). If the times are equal, in the wrong order, or closer than 5 minutes, schedule **neither**. Say why in one line and ask for new times.
- **"Start stream N minutes after going live"** (e.g. "prepare for stream, then start stream 2 minutes after going live"): no gap rule. Do prepare now (or at its time); only once step 2's `go-live` reports `"live": true` and the save is reloaded and paused, run `wait_until.py +Nm start-stream` in the background, reply in one line, and end the turn.
- Check now that things work, so problems surface early: `obs.py status` and `ping`.
- Run `wait_until.py <time> prepare-for-stream` with Bash `run_in_background: true` (and `wait_until.py <time> start-stream` for the start command). Note each task ID.
- Reply in one line: what is scheduled, and when. While waiting, only do read-only prep (session-start reading, opening plan in chat), then end the turn. The timer's exit wakes you; then do steps 1-5.
- If the user says "cancel", stop the wait task(s) with TaskStop.

## 1. OBS: Starting soon, game hidden
- `obs.py launch`: starts OBS with the TimberLive collection if it isn't running and checks 1080p30, the YouTube service and the sources. Fix any `problems` before going on. If `streamKeySet` is false, run `youtube_meta.py obs-key` (puts the channel's persistent key into OBS without printing it).
- **YouTube metadata** (if `media/epN/stream-info.md` exists for this episode): `youtube_meta.py prepare --info ../media/epN/stream-info.md --thumbnail ../media/epN/thumbnail.png`, then `youtube_meta.py verify --info ...` must say ok (tags can lag ~20 s; re-run verify once). Season 2 uses `media/s2eN/`. If the broadcast was set up early as private, add `--privacy public` so it goes public. If the token has expired, tell the user to run `youtube_meta.py auth` (one browser click) and carry on.

`obs.py starting-soon`. The output's `showing` must include `Slate: Starting soon` and `TimberLive overlay`, and must not include `Timberborn (game)`. The main overlay always stays on (user rule); only the slates and the game turn on and off.

## 2. OBS: go live
`obs.py go-live`. Check that `"live": true`. Twitch goes live with it: the obs-multi-rtmp plugin's Twitch target (profile `obs-multi-rtmp.json`) has sync-start/sync-stop on and shares the main encoder; check the OBS log's `[obs-multi-rtmp]` lines if Twitch doesn't show up. The user's command is the permission to go live. Never end a stream unless the user asks.

## 3. Reload the game and pause it
- `ping`.
  - **Game:** `save_game("pre-stream")`, then `load_save(most_recent=True)`. This reloads the level exactly where it was.
  - **MainMenu:** `load_save(most_recent=True)`.
  - **No answer (game closed):** start it with `"C:\Program Files (x86)\Steam\steam.exe" -applaunch 1062090 -skipModManager`. Poll `ping` until it answers, then `load_save(most_recent=True)`.
- Poll `ping` until the context is `Game`, then `set_speed(0)` right away. Confirm the speed is 0 with `get_colony`.

## 4. Overlay ready, texts reset
- `overlay_reset.py`: empties "What I'm thinking" and "The plan" and removes any old poll.
- `curl -s 127.0.0.1:8096/colony.json`. If the overlay server is down, start `overlay/start-overlay.cmd`.
- Keep the panels empty until start-stream (go-ahead gate).
- **Poll counter test** (needs the user at the Studio chat in Chrome, where Tampermonkey runs `chatpoll/timberlive-poll.user.js`): `start_poll("Test poll", ["Test A", "Test B"], 1)`, ask the user to type 1 in chat, check `poll_results()` shows 1 vote, then `close_poll(clear=True)`. The overlay is hidden behind the slate, so viewers don't see it. If no vote arrives, check the chat tab is open and Tampermonkey is on.

## 5. Report and wait
- Do the CLAUDE.md session-start reading if it isn't done yet, and have the opening plan ready in chat.
- Reply in one or two lines, e.g. "Live on Starting soon; game reloaded and paused at c3d18. Ready for start stream."
- If "start stream" is scheduled, end the turn and let its timer wake you. Otherwise wait for the user.
