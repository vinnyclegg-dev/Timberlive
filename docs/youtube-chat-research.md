# YouTube Live Chat Overlay: Technical Research

Researched 2026-10-08 against the current Google and YouTube docs. Items marked **[UNCERTAIN]** are not confirmed by an official source and should be tested before anything depends on them. Items marked **[INFERENCE]** are my own reading of the docs.

---

## 1. Reading live chat

### 1.1 Getting the `liveChatId`

| Route | Auth | Quota | Field |
|---|---|---|---|
| `videos.list?part=liveStreamingDetails&id=VIDEO_ID` | API key is enough (public data) | 1 unit | `liveStreamingDetails.activeLiveChatId`. Per the docs it is "filled only if the video is a currently live broadcast that has live chat." |
| `liveBroadcasts.list?part=snippet&broadcastStatus=active&mine=true` | OAuth (`youtube.readonly`, `youtube`, or `youtube.force-ssl`) | 1 unit | `snippet.liveChatId` |
| `search.list?channelId=...&eventType=live&type=video`, then `videos.list` | API key | Since 2026-06-01 `search.list` has **its own bucket: 100 calls/day, 1 unit each** | Finds the current live video ID automatically |

For a bot that runs on the owner's channel, the simplest auto-discovery is `liveBroadcasts.list?mine=true&broadcastStatus=active`. It is cheap (1 unit) and the bot needs OAuth for moderation anyway.

- https://developers.google.com/youtube/v3/docs/videos (liveStreamingDetails)
- https://developers.google.com/youtube/v3/live/docs/liveBroadcasts/list
- https://developers.google.com/youtube/v3/revision_history (2026-06-01 granular quota for `search.list` / `videos.insert`)

### 1.2 `liveChatMessages.list` (REST polling)

- **Quota cost:** 5 units per call.
- **Parameters:** `liveChatId` (required); `part` = `id,snippet,authorDetails` (required); `pageToken`; `maxResults` (200–2000, default 500); `profileImageSize` (16–720, default 88); `hl`.
- **Response:** `items[]`, `nextPageToken`, `pollingIntervalMillis` ("the amount of time ... the client should wait before polling again"), `offlineAt` (set when the stream goes offline), and `activePollItem`.
- **Polling loop:** pass the previous `nextPageToken` as `pageToken` each time, so you only get new messages. Sleep for at least `pollingIntervalMillis` between calls. If you poll faster, expect `rateLimitExceeded`.
- **Auth [UNCERTAIN, though widely used in practice]:** the docs page does not show an Authorization/scopes block for `list`. The generated client docs say an API key is accepted unless an OAuth token is supplied. Community projects read public chats with only an API key; if that fails with `forbidden` or `insufficientPermissions`, they fall back to OAuth. With OAuth, the read-only scope is `https://www.googleapis.com/auth/youtube.readonly`. Our bot will hold `youtube.force-ssl` for moderation anyway, and that scope also covers reading.
- The `list` page itself now says: *"To poll for live chat messages, use the `liveChatMessages.streamList` method ... which reduces the need for constant polling."*
- https://developers.google.com/youtube/v3/live/docs/liveChatMessages/list

### 1.3 `liveChatMessages.streamList` (server-streaming)

