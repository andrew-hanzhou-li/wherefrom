// Shared by the popup and the welcome page: talking to the background script
// and drawing the connection status. Everything shown is set as text.

var WherefromUI = (function () {
  "use strict";
  var api = globalThis.browser || globalThis.chrome;
  var REPO = "https://github.com/andrew-hanzhou-li/wherefrom";
  var SETUP_EXE = REPO + "/releases/latest/download/wherefrom-setup.exe";

  // Promise forms only: Firefox's `browser.*` takes no callbacks, and
  // Chrome's MV3 `chrome.*` returns promises when given none.
  function ask(message) {
    try {
      return api.runtime.sendMessage(message).then(
        function (reply) { return reply || { ok: false }; },
        function () { return { ok: false }; });
    } catch (e) {
      return Promise.resolve({ ok: false });
    }
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") node.textContent = attrs[k];
      else if (k === "class") node.className = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function copyButton(text) {
    var button = el("button", { type: "button", class: "btn secondary", text: "Copy" });
    button.addEventListener("click", function () {
      var done = function () { button.textContent = "Copied"; setTimeout(function () { button.textContent = "Copy"; }, 1500); };
      try { navigator.clipboard.writeText(text).then(done, function () { button.textContent = "Select and copy"; }); }
      catch (e) { button.textContent = "Select and copy"; }
    });
    return button;
  }

  /** Where to get wherefrom on this system: the installer on Windows, the README elsewhere. */
  function installTarget() {
    var fallback = { href: REPO + "#install", label: "Get wherefrom", windows: false };
    try {
      return api.runtime.getPlatformInfo().then(function (info) {
        return info && info.os === "win" ? { href: SETUP_EXE, label: "Download wherefrom for Windows", windows: true } : fallback;
      }, function () { return fallback; });
    } catch (e) {
      return Promise.resolve(fallback);
    }
  }

  /** Fill `box` (a .status element) for this status; `onCheck` runs "Check again". */
  function renderStatus(box, status, settings, onCheck, install) {
    var state = (status && status.state) || "unknown";
    var title, lines = [], actions = [], kind = "";
    var check = el("button", { type: "button", class: "btn secondary", text: "Check again" });
    check.addEventListener("click", function () {
      check.disabled = true; check.textContent = "Checking…";
      onCheck().then(function () { check.disabled = false; check.textContent = "Check again"; });
    });
    if (settings && settings.paused) {
      title = "Paused"; kind = "paused";
      lines.push(el("p", { class: "muted", text: "New downloads aren't recorded until you turn recording back on." }));
    } else if (state === "connected") {
      title = "Recording downloads"; kind = "connected";
      lines.push(el("p", { class: "muted", text: status.version ? "Connected to wherefrom " + status.version + "." : "Connected to wherefrom." }));
    } else if (state === "missing") {
      title = "wherefrom isn't set up on this computer"; kind = "problem";
      lines.push(el("p", { text: "This extension sends each download to the wherefrom program, which keeps the record. Downloads wait here until it's installed." }));
      var get = el("a", { class: "btn primary", href: install.href, target: "_blank", rel: "noopener", text: install.label });
      actions.push(get, check);
    } else if (state === "forbidden") {
      title = "wherefrom doesn't recognise this copy of the extension yet"; kind = "problem";
      var cmd = "wherefrom browser setup --extension-id " + api.runtime.id;
      lines.push(el("p", { text: "Run this once in a terminal, then check again:" }));
      lines.push(el("div", { class: "command" }, [el("code", { text: cmd }), copyButton(cmd)]));
      actions.push(check);
    } else if (state === "error") {
      title = "wherefrom didn't answer"; kind = "problem";
      lines.push(el("p", { text: "Try again in a moment. If it keeps happening, reinstalling wherefrom usually fixes it." }));
      if (status.detail) lines.push(el("p", { class: "muted small", text: "Details: " + status.detail }));
      actions.push(check);
    } else {
      title = "Checking…";
    }
    box.className = "status " + kind;
    box.replaceChildren(el("p", { class: "title" }, [el("span", { class: "dot" }), el("span", { text: title })]));
    lines.forEach(function (n) { box.appendChild(n); });
    if (actions.length) box.appendChild(el("div", { class: "actions" }, actions));
  }

  function read(keys) {
    try {
      return api.storage.local.get(keys).then(function (data) { return data || {}; }, function () { return {}; });
    } catch (e) {
      return Promise.resolve({});
    }
  }

  return { api: api, ask: ask, el: el, renderStatus: renderStatus, installTarget: installTarget, read: read, REPO: REPO };
})();
