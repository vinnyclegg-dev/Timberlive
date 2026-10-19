using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEngine;

namespace TimberLive.Bridge.Core {
  /// <summary>
  /// Loads the hot-reloadable logic assembly (all bridge modules) from bytes, so a
  /// rebuilt TimberLive.Bridge.Logic can be swapped in without restarting the game.
  /// The file uses a .bin extension so the game's mod loader doesn't load it too.
  /// </summary>
  public static class LogicLoader {

    public const string FileName = "TimberLive.Bridge.Logic.bin";

    private static string _path;

    public static Assembly Current { get; private set; }
    public static DateTime LoadedFileTime { get; private set; }
    public static int Generation { get; private set; }

    public static void Initialize(string modPath) {
      _path = Path.Combine(modPath, "Logic", FileName);
      AppDomain.CurrentDomain.AssemblyResolve += ResolveShim;
      Load();
    }

    /// <summary>Loads the latest logic file. Returns false (keeping the old one) on failure.</summary>
    public static bool Load() {
      if (!File.Exists(_path)) {
        Debug.LogError($"[TimberLive] Logic assembly missing: {_path}");
        return false;
      }
      try {
        var assembly = Assembly.Load(File.ReadAllBytes(_path));
        assembly.GetTypes();
        Current = assembly;
        LoadedFileTime = File.GetLastWriteTimeUtc(_path);
        Generation++;
        Debug.Log($"[TimberLive] Logic loaded (generation {Generation}, built {LoadedFileTime:u})");
        return true;
      } catch (Exception e) {
        Debug.LogError($"[TimberLive] Failed to load logic assembly: {e}");
        return false;
      }
    }

    public static Type[] ModuleTypes(string contextName) {
      if (Current == null) {
        return Type.EmptyTypes;
      }
      return Current.GetTypes()
          .Where(t => typeof(IBridgeModule).IsAssignableFrom(t) && !t.IsAbstract)
          .Where(t => t.GetCustomAttribute<BridgeModuleAttribute>()?.Contexts.Contains(contextName) == true)
          .ToArray();
    }

    private static Assembly ResolveShim(object sender, ResolveEventArgs args) {
      var shim = typeof(LogicLoader).Assembly;
      return new AssemblyName(args.Name).Name == shim.GetName().Name ? shim : null;
    }

  }

  /// <summary>Marks a logic module and the scene contexts it is created in.</summary>
  [AttributeUsage(AttributeTargets.Class)]
  public class BridgeModuleAttribute : Attribute {

    public string[] Contexts { get; }

    public BridgeModuleAttribute(params string[] contexts) {
      Contexts = contexts;
    }

  }
}
