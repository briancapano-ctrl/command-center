// Watchdog. Knows which tabs are the add-on's own work tabs (they report in when they load) and only ever touches those.
// Every 2 minutes it checks how old each number is; if a work tab stopped updating, it reloads that one tab.
// After the add-on itself is reloaded or updated, it refreshes its own tabs so the new code starts right away.
const LIMITS = { mail: 6, cal: 6, copilot: 30 };   // minutes before a tab is considered stuck
const KEYS = { mail: "cc_mail", cal: "cc_cal", copilot: "cc_copilot" };

async function laneTabs() {
  const { cc_lane_tabs } = await chrome.storage.local.get("cc_lane_tabs");
  return cc_lane_tabs || {};
}
async function reloadTab(id) {
  try { await chrome.tabs.get(id); await chrome.tabs.reload(id); return true; } catch (e) { return false; }   // tab was closed
}

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg || !sender.tab || !sender.tab.id) return;
  if (msg.cc === "lane" && KEYS[msg.kind]) {
    laneTabs().then(t => { t[msg.kind] = sender.tab.id; return chrome.storage.local.set({ cc_lane_tabs: t }); });
  }
  if (msg.cc === "relay") {
    laneTabs().then(t => { t.page = sender.tab.id; return chrome.storage.local.set({ cc_lane_tabs: t }); });
  }
});

async function arm() { await chrome.alarms.create("cc-watch", { periodInMinutes: 2 }); }
chrome.runtime.onStartup.addListener(arm);
chrome.runtime.onInstalled.addListener(async () => {
  await arm();
  // Fresh code: restart only our own tabs (work tabs and the Command Center page), nothing else.
  const t = await laneTabs();
  for (const k of Object.keys(t)) { if (!(await reloadTab(t[k]))) delete t[k]; }
  await chrome.storage.local.set({ cc_lane_tabs: t, cc_reloads: {} });
});

chrome.alarms.onAlarm.addListener(async a => {
  if (a.name !== "cc-watch") return;
  const st = await chrome.storage.local.get(["cc_mail", "cc_cal", "cc_copilot", "cc_reloads", "cc_lane_tabs"]);
  const tabs = st.cc_lane_tabs || {}, reloads = st.cc_reloads || {};
  let changed = false;
  for (const kind of Object.keys(LIMITS)) {
    const age = (Date.now() - ((st[KEYS[kind]] && st[KEYS[kind]].ts) || 0)) / 60000;
    if (age < LIMITS[kind] || !tabs[kind]) continue;
    if (Date.now() - (reloads[kind] || 0) < LIMITS[kind] * 60000) continue;   // one reload per window, then wait
    reloads[kind] = Date.now(); changed = true;
    if (!(await reloadTab(tabs[kind]))) delete tabs[kind];
  }
  if (changed) await chrome.storage.local.set({ cc_reloads: reloads, cc_lane_tabs: tabs });
});
