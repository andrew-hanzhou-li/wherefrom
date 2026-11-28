// The extension's decisions (wherefrom/extension/logic.js). Run with
// `node --test tests/extension/logic.test.js`; tests/test_extension_logic.py
// runs it as part of pytest.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const L = require(path.join(__dirname, "..", "..", "wherefrom", "extension", "logic.js"));

test("siteOf finds the site of ordinary, blob and odd links", () => {
  assert.equal(L.siteOf("https://www.Example.com/files/a.pdf"), "example.com");
  assert.equal(L.siteOf("http://cdn.example.com:8080/x"), "cdn.example.com");
  assert.equal(L.siteOf("blob:https://drive.example.org/1b2c-3d"), "drive.example.org");
  assert.equal(L.siteOf("data:application/pdf;base64,AAAA"), null);
  assert.equal(L.siteOf("file:///C:/x.pdf"), null);
  assert.equal(L.siteOf("not a link"), null);
  assert.equal(L.siteOf(""), null);
  assert.equal(L.siteOf(undefined), null);
});

test("normalizeSite accepts what people type and refuses the rest", () => {
  assert.equal(L.normalizeSite("example.com"), "example.com");
  assert.equal(L.normalizeSite("  https://www.Example.com/some/page?q=1 "), "example.com");
  assert.equal(L.normalizeSite("sub.example.co.uk"), "sub.example.co.uk");
  assert.equal(L.normalizeSite("localhost"), "localhost");
  assert.equal(L.normalizeSite("127.0.0.1"), "127.0.0.1");
  assert.equal(L.normalizeSite("nodot"), null);
  assert.equal(L.normalizeSite("exa mple.com"), null);
  assert.equal(L.normalizeSite(""), null);
  assert.equal(L.normalizeSite(null), null);
});

test("an excluded site covers its subdomains but not look-alikes", () => {
  assert.equal(L.siteMatches("example.com", ["example.com"]), true);
  assert.equal(L.siteMatches("cdn.example.com", ["example.com"]), true);
  assert.equal(L.siteMatches("notexample.com", ["example.com"]), false);
  assert.equal(L.siteMatches("example.com.evil.net", ["example.com"]), false);
  assert.equal(L.siteMatches(null, ["example.com"]), false);
});

test("a download is excluded by its link, final link or page", () => {
  const ex = ["bank.example"];
  assert.equal(L.excludedBy({ url: "https://bank.example/s.pdf" }, ex), "bank.example");
  assert.equal(L.excludedBy({ url: "https://short.link/x", finalUrl: "https://files.bank.example/s.pdf" }, ex), "bank.example");
  assert.equal(L.excludedBy({ url: "https://cdn.net/s.pdf", referrer: "https://www.bank.example/statements" }, ex), "bank.example");
  assert.equal(L.excludedBy({ url: "https://cdn.net/s.pdf", referrer: "" }, ex), null);
  assert.equal(L.excludedBy({ url: "https://bank.example/s.pdf" }, []), null);
});

test("data: links shrink to their header; long links are cut", () => {
  assert.equal(L.shortenUrl("data:application/pdf;base64,JVBERi0xLjQK" + "A".repeat(5000)), "data:application/pdf;base64,…");
  assert.equal(L.shortenUrl("data:,hello"), "data:,…");
  const long = "https://example.com/?" + "q".repeat(9000);
  assert.equal(L.shortenUrl(long).length, L.MAX_URL + 1);
  assert.equal(L.shortenUrl("https://example.com/a"), "https://example.com/a");
  assert.equal(L.shortenUrl(""), null);
});

test("the message carries the final link, the first link and the page", () => {
  const m = L.buildMessage({
    filename: "C:\\Users\\me\\Downloads\\r.csv", url: "https://e.com/redirect", finalUrl: "https://cdn.e.com/r.csv",
    referrer: "https://e.com/page", mime: "text/csv", fileSize: 8, endTime: "2026-11-28T10:00:00.000Z",
  });
  assert.deepEqual(m, {
    type: "download", path: "C:\\Users\\me\\Downloads\\r.csv", url: "https://cdn.e.com/r.csv",
    original_url: "https://e.com/redirect", referrer: "https://e.com/page", mime: "text/csv", size: 8,
    ended: "2026-11-28T10:00:00.000Z",
  });
  const firefox = L.buildMessage({ filename: "/home/me/r.csv", url: "https://e.com/r.csv", referrer: "" });
  assert.equal(firefox.url, "https://e.com/r.csv");          // Firefox has no finalUrl
  assert.equal(firefox.referrer, null);
});

