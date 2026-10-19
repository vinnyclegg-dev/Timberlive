using Bindito.Core;
using TimberLive.Bridge.Core;

namespace TimberLive.Bridge {
  public class MainMenuBridgeContext : BridgeContext {

    public override string Name => "MainMenu";

    public MainMenuBridgeContext(IContainer container) : base(container) {
    }

  }

  public class GameBridgeContext : BridgeContext {

    public override string Name => "Game";

    public GameBridgeContext(IContainer container) : base(container) {
    }

  }

  [Context("MainMenu")]
  public class MainMenuBridgeConfigurator : Configurator {

    protected override void Configure() {
      Bind<MainMenuBridgeContext>().AsSingleton();
    }

  }

  [Context("Game")]
  public class GameBridgeConfigurator : Configurator {

    protected override void Configure() {
      Bind<GameBridgeContext>().AsSingleton();
    }

  }
}
