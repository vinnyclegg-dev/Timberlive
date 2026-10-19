"""Set and check a YouTube live stream's title, description, tags, category and thumbnail (Data API v3).

    ../runtime/python youtube_meta.py auth                 # one-time browser consent, saves the token
    ../runtime/python youtube_meta.py status               # channel, OBS's stream (health), upcoming/live broadcasts
    ../runtime/python youtube_meta.py check-info --info ../media/ep2/stream-info.md   # offline: parse + limits
    ../runtime/python youtube_meta.py prepare --info ../media/ep2/stream-info.md \
        --thumbnail ../media/ep2/thumbnail.png [--start "2026-10-11T19:00"] [--privacy public|unlisted|private]
    ../runtime/python youtube_meta.py verify --info ../media/ep2/stream-info.md [--id <broadcastId>]
    ../runtime/python youtube_meta.py --stream-id <id> prepare ...   # pick the liveStream by hand
    ../runtime/python youtube_meta.py video --info ../media/github-video/youtube/video-info.md \
        --thumbnail ../media/github-video/youtube/thumbnail.png [--id <videoId>] [--privacy public]
        # a normal video uploaded in Studio (API uploads from an unaudited project are locked private)

The liveStream is the one whose key matches OBS's saved key; else the only one; else the one bound to a
live/upcoming broadcast. If OBS is signed in to YouTube ("Connect Account") its key field is empty: then use
--stream-id, or in OBS pick the prepared broadcast under Manage Broadcast > Select existing broadcast.

Info file: JSON {"title", "description", "tags": [...]} or the media/epN/stream-info.md layout
(title = the "<- recommended" line under "## Title", description = "## Description", tags = "## Tags").
The game title ("Timberborn") can't be set through the API: set it once in YouTube Studio.

Secrets: the OAuth client file and token live in %LOCALAPPDATA%\\TimberLive\\ (token encrypted with Windows
DPAPI, current user). The OBS stream key is only compared internally. None of them is ever printed.
"""
import argparse
import base64
import configparser
import ctypes
import json
import os
import re
import sys
import tempfile
from ctypes import wintypes
from datetime import datetime, timedelta, timezone

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "TimberLive")
CLIENT_FILE = os.path.join(DATA_DIR, "youtube-oauth-client.json")
TOKEN_FILE = os.path.join(DATA_DIR, "youtube-token.json")
OBS_DIR = os.path.join(os.environ.get("APPDATA", ""), "obs-studio")
GAME_NOTE = "Game title 'Timberborn' is Studio-only: set it once in YouTube Studio (not possible via the API)."
SETUP = [
    "Go to https://console.cloud.google.com/ and create a project (e.g. 'TimberLive').",
    "APIs & Services > Library: enable 'YouTube Data API v3'.",
    "APIs & Services > OAuth consent screen: User type External; fill in app name + emails; "
    "under Test users add the Google account that owns the YouTube channel.",
    "APIs & Services > Credentials > Create credentials > OAuth client ID > Application type 'Desktop app'.",
    f"Download the JSON and save it as {CLIENT_FILE}",
    "Run: ../runtime/python youtube_meta.py auth  (pick the channel's account/brand in the browser).",
    "Note: while the app is in 'Testing', the refresh token expires after 7 days; re-run 'auth' then, "
    "or publish the app (Publishing status > In production) to keep it.",
]
HINTS = {
    "quotaExceeded": "Daily API quota used up (10,000 units; thumbnails/updates cost 50 each). Try again after midnight Pacific.",
    "forbidden": "Not allowed. For thumbnails: the channel must be verified for custom thumbnails (youtube.com/verify).",
    "liveStreamingNotEnabled": "Live streaming isn't enabled on this channel: enable it at youtube.com/features (takes up to 24 h).",
    "insufficientPermissions": "Token lacks the youtube.force-ssl scope: run 'auth' again.",
    "invalidTitle": "YouTube rejected the title (empty, too long or contains < or >).",
    "invalidDescription": "YouTube rejected the description (too long or contains < or >).",
    "invalidTags": "YouTube rejected the tags (too long overall, or a bad character).",
    "uploadRateLimitExceeded": "Thumbnail upload rate limit: wait a few minutes.",
    "mediaBodyRequired": "Thumbnail file missing or empty.",
    "redundantTransition": "The broadcast is already in that state.",
}


