using System;
using System.Collections;
using System.Threading.Tasks;
using UnityEngine;

namespace TimberLive.Bridge.Core {
  /// <summary>
  /// Captures JPEG screenshots. "screen" grabs the presented frame including UI;
  /// "camera" renders the main camera off-screen (no UI) and works even when the
  /// window isn't being presented. "auto" tries screen, then falls back to camera.
  /// Also keeps the game simulating while unfocused, which the bridge depends on.
  /// </summary>
  public class ScreenshotTaker : MonoBehaviour {

    private const float ScreenTimeoutSeconds = 2f;

    private static ScreenshotTaker _instance;

    public void Awake() {
      _instance = this;
    }

    public void Update() {
      if (!Application.runInBackground) {
        Application.runInBackground = true;
        Debug.Log("[TimberLive] Enabled runInBackground so the bridge keeps working while unfocused");
      }
    }

    /// <summary>Lets logic modules run coroutines (e.g. smooth camera moves) on this persistent object.</summary>
    public static Coroutine RunCoroutine(IEnumerator routine) {
      return _instance.StartCoroutine(routine);
    }

    public static void StopRunning(Coroutine coroutine) {
      if (coroutine != null && _instance != null) {
        _instance.StopCoroutine(coroutine);
      }
    }

    /// <summary>Quits after a short delay so the HTTP response can be sent first.</summary>
    public static void QuitSoon() {
      _instance.StartCoroutine(QuitAfterDelay());
    }

    private static IEnumerator QuitAfterDelay() {
      yield return new WaitForSecondsRealtime(1f);
      Application.Quit();
    }

    public static Task<object> Capture(int maxWidth, int quality, string mode) {
      if (_instance == null) {
        throw new BridgeException(503, "Screenshot component not ready");
      }
      if (mode == "camera") {
        return Task.FromResult<object>(new BinaryResult("image/jpeg", RenderCamera(maxWidth, quality)));
      }
      var completion = new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);
      _instance.StartCoroutine(_instance.CaptureScreen(maxWidth, quality, completion));
      if (mode == "auto") {
        _instance.StartCoroutine(_instance.CameraFallback(maxWidth, quality, completion));
      }
      return completion.Task;
    }

    private IEnumerator CameraFallback(int maxWidth, int quality, TaskCompletionSource<object> completion) {
      yield return new WaitForSecondsRealtime(ScreenTimeoutSeconds);
      if (!completion.Task.IsCompleted) {
        try {
          completion.TrySetResult(new BinaryResult("image/jpeg", RenderCamera(maxWidth, quality)));
        } catch (Exception e) {
          completion.TrySetException(e);
        }
      }
    }

    private IEnumerator CaptureScreen(int maxWidth, int quality, TaskCompletionSource<object> completion) {
      yield return new WaitForEndOfFrame();
      if (completion.Task.IsCompleted) {
        yield break;
      }
      Texture2D full = null;
      try {
        full = ScreenCapture.CaptureScreenshotAsTexture();
        completion.TrySetResult(new BinaryResult("image/jpeg", Encode(full, maxWidth, quality)));
      } catch (Exception e) {
        completion.TrySetException(e);
      } finally {
        if (full != null) {
          Destroy(full);
        }
      }
    }

    private static byte[] RenderCamera(int maxWidth, int quality) {
      var camera = Camera.main;
      if (camera == null) {
        throw new BridgeException(503, "No main camera in this scene");
      }
      var width = Math.Min(maxWidth, Screen.width > 0 ? Screen.width : maxWidth);
      var aspect = Screen.width > 0 && Screen.height > 0 ? Screen.height / (float) Screen.width : 9f / 16f;
      var height = Mathf.RoundToInt(width * aspect);
      var rt = RenderTexture.GetTemporary(width, height, 24);
      var previousTarget = camera.targetTexture;
      var previousActive = RenderTexture.active;
      var texture = new Texture2D(width, height, TextureFormat.RGB24, false);
      try {
        camera.targetTexture = rt;
        camera.Render();
        RenderTexture.active = rt;
        texture.ReadPixels(new Rect(0, 0, width, height), 0, 0);
        texture.Apply();
        return texture.EncodeToJPG(quality);
      } finally {
        camera.targetTexture = previousTarget;
        RenderTexture.active = previousActive;
        RenderTexture.ReleaseTemporary(rt);
        Destroy(texture);
      }
    }

    private static byte[] Encode(Texture2D full, int maxWidth, int quality) {
      var width = Math.Min(maxWidth, full.width);
      if (width == full.width) {
        return full.EncodeToJPG(quality);
      }
      var height = Mathf.RoundToInt(full.height * (width / (float) full.width));
      var rt = RenderTexture.GetTemporary(width, height);
      var previous = RenderTexture.active;
      var scaled = new Texture2D(width, height, TextureFormat.RGB24, false);
      try {
        Graphics.Blit(full, rt);
        RenderTexture.active = rt;
        scaled.ReadPixels(new Rect(0, 0, width, height), 0, 0);
        scaled.Apply();
        return scaled.EncodeToJPG(quality);
      } finally {
        RenderTexture.active = previous;
        RenderTexture.ReleaseTemporary(rt);
        Destroy(scaled);
      }
    }

  }
}
