// wherefrom browser extension: when a download finishes, tell wherefrom
// (through the browser's native messaging) where it came from.
//
// It sends one small message per finished download and nothing else: no
// browsing history, no page contents. Private/incognito downloads are never
// sent. If wherefrom can't be reached, downloads wait here (up to 14 days)
// and are sent once it can.
//
// This script is the only part that talks to wherefrom or changes what the
// extension keeps; the popup and the welcome page ask it by message.

if (typeof importScripts === "function" && typeof WherefromLogic === "undefined") {
  importScripts("logic.js");      // Chrome's service worker; Firefox lists logic.js itself
}

const api = globalThis.browser ?? globalThis.chrome;
const L = WherefromLogic;
const HOST = "com.wherefrom.host";
const ALARM = "wherefrom-retry";
const DEFAULTS = {
  settings: { paused: false, excluded: [] },
  queue: [],          // downloads waiting to be sent: {key, downloadId, added, attempts, message}
  recent: [],         // what the popup shows: {key, downloadId, name, site, time, state, detail}
  status: { state: "unknown" },
  dropped: 0,         // downloads given up on because the waiting list was full or too old
  failures: 0,        // failed rounds in a row, for backing off
};

// ---- One change at a time ------------------------------------------------
// Downloads, the retry alarm and the popup can all arrive together; each
// change runs after the previous one finishes, so none is lost.
let chain = Promise.resolve();
function locked(fn) {
  const run = chain.then(() => fn());
  chain = run.catch(() => {});
  return run;
}

async function load() {
  const stored = await api.storage.local.get(Object.keys(DEFAULTS));
  const state = {};
  for (const [key, value] of Object.entries(DEFAULTS)) {
    state[key] = stored[key] === undefined ? structuredClone(value) : stored[key];
  }
  state.settings = { ...DEFAULTS.settings, ...state.settings };
  return state;
}

// ---- Talking to wherefrom --------------------------------------------------
// One connection per round: wherefrom answers any number of messages on it,
// so a long waiting list starts the program once, not once per download.
function connect() {
  const port = api.runtime.connectNative(HOST);
  const waiting = [];
  let closed = null;
  port.onMessage.addListener((reply) => {
    const next = waiting.shift();
    if (next) next.resolve(reply);
  });
  port.onDisconnect.addListener((p) => {
    closed = (api.runtime.lastError && api.runtime.lastError.message) ||
      (p && p.error && p.error.message) || "wherefrom closed the connection";
    while (waiting.length) waiting.shift().reject(new Error(closed));
  });
  return {
    ask(message, ms) {
      if (closed) return Promise.reject(new Error(closed));
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          reject(new Error("wherefrom didn't answer in time"));
          try { port.disconnect(); } catch (e) { /* already closed */ }
        }, ms);
        waiting.push({
          resolve: (v) => { clearTimeout(timer); resolve(v); },
          reject: (e) => { clearTimeout(timer); reject(e); },
        });
        try {
          port.postMessage(message);
        } catch (error) {
          waiting.pop();
          clearTimeout(timer);
          reject(new Error(closed || String(error && error.message || error)));
        }
      });
    },
    close() { try { port.disconnect(); } catch (e) { /* already closed */ } },
  };
}

const NOT_RECORDED = {
  "file not found": "The file was moved or deleted before it could be recorded.",
  "no source": "The browser didn't say where it came from.",
  "no full path": "The browser didn't say where it saved the file.",
};