def out(obj: dict, code: int = 0) -> None:
    print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    sys.exit(code)


def fail(msg: str, **extra) -> None:
    out({"ok": False, "error": msg, **extra}, 1)


# ---- token storage (DPAPI, current Windows user) -------------------------------------------------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in, blob_out = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):  # UI_FORBIDDEN
        raise OSError("DPAPI call failed (token made by another Windows user?)")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def save_token(creds) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    enc = base64.b64encode(_dpapi(creds.to_json().encode("utf-8"), True)).decode("ascii")
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"dpapi": enc}, f)


def load_creds():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not os.path.exists(TOKEN_FILE):
        fail("Not signed in: run 'youtube_meta.py auth' first.", setup=SETUP)
    with open(TOKEN_FILE, encoding="utf-8") as f:
        stored = json.load(f)
    info = json.loads(_dpapi(base64.b64decode(stored["dpapi"]), False)) if "dpapi" in stored else stored
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError:
            fail("Token expired or revoked (test-mode tokens last 7 days): run 'youtube_meta.py auth' again.")
        save_token(creds)
    return creds


def youtube():
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=load_creds(), cache_discovery=False)


# ---- info file --------------------------------------------------------------------------------------
def md_section(text: str, heading: str) -> str:
    m = re.search(rf"^##\s*{heading}[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return m.group(1) if m else ""


def load_info(path: str) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    if path.lower().endswith(".json"):
        d = json.loads(text)
        info = {"title": d.get("title", ""), "description": d.get("description", ""), "tags": d.get("tags", [])}
    else:
        lines = [l for l in md_section(text, "Title").splitlines() if l.strip()]
        pick = next((l for l in lines if re.search(r"←\s*recommended", l)), lines[0] if lines else "")
        title = re.sub(r"←\s*recommended.*$", "", pick)
        title = re.sub(r"^\s*(\d+[.)]|[-*])\s*", "", title).replace("**", "").strip()
        desc = md_section(text, "Description").replace("**", "").strip()
        tag_line = next((l for l in md_section(text, "Tags").splitlines() if l.strip()), "")
        info = {"title": title, "description": desc, "tags": tag_line.split(",")}
    info["title"] = info["title"].strip()
    info["description"] = info["description"].replace("\r\n", "\n").strip()
    info["tags"] = [t.strip() for t in info["tags"] if t and t.strip()]
    return info


def tag_chars(tags: list) -> int:  # YouTube's count: commas between tags, quotes around tags with spaces
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(len(tags) - 1, 0)


def check_info(info: dict) -> list:
    errs = []
    if not info["title"]:
        errs.append("title is empty")
    if len(info["title"]) > 100:
        errs.append(f"title is {len(info['title'])} chars (max 100)")
    if len(info["description"].encode("utf-8")) > 5000:
        errs.append(f"description is {len(info['description'].encode('utf-8'))} bytes (max 5000)")
    if tag_chars(info["tags"]) > 500:
        errs.append(f"tags are {tag_chars(info['tags'])} chars (max 500)")
    for field in ("title", "description"):
        if re.search(r"[<>]", info[field]):
            errs.append(f"{field} contains < or > (YouTube rejects them)")
    return errs


def info_summary(info: dict) -> dict:
    warn = re.findall(r"\[(?:add|todo|tbd)[^\]]*\]", info["description"], re.I)
    return {"title": info["title"], "titleLen": len(info["title"]), "descLen": len(info["description"]),
            "descBytes": len(info["description"].encode("utf-8")), "tagCount": len(info["tags"]),
            "tagChars": tag_chars(info["tags"]), "placeholders": warn}


# ---- YouTube helpers ---------------------------------------------------------------------------------
def obs_stream_key() -> str:
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    for name in ("user.ini", "global.ini"):
        p = os.path.join(OBS_DIR, name)
        if os.path.exists(p):
            cp.read(p, encoding="utf-8-sig")
            if cp.has_section("Basic"):
                break
    prof = cp.get("Basic", "ProfileDir", fallback=None) or cp.get("Basic", "Profile", fallback="Untitled")
    try:
        with open(os.path.join(OBS_DIR, "basic", "profiles", prof, "service.json"), encoding="utf-8") as f:
            return json.load(f).get("settings", {}).get("key", "") or ""
    except (OSError, ValueError):
        return ""


def list_streams(yt) -> list:
    return yt.liveStreams().list(part="id,snippet,cdn,status", mine=True, maxResults=50).execute().get("items", [])


def find_stream(yt, stream_id: str = None, bcs: list = None) -> tuple:
    """Return (liveStream, how it was chosen). Order: --stream-id, OBS key match, only stream, bound to a
    live broadcast, bound to an upcoming broadcast. The key is compared here and never leaves this function."""
    streams = list_streams(yt)
    if not streams:
        fail("No liveStreams on this channel. Open YouTube Studio > Go live once so the stream key exists.")
    if stream_id:
        hit = [s for s in streams if s["id"] == stream_id]
        return (hit[0], "--stream-id") if hit else fail(f"No liveStream with id {stream_id}.")
    key = obs_stream_key()
    match = [s for s in streams if key and s.get("cdn", {}).get("ingestionInfo", {}).get("streamName") == key]
    if len(match) == 1:
        return match[0], "obs-key"
    if len(streams) == 1:
        return streams[0], "only-stream"
    by_id = {s["id"]: s for s in streams}
    for b in sorted(bcs if bcs is not None else broadcasts(yt), key=lambda b: b["status"].get("lifeCycleStatus") != "live"):
        sid = b.get("contentDetails", {}).get("boundStreamId")
        if sid in by_id:
            return by_id[sid], f"bound-to-{b['status'].get('lifeCycleStatus')}-broadcast"
    fail("Can't tell which stream OBS uses: " + ("OBS's stream key matched none." if key else
         "OBS has no stream key saved (it is signed in to YouTube via 'Connect Account' / Manage Broadcast). "
         "Either set OBS to 'Use Stream Key' with the persistent key, or pass --stream-id."),
         streams=[stream_view(s) for s in streams])


def stream_view(s: dict) -> dict:  # deliberately no cdn.ingestionInfo (it holds the key)
    st = s.get("status", {})
    return {"id": s["id"], "title": s["snippet"].get("title"), "status": st.get("streamStatus"),
            "health": st.get("healthStatus", {}).get("status"), "resolution": s.get("cdn", {}).get("resolution")}


def broadcasts(yt) -> list:
    items = []
    for state in ("active", "upcoming"):
        items += yt.liveBroadcasts().list(part="id,snippet,status,contentDetails", broadcastStatus=state,
                                          broadcastType="all", maxResults=50).execute().get("items", [])
    return items


def bc_view(b: dict) -> dict:
    return {"id": b["id"], "title": b["snippet"].get("title"), "scheduledStart": b["snippet"].get("scheduledStartTime"),
            "lifeCycle": b["status"].get("lifeCycleStatus"), "privacy": b["status"].get("privacyStatus"),
            "boundStreamId": b.get("contentDetails", {}).get("boundStreamId")}


def pick_broadcast(items: list, stream_id: str):
    bound = [b for b in items if b.get("contentDetails", {}).get("boundStreamId") == stream_id]
    for states in (("live", "testing", "liveStarting", "testStarting"), ("ready", "created")):
        hits = [b for b in bound if b["status"].get("lifeCycleStatus") in states]
        if hits:
            return sorted(hits, key=lambda b: b["snippet"].get("scheduledStartTime", ""))[0]
    return None


def utc_iso(local: str = None) -> str:
    dt = datetime.fromisoformat(local).astimezone() if local else datetime.now(timezone.utc) + timedelta(minutes=5)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def thumbnail_file(path: str) -> tuple:
    if os.path.getsize(path) <= 2 * 1024 * 1024:
        return path, "image/png" if path.lower().endswith(".png") else "image/jpeg"
    try:
        from PIL import Image
    except ImportError:
        fail("Thumbnail is over 2 MB and Pillow isn't installed: pip install pillow, or shrink it.")
    tmp = os.path.join(tempfile.gettempdir(), "timberlive-thumb.jpg")
    for q in (92, 85, 75, 65):
        Image.open(path).convert("RGB").save(tmp, "JPEG", quality=q, optimize=True)
        if os.path.getsize(tmp) <= 2 * 1024 * 1024:
            return tmp, "image/jpeg"
    fail("Couldn't get the thumbnail under 2 MB.")


# ---- commands ----------------------------------------------------------------------------------------
def cmd_auth(_a) -> None:
    if not os.path.exists(CLIENT_FILE):
        fail(f"OAuth client file missing: {CLIENT_FILE}", setup=SETUP)
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True, prompt="consent", access_type="offline")
    save_token(creds)
    from googleapiclient.discovery import build
    ch = build("youtube", "v3", credentials=creds, cache_discovery=False).channels().list(
        part="snippet", mine=True).execute().get("items", [])
    out({"ok": True, "token": "saved (DPAPI-encrypted)", "channel": ch[0]["snippet"]["title"] if ch else None})


