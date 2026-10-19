// ==UserScript==
// @name         TimberLive poll counter
// @namespace    timberlive
// @version      1.1
// @description  Counts 1/2/3 votes and first-time chatters in YouTube live chat (Studio or pop-out) and sends ONLY the numbers to the local overlay.
// @match        https://www.youtube.com/live_chat*
// @match        https://studio.youtube.com/live_chat*
// @updateURL    http://127.0.0.1:8096/timberlive-poll.user.js
// @downloadURL  http://127.0.0.1:8096/timberlive-poll.user.js
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

// Chat text, names and IDs stay in this page. The overlay server only accepts
// {id, counts: [ints], voters: int} and {new: int}, so nothing else can reach Claude
// or the stream. The ticker turns {new: 3} into "Welcome to the 3 new people in chat!".
(function () {
  "use strict";
  const OVERLAY = "http://127.0.0.1:8096";
  const VOTE = /^!?\s*(?:vote\s*)?([1-9])$/;
  let pollId = null, options = 0, opened = false;
  let ignored = new Set(), votes = new Map(), lastSent = "";
  // Welcomes: authors seen this session (kept in this page only) and how many are new since
  // the last welcome. People already in chat when the script loads don't count as new.
  const seenMessages = new Set(), seenAuthors = new Set();
  let newChatters = 0, primed = false;

  function request(method, path, body, onload) {
    GM_xmlhttpRequest({
      method, url: OVERLAY + path,
      headers: { "Content-Type": "application/json", "X-TimberLive-Poll": "1" },
      data: body ? JSON.stringify(body) : undefined,
      onload: r => onload && onload(r), onerror: () => {},
    });
  }

  function messages() {
    return document.querySelectorAll("yt-live-chat-text-message-renderer");
  }

  function checkPoll() {
    request("GET", "/state.json", null, r => {
      let poll = null;
      try { poll = JSON.parse(r.responseText).poll || null; } catch (e) { return; }
      const now = Date.now() / 1000;
      opened = !!poll && !poll.closed && now < poll.closes + 8;
      if (poll && poll.id !== pollId) {
        // New poll: anything already in chat doesn't count.
        pollId = poll.id; options = poll.options.length; votes = new Map(); lastSent = "";
        ignored = new Set([...messages()].map(m => m.id));
      }
    });
  }

  function count() {
    if (!opened || pollId === null) return;
    for (const m of messages()) {
      if (!m.id || ignored.has(m.id)) continue;
      ignored.add(m.id);
      const text = (m.querySelector("#message")?.textContent || "").normalize("NFKC").trim().toLowerCase();
      const author = m.querySelector("#author-name")?.textContent?.trim();
      const match = VOTE.exec(text);
      const choice = match ? Number(match[1]) : 0;
      if (author && choice >= 1 && choice <= options) votes.set(author, choice);
    }
    const counts = new Array(options).fill(0);
    for (const c of votes.values()) counts[c - 1]++;
    const payload = { id: pollId, counts, voters: votes.size };
    const key = JSON.stringify(payload);
    if (key !== lastSent) { lastSent = key; request("POST", "/poll_counts", payload); }
  }

  function scanChatters() {
    for (const m of messages()) {
      if (!m.id || seenMessages.has(m.id)) continue;
      seenMessages.add(m.id);
      if (m.getAttribute("author-type") === "owner") continue;   // the channel itself
      const author = m.querySelector("#author-name")?.textContent?.trim();
      if (!author || seenAuthors.has(author)) continue;
      seenAuthors.add(author);
      if (primed) newChatters++;
    }
  }

  function sendWelcome() {
    // The server keeps at most one welcome per 3 minutes; unsent people roll into the next one.
    if (newChatters < 1) return;
    const n = newChatters;
    request("POST", "/welcome", { new: n }, r => {
      try { if (JSON.parse(r.responseText).ok) newChatters -= n; } catch (e) {}
    });
  }

  checkPoll();
  setInterval(checkPoll, 3000);
  setInterval(count, 1000);
  setInterval(scanChatters, 2000);
  setTimeout(() => { scanChatters(); primed = true; }, 10000);   // chat backlog has loaded by then
  setInterval(sendWelcome, 30000);
})();
