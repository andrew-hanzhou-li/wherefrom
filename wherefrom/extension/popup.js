// The toolbar popup: whether wherefrom is connected, recent downloads,
// pausing, and sites not to record. It only draws what the background script
// keeps, and asks it (by message) to change anything.
(function () {
  "use strict";
  var UI = WherefromUI, L = WherefromLogic, el = UI.el;
  var install = { href: UI.REPO + "#install", label: "Get wherefrom" };

  var LABELS = {
    recorded: "Recorded", known: "Already known", waiting: "Waiting",
    final: "Not recorded", failed: "Not recorded", expired: "Gave up",
  };

  function check() { return UI.ask({ cmd: "check" }); }

  function renderRecent(recent, now) {
    var list = document.getElementById("recent");
    list.replaceChildren();
    recent.forEach(function (r) {
      var meta = el("span", { class: "meta" });
      if (r.site) {
        meta.appendChild(el("span", { text: r.site + " ·" }));
      }
      meta.appendChild(el("span", { text: L.ago(r.time, now) }));
      if (r.site) {
        var skip = el("button", { type: "button", class: "btn quiet small", text: "Don't record this site",
          "aria-label": "Don't record downloads from " + r.site });
        skip.addEventListener("click", function () {
          UI.ask({ cmd: "exclude", site: r.site });
          document.getElementById("sites").open = true;
        });
        meta.appendChild(skip);
      }
      var item = el("li", {}, [
        el("span", { class: "name", text: r.name || "(no name)", title: r.name || "" }),
        el("span", { class: "chip " + r.state, text: LABELS[r.state] || r.state }),
        meta,
      ]);
      var detail = r.detail || (r.state === "expired" ? "wherefrom wasn't reachable for 14 days." : "") ||
        (r.state === "known" ? "wherefrom had already recorded this file." : "");
      if (detail) item.appendChild(el("span", { class: "detail", text: detail }));
      list.appendChild(item);
    });
    document.getElementById("recent-empty").hidden = recent.length > 0;
    document.getElementById("clear-recent").hidden = recent.length === 0;
  }

  function renderSites(excluded) {
    var list = document.getElementById("excluded");
    list.replaceChildren();
    excluded.forEach(function (site) {
      var remove = el("button", { type: "button", class: "btn quiet", text: "Remove", "aria-label": "Record " + site + " again" });
      remove.addEventListener("click", function () { UI.ask({ cmd: "include", site: site }); });
      list.appendChild(el("li", {}, [el("span", { class: "name", text: site }), remove]));
    });
    document.getElementById("sites-count").textContent = excluded.length ? "(" + excluded.length + ")" : "";
  }

  function render(data) {
    var settings = Object.assign({ paused: false, excluded: [] }, data.settings);
    UI.renderStatus(document.getElementById("status"), data.status, settings, check, install);
    var record = document.getElementById("record");
    record.checked = !settings.paused;
    record.setAttribute("aria-checked", String(!settings.paused));
    renderRecent(data.recent || [], Date.now());
    renderSites(settings.excluded);
    var waiting = (data.queue || []).length, dropped = data.dropped || 0;
    var note = document.getElementById("dropped");
    var parts = [];
    if (waiting && data.status && data.status.state !== "connected") parts.push(waiting + (waiting === 1 ? " download is" : " downloads are") + " waiting for wherefrom.");
    if (dropped) parts.push(dropped + (dropped === 1 ? " download was" : " downloads were") + " given up on (more than 200 waiting, or older than 14 days).");
    note.textContent = parts.join(" ");
    note.hidden = parts.length === 0;
  }

  function refresh() {
    return UI.read(["settings", "status", "recent", "queue", "dropped"]).then(render);
  }

  document.getElementById("record").addEventListener("change", function (event) {
    UI.ask({ cmd: "pause", value: !event.target.checked });
  });
  document.getElementById("clear-recent").addEventListener("click", function () { UI.ask({ cmd: "clear-recent" }); });
  document.getElementById("add-site").addEventListener("submit", function (event) {
    event.preventDefault();
    var input = document.getElementById("site"), error = document.getElementById("site-error");
    UI.ask({ cmd: "exclude", site: input.value }).then(function (reply) {
      error.hidden = Boolean(reply && reply.ok);
      error.textContent = reply && reply.ok ? "" : (reply && reply.error) || "Couldn't add that site.";
      if (reply && reply.ok) input.value = "";
    });
  });

  UI.api.storage.onChanged.addListener(function (changes, area) { if (area === "local") refresh(); });
  UI.installTarget().then(function (target) { install = target; refresh(); });
  refresh();
  check();      // find out now whether wherefrom is there, and send anything waiting
})();