/** Send everything waiting, and find out whether wherefrom is there. */
function drain() {
  return locked(async () => {
    const s = await load();
    const now = Date.now();
    const expired = L.expire(s.queue, now);
    if (expired.dropped) {
      const gone = new Set(s.queue.filter((q) => !expired.queue.includes(q)).map((q) => q.key));
      s.recent = s.recent.map((r) => gone.has(r.key) ? { ...r, state: "expired", detail: "" } : r);
      s.queue = expired.queue;
      s.dropped += expired.dropped;
    }
    if (s.settings.paused) {
      await api.storage.local.set({ queue: s.queue, recent: s.recent, dropped: s.dropped });
      await showBadge(s.status, s.settings);
      return s.status;
    }

    const host = connect();
    let status;
    try {
      const pong = await host.ask({ type: "ping" }, 15000);
      // Any answer means it's there; wherefrom 0.3 and older don't know "ping" or say their version
      status = { state: "connected", version: (pong && pong.ok && pong.version) || null, checked: now };
      for (const entry of [...s.queue]) {
        const reply = await host.ask(entry.message, 120000);   // big files take a while to fingerprint
        const { outcome, detail } = L.classifyReply(reply);
        let update;
        if (outcome === "retry") {
          entry.attempts = (entry.attempts || 0) + 1;
          if (entry.attempts < L.READ_ATTEMPTS) {
            update = { state: "waiting", detail: "wherefrom couldn't read the file yet; trying again soon." };
          } else {
            s.queue = s.queue.filter((q) => q.key !== entry.key);
            update = { state: "failed", detail: "wherefrom couldn't read the file: " + detail.replace(/^can't read the file:\s*/i, "") };
          }
        } else {
          s.queue = s.queue.filter((q) => q.key !== entry.key);
          update = outcome === "final"
            ? { state: "final", detail: NOT_RECORDED[detail] || detail }
            : { state: outcome, detail: "" };
        }
        s.recent = s.recent.map((r) => r.key === entry.key ? { ...r, ...update } : r);
      }
      s.failures = s.queue.length ? s.failures + 1 : 0;
    } catch (error) {
      const message = String(error && error.message || error);
      status = { state: L.classifyError(message), detail: message, checked: now };
      s.failures += 1;
    } finally {
      host.close();
    }

    await api.storage.local.set({ queue: s.queue, recent: s.recent, status, failures: s.failures, dropped: s.dropped });
    if (s.queue.length) {
      api.alarms.create(ALARM, { delayInMinutes: L.retryDelay(s.failures) });
    } else {
      await api.alarms.clear(ALARM);
    }
    await showBadge(status, s.settings);
    return status;
  });
}

// ---- The toolbar icon ------------------------------------------------------
async function showBadge(status, settings) {
  let text = "", color = "#166088", title = "wherefrom: recording downloads";
  if (settings.paused) {
    text = "off"; color = "#66737c"; title = "wherefrom: paused";
  } else if (status.state === "missing") {
    text = "!"; color = "#b3261e"; title = "wherefrom isn't set up on this computer";
  } else if (status.state === "forbidden") {
    text = "!"; color = "#b3261e"; title = "wherefrom doesn't recognise this copy of the extension yet";
  } else if (status.state === "error") {
    text = "!"; color = "#b3261e"; title = "wherefrom didn't answer";
  }
  try {
    await api.action.setBadgeBackgroundColor({ color });
    await api.action.setBadgeText({ text });
    await api.action.setTitle({ title });
  } catch (e) { /* the icon isn't essential */ }
}

// ---- Downloads -------------------------------------------------------------
async function capture(downloadId) {
  const [item] = await api.downloads.search({ id: downloadId });
  if (!item || !item.filename || item.incognito) return;
  const added = await locked(async () => {
    const s = await load();
    if (s.settings.paused || L.excludedBy(item, s.settings.excluded)) return false;
    const key = downloadId + "|" + (item.startTime || "");
    const now = Date.now();
    const queued = L.enqueue(s.queue, { key, downloadId, added: now, attempts: 0, message: L.buildMessage(item) });
    const recent = L.upsertRecent(s.recent, {
      key, downloadId, name: L.fileName(item.filename),
      site: L.siteOf(item.finalUrl || item.url) || L.siteOf(item.referrer) || "",
      time: now, state: "waiting", detail: "",
    });
    await api.storage.local.set({ queue: queued.queue, recent, dropped: s.dropped + queued.dropped });
    return true;
  });
  if (added) await drain();
}

// ---- Commands from the popup and the welcome page --------------------------
async function command(message) {
  switch (message && message.cmd) {
    case "check":
      return { ok: true, status: await drain() };
    case "pause":
      await locked(async () => {
        const s = await load();
        s.settings.paused = Boolean(message.value);
        await api.storage.local.set({ settings: s.settings });
        await showBadge(s.status, s.settings);
      });
      if (!message.value) await drain();
      return { ok: true };
    case "exclude":
    case "include": {
      const site = message.cmd === "exclude" ? L.normalizeSite(message.site) : message.site;
      if (!site) return { ok: false, error: "That doesn't look like a site, e.g. example.com" };
      await locked(async () => {
        const s = await load();
        const others = s.settings.excluded.filter((x) => x !== site);
        s.settings.excluded = message.cmd === "exclude" ? [...others, site].sort() : others;
        await api.storage.local.set({ settings: s.settings });
      });
      return { ok: true, site };
    }
    case "show":
      // The file in its folder (the browser's own "Show in folder")
      try {
        await api.downloads.show(Number(message.downloadId));
        return { ok: true };
      } catch (error) {
        return { ok: false, error: "The browser no longer knows this download." };
      }
    case "clear-recent":
      await locked(() => api.storage.local.set({ recent: [] }));
      return { ok: true };
    default:
      return { ok: false, error: "unknown command" };
  }
}

// ---- Listeners (registered at once, so the browser can wake this script) ---
api.downloads.onChanged.addListener((delta) => {
  if (delta.state && delta.state.current === "complete") capture(delta.id);
});

// Removed from the browser's download list (e.g. "Clear browsing data"): forget it here too
api.downloads.onErased.addListener((downloadId) => {
  locked(async () => {
    const s = await load();
    await api.storage.local.set({
      queue: s.queue.filter((q) => q.downloadId !== downloadId),
      recent: s.recent.filter((r) => r.downloadId !== downloadId),
    });
  });
});

api.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM) drain();
});

api.runtime.onStartup.addListener(() => { drain(); });

api.runtime.onInstalled.addListener(async (details) => {
  const status = await drain();
  if (details.reason === "install" && status.state !== "connected") {
    api.tabs.create({ url: api.runtime.getURL("welcome.html") });
  }
});

api.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== api.runtime.id) return false;
  command(message).then(sendResponse, (error) => sendResponse({ ok: false, error: String(error && error.message || error) }));
  return true;      // answering later
});
