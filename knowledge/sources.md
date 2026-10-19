# Sources

## Local ground truth (this install, v1.1.2.7-2c14458-xsw)
- `C:\Program Files (x86)\Steam\steamapps\common\Timberborn\Timberborn_Data\StreamingAssets\Version.txt`: version string.
- `...\StreamingAssets\Modding\Blueprints.zip`: all building, good, need, recipe, crop, difficulty and config blueprints (JSON). This is where every [bp] number comes from. Extractor: `knowledge/_tools/extract_blueprints.py`.
- Blueprint folders used for `09`–`11`: `Buildings/*` (both factions), `MapEditor/Objects`, `MapEditor/Ruins`, `MapEditor/Water` (Slope, Blockage, NaturalDam, NaturalOverhang, Thorns, Relics, UnstableCore, GeothermalField, UndergroundRuins, RuinColumn, Reserve stores, Aquifer, sources, seeps, BadtideDrain), `NaturalResources/*`, `Needs/*`, `NeedCollections/*`, `Goods/*`, `Recipes/*`, `WellbeingTiers`, `Characters/*` (BeaverAdult, BeaverChild, Bots), `NewGameModes`, `TemplateCollections`, and `Configurations/*` (WaterSimulator, WaterStrength, SoilMoistureSimulator, SoilMoistureMap, SoilContaminationSimulator, SoilContaminationMap, ProbabilityGroups, LifeService, MigrationCoordinator, WindService, GameSpeedThrottler, TickTime, DayStageCycle, MapSize, ZiplineConnectionService, ZiplineCableNavMesh, Autosaver).
- `harness/` map survey (`SurveyModule.cs`, `map_summary`): which natural objects the bridge detects.
- `...\StreamingAssets\Modding\Localizations.zip` (`enUS.csv`): display names, descriptions, UI strings [loc].
- `...\StreamingAssets\HttpApi\*.hbs`: built-in HTTP API cheat-sheet page templates.
- `_decompiled\src\` (ILSpy output of `Timberborn.*.dll`) [code]. Key namespaces:
  - Timberborn.HttpApiSystem (HttpApi, HttpLeverJsonEndpoint, HttpAdaptersJsonEndpoint, HttpAdapter, HttpWebhookCaller, HttpApiIntermediary)
  - Timberborn.HttpApiSystemUI (HttpApiFragment: Start API button and port)
  - Timberborn.Automation (Automatable, AutomationRunner, Automator)
  - Timberborn.AutomationBuildings (sensors, Relay, Timer, Memory, WeatherStation, ResourceCounter, PopulationCounter, PowerMeter, Chronometer, Gate, Detonator, Indicator, PausableBuildingTerminal)
  - Timberborn.WaterBuildings (Floodgate, FillValve, ThrottlingValve)
  - Timberborn.WaterSourceSystem (WaterSourceRegulator)
  - Timberborn.PowerManagement (Clutch)
  - Timberborn.HazardousWeatherSystem (durations, badtide chance)
  - Timberborn.GameFactionSystem (NeedModificationService)
  - Timberborn.Wellbeing (tiers)
  - Timberborn.Reproduction (ProcreationHouse 18.75%/day, BreedingPod)
  - Timberborn.BeaverContaminationSystem (5% threshold, 3-day incubation)
  - Timberborn.WaterWorkshops (pump efficiency = 1 − contamination)
  - Timberborn.GameOver (GameOverChecker)
  - Timberborn.Characters (GameSpeedThrottler)
  - Timberborn.TimeSystem (SpeedManager)
  - Timberborn.TimeSystemUI (SpeedControlPanel)

## Web
Reliability: the official wiki and Steam patch notes are high. Steam guides and threads are medium, with dates noted. timberborn.org, whisperofthehouse.com, treyexgaming, vortexgaming and 5gamers read like AI aggregators and are **low** (they contain factual errors). reddit couldn't be fetched.

### Official
- Steam News API (full patch-note text, 2024-11 → 2026-10-08): https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1062090 ; https://store.steampowered.com/news/app/1062090
- 1.1 announcement: https://steamcommunity.com/games/1062090/announcements/detail/713408417186711420/
- GOG release notes: https://www.gogdb.org/product/1711765822/releasenotes

### Official wiki (timberborn.wiki.gg/wiki/…)
- Versions and mechanics: Version_1, Version_1.1, Update_5, Update_6, Update_7, Functional_Update_History, Difficulty, Game_Mode, Weather, Drought, Badtide, Badwater, Badtide_Drain, Contamination, Evaporation, Irrigation, Plants, Barriers, Water_Source, Time, Key_Binding
- Beavers: Beavers, Needs, Hunger, Thirst, Kit, Well-Being, Injury
- Factions and housing: Folktails, Iron_Teeth, Housing, Lodge, Breeding_Pod, Advanced_Breeding_Pod
- Water buildings: Water_Pump, Deep_Water_Pump, Large_Water_Pump, Mechanical_Pump, Tanks, Medium_Tank, Fluid_Dump, Discharge, Aquifer_Drill, Water_Wheel
- Food and production: Food, Crops, Trees, Farmhouse, Efficient_Farmhouse, Kohlrabi, Carrot, Gristmill, Grill, Fermenter, Hydroponic_Garden, Inventor, Science
- Logistics: Storage, Buildings, District_Center, Hauling_Post, Builders'_Hut
- Structures: Levee, Dam, Platform, Stairs, Floodgate, Double_Floodgate, Triple_Floodgate, Sluice, Fill_Valve, Throttling_Valve, Badwater_Dome, Dynamite, Double_Dynamite, Triple_Dynamite
- Misc buildings: Forester, Wind_Turbine, Gear_Workshop, Medical_Bed, Campfire
- Wonders and starting: Wonders, Earth_Recultivator, Starting_Timberborn, New_Game
- Automation: Automation, Lever, Relay, Timer, Memory, Depth_Sensor, Flow_Sensor, Contamination_Sensor, Weather_Station, Resource_Counter, Population_Counter, Science_Counter, Power_Meter, Chronometer, Indicator, Speaker, Clutch, Gate, Detonator, HTTP_API, HTTP_Adapter, HTTP_Lever
- Base URL pattern: https://timberborn.wiki.gg/wiki/<Page>

### Steam community
- Food & Water Planning Guide (1.0, Apr 2026): https://steamcommunity.com/sharedfiles/filedetails/?id=3696284505
- Iron Teeth guide (2021, outdated): https://steamcommunity.com/sharedfiles/filedetails/?id=2615052120
- Discussion threads, under https://steamcommunity.com/app/1062090/discussions/0/<id>/ :
  - Strategy:
    - 4635988093614163486 (Nov 2024 strategy)
    - 4703539060904129233
    - 4349990463680544078 (breeding)
    - 5362100320218997383 (reservoir depth)
    - 3825287408052775690
  - Water and automation:
    - 805719856669398945 (floodgate automation)
    - 837250603130385305 (valves)
    - 564786459586997240 (weather station)
    - 804596162400160535 (resource counter)
    - 804595355558684252
    - 4330763833483683939 (irrigation / evaporation)
    - 4703538708010047279 (sluice)
    - 599647681450617558
    - 4146194424445376378 (water wheels)

### Other
- Unstable Core blast effects (destroys buildings, terrain, water and trees in radius): https://2upskill.com/timberborn-unstable-cores-guide-2026-how-to-mine-defuse-and-survive-the-blast/ (low–medium; its title says "defuse", but the blueprint marks the core not demolishable).
- https://www.gamedeveloper.com/design/deep-dive-timberborn-s-water-mechanics
- https://notes.hamatti.org/Gaming/Video-games/Timberborn---Automated-local-pond-water-pump
- https://laughingmeme.org/2026/03/15/timberborn-1-0-http-lever-and-claude-code.html
- https://github.com/Agroqirax/timberborn-hass ; https://github.com/Agroqirax/timberborn-http ; https://github.com/joshhallick6-glitch/timberborn-dashboard ; https://github.com/abix-/TimberbornMods
- https://timberborn.io/ (third party)
- https://www.gamepressure.com/newsroom/timberborn-water-wheel-not-working-fix-produce-power-once-again/z65188
- Feature request: https://timberborn.featureupvote.com/suggestions/703388/extend-the-http-api-to-cover-all-automation-components-readings
- https://en.wikipedia.org/wiki/Timberborn
- Low confidence:
  - https://timberborn.org/articles/automation-guide
  - https://timberborn.org/articles/early-game-strategy
  - https://timberborn.org/articles/science-unlock-guide
  - https://timberborn.org/wiki/automation-components/http-adapter
  - https://www.whisperofthehouse.com/timberborn/dam-levee-floodgate-guide
  - https://www.whisperofthehouse.com/timberborn/first-drought-guide
  - https://www.whisperofthehouse.com/timberborn/beginner-guide
  - https://www.treyexgaming.com/timberborn-1-0-automation-guide/
  - https://vortexgaming.io/en/postdetail/715111
  - https://5gamers.com/en/timberborn/guides/automation
  - https://www.thegamer.com/timberborn-complete-guide-to-automation-resource-management-lever-tracker-sensor/

## Known wiki vs. build-1.1.2.7 blueprint conflicts (blueprint wins)
- Natural Dam height: wiki 0.5 vs **0.65** (same as a built Dam)
- Weather Station SP 150 (wiki page) vs **300**
- Memory 100 vs **1000**
- Badwater Dome 1000 SP vs **2000**
- Science Counter planks vs **6 Gear**
- Builders' Hut 400 SP vs **100**
- Hydroponic Garden 5 vs **10 Metal Parts**
- Mechanical Pump page (2500 SP) vs **2000 SP, 50 Gear 15 TreatedPlank, 500 power**
- HTTP Adapter webhook methods: community says GET/POST/PUT; the code enum is **GET/POST only**