def cmd_status(_a) -> None:
    yt = youtube()
    ch = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
    key, bcs = obs_stream_key(), broadcasts(yt)
    streams = []
    for s in list_streams(yt):
        view = stream_view(s)
        view["obsKeyMatch"] = bool(key) and s.get("cdn", {}).get("ingestionInfo", {}).get("streamName") == key
        streams.append(view)
    out({"ok": True, "channel": {"id": ch[0]["id"], "title": ch[0]["snippet"]["title"]} if ch else None,
         "obsStreamKeySet": bool(key), "streams": streams, "broadcasts": [bc_view(b) for b in bcs], "note": GAME_NOTE})


def cmd_check_info(a) -> None:
    info = load_info(a.info)
    errs = check_info(info)
    out({"ok": not errs, "errors": errs, **info_summary(info)}, 1 if errs else 0)


def cmd_prepare(a) -> None:
    info = load_info(a.info)
    errs = check_info(info)
    if errs:
        fail("Info file over YouTube limits", errors=errs)
    if not os.path.exists(a.thumbnail):
        fail(f"Thumbnail not found: {a.thumbnail}")
    yt = youtube()
    bcs = broadcasts(yt)
    stream, how = find_stream(yt, a.stream_id, bcs)
    b = pick_broadcast(bcs, stream["id"])
    reused = b is not None
    if not b:
        b = yt.liveBroadcasts().insert(part="id,snippet,status,contentDetails", body={
            "snippet": {"title": info["title"], "description": info["description"], "scheduledStartTime": utc_iso(a.start)},
            "status": {"privacyStatus": a.privacy or "public", "selfDeclaredMadeForKids": False},
            "contentDetails": {"enableAutoStart": True, "enableAutoStop": False, "enableDvr": True,
                               "latencyPreference": "normal"}}).execute()
        b = yt.liveBroadcasts().bind(id=b["id"], part="id,snippet,status,contentDetails", streamId=stream["id"]).execute()
    elif a.start and b["status"].get("lifeCycleStatus") in ("created", "ready"):
        yt.liveBroadcasts().update(part="snippet", body={"id": b["id"], "snippet": {
            "title": info["title"], "description": info["description"], "scheduledStartTime": utc_iso(a.start)}}).execute()
    vid = b["id"]
    if reused and a.privacy:
        yt.videos().update(part="status", body={"id": vid, "status": {
            "privacyStatus": a.privacy, "selfDeclaredMadeForKids": False}}).execute()
    yt.videos().update(part="snippet", body={"id": vid, "snippet": {
        "title": info["title"], "description": info["description"], "tags": info["tags"],
        "categoryId": "20", "defaultLanguage": "en", "defaultAudioLanguage": "en"}}).execute()
    from googleapiclient.http import MediaFileUpload
    path, mime = thumbnail_file(a.thumbnail)
    thumbs = yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(path, mimetype=mime)).execute()
    out({"ok": True, "reusedBroadcast": reused, "broadcast": bc_view(b), "stream": stream_view(stream), "streamChosenBy": how,
         "thumbnail": sorted(thumbs.get("items", [{}])[0].keys()), "link": f"https://youtu.be/{vid}",
         "studio": f"https://studio.youtube.com/video/{vid}/livestreaming", "note": GAME_NOTE})


