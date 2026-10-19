"""TimberLive viewer poll counter (separate process from Claude's tools).

Claude opens a poll by writing question + options (taken from its own plan) into
overlay/state.json. While a poll is open, this service reads YouTube live chat and
counts messages that are exactly a vote ("1", "!2", "vote 3"), one vote per viewer
(their latest vote wins).

Isolation: chat text never leaves this process. The only thing written out is
overlay/poll_counts.json, which holds integers and a fixed status word. Nothing
here logs, prints or stores message text, names or channel IDs.

Config (outside the repo, never printed): %LOCALAPPDATA%\\TimberLive\\youtube.json
  {"api_key": "...", "channel_id": "UC...", "video_id": ""}
video_id is optional; without it the current live video is found from channel_id.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "overlay" / "state.json"
COUNTS_FILE = ROOT / "overlay" / "poll_counts.json"
CONFIG_FILE = Path(os.environ["LOCALAPPDATA"]) / "TimberLive" / "youtube.json"
API = "https://www.googleapis.com/youtube/v3/"
MIN_INTERVAL = 6.0      # seconds between chat reads (5 quota units each)
IDLE_INTERVAL = 2.0     # how often to check for a new poll
GRACE = 8.0             # keep counting a few seconds after the poll closes (chat lag)
VOTE = re.compile(r"^!?\s*(?:vote|option)?\s*#?([1-9])(?!\d)")  # "2", "!vote 2", "2 corn please"


class ServiceError(Exception):
    """Carries a fixed status word only (never API text, URLs or keys)."""


def _get(method: str, key: str, **params) -> dict:
    query = urllib.parse.urlencode({**params, "key": key})
    try:
        with urllib.request.urlopen(f"{API}{method}?{query}", timeout=20) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        raise ServiceError(f"api_error_{e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ServiceError("network_error") from None


def _find_chat_id(config: dict) -> str:
    key = config["api_key"]
    video = config.get("video_id") or ""
    if not video:
        if not config.get("channel_id"):
            raise ServiceError("no_video_or_channel")
        found = _get("search", key, part="id", channelId=config["channel_id"], eventType="live", type="video")
        items = found.get("items", [])
        if not items:
            raise ServiceError("not_live")
        video = items[0]["id"]["videoId"]
    details = _get("videos", key, part="liveStreamingDetails", id=video)
    items = details.get("items", [])
    chat = items[0].get("liveStreamingDetails", {}).get("activeLiveChatId") if items else None
    if not chat:
        raise ServiceError("not_live")
    return chat


def _vote(text: str, options: int) -> int | None:
    text = unicodedata.normalize("NFKC", text or "").strip().lower()
    match = VOTE.match(text)
    if not match:
        return None
    choice = int(match.group(1))
    return choice if 1 <= choice <= options else None


def _timestamp(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return 0.0


def _write(poll_id, counts, voters, status):
    payload = {"id": poll_id, "counts": [int(c) for c in counts], "voters": int(voters),
               "status": status, "updated": time.time()}
    tmp = COUNTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(COUNTS_FILE)


def _open_poll() -> dict | None:
    try:
        poll = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("poll")
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not poll or poll.get("closed"):
        return None
    if time.time() > poll.get("closes", 0) + GRACE:
        return None
    return poll


def main():
    chat_id = None
    current = None          # id of the poll being counted
    votes: dict[str, int] = {}
    page_token = None
    while True:
        poll = _open_poll()
        if not poll:
            time.sleep(IDLE_INTERVAL)
            continue
        options = len(poll.get("options", []))
        if poll["id"] != current:
            current, votes, page_token = poll["id"], {}, None
            _write(current, [0] * options, 0, "starting")
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if not config.get("api_key"):
                raise ServiceError("no_api_key")
            if not chat_id:
                chat_id = _find_chat_id(config)
            params = {"liveChatId": chat_id, "part": "snippet", "maxResults": 2000}
            if page_token:
                params["pageToken"] = page_token
            result = _get("liveChat/messages", config["api_key"], **params)
            page_token = result.get("nextPageToken")
            for item in result.get("items", []):
                snippet = item.get("snippet", {})
                if snippet.get("type") != "textMessageEvent":
                    continue
                if _timestamp(snippet.get("publishedAt", "")) < poll.get("opened", 0):
                    continue
                choice = _vote(snippet.get("displayMessage", ""), options)
                if choice and snippet.get("authorChannelId"):
                    votes[snippet["authorChannelId"]] = choice
            counts = [0] * options
            for choice in votes.values():
                counts[choice - 1] += 1
            _write(current, counts, len(votes), "counting")
            wait = max(MIN_INTERVAL, result.get("pollingIntervalMillis", 0) / 1000)
        except FileNotFoundError:
            _write(current, [0] * options, 0, "no_config")
            wait = 10.0
        except (ServiceError, json.JSONDecodeError, KeyError) as e:
            status = str(e) if isinstance(e, ServiceError) else "bad_config"
            if status in ("api_error_403", "api_error_404", "not_live"):
                chat_id = None  # chat ended or changed; look it up again
            counts = [0] * options
            for choice in votes.values():
                counts[choice - 1] += 1
            _write(current, counts, len(votes), status)
            wait = 15.0
        time.sleep(wait)


if __name__ == "__main__":
    main()
