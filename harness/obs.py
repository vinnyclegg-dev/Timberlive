"""Control OBS Studio through its built-in WebSocket server (Tools > WebSocket Server Settings).

    ../runtime/python obs.py launch          # start OBS if needed, then check its settings
    ../runtime/python obs.py status          # live?, scene, which sources are showing
    ../runtime/python obs.py starting-soon   # show "Starting soon" slate, hide game (overlay stays on)
    ../runtime/python obs.py game-view       # show game + overlay, hide every slate
    ../runtime/python obs.py go-live         # start streaming (no-op if already live)
    ../runtime/python obs.py thanks          # show "Thanks for watching" slate, hide game (overlay stays on)
    ../runtime/python obs.py end-stream      # stop streaming
    ../runtime/python obs.py quit            # close OBS (refuses while live; run end-stream first)
    ../runtime/python obs.py show|hide "<source name>"

The password is read from OBS's own config (config.json or global.ini) and is never printed.
"""
import configparser
import json
import os
import subprocess
import sys
import time

import obsws_python as obs

SCENE = "TimberLive - Game"
GAME = "Timberborn (game)"
OVERLAY = "TimberLive overlay"
STARTING_SOON = "Slate: Starting soon"
THANKS = "Slate: Thanks for watching"
# Scene collection and profile names: the imported collection is "TimberLive" (overlay/obs/TimberLive.json).
# Override per PC in %LOCALAPPDATA%\TimberLive\obs.json: {"collection": "...", "profile": "..."} (the app's Stream page).
_LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", ""), "TimberLive", "obs.json")
try:
    with open(_LOCAL, encoding="utf-8") as _f:
        _CFG = json.load(_f)
except (OSError, ValueError):
    _CFG = {}
COLLECTION = _CFG.get("collection") or "TimberLive"
PROFILE = _CFG.get("profile") or "Untitled"
OBS_DIR = r"C:\Program Files\obs-studio\bin\64bit"
GLOBAL_INI = os.path.join(os.environ["APPDATA"], "obs-studio", "global.ini")
CONFIG = os.path.join(os.environ["APPDATA"], "obs-studio", "plugin_config", "obs-websocket", "config.json")


def websocket_config() -> dict:
    """WebSocket settings: plugin_config/obs-websocket/config.json, or [OBSWebSocket] in global.ini (OBS 30+)."""
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
        return {"enabled": cfg.get("server_enabled", False), "port": cfg.get("server_port", 4455),
                "auth": cfg.get("auth_required", True), "password": cfg.get("server_password", "")}
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    ini.optionxform = str
    ini.read(GLOBAL_INI, encoding="utf-8-sig")
    ws = ini["OBSWebSocket"] if ini.has_section("OBSWebSocket") else {}
    return {"enabled": ws.get("ServerEnabled", "false") == "true", "port": int(ws.get("ServerPort", 4455)),
            "auth": ws.get("AuthRequired", "true") == "true", "password": ws.get("ServerPassword", "")}


def connect() -> obs.ReqClient:
    cfg = websocket_config()
    if not cfg["enabled"]:
        sys.exit("OBS WebSocket is off: in OBS open Tools > WebSocket Server Settings and tick Enable.")
    password = cfg["password"] if cfg["auth"] else ""
    try:
        return obs.ReqClient(host="127.0.0.1", port=cfg["port"], password=password, timeout=5)
    except Exception as e:  # never echo the password; the exception text doesn't contain it
        sys.exit(f"Can't reach OBS ({type(e).__name__}). Is OBS running with the WebSocket server enabled?")


def launch() -> obs.ReqClient:
    """Start OBS with the TimberLive collection and profile unless it is already running."""
    running = "obs64.exe" in subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"],
                                            capture_output=True, text=True).stdout
    if not running:
        subprocess.Popen([os.path.join(OBS_DIR, "obs64.exe"), "--collection", COLLECTION, "--profile", PROFILE,
                          "--scene", SCENE, "--disable-shutdown-check"], cwd=OBS_DIR)
    for _ in range(60):
        try:
            with open(os.devnull, "w") as quiet:
                old, sys.stderr = sys.stderr, quiet
                try:
                    cl = connect()
                finally:
                    sys.stderr = old
            cl.get_scene_collection_list()   # raises code 207 while OBS is still loading
            return cl
        except (SystemExit, obs.error.OBSSDKRequestError):
            time.sleep(2)
    sys.exit("OBS started but was not ready within 2 minutes.")