- **Availability:** generally available. The live API revision history (2025-07-14) says its description was "updated to provide guidance on the streamList API usages". It is the method Google now recommends.
- **What it does:** "establishes a server-streaming connection that lets you receive live chat messages for a specific chat with low latency". On connect it sends recent chat history, then pushes new messages as they arrive.
- **gRPC details** (from the official Python demo):
  - Endpoint: `dns:///youtube.googleapis.com:443` (TLS)
  - Proto: `stream_list.proto`, `package youtube.api.v3;`. The full proto text is printed on the guide page and has to be copied from there; I found no separate download.
  - Service: `V3DataLiveChatMessageService`, method `rpc StreamList(LiveChatMessageListRequest) returns (stream LiveChatMessageListResponse)`.
  - Request fields: `live_chat_id`, `part` (repeated: `id`, `snippet`, `authorDetails`), `max_results`, `page_token`, `hl`, `profile_image_size`.
  - Response fields: `items`, `next_page_token`, `offline_at`, `active_poll_item`, and others.
  - Auth metadata. API key: `("x-goog-api-key", KEY)`. OAuth: `("authorization", "Bearer " + TOKEN)`.
  - Python dependencies: `grpcio` and `grpcio-tools`. Generate stubs with `python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. stream_list.proto`.
  - Demo loop: `for response in stub.StreamList(request, metadata=md): ...; next_page_token = response.next_page_token`. When the stream ends, reconnect with that token.
  - Error codes: `PERMISSION_DENIED (7)`, `INVALID_ARGUMENT (3)`, `FAILED_PRECONDITION (9)`, `NOT_FOUND (5)`, and `RESOURCE_EXHAUSTED (8)` (quota or rate limit).
- **Quota:** listed as **5 units**, the same as `list`. **[UNCERTAIN]** Google does not say whether the 5 units are charged per connection or per pushed response. Open-source projects assume per connection, but nobody has published a measurement. Check the Cloud Console quota graph during a test stream.
- **Python client options:**
  1. Raw gRPC as above. This is the most direct and documented route.
  2. `google-api-python-client` now exposes `youtube.liveChat().messages().stream(liveChatId=..., part=...)` plus `stream_next()`, described as "load live chat through a server-streamed RPC". **[UNCERTAIN]** This is a REST binding over httplib2, and I have not confirmed that it delivers messages incrementally rather than buffering the whole response. Prefer raw gRPC.
  3. `google-api-python-client` `liveChatMessages().list()` for plain polling. Use it as the fallback.
  - Auth libraries: `google-auth` and `google-auth-oauthlib` (`InstalledAppFlow`) to get and refresh the OAuth token. Pass the access token in gRPC metadata.
- https://developers.google.com/youtube/v3/live/docs/liveChatMessages/streamList
- https://developers.google.com/youtube/v3/live/streaming-live-chat
- https://googleapis.github.io/google-api-python-client/docs/dyn/youtube_v3.youtube.v3.liveChat.messages.html
- https://developers.google.com/youtube/v3/live/revision_history

### 1.4 Quota budget (default project)

- **Default:** 10,000 units/day for all endpoints combined, except `search.list` and `videos.insert`, which have separate buckets. Resets at midnight Pacific Time. Every request costs at least 1 unit, including invalid ones.
- **Polling with `list` at 5 units/call** gives 2,000 calls/day:
  - every 5 s: about 3,600 units/h, so about 2.8 h of streaming per day
  - every 8 s: about 2,250 units/h, so about 4.4 h per day
- **Moderation is expensive:** `liveChatBans.insert` costs **200** units, so 10 bans use 2,000 units. `liveChatMessages.delete` costs 20.
- **Recommendation:** use `streamList`, keep a local quota counter, and apply for a quota extension (this goes through a YouTube API Services compliance audit) if streams are long. Developer Policies section III.D.3 covers this.
- https://developers.google.com/youtube/v3/determine_quota_cost
- https://developers.google.com/youtube/v3/getting-started#quota

**Quota cost table (verbatim from determine_quota_cost, 2026-10):**

| Method | Units |
|---|---|
| liveChatMessages list / streamList | 5 / 5 |
| liveChatMessages insert / delete / transition | 20 / 20 / 20 |
| liveChatBans insert / delete | 200 / 200 |
| liveChatModerators insert / delete / list | 200 / 200 / 50 |
| liveBroadcasts list | 1 |
| videos list | 1 |
| search list | own bucket, 100/day, 1 per call |

### 1.5 OAuth practicalities

- If the OAuth consent screen is left in **"Testing"** status, refresh tokens **expire after 7 days**. Set it to "In production" so the bot runs unattended. An unverified app with sensitive scopes shows a warning screen, but the owner can click through it, and use is capped at 100 users. That is fine for a single-channel bot.
- https://developers.google.com/identity/protocols/oauth2#expiration

