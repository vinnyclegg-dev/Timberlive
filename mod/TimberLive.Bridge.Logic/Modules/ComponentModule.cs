using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Newtonsoft.Json.Linq;
using TimberLive.Bridge.Core;
using Timberborn.Automation;
using Timberborn.BaseComponentSystem;
using Timberborn.BlockSystem;
using Timberborn.EntitySystem;
using Timberborn.InventorySystem;
using Timberborn.Planting;
using Timberborn.TemplateSystem;
using Timberborn.TerrainSystem;
using Timberborn.Workshops;
using UnityEngine;

namespace TimberLive.Bridge.Logic.Modules {
  /// <summary>
  /// Generic access to the settings a player can change in a building's panel:
  /// storage good, recipes, crop priority, hauler priority, emptying, floodgate
  /// height and every automation part (sensors, relays, timers, levers, inputs).
  /// Only allow-listed components and action-style methods are exposed.
  /// </summary>
  [BridgeModule("Game")]
  public class ComponentModule : IBridgeModule {

    private static readonly string[] AutomationNamespaces = {
        "Timberborn.Automation", "Timberborn.AutomationBuildings", "Timberborn.HttpApiSystem",
    };

    private static readonly string[] AutomationActionPrefixes = {
        "Set", "Switch", "Toggle", "Increase", "Decrease", "Remove", "Reset", "Press", "Release",
    };

    /// <summary>Explicitly allowed actions on non-automation components.</summary>
    private static readonly Dictionary<string, string[]> AllowedActions = new() {
        ["SingleGoodAllower"] = new[] { "Allow", "Disallow" },
        ["Manufactory"] = new[] { "SetRecipe" },
        ["PlantablePrioritizer"] = new[] { "PrioritizePlantable" },
        ["FarmHouse"] = new[] { "PrioritizePlanting", "UnprioritizePlanting" },
        ["Emptiable"] = new[] { "MarkForEmptyingWithStatus", "UnmarkForEmptying" },
        ["Floodgate"] = new[] { "SetHeightAndSynchronize", "SetAutomationHeightAndSynchronize", "ToggleSynchronization" },
        ["HaulPrioritizable"] = new[] { "set_Prioritized" },
        // Stockpile priority: obtain = pull the good in from other stores, supply = push it out to them.
        ["GoodObtainer"] = new[] { "EnableObtaining", "DisableObtaining" },
        ["GoodSupplier"] = new[] { "EnableSupplying", "DisableSupplying" },
    };

    private static readonly HashSet<string> LifecycleMethods = new() {
        "SetInput", "SetResetInput", "SetState",
    };

    private readonly EntityRegistry _entityRegistry;
    private readonly TemplateService _templateService;
    private readonly ITerrainService _terrainService;

    public ComponentModule(EntityRegistry entityRegistry, TemplateService templateService,
                           ITerrainService terrainService) {
      _entityRegistry = entityRegistry;
      _templateService = templateService;
      _terrainService = terrainService;
    }

    public IEnumerable<Route> GetRoutes() {
      yield return new Route("GET", "/api/building/inspect",
                             "Settings, inventory and available actions of a building ?id=&all=true (all=also read-only state of every component)", Inspect);
      yield return new Route("POST", "/api/building/act",
                             "Run a panel action {id, component, action, args:[...]} (see inspect)", Act);
      yield return new Route("GET", "/api/automation", "All automation transmitters and automated buildings",
                             ListAutomation);
    }

    private EntityComponent FindEntity(string raw) {
      if (!Guid.TryParse(raw, out var id)) {
        throw new BridgeException(400, "id must be a GUID from list_buildings");
      }
      var entity = _entityRegistry.GetEntity(id);
      if (!entity) {
        throw new BridgeException(404, $"No entity with id {raw}");
      }
      var blockObject = entity.GetComponent<BlockObject>();
      if (blockObject) {
        CameraModule.Focus(blockObject.CoordinatesAtBaseZ);
      }
      return entity;
    }

    private static bool IsAutomationType(Type type) {
      return AutomationNamespaces.Contains(type.Namespace);
    }

    private static bool IsExposed(Type type) {
      return IsAutomationType(type) || AllowedActions.ContainsKey(type.Name);
    }

    private static IEnumerable<MethodInfo> Actions(Type type) {
      var methods = type.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
          .Where(m => m.ReturnType == typeof(void));
      if (IsAutomationType(type)) {
        return methods.Where(m => !m.IsSpecialName
                                  && AutomationActionPrefixes.Any(p => m.Name.StartsWith(p, StringComparison.Ordinal))
                                  && (type != typeof(Automator) || !LifecycleMethods.Contains(m.Name)));
      }
      var allowed = AllowedActions[type.Name];
      return methods.Where(m => allowed.Contains(m.Name));
    }

    private object Inspect(BridgeRequest request) {
      var entity = FindEntity(request.Require<string>("id"));
      var all = request.Get("all", false);
      var components = new List<object>();
      foreach (var component in entity.AllComponents) {
        var type = component.GetType();
        if (component is Inventory inventory) {
          components.Add(DescribeInventory(inventory));
          continue;
        }
        if (!IsExposed(type)) {
          if (all) {
            var state = ReadState(component, type);
            if (state.Count > 0) {
              components.Add(new { component = type.Name, state, readOnly = true });
            }
          }
          continue;
        }
        components.Add(new {
            component = type.Name,
            state = ReadState(component, type),
            actions = Actions(type).Select(DescribeAction).ToList(),
            recipes = component is Manufactory manufactory
                ? manufactory.ProductionRecipes.Select(r => r.Id).ToList() : null,
            plantables = component is PlantablePrioritizer
                ? _templateService.GetAll<PlantableSpec>().Select(p => p.TemplateName).ToList() : null,
        });
      }
      return new {
          id = entity.EntityId.ToString(),
          template = entity.GetComponent<TemplateSpec>()?.TemplateName,
          powerConnections = PowerConnections.FromEntity(entity, _terrainService),
          components,
      };
    }

