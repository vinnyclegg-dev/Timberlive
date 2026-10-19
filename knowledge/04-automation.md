# 04 — Automation system (v1.1.2.7)

Source key: **[code]** means the decompiled game assemblies in `_decompiled\src` (Timberborn.Automation, .AutomationBuildings, .HttpApiSystem, .WaterBuildings and others). **[bp]** means the game blueprints in `Timberborn_Data\StreamingAssets\Modding\Blueprints.zip`. **[loc]** means `Localizations.zip/enUS.csv`. **[web]** means sources.md. Code and blueprints are ground truth for this exact build. Web guides may describe older builds.

**History.**
- Automation shipped with **1.0, released 2026-03-12**.
- 1.1 went to the experimental branch on 2026-06-10 and to the main branch (1.1.2.4) on 2026-09-03. Changes in 1.1:
  - Relays went from 2 inputs to up to 8.
  - The Sluice was removed for good (old saves convert it to a Fill Valve).
  - The Duplicate tool no longer breaks automation settings.
  - Badwater Discharge was renamed Badwater Pressurizer.
  - New: Airlock, Compact Mechanical Pump, Impermeable Power Shaft and Tubeway.
  [web W-V1, W-V11, GOG]
- Wiki pages are partly stubs. Where the wiki and the blueprints disagree (Weather Station 150 vs **300** SP, Memory 100 vs **1000**, Badwater Dome 1000 vs **2000**, Science Counter planks vs **gears**), the blueprint value in this file is the one this build uses.
- Science unlocks for the HTTP buildings carry over across playthroughs (unverified for other unlocks) [W-HTTPL].

## 1. Core model

- **Signals are boolean.** Each automation output is On or Off. An input can also be **Disconnected** (nothing selected) [code `ConnectionState`].
- **Connections are wireless, with no range limit.** Every receiver ("terminal") has an input dropdown, or a "Select transmitter" picker tool, that lists every transmitter on the map by name [code `TransmitterDropdownProvider`, `AutomatorRegistry`]. You don't wire anything physically.
- **One input per actuator.** A normal building has exactly one automation input. Combine several conditions with a Relay first (up to 8 inputs, A–H).
- **Unfinished buildings output Off.** An actuator whose block isn't finished treats an On input as Off [code `Automatable.State`].
- **Evaluation runs per tick** (1 tick = 0.6 s at 1×; 32 ticks = 1 game hour; 768 ticks = 1 day) [bp TickTime, DayNightCycle].
  - Sensors and counters are *sampling* transmitters. They read the world once per tick.
  - Relays are *combinational*. They settle instantly within the tick.
  - Timer and Memory are *sequential*. They update on the tick commit, so each adds about 1 tick of latency [code `AutomationRunner`].
- **Loops get flagged.** A cycle made only of combinational parts (for example Relay A → Relay B → Relay A) raises the status "Automation loop" [loc]. To build feedback, put a Memory or Timer in the loop.
- **Naming.** Transmitters are auto-numbered ("Lever 1", etc.) and can be renamed. HTTP Levers and HTTP Adapters need a **unique** name, or they don't appear in the API [code `UniquelyNamedEntity`].
- **Reset.** Timer and Memory have a RST input plus "Reset" and "Reset circuit" buttons. Reset sets the state to Off and the counter to 0.
- **HUD.** Levers and Indicators can be **pinned** to the HUD. Pinned levers get hotkeys `PinnedLever1..10` [bp KeyBindings].

### What an actuator does with its input (exact semantics) [code]

