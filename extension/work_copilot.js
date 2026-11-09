// Extracts priority headings, brief context and action passages from the user's existing briefing.
// Browser-local only. Never sends a prompt or any Command Center data to Copilot.
(() => {
  // After the add-on is reloaded or updated, copies already running in open tabs lose their connection.
  // Stop quietly instead of logging "Extension context invalidated" every 30 seconds.
  const alive = () => { try { return !!(chrome.runtime && chrome.runtime.id); } catch (e) { return false; } };
  const timers = [];
  const every = (fn, ms) => timers.push(setInterval(() => { if (!alive()) { timers.forEach(clearInterval); return; } fn(); }, ms));
  const put = obj => { try { if (alive()) Promise.resolve(chrome.storage.local.set(obj)).catch(() => {}); } catch (e) { /* context lost during reload */ } };
  const PATTERN = /briefing|digest/i;
  const NOT_BRIEFING = /code|automation|prompt|template|setup|instruction|build/i;
  const GUARD = "cc_copilot_nav";

  function findLatest() {
    const links = [...document.querySelectorAll('a[href*="/chat/conversation/"]')];
    return links.find(a => { const t = a.textContent || ""; return PATTERN.test(t) && !NOT_BRIEFING.test(t); });
  }

  function read() {
    if (!globalThis.CCWorkParse) return false;
    const b = CCWorkParse.briefing(document, location.href);
    if (!b) return false;
    put({ cc_copilot: { ...b, ts: Date.now(), schema: 2 } });
    return true;
  }

  function tick() {
    try {
      const lane = sessionStorage.getItem("cc_lane") === "1";
      const onConv = /\/chat\/conversation\//.test(location.pathname);
      if (!onConv) {
        if (!lane) return;
        const a = findLatest();
        const lastNav = Number(sessionStorage.getItem(GUARD) || 0);
        if (a && Date.now() - lastNav > 5 * 60000) { sessionStorage.setItem(GUARD, String(Date.now())); location.href = a.href; }
        return;
      }
      if (lane && NOT_BRIEFING.test(document.title)) { sessionStorage.removeItem(GUARD); location.href = "https://m365.cloud.microsoft/chat"; return; }
      if (PATTERN.test(document.title) || lane) read();
    } catch (e) { /* retry next tick */ }
  }
  setTimeout(tick, 7000);
  document.addEventListener("resume", () => { if (alive()) tick(); });   // tab woke up from sleep: count right away
  every(tick, 30000);
  // Re-open the chat list every 15 minutes so a new morning briefing is picked up.
  every(() => { if (sessionStorage.getItem("cc_lane") === "1") { sessionStorage.removeItem(GUARD); location.href = "https://m365.cloud.microsoft/chat"; } }, 15 * 60000);
})();