    private static object DescribeInventory(Inventory inventory) {
      return new {
          component = "Inventory",
          name = inventory.ComponentName,
          capacity = inventory.Capacity,
          stock = inventory.AllowedGoods
              .Select(g => new { good = g.StorableGood.GoodId, amount = inventory.AmountInStock(g.StorableGood.GoodId), max = g.Amount })
              .ToList(),
      };
    }

    private static Dictionary<string, object> ReadState(object component, Type type) {
      var state = new Dictionary<string, object>();
      foreach (var property in type.GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)) {
        if (property.GetIndexParameters().Length > 0 || !property.CanRead) {
          continue;
        }
        var propertyType = property.PropertyType;
        object value;
        try {
          value = property.GetValue(component);
        } catch (Exception) {
          continue;
        }
        if (propertyType.IsPrimitive || propertyType == typeof(string)) {
          state[property.Name] = value;
        } else if (propertyType.IsEnum) {
          state[property.Name] = value?.ToString();
        } else if (value is Vector3Int v) {
          state[property.Name] = new[] { v.x, v.y, v.z };
        } else if (value is Automator automator) {
          state[property.Name] = automator ? new { id = automator.AutomatorId, name = automator.AutomatorName } : null;
        } else if (value is RecipeSpec recipe) {
          state[property.Name] = recipe.Id;
        } else if (value is PlantableSpec plantable) {
          state[property.Name] = plantable.TemplateName;
        }
      }
      return state;
    }

    private static object DescribeAction(MethodInfo method) {
      return new {
          action = method.Name.StartsWith("set_") ? method.Name.Substring(4) : method.Name,
          args = method.GetParameters().Select(p => new {
              name = p.Name,
              type = p.ParameterType.IsEnum
                  ? string.Join("|", Enum.GetNames(p.ParameterType))
                  : p.ParameterType == typeof(Automator) ? "transmitter id" : p.ParameterType.Name,
          }).ToList(),
      };
    }

    private object Act(BridgeRequest request) {
      var entity = FindEntity(request.Require<string>("id"));
      var componentName = request.Require<string>("component");
      var actionName = request.Require<string>("action");
      var component = entity.AllComponents.FirstOrDefault(c => c.GetType().Name == componentName && IsExposed(c.GetType()))
                      ?? throw new BridgeException(404, $"No exposed component '{componentName}' (see inspect)");
      var type = component.GetType();
      var args = request.Body["args"] as JArray ?? new JArray();
      var method = Actions(type).FirstOrDefault(m => (m.Name == actionName || m.Name == "set_" + actionName)
                                                     && m.GetParameters().Length == args.Count)
                   ?? throw new BridgeException(404, $"No action '{actionName}' with {args.Count} args on {componentName}");
      var parameters = method.GetParameters();
      var values = new object[parameters.Length];
      for (var i = 0; i < parameters.Length; i++) {
        values[i] = Convert(args[i], parameters[i].ParameterType, component);
      }
      try {
        method.Invoke(component, values);
      } catch (TargetInvocationException e) when (e.InnerException != null) {
        throw new BridgeException(409, $"{actionName} failed: {e.InnerException.Message}");
      }
      return new { ok = true, component = componentName, state = ReadState(component, type) };
    }

    private object Convert(JToken token, Type type, object component) {
      if (type.IsEnum) {
        return Enum.Parse(type, token.ToString(), true);
      }
      if (type == typeof(Automator)) {
        var raw = token.Type == JTokenType.Null ? null : token.ToString();
        if (string.IsNullOrEmpty(raw)) {
          return null;
        }
        var automator = FindEntity(raw).GetComponent<Automator>();
        return automator ? automator : throw new BridgeException(400, $"{raw} is not an automation transmitter");
      }
      if (type == typeof(RecipeSpec)) {
        var id = token.ToString();
        return ((Manufactory) component).ProductionRecipes.FirstOrDefault(r => r.Id == id)
               ?? throw new BridgeException(400, $"Unknown recipe '{id}' for this building");
      }
      if (type == typeof(PlantableSpec)) {
        var name = token.ToString();
        return _templateService.GetAll<PlantableSpec>().FirstOrDefault(p => p.TemplateName == name)
               ?? throw new BridgeException(400, $"Unknown plantable '{name}'");
      }
      return token.ToObject(type);
    }

    private object ListAutomation(BridgeRequest request) {
      var transmitters = new List<object>();
      var automated = new List<object>();
      foreach (var entity in _entityRegistry.Entities) {
        var template = entity.GetComponent<TemplateSpec>()?.TemplateName;
        var automator = entity.GetComponent<Automator>();
        if (automator && automator.IsTransmitter) {
          transmitters.Add(new {
              id = automator.AutomatorId, name = automator.AutomatorName, template,
              state = automator.State.ToString(),
          });
        }
        var automatable = entity.GetComponent<Automatable>();
        if (automatable && automatable.IsAutomated) {
          automated.Add(new {
              id = entity.EntityId.ToString(), template,
              input = automatable.Input ? automatable.Input.AutomatorName : null,
              state = automatable.State.ToString(),
          });
        }
      }
      return new { transmitters, automated };
    }

  }
}
