# YouTube video: TimberLive demo (44 s)

Video: `../renders/timberlive-github.mp4` (1920x1080, 30 fps, 44.5 s, silent).
Thumbnail: `thumbnail.png` (1280x720), from `thumbnail.html` over `bg-map3d.png` (Foreman's 3D map). Re-render it with headless Chrome at 1280x720.

Publishing (the MP4 goes up in Studio: API uploads from our unaudited Google Cloud project are locked to private):
1. YouTube Studio > Create > Upload videos > drop `timberlive-github.mp4`. Close the dialog once it starts (it stays private/draft, titled "timberlive-github").
2. `cd harness && ../runtime/python youtube_meta.py video --info ../media/github-video/youtube/video-info.md --thumbnail ../media/github-video/youtube/thumbnail.png` sets title, description, tags, category and thumbnail on that newest upload, keeping it private.
3. `../runtime/python youtube_meta.py verify --info ../media/github-video/youtube/video-info.md --id <videoId>` checks it.
4. Publish: rerun step 2 with `--privacy public` (or flip it in Studio).

## Title (pick one)
1. **Let Your AI Play Timberborn: Free Mod, 3D Map and AI Advisor 🦫 TimberLive** ← recommended
2. TimberLive: How Claude Plays Timberborn (Mod + MCP Tools + 3D Map)
3. I Gave an AI a Timberborn Mod and a 3D Map of the Colony 🦫

## Description

🦫 **TimberLive lets your AI play Timberborn.** It's the kit behind the "Claude plays Timberborn" streams on this channel, now packaged as one Windows app.

**What's in it**
🎮 **A game mod** that gives your AI player tools only: build, plant, dam, set priorities and explain every move. No cheats, no dev tools.
🔧 **MCP tools** so Claude, or another AI that supports MCP, can read the colony and act.
🗺️ **Foreman, a read-only advisor** that rebuilds the map in 2D and 3D: heights, rivers, badwater, moisture, roads, work ranges and proposed dam sites. It checks food and water days, births against deaths, power and storage, and suggests the exact fix. It never touches the game.
📺 **An optional streaming kit:** an overlay with the AI's thoughts and its plan, OBS control and viewer polls (only the vote counts reach the AI).

**How it works**
1. Install TimberLive and click **Install mod**.
2. Start Timberborn, enable the mod, and load a save or start a new game.
3. Connect your AI: a Claude Code workspace, Claude Desktop, or any MCP client.
4. Tell it to read the playbook and check the game. It stays paused and plans its opening until you say go.

⚠️ Tested with the Iron Teeth faction so far. Folktails support isn't verified yet.

⏱️ **In this video**
0:00 TimberLive
0:04 The AI plays the real game
0:09 The map in 3D
0:17 Every layer in 2D
0:25 Slicing the terrain by height
0:30 Foreman, the advisor
0:35 The app
0:40 Get it

🔗 Download and source code: https://github.com/vinnyclegg-dev/TimberLive
📺 Watch the AI play live: the "Claude Plays Timberborn" streams on this channel.

🎮 Game: Timberborn by Mechanistry
🤖 AI player: Claude by Anthropic
TimberLive is a fan-made project and isn't affiliated with Mechanistry or Anthropic.

#Timberborn #AI #Claude #MCP #Modding #CityBuilder

## Tags
Timberborn, Timberborn mod, Timberborn AI, Timberborn 3D map, TimberLive, Claude, Claude AI, Claude Code, Anthropic, MCP, Model Context Protocol, AI agent, AI plays games, AI plays Timberborn, AI gaming, game mod, city builder, colony sim, beaver game, Foreman advisor

## Studio settings (can't be set by the API)
- **Game title:** Timberborn.
- **Playlist:** add it to the "Claude Plays Timberborn" playlists, or a new "TimberLive" playlist.
- **Altered or synthetic content:** "No". The game footage and map views are real; the beaver mascot in the thumbnail is AI-made art, which is fine in a thumbnail.
- **Audience:** "No, it's not made for kids" (the tool sets this).
- **Sound:** the video is silent. Optionally add a track from the YouTube Audio Library in Studio's Editor.
