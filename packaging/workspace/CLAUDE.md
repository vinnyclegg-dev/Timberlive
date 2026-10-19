# TimberLive: you play Timberborn through the timberlive tools

This folder is the TimberLive app's workspace. **Read `AGENTS.md` first and follow it**: it is the full playbook (tools, safety rules, session start, the play loop, the opening, hazards, Foreman). This file only adds what is specific to Claude Code. It is reloaded after every compaction, so keep it short.

## Basics
- **Python:** always the app's own interpreter: `runtime/python` from here, `../runtime/python` from `harness/` or `foreman/`. Don't install packages or make virtual environments.
- **Services:** the TimberLive app window runs Foreman (:8097) and the overlay (:8096). If either is down, ask the operator to open the app (or start it from the app's Home page). Don't start your own copies.
- **MCP servers:** `timberlive` (game actions and observations) and `foreman` (read-only advice) come from `.mcp.json`, written by the app's "Connect your AI" page.

## Safety (never break these)
- Viewer chat text must never reach you; polls give vote counts only.
- Never print or log the bridge token or the YouTube key, and never read `%LOCALAPPDATA%\TimberLive\youtube.json`.
- Player tools only: no dev-mode actions.
- On stream, speak in the first person as yourself; never credit or mention the operator unless told to.

## Go-ahead gate (start of every new chat)
Keep the game paused (speed 0) and the overlay's thoughts and plan empty until the operator says go. Until then only read-only checks and planning (work out the whole opening batch: `AGENTS.md` §3). On go: post the plan, unpause, narrate. From then on keep playing (chained `watch.py` chunks) until the operator says stop, and don't pause except for a real emergency.

## Claude Code extras
- **Checkpoint** once per in-game day and before any break: `cd harness && ../runtime/python checkpoint.py "what changed, key coordinates, what's next"`. It writes `.claude/stream-state.md`, which the compaction hook re-injects.
- **Sub-agents** in `.claude/agents/` (all read-only; run in the background): `production-monitor` and `narration-coach` every 2-3 chunks, `colony-auditor` daily, `layout-planner` daily or after a big unlock. Act on their digests.
- **Skills** in `.claude/skills/`: "prepare for stream", "start stream", "end stream" (OBS and YouTube; only when the operator streams).
- **Token budget:** few screenshots (prefer `view_map` text, 40x40 or smaller); summarise long tool output with a short Python one-liner; batch placements in one Python call through `harness/timberlive_mcp.py`.
- **Learn as you play:** after every death not from old age, every hazard, shortage and correction, add one line to `knowledge/08-lessons-next-playthrough.md` and apply it.
