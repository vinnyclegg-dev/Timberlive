using System;
using System.Collections.Generic;
using System.Globalization;
using Newtonsoft.Json.Linq;

namespace TimberLive.Bridge.Core {
  public class BridgeException : Exception {

    public int StatusCode { get; }

    public BridgeException(int statusCode, string message) : base(message) {
      StatusCode = statusCode;
    }

  }

  public class BinaryResult {

    public string ContentType { get; }
    public byte[] Bytes { get; }

    public BinaryResult(string contentType, byte[] bytes) {
      ContentType = contentType;
      Bytes = bytes;
    }

  }

  public class BridgeRequest {

    public string Method { get; }
    public string Path { get; }
    public IReadOnlyDictionary<string, string> Query { get; }
    public JObject Body { get; }

    public BridgeRequest(string method, string path, IReadOnlyDictionary<string, string> query, JObject body) {
      Method = method;
      Path = path;
      Query = query;
      Body = body;
    }

    /// <summary>Reads a value from the JSON body, falling back to the query string.</summary>
    public T Get<T>(string name, T fallback = default) {
      if (Body.TryGetValue(name, StringComparison.OrdinalIgnoreCase, out var token)
          && token.Type != JTokenType.Null) {
        return token.ToObject<T>();
      }
      if (Query.TryGetValue(name, out var raw) && raw != null) {
        var type = Nullable.GetUnderlyingType(typeof(T)) ?? typeof(T);
        return (T) Convert.ChangeType(raw, type, CultureInfo.InvariantCulture);
      }
      return fallback;
    }

    public T Require<T>(string name) {
      if (!Body.ContainsKey(name) && !Query.ContainsKey(name)) {
        throw new BridgeException(400, $"Missing parameter '{name}'");
      }
      return Get<T>(name);
    }

  }

  public delegate object RouteHandler(BridgeRequest request);

  public class Route {

    public string Method { get; }
    public string Path { get; }
    public string Description { get; }
    public RouteHandler Handler { get; }

    public Route(string method, string path, string description, RouteHandler handler) {
      Method = method;
      Path = path;
      Description = description;
      Handler = handler;
    }

  }

  /// <summary>Implemented by anything that contributes routes to a context.</summary>
  public interface IBridgeModule {

    IEnumerable<Route> GetRoutes();

  }
}