---

## 2. Message object (`youtube#liveChatMessage`)

```
id, etag, kind
snippet:
  type, liveChatId, authorChannelId, publishedAt,
  hasDisplayContent, displayMessage,
  textMessageDetails{messageText},
  superChatDetails{amountMicros, currency, amountDisplayString, userComment, tier},
  superStickerDetails{...}, newSponsorDetails{memberLevelName, isUpgrade},
  memberMilestoneChatDetails{memberLevelName, memberMonth, userComment},
  membershipGiftingDetails{...}, giftMembershipReceivedDetails{...},
  userBannedDetails{bannedUserDetails, banType, banDurationSeconds},
  pollDetails{...}, giftEventDetails{...}, fanFundingEventDetails (legacy)
authorDetails:
  channelId, channelUrl, displayName, profileImageUrl,
  isVerified, isChatOwner, isChatSponsor (= channel member), isChatModerator
```

**`snippet.type` values (current docs):**

- `textMessageEvent`: an ordinary chat message
- `superChatEvent` and `superStickerEvent`: paid
- `newSponsorEvent`: a new member
- `memberMilestoneChatEvent`: a member anniversary message, which can include `userComment`
- `membershipGiftingEvent` and `giftMembershipReceivedEvent`: gifted memberships
- `giftEvent`: Jewels gifts, added 2026-03-26
- `pollEvent`
- `userBannedEvent`
- `tombstone`: "A message used to exist with this id ... but it has since been deleted". Use it to remove a message that is already on the overlay.
- `sponsorOnlyModeStartedEvent` and `sponsorOnlyModeEndedEvent`
- `chatEndedEvent`

`displayMessage` is missing for `chatEndedEvent` and `tombstone`. The older `messageDeletedEvent` / `messageRetractedEvent` types no longer appear on the resource page, and `tombstone` takes their place. **[INFERENCE]**

**Text the overlay must filter:** `textMessageDetails.messageText`, plus the free-text parts of other types: `superChatDetails.userComment`, `memberMilestoneChatDetails.userComment`, and `displayName`. All of these are user-controlled.

**Emoji [UNCERTAIN, community-observed, not documented]:**

- Standard emoji come through as Unicode characters in `messageText`.
- Channel and member custom emoji come through as text shortcodes, e.g. `:_emojiName:`. The pytchat docs say custom emoji are "represented by `:(shortcut text):`".
- YouTube's built-in "YouTube" emoji set may also arrive as `:shortcode:`.
- The Data API does not return image URLs for custom emoji. To render them as images you would need your own mapping. Otherwise strip them or show them as text.
- Sources: https://pypi.org/project/pytchat/0.4.5/ and https://developers.google.com/youtube/v3/live/docs/liveChatMessages

---

## 3. Moderation via API

| Action | Method | Quota | Scope |
|---|---|---|---|
| Delete a message | `liveChatMessages.delete?id=MSG_ID` | 20 | `youtube` or `youtube.force-ssl` |
| Timeout | `liveChatBans.insert` with `snippet.type=temporary`, `snippet.banDurationSeconds=N`, `snippet.bannedUserDetails.channelId`, `snippet.liveChatId` | 200 | same |
| Permanent ban | `liveChatBans.insert` with `snippet.type=permanent` | 200 | same |
| Unban | `liveChatBans.delete?id=BAN_ID` (the ban `id` is returned by insert, so store it) | 200 | same |
| Add a moderator | `liveChatModerators.insert` | 200 | same |

**Who can call these:** "The API request must be authorized by the channel owner or a moderator of the live chat."

- The easiest setup is to authorize the bot with the **channel owner's** Google account.
- A separate bot account also works, but it must be added as a moderator first, either in Studio or with `liveChatModerators.insert`.
- You cannot ban the owner or another moderator (403). Pre-filter on `isChatOwner` and `isChatModerator`.

**Errors to handle:**

