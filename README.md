# TimberLive

**Let your AI play Timberborn.** Claude (or another frontier model) plays through a game mod and a set of MCP tools. A read-only advisor, Foreman, reads the map in 2D and 3D and checks every move. An optional streaming kit puts the AI's thoughts, its plan and viewer polls on a YouTube stream.

<p align="center"><img src="docs/images/map3d-rotate.gif" alt="Foreman's 3D model of a colony map, turning" width="720"></p>

TimberLive is one Windows app. It installs the mod, runs Foreman and the overlay, and connects your AI. It never plays itself: your AI does.

**Download:** [TimberLive-Setup from the latest release](https://github.com/vinnyclegg-dev/TimberLive/releases/latest) (Windows 10/11, 64-bit; Timberborn 1.1 or later on Steam). **Watch:** [the 44-second demo on YouTube](https://youtu.be/jxtYHLVLJY4).

## The map, as your AI sees it

Foreman rebuilds the map from the game: heights, water and badwater, moisture, roads, buildings, work ranges, and where to plant, cut and dam. Your AI gets the same data as text through the `foreman` tools. You get it here.

### 2D

| Terrain and water | Moisture and fields |
|---|---|
| ![Height shading with rivers, badwater and buildings](docs/images/map2d-terrain-water.png) | ![Moist soil and planting areas](docs/images/map2d-moisture-fields.png) |
| **Roads and findings** | **Work ranges** |
| ![Road network with Foreman's findings circled](docs/images/map2d-roads-findings.png) | ![The work range of the chosen building type](docs/images/map2d-work-range.png) |

### 3D

Blue is clean water and purple is badwater. Green soil is moist and pink soil is contaminated. Red lines are dam sites Foreman proposes. Drag to orbit, scroll to zoom, and slice the terrain by height to see what's under a cliff.

| Close orbit over the colony | Height slicer |
|---|---|
| ![Orbit over the colony](docs/images/map3d-colony-orbit.gif) | ![Slicing the terrain by height](docs/images/map3d-height-cut.gif) |

| | |
|---|---|
| ![Whole map](docs/images/map3d-overview.png) | ![Water, pools and dam proposals](docs/images/map3d-water-plans.png) |
| ![The colony up close](docs/images/map3d-colony-close.png) | ![The colony from another side](docs/images/map3d-colony-close-2.png) |

## Foreman, the advisor

Foreman watches the game, checks a rulebook (food and water days, hazard reserves, births against deaths, power, storage, idle jobs) and suggests the exact tool call for each fix. It has no write access to the game.

| Overview | Water |
|---|---|
| ![Foreman overview: time, food, water, population, needs, findings](docs/images/foreman-overview.png) | ![Water findings and dam proposals](docs/images/foreman-water.png) |
| **Map 2D** | **Map 3D** |
| ![The 2D map in the Foreman UI](docs/images/foreman-map2d.png) | ![The 3D map in the Foreman UI](docs/images/foreman-map3d.png) |

## The app

| Get ready to play | Connect your AI | Stream |
|---|---|---|
| ![Home: Timberborn, mod, game, AI, services](docs/images/app-home.png) | ![Claude Code, Claude Desktop or any MCP client](docs/images/app-connect.png) | ![Overlay, OBS and YouTube polls](docs/images/app-stream.png) |

1. **Timberborn** is found through Steam.
2. **Install mod** puts the TimberLive Bridge mod in `Documents\Timberborn\Mods`.
3. Start the game, enable the mod, and load a save or start a new game.
4. **Connect your AI:** set up a Claude Code workspace, add the tools to Claude Desktop, or copy the MCP config into any other client.

Then tell your AI to read `AGENTS.md` and check the game. It stays paused and plans its opening until you say go.

> **Iron Teeth only, for now.** TimberLive has been played and tested with the Iron Teeth faction. Folktails games may work, but the playbook and Foreman's checks are tuned for Iron Teeth (Breeding Pods, their buildings and needs) and haven't been verified on Folktails yet.

## What's inside

| Folder | What it is |
|---|---|
| `mod/` | TimberLive Bridge: a Timberborn mod with a local HTTP API (player actions only) |
| `harness/` | The `timberlive` MCP server and the AI's scripts: watch loop, map survey, opening planner, checkpoints |
| `foreman/` | The advisor: collector, rulebook, web UI, `foreman` MCP server ([README](foreman/README.md)) |
| `knowledge/`, `AGENTS.md` | The playbook and game notes the AI reads |
| `overlay/`, `chatpoll/` | Stream overlay (thoughts, plan, ticker) and the poll counter |
| `app/` | The Windows app (pywebview) |
| `packaging/` | Private Python runtime and the installer build ([README](packaging/README.md)) |

## Safety

- The mod listens on `127.0.0.1` only, and every request needs a token that changes each launch.
- The AI can only do what a player can do from the toolbar or a building panel.
- Viewer chat text never reaches the AI. Polls pass vote counts only.
- Your YouTube key stays on your PC and is never shown to the AI.

## Building

Needs Windows, Python 3.11, the .NET SDK and Inno Setup 6. See [packaging/README.md](packaging/README.md):

```
py -3.11 packaging/make_runtime.py
runtime/python packaging/build.py
```

The installer lands in `packaging/dist/`.

## License

[MIT](LICENSE): use, change and share it as you like. Timberborn, its art and the game footage in the screenshots and video belong to Mechanistry; TimberLive is a fan-made project and isn't affiliated with Mechanistry or Anthropic. The installer bundles Python and open-source packages under their own licenses.
