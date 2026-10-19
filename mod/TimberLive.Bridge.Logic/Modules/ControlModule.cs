using System;
using System.Collections.Generic;
using System.Linq;
using TimberLive.Bridge.Core;
using Timberborn.GameSaveRepositorySystem;
using Timberborn.GameSaveRuntimeSystem;
using Timberborn.SettlementNameSystem;
using Timberborn.TimeSystem;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>Game speed and saving. Only the player's speeds (0, 1, 3, 7) are allowed.</summary>
  [BridgeModule("Game")]
  public class ControlModule : IBridgeModule {

    private static readonly float[] PlayerSpeeds = { 0f, 1f, 3f, 7f };

    private readonly SpeedManager _speedManager;
    private readonly GameSaver _gameSaver;
    private readonly SettlementReferenceService _settlementReferenceService;

    public ControlModule(SpeedManager speedManager, GameSaver gameSaver,
                         SettlementReferenceService settlementReferenceService) {
      _speedManager = speedManager;
      _gameSaver = gameSaver;
      _settlementReferenceService = settlementReferenceService;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("POST", "/api/speed", "Set game speed {speed: 0|1|3|7}", SetSpeed);
      yield return new Route("POST", "/api/save", "Save the game {name}", Save);
    }

    private object SetSpeed(BridgeRequest request) {
      var speed = request.Require<float>("speed");
      if (!PlayerSpeeds.Contains(speed)) {
        throw new BridgeException(400, "speed must be one of 0, 1, 3, 7");
      }
      // SpeedManager applies the change on its next LateUpdate.
      _speedManager.ChangeSpeed(speed);
      return new { speed, previous = _speedManager.CurrentSpeed };
    }

    private object Save(BridgeRequest request) {
      var name = request.Get("name", "TimberLive " + DateTime.Now.ToString("yyyy-MM-dd HH-mm-ss"));
      var saveReference = new SaveReference(name, _settlementReferenceService.SettlementReference);
      _gameSaver.QueueSave(saveReference, () => { });
      return new { ok = true, queued = saveReference.ToString() };
    }

  }

  /// <summary>Screenshots, available in every context.</summary>
  [BridgeModule("MainMenu", "Game")]
  public class ScreenshotModule : IBridgeModule {

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("GET", "/api/screenshot",
                             "JPEG ?width=1280&quality=75&mode=auto|screen|camera (camera = world only, no UI)",
                             request => ScreenshotTaker.Capture(request.Get("width", 1280),
                                                                request.Get("quality", 75),
                                                                request.Get("mode", "auto")));
    }

  }
}
