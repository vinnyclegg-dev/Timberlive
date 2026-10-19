using Timberborn.ModManagerScene;
using UnityEngine;

namespace TimberLive.Bridge.Core {
  public class BridgeStarter : IModStarter {

    public void StartMod(IModEnvironment modEnvironment) {
      var runner = new GameObject("TimberLive.Bridge");
      Object.DontDestroyOnLoad(runner);
      runner.AddComponent<ScreenshotTaker>();
      LogicLoader.Initialize(modEnvironment.ModPath);
      BridgeServer.Start();
    }

  }
}