- delete: 403 `forbidden` (cannot delete), 404 (message not found)
- bans: 403 (no permission, or target is owner/moderator), 400/404 (bad `liveChatId`, bad `channelId`, or chat not found)

**Quota warning:** because each ban costs 200 units, prefer **delete (20)** plus a local blocklist that hides that user from the overlay. Save API bans for repeat offenders.

- https://developers.google.com/youtube/v3/live/docs/liveChatBans/insert
- https://developers.google.com/youtube/v3/live/docs/liveChatMessages/delete
- https://developers.google.com/youtube/v3/determine_quota_cost

---

## 4. YouTube Studio live chat settings

These are set in Studio under Settings > Community, or per stream in Live Control Room > Edit > Customization.

- **Hold potentially inappropriate messages for review:**
  - Levels are **None**, **Basic** ("Hold potentially inappropriate messages"), and **Strict** ("Hold a broader range of potentially inappropriate messages"). Older UIs used Standard/Strict.
  - Held messages appear only to the owner and moderators, who choose SHOW or HIDE.
  - "If you take no action: Chat messages remain hidden from viewers."
  - https://support.google.com/youtube/answer/9826490
- **Blocked words** (channel-wide, Studio > Settings > Community > Automated filters):
  - "Live chat messages containing or closely matching these terms will also be blocked."
  - Matching is fuzzy and undocumented, so treat it as a first layer only.
  - https://support.google.com/youtube/answer/9483359
- **Block links:**
  - "Live chat messages with URLs are also blocked."
  - The newer Content controls page describes a "Link text" toggle that holds comments with hashtags and URLs. https://support.google.com/youtube/answer/16622701
- **Slow mode:** "limit how often each user can comment by setting a time limit between comments". **[UNCERTAIN]** The exact allowed range is not given on the help page; Studio takes a seconds value.
- **Subscribers-only mode:** "you can specify how long viewers must be subscribed". **[UNCERTAIN]** The exact duration choices are not listed on the help page. Third-party coverage mentions minutes, hours, days, weeks, months, and years.
- **Members-only mode:** only paid channel members can chat. The API emits `sponsorOnlyModeStartedEvent` and `sponsorOnlyModeEndedEvent` when it toggles.
- **Live commentary / Approved users mode:** only users on the Approved Users list can chat.
- **Hidden users:** Studio-level hide. Their messages are invisible to everyone else.
- **Do held messages reach the API? [UNCERTAIN, must test]:**
  - No official doc says either way.
  - The `liveChatMessage` resource has no held or review-status field, and nothing in the API exposes a review queue. That suggests the API returns only messages that are publicly visible, with held messages appearing only after a moderator approves them (SHOW). **[INFERENCE]**
  - Google's internal comment model does have a `heldForCreatorReviewStatus` field "currently only effective for live chat", which proves a held state exists server-side but says nothing about Data API exposure: https://google-api-content-warehouse.hexdocs.pm/0.4.0/GoogleApi.ContentWarehouse.V1.Model.YoutubeCommentsApiCommentEnforcementStatus.html
  - **Test protocol:** set Strict holding and add a test word to Blocked words. From a second account, post a held message and a blocked-word message, then check whether either appears in `list` or `streamList` output, both when the token belongs to the owner and when you use an API key.
  - Until confirmed, the local classifier must treat every message as unfiltered.

---

## 5. ToS and policy points

