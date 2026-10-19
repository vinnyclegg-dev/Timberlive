using System;
using System.Collections.Generic;
using System.Linq;
using TimberLive.Bridge.Core;
using Timberborn.FactionSystem;
using Timberborn.GameSaveRepositorySystem;
using Timberborn.GameSceneLoading;
using Timberborn.MapRepositorySystem;
using Timberborn.NewGameConfigurationSystem;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>Save listing, loading and new-game creation. Bound in MainMenu and Game.</summary>
  [BridgeModule("MainMenu", "Game")]
  public class SessionModule : IBridgeModule {

    private readonly GameSaveRepository _gameSaveRepository;
    private readonly GameSceneLoader _gameSceneLoader;
    private readonly MapRepository _mapRepository;
    private readonly FactionSpecService _factionSpecService;
    private readonly GameModeSpecService _gameModeSpecService;

    public SessionModule(GameSaveRepository gameSaveRepository,
                         GameSceneLoader gameSceneLoader,
                         MapRepository mapRepository,
                         FactionSpecService factionSpecService,
                         GameModeSpecService gameModeSpecService) {
      _gameSaveRepository = gameSaveRepository;
      _gameSceneLoader = gameSceneLoader;
      _mapRepository = mapRepository;
      _factionSpecService = factionSpecService;
      _gameModeSpecService = gameModeSpecService;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("GET", "/api/saves", "List settlements and their saves, newest first", ListSaves);
      yield return new Route("POST", "/api/load", "Load a save {settlement, save} or {mostRecent:true}", LoadSave);
      yield return new Route("GET", "/api/new-game/options", "Factions, maps and game modes for a new game",
                             NewGameOptions);
      yield return new Route("POST", "/api/new-game", "Start a new game {faction, map, mode, settlementName}",
                             NewGame);
      yield return new Route("GET", "/api/maps/file",
                             "Raw .timber map file as base64 ?name=&builtin=true|false (read-only, for map research)",
                             MapFile);
    }

    private object MapFile(BridgeRequest request) {
      var name = request.Require<string>("name");
      var builtin = request.Get("builtin", true);
      var reference = builtin ? MapFileReference.FromResource(name) : MapFileReference.FromUserFolder(name);
      using (var stream = _mapRepository.OpenMap(reference))
      using (var memory = new System.IO.MemoryStream()) {
        stream.CopyTo(memory);
        return new { name, builtin, bytes = memory.Length, base64 = Convert.ToBase64String(memory.ToArray()) };
      }
    }

    private object ListSaves(BridgeRequest request) {
      var limit = request.Get("limit", 10);
      return _gameSaveRepository.GetAllSettlements()
          .Select(settlement => new {
              settlement = settlement.SettlementName,
              saves = _gameSaveRepository.GetSaves(settlement)
                  .OrderByDescending(_gameSaveRepository.GetSaveLastWriteTime)
                  .Take(limit)
                  .Select(save => new {
                      save = save.SaveName,
                      modified = _gameSaveRepository.GetSaveLastWriteTime(save).ToString("u"),
                  })
                  .ToList(),
          })
          .OrderByDescending(s => s.saves.FirstOrDefault()?.modified)
          .ToList();
    }

    private object LoadSave(BridgeRequest request) {
      SaveReference saveReference;
      if (request.Get("mostRecent", false)) {
        saveReference = _gameSaveRepository.GetMostRecentSave()
                        ?? throw new BridgeException(404, "No saves found");
      } else {
        var settlementName = request.Require<string>("settlement");
        var saveName = request.Require<string>("save");
        var settlement = _gameSaveRepository.GetAllSettlements()
                             .FirstOrDefault(s => s.SettlementName == settlementName)
                         ?? throw new BridgeException(404, $"Settlement '{settlementName}' not found");
        saveReference = _gameSaveRepository.GetSaves(settlement).FirstOrDefault(s => s.SaveName == saveName)
                        ?? throw new BridgeException(404, $"Save '{saveName}' not found");
      }
      _gameSceneLoader.StartSaveGame(saveReference);
      return new { ok = true, loading = saveReference.ToString() };
    }

    private object NewGameOptions(BridgeRequest request) {
      return new {
          factions = _factionSpecService.Factions.Select(f => new { id = f.Id, name = f.DisplayName.Value }),
          builtinMaps = _mapRepository.GetBuiltinMapNames(),
          userMaps = _mapRepository.GetUserMapNames(),
          modes = _gameModeSpecService.GetSpecsOrdered().Select(m => new {
              id = m.DisplayNameLocKey,
              isDefault = m.IsDefault,
              m.StartingAdults,
              m.StartingChildren,
              m.StartingFood,
              m.StartingWater,
              m.FoodConsumption,
              m.WaterConsumption,
          }),
      };
    }

    private object NewGame(BridgeRequest request) {
      var factionId = request.Require<string>("faction");
      if (_factionSpecService.Factions.All(f => f.Id != factionId)) {
        throw new BridgeException(400, $"Unknown faction '{factionId}'");
      }
      var mapName = request.Require<string>("map");
      MapFileReference map;
      if (_mapRepository.GetBuiltinMapNames().Contains(mapName)) {
        map = MapFileReference.FromResource(mapName);
      } else if (_mapRepository.GetUserMapNames().Contains(mapName)) {
        map = MapFileReference.FromUserFolder(mapName);
      } else {
        throw new BridgeException(400, $"Unknown map '{mapName}'");
      }
      var modeId = request.Get<string>("mode");
      var mode = modeId == null
          ? _gameModeSpecService.GetDefaultSpec()
          : _gameModeSpecService.GetSpecsOrdered().FirstOrDefault(m => m.DisplayNameLocKey == modeId)
            ?? throw new BridgeException(400, $"Unknown mode '{modeId}'");
      var settlementName = request.Get("settlementName", "TimberLive " + DateTime.Now.ToString("yyyy-MM-dd HHmm"));
      _gameSceneLoader.StartNewGame(new NewGameConfiguration(factionId, map, mode, settlementName));
      return new { ok = true, faction = factionId, map = mapName, mode = mode.DisplayNameLocKey, settlementName };
    }

  }
}
