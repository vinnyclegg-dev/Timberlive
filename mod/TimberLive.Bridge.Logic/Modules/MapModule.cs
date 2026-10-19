using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using TimberLive.Bridge.Core;
using Timberborn.BlockSystem;
using Timberborn.MapStateSystem;
using Timberborn.SoilMoistureSystem;
using Timberborn.SoilContaminationSystem;
using Timberborn.TemplateSystem;
using Timberborn.TerrainSystem;
using Timberborn.Demolishing;
using Timberborn.EntitySystem;
using Timberborn.Planting;
using Timberborn.Growing;
using Timberborn.Gathering;
using Timberborn.NaturalResourcesLifecycle;
using Timberborn.Yielding;
using Timberborn.WaterSourceSystem;
using Timberborn.WaterSystem;
using UnityEngine;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>
  /// Compact map views for planning: surface height, water depth, contamination
  /// and what occupies each surface tile. Rows run from high y (north) to low y.
  /// </summary>
  [BridgeModule("Game")]
  public class MapModule : IBridgeModule {

    private const int MaxArea = 64 * 64;

    private readonly MapSize _mapSize;
    private readonly ITerrainService _terrainService;
    private readonly IThreadSafeWaterMap _waterMap;
    private readonly IBlockService _blockService;
    private readonly EntityComponentRegistry _entityComponentRegistry;
    private readonly ISoilMoistureService _soilMoistureService;
    private readonly PlantingService _plantingService;
    private readonly ISoilContaminationService _soilContaminationService;

    public MapModule(MapSize mapSize, ITerrainService terrainService, IThreadSafeWaterMap waterMap,
                     IBlockService blockService, EntityComponentRegistry entityComponentRegistry,
                     ISoilMoistureService soilMoistureService, PlantingService plantingService,
                     ISoilContaminationService soilContaminationService) {
      _soilContaminationService = soilContaminationService;
      _plantingService = plantingService;
      _entityComponentRegistry = entityComponentRegistry;
      _soilMoistureService = soilMoistureService;
      _mapSize = mapSize;
      _terrainService = terrainService;
      _waterMap = waterMap;
      _blockService = blockService;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("GET", "/api/map/size", "Map dimensions", GetSize);
      yield return new Route("GET", "/api/map",
                             "Area grid ?x=&y=&w=&h= (max 64x64): height, water, contamination, objects",
                             GetArea);
      yield return new Route("GET", "/api/map/water-sources",
                             "Every water/badwater source: centre, size, strength, contamination", GetWaterSources);
      yield return new Route("GET", "/api/map/plants",
                             "Plant growth summary per type in ?x=&y=&w=&h=: grown, growing, dying, dead, ripe yield",
                             GetPlants);
      yield return new Route("POST", "/api/map/demolish-resources",
                             "Player's Demolish resources tool: mark (or {unmark:true}) plants in {x0,y0,x1,y1} "
                             + "for builders to remove; marking also clears planting marks there",
                             DemolishResources);
      yield return new Route("GET", "/api/map/tile", "Everything stacked at one column ?x=&y=", GetTile);
    }

    // Same as the toolbar's Demolish resources / Cancel tools: builders walk over and remove what is marked.
    private object DemolishResources(BridgeRequest request) {
      var x0 = request.Require<int>("x0");
      var y0 = request.Require<int>("y0");
      var x1 = request.Require<int>("x1");
      var y1 = request.Require<int>("y1");
      var unmark = request.Get("unmark", false);
      if ((Math.Abs(x1 - x0) + 1) * (Math.Abs(y1 - y0) + 1) > MaxArea) {
        throw new BridgeException(400, $"Area must be at most {MaxArea} tiles");
      }
      var changed = new List<object>();
      for (var y = Math.Min(y0, y1); y <= Math.Max(y0, y1); y++) {
        for (var x = Math.Min(x0, x1); x <= Math.Max(x0, x1); x++) {
          if (!_terrainService.Contains(new Vector2Int(x, y))) {
            continue;
          }
          var coordinates = new Vector3Int(x, y, SurfaceHeight(x, y));
          foreach (var blockObject in _blockService.GetObjectsAt(coordinates).ToList()) {
            var demolishable = blockObject.GetComponent<Demolishable>();
            if (demolishable == null || demolishable.IsMarked != unmark) {
              continue;
            }
            if (unmark) {
              demolishable.Unmark();
            } else {
              demolishable.Mark();
            }
            changed.Add(new { x, y, template = TemplateName(blockObject) });
          }
          if (!unmark) {
            _plantingService.UnsetPlantingCoordinates(coordinates);
          }
        }
      }
      CameraModule.Focus(new Vector3Int((x0 + x1) / 2, (y0 + y1) / 2, SurfaceHeight((x0 + x1) / 2, (y0 + y1) / 2)));
      return new { ok = true, marked = unmark ? 0 : changed.Count, unmarked = unmark ? changed.Count : 0, objects = changed };
    }

    private object GetPlants(BridgeRequest request) {
      var x0 = request.Require<int>("x");
      var y0 = request.Require<int>("y");
      var w = request.Require<int>("w");
      var h = request.Require<int>("h");
      if (w <= 0 || h <= 0 || w * h > MaxArea) {
        throw new BridgeException(400, $"Area must be positive and at most {MaxArea} tiles");
      }
      var stats = new Dictionary<string, PlantStats>();
      for (var y = y0; y < y0 + h; y++) {
        for (var x = x0; x < x0 + w; x++) {
          if (!_terrainService.Contains(new Vector2Int(x, y))) {
            continue;
          }
          var surface = SurfaceHeight(x, y);
          foreach (var blockObject in _blockService.GetObjectsAt(new Vector3Int(x, y, surface))) {
            var growable = blockObject.GetComponent<Growable>();
            if (growable == null) {
              continue;
            }
            var name = TemplateName(blockObject);
            if (!stats.TryGetValue(name, out var s)) {
              stats[name] = s = new PlantStats();
            }
            s.total++;
            var living = blockObject.GetComponent<LivingNaturalResource>();
            if (living != null && living.IsDead) {
              s.dead++;
              continue;
            }
            var dying = blockObject.GetComponent<DyingNaturalResource>();
            if (dying != null && dying.IsDying) {
              s.dying++;
            }
            if (growable.IsGrown) {
              s.grown++;
            } else {
              s.growing++;
              s.progressSum += growable.GrowthProgress;
            }
            var gatherable = blockObject.GetComponent<Gatherable>();
            if (gatherable != null && gatherable.Yielder != null && gatherable.Yielder.Yield.Amount > 0) {
              s.ripe++;
            }
          }
        }
      }
      return stats.ToDictionary(kv => kv.Key, kv => (object) new {
          kv.Value.total, kv.Value.grown, kv.Value.growing,
          avgGrowth = kv.Value.growing > 0 ? (float) Math.Round(kv.Value.progressSum / kv.Value.growing, 2) : 0f,
          kv.Value.dying, kv.Value.dead, gatherableRipe = kv.Value.ripe,
      });
    }

    private class PlantStats {
      public int total, grown, growing, dying, dead, ripe;
      public float progressSum;
    }

    private object GetSize(BridgeRequest request) {
      var size = _mapSize.TerrainSize;
      return new { width = size.x, height = size.y, maxTerrainHeight = size.z, maxBuildHeight = _mapSize.TotalSize.z };
    }

    private object GetArea(BridgeRequest request) {
      var x0 = request.Require<int>("x");
      var y0 = request.Require<int>("y");
      var w = request.Get("w", 32);
      var h = request.Get("h", 32);
      if (w <= 0 || h <= 0 || w * h > MaxArea) {
        throw new BridgeException(400, $"Area must be positive and at most {MaxArea} tiles");
      }
      if (_terrainService.Contains(new Vector2Int(x0 + w / 2, y0 + h / 2))) {
        CameraModule.Focus(new Vector3Int(x0 + w / 2, y0 + h / 2, SurfaceHeight(x0 + w / 2, y0 + h / 2)));
      }
      var heights = new List<string>();
      var water = new List<string>();
      var objects = new List<string>();
      var legend = new Dictionary<string, char>();
      var flows = new List<string>();
      var moisture = new List<string>();
      // ThreadSafeWaterMap is internal; its flow lookup is reached by reflection.
      var flowMethod = _waterMap.GetType().GetMethod("WaterFlowDirection", new[] { typeof(Vector3Int) });
      var anyContamination = false;
      for (var y = y0 + h - 1; y >= y0; y--) {
        var heightRow = new StringBuilder();
        var waterRow = new StringBuilder();
        var objectRow = new StringBuilder();
        var flowRow = new StringBuilder();
        var moistRow = new StringBuilder();
        for (var x = x0; x < x0 + w; x++) {
          if (!_terrainService.Contains(new Vector2Int(x, y))) {
            heightRow.Append("  .");
            waterRow.Append('.');
            objectRow.Append('.');
            flowRow.Append('.');
            moistRow.Append('.');
            continue;
          }
          var surface = SurfaceHeight(x, y);
          var top = new Vector3Int(x, y, surface);
          heightRow.Append(surface.ToString().PadLeft(3));
          var depth = _waterMap.WaterDepth(top);
          var contamination = depth > 0 ? _waterMap.ColumnContamination(top) : 0f;
          anyContamination |= contamination > 0.05f;
          waterRow.Append(WaterChar(depth, contamination));
          objectRow.Append(ObjectChar(top, legend));
          flowRow.Append(depth > 0.05f && flowMethod != null
              ? FlowChar((Vector2) flowMethod.Invoke(_waterMap, new object[] { top })) : ' ');
          moistRow.Append(depth > 0.05f ? 'w' : _soilContaminationService.SoilIsContaminated(top) ? 'x'
              : _soilMoistureService.SoilIsMoist(top) ? '#' : ' ');
        }
        heights.Add(heightRow.ToString());
        water.Add(waterRow.ToString());
        objects.Add(objectRow.ToString());
        flows.Add(flowRow.ToString());
        moisture.Add(moistRow.ToString());
      }
      return new {
          origin = new { x = x0, y = y0, w, h },
          note = "Rows are listed from y=" + (y0 + h - 1) + " (top) down to y=" + y0 + "; columns from x=" + x0,
          heights,
          waterKey = "' '=dry, 1-9 = depth in quarter-blocks (9 = 2.25+), lowercase a-i = contaminated water",
          water,
          anyContamination,
          objectsKey = "' '=empty surface; letters per legend",
          objects,
          legend = legend.GroupBy(kv => kv.Value.ToString())
              .ToDictionary(g => g.Key, g => string.Join(", ", g.Select(kv => kv.Key))),
          flowKey = "Water flow: > east (+x), < west, ^ north (+y), v south, o still",
          flow = flows,
          moistureKey = "# = moist soil (crops and trees grow), x = contaminated soil (plants die), ' ' = dry, w = water",
          moisture,
      };
    }

    private object GetTile(BridgeRequest request) {
      var x = request.Require<int>("x");
      var y = request.Require<int>("y");
      if (!_terrainService.Contains(new Vector2Int(x, y))) {
        throw new BridgeException(400, "Tile outside the map");
      }
      var surface = SurfaceHeight(x, y);
      var top = new Vector3Int(x, y, surface);
      CameraModule.Focus(top);
      var stack = new List<object>();
      for (var z = Math.Max(0, surface - 2); z < _mapSize.TotalSize.z; z++) {
        foreach (var blockObject in _blockService.GetObjectsAt(new Vector3Int(x, y, z))) {
          stack.Add(new { z, template = TemplateName(blockObject), finished = blockObject.IsFinished,
              id = blockObject.GetComponent<EntityComponent>()?.EntityId.ToString() });
        }
      }
      var depth = _waterMap.WaterDepth(top);
      return new {
          x, y,
          surfaceHeight = surface,
          waterDepth = (float) Math.Round(depth, 2),
          contamination = depth > 0 ? (float) Math.Round(_waterMap.ColumnContamination(top), 2) : 0f,
          moist = _soilMoistureService.SoilIsMoist(top),
          soilContaminated = _soilContaminationService.SoilIsContaminated(top),
          objects = stack.Distinct().ToList(),
      };
    }

    private int SurfaceHeight(int x, int y) {
      return _terrainService.GetTerrainHeightBelow(new Vector3Int(x, y, _mapSize.TotalSize.z - 1));
    }

    private static char FlowChar(Vector2 flow) {
      if (flow.sqrMagnitude < 0.0004f) {
        return 'o';
      }
      return Mathf.Abs(flow.x) >= Mathf.Abs(flow.y) ? (flow.x > 0 ? '>' : '<') : (flow.y > 0 ? '^' : 'v');
    }

    private object GetWaterSources(BridgeRequest request) {
      return _entityComponentRegistry.GetAll<WaterSource>()
          .Select(source => {
            var tiles = source.Coordinates;
            return new {
                x = tiles.Length == 0 ? 0 : (int) Math.Round(tiles.Average(c => c.x)),
                y = tiles.Length == 0 ? 0 : (int) Math.Round(tiles.Average(c => c.y)),
                z = tiles.Length == 0 ? 0 : tiles.Max(c => c.z),
                minX = tiles.Min(c => c.x), maxX = tiles.Max(c => c.x),
                minY = tiles.Min(c => c.y), maxY = tiles.Max(c => c.y),
                tiles = tiles.Length,
                specifiedStrength = (float) Math.Round(source.SpecifiedStrength, 2),
                currentStrength = (float) Math.Round(source.CurrentStrength, 2),
                contamination = (float) Math.Round(source.Contamination, 2),
            };
          })
          .ToList();
    }

    private static char WaterChar(float depth, float contamination) {
      if (depth < 0.05f) {
        return ' ';
      }
      var level = Mathf.Clamp(Mathf.CeilToInt(depth * 4f), 1, 9);
      return contamination > 0.05f ? (char) ('a' + level - 1) : (char) ('0' + level);
    }

    private char ObjectChar(Vector3Int top, Dictionary<string, char> legend) {
      var blockObject = _blockService.GetBottomObjectAt(top);
      if (blockObject == null) {
        return ' ';
      }
      var name = TemplateName(blockObject);
      if (blockObject.GetComponent<LivingNaturalResource>()?.IsDead == true) {
        name += " (dead)";
      }
      if (!legend.TryGetValue(name, out var symbol)) {
        // '?' is kept for overflow only; the legend groups every overflow name under it.
        const string symbols = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz#@$%&*+=!<>^~";
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
