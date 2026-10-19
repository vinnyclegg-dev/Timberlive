---
format: 1920x1080
duration: 47s
message: "Let your AI play Timberborn: it reads the map in 2D and 3D, and an advisor checks every move"
arc: Title → Real game → 3D map → 2D layers → Orbit vs slice → Advisor → App → End card
audience: GitHub visitors
mode: autonomous
---

## Frame 1 — Title
- src: compositions/s1-title.html
- duration: 4.5s
- transition_in: cut
- motion: blueprint titlecard-reveal
- status: animated

Icon, "TimberLive", "Let your AI play Timberborn." over the dimmed 3D orbit.

## Frame 2 — Real game
- src: compositions/s2-game.html
- duration: 6s
- transition_in: crossfade
- motion: rules viewport-change (slow push 1.0→1.08)
- status: animated

Two real stream shots, slow push and crossfade. "Your AI plays the real game through a mod."

## Frame 3 — 3D map
- src: compositions/s3-orbit.html
- duration: 8.5s
- transition_in: crossfade
- motion: rules spring-pop-entrance (legend chips), discrete-text-sequence
- status: animated

Full orbit video. "Foreman rebuilds the map in 3D." Legend chips for water, badwater, moist soil, dam sites.

## Frame 4 — 2D layers
- src: compositions/s4-layers.html
- duration: 8s
- transition_in: crossfade
- motion: blueprint grid-card-assemble
- status: animated

Four 2D layers assemble into a row with labels. "Every layer, in 2D."

## Frame 5 — Orbit vs slice
- src: compositions/s5-split.html
- duration: 6s
- transition_in: crossfade
- motion: blueprint comparison-split
- status: animated

Close orbit and height slicer side by side.

## Frame 6 — Advisor
- src: compositions/s6-foreman.html
- duration: 5.5s
- transition_in: crossfade
- motion: rules viewport-change
- status: animated

Foreman overview then water page. "An advisor checks every move." Read-only.

## Frame 7 — The app
- src: compositions/s7-app.html
- duration: 5s
- transition_in: crossfade
- motion: blueprint grid-card-assemble (cascade)
- status: animated

Three app windows cascade in. "One Windows app sets it all up."

## Frame 8 — End card
- src: compositions/s8-end.html
- duration: 3.5s
- transition_in: crossfade
- motion: blueprint titlecard-reveal
- status: animated

Icon, TimberLive, tagline, "Windows app · MCP tools · stream overlay".