def latest_upload(yt, prefix: str) -> dict:
    """Newest video in the channel's uploads whose title starts with `prefix` (Studio titles new uploads with the file name)."""
    ch = yt.channels().list(part="contentDetails", mine=True).execute().get("items", [])
    if not ch:
        fail("No channel on this account.")
    uploads = ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt.playlistItems().list(part="snippet", playlistId=uploads, maxResults=15).execute().get("items", [])
    for it in items:
        if it["snippet"]["title"].lower().startswith(prefix.lower()):
            return {"id": it["snippet"]["resourceId"]["videoId"], "title": it["snippet"]["title"]}
    fail(f"No recent upload titled '{prefix}...': upload the MP4 in Studio first, or pass --id.",
         recent=[it["snippet"]["title"] for it in items[:5]])


def cmd_video(a) -> None:
    """Set title, description, tags, category, thumbnail (and optionally privacy) on a video uploaded in Studio.

    Uploads through the API from an unaudited project are locked to private, so the MP4 itself goes up in Studio."""
    info = load_info(a.info)
    errs = check_info(info)
    if errs:
        fail("Info file over YouTube limits", errors=errs)
    if not os.path.exists(a.thumbnail):
        fail(f"Thumbnail not found: {a.thumbnail}")
    yt = youtube()
    found = {"id": a.id, "title": None} if a.id else latest_upload(yt, a.match)
    vid = found["id"]
    items = yt.videos().list(part="status", id=vid).execute().get("items", [])
    if not items:
        fail(f"Video {vid} not found on this channel.")
    status = {"privacyStatus": a.privacy or items[0]["status"]["privacyStatus"], "selfDeclaredMadeForKids": False,
              "embeddable": True}
    yt.videos().update(part="snippet,status", body={"id": vid, "status": status, "snippet": {
        "title": info["title"], "description": info["description"], "tags": info["tags"],
        "categoryId": "20", "defaultLanguage": "en", "defaultAudioLanguage": "en"}}).execute()
    from googleapiclient.http import MediaFileUpload
    path, mime = thumbnail_file(a.thumbnail)
    yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(path, mimetype=mime)).execute()
    out({"ok": True, "id": vid, "oldTitle": found["title"], "privacy": status["privacyStatus"],
         "link": f"https://youtu.be/{vid}", "studio": f"https://studio.youtube.com/video/{vid}/edit", "note": GAME_NOTE,
         "placeholders": info_summary(info)["placeholders"]})


