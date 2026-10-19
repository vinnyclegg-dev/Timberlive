using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace TimberLive.Bridge.Core {
  /// <summary>
  /// Process-wide HTTP server. Lives for the whole game session; scene contexts
  /// (MainMenu, Game) attach their routes while loaded and detach on unload.
  /// Every handler runs on the Unity main thread via the attached context.
  /// </summary>
  public static class BridgeServer {

    public const int Port = 8095;
    public const string TokenHeader = "X-TimberLive-Token";
    private static readonly TimeSpan HandlerTimeout = TimeSpan.FromSeconds(20);
    private static readonly JsonSerializerSettings JsonSettings = new() {
        NullValueHandling = NullValueHandling.Ignore,
        ReferenceLoopHandling = ReferenceLoopHandling.Ignore,
    };

    private static readonly object Lock = new();
    private static HttpListener _listener;
    private static string _token;
    private static BridgeContext _context;

    public static string ContextName {
      get {
        lock (Lock) {
          return _context?.Name ?? "none";
        }
      }
    }

    public static void Start() {
      if (_listener != null) {
        return;
      }
      _token = CreateToken();
      WriteConnectionFile();
      _listener = new HttpListener();
      _listener.Prefixes.Add($"http://127.0.0.1:{Port}/");
      _listener.Prefixes.Add($"http://localhost:{Port}/");
      try {
        _listener.Start();
      } catch (Exception e) {
        Debug.LogError($"[TimberLive] Failed to start bridge on port {Port}: {e.Message}");
        _listener = null;
        return;
      }
      Task.Run(AcceptLoop);
      Debug.Log($"[TimberLive] Bridge listening on http://127.0.0.1:{Port}/");
    }

    public static void Attach(BridgeContext context) {
      lock (Lock) {
        _context = context;
      }
      Debug.Log($"[TimberLive] Context attached: {context.Name}");
    }

    public static void Detach(BridgeContext context) {
      lock (Lock) {
        if (_context == context) {
          _context = null;
        }
      }
      context.FailPending("Context unloaded");
      Debug.Log($"[TimberLive] Context detached: {context.Name}");
    }

    private static string CreateToken() {
      var bytes = new byte[24];
      using (var rng = RandomNumberGenerator.Create()) {
        rng.GetBytes(bytes);
      }
      return Convert.ToBase64String(bytes).Replace('+', '-').Replace('/', '_').TrimEnd('=');
    }

    private static void WriteConnectionFile() {
      var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                             "TimberLive");
      Directory.CreateDirectory(dir);
      var json = JsonConvert.SerializeObject(new { port = Port, token = _token });
      File.WriteAllText(Path.Combine(dir, "bridge.json"), json);
    }

    private static async Task AcceptLoop() {
      while (_listener is { IsListening: true }) {
        HttpListenerContext http;
        try {
          http = await _listener.GetContextAsync();
        } catch (Exception) {
          break;
        }
        _ = Task.Run(() => Handle(http));
      }
    }

    private static async Task Handle(HttpListenerContext http) {
      try {
        var request = http.Request;
        // Custom header requirement also blocks browser-originated (CSRF) calls.
        if (request.Headers[TokenHeader] != _token) {
          await WriteJson(http, 401, new { error = "Missing or invalid token" });
          return;
        }
        if (request.HttpMethod == "GET" && request.Url.AbsolutePath == "/api/ping") {
          await WriteJson(http, 200, new { ok = true, context = ContextName, version = Application.version });
          return;
        }
        BridgeContext context;
        lock (Lock) {
          context = _context;
        }
        if (context == null) {
          await WriteJson(http, 503, new { error = "Game is loading; no context attached", context = "none" });
          return;
        }
        var bridgeRequest = await ReadRequest(request);
        if (!context.TryGetRoute(bridgeRequest.Method, bridgeRequest.Path, out var route)
            && !TryGetDevRoute(context, bridgeRequest, out route)) {
          await WriteJson(http, 404, new {
              error = $"No route {bridgeRequest.Method} {bridgeRequest.Path} in context {context.Name}",
              routes = context.RouteList(),
          });
          return;
        }
        var resultTask = context.Enqueue(route, bridgeRequest);
        var completed = await Task.WhenAny(resultTask, Task.Delay(HandlerTimeout));
        if (completed != resultTask) {
          await WriteJson(http, 504, new { error = "Handler timed out (is the game window minimised or frozen?)" });
          return;
        }
        var result = await resultTask;
        while (result is Task<object> deferred) {
          var done = await Task.WhenAny(deferred, Task.Delay(HandlerTimeout));
          if (done != deferred) {
            await WriteJson(http, 504, new { error = "Deferred handler timed out" });
            return;
          }
          result = await deferred;
        }
        if (result is BinaryResult binary) {
          await Write(http, 200, binary.ContentType, binary.Bytes);
        } else {
          await WriteJson(http, 200, result ?? new { ok = true });
        }
      } catch (BridgeException e) {
        await SafeWriteJson(http, e.StatusCode, new { error = e.Message });
      } catch (Exception e) {
        Debug.LogWarning("[TimberLive] " + e);
        await SafeWriteJson(http, 500, new { error = e.GetType().Name + ": " + e.Message });
      }
    }

    /// <summary>Routes owned by the stable shim, so they survive a broken logic build.</summary>
    private static bool TryGetDevRoute(BridgeContext context, BridgeRequest request, out Route route) {
      route = (request.Method, request.Path.ToLowerInvariant()) switch {
          ("POST", "/api/dev/reload") => new Route("POST", "/api/dev/reload", "Reload logic", _ => context.Reload()),
          ("GET", "/api/dev/info") => new Route("GET", "/api/dev/info", "Logic info", _ => context.Info()),
          ("POST", "/api/dev/quit") => new Route("POST", "/api/dev/quit", "Quit the game", _ => {
            ScreenshotTaker.QuitSoon();
            return new { ok = true, quitting = true };
          }),
          _ => null,
      };
      return route != null;
    }

    private static async Task<BridgeRequest> ReadRequest(HttpListenerRequest request) {
      JObject body = null;
      if (request.HasEntityBody) {
        using var reader = new StreamReader(request.InputStream, Encoding.UTF8);
        var text = await reader.ReadToEndAsync();
        if (!string.IsNullOrWhiteSpace(text)) {
          try {
            body = JObject.Parse(text);
          } catch (JsonException e) {
            throw new BridgeException(400, "Body is not a JSON object: " + e.Message);
          }
        }
      }
      var query = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
      foreach (var key in request.QueryString.AllKeys) {
        if (key != null) {
          query[key] = request.QueryString[key];
        }
      }
      var path = request.Url.AbsolutePath.TrimEnd('/');
      return new BridgeRequest(request.HttpMethod, path, query, body ?? new JObject());
    }

    private static async Task SafeWriteJson(HttpListenerContext http, int status, object payload) {
      try {
        await WriteJson(http, status, payload);
      } catch (Exception) {
        // Client already gone.
      }
    }

    private static Task WriteJson(HttpListenerContext http, int status, object payload) {
      var bytes = Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(payload, JsonSettings));
      return Write(http, status, "application/json; charset=utf-8", bytes);
    }

    private static async Task Write(HttpListenerContext http, int status, string contentType, byte[] bytes) {
      var response = http.Response;
      response.StatusCode = status;
      response.ContentType = contentType;
      response.ContentLength64 = bytes.Length;
      await response.OutputStream.WriteAsync(bytes, 0, bytes.Length);
      response.Close();
    }

  }
}