test("fileName works for Windows and POSIX paths", () => {
  assert.equal(L.fileName("C:\\Users\\me\\Downloads\\a b.pdf"), "a b.pdf");
  assert.equal(L.fileName("/home/me/Downloads/r.csv"), "r.csv");
  assert.equal(L.fileName(undefined), "");
});

test("replies: recorded, already known, retry only when the file couldn't be read", () => {
  assert.equal(L.classifyReply({ ok: true, new: true }).outcome, "recorded");
  assert.equal(L.classifyReply({ ok: true, new: false }).outcome, "known");
  assert.equal(L.classifyReply({ ok: false, error: "can't read the file: Permission denied" }).outcome, "retry");
  for (const error of ["file not found", "no source", "no full path", "unknown message"]) {
    assert.equal(L.classifyReply({ ok: false, error }).outcome, "final", error);
  }
  assert.equal(L.classifyReply(undefined).outcome, "retry");
});

test("the browsers' connection errors are told apart", () => {
  // Chrome
  assert.equal(L.classifyError("Specified native messaging host not found."), "missing");
  assert.equal(L.classifyError("Access to the specified native messaging host is forbidden."), "forbidden");
  assert.equal(L.classifyError("Native host has exited."), "error");
  assert.equal(L.classifyError("Error when communicating with the native messaging host."), "error");
  // Firefox
  assert.equal(L.classifyError("No such native application com.wherefrom.host"), "missing");
  assert.equal(L.classifyError("An unexpected error occurred"), "error");
});

test("retries back off and then hold at two hours", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 9].map(L.retryDelay), [1, 1, 5, 30, 120, 120]);
});

test("the waiting list replaces duplicates and drops the oldest when full", () => {
  let q = [];
  for (let i = 0; i < L.QUEUE_LIMIT; i++) q = L.enqueue(q, { id: i, added: i }).queue;
  let r = L.enqueue(q, { id: 5, added: 999 });                  // same download again: no growth
  assert.equal(r.queue.length, L.QUEUE_LIMIT);
  assert.equal(r.dropped, 0);
  r = L.enqueue(r.queue, { id: "new", added: 1000 });
  assert.equal(r.dropped, 1);
  assert.equal(r.queue[0].id, 1);                               // id 0 was the oldest
  assert.equal(r.queue[r.queue.length - 1].id, "new");
});

test("entries older than the limit expire", () => {
  const day = 24 * 60 * 60 * 1000, now = 100 * day;
  const r = L.expire([{ id: 1, added: now - 15 * day }, { id: 2, added: now - day }], now);
  assert.deepEqual(r.queue.map((q) => q.id), [2]);
  assert.equal(r.dropped, 1);
});

test("Recent keeps the newest and updates an entry in place", () => {
  let recent = [];
  for (let i = 1; i <= 10; i++) recent = L.upsertRecent(recent, { id: i, time: i, state: "waiting" });
  assert.equal(recent.length, L.RECENT_LIMIT);
  assert.equal(recent[0].id, 10);
  recent = L.upsertRecent(recent, { id: 9, state: "recorded" });
  const nine = recent.find((r) => r.id === 9);
  assert.equal(nine.state, "recorded");
  assert.equal(nine.time, 9);                                   // the rest of the entry is kept
});

test("ago reads naturally", () => {
  const m = 60000;
  assert.equal(L.ago(0, 30000), "just now");
  assert.equal(L.ago(0, 5 * m), "5 min ago");
  assert.equal(L.ago(0, 3 * 60 * m), "3 h ago");
  assert.equal(L.ago(0, 24 * 60 * m), "1 day ago");
  assert.equal(L.ago(0, 3 * 24 * 60 * m), "3 days ago");
});
