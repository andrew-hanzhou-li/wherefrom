// The page opened once when the extension is installed and wherefrom isn't
// reachable yet. It checks again on its own every few seconds while open.
(function () {
  "use strict";
  var UI = WherefromUI;
  var install = { href: UI.REPO + "#install", label: "Get wherefrom" };
  var timer = null;

  function check() { return UI.ask({ cmd: "check" }); }

  function render(data) {
    var status = data.status || { state: "unknown" };
    var settings = Object.assign({ paused: false }, data.settings);
    UI.renderStatus(document.getElementById("status"), status, settings, check, install);
    var connected = status.state === "connected";
    document.body.classList.toggle("done", connected);
    document.querySelector("h1").textContent = connected ? "You're all set" : "One more step: install wherefrom";
    if (connected) {
      var note = document.createElement("p");
      note.textContent = "Downloads are recorded from now on. You can close this tab.";
      document.getElementById("status").appendChild(note);
      if (timer) { clearInterval(timer); timer = null; }
    }
  }

  function refresh() { return UI.read(["settings", "status"]).then(render); }

  UI.installTarget().then(function (target) {
    install = target;
    var link = document.getElementById("install-link");
    link.href = target.href;
    link.textContent = target.label;
    document.getElementById("install-text").textContent = target.windows
      ? "Download the installer and double-click it. It's free and open source, and needs no admin rights."
      : "On macOS and Linux it's two commands; the link shows them. It's free and open source.";
    refresh();
  });
  UI.api.storage.onChanged.addListener(function (changes, area) { if (area === "local") refresh(); });
  refresh();
  check();
  timer = setInterval(check, 5000);     // notice the install without a click
})();
