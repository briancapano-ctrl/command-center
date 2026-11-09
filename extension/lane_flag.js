// Marks a tab opened by the add-on ("Open and pin my work tabs") so only those tabs ever navigate or reload themselves.
// It also tells the add-on which tab this is, so the watchdog can refresh exactly this tab and nothing else.
(() => {
  if (location.hash.includes("cc-lane") || location.search.includes("cclane=1")) sessionStorage.setItem("cc_lane", "1");
  if (sessionStorage.getItem("cc_lane") !== "1") return;
  const kind = /\/calendar/.test(location.pathname) ? "cal" : /^outlook\./.test(location.hostname) ? "mail" : "copilot";
  try { chrome.runtime.sendMessage({ cc: "lane", kind }).catch(() => {}); } catch (e) { /* add-on reloading */ }
  // Ask the browser not to put this tab to sleep (sleeping tabs stop counting).
  try { navigator.locks && navigator.locks.request("cc-lane-awake", () => new Promise(() => {})); } catch (e) { /* optional */ }
})();