**YouTube API Services Developer Policies** (https://developers.google.com/youtube/terms/developer-policies):

- **III.I.2:** "you must not automate or trigger views, uploads, comments, likes, dislikes, or other actions without the user's prior specific and express consent."
  - **[INFERENCE]** The channel owner setting up the bot on their own channel is that consent.
  - Avoid automated *posting* that looks like spam, and never automate engagement.
- **III.I.4:** you must not "modify, interfere with, replace, or otherwise disable any functionality, data, or content". Its example is about links in players and API data.
  - **[INFERENCE]** Showing a filtered subset of chat on your own stream is normal practice.
  - Do not alter message text and present it as the user's words. Masking a word with asterisks or dropping the message is safer than rewriting it.
- **III.E.4.c/d:** stored authorized and non-authorized API data must be kept **no longer than 30 calendar days**. This covers logs of chat messages and user IDs, so rotate logs at or before 30 days. Ban records may need to be summarized, e.g. as channel IDs only.
- **III.E.4.g:** if you store user data, you must provide a way for users to request deletion, and honour it within 7 days.
- **III.E.4.h:** do not create new derived metrics from API Data. **[INFERENCE]** Per-message moderation scores used internally are unlikely to be the target, but do not publish derived per-user "toxicity scores".
- **III.A.2:** a privacy policy is required for API clients that access user data. It is needed for the audit and the quota extension.

**Live content responsibility:**

- Everything shown in the stream, including the chat overlay, must follow the Community Guidelines. A violation can lead to a Community Guidelines strike or the stream being taken down, and can restrict the channel's ability to go live. See "Avoid restrictions on YouTube live streaming": https://support.google.com/youtube/answer/2853834
- Google's live-streaming guidance also expects the producer to make a "good faith effort to monitor" the stream. **[UNCERTAIN]** This wording came from a search snippet; I did not locate it on a fetched page. See https://support.google.com/youtube/answer/2474026
- An unmoderated overlay that displays slurs counts as the channel's own content. This is the main reason for layered filtering.

**AI / synthetic content disclosure** (https://support.google.com/youtube/answer/14328491):

- Disclosure is required only for *realistic* altered or synthetic content: making a real person appear to say or do something, altering real events or places, realistic fake scenes, or AI music that is the main focus.
- Not required for clearly unrealistic or animated content, or for "production assistance".
- An AI agent visibly playing a video game is probably not "realistic A/S content". **[INFERENCE]**
- AI TTS voices that imitate a real person **would** need disclosure.
- The upload flow has an "AI use / altered content" setting. **[UNCERTAIN]** The help page documents no equivalent toggle for live streams. Disclose in the stream title or description and with an on-screen "AI-controlled" label.
- The API has `status.containsSyntheticMedia` on videos, added 2024-10-30, so it can be set programmatically on the VOD: https://developers.google.com/youtube/v3/revision_history

**Monetization:** the YPP "inauthentic content" update (2025-07-15) targets "mass-produced and repetitious" content. A 24/7 automated AI stream risks being judged repetitive, so add real variety and commentary.

- https://www.plagiarismtoday.com/2025/07/08/youtube-targets-inauthentic-content/
- YPP policy page: https://support.google.com/youtube/answer/1311392. It prohibits "AI-generated content made with generic or unoriginal templates giving the impression of mass production without adding the creator's original, authentic insights or perspective."

---

## 6. Local moderation tooling (RTX 4080, 16 GB)

### 6.1 Classifiers

| Model | How to run | Labels / output | Licence | Notes |
|---|---|---|---|---|
| **Detoxify `original`** (bert-base-uncased) | `pip install detoxify` (v0.5.2, 2024-02) | toxic(ity), severe_toxic(ity), obscene, threat, insult, identity_hate / identity_attack | Apache-2.0 (code and weights) | Fast, a few ms per message on GPU. Same model as `unitary/toxic-bert` on Hugging Face, but HF outputs differ slightly from the library. |
| **Detoxify `unbiased`** (roberta-base) | same | toxicity, severe_toxicity, obscene, threat, insult, identity_attack, sexual_explicit | Apache-2.0 | Trained to reduce identity-term bias. A good default for English chat. |
| **Detoxify `multilingual`** (xlm-roberta-base) | same | same 7 as unbiased | Apache-2.0 | en, fr, es, it, pt, tr, ru |
| `original-small`, `unbiased-small` (ALBERT) | same | same | Apache-2.0 | Lighter variants |
| **Llama Guard 3** | `ollama pull llama-guard3:8b` (4.9 GB) or `llama-guard3:1b` (1.6 GB) | `safe` / `unsafe` plus a category: S1 Violent Crimes, S2 Non-Violent Crimes, S3 Sex-Related Crimes, S4 Child Sexual Exploitation, S5 Defamation, S6 Specialized Advice, S7 Privacy, S8 IP, S9 Indiscriminate Weapons, **S10 Hate**, S11 Self-Harm, **S12 Sexual Content**, S13 Elections, S14 Code Interpreter Abuse (8B only) | Llama 3.1/3.2 Community License (needs "Built with Llama" attribution and the AUP) | Built for LLM prompt/response safety. It has **no general insult, harassment, or profanity category**, so it is weak at catching ordinary chat toxicity. Use it as a second-pass check for hate, sexual, and self-harm content. Languages: en, fr, de, hi, it, pt, es, th. |
| **ShieldGemma** | `ollama pull shieldgemma:2b` (1.7 GB), `:9b` (5.8 GB, the default), `:27b` (17 GB) | Yes / No per policy: sexually explicit, dangerous content, **hate**, **harassment** | Gemma Terms of Use (not OSI; permits commercial use, with a prohibited-use policy) | English only, 8K context. One call per policy, or put several policies in one prompt. |
| **IBM Granite Guardian 3.0** | `ollama pull granite3-guardian:2b` (2.7 GB) or `:8b` (5.8 GB) | Yes / No. Select the risk via the system prompt: `harm`, `social_bias`, `profanity`, `sexual_content`, `unethical_behavior`, `violence`, `jailbreak` | Apache-2.0 | Has a **profanity** risk. Single-token output, so it is fast. |
| **IBM Granite Guardian 4.1** | `ollama pull granite4.1-guardian` (8B, 6.9 GB, released 2026-04) | yes / no in `<score>` tags. Built-in criteria plus "Bring Your Own Criteria" | Apache-2.0 | Optional thinking mode, which is slower |
| **gpt-oss-safeguard** | `ollama pull gpt-oss-safeguard:20b` (14 GB, fits 16 GB VRAM) | A reasoned decision against **your own written policy**, with low, medium, or high reasoning effort | Apache-2.0 | Most flexible, but slowest. Too heavy to run alongside a game plus TTS on one 16 GB card. **[INFERENCE]** |

Sources:

- https://github.com/unitaryai/detoxify
- https://pypi.org/project/detoxify/
- https://huggingface.co/unitary/toxic-bert
- https://ollama.com/library/llama-guard3
- https://huggingface.co/meta-llama/Llama-Guard-3-8B
- https://ollama.com/library/shieldgemma
- https://ollama.com/library/granite3-guardian
- https://ollama.com/library/granite4.1-guardian
- https://ollama.com/library/gpt-oss-safeguard

**Suggested stack [INFERENCE]:**

1. Normalize the text (section 6.2).
2. Check it against a wordlist or regex.
3. Run Detoxify `unbiased` on the GPU, which takes milliseconds.
4. For borderline scores, or anything that will be read aloud, run an LLM guard: ShieldGemma 2b or 9b, or Granite Guardian, which covers harassment and profanity.
5. Default to deny on errors or timeouts.

VRAM: Detoxify needs about 0.5 GB, and a 2B guard needs about 2–3 GB.

### 6.2 Unicode confusables and evasion

| Tool | What it does | Licence | Notes |
|---|---|---|---|
| `unicodedata.normalize('NFKC', s)` (stdlib) | Folds compatibility forms: fullwidth letters, math alphanumerics like 𝕍, ligatures, superscripts | PSF | Always run this first. Then `casefold()`. |
| **`confusable_homoglyphs`** 3.3.1 (2024-01) | `is_dangerous`, `is_confusable`, `is_mixed_script`, built on Unicode confusables.txt and Scripts.txt | MIT | Detection only. **It does not produce a skeleton.** |
| **`confusables`** (woodgern) | `normalize(s, prioritize_alpha=True)` returns candidate ASCII forms, e.g. `'Ʀỏ𝕍3ℛ'` gives `['rov3r','rover']`; also `confusable_regex()` and `is_confusable()` | MIT | Data is Unicode 8.0.0, which is old. The README has a `make update` step for newer data. |
| **PyICU** `icu.SpoofChecker().getSkeleton(...)` | The real UTS #39 skeleton, maintained by ICU | PyICU MIT, ICU Unicode licence | **[UNCERTAIN]** Windows install is awkward: there are no official wheels, so you need conda (`conda install -c conda-forge pyicu`) or community wheels. https://gitlab.pyicu.org/main/pyicu |
| **`Unidecode`** 1.4.0 (2025-04) | Transliterates Unicode to ASCII | **GPL-2.0+** | Copyleft, which matters if the project is distributed. Context-free. |
| **`anyascii`** 0.3.3 (2025-06) | Transliterates Unicode to ASCII | **ISC** (permissive) | Drop-in alternative to Unidecode with a permissive licence |

Spec: UTS #39 (https://www.unicode.org/reports/tr39/) and confusables.txt (https://www.unicode.org/Public/security/latest/confusables.txt).

**Also needed** (well-known techniques, not from a specific source):

- Strip zero-width and format characters (category `Cf`: U+200B–U+200D, U+2060, U+FEFF) and combining marks (category `Mn`, after NFD) for "zalgo" text.
- Collapse repeated letters.
- Map leetspeak (0→o, 1→i/l, 3→e, 4→a, 5→s, 7→t, @→a, $→s).
- Match against a de-spaced copy as well ("f u c k").

Sources:

- https://pypi.org/project/confusable-homoglyphs/
- https://github.com/woodgern/confusables
- https://pypi.org/project/Unidecode/
- https://pypi.org/project/anyascii/

### 6.3 Profanity and slur lists

| List | Size / format | Licence | Notes |
|---|---|---|---|
| **LDNOOBW** (List of Dirty, Naughty, Obscene and Otherwise Bad Words) | Plain text, 27 languages | **CC-BY-4.0** (attribution required) | Originally from Shutterstock. Subjective, includes many non-slur sexual terms. https://github.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words |
| **dsojevic/profanity-list** | JSON: 434 English entries / 809 match patterns, severity 1–4, tags (`racial`, `lgbtq`, `religious`, `sexual`, `shock`, `general`), exceptions; also an emoji set | **MIT** | The best fit for tiered blocking, e.g. always block slurs tagged racial or lgbtq. https://github.com/dsojevic/profanity-list |
| **cuss** (wooorm) | About 1,770 English words with a 0–2 likelihood rating; also es, fr, it, pt, ar-latn | **MIT** | Its README warns it is for research, not filters. Use the rating-2 words. https://github.com/wooorm/cuss |
| **Surge AI profanity dataset** | 1,600+ English terms, 1–3 severity, categories (racial/ethnic, sexual orientation/gender, disability, etc.) | **[UNCERTAIN]** I believe MIT, but the original GitHub repo (`surge-ai/profanity`) now returns 404 | https://www.surgehq.ai/blog/the-obscenity-list-surge |
| **better_profanity** (Python) | Built-in wordlist plus leetspeak variant generation | MIT | v0.7.0 from 2020, unmaintained. Easy to evade by adding characters. |

**Recommendation [INFERENCE]:**

- Keep a small, hand-curated **hard-block list** (slurs, from dsojevic's severity 3–4 / racial / lgbtq tags plus LDNOOBW English) and match it after normalization. Use substring and regex matching with an exceptions list to avoid the "Scunthorpe problem".
- Leave mild profanity to the classifier thresholds.
- Credit LDNOOBW if it is used (CC-BY).

---

## Open questions to test early

1. Do Studio-held or blocked-word messages ever appear in `list` or `streamList`? (Section 4)
2. Is `streamList` charged 5 units per connection or per response? Measure it on the Cloud Console quota graph.
3. Does `liveChatMessages.list` / `streamList` with only an API key work for our own public stream? It is expected to.
4. How do custom and member emoji appear in `messageText`?
5. Does Live Control Room have an AI or altered-content toggle for live streams?
