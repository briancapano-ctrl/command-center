// Watchdog. Every 2 minutes it checks how old each number is. If a work tab stopped updating
// (Comet can put background tabs to sleep), it reloads only that pinned work tab. It reads no page content.
const LIMITS = { cc_mail: 6, cc_cal: 6, cc_copilot: 30 };   // minutes
const MATCH = {
  cc_mail: u => /^https:\/\/outlook\.(office|office365|cloud)\.(com|microsoft)\/mail/.test(u),
  cc_cal: u => /^https:\/\/outlook\.(office|office365|cloud)\.(com|microsoft)\/calendar/.test(u),
  cc_copilot: u => /^https:\/\/m365\.cloud\.microsoft\/chat/.test(u)
};
chrome.runtime.onInstalled.addListener(() => chrome.alarms.create("cc-watch", { periodInMinutes: 2 }));
chrome.runtime.onStartup.addListener(() => chrome.alarms.create("cc-watch", { periodInMinutes: 2 }));
chrome.alarms.onAlarm.addListener(async a => {
  if (a.name !== "cc-watch") return;
  const st = await chrome.storage.local.get(["cc_mail", "cc_cal", "cc_copilot", "cc_reloads"]);
  const tabs = await chrome.tabs.query({ pinned: true });
  const reloads = st.cc_reloads || {};
  for (const key of Object.keys(LIMITS)) {
    const age = (Date.now() - ((st[key] && st[key].ts) || 0)) / 60000;
    if (age < LIMITS[key]) continue;
    if (Date.now() - (reloads[key] || 0) < LIMITS[key] * 60000) continue;   // at most one reload per window
    const hits = tabs.filter(t => t.url && MATCH[key](t.url));
    const tab = hits.find(t => t.url.includes("cc-lane")) || hits[0];
    if (!tab) continue;
    reloads[key] = Date.now();
    try { await chrome.tabs.reload(tab.id); } catch (e) { /* tab closed */ }
  }
  await chrome.storage.local.set({ cc_reloads: reloads });
});