def cmd_obs_key(a) -> None:
    """Put the stream's persistent key into OBS ('Use Stream Key' mode) over obs-websocket. Never printed."""
    yt = youtube()
    stream, how = find_stream(yt, a.stream_id)
    ing = stream.get("cdn", {}).get("ingestionInfo", {})
    key = ing.get("streamName")
    if not key:
        fail("That liveStream has no ingestion key.", stream=stream_view(stream))
    import obs
    cl = obs.connect()
    cur = cl.get_stream_service_settings().stream_service_settings
    if cur.get("key") != key:
        cl.set_stream_service_settings("rtmp_common", {
            "service": "YouTube - RTMPS", "protocol": "RTMPS", "bwtest": False,
            "server": "rtmps://a.rtmps.youtube.com:443/live2", "key": key})
    ok = cl.get_stream_service_settings().stream_service_settings.get("key") == key
    out({"ok": ok, "obsStreamKeySet": ok, "changed": cur.get("key") != key, "stream": stream_view(stream),
         "streamChosenBy": how}, 0 if ok else 1)


def cmd_end(a) -> None:
    """End the live broadcast (enableAutoStop is off, so stopping OBS alone leaves it 'live' on YouTube)."""
    yt = youtube()
    bcs = broadcasts(yt)
    stream, _ = find_stream(yt, a.stream_id, bcs)
    live = [b for b in bcs if b.get("contentDetails", {}).get("boundStreamId") == stream["id"]
            and b["status"].get("lifeCycleStatus") in ("live", "liveStarting")]
    if not live:
        out({"ok": True, "ended": None, "note": "no live broadcast bound to OBS's stream"})
    b = yt.liveBroadcasts().transition(broadcastStatus="complete", id=live[0]["id"],
                                       part="id,snippet,status,contentDetails").execute()
    out({"ok": True, "ended": bc_view(b), "link": f"https://youtu.be/{b['id']}"})


