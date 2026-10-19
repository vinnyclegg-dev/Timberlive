using System;
using System.Collections.Generic;
using System.Linq;
using TimberLive.Bridge.Core;
using Timberborn.Beavers;
using Timberborn.Bots;
using Timberborn.GameCycleSystem;
using Timberborn.GameDistricts;
using Timberborn.Goods;
using Timberborn.HazardousWeatherSystem;
using Timberborn.HazardousWeatherSystemUI;
using Timberborn.Population;
using Timberborn.ResourceCountingSystem;
using Timberborn.ScienceSystem;
using Timberborn.TimeSystem;
using Timberborn.WeatherSystem;
using Timberborn.Wellbeing;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>
  /// Read-only colony overview. Weather information mirrors what the in-game
  /// weather panel shows, so the agent never knows more than a human player.
  /// </summary>
  [BridgeModule("Game")]
  public class StateModule : IBridgeModule {

    private readonly GameCycleService _gameCycleService;
    private readonly IDayNightCycle _dayNightCycle;
    private readonly SpeedManager _speedManager;
    private readonly WeatherService _weatherService;
    private readonly HazardousWeatherService _hazardousWeatherService;
    private readonly HazardousWeatherApproachingTimer _approachingTimer;
    private readonly BeaverPopulation _beaverPopulation;
    private readonly BotPopulation _botPopulation;
    private readonly PopulationService _populationService;
    private readonly WellbeingService _wellbeingService;
    private readonly ScienceService _scienceService;
    private readonly IGoodService _goodService;
    private readonly ResourceCountingService _resourceCountingService;
    private readonly DistrictCenterRegistry _districtCenterRegistry;

    public StateModule(GameCycleService gameCycleService,
                       IDayNightCycle dayNightCycle,
                       SpeedManager speedManager,
                       WeatherService weatherService,
                       HazardousWeatherService hazardousWeatherService,
                       HazardousWeatherApproachingTimer approachingTimer,
                       BeaverPopulation beaverPopulation,
                       BotPopulation botPopulation,
                       PopulationService populationService,
                       WellbeingService wellbeingService,
                       ScienceService scienceService,
                       IGoodService goodService,
                       ResourceCountingService resourceCountingService,
                       DistrictCenterRegistry districtCenterRegistry) {
      _gameCycleService = gameCycleService;
      _dayNightCycle = dayNightCycle;
      _speedManager = speedManager;
      _weatherService = weatherService;
      _hazardousWeatherService = hazardousWeatherService;
      _approachingTimer = approachingTimer;
      _beaverPopulation = beaverPopulation;
      _botPopulation = botPopulation;
      _populationService = populationService;
      _wellbeingService = wellbeingService;
      _scienceService = scienceService;
      _goodService = goodService;
      _resourceCountingService = resourceCountingService;
      _districtCenterRegistry = districtCenterRegistry;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("GET", "/api/state", "Time, weather, population, wellbeing, science, districts",
                             GetState);
      yield return new Route("GET", "/api/goods", "Global stock and capacity per good (?all=true for zeros)",
                             GetGoods);
    }

    private object GetState(BridgeRequest request) {
      var global = _populationService.GlobalPopulationData;
      return new {
          time = new {
              cycle = _gameCycleService.Cycle,
              cycleDay = _gameCycleService.CycleDay,
              dayProgress = Round(_dayNightCycle.DayProgress),
              speed = _speedManager.CurrentSpeed,
          },
          weather = GetWeather(),
          population = new {
              adults = _beaverPopulation.NumberOfAdults,
              children = _beaverPopulation.NumberOfChildren,
              bots = _botPopulation.NumberOfBots,
              homeless = global.BedData.Homeless,
              freeBeds = global.BedData.FreeBeds,
              unemployed = global.BeaverWorkplaceData.Unemployed,
              freeWorkslots = global.BeaverWorkplaceData.FreeWorkslots,
              contaminated = global.ContaminationData.ContaminatedAdults
                             + global.ContaminationData.ContaminatedChildren,
              allDead = _populationService.AllDead,
          },
          wellbeing = _wellbeingService.AverageGlobalWellbeing,
          science = _scienceService.SciencePoints,
          districts = _districtCenterRegistry.FinishedDistrictCenters.Select(d => new {
              name = d.DistrictName,
              x = d.CenterCoordinates.x,
              y = d.CenterCoordinates.y,
              z = d.CenterCoordinates.z,
              adults = d.DistrictPopulation.NumberOfAdults,
              children = d.DistrictPopulation.NumberOfChildren,
              bots = d.DistrictPopulation.NumberOfBots,
              wellbeing = _wellbeingService.GetAverageDistrictWellbeing(d),
          }),
      };
    }

    private object GetWeather() {
      var partialDay = _gameCycleService.PartialCycleDay;
      var hazardStart = _weatherService.HazardousWeatherStartCycleDay;
      var hazardId = _hazardousWeatherService.CurrentCycleHazardousWeather?.Id;
      if (_weatherService.IsHazardousWeather) {
        var elapsed = partialDay - hazardStart;
        return new {
            state = "hazardous",
            hazard = hazardId,
            daysRemaining = Round(_weatherService.HazardousWeatherDuration - elapsed),
        };
      }
      if (_approachingTimer.GetProgress() > 0f) {
        return new {
            state = "approaching",
            hazard = hazardId,
            daysUntil = Round(hazardStart - partialDay),
        };
      }
      return new { state = "temperate", hazard = (string) null };
    }

    private object GetGoods(BridgeRequest request) {
      var includeAll = request.Get("all", false);
      var result = new List<object>();
      foreach (var goodId in _goodService.Goods) {
        var count = _resourceCountingService.GetGlobalResourceCount(goodId);
        if (!includeAll && count.AllStock == 0 && count.TotalCapacity == 0) {
          continue;
        }
        result.Add(new {
            id = goodId,
            available = count.AvailableStock,
            total = count.AllStock,
            capacity = count.TotalCapacity,
            fillRate = Round(count.FillRate),
        });
      }
      return result;
    }

    private static float Round(float value) {
      return (float) Math.Round(value, 2);
    }

  }
}
