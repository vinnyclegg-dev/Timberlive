using System;
using System.Collections.Generic;
using System.Linq;
using TimberLive.Bridge.Core;
using Timberborn.Buildings;
using Timberborn.EntitySystem;
using Timberborn.NeedSystem;
using Timberborn.NotificationSystem;
using Timberborn.ScienceSystem;
using Timberborn.TemplateSystem;
using Timberborn.WorkSystem;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>Science unlocks, beaver needs, game notifications and working hours.</summary>
  [BridgeModule("Game")]
  public class ColonyModule : IBridgeModule, IDisposable {

    private const int MaxAlerts = 60;

    private readonly BuildingService _buildingService;
    private readonly BuildingUnlockingService _buildingUnlockingService;
    private readonly ScienceService _scienceService;
    private readonly EntityComponentRegistry _entityComponentRegistry;
    private readonly NotificationBus _notificationBus;
    private readonly WorkingHoursManager _workingHoursManager;
    private readonly LinkedList<Alert> _alerts = new();
    private int _alertSequence;

    public ColonyModule(BuildingService buildingService,
                        BuildingUnlockingService buildingUnlockingService,
                        ScienceService scienceService,
                        EntityComponentRegistry entityComponentRegistry,
                        NotificationBus notificationBus,
                        WorkingHoursManager workingHoursManager) {
      _buildingService = buildingService;
      _buildingUnlockingService = buildingUnlockingService;
      _scienceService = scienceService;
      _entityComponentRegistry = entityComponentRegistry;
      _notificationBus = notificationBus;
      _workingHoursManager = workingHoursManager;
      _notificationBus.NotificationPosted += OnNotificationPosted;
    }

    public void Dispose() {
      _notificationBus.NotificationPosted -= OnNotificationPosted;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("POST", "/api/unlock", "Spend science to unlock {template}", Unlock);
      yield return new Route("GET", "/api/needs", "Per-need beaver averages and how many are critical", GetNeeds);
      yield return new Route("GET", "/api/alerts", "Game notifications since this bridge load (?since=seq)",
                             GetAlerts);
      yield return new Route("POST", "/api/work-hours", "Set working hours per day {hours 1-24}", SetWorkHours);
    }

    private void OnNotificationPosted(object sender, NotificationEventArgs args) {
      var notification = args.Notification;
      _alerts.AddLast(new Alert {
          seq = ++_alertSequence,
          cycle = notification.Cycle,
          day = notification.CycleDay,
          text = notification.Description,
          subject = notification.Subject == Guid.Empty ? null : notification.Subject.ToString(),
      });
      while (_alerts.Count > MaxAlerts) {
        _alerts.RemoveFirst();
      }
    }

    private object GetAlerts(BridgeRequest request) {
      var since = request.Get("since", 0);
      return new {
          latest = _alertSequence,
          alerts = _alerts.Where(a => a.seq > since).ToList(),
      };
    }

    private object Unlock(BridgeRequest request) {
      var templateName = request.Require<string>("template");
      var spec = _buildingService.Buildings.FirstOrDefault(b => b.GetSpec<TemplateSpec>().TemplateName == templateName)
                 ?? throw new BridgeException(404, $"Unknown building '{templateName}'");
      if (_buildingUnlockingService.Unlocked(spec)) {
        return new { ok = true, alreadyUnlocked = true, science = _scienceService.SciencePoints };
      }
      if (!_buildingUnlockingService.Unlockable(spec)) {
        throw new BridgeException(409,
                                  $"Needs {spec.ScienceCost} science, have {_scienceService.SciencePoints}");
      }
      _buildingUnlockingService.Unlock(spec);
      return new { ok = true, unlocked = templateName, spent = spec.ScienceCost, science = _scienceService.SciencePoints };
    }

    private object GetNeeds(BridgeRequest request) {
      var managers = _entityComponentRegistry.GetAll<NeedManager>().ToList();
      var summary = new Dictionary<string, (float total, int count, int critical, int warning)>();
      foreach (var manager in managers) {
        foreach (var spec in manager.NeedSpecs) {
          if (!manager.NeedIsActive(spec.Id)) {
            continue;
          }
          summary.TryGetValue(spec.Id, out var s);
          s.total += manager.GetNeedPoints(spec.Id);
          s.count++;
          if (manager.NeedIsInCriticalState(spec.Id)) {
            s.critical++;
          } else if (manager.NeedIsBelowWarningThreshold(spec.Id)) {
            s.warning++;
          }
          summary[spec.Id] = s;
        }
      }
      return new {
          characters = managers.Count,
          needs = summary.OrderByDescending(kv => kv.Value.critical).ThenBy(kv => kv.Key)
              .Select(kv => new {
                  need = kv.Key,
                  average = (float) Math.Round(kv.Value.total / Math.Max(1, kv.Value.count), 2),
                  beavers = kv.Value.count,
                  critical = kv.Value.critical,
                  warning = kv.Value.warning,
              })
              .ToList(),
      };
    }

    // Lower-case fields so the JSON matches the rest of the API.
    private class Alert {

      public int seq;
      public int cycle;
      public int day;
      public string text;
      public string subject;

    }

    private object SetWorkHours(BridgeRequest request) {
      var hours = request.Require<float>("hours");
      if (hours < 1 || hours > 24) {
        throw new BridgeException(400, "hours must be between 1 and 24");
      }
      _workingHoursManager.WorkedPartOfDay = hours / 24f;
      return new { ok = true, hours, endsAt = _workingHoursManager.EndHours };
    }

  }
}
