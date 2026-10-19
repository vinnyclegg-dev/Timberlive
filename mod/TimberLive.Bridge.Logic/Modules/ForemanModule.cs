using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using TimberLive.Bridge.Core;
using Timberborn.BaseComponentSystem;
using Timberborn.Beavers;
using Timberborn.BlockSystem;
using Timberborn.Buildings;
using Timberborn.BuildingsNavigation;
using Timberborn.Characters;
using Timberborn.ConstructionSites;
using Timberborn.EntitySystem;
using Timberborn.Forestry;
using Timberborn.GameDistricts;
using Timberborn.Goods;
using Timberborn.InventorySystem;
using Timberborn.LifeSystem;
using Timberborn.MechanicalSystem;
using Timberborn.Navigation;
using Timberborn.Planting;
using Timberborn.TimeSystem;
using Timberborn.Workshops;
using Timberborn.WorkSystem;
using Timberborn.Yielding;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>
  /// Read-only views for Foreman (the advisor tool): power networks, production state, per-building
  /// stock, construction materials, district range, cutting/planting marks and beaver ages.
  /// Nothing here changes the game, and nothing reveals more than the player can see in the UI
  /// (power panel, building panels, district range overlay, cutting/planting overlays, beaver panel).
  /// </summary>
  [BridgeModule("Game")]
  public class ForemanModule : IBridgeModule {

    private readonly EntityComponentRegistry _entityComponentRegistry;
    private readonly DistrictCenterRegistry _districtCenterRegistry;
    private readonly INavigationRangeService _navigationRangeService;
    private readonly TreeCuttingArea _treeCuttingArea;
    private readonly PlantingService _plantingService;
    private readonly CharacterPopulation _characterPopulation;
    private readonly LifeService _lifeService;
    private readonly IDayNightCycle _dayNightCycle;
    private readonly WorkingHoursManager _workingHoursManager;

    public ForemanModule(EntityComponentRegistry entityComponentRegistry,
                         DistrictCenterRegistry districtCenterRegistry,
                         INavigationRangeService navigationRangeService,
                         TreeCuttingArea treeCuttingArea,
                         PlantingService plantingService,
                         CharacterPopulation characterPopulation,
                         LifeService lifeService,
                         IDayNightCycle dayNightCycle,
                         WorkingHoursManager workingHoursManager) {
      _entityComponentRegistry = entityComponentRegistry;
      _districtCenterRegistry = districtCenterRegistry;
      _navigationRangeService = navigationRangeService;
      _treeCuttingArea = treeCuttingArea;
      _plantingService = plantingService;
      _characterPopulation = characterPopulation;
      _lifeService = lifeService;
      _dayNightCycle = dayNightCycle;
      _workingHoursManager = workingHoursManager;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("GET", "/api/foreman/power", "Power networks: id, supply, demand, batteries, member buildings",
                             GetPower);
      yield return new Route("GET", "/api/foreman/production", "Every manufactory: recipe, progress, ready, inputs, output space",
                             GetProduction);
      yield return new Route("GET", "/api/foreman/stock", "Per-building inventory (stores, workshops); ?empty=true for empty ones",
                             GetStock);
      yield return new Route("GET", "/api/foreman/sites", "Construction sites: build and material progress, goods still missing",
                             GetSites);
      yield return new Route("GET", "/api/foreman/range", "District range: road tiles (with distance) and the terrain spill around them",
                             GetRange);
      yield return new Route("GET", "/api/foreman/marks", "Tree cutting area tiles and crop/tree planting marks",
                             GetMarks);
      yield return new Route("GET", "/api/foreman/reach", "Work range of every planter, lumberjack, gatherer, scavenger and tapper: tiles, marked plots and yielders in range",
                             GetReach);
      yield return new Route("GET", "/api/foreman/beavers", "Every beaver and bot: age in days, child, life left in days",
                             GetBeavers);
      yield return new Route("GET", "/api/foreman/hours", "Work hours: length of the workday, end hour, hour now, working now",
                             GetHours);
    }

    private object GetHours(BridgeRequest request) {
      return new {
          hours = _workingHoursManager.WorkedPartOfDay * 24f,
          endsAt = _workingHoursManager.EndHours,
          now = _dayNightCycle.HoursPassedToday,
          working = _workingHoursManager.AreWorkingHours,
      };
    }

    private static string Id(BaseComponent component) {
      return component.GetComponent<EntityComponent>().EntityId.ToString();
    }

    private static int[] Xyz(UnityEngine.Vector3Int c) {
      return new[] { c.x, c.y, c.z };
    }

    private object GetPower(BridgeRequest request) {
      var graphs = new Dictionary<MechanicalGraph, List<MechanicalNode>>();
      foreach (var building in _entityComponentRegistry.GetAll<Building>()) {
        var node = building.GetComponent<MechanicalNode>();
        if (node == null || node.Graph == null) {
          continue;
        }
        if (!graphs.TryGetValue(node.Graph, out var nodes)) {
          graphs[node.Graph] = nodes = new List<MechanicalNode>();
        }
        nodes.Add(node);
      }
      return graphs.Select(kv => new {
          id = RuntimeHelpers.GetHashCode(kv.Key),
          supply = kv.Key.PowerSupply,
          demand = kv.Key.PowerDemand,
          efficiency = (float) Math.Round(kv.Key.PowerEfficiency, 2),
          batteryCharge = kv.Key.BatteryCharge,
          batteryCapacity = kv.Key.BatteryCapacity,
          generators = kv.Key.NumberOfGenerators,
          members = kv.Value.Select(n => new {
              id = Id(n),
              role = n.IsGenerator ? "generator" : n.IsConsumer ? "consumer" : n.IsShaft ? "shaft" : "other",
              output = n.Actuals?.PowerOutput ?? 0,
              input = n.Actuals?.PowerInput ?? 0,
          }).ToList(),
      }).ToList();
    }

    private object GetProduction(BridgeRequest request) {
      return _entityComponentRegistry.GetAll<Building>()
          .Select(b => (building: b, manufactory: b.GetComponent<Manufactory>()))
          .Where(t => t.manufactory != null && t.building.GetComponent<BlockObject>().IsFinished)
          .Select(t => {
            var m = t.manufactory;
            return new {
                id = Id(t.building),
                recipe = m.CurrentRecipe?.Id,
                progress = (float) Math.Round(m.ProductionProgress, 3),
                ready = m.IsReadyToProduce,
                ingredients = m.HasAllIngredients,
                fuel = m.HasFuel,
                outputSpace = m.HasCurrentRecipe && m.HasUnreservedCapacityForCurrentProducts(),
                stock = m.Inventory == null ? null : Stock(m.Inventory),
            };
          })
          .ToList();
    }

    private static Dictionary<string, int> Stock(Inventory inventory) {
      return inventory.Stock.Where(g => g.Amount > 0).ToDictionary(g => g.GoodId, g => g.Amount);
    }

    private object GetStock(BridgeRequest request) {
      var withEmpty = request.Get("empty", false);
      var result = new List<object>();
      foreach (var building in _entityComponentRegistry.GetAll<Building>()) {
        if (!building.GetComponent<BlockObject>().IsFinished) {
          continue;
        }
        foreach (var component in building.GetComponent<EntityComponent>().AllComponents) {
          if (component is not Inventory inventory || !inventory.Enabled) {
            continue;
          }
          if (inventory.IsEmpty && !withEmpty) {
            continue;
          }
          result.Add(new {
              id = Id(building),
              inventory = inventory.ComponentName,
              capacity = inventory.Capacity,
              total = inventory.TotalAmountInStock,
              stock = Stock(inventory),
          });
        }
      }
      return result;
    }

    private object GetSites(BridgeRequest request) {
      return _entityComponentRegistry.GetAll<ConstructionSite>()
          .Where(s => !s.GetComponent<BlockObject>().IsFinished)
          .Select(s => {
            var missing = new SortedSet<GoodAmount>();
            s.RemainingRequiredGoods(missing);
            return new {
                id = Id(s),
                buildProgress = (float) Math.Round(s.BuildTimeProgress, 3),
                materialProgress = (float) Math.Round(s.MaterialProgress, 3),
                hasMaterials = s.HasMaterialsToResumeBuilding,
                started = s.WasStarted,
                on = s.IsOn,
                builderSpots = s.HasFreeSpots,
                missing = missing.Where(g => g.Amount > 0).ToDictionary(g => g.GoodId, g => g.Amount),
            };
          })
          .ToList();
    }

    private object GetRange(BridgeRequest request) {
      return _districtCenterRegistry.FinishedDistrictCenters.Select(dc => {
        var access = dc.GetComponent<BuildingAccessible>()?.Accessible?.UnblockedSingleAccessInstant;
        if (!access.HasValue) {
          return (object) new { name = dc.DistrictName, error = "district centre has no access" };
        }
        return new {
            name = dc.DistrictName,
            access = new[] { (int) Math.Floor(access.Value.x), (int) Math.Floor(access.Value.z), (int) Math.Round(access.Value.y) },  // Unity (x, height, y) -> grid (x, y, z)
            roads = _navigationRangeService.GetRoadNodesInRange(access.Value)
                .Select(w => new[] { w.Coordinates.x, w.Coordinates.y, w.Coordinates.z, (int) Math.Round(w.Distance) })
                .ToList(),
            spill = _navigationRangeService.GetRoadSpillNodesInRange(access.Value).Select(Xyz).ToList(),
        };
      }).ToList();
    }

    private object GetMarks(BridgeRequest request) {
      var cutting = _treeCuttingArea.CuttingArea.ToList();
      return new {
          cutting = cutting.Select(c => new[] { c.x, c.y, c.z, _treeCuttingArea.HasYielder(c) ? 1 : 0 }).ToList(),
          planting = _plantingService.PlantingCoordinates
              .Select(c => new object[] { c.x, c.y, c.z, _plantingService.GetResourceAt(c) })
              .ToList(),
      };
    }

    private object GetReach(BridgeRequest request) {
      // The game's own work range (BuildingTerrainRange: terrain nodes within walking distance of the door),
      // the same tiles the range overlay shows when a planter or lumberjack is selected.
      var union = new Dictionary<string, HashSet<UnityEngine.Vector3Int>>();
      var buildings = new List<object>();
      var marks = new HashSet<UnityEngine.Vector3Int>(_plantingService.PlantingCoordinates);
      foreach (var building in _entityComponentRegistry.GetAll<Building>()) {
        var range = building.GetComponent<BuildingTerrainRange>();
        if (range == null || !building.GetComponent<BlockObject>().IsFinished) {
          continue;
        }
        var name = building.GetComponent<EntityComponent>().Name.Replace("(Clone)", "");
        if (!union.TryGetValue(name, out var set)) {
          union[name] = set = new HashSet<UnityEngine.Vector3Int>();
        }
        var count = 0;
        var plots = new Dictionary<string, int>();
        foreach (var tile in range.GetRange()) {
          set.Add(tile);
          count++;
          if (marks.Contains(tile)) {
            var plant = _plantingService.GetResourceAt(tile) ?? "?";
            plots[plant] = plots.TryGetValue(plant, out var n) ? n + 1 : 1;
          }
        }
        var yielders = building.GetComponent<InRangeYielders>();
        var free = new List<Yielder>();
        var anyYielder = yielders != null && yielders.GetYielders(free);
        buildings.Add(new {
            id = Id(building),
            tiles = count,
            plots,
            yielders = yielders == null ? (int?) null : free.Count,
            hasYielders = yielders == null ? (bool?) null : anyYielder,
        });
      }
      return new {
          buildings,
          union = union.ToDictionary(kv => kv.Key, kv => kv.Value.Select(Xyz).ToList()),
      };
    }

    private object GetBeavers(BridgeRequest request) {
      // LifeService: progress grows by 1/averageLifespan per day, so days left = (expected - progress) x lifespan.
      var lifespanDays = _lifeService.LifeProgressIncreasePerTick > 0
          ? _dayNightCycle.FixedDeltaTimeInHours / 24f / _lifeService.LifeProgressIncreasePerTick : 0f;
      return _characterPopulation.Characters.Where(c => c.Alive).Select(c => {
        var life = c.GetComponent<LifeProgressor>();
        var longevity = c.GetComponent<ILongevity>();
        var left = life != null && longevity != null ? (longevity.ExpectedLongevity - life.LifeProgress) * lifespanDays : (float?) null;
        return new {
            id = Id(c),
            age = c.Age,
            child = c.GetComponent<Child>() != null,
            bot = c.GetComponent<Beaver>() == null,
            daysLeft = left.HasValue ? (float?) Math.Round(left.Value, 1) : null,
        };
      }).ToList();
    }

  }
}
