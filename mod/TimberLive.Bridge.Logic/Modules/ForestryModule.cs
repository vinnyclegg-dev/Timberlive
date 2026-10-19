using System;
using System.Collections.Generic;
using System.Linq;
using TimberLive.Bridge.Core;
using Timberborn.Buildings;
using Timberborn.EntitySystem;
using Timberborn.Forestry;
using Timberborn.Localization;
using Timberborn.MapStateSystem;
using Timberborn.Planting;
using Timberborn.ScienceSystem;
using Timberborn.TemplateSystem;
using Timberborn.TerrainSystem;
using UnityEngine;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>
  /// Crop/tree planting marks and the tree-cutting area, using the same
  /// validation and lock rules as the player's planting and cutting tools.
  /// </summary>
  [BridgeModule("Game")]
  public class ForestryModule : IBridgeModule {

    private const int MaxArea = 40 * 40;

    private readonly TemplateService _templateService;
    private readonly PlantingService _plantingService;
    private readonly PlantingAreaValidator _plantingAreaValidator;
    private readonly BuildingService _buildingService;
    private readonly BuildingUnlockingService _buildingUnlockingService;
    private readonly TreeCuttingArea _treeCuttingArea;
    private readonly ITerrainService _terrainService;
    private readonly MapSize _mapSize;
    private readonly ILoc _loc;

    public ForestryModule(TemplateService templateService,
                          PlantingService plantingService,
                          PlantingAreaValidator plantingAreaValidator,
                          BuildingService buildingService,
                          BuildingUnlockingService buildingUnlockingService,
                          TreeCuttingArea treeCuttingArea,
                          ITerrainService terrainService,
                          MapSize mapSize,
                          ILoc loc) {
      _templateService = templateService;
      _plantingService = plantingService;
      _plantingAreaValidator = plantingAreaValidator;
      _buildingService = buildingService;
      _buildingUnlockingService = buildingUnlockingService;
      _treeCuttingArea = treeCuttingArea;
      _terrainService = terrainService;
      _mapSize = mapSize;
      _loc = loc;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("GET", "/api/plantables", "Crops and trees you can mark for planting, and which building plants them",
                             GetPlantables);
      yield return new Route("POST", "/api/plant", "Mark {plant, x0,y0,x1,y1} for planting", Plant);
      yield return new Route("POST", "/api/unplant", "Clear planting marks in {x0,y0,x1,y1}", Unplant);
      yield return new Route("POST", "/api/cutting-area", "Add or remove {x0,y0,x1,y1, remove} tree cutting area",
                             CuttingArea);
    }

    private IEnumerable<PlantableSpec> PlayerPlantables() {
      var plantedGroups = _templateService.GetAll<PlanterBuildingSpec>()
          .Select(b => b.PlantableResourceGroup).ToHashSet();
      return _templateService.GetAll<PlantableSpec>().Where(p => plantedGroups.Contains(p.ResourceGroup));
    }

    /// <summary>Same rule as the game's UnlockedPlantableGroupsRegistry (internal).</summary>
    private bool IsLocked(PlantableSpec plantable) {
      return !_buildingService.Buildings.Any(b => _buildingUnlockingService.Unlocked(b)
                                                  && b.HasSpec<PlanterBuildingSpec>()
                                                  && b.GetSpec<PlanterBuildingSpec>().PlantableResourceGroup
                                                  == plantable.ResourceGroup);
    }

    private object GetPlantables(BridgeRequest request) {
      var planters = _templateService.GetAll<PlanterBuildingSpec>().ToList();
      return PlayerPlantables()
          .Select(p => new {
              plant = p.TemplateName,
              name = p.HasSpec<LabeledEntitySpec>() ? _loc.T(p.GetSpec<LabeledEntitySpec>().DisplayNameLocKey) : null,
              group = p.ResourceGroup,
              plantedBy = planters.Where(b => b.PlantableResourceGroup == p.ResourceGroup)
                  .Select(b => b.GetSpec<TemplateSpec>().TemplateName).ToList(),
              locked = IsLocked(p),
          })
          .ToList();
    }

    private object Plant(BridgeRequest request) {
      var name = request.Require<string>("plant");
      var plantable = PlayerPlantables().FirstOrDefault(p => p.TemplateName == name)
                      ?? throw new BridgeException(404, $"Unknown plantable '{name}' (see /api/plantables)");
      if (IsLocked(plantable)) {
        throw new BridgeException(409, $"'{name}' is locked; unlock the building that plants it first");
      }
      var area = Area(request).ToList();
      CameraModule.Focus(area);
      var marked = 0;
      var skipped = 0;
      foreach (var coordinates in area) {
        if (_plantingAreaValidator.CanPlant(coordinates, name)) {
          _plantingService.SetPlantingCoordinates(coordinates, name);
          marked++;
        } else {
          skipped++;
        }
      }
      return new {
          ok = marked > 0, marked, skipped,
          note = "Planting only happens within range of a matching planter building with workers",
      };
    }

    private object Unplant(BridgeRequest request) {
      var area = Area(request).ToList();
      CameraModule.Focus(area);
      var cleared = 0;
      foreach (var coordinates in area) {
        if (_plantingService.IsResourceAt(coordinates)) {
          _plantingService.UnsetPlantingCoordinates(coordinates);
          cleared++;
        }
      }
      return new { ok = true, cleared };
    }

    private object CuttingArea(BridgeRequest request) {
      var coordinates = Area(request).ToList();
      CameraModule.Focus(coordinates);
      if (request.Get("remove", false)) {
        _treeCuttingArea.RemoveCoordinates(coordinates);
      } else {
        _treeCuttingArea.AddCoordinates(coordinates);
      }
      var trees = coordinates.Count(_treeCuttingArea.HasYielder);
      return new { ok = true, tiles = coordinates.Count, treesInArea = trees };
    }

    /// <summary>Surface-level coordinates for every on-map tile in the requested rectangle.</summary>
    private IEnumerable<Vector3Int> Area(BridgeRequest request) {
      var x0 = request.Require<int>("x0");
      var y0 = request.Require<int>("y0");
      var x1 = request.Require<int>("x1");
      var y1 = request.Require<int>("y1");
      var (minX, maxX) = (Math.Min(x0, x1), Math.Max(x0, x1));
      var (minY, maxY) = (Math.Min(y0, y1), Math.Max(y0, y1));
      if ((maxX - minX + 1) * (maxY - minY + 1) > MaxArea) {
        throw new BridgeException(400, $"Area must be at most {MaxArea} tiles");
      }
      for (var x = minX; x <= maxX; x++) {
        for (var y = minY; y <= maxY; y++) {
          if (_terrainService.Contains(new Vector2Int(x, y))) {
            var z = _terrainService.GetTerrainHeightBelow(new Vector3Int(x, y, _mapSize.TotalSize.z - 1));
            yield return new Vector3Int(x, y, z);
          }
        }
      }
    }

  }
}
