// wherefrom browser extension: when a download finishes, tell wherefrom
// (through the browser's native messaging) where it came from.
//
// It sends one small message per finished download and nothing else: no
// browsing history, no page contents. Private/incognito downloads are never
// sent.

const api = globalThis.browser ?? globalThis.chrome;
const HOST = "com.wherefrom.host";

api.downloads.onChanged.addListener(async (delta) => {
  if (!delta.state || delta.state.current !== "complete") return;
  const [item] = await api.downloads.search({ id: delta.id });
  if (!item || !item.filename || item.incognito) return;
  const message = {
    type: "download",
    path: item.filename,                    // full path of the saved file
    url: item.finalUrl || item.url,         // where the bytes came from, after redirects
    original_url: item.url,                 // what was first asked for
    referrer: item.referrer || null,        // usually the page the link was on
    mime: item.mime || null,
    size: item.fileSize ?? null,
    ended: item.endTime || null,
  };
  try {
    await api.runtime.sendNativeMessage(HOST, message);
  } catch (error) {
    // wherefrom isn't set up on this computer: run "wherefrom browser setup"
    console.warn("wherefrom: couldn't reach the wherefrom program:", error);
  }
});