| Actuator | Input **On** | Input **Off** | Disconnected |
|---|---|---|---|
| Any pausable building (workshops, pumps, farms, gatherers, etc., anything with `IFinishedPausable`) | runs | **paused** ("Paused by automation"). Outputs keep auto-emptying unless you paused it manually | runs (not blocked) |
| Floodgate / Double / Triple | gate moves to **Automation height** (default = MaxHeight, fully raised) | gate moves to normal **Height** | normal Height |
| Fill Valve (old "Sluice") | uses **Automation target height** (default enabled, offset 0 → effectively closed) | uses normal target height (default floor+0.5; can be "Unlimited") | normal |
| Throttling Valve (old "Valve") | uses **Automation flow limit** (default enabled, 0.0 → closed) | normal flow limit (default 1.0, max 2.0, step 0.01) | normal |
| Gate (path) in Automated mode | open | **closed** (beavers can't pass) | open |
| Clutch in Automated mode | engaged (power passes) | disengaged | disengaged |
| Badwater Dome / Badwater Pressurizer (WaterSourceRegulator) in Automated mode | source **open** (badwater flows) | closed (sealed) | closed |
| Detonator | rising edge **arms and triggers the dynamite underneath it** | — | — |
| Firework Launcher | fires while On | idle | idle |
| Indicator | lights up; optional warning, journal entry, HUD pin, colour replication | dark | dark |
| Speaker | plays the sound (once or looped) | silent / stops | silent |
| HTTP Adapter | API state `true`; fires the "switched on" webhook on an Off→On edge | `false`; fires the "switched off" webhook on an On→Off edge | — |

The wiki lists the automatable set as gates, floodgates, fill and throttling valves, all workplaces, **all housing**, and all power generators and consumers [W-AUTO]. In code this is everything with `IFinishedPausable` plus the special cases above. An automation pause behaves like a manual pause, so workers leave and reassign [STEAM-RC]. A Gate closing doesn't stop beavers already committed to a route through it [W-GATE].

Sensor placement rules [W-DEPTH, W-FLOW, W-CONT]:
- Depth and Contamination sensors read the column under the arm. They're blocked by impermeable floor, dirt, dams, floodgates, levees and valves. Readings over a dam or floodgate are unreliable, so put the arm over open water.
- The Flow sensor can sit inside streams and tunnels, and reads through dams, floodgates (if the arm is high enough), platforms and bridges. It doesn't read through levees, valves or floors.

Key consequence: **for pausable buildings, Off = paused.** To pause a building when some condition is TRUE, feed it the *inverse* (Relay NOT), or choose the opposite comparison in the sensor.

## 2. Components: cost, unlock, settings

Costs and science points (SP) are from [bp]. They're the same for both factions unless marked.

| Component | Cost | SP | Output / settings |
|---|---|---|---|
| **Lever** | 1 Plank, 2 Gear | 50 | Manual On/Off. Options: **Spring-return** (momentary pulse when switched on), **Pinned** (HUD button + hotkey). |
| **Relay** | 1 Plank, 1 Gear | 80 | Modes: **NOT** (1 input), **Passthrough** (1 input), **AND / OR / XOR** (2–8 inputs). Default inputs = 2. XOR = on when an odd number of inputs are on. NOT with nothing connected = On. |
| **Flow Sensor** | 6 Plank, 4 Gear | 100 | Measures water flow speed in the tile under its arm (1 tile in front). Comparison: > < ≥ ≤ = ≠ vs threshold 0.00–2.00 (precision 0.01, default 0). No water under the arm → Off. |
| **Chronometer** | 8 Plank, 6 Gear | 150 | Modes: **Time range** (start/end hour; wraps past midnight; default 0–16h), **Working hours**, **Non-working hours**. |
| **Depth Sensor** | 4 Gear, 8 ScrapMetal | 200 | Measures water surface height in the tile under its arm. Compare vs threshold (UI shows depth above floor; max = sensor z + 0.5). Default mode "Greater", default threshold = sensor z − 0.5. Dry tile → compares against the floor height. |
| **Population Counter** | 2 Plank, 2 Gear, 1 Paper (IT: 1 MetalPart) | 200 | Metric: total population, total beavers, adults, children, bots, occupied beds, free beds, homeless, jobs, employed, unemployed, vacancies, total workers, healthy workers, unhealthy workers, contaminated total/adults/children. Scope: **District** or **Global**. Toggles count beavers / bots. Compare vs integer threshold. |
| **Resource Counter** | 4 Plank, 4 Gear, 1 Paper (IT: 1 MetalPart) | 250 | Good + mode: **Quantity** (integer stock; "Include inputs" toggles AllStock vs AvailableStock) or **Percent (%)** fill rate of storage for that good. Compare vs threshold. **District-scoped:** it must connect to a district by path, otherwise it outputs Off. |
| **Science Counter** | 6 Gear, 4 ScrapMetal, 6 Paper (IT: 6 MetalPart) | 300 | Compare current SP vs threshold. |
| **Weather Station** | 10 Gear, 8 TreatedPlank | 300 | Mode: **Temperate / Drought / Badtide**. "Activate early" fires up to **72 h (3 days)** before the season starts. The current cycle's hazard type is decided at cycle start, so Drought mode never fires in a badtide cycle (and vice versa). Temperate mode = on from cycle start until the hazard begins (minus early hours). |
| **Indicator** | 2 ScrapMetal, 1 PineResin | 400 | Light. Options: Pinned (always / when on), Show warning when on, Add journal entry when on, Replicate input colour. |
| **Contamination Sensor** | 8 Gear, 8 MetalBlock | 400 | Water-column contamination (0–1, shown as %) under its arm. Default threshold 0.05 (5%), default mode Greater, precision 0.01. No water → Off. |
| **Speaker** | 4 Plank, 2 Gear, 4 MetalBlock | 500 | Sounds: Alarm, Buzz, Chime 1, Chime 2 (custom sounds loadable). Play once / continuously. Spatial / non-spatial. |
| **Power Meter** | 10 Gear, 6 MetalBlock | 600 | Network **Supply / Demand / Surplus** (integer hp) or **Battery charge** (%; default threshold 50%). |
| **Timer** | 1 TreatedPlank, 1 MetalBlock | 600 | Units: ticks / hours / days (default 1 h). Modes below. Has RST input. |
| **Firework Launcher** | 1 Gear, 2 TreatedPlank | 700 | Cosmetic. |
| **Memory** | 1 MetalBlock, 1 Extract | 1000 | Modes below. Inputs A, B, RST. |
| **Detonator** | 1 MetalBlock, 1 Explosives, 1 Extract | 1400 | Placed on top of Dynamite. On → detonates. Adjacent dynamites chain. |
| **HTTP Lever** | 2 Gear, 2 ScrapMetal | 5000 | Lever controlled through the HTTP API. |
| **HTTP Adapter** | 2 Gear, 4 ScrapMetal | 7500 | Exposes its input via the API and calls webhooks. |

Related automatable non-automation buildings [bp/code]:
- Floodgate (150 SP, 10 Log 5 Plank, max 1 m)
- Double Floodgate (250 SP, max 2 m)
- Triple Floodgate (500 SP, max 3 m)
- Fill Valve (300 SP, 5 Plank 5 MetalBlock)
- Throttling Valve (500 SP, 5 TreatedPlank 5 MetalBlock)
- Gate (200 SP, 6 Plank 4 Gear 4 ScrapMetal)
- Clutch (400 SP, 2 Gear 6 MetalBlock)
- Badwater Dome (FT, 2000 SP) and Badwater Pressurizer (IT, 4000 SP)
- Every pausable workplace

Timer modes [code `Timer.Evaluate*`] (T1 = interval A, T2 = interval B):
- **Delay**: output turns On after the input has been On for T1, and turns Off after the input has been Off for T2. Good for debounce and hysteresis-in-time.
- **Pulse**: on an input rising edge, outputs On for T1 (non-retriggerable while running).
- **Oscillator**: while the input is On, alternates On for T1 / Off for T2. Input Off → Off.
- **Accumulator**: counts ticks while the input is On (it doesn't reset when the input goes Off). Output latches On once the total reaches T1. Clear it with RST.
- **Random**: while the input is On, re-randomises (50/50) every T1.

Memory modes [code `Memory.EvaluateNext`]:
- **Set-Reset**: A sets, B resets, and **reset wins** if both are on. This is the hysteresis workhorse.
- **Toggle**: flips on each rising edge of A.
- **Latch**: while B is on, the output follows A. When B goes off, it holds.
- **Flip-flop**: on a rising edge of B, captures A.
- RST forces Off in every mode.

## 3. HTTP API (built-in) [code Timberborn.HttpApiSystem]

**Enabling it.** You can't enable it in the settings menu. Select any finished **HTTP Lever or HTTP Adapter** and press **"Start API"** in its panel. The port can be edited before starting (default **8080**; it's saved per save file only if it isn't 8080). The running state **isn't saved**: after every load, buildings show the status "API stopped" until you press Start again. If any adapter has a webhook URL that isn't loopback, a confirmation dialog ("I understand the risk") appears first. The panel has "Open browser" (cheat-sheet page) and shows the URL.

**Server details.**
- `HttpListener` on the prefix `http://localhost:{port}/`. It's localhost only, with **no auth**.
- The HTTP method isn't checked, so GET or POST both work.
- Responses are JSON (indented, `application/json`) or plain text.
- Unknown URL → 404 `Beaver says URL no exist.`
- Lever commands are queued and applied on the main thread on the next frame (`UpdateSingleton`), so a `switch-on` that returns `OK` takes effect within about one frame.

**Endpoints** (name = URL-escaped unique building name, e.g. `HTTP%20Lever%201`; trailing slash optional except on `color`):

| Path | Returns |
|---|---|
| `/` | HTML cheat-sheet listing all levers/adapters with On/Off/Red/Green buttons |
| `/api/levers` | `[{"name":"HTTP Lever 1","state":false,"springReturn":false}, ...]` |
| `/api/levers/{name}` | one lever object, or 404 `HttpLever not found: {name}` |
| `/api/switch-on/{name}` | `OK` (200); 404 if unknown |
| `/api/switch-off/{name}` | `OK` (200); 404 if unknown |
| `/api/color/{name}/{RRGGBB}` | sets the lever's light colour (6 hex digits, no `#`, **no trailing slash**); `Invalid color` 400 |
| `/api/adapters` | `[{"name":"HTTP Adapter 1","state":true}, ...]` |
| `/api/adapters/{name}` | one adapter object, or 404 `HttpAdapter not found: {name}` |

```bash
curl http://localhost:8080/api/levers
curl http://localhost:8080/api/switch-on/Drought%20Override
curl http://localhost:8080/api/adapters/Water%20Low
```

**HTTP Lever.**
- Behaves like a Lever. The lever's own On/Off is the signal, and other buildings select it as a transmitter.
- Spring-return HTTP levers produce a one-tick pulse on `switch-on`.
- The snapshot `state` refreshes whenever the automator state changes.

**HTTP Adapter (webhooks).**
- Takes one input. `state` in the JSON = input is On.
- Two URL fields: "Call when switched on" (default `http://localhost:8081/on/{name}`) and "Call when switched off" (default `http://localhost:8081/off/{name}`). Each has its own enable checkbox; **both are disabled by default**.
- Method: GET or POST (empty body). `{name}` is replaced by the URL-escaped adapter name.
- Edge-triggered only: Off→On fires the "on" URL, On→Off fires the "off" URL. There's no call at load or for the initial state.
- Calls go out from a background thread. Timeout 5 s. Queue max 100 pending calls; extra calls are dropped. Only http/https are allowed.
- **Failure handling:** a failed call clears the whole pending queue. The thread then sleeps 1 s (loopback) or 1/2/4/8/16/32 s exponential backoff per host (non-loopback).
- Non-loopback hosts are limited to **30 calls/min**.
- The panel shows Status OK / Error for the last on and off calls.

**What the API can't do (1.1.2.7).** It only exposes HTTP Levers and HTTP Adapters. It can't read stock, weather or buildings, can't place anything, and can't change speed. To read game state, wire a sensor → HTTP Adapter (one boolean per adapter). There's a feature request to extend this [web featureupvote]. TimberLive's own mod is the planned route for full state and control.

**Port conflicts.** If 8080 is busy (common), Start fails with an error dialog. Set a port in 50000–65535 in any HTTP building's panel; it applies to all of them [W-API]. Lever names are case-sensitive; letters and digits only avoids URL-encoding trouble. Remote access needs a tunnel or a mod, because the server binds to localhost only.

**Community tools** [web]:
- `Agroqirax/timberborn-http`: Python client, webhook receiver.
- `Agroqirax/timberborn-hass`: Home Assistant integration. It mentions PUT; the code supports **only GET/POST**.
- Web dashboards polling about every 2 s.
- A blog post wiring Claude Code hooks to `curl /api/switch-on/HTTP%20Lever%201` to launch fireworks [LAUGH].
- The "Timberbot" mod (port 8085) is a separate mod API, not vanilla.

**Polling pattern for an external agent.** Name adapters meaningfully ("Water<30%", "Drought", "Food<200", "Contaminated>5%") and poll `GET /api/adapters` every few seconds. Or run a tiny local server on port 8081 and enable webhooks, so the game pushes edges to you.

## 4. Cookbook (sensor → logic → actuator)

Notation: `X → Y` means Y's input = X.

1. **Close the reservoir at drought start** (keep the water you've stored).
   - Weather Station (Drought, *Activate early* 6–24 h) → reservoir outlet Floodgate (Automation height = max).
   - The gate rises before the drought and drops back to the normal height when it ends. For the badtide equivalent, use a second station in Badtide mode, both feeding a Relay OR.
2. **Seal intake during badtide or contamination.**
   - Contamination Sensor (arm over the inflow channel, "> 0.05") → Fill Valve or Throttling Valve on the intake (On = automation target 0 / flow 0 = closed).
   - Add Delay T2 = 6–12 h on the off-edge so it doesn't reopen on a brief clean blip: Sensor → Timer(Delay, T1 = 1 tick, T2 = 12 h) → valve.
3. **Pause producers when storage is full.**
   - Resource Counter (good = Plank, Percent, "< 90") → Lumber Mill. Off (≥ 90%) pauses the mill.
   - With hysteresis, so it doesn't flicker: Counter A "≤ 70%" → Memory(Set-Reset).A, Counter B "≥ 95%" → Memory.B, Memory → mill. The mill runs from 70% until 95%, then pauses until stock falls back to 70%.
4. **Pump only when the tank is low.** Resource Counter (Water, Quantity, "< 500") → Water Pump(s). This frees workers for other jobs when water is plentiful (pumps paused → workers re-assign).
5. **Drought rationing of workers.** Weather Station (Drought) → Relay NOT → non-essential workshops (paper, gears, decoration). They pause during the drought, freeing workers for haulers and food.
6. **Low-water alarm.**
   - Depth Sensor on the reservoir, "< 0.5 m" → Indicator (warning + journal + pinned) and Speaker (Alarm, once).
   - Or Resource Counter (Water, Quantity, "< 2.5 × beavers × days-left") → Indicator.
7. **Auto-refill a reservoir to a level.** Fill Valve with target height = desired level. No automation needed; it's a level-regulating one-way outlet. Add a contamination sensor → valve to stop badwater getting in (recipe 2).
8. **Floodgate level control (hysteresis).** Depth Sensor upstream "> 2.0" → Memory.A (set); second Depth Sensor "< 1.2" → Memory.B (reset); Memory → spill Floodgate (On = Automation height low = open spill). The gate releases water when it's high and closes when it's low.
9. **Power load shedding.** Power Meter (Battery charge, "< 20%") → Relay NOT → Clutch (Automated) on a non-critical power branch. Below 20% battery, that branch disengages.
10. **Night-only / day-only jobs.** Chronometer (Non-working hours) → Gate, for example to close a path at night. Chronometer (Working hours) → producers.
11. **Homeless or vacancies alarm.** Population Counter (Homeless, "> 0") → Indicator. Population Counter (Unemployed, "> 3") → Indicator ("build workplaces").
12. **Science gate.** Science Counter "≥ 5000" → Indicator ("can afford HTTP Lever").
13. **Contaminated beavers.** Population Counter (Contaminated total, "> 0", Global) → Indicator + Speaker. Pair it with Herbalist/antidote (FT) or Decontamination Pod (IT).
14. **Manual override for an agent or stream.**
    - HTTP Lever "Override" → Relay OR (with the automatic signal) → actuator. Force-on with `switch-on`.
    - For force-off: Relay AND(auto, NOT(override)).
15. **Report state to an external agent.** Any sensor or relay → HTTP Adapter named for the condition. Poll `/api/adapters`.
16. **Badwater dome on demand** (harvest badwater for extract/explosives without flooding the map). Resource Counter (Badwater, Quantity, "< 100") → Badwater Dome (Automated). The source opens only while the badwater stock is low and stays sealed otherwise. Keep a Badwater Pump next to the outflow. (Pattern inferred from the code; untested.)
17. **Blast on command.** HTTP Lever (spring-return) → Detonator on a dynamite chain, for remote terraforming. Safer still: Chronometer (time range 2–3 h) AND HTTP Lever → Detonator, so it blasts while beavers sleep [W-DET].
18. **Keep beavers out of badwater.** Weather Station (Badtide) OR Contamination Sensor ("> 0.05") → Relay NOT → Gate (Automated) on paths that wade through water [W-GATE].
19. **"Any hazard" signal.** Weather Station (Temperate) → Relay NOT. This is On during drought *and* badtide; one station instead of two [STEAM-CONF]. With early activation on the Temperate station, NOT(Temperate) turns on X hours early too, because Temperate mode turns off early.
20. **Breeding pod cap (IT).** Population Counter (Total beavers or Free beds, compare to your target) → Breeding Pods. When the cap is reached the pods pause, which saves water and berries [W-POP].
21. **Smart badtide diversion.** Contamination Sensor > 0.05 → intake Floodgate (Automation height = max, closed) and, through NOT, a bypass Floodgate (open), which dumps the bad water downstream past the town [W-CONT, TBORG-GUIDE].
22. **Logic clock.** Timer (Oscillator T1 = T2 = n h) → Memory (Flip-flop) gives a steady divide-by-2 clock, for example for rotating jobs [W-TIMER].

## 5. Gotchas

- An actuator only has one input. Build complex conditions in Relays.
- Off-means-paused also applies to *disconnected → not paused*. Deleting the source building disconnects the input, and paused buildings resume.
- A Resource Counter not reached by any path or district reads Off. Every pausable building fed by it then **pauses**. Put counters on a path inside the district.
- Weather Station Drought mode is Off during a badtide cycle. Use OR of both modes for "any hazard".
- Fill Valve and Throttling Valve automation defaults are "closed when On". Floodgate automation default is "max height when On". Check the slider before relying on a default.
- The HTTP API stops on load. Re-press Start API (or have the mod call `HttpApi.Start()`).
- Webhook failure clears all pending calls, so an edge can be lost. Treat polling `/api/adapters` as the source of truth.
