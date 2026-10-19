# Foreman

A read-only advisor for any AI playing Timberborn through the TimberLive harness. Foreman watches the game, checks every rule and suggests exact harness calls. **It never plays**: its bridge client has no write methods, and the AI makes every game action through the harness (MCP tools, `watch.py`, `h.py`).

## Setup

Foreman runs on the app's shared runtime (`runtime/`, built by `py -3.11 packaging/make_runtime.py`), which already has its packages and puts `foreman` on the path. The TimberLive app starts `serve` for you while its window is open.

## Use (from `foreman/`)

| Command | What it does |
|---|---|
| `../runtime/python -m foreman brief` | Collects once and prints the ~30-line briefing: time, weather, food/water days and reserves, ledger, stock, needs, power, batches, sites, top findings with fixes, open requests |
| `../runtime/python -m foreman findings [--json]` | Every current finding with its suggested harness call |
| `../runtime/python -m foreman collect` | Collector loop (fast 5 s, medium 30 s, slow 3 min) into `data/foreman.db` |
| `../runtime/python -m foreman rules` | Rulebook coverage: checked, waiting for a phase, conduct |
| `../runtime/python -m foreman pause-reason <id> "<reason>" --until "Log > 100 and weather == temperate"` | Log why a building is paused and when to resume; `bld.paused` then says when the condition is met (metrics: any good id, `food_days`, `water_days`, `beavers`, `cycle`, `day`, `weather`) |
| `../runtime/python -m foreman reset` | New game: clear the store |
| `../runtime/python -m foreman serve [--fixture FILE.json] [--port 8097]` | Web UI and JSON API on http://127.0.0.1:8097 (collects live, or serves a recorded fixture): Overview, Findings, Buildings, Supply, Map 2D/3D, Water, Plan, Requests, Rules. All GET except pure computations |

| `../runtime/python -m foreman plan [--regenerate [ZONE]] [--accept ZONE] [--reject ZONE] [--next N]` | Masterplan (`data/masterplan.json`): zones, staged steps with exact calls, and the next N steps validated against the live game |
| `../runtime/python -m foreman check '<harness call>' ...` | Validate harness calls before running them (exit 1 on a critical problem) |
| `../runtime/python mcp_server.py` | MCP server (stdio, stdlib only) over the running service: 12 `foreman_*` tools. Registered as `foreman` in `.mcp.json` |
| `runtime/python foreman/local_model_driver.py --model M` | Phase 6 test: a local model plays through the harness, guided by Foreman ([docs/foreman-local-model-test.md](../docs/foreman-local-model-test.md)) |

`--map-age SECS` reuses the stored map scan if it is younger (default 180 s).

## API (http://127.0.0.1:8097)

| Route | What it gives |
|---|---|
| `GET /api/briefing?top=8` | The text briefing (plain text), ending with NEXT masterplan steps |
| `GET /api/status`, `/api/overview`, `/api/findings`, `/api/buildings`, `/api/supply`, `/api/requests`, `/api/rules` | The UI pages' data |
| `GET /api/map`, `/api/map3d`, `/api/tile?x&y`, `/api/water` | Map grids (height, water, flow, speed, moisture, contamination, layered tiles), 3D columns, one tile, the water analysis (bodies, sources, dam options, pools, badwater) |
| `POST /api/validate` `{actions: [...], skip: [ids]}` | Checks harness calls before they run: footprint, door on a district road, unlocked, materials, plant tiles, storage good, water, power. Returns an id |
| `GET /api/verify/{id}` | After running a validated batch: each call's state (not placed, site N%, finished) with door, power-link and storage-good checks |
| `GET /api/masterplan`, `/api/suggestions?n=3` | The plan (generated on first call) and the next steps validated now |
| `GET /api/where?template&x&y&radius&good` | A clean spot near (x, y) plus the Path calls for its door, validated |
| `GET /api/plantable?x0&y0&x1&y1&plant&fx&fy&fz` | Which tiles can grow a plant, and the `h.safe_plant` call |
| `GET /api/dam?x0&y0&x1&y1` | Holds, leaks and cost for a straight dam/levee line you choose |
| `GET /api/events?since=SEQ&timeout=25` | Long-poll: findings opened and cleared, plus a tick each collection (replaces the planned WebSocket; no extra dependency) |

## Harness hooks

Foreman is optional: when it is down the harness behaves exactly as before.

- `h.py`: `foreman_check(actions)` runs before `safe_plant`, `place_on_path`, `place_near`, `place_with_route` and `place_scan` place anything. It prints problems only and never blocks.
- `plan_opening.py`: the whole opening batch is validated when shown and again before `--apply`.
- `watch.py`: prints the top `FOREMAN` findings after the AUDIT lines each chunk.

## Layout

- `foreman/bridge.py`: read-only bridge client (allowlist of read endpoints; `/api/place` only as `check: true`)
- `foreman/collector.py`: tiered polling into the SQLite store (`store.py`)
- `foreman/world.py`: 2.5D world model (grids, buildings, road graph + flood fill + single links, power networks)
- `foreman/findings.py`: Finding, `@monitor` registry, ranking
- `foreman/monitors/` (plain Python, no LLM):
  - `supply`: food days, water and food reserves, storage full, empty inputs, pumps per beaver, hazard countdown
  - `buildings`: jobs, storage goods, recipes, badwater pumps, power and power links, statuses, road links, farm split, stuck sites, science, paused register
  - `production`: batch progress with the reason, food processing, flooded buildings, build range, single road links, site materials
  - `population`: ledger, pods needed, beds, needs, old-age wave, medical beds
  - `land`: plantable patches, wrong plant marks, farm plots per house, trees and lumberjacks, dead and dying plants
  - `forecast`: stock trends, the hazard record, checks during a hazard
  - `progress`: one of every building, the material chain that gates the rest
  - `ops`: food crisis, hoarding, growth gate, priority tiers, workday, power shedding order, steam engine feed, pre-hazard checklist, game speed, tank capacity, support building caps
  - `stream`: thought age, plan, stale plan items, polls, requests, checkpoint, overlay/OBS health
  - `water`: underground assessment, dam proposals, pump pools, drought-proof power, flood risk, fields near held water, reservoirs, badwater
  - `plan`: opening checklist (pods by day 5, pumps and tanks, farmhouse first), wood, science order, the masterplan's drift
- `foreman/geometry.py`: footprints and rotation, doors, supports, store kinds, plants
- `foreman/hydro.py`: 3D water model: bodies, spills, sources, flood fills, pools, dam/levee proposals and custom lines
- `foreman/checker.py`: guards for `validate` and `verify`
- `foreman/masterplan.py`: zones and staged steps from the start, `Planner.find_spot`, suggestions
- `foreman/ui/`: plain JS pages; `vendor/` holds three.js r169 (MIT) for the 3D map; the 3D map carves caves and overhangs out of the ground, draws them see-through, and "go to caves" steps through them, biggest first
- `mcp_server.py`, `local_model_driver.py`: the any-AI interfaces (phase 6)
- `foreman/paused.py`: paused-building register (`data/paused.json`) with resume conditions
- `foreman/briefing.py`, `foreman/rules.yaml` + `rules.py`
- `tests/`: offline tests on a recorded save (`tests/record_fixture.py <name>` records one, read-only)

## Findings

`{rule, severity, message, entity, where, evidence, fix, runs}`. `fix` is the exact harness call, for example
`building_action(building_id="…", component="SingleGoodAllower", action="Allow", args=["Water"])`.
The AI decides whether to run it. `runs` counts how many collections in a row the finding has been open.
