// Runs on your Copilot chat tab. Finds your newest briefing chat, then counts the red, orange and yellow priority headings.
// It stores the counts and the briefing's own date line only. No customer names or text.
(() => {
  // After the add-on is reloaded or updated, copies already running in open tabs lose their connection.
  // Stop quietly instead of logging "Extension context invalidated" every 30 seconds.
  const alive = () => { try { return !!(chrome.runtime && chrome.runtime.id); } catch (e) { return false; } };
  const timers = [];
  const every = (fn, ms) => timers.push(setInterval(() => { if (!alive()) { timers.forEach(clearInterval); return; } fn(); }, ms));
  const put = obj => { if (alive()) chrome.storage.local.set(obj).catch(() => {}); };
  const PATTERN = /briefing|digest/i;
  const NOT_BRIEFING = /code|automation|prompt|template|setup|instruction|build/i;
  const GUARD = "cc_copilot_nav";

  function findLatest() {
    const links = [...document.querySelectorAll('a[href*="/chat/conversation/"]')];
    return links.find(a => { const t = a.textContent || ""; return PATTERN.test(t) && !NOT_BRIEFING.test(t); });
  }

  function read() {
    const outs = [...document.querySelectorAll('[data-testid="chatOutput"],[data-testid="markdown-reply"]')];
    if (!outs.length) return false;
    // newest reply in this chat that is a briefing (has a heading with "briefing" or "digest")
    let heads = [], start = -1;
    for (let k = outs.length - 1; k >= 0 && start < 0; k--) {
      heads = [...outs[k].querySelectorAll("h1,h2,h3")];
      heads.forEach((h, i) => { if (start < 0 && /briefing|digest/i.test(h.innerText)) start = i; });
    }
    if (start < 0) return false; // no briefing reply here; keep the last good counts
    const scope = heads.slice(start + 1);
    const count = e => scope.filter(h => h.innerText.trim().startsWith(e)).length;
    const title = heads[start].innerText.trim().replace(/^[^A-Za-z0-9]+/, "");
    put({ cc_copilot: { ts: Date.now(), title, red: count("\u{1F534}"), orange: count("\u{1F7E0}"), yellow: count("\u{1F7E1}") } });
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
