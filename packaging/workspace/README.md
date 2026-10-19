# TimberLive

Let your AI play Timberborn: Claude (or another frontier model) plays through a game mod, with an advisor that checks its moves and an optional streaming kit for YouTube.

The TimberLive app sets everything up. It doesn't play itself: your AI does, with the tools in this folder.

## What you need
- Windows 10 or 11. Windows 11 already has the WebView2 runtime the app window uses. On Windows 10, if the window stays blank, install it from https://developer.microsoft.com/microsoft-edge/webview2/.
- Timberborn on Steam.
- An AI that can use MCP tools: Claude Code (best), Claude Desktop, or any other MCP client.
- For streaming (optional): OBS Studio and a YouTube Data API key.

## Getting started
1. Open **TimberLive** from the Start menu and work down the four steps on the Home page:
   1. **Timberborn:** found automatically through Steam.
   2. **Bridge mod:** click *Install mod*. It goes into `Documents\Timberborn\Mods`.
   3. **Game running:** start Timberborn, enable *TimberLive Bridge* in the Mod manager, and load or start a game.
   4. **Connect your AI:** see below.
2. Keep the app open while you play. It runs the advisor (Foreman) and the stream overlay.

## Connecting your AI
On the app's **Connect your AI** page:
- **Claude Code:** click *Set up workspace*, then *Open Claude Code here* (or open this folder in VS Code). Approve the two project MCP servers, `timberlive` and `foreman`, when asked. Claude Code can also run the harness scripts, which makes it the strongest player.
- **Claude Desktop:** click *Add to Claude Desktop* and restart it. Your old config is backed up first.
- **Anything else:** copy the JSON snippet into your client's MCP settings. If the client can run commands, open this folder in it and tell it to read `AGENTS.md`.

Then send a first message such as:

> Read AGENTS.md, then check the game with the timberlive ping tool and tell me what you see. Stay paused until I say go.

The AI stays paused and plans its opening until you say go.

## Streaming (optional)
On the **Stream** page:
- **Overlay:** add `http://127.0.0.1:8096/` to OBS as a 1920x1080 browser source. It shows the AI's thoughts, its plan and a ticker.
- **OBS:** *Make the scene collection*, then import it in OBS (Scene Collection > Import). Enable OBS's WebSocket server (Tools > WebSocket Server Settings) so the AI can switch slates.
- **Polls:** save a YouTube Data API key and your channel id. Viewers vote by typing an option's number in chat. Only vote counts reach the AI, never chat text. The key stays on this PC and is never shown again or given to the AI.

## What's in this folder
| Folder | What it is |
|---|---|
| `AGENTS.md`, `CLAUDE.md` | The AI's playbook |
| `knowledge/` | Game notes the AI reads: buildings, systems, water engineering and lessons from earlier games |
| `harness/` | The `timberlive` tool server and the AI's scripts (watch loop, map survey, opening planner, checkpoints) |
| `foreman/` | The advisor: it watches the game, checks the rules and suggests exact calls, but never acts |
| `overlay/`, `chatpoll/` | Stream overlay and poll counter |
| `app/` | This app |
| `runtime/` | The app's private Python. Everything here runs on it, so nothing else needs installing |
| `mod-dist/` | The bridge mod the app installs |

## Safety
- **The mod** only listens on `127.0.0.1`, and every request needs a token that is new each launch.
- **Player tools only:** the AI does only what a player could do from the toolbar or a building panel.
- **Chat:** viewer chat text never reaches the AI.

## Experimental
The **Experimental** page runs a local model (Ollama, LM Studio, vLLM) on the same tools, for testing. Use a new game or a throwaway save for live runs.

## Uninstalling
Use *Apps > Installed apps > TimberLive*. This removes the whole install folder, including the AI's checkpoints and any notes it added to `knowledge/`, so copy those first if you want to keep them. Your settings in `%LOCALAPPDATA%\TimberLive` and the mod in `Documents\Timberborn\Mods` stay. Delete them by hand if you want them gone.

Updating (running a newer installer over this one) keeps `knowledge/goals.md` and `knowledge/08-lessons-next-playthrough.md`, which the AI writes to as it plays.
