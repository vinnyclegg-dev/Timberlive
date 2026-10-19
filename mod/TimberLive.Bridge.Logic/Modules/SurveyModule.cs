using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using TimberLive.Bridge.Core;
using Timberborn.BlockSystem;
using Timberborn.MapStateSystem;
using Timberborn.Navigation;
using Timberborn.SoilContaminationSystem;
using Timberborn.SoilMoistureSystem;
using Timberborn.TemplateSystem;
using Timberborn.TerrainSystem;
using Timberborn.WaterSystem;
using UnityEngine;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>
  /// Read-only map survey for planning. Unlike /api/map it never moves the camera,
  /// sees every terrain layer in a column (overhangs, caves, ground under ledges),
  /// lists natural map objects (slopes, natural dams, ruins, seeps...) and asks the
  /// game's own nav mesh whether places can be walked to.
  /// Grids are strings, one per row, from y=y0 (first) upwards; one char per tile,
  /// encoded with Code(): 0-9, a-z (10-35), A-Z (36-61).
  /// </summary>
  [BridgeModule("Game")]
  public class SurveyModule : IBridgeModule {

    private const int MaxArea = 64 * 64;
    private const int MaxTargets = 400;
    private const string Digits = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

    // Map-editor objects and connectors worth reporting by position.
    private static readonly string[] FeaturePrefixes = {
        "Slope", "Stairs", "SpiralStairs", "NaturalDam", "NaturalOverhang", "Blockage", "Thorns",
        "SmallRelic", "MediumRelic", "LargeRelic", "UnstableCore", "GeothermalField", "Reserve",
        "RuinColumn", "UndergroundRuins", "Aquifer", "AncientAquiferDrill", "BadtideDrain",
        "BadwaterSeep", "BadwaterSource", "WaterSeep", "WaterSource", "DistrictCenter", "Dam",
        "Levee", "Floodgate", "Platform", "Overhang", "Tubeway", "Zipline",
    };

    private readonly MapSize _mapSize;
    private readonly ITerrainService _terrainService;
    private readonly IThreadSafeWaterMap _waterMap;
    private readonly IBlockService _blockService;
    private readonly ISoilMoistureService _soilMoistureService;
    private readonly INavigationService _navigationService;
    private readonly ISoilContaminationService _soilContaminationService;

    public SurveyModule(MapSize mapSize, ITerrainService terrainService, IThreadSafeWaterMap waterMap,
                        IBlockService blockService, ISoilMoistureService soilMoistureService,
                        INavigationService navigationService,
                        ISoilContaminationService soilContaminationService) {
      _mapSize = mapSize;
      _terrainService = terrainService;
      _waterMap = waterMap;
      _blockService = blockService;
      _soilMoistureService = soilMoistureService;
      _navigationService = navigationService;
      _soilContaminationService = soilContaminationService;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("GET", "/api/map/columns",
                             "Survey grid ?x=&y=&w=&h= (max 64x64, no camera move): top height, every terrain "
                             + "layer per column, water depth/contamination/flow, moisture, objects, natural features",
                             GetColumns);
      yield return new Route("POST", "/api/map/reachable",
                             "Walking distance on the nav mesh {from:[x,y,z], targets:[[x,y,z],...]} "
                             + "(max 400); null = unreachable",
                             GetReachable);
    }

    private object GetColumns(BridgeRequest request) {
      var x0 = request.Require<int>("x");
      var y0 = request.Require<int>("y");
      var w = request.Get("w", 64);
      var h = request.Get("h", 64);
      var raw = request.Get("raw", false);
      if (w <= 0 || h <= 0 || w * h > MaxArea) {
        throw new BridgeException(400, $"Area must be positive and at most {MaxArea} tiles");
      }
      var flowMethod = _waterMap.GetType().GetMethod("WaterFlowDirection", new[] { typeof(Vector3Int) });
      var top = new List<string>();
      var water = new List<string>();
      var contamination = new List<string>();
      var flow = new List<string>();
      var speed = new List<string>();
      var moist = new List<string>();
      var objects = new List<string>();
      var legend = new Dictionary<string, char>();
      var layered = new List<object>();
      var features = new List<object>();
      var seen = new HashSet<BlockObject>();
      var rawColumns = raw ? new List<string>() : null;
      for (var y = y0; y < y0 + h; y++) {
        var topRow = new StringBuilder();
        var waterRow = new StringBuilder();
        var contaminationRow = new StringBuilder();
        var flowRow = new StringBuilder();
        var speedRow = new StringBuilder();
        var moistRow = new StringBuilder();
        var objectRow = new StringBuilder();
        for (var x = x0; x < x0 + w; x++) {
          if (!_terrainService.Contains(new Vector2Int(x, y))) {
            topRow.Append('.');
            waterRow.Append('.');
            contaminationRow.Append('.');
            flowRow.Append('.');
            speedRow.Append('.');
            moistRow.Append('.');
            objectRow.Append('.');
            continue;
          }
          var levels = StandingLevels(x, y);
          var surface = levels.Count > 0 ? levels[levels.Count - 1] : 0;
          var cell = new Vector3Int(x, y, surface);
          var depth = _waterMap.WaterDepth(cell);
          var dirty = depth > 0.05f ? _waterMap.ColumnContamination(cell) : 0f;
          var direction = depth > 0.05f && flowMethod != null
              ? (Vector2) flowMethod.Invoke(_waterMap, new object[] { cell }) : Vector2.zero;
          topRow.Append(Code(surface));
          waterRow.Append(depth < 0.05f ? ' ' : Code(Mathf.RoundToInt(depth * 10f)));
          contaminationRow.Append(depth < 0.05f ? ' ' : Code(Mathf.RoundToInt(dirty * 9f)));
          flowRow.Append(depth < 0.05f ? ' ' : FlowChar(direction));
          speedRow.Append(depth < 0.05f ? ' ' : Code(Mathf.RoundToInt(direction.magnitude * 10f)));
          moistRow.Append(depth > 0.05f ? 'w' : _soilContaminationService.SoilIsContaminated(cell) ? 'x'
              : _soilMoistureService.SoilIsMoist(cell) ? '#' : ' ');
          objectRow.Append(ObjectChar(cell, legend));
          if (levels.Count > 1) {
            layered.Add(new {
                x, y,
                levels = levels.Select(z => {
                  var at = new Vector3Int(x, y, z);
                  var headroom = _terrainService.TryGetDistanceToTerrainAbove(at, out var distance) ? distance : -1;
                  var bottom = _blockService.GetBottomObjectAt(at);
                  var levelDepth = _waterMap.WaterDepth(at);
                  return new object[] {
                      z, headroom, (float) Math.Round(levelDepth, 1),
                      bottom == null ? null : TemplateName(bottom),
                      levelDepth > 0.05f ? (float) Math.Round(_waterMap.ColumnContamination(at), 2) : 0f,
                  };
                }).ToList(),
            });
          }
          foreach (var z in levels) {
            CollectFeatures(new Vector3Int(x, y, z), features, seen);
          }
          if (raw) {
            var bits = new StringBuilder();
            for (var z = 0; z < _mapSize.TerrainSize.z; z++) {
              bits.Append(_terrainService.Underground(new Vector3Int(x, y, z)) ? '#' : '.');
            }
            rawColumns.Add($"{x},{y}: underground {bits} allHeights "
                           + string.Join(",", _terrainService.GetAllHeightsInCell(new Vector2Int(x, y))
                                                   .Select(v => v.z)));
          }
        }
        top.Add(topRow.ToString());
        water.Add(waterRow.ToString());
        contamination.Add(contaminationRow.ToString());
        flow.Add(flowRow.ToString());
        speed.Add(speedRow.ToString());
        moist.Add(moistRow.ToString());
        objects.Add(objectRow.ToString());
      }
      return new {
          origin = new { x = x0, y = y0, w, h },
          note = "Rows run from y=" + y0 + " (first) upwards; chars use 0-9 a-z A-Z for 0-61; '.' = off map",
          top,
          water, waterKey = "depth in tenths of a block (' ' = dry)",
          contamination, contaminationKey = "0-9 = share of badwater in ninths (' ' = dry)",
          flow, flowKey = "> east, < west, ^ north (+y), v south, o still",
          speed, speedKey = "flow speed x10",
          moist, moistKey = "# moist, x contaminated soil, w water, ' ' dry",
          objects, legend = legend.ToDictionary(kv => kv.Value.ToString(), kv => kv.Key),
          layered, layeredKey = "columns with more than one standing level: [z, headroom (-1 = open sky), "
                                + "water depth, bottom object, contamination 0-1]",
          features,
          raw = rawColumns,
      };
    }

    private object GetReachable(BridgeRequest request) {
      var from = request.Require<int[]>("from");
      var targets = request.Require<int[][]>("targets");
      if (from.Length != 3) {
        throw new BridgeException(400, "from must be [x, y, z]");
      }
      if (targets.Length > MaxTargets) {
        throw new BridgeException(400, $"At most {MaxTargets} targets");
      }
      var start = NavigationCoordinateSystem.GridToWorld(new Vector3Int(from[0], from[1], from[2]));
      var corners = new List<PathCorner>();
      var result = new List<object>();
      foreach (var t in targets) {
        if (t.Length != 3) {
          result.Add(null);
          continue;
        }
        var end = NavigationCoordinateSystem.GridToWorld(new Vector3Int(t[0], t[1], t[2]));
        corners.Clear();
        result.Add(_navigationService.FindPathUnlimitedRange(start, end, corners, out var distance)
            ? (object) (float) Math.Round(distance, 1) : null);
      }
      return new { from, startOnNavMesh = _navigationService.IsOnNavMesh(start), distances = result };
    }

    // Every height a beaver could stand on in this column, lowest first.
    private List<int> StandingLevels(int x, int y) {
      var levels = _terrainService.GetAllHeightsInCell(new Vector2Int(x, y)).Select(v => v.z).Distinct().ToList();
      var surface = _terrainService.GetTerrainHeightBelow(new Vector3Int(x, y, _mapSize.TotalSize.z - 1));
      if (!levels.Contains(surface)) {
        levels.Add(surface);
      }
      levels.Sort();
      return levels;
    }

    private void CollectFeatures(Vector3Int cell, List<object> features, HashSet<BlockObject> seen) {
      foreach (var blockObject in _blockService.GetObjectsAt(cell)) {
        if (!seen.Add(blockObject)) {
          continue;
        }
        var name = TemplateName(blockObject);
        if (!FeaturePrefixes.Any(p => name.StartsWith(p, StringComparison.Ordinal))) {
          continue;
        }
        features.Add(new {
            name,
            x = blockObject.Coordinates.x, y = blockObject.Coordinates.y, z = blockObject.Coordinates.z,
            orientation = (int) blockObject.Orientation,
            state = HazardState(blockObject),
        });
      }
    }

    private static readonly string[] HazardComponents = {
        "UnstableCore", "TimedComponentActivator", "WaterSource", "WaterSourceContamination",
    };

    /// <summary>Timers, radius and strength of cores and sources, read without the camera moving.</summary>
    private static Dictionary<string, object> HazardState(BlockObject blockObject) {
      var entity = blockObject.GetComponent<Timberborn.EntitySystem.EntityComponent>();
      if (entity == null) {
        return null;
      }
      var state = new Dictionary<string, object>();
      foreach (var component in entity.AllComponents) {
        var type = component.GetType();
        if (!HazardComponents.Contains(type.Name)) {
          continue;
        }
        foreach (var property in type.GetProperties(System.Reflection.BindingFlags.Public
                                                    | System.Reflection.BindingFlags.Instance
                                                    | System.Reflection.BindingFlags.DeclaredOnly)) {
          if (property.GetIndexParameters().Length > 0
              || !(property.PropertyType.IsPrimitive || property.PropertyType.IsEnum)) {
            continue;
          }
          try {
            var value = property.GetValue(component);
            state[type.Name + "." + property.Name] = value is float f ? (object) Math.Round(f, 3)
                : property.PropertyType.IsEnum ? value.ToString() : value;
          } catch (Exception) {
            // Some getters throw before the entity is fully initialised.
          }
        }
      }
      return state.Count > 0 ? state : null;
    }

    private static char Code(int value) {
      return Digits[Mathf.Clamp(value, 0, Digits.Length - 1)];
    }

    private static char FlowChar(Vector2 flow) {
      if (flow.sqrMagnitude < 0.0004f) {
        return 'o';
      }
      return Mathf.Abs(flow.x) >= Mathf.Abs(flow.y) ? (flow.x > 0 ? '>' : '<') : (flow.y > 0 ? '^' : 'v');
    }

    private char ObjectChar(Vector3Int cell, Dictionary<string, char> legend) {
      var blockObject = _blockService.GetBottomObjectAt(cell);
      if (blockObject == null) {
        return ' ';
      }
      var name = TemplateName(blockObject);
      if (!legend.TryGetValue(name, out var symbol)) {
        const string symbols = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#@$%&*+=?!<>^~";
        symbol = legend.Count < symbols.Length ? symbols[legend.Count] : '?';
        legend[name] = symbol;
      }
      return symbol;
    }

    private static string TemplateName(BlockObject blockObject) {
      var name = blockObject.GetComponent<TemplateSpec>()?.TemplateName ?? blockObject.Name;
      return blockObject.IsFinished ? name : name + " (unfinished)";
    }

  }
}