def cmd_verify(a) -> None:
    info = load_info(a.info)
    yt = youtube()
    vid = a.id
    if not vid:
        bcs = broadcasts(yt)
        b = pick_broadcast(bcs, find_stream(yt, a.stream_id, bcs)[0]["id"])
        if not b:
            fail("No live or upcoming broadcast bound to OBS's stream; pass --id.")
        vid = b["id"]
    items = yt.videos().list(part="snippet,status,liveStreamingDetails", id=vid).execute().get("items", [])
    if not items:
        fail(f"Video {vid} not found on this channel.")
    v = items[0]
    sn = v["snippet"]
    diffs = {}
    if sn.get("title", "") != info["title"]:
        diffs["title"] = {"want": info["title"], "have": sn.get("title")}
    if sn.get("description", "").replace("\r\n", "\n").strip() != info["description"]:
        diffs["description"] = {"wantLen": len(info["description"]), "haveLen": len(sn.get("description", ""))}
    if sorted(sn.get("tags", [])) != sorted(info["tags"]):  # YouTube may reorder tags
        have = sn.get("tags", [])
        diffs["tags"] = {"missing": [t for t in info["tags"] if t not in have], "extra": [t for t in have if t not in info["tags"]]}
    if sn.get("categoryId") != "20":
        diffs["categoryId"] = {"want": "20", "have": sn.get("categoryId")}
    lsd = v.get("liveStreamingDetails", {})
    out({"ok": not diffs, "id": vid, "link": f"https://youtu.be/{vid}", "diffs": diffs,
         "privacy": v["status"].get("privacyStatus"), "scheduledStart": lsd.get("scheduledStartTime"),
         "actualStart": lsd.get("actualStartTime"),
         "thumbnails": {k: t.get("url") for k, t in sn.get("thumbnails", {}).items()}, "note": GAME_NOTE},
        0 if not diffs else 1)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # titles carry emoji; the Windows console codepage cannot print them
    p = argparse.ArgumentParser(description="Set/verify YouTube live stream metadata (Data API v3, OAuth).")
    p.add_argument("--stream-id", help="liveStream id to use (see 'status') when OBS's stream key can't be matched")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth", help="one-time browser consent; saves the token")
    sub.add_parser("status", help="channel, OBS's liveStream and its health, live/upcoming broadcasts")
    c = sub.add_parser("check-info", help="offline: parse an info file and check YouTube limits")
    c.add_argument("--info", required=True)
    pr = sub.add_parser("prepare", help="reuse/create the broadcast, set metadata + thumbnail")
    pr.add_argument("--info", required=True)
    pr.add_argument("--thumbnail", required=True)
    pr.add_argument("--start", help="scheduled start, local time, e.g. 2026-10-11T19:00 (new broadcasts default to now+5 min)")
    pr.add_argument("--privacy", choices=["public", "unlisted", "private"],
                    help="new broadcasts default to public; existing ones keep theirs unless given")
    v = sub.add_parser("verify", help="re-read the video and compare with the info file")
    v.add_argument("--info", required=True)
    v.add_argument("--id", help="broadcast/video id (default: the live or upcoming one bound to OBS's stream)")
    vd = sub.add_parser("video", help="set metadata + thumbnail on a video uploaded in Studio (newest upload by title)")
    vd.add_argument("--info", required=True)
    vd.add_argument("--thumbnail", required=True)
    vd.add_argument("--id", help="video id (default: newest upload whose title starts with --match)")
    vd.add_argument("--match", default="timberlive-github", help="title prefix of the fresh Studio upload")
    vd.add_argument("--privacy", choices=["public", "unlisted", "private"], help="default: keep the current one")
    sub.add_parser("obs-key", help="set OBS to 'Use Stream Key' with this stream's persistent key (never printed)")
    sub.add_parser("end", help="end the live broadcast after OBS stops (auto-stop is off)")
    a = p.parse_args()
    from googleapiclient.errors import HttpError
    try:
        {"auth": cmd_auth, "status": cmd_status, "check-info": cmd_check_info, "prepare": cmd_prepare,
         "verify": cmd_verify, "video": cmd_video, "obs-key": cmd_obs_key, "end": cmd_end}[a.cmd](a)
    except HttpError as e:
        try:
            err = json.loads(e.content.decode("utf-8")).get("error", {})
            reason = (err.get("errors") or [{}])[0].get("reason", "") or err.get("status", "")
            message = err.get("message", "")
        except (ValueError, AttributeError):
            reason, message = "", str(e.reason)
        fail(f"YouTube API error {e.resp.status}: {message}", reason=reason, hint=HINTS.get(reason))
    except (OSError, ValueError) as e:
        fail(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