def check_settings(cl: obs.ReqClient) -> None:
    """Exit with a list of problems if OBS isn't set up the TimberLive way. Never prints the stream key."""
    problems = []
    if cl.get_scene_collection_list().current_scene_collection_name != COLLECTION:
        cl.set_current_scene_collection(COLLECTION)
        time.sleep(3)
    v = cl.get_video_settings()
    if (v.base_width, v.base_height, v.output_width, v.output_height) != (1920, 1080, 1920, 1080):
        problems.append(f"video is {v.output_width}x{v.output_height}, expected 1920x1080")
    if round(v.fps_numerator / v.fps_denominator) != 30:
        problems.append(f"fps is {v.fps_numerator}/{v.fps_denominator}, expected 30")
    service = cl.get_stream_service_settings()
    settings = service.stream_service_settings or {}
    if "youtube" not in json.dumps(settings).lower():
        problems.append(f"stream service is not YouTube ({service.stream_service_type})")
    missing = [n for n in (GAME, OVERLAY, STARTING_SOON) if n not in scene_items(cl)]
    if missing:
        problems.append(f"missing sources: {missing}")
    print(json.dumps({"collection": COLLECTION, "video": "1920x1080@30", "service": settings.get("service"),
                      "streamKeySet": bool(settings.get("key")), "problems": problems}))
    if problems:
        sys.exit(1)


def scene_items(cl: obs.ReqClient) -> dict:
    return {i["sourceName"]: i for i in cl.get_scene_item_list(SCENE).scene_items}


def set_visible(cl: obs.ReqClient, source: str, visible: bool) -> None:
    item = scene_items(cl).get(source)
    if item is None:
        sys.exit(f"No source called '{source}' in scene '{SCENE}'.")
    cl.set_scene_item_enabled(SCENE, item["sceneItemId"], visible)


def status(cl: obs.ReqClient) -> None:
    stream = cl.get_stream_status()
    showing = [n for n, i in scene_items(cl).items() if i["sceneItemEnabled"]]
    print(json.dumps({
        "live": stream.output_active,
        "reconnecting": stream.output_reconnecting,
        "liveFor": stream.output_timecode if stream.output_active else None,
        "droppedFrames": f"{stream.output_skipped_frames}/{stream.output_total_frames}" if stream.output_active else None,
        "scene": cl.get_current_program_scene().current_program_scene_name,
        "showing": showing,
    }))


def obs_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"], capture_output=True, text=True).stdout
    return "obs64.exe" in out


def quit_obs() -> None:
    """Close OBS the normal way (like clicking X). Never while live, so a stream can't be cut by accident."""
    if not obs_running():
        print(json.dumps({"obsRunning": False}))
        return
    if connect().get_stream_status().output_active:
        sys.exit("OBS is still live: run `obs.py end-stream` first.")
    subprocess.run(["taskkill", "/IM", "obs64.exe"], capture_output=True)
    for _ in range(90):  # multistream OBS took >30 s to exit after S2E1
        time.sleep(1)
        if not obs_running():
            print(json.dumps({"obsRunning": False}))
            return
    sys.exit("OBS did not close within 90 s (a dialog may be open); close it by hand.")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, arg = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
    if cmd == "quit":
        quit_obs()
        return
    cl = launch() if cmd == "launch" else connect()
    if cmd == "launch":
        check_settings(cl)
    elif cmd == "status":
        pass
    elif cmd == "starting-soon":
        cl.set_current_program_scene(SCENE)
        set_visible(cl, STARTING_SOON, True)  # slate first so the screen is never empty
        set_visible(cl, GAME, False)
        set_visible(cl, OVERLAY, True)  # the main overlay always stays on (user rule)
    elif cmd == "thanks":
        cl.set_current_program_scene(SCENE)
        set_visible(cl, THANKS, True)  # slate first so the screen is never empty
        set_visible(cl, GAME, False)
        set_visible(cl, OVERLAY, True)
    elif cmd == "game-view":
        cl.set_current_program_scene(SCENE)
        set_visible(cl, GAME, True)
        set_visible(cl, OVERLAY, True)
        for name in scene_items(cl):
            if name.startswith("Slate:"):
                set_visible(cl, name, False)
    elif cmd == "go-live":
        if not cl.get_stream_status().output_active:
            cl.start_stream()
            for _ in range(20):
                time.sleep(1)
                if cl.get_stream_status().output_active:
                    break
            else:
                sys.exit("OBS did not go live within 20 s; check OBS's stream settings.")
    elif cmd == "end-stream":
        if cl.get_stream_status().output_active:
            cl.stop_stream()
            time.sleep(2)
    elif cmd in ("show", "hide") and arg:
        set_visible(cl, arg, cmd == "show")
    else:
        sys.exit(__doc__)
    status(cl)


if __name__ == "__main__":
    main()
