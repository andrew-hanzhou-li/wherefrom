// wherefrom extension: the decisions, kept free of browser APIs so they can
// be tested on their own (tests/extension/logic.test.js) and shared by the
// background script and the popup.
//
// Loaded as a classic script (Chrome: importScripts, Firefox: listed before
// background.js, pages: <script src>), so it defines one global and nothing
// else at the top level.

var WherefromLogic = (function () {
  "use strict";

  var MAX_URL = 8000;             // the wherefrom program ignores fields over 8192 characters
  var QUEUE_LIMIT = 200;          // downloads kept while waiting for wherefrom
  var QUEUE_DAYS = 14;            // and for how long
  var READ_ATTEMPTS = 5;          // tries when wherefrom couldn't read the file yet
  var RECENT_LIMIT = 8;
  var RETRY_MINUTES = [1, 5, 30, 120];
  var DAY = 24 * 60 * 60 * 1000;

  /** The site a link belongs to, lowercase and without "www.", or null. */
  function siteOf(url) {
    if (typeof url !== "string" || !url) return null;
    if (/^data:/i.test(url)) return null;
    if (/^blob:/i.test(url)) url = url.slice(5);          // blob:https://site/uuid
    try {
      var host = new URL(url).hostname.toLowerCase();
      if (!host) return null;
      return host.replace(/^www\./, "");
    } catch (e) {
      return null;
    }
  }

  /** What someone typed as a site ("https://www.Example.com/x", "example.com") -> "example.com", or null. */
  function normalizeSite(input) {
    if (typeof input !== "string") return null;
    var text = input.trim();
    if (!text) return null;
    if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(text)) text = "https://" + text;
    var site = siteOf(text);
    if (!site || !/^[a-z0-9.-]+$/.test(site) || site.indexOf(".") === -1 && site !== "localhost") return null;
    return site;
  }

  /** True if `site` is, or is under, any excluded site. */
  function siteMatches(site, excluded) {
    if (!site) return false;
    for (var i = 0; i < excluded.length; i++) {
      var ex = excluded[i];
      if (site === ex || site.slice(-(ex.length + 1)) === "." + ex) return true;
    }
    return false;
  }

  /** The excluded site that matches this download (its link, final link or page), or null. */
  function excludedBy(item, excluded) {
    var links = [item.finalUrl, item.url, item.referrer];
    for (var i = 0; i < links.length; i++) {
      var site = siteOf(links[i]);
      for (var j = 0; j < excluded.length; j++) {
        if (siteMatches(site, [excluded[j]])) return excluded[j];
      }
    }
    return null;
  }

  /** A link as it's sent to wherefrom: a data: link (the whole file, inside
   * the link) becomes just its header; anything too long is cut. */
  function shortenUrl(url) {
    if (typeof url !== "string" || !url) return null;
    var data = /^data:([^,]*),/i.exec(url);
    if (data) return "data:" + data[1] + ",…";
    if (url.length > MAX_URL) return url.slice(0, MAX_URL) + "…";
    return url;
  }

  /** The message for wherefrom about one finished download. */
  function buildMessage(item) {
    var url = shortenUrl(item.finalUrl || item.url);
    var original = shortenUrl(item.url);
    return {
      type: "download",
      path: item.filename,
      url: url,
      original_url: original,
      referrer: shortenUrl(item.referrer) || null,
      mime: item.mime || null,
      size: typeof item.fileSize === "number" ? item.fileSize : null,
      ended: item.endTime || null,
    };
  }

  /** The file name from a full path (Windows or POSIX). */
  function fileName(path) {
    if (typeof path !== "string") return "";
    var parts = path.split(/[\\/]/);
    return parts[parts.length - 1] || path;
  }

  /** What wherefrom's reply means: "recorded", "known" (seen before),
   * "retry" (it couldn't read the file yet) or "final" (won't work later either). */
  function classifyReply(reply) {
    if (!reply || typeof reply !== "object") return { outcome: "retry", detail: "no answer" };
    if (reply.ok) return { outcome: reply.new === false ? "known" : "recorded", detail: "" };
    var error = String(reply.error || "unknown error");
    if (/^can't read the file/i.test(error)) return { outcome: "retry", detail: error };
    return { outcome: "final", detail: error };
  }

  /** Why the browser couldn't reach wherefrom, from its error message:
   * "missing" (not installed or not set up), "forbidden" (set up, but not
   * for this copy of the extension) or "error" (it started and failed). */
  function classifyError(message) {
    var text = String(message || "");
    if (/forbidden/i.test(text)) return "forbidden";
    if (/not found|no such native application|not registered|cannot find/i.test(text)) return "missing";
    return "error";
  }

  /** Minutes until the next retry after `failures` failed rounds in a row. */
  function retryDelay(failures) {
    var i = Math.max(0, Math.min(failures, RETRY_MINUTES.length) - 1);
    return RETRY_MINUTES[i];
  }

  /** Add a download to the waiting list (replacing an older entry for the
   * same download). Returns {queue, dropped}: the oldest go when it's full. */
  function enqueue(queue, entry) {
    var next = queue.filter(function (q) { return q.id !== entry.id; });
    next.push(entry);
    var dropped = Math.max(0, next.length - QUEUE_LIMIT);
    return { queue: next.slice(dropped), dropped: dropped };
  }

  /** Drop entries waiting longer than the limit. Returns {queue, dropped}. */
  function expire(queue, now) {
    var keep = queue.filter(function (q) { return now - q.added < QUEUE_DAYS * DAY; });
    return { queue: keep, dropped: queue.length - keep.length };
  }

  /** Put or update a Recent entry (newest first, limited). */
  function upsertRecent(recent, entry) {
    var others = recent.filter(function (r) { return r.id !== entry.id; });
    var old = recent.filter(function (r) { return r.id === entry.id; })[0];
    var merged = Object.assign({}, old || {}, entry);
    return [merged].concat(others).sort(function (a, b) { return b.time - a.time; }).slice(0, RECENT_LIMIT);
  }

  /** "just now", "5 min ago", "3 h ago", "2 days ago". */
  function ago(then, now) {
    var minutes = Math.floor((now - then) / 60000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return minutes + " min ago";
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + " h ago";
    var days = Math.floor(hours / 24);
    return days === 1 ? "1 day ago" : days + " days ago";
  }

  return {
    MAX_URL: MAX_URL, QUEUE_LIMIT: QUEUE_LIMIT, QUEUE_DAYS: QUEUE_DAYS, READ_ATTEMPTS: READ_ATTEMPTS,
    RECENT_LIMIT: RECENT_LIMIT, RETRY_MINUTES: RETRY_MINUTES,
    siteOf: siteOf, normalizeSite: normalizeSite, siteMatches: siteMatches, excludedBy: excludedBy,
    shortenUrl: shortenUrl, buildMessage: buildMessage, fileName: fileName,
    classifyReply: classifyReply, classifyError: classifyError, retryDelay: retryDelay,
    enqueue: enqueue, expire: expire, upsertRecent: upsertRecent, ago: ago,
  };
})();

if (typeof module === "object" && module.exports) module.exports = WherefromLogic;
