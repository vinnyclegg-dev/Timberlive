using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Bindito.Core;
using Timberborn.SingletonSystem;
using Debug = UnityEngine.Debug;

namespace TimberLive.Bridge.Core {
  /// <summary>
  /// One per scene context. Builds the logic modules for its context (resolving their
  /// constructor parameters from the game's DI container), owns the route table, and
  /// runs queued handlers on the Unity main thread (UpdateSingleton runs every frame,
  /// including while paused).
  /// </summary>
  public abstract class BridgeContext : ILoadableSingleton, IUnloadableSingleton, IUpdatableSingleton {

    private static readonly TimeSpan FrameBudget = TimeSpan.FromMilliseconds(25);

    private readonly ConcurrentQueue<WorkItem> _queue = new();
    private readonly IContainer _container;
    private Dictionary<string, Route> _routes = new();
    private List<IBridgeModule> _modules = new();
    private List<string> _moduleErrors = new();

    public abstract string Name { get; }

    protected BridgeContext(IContainer container) {
      _container = container;
    }

    public void Load() {
      BuildModules();
      BridgeServer.Attach(this);
    }

    public void Unload() {
      BridgeServer.Detach(this);
      DisposeModules();
    }

    public void UpdateSingleton() {
      var stopwatch = Stopwatch.StartNew();
      while (stopwatch.Elapsed < FrameBudget && _queue.TryDequeue(out var item)) {
        try {
          item.Completion.SetResult(item.Route.Handler(item.Request));
        } catch (Exception e) {
          var inner = e is System.Reflection.TargetInvocationException { InnerException: not null } t
              ? t.InnerException : e;
          if (inner is not BridgeException) {
            Debug.LogWarning("[TimberLive] " + inner);  // LogException opens the game's crash screen
          }
          item.Completion.SetException(inner);
        }
      }
    }

    /// <summary>Main thread only. Reloads the logic assembly and rebuilds modules.</summary>
    public object Reload() {
      var loaded = LogicLoader.Load();
      DisposeModules();
      BuildModules();
      return new {
          ok = loaded && _moduleErrors.Count == 0,
          generation = LogicLoader.Generation,
          built = LogicLoader.LoadedFileTime.ToString("u"),
          modules = _modules.Select(m => m.GetType().Name),
          errors = _moduleErrors,
          routes = _routes.Count,
      };
    }

    public object Info() {
      return new {
          context = Name,
          generation = LogicLoader.Generation,
          built = LogicLoader.LoadedFileTime.ToString("u"),
          modules = _modules.Select(m => m.GetType().Name),
          errors = _moduleErrors,
      };
    }

    public bool TryGetRoute(string method, string path, out Route route) {
      return _routes.TryGetValue(Key(method, path), out route);
    }

    public IEnumerable<string> RouteList() {
      return _routes.Values.Select(r => $"{r.Method} {r.Path} - {r.Description}").OrderBy(s => s);
    }

    public Task<object> Enqueue(Route route, BridgeRequest request) {
      var item = new WorkItem(route, request);
      _queue.Enqueue(item);
      return item.Completion.Task;
    }

    public void FailPending(string reason) {
      while (_queue.TryDequeue(out var item)) {
        item.Completion.TrySetException(new BridgeException(503, reason));
      }
    }

    private void BuildModules() {
      var modules = new List<IBridgeModule>();
      var errors = new List<string>();
      var routes = new Dictionary<string, Route>();
      foreach (var type in LogicLoader.ModuleTypes(Name)) {
        try {
          var module = (IBridgeModule) Construct(type);
          foreach (var route in module.GetRoutes()) {
            routes[Key(route.Method, route.Path)] = route;
          }
          modules.Add(module);
        } catch (Exception e) {
          var inner = e is System.Reflection.TargetInvocationException { InnerException: not null } t
              ? t.InnerException : e;
          errors.Add($"{type.Name}: {inner.GetType().Name}: {inner.Message}");
          Debug.LogError($"[TimberLive] Module {type.Name} failed: {inner}");
        }
      }
      _modules = modules;
      _moduleErrors = errors;
      _routes = routes;
    }

    private object Construct(Type type) {
      var constructor = type.GetConstructors().OrderByDescending(c => c.GetParameters().Length).First();
      var arguments = constructor.GetParameters().Select(p => Resolve(p.ParameterType)).ToArray();
      return constructor.Invoke(arguments);
    }

    private object Resolve(Type type) {
      if (type.IsGenericType && type.GetGenericTypeDefinition() == typeof(IEnumerable<>)) {
        var element = type.GetGenericArguments()[0];
        var items = _container.GetInstances(element).ToList();
        var array = Array.CreateInstance(element, items.Count);
        for (var i = 0; i < items.Count; i++) {
          array.SetValue(items[i], i);
        }
        return array;
      }
      return _container.GetInstance(type);
    }

    private void DisposeModules() {
      foreach (var module in _modules.OfType<IDisposable>()) {
        try {
          module.Dispose();
        } catch (Exception e) {
          Debug.LogWarning("[TimberLive] " + e);
        }
      }
      _modules.Clear();
    }

    private static string Key(string method, string path) {
      return method.ToUpperInvariant() + " " + path.TrimEnd('/').ToLowerInvariant();
    }

    private class WorkItem {

      public Route Route { get; }
      public BridgeRequest Request { get; }
      public TaskCompletionSource<object> Completion { get; } =
        new(TaskCreationOptions.RunContinuationsAsynchronously);

      public WorkItem(Route route, BridgeRequest request) {
        Route = route;
        Request = request;
      }

    }

  }
}
