using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using TimberLive.Bridge.Core;
using Timberborn.BlockObjectTools;
using Timberborn.BlockSystem;
using Timberborn.BuilderPrioritySystem;
using Timberborn.Buildings;
using Timberborn.ConstructionSites;
using Timberborn.Coordinates;
using Timberborn.EntitySystem;
using Timberborn.Localization;
using Timberborn.MechanicalSystem;
using Timberborn.PrioritySystem;
using Timberborn.RecoverableGoodSystemUI;
using Timberborn.ScienceSystem;
using Timberborn.StatusSystem;
using Timberborn.TemplateSystem;
using Timberborn.TerrainSystem;
using Timberborn.UndoSystem;
using Timberborn.WaterBuildings;
using Timberborn.WaterSystem;
using Timberborn.WorkSystem;
using UnityEngine;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>
  /// Building catalogue, placement and per-building controls. Placement goes
  /// through the same preview validation and placers as the player's build
  /// tool; locked buildings and dev-mode tools are refused.
  /// </summary>
  [BridgeModule("Game")]
  public class BuildModule : IBridgeModule {

    private readonly TemplateService _templateService;
    private readonly BlockObjectToolGroupSpecService _toolGroupSpecService;
    private readonly BuildingUnlockingService _buildingUnlockingService;
    private readonly PreviewPlacerFactory _previewPlacerFactory;
    private readonly BlockObjectPlacerService _blockObjectPlacerService;
    private readonly IUndoRegistry _undoRegistry;
    private readonly EntityComponentRegistry _entityComponentRegistry;
    private readonly EntityRegistry _entityRegistry;
    private readonly EntityService _entityService;
    private readonly ILoc _loc;
    private readonly IThreadSafeWaterMap _waterMap;
    private readonly ITerrainService _terrainService;
    private readonly Dictionary<string, PreviewPlacer> _previewPlacers = new();
    private readonly Dictionary<string, WaterWheel> _waterWheels = new();
    private Dictionary<string, PlaceableBlockObjectSpec> _placeables;

    public BuildModule(TemplateService templateService,
                       BlockObjectToolGroupSpecService toolGroupSpecService,
                       BuildingUnlockingService buildingUnlockingService,
                       PreviewPlacerFactory previewPlacerFactory,
                       BlockObjectPlacerService blockObjectPlacerService,
                       IUndoRegistry undoRegistry,
                       EntityComponentRegistry entityComponentRegistry,
                       EntityRegistry entityRegistry,
                       EntityService entityService,
                       ILoc loc,
                       IThreadSafeWaterMap waterMap,
                       ITerrainService terrainService) {
      _templateService = templateService;
      _toolGroupSpecService = toolGroupSpecService;
      _buildingUnlockingService = buildingUnlockingService;
      _previewPlacerFactory = previewPlacerFactory;
      _blockObjectPlacerService = blockObjectPlacerService;
      _undoRegistry = undoRegistry;
      _entityComponentRegistry = entityComponentRegistry;
      _entityRegistry = entityRegistry;
      _entityService = entityService;
      _loc = loc;
      _waterMap = waterMap;
      _terrainService = terrainService;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("GET", "/api/blueprints",
                             "Placeable buildings: name, group, size, cost, science, unlocked (?group=)",
                             GetBlueprints);
      yield return new Route("POST", "/api/place",
                             "Place {template, x,y,z, orientation 0-3, flip} or {template, placements:[...]}",
                             Place);
      yield return new Route("POST", "/api/place/scan",
                             "Check many spots in one call {template, z, x0,y0,x1,y1 or candidates:[[x,y,o]], "
                             + "orientations}: every buildable spot with its footprint, doorstep and water intake",
                             Scan);
      yield return new Route("GET", "/api/buildings", "Buildings with status (?template= substring filter)",
                             GetBuildings);
      yield return new Route("POST", "/api/building/priority", "Set {id, priority VeryLow..VeryHigh}",
                             SetPriority);
      yield return new Route("POST", "/api/building/workers", "Set desired workers {id, workers}",
                             SetWorkers);
      yield return new Route("POST", "/api/building/pause", "Pause or resume {id, paused}", SetPaused);
      yield return new Route("POST", "/api/demolish", "Deconstruct a building like the player's tool {id}",
                             Demolish);
    }

    private Dictionary<string, PlaceableBlockObjectSpec> Placeables {
      get {
        if (_placeables == null) {
          var groups = _toolGroupSpecService.AllSpecs.Select(g => g.Id).ToHashSet();
          _placeables = _templateService.GetAll<PlaceableBlockObjectSpec>()
              .Where(s => !s.DevModeTool && s.UsableWithCurrentFeatureToggles && groups.Contains(s.ToolGroupId))
              .GroupBy(s => s.GetSpec<TemplateSpec>().TemplateName)
              .ToDictionary(g => g.Key, g => g.First());
        }
        return _placeables;
      }
    }

    private object GetBlueprints(BridgeRequest request) {
      var group = request.Get<string>("group");
      return Placeables
          .Where(p => group == null || string.Equals(p.Value.ToolGroupId, group, StringComparison.OrdinalIgnoreCase))
          .OrderBy(p => p.Value.ToolGroupId).ThenBy(p => p.Value.ToolOrder)
          .Select(p => {
            var spec = p.Value;
            var building = spec.HasSpec<BuildingSpec>() ? spec.GetSpec<BuildingSpec>() : null;
            var blockSpec = spec.GetSpec<BlockObjectSpec>();
            var size = blockSpec.Size;
            var entrance = blockSpec.Entrance;
            return new {
                template = p.Key,
                name = DisplayName(spec),
                group = spec.ToolGroupId,
                layout = spec.Layout.ToString(),
                size = new[] { size.x, size.y, size.z },
                entrance = entrance is { HasEntrance: true }
                    ? new[] { entrance.Coordinates.x, entrance.Coordinates.y } : null,
                waterInput = spec.HasSpec<WaterInputSpec>()
                    ? new[] { spec.GetSpec<WaterInputSpec>().WaterInputCoordinates.x,
                              spec.GetSpec<WaterInputSpec>().WaterInputCoordinates.y } : null,
                cost = building?.BuildingCost.ToDictionary(c => c.Id, c => c.Amount),
                science = building?.ScienceCost ?? 0,
                unlocked = building == null || _buildingUnlockingService.Unlocked(building),
            };
          })
          .ToList();
    }

    private object Place(BridgeRequest request) {
      var templateName = request.Require<string>("template");
      if (!Placeables.TryGetValue(templateName, out var spec)) {
        throw new BridgeException(404, $"Unknown or unavailable template '{templateName}' (see /api/blueprints)");
      }
      if (spec.HasSpec<BuildingSpec>() && !_buildingUnlockingService.Unlocked(spec.GetSpec<BuildingSpec>())) {
        throw new BridgeException(409, $"'{templateName}' is locked; unlock it with science first");
      }
      // Callers give z as the level the building stands on; the game's placement
      // origin is BaseZ blocks lower (e.g. pumps with parts below ground level).
      var baseZ = spec.GetSpec<BlockObjectSpec>().BaseZ;
      var requested = ParsePlacements(request, baseZ);
      var maxPerCall = spec.Layout.GetPreviewCount();
      if (requested.Count > maxPerCall) {
        throw new BridgeException(400, $"At most {maxPerCall} placements per call for layout {spec.Layout}");
      }
      var previewPlacer = GetPreviewPlacer(templateName, spec);
      var buildable = previewPlacer.GetBuildableCoordinates(requested).ToList();
      // check=true is the player hovering the preview: report what would fit, place nothing, keep the camera still.
      if (request.Get("check", false)) {
        // Like the player's hover: the preview's warning tooltip, plus which blocks need what below them.
        previewPlacer.ShowPreviews(requested);
        var warning = previewPlacer.WarningText;
        previewPlacer.HideAllPreviews();
        var blockSpec = spec.GetSpec<BlockObjectSpec>();
        var wheel = GetWaterWheel(templateName, spec);
        return new {
            ok = buildable.Count > 0,
            buildable = buildable.Select(r => DescribeWithPower(r, baseZ, wheel, spec)).ToList(),
            rejected = requested.Where(r => !buildable.Contains(r))
                .Select(r => DescribeWithPower(r, baseZ, null, spec)).ToList(),
            warning = string.IsNullOrEmpty(warning) ? null : warning,
            needs = buildable.Count > 0 || !request.Get("explain", false) ? null
                : blockSpec.GetBlocks(requested[0])
                    .Where(b => b.MatterBelow != MatterBelow.Any || b.Underground)
                    .Select(b => new {
                        x = b.Coordinates.x, y = b.Coordinates.y, z = b.Coordinates.z + baseZ,
                        below = b.MatterBelow.ToString(), underground = b.Underground,
                    })
                    .ToList(),
        };
      }
      CameraModule.Focus((buildable.Count > 0 ? buildable : requested).Select(p => p.Coordinates));
      // Expected output is read before placing, like the hover preview (current water, no wheel yet).
      var placedWheel = GetWaterWheel(templateName, spec);
      var placed = buildable.Select(r => DescribeWithPower(r, baseZ, placedWheel, spec)).ToList();
      var placer = _blockObjectPlacerService.GetMatchingPlacer(spec.GetSpec<BlockObjectSpec>());
      foreach (var placement in buildable) {
        placer.Place(new EntitySetup.Builder(spec.Blueprint), placement);
      }
      _undoRegistry.CommitStack();
      previewPlacer.HideAllPreviews();
      var rejected = requested.Where(r => !buildable.Contains(r)).Select(r => Describe(r, baseZ)).ToList();
      return new {
          ok = buildable.Count > 0,
          placed,
          rejected,
          hint = rejected.Count > 0
              ? "Rejected spots are blocked, unsupported, off-terrain, underwater or overlapping. "
                + "Check /api/map around them."
              : null,
      };
    }

    /// <summary>
    /// The placement check for a whole area in one call: each buildable spot with the tiles it
    /// covers, its doorstep and, for pumps, where the pipe ends and whether that cell is underwater
    /// (WaterInputPipeCoordinates: the pipe drops from the input until terrain, up to MaxDepth).
    /// </summary>
    private object Scan(BridgeRequest request) {
      var templateName = request.Require<string>("template");
      if (!Placeables.TryGetValue(templateName, out var spec)) {
        throw new BridgeException(404, $"Unknown or unavailable template '{templateName}' (see /api/blueprints)");
      }
      var blockSpec = spec.GetSpec<BlockObjectSpec>();
      var baseZ = blockSpec.BaseZ;
      var z = request.Require<int>("z");
      var candidates = new List<Placement>();
      if (request.Body.TryGetValue("candidates", out var list) && list is JArray array) {
        foreach (var c in array) {
          candidates.Add(new Placement(new Vector3Int((int) c[0], (int) c[1], z - baseZ), (Orientation) (int) c[2],
                                       FlipMode.Unflipped));
        }
      } else {
        var oris = request.Body.TryGetValue("orientations", out var o) && o is JArray oa
            ? oa.Select(v => (int) v).ToArray() : new[] { 0, 1, 2, 3 };
        int x0 = request.Require<int>("x0"), y0 = request.Require<int>("y0");
        int x1 = request.Require<int>("x1"), y1 = request.Require<int>("y1");
        if ((x1 - x0 + 1) * (y1 - y0 + 1) * oris.Length > 20000) {
          throw new BridgeException(400, "Scan area too large (max 20000 spots x orientations)");
        }
        for (var x = x0; x <= x1; x++) {
          for (var y = y0; y <= y1; y++) {
            foreach (var ori in oris) {
              candidates.Add(new Placement(new Vector3Int(x, y, z - baseZ), (Orientation) ori, FlipMode.Unflipped));
            }
          }
        }
      }
      var previewPlacer = GetPreviewPlacer(templateName, spec);
      var layout = blockSpec.GetBlocks();
      var entrance = blockSpec.Entrance is { HasEntrance: true } ? blockSpec.Entrance.Coordinates : (Vector3Int?) null;
      var input = spec.HasSpec<WaterInputSpec>() ? spec.GetSpec<WaterInputSpec>().WaterInputCoordinates : (Vector3Int?) null;
      var maxDepth = spec.HasSpec<WaterInputPipeSpec>() ? spec.GetSpec<WaterInputPipeSpec>().MaxDepth : 0;
      var results = new List<object>();
      foreach (var p in candidates) {
        // Enumerate fully: the game's iterator only clears its preview list after the last item.
        if (previewPlacer.GetBuildableCoordinates(new List<Placement> { p }).ToList().Count == 0) {
          continue;
        }
        var tiles = blockSpec.GetBlocks(p).Select(b => new[] { b.Coordinates.x, b.Coordinates.y })
            .GroupBy(t => (t[0], t[1])).Select(g => g.First()).ToList();
        int[] door = null;
        if (entrance is { } e) {
          var d = layout.Transform(e, p);  // Transform already adds BaseZ
          door = new[] { d.x, d.y, d.z };
        }
        object water = null;
        if (input is { } wi) {
          var start = layout.Transform(wi, p) + new Vector3Int(0, 0, baseZ + 1);
          var end = start;
          if (maxDepth > 0) {
            var bottom = start.z - maxDepth;
            for (var zz = start.z - 1; zz >= bottom; zz--) {
              if (_terrainService.Underground(new Vector3Int(start.x, start.y, zz))) {
                bottom = zz + 1;
                break;
              }
            }
            end = new Vector3Int(start.x, start.y, bottom);
          }
          var wet = _waterMap.CellIsUnderwater(end);
          water = new {
              x = end.x, y = end.y, z = end.z, underwater = wet,
              depth = wet ? (float) Math.Round(_waterMap.WaterDepth(end), 2) : 0f,
              contamination = wet ? (float) Math.Round(_waterMap.ColumnContamination(end), 2) : 0f,
          };
        }
        results.Add(new {
            x = p.Coordinates.x, y = p.Coordinates.y, orientation = (int) p.Orientation,
            door, tiles, water,
        });
      }
      return new { template = templateName, z, tried = candidates.Count, buildable = results };
    }

    private PreviewPlacer GetPreviewPlacer(string templateName, PlaceableBlockObjectSpec spec) {
      if (!_previewPlacers.TryGetValue(templateName, out var previewPlacer)) {
        previewPlacer = _previewPlacerFactory.Create(spec);
        _previewPlacers[templateName] = previewPlacer;
      }
      return previewPlacer;
    }

    private static List<Placement> ParsePlacements(BridgeRequest request, int baseZ) {
      if (request.Body.TryGetValue("placements", out var list) && list is JArray array) {
        return array.Select(item => ParsePlacement((JObject) item, baseZ)).ToList();
      }
      return new List<Placement> { ParsePlacement(request.Body, baseZ) };
    }

    private static Placement ParsePlacement(JObject item, int baseZ) {
      int Int(string key) => item.Value<int?>(key) ?? throw new BridgeException(400, $"Placement missing '{key}'");
      var orientation = item.Value<int?>("orientation") ?? 0;
      if (orientation is < 0 or > 3) {
        throw new BridgeException(400, "orientation must be 0-3 (clockwise quarter turns)");
      }
      var flip = item.Value<bool?>("flip") ?? false;
      return new Placement(new Vector3Int(Int("x"), Int("y"), Int("z") - baseZ), (Orientation) orientation,
                           flip ? FlipMode.Flipped : FlipMode.Unflipped);
    }

    private static object Describe(Placement p, int baseZ) {
      return new {
          x = p.Coordinates.x, y = p.Coordinates.y, z = p.Coordinates.z + baseZ,
          orientation = (int) p.Orientation, flip = p.FlipMode.IsFlipped,
      };
    }

    /// <summary>Water wheel data from the internal WaterPoweredGeneratorSpec (read by reflection).</summary>
    private sealed class WaterWheel {
      public Vector2Int[] Blocks;
      public Vector2 Direction;
      public float MinOutflow;
      public int PowerOutput;
      public Blocks Layout;
    }

    private WaterWheel GetWaterWheel(string templateName, PlaceableBlockObjectSpec spec) {
      if (_waterWheels.TryGetValue(templateName, out var cached)) {
        return cached;
      }
      WaterWheel wheel = null;
      try {
        var gen = FindSpec(spec.Blueprint, "WaterPoweredGeneratorSpec");
        if (gen != null) {
          var t = gen.GetType();
          var blocks = ((IEnumerable<Vector2Int>) t.GetProperty("Blocks").GetValue(gen)).ToArray();
          var node = FindSpec(spec.Blueprint, nameof(MechanicalNodeSpec)) as MechanicalNodeSpec;
          if (blocks.Length > 0) {
            wheel = new WaterWheel {
                Blocks = blocks,
                Direction = (Vector2) t.GetProperty("ExpectedWaterDirection").GetValue(gen),
                MinOutflow = (float) t.GetProperty("MinRequiredOutflow").GetValue(gen),
                PowerOutput = node?.PowerOutput ?? 0,
                Layout = spec.GetSpec<BlockObjectSpec>().GetBlocks(),
            };
          }
        }
      } catch (Exception e) {
        Debug.LogWarning($"[TimberLive] water wheel spec for {templateName}: {e.Message}");
        wheel = null;
      }
      _waterWheels[templateName] = wheel;
      return wheel;
    }

    internal static object FindSpec(Timberborn.BlueprintSystem.Blueprint blueprint, string typeName) {
      if (blueprint == null) {
        return null;
      }
      object found = blueprint.Specs.FirstOrDefault(s => s.GetType().Name == typeName);
      if (found != null) {
        return found;
      }
      foreach (var child in blueprint.Children) {
        found = FindSpec(child, typeName);
        if (found != null) {
          return found;
        }
      }
      return null;
    }

    /// <summary>
    /// Describe plus, for water wheels, the power the hover preview shows: the same maths as
    /// WaterPoweredGenerator.CalculateGeneratedRotation x MechanicalNodeSpec.PowerOutput.
    /// </summary>
    private object DescribeWithPower(Placement p, int baseZ, WaterWheel wheel, PlaceableBlockObjectSpec spec) {
      var connections = PowerConnections.FromSpec(spec, p, _terrainService);
      var basic = connections == null ? Describe(p, baseZ) : new {
          x = p.Coordinates.x, y = p.Coordinates.y, z = p.Coordinates.z + baseZ,
          orientation = (int) p.Orientation, flip = p.FlipMode.IsFlipped,
          powerConnections = connections,
      };
      if (wheel == null) {
        return basic;
      }
      try {
        Vector2 dir = p.Orientation.Transform(wheel.Direction);
        var sum = 0f;
        var magSum = 0f;
        var tiles = new List<object>();
        foreach (var b in wheel.Blocks) {
          var c = wheel.Layout.Transform(new Vector3Int(b.x, b.y, 0), p);
          var wet = _waterMap.CellIsUnderwater(c);
          var flow = wet ? _waterMap.WaterFlowDirection(c) : Vector2.zero;
          var along = !wet ? 0f
              : dir.x != 0f ? flow.x * Math.Sign(dir.x)
              : dir.y != 0f ? flow.y * Math.Sign(dir.y) : 0f;
          if (Math.Abs(along) > wheel.MinOutflow) {
            sum += along;
          }
          magSum += flow.magnitude;
          tiles.Add(new {
              x = c.x, y = c.y, z = c.z + baseZ, wet,
              flow = (float) Math.Round(flow.magnitude, 3),
              along = (float) Math.Round(along, 3),
          });
        }
        var rotation = sum / wheel.Blocks.Length;
        return new {
            x = p.Coordinates.x, y = p.Coordinates.y, z = p.Coordinates.z + baseZ,
            orientation = (int) p.Orientation, flip = p.FlipMode.IsFlipped,
            power = (int) Math.Abs(rotation * wheel.PowerOutput),
            maxPower = wheel.PowerOutput,
            flow = (float) Math.Round(magSum / wheel.Blocks.Length, 3),
            waterTiles = tiles,
            powerConnections = connections,
        };
      } catch (Exception e) {
        Debug.LogWarning($"[TimberLive] water wheel power: {e.Message}");
        return basic;
      }
    }

    // Network supply/demand for generators and consumers (not shafts), so the player can see a short network.
    private static object PowerInfo(Building building) {
      var node = building.GetComponent<MechanicalNode>();
      if (node == null || node.IsShaft || node.Graph == null || !(node.IsGenerator || node.IsConsumer)) {
        return null;
      }
      var graph = node.Graph;
      return new {
          output = node.Actuals?.PowerOutput ?? 0,
          input = node.Actuals?.PowerInput ?? 0,
          networkSupply = graph.PowerSupply,
          networkDemand = graph.PowerDemand,
          efficiency = (float) Math.Round(graph.PowerEfficiency, 2),
      };
    }

    private object GetBuildings(BridgeRequest request) {
      var filter = request.Get<string>("template");
      return _entityComponentRegistry.GetAll<Building>()
          .Select(b => (building: b, template: b.GetComponent<TemplateSpec>()?.TemplateName ?? b.Name))
          .Where(t => filter == null || t.template.IndexOf(filter, StringComparison.OrdinalIgnoreCase) >= 0)
          .Select(t => DescribeBuilding(t.building, t.template))
          .ToList();
    }

    private object DescribeBuilding(Building building, string template) {
      var blockObject = building.GetComponent<BlockObject>();
      var workplace = building.GetComponent<Workplace>();
      var pausable = building.GetComponent<PausableBuilding>();
      var site = building.GetComponent<ConstructionSite>();
      var workPriority = building.GetComponent<WorkplacePriority>();
      var buildPriority = building.GetComponent<BuilderPrioritizable>();
      return new {
          id = building.GetComponent<EntityComponent>().EntityId.ToString(),
          template,
          x = blockObject.Coordinates.x,
          y = blockObject.Coordinates.y,
          z = blockObject.CoordinatesAtBaseZ.z,
          orientation = (int) blockObject.Orientation,
          finished = blockObject.IsFinished,
          buildProgress = blockObject.IsFinished || site == null ? (float?) null
              : (float) Math.Round(site.BuildTimeProgress, 2),
          priority = blockObject.IsFinished
              ? workPriority?.Priority.ToString()
              : buildPriority?.Priority.ToString(),
          workers = workplace == null ? null : new {
              assigned = workplace.NumberOfAssignedWorkers,
              desired = workplace.DesiredWorkers,
              max = workplace.MaxWorkers,
          },
          paused = pausable != null && pausable.Paused ? true : (bool?) null,
          powerConnections = PowerConnections.FromEntity(building, _terrainService),
          power = PowerInfo(building),
          // The tile in front of the entrance; a path must be on this tile.
          pathTile = blockObject.PositionedEntrance == null ? null : new[] {
              blockObject.PositionedEntrance.Coordinates.x,
              blockObject.PositionedEntrance.Coordinates.y,
              blockObject.PositionedEntrance.Coordinates.z,
          },
          statuses = Statuses(building),
          setup = Setup(building),
      };
    }

    /// <summary>Panel settings the watchdog audits: storage good, recipe, emptying, farm mode.</summary>
    private static Dictionary<string, object> Setup(Building building) {
      var setup = new Dictionary<string, object>();
      foreach (var component in building.GetComponent<EntityComponent>().AllComponents) {
        switch (component.GetType().Name) {
          case "SingleGoodAllower":
            setup["good"] = Id(Prop(component, "AllowedGood")) ?? "";
            break;
          case "Manufactory":
            setup["recipe"] = Id(Prop(component, "CurrentRecipe")) ?? "";
            break;
          case "Emptiable":
            if (Prop(component, "IsMarkedForEmptying") is true) {
              setup["emptying"] = true;
            }
            break;
          case "FarmHouse":
            setup["plantingFirst"] = Prop(component, "PlantingPrioritized") is true;
            break;
        }
      }
      return setup.Count > 0 ? setup : null;
    }

    private static object Prop(object component, string name) {
      try {
        return component.GetType().GetProperty(name)?.GetValue(component);
      } catch (Exception) {
        return null;
      }
    }

    private static string Id(object value) {
      if (value == null || value is string) {
        return (string) value;
      }
      return Prop(value, "Id") as string ?? value.ToString();
    }

    private static List<string> Statuses(Building building) {
      var subject = building.GetComponent<StatusSubject>();
      if (subject == null) {
        return null;
      }
      var statuses = subject.ActiveStatuses.Where(s => s.IsActive).Select(s => s.StatusDescription).ToList();
      return statuses.Count > 0 ? statuses : null;
    }

    private Building FindBuilding(BridgeRequest request) {
      var raw = request.Require<string>("id");
      if (!Guid.TryParse(raw, out var id)) {
        throw new BridgeException(400, "id must be a building GUID from /api/buildings");
      }
      var entity = _entityRegistry.GetEntity(id);
      var building = entity ? entity.GetComponent<Building>() : null;
      if (!building) {
        throw new BridgeException(404, $"No building with id {raw}");
      }
      CameraModule.Focus(building.GetComponent<BlockObject>().CoordinatesAtBaseZ);
      return building;
    }

    private object SetPriority(BridgeRequest request) {
      var building = FindBuilding(request);
      if (!Enum.TryParse<Priority>(request.Require<string>("priority"), true, out var priority)) {
        throw new BridgeException(400, "priority must be one of " + string.Join(", ", Enum.GetNames(typeof(Priority))));
      }
      var blockObject = building.GetComponent<BlockObject>();
      if (blockObject.IsFinished) {
        var workPriority = building.GetComponent<WorkplacePriority>()
                           ?? throw new BridgeException(409, "Building has no workplace priority");
        workPriority.SetPriority(priority);
      } else {
        var buildPriority = building.GetComponent<BuilderPrioritizable>()
                            ?? throw new BridgeException(409, "Construction site has no builder priority");
        buildPriority.SetPriority(priority);
      }
      return DescribeBuilding(building, building.GetComponent<TemplateSpec>()?.TemplateName);
    }

    private object SetWorkers(BridgeRequest request) {
      var building = FindBuilding(request);
      var workplace = building.GetComponent<Workplace>()
                      ?? throw new BridgeException(409, "Building is not a workplace");
      // The game's minimum is 1 desired worker; pause the building to stop it entirely.
      var target = Mathf.Clamp(request.Require<int>("workers"), 1, workplace.MaxWorkers);
      // Bounded loops: a no-op Increase/Decrease must never hang the main thread.
      for (var i = 0; i < 32 && workplace.DesiredWorkers < target; i++) {
        workplace.IncreaseDesiredWorkers();
      }
      for (var i = 0; i < 32 && workplace.DesiredWorkers > target; i++) {
        workplace.DecreaseDesiredWorkers();
      }
      return DescribeBuilding(building, building.GetComponent<TemplateSpec>()?.TemplateName);
    }

    private object SetPaused(BridgeRequest request) {
      var building = FindBuilding(request);
      var pausable = building.GetComponent<PausableBuilding>();
      if (pausable == null || !pausable.IsPausable()) {
        throw new BridgeException(409, "Building cannot be paused");
      }
      if (request.Require<bool>("paused")) {
        pausable.Pause();
      } else {
        pausable.Resume();
      }
      return DescribeBuilding(building, building.GetComponent<TemplateSpec>()?.TemplateName);
    }

    private object Demolish(BridgeRequest request) {
      var building = FindBuilding(request);
      var blockObject = building.GetComponent<BlockObject>();
      var blockers = new List<IBlockObjectDeletionBlocker>();
      blockObject.GetComponents(blockers);
      var blocker = blockers.FirstOrDefault(b => b.IsStackedDeletionBlocked || b.IsDeletionBlocked);
      if (blocker != null) {
        throw new BridgeException(409, "Deletion blocked: " + _loc.T(blocker.ReasonLocKey));
      }
      // The toolbar's Deconstruct tool only takes buildings (plants go through demolish-resources).
      if (building.GetComponent<BuildingSpec>() == null) {
        throw new BridgeException(409, "Not a building; use demolish_resources for plants and trees");
      }
      var template = building.GetComponent<TemplateSpec>()?.TemplateName;
      var coordinates = blockObject.CoordinatesAtBaseZ;
      // Like the tool, also take the linked object it recovers with (e.g. a building's attached part).
      var linked = blockObject.GetComponent<IRecoverableObjectAdder>()?.GetAdditionalObjectToRecover();
      _entityService.Delete(blockObject);
      if (linked) {
        _entityService.Delete(linked);
      }
      _undoRegistry.CommitStack();
      return new { ok = true, demolished = template, x = coordinates.x, y = coordinates.y, z = coordinates.z };
    }

    private string DisplayName(PlaceableBlockObjectSpec spec) {
      return spec.HasSpec<LabeledEntitySpec>() ? _loc.T(spec.GetSpec<LabeledEntitySpec>().DisplayNameLocKey) : null;
    }

  }
  /// <summary>
  /// Mechanical (power) connection points: for each transput of a mechanical node
  /// (generator, consumer or shaft: has a MechanicalNodeSpec), the world tile just outside
  /// it where a shaft or another mechanical building must sit (its transput must face back).
  /// Same maths as Transput.Coordinates/Direction/Target. Buildings that only carry
  /// pass-through transputs (houses etc., no MechanicalNodeSpec) get null, so no field.
  /// Up/down points into solid terrain are dropped.
  /// </summary>
  internal static class PowerConnections {
    private static string DirName(Direction3D d) => d switch {
        Direction3D.Right => "+x", Direction3D.Left => "-x",
        Direction3D.Up => "+y", Direction3D.Down => "-y",
        Direction3D.Top => "up", Direction3D.Bottom => "down",
        _ => d.ToString(),
    };

    private static bool Useless(Direction3D dir, Vector3Int target, ITerrainService terrain) {
      return !dir.IsHorizontal() && (!terrain.Contains(target) || terrain.Underground(target));
    }

    private static List<object> Compute(TransputProviderSpec provider, Func<Vector3Int, Vector3Int> transform,
                                        Func<Direction3D, Direction3D> rotate, ITerrainService terrain) {
      if (provider == null || provider.Transputs.IsDefaultOrEmpty) {
        return null;
      }
      var list = new List<object>();
      foreach (var t in provider.Transputs) {
        var from = transform(t.Coordinates);
        foreach (Direction3D d in t.Directions.GetEnumerator()) {
          var dir = rotate(d);
          var target = from + dir.ToOffset();
          if (!Useless(dir, target, terrain)) {
            list.Add(new { x = target.x, y = target.y, z = target.z, dir = DirName(dir),
                           from = new[] { from.x, from.y, from.z } });
          }
        }
      }
      return list.Count > 0 ? list : null;
    }

    /// <summary>For a preview placement (place_building check / placed results).</summary>
    public static List<object> FromSpec(PlaceableBlockObjectSpec spec, Placement p, ITerrainService terrain) {
      try {
        if (BuildModule.FindSpec(spec.Blueprint, nameof(MechanicalNodeSpec)) == null) {
          return null;
        }
        var provider = BuildModule.FindSpec(spec.Blueprint, nameof(TransputProviderSpec)) as TransputProviderSpec;
        var layout = spec.GetSpec<BlockObjectSpec>().GetBlocks();
        return Compute(provider, c => layout.Transform(c, p),
                       d => p.FlipMode.Transform(d).RotateHorizontally(p.Orientation), terrain);
      } catch (Exception e) {
        Debug.LogWarning($"[TimberLive] power connections: {e.Message}");
        return null;
      }
    }

    /// <summary>For an existing building or construction site.</summary>
    public static List<object> FromEntity(Timberborn.BaseComponentSystem.BaseComponent entity, ITerrainService terrain) {
      try {
        if (entity.GetComponent<MechanicalNodeSpec>() == null) {
          return null;
        }
        var node = entity.GetComponent<MechanicalNode>();
        if (node != null && !node.Transputs.IsDefaultOrEmpty) {
          var live = node.Transputs.Where(t => !Useless(t.Direction, t.Target, terrain)).Select(t => (object) new {
              x = t.Target.x, y = t.Target.y, z = t.Target.z, dir = DirName(t.Direction),
              from = new[] { t.Coordinates.x, t.Coordinates.y, t.Coordinates.z },
              connected = t.Connected,
          }).ToList();
          return live.Count > 0 ? live : null;
        }
        var blockObject = entity.GetComponent<BlockObject>();
        if (blockObject == null) {
          return null;
        }
        return Compute(entity.GetComponent<TransputProviderSpec>(), blockObject.TransformCoordinates,
                       blockObject.TransformDirection, terrain);
      } catch (Exception e) {
        Debug.LogWarning($"[TimberLive] power connections: {e.Message}");
        return null;
      }
    }
  }
}
