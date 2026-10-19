using System.Collections;
using System.Collections.Generic;
using System.Linq;
using TimberLive.Bridge.Core;
using Timberborn.CameraSystem;
using Timberborn.Coordinates;
using Timberborn.EntitySystem;
using Timberborn.LevelVisibilitySystem;
using Timberborn.TemplateSystem;
using Timberborn.WorkSystem;
using UnityEngine;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>
  /// Stream camera. By default every action that targets map coordinates pans the
  /// camera smoothly to it, so viewers always see what the agent is doing.
  /// Other modules call <see cref="Focus(IEnumerable{Vector3Int})"/>.
  /// </summary>
  [BridgeModule("Game")]
  public class CameraModule : IBridgeModule, System.IDisposable {

    // Slow, gentle pans: fast camera jumps make stream viewers motion sick.
    private const float PanSeconds = 2.5f;

    private static CameraModule _current;
    private static bool _follow = true;

    private readonly CameraService _cameraService;
    private readonly EntityComponentRegistry _entityComponentRegistry;
    private readonly ILevelVisibilityService _levelVisibilityService;
    private Coroutine _pan;
    private Coroutine _orbit;
    private float _orbitSpeed;

    public CameraModule(CameraService cameraService, EntityComponentRegistry entityComponentRegistry,
                        ILevelVisibilityService levelVisibilityService) {
      _cameraService = cameraService;
      _entityComponentRegistry = entityComponentRegistry;
      _levelVisibilityService = levelVisibilityService;
      _current = this;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("GET", "/api/camera", "Camera target, zoom, angles and follow mode", GetCamera);
      yield return new Route("POST", "/api/camera",
                             "Move camera {x,y,z?, zoom?, horizontalAngle?, verticalAngle?, follow?, "
                             + "orbit? (degrees per second, 0 stops)}", SetCamera);
      yield return new Route("GET", "/api/camera/working-beavers",
                             "Where employed beavers are doing their job right now (for the stream camera)",
                             WorkingBeavers);
      yield return new Route("POST", "/api/camera/layers",
                             "The player's layer slider: hide everything above {level}, or {reset:true}", SetLayers);
    }

    /// <summary>Pans to the centre of the given grid coordinates if follow mode is on.</summary>
    public static void Focus(IEnumerable<Vector3Int> coordinates) {
      var list = coordinates?.ToList();
      if (!_follow || _current == null || list == null || list.Count == 0) {
        return;
      }
      var centre = new Vector3((float) list.Average(c => c.x) + 0.5f,
                               (float) list.Average(c => c.y) + 0.5f,
                               (float) list.Average(c => c.z));
      _current.PanTo(centre);
    }

    public static void Focus(Vector3Int coordinates) {
      Focus(new[] { coordinates });
    }

    public void Dispose() {
      ScreenshotTaker.StopRunning(_pan);
      ScreenshotTaker.StopRunning(_orbit);
      if (_current == this) {
        _current = null;
      }
    }

    private void PanTo(Vector3 gridTarget) {
      ScreenshotTaker.StopRunning(_pan);
      _pan = ScreenshotTaker.RunCoroutine(Pan(CoordinateSystem.GridToWorld(gridTarget)));
    }

    private IEnumerator Pan(Vector3 worldTarget) {
      var start = _cameraService.Target;
      var elapsed = 0f;
      while (elapsed < PanSeconds) {
        elapsed += Time.unscaledDeltaTime;
        var t = Mathf.SmoothStep(0f, 1f, elapsed / PanSeconds);
        _cameraService.MoveTargetTo(Vector3.Lerp(start, worldTarget, t));
        yield return null;
      }
      _cameraService.MoveTargetTo(worldTarget);
    }

    private object GetCamera(BridgeRequest request) {
      var grid = CoordinateSystem.WorldToGrid(_cameraService.Target);
      return new {
          x = Mathf.RoundToInt(grid.x), y = Mathf.RoundToInt(grid.y), z = Mathf.RoundToInt(grid.z),
          zoom = _cameraService.ZoomLevel,
          horizontalAngle = _cameraService.HorizontalAngle,
          verticalAngle = _cameraService.VerticalAngle,
          follow = _follow,
          orbit = _orbitSpeed,
          maxVisibleLevel = _levelVisibilityService.MaxVisibleLevel,
      };
    }

    private object SetCamera(BridgeRequest request) {
      _follow = request.Get("follow", _follow);
      var zoom = request.Get<float?>("zoom");
      if (zoom.HasValue) {
        _cameraService.ZoomLevel = zoom.Value;
      }
      var horizontal = request.Get<float?>("horizontalAngle");
      if (horizontal.HasValue) {
        _cameraService.HorizontalAngle = horizontal.Value;
      }
      var vertical = request.Get<float?>("verticalAngle");
      if (vertical.HasValue) {
        _cameraService.VerticalAngle = vertical.Value;
      }
      var x = request.Get<int?>("x");
      var y = request.Get<int?>("y");
      if (x.HasValue && y.HasValue) {
        var z = request.Get("z", Mathf.RoundToInt(CoordinateSystem.WorldToGrid(_cameraService.Target).z));
        PanTo(new Vector3(x.Value + 0.5f, y.Value + 0.5f, z));
      }
      var orbit = request.Get<float?>("orbit");
      if (orbit.HasValue) {
        _orbitSpeed = Mathf.Clamp(orbit.Value, -30f, 30f);
        ScreenshotTaker.StopRunning(_orbit);
        _orbit = _orbitSpeed != 0f ? ScreenshotTaker.RunCoroutine(Orbit()) : null;
      }
      return GetCamera(request);
    }

    // A slow, continuous turn around the camera target, smooth every frame.
    private IEnumerator Orbit() {
      while (true) {
        _cameraService.HorizontalAngle = Mathf.Repeat(_cameraService.HorizontalAngle
                                                      + _orbitSpeed * Time.unscaledDeltaTime, 360f);
        yield return null;
      }
    }

    private object WorkingBeavers(BridgeRequest request) {
      return _entityComponentRegistry.GetAll<Worker>()
          .Where(w => w.Employed && w.JobRunning)
          .Select(w => {
            var grid = CoordinateSystem.WorldToGrid(w.Transform.position);
            return new {
                x = Mathf.FloorToInt(grid.x), y = Mathf.FloorToInt(grid.y), z = Mathf.FloorToInt(grid.z),
                workplace = w.Workplace.GetComponent<TemplateSpec>()?.TemplateName,
            };
          })
          .ToList();
    }

    private object SetLayers(BridgeRequest request) {
      if (request.Get("reset", false)) {
        _levelVisibilityService.ResetMaxVisibleLevel();
      } else {
        _levelVisibilityService.SetMaxVisibleLevel(request.Require<int>("level"));
      }
      return new { ok = true, maxVisibleLevel = _levelVisibilityService.MaxVisibleLevel };
    }

  }
}
