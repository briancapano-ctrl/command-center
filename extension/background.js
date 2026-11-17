// Watchdog. Knows which tabs are the add-on's own work tabs (they report in when they load) and only ever touches those.
// Every 2 minutes it checks how old each number is; if a work tab stopped updating, it reloads that one tab.
// After the add-on itself is reloaded or updated, it refreshes its own tabs so the new code starts right away.
// It also pins its own tabs (a pinned tab has no close button) and quietly reopens one, pinned, if it is ever closed.
const LIMITS = { mail: 6, cal: 6, copilot: 30 };   // minutes before a tab is considered stuck
const KEYS = { mail: "cc_mail", cal: "cc_cal", copilot: "cc_copilot" };
const PATTERNS = {   // which pinned tab is which, used to adopt a tab after a browser restart instead of opening a duplicate
  mail: /^https:\/\/outlook\.(office\.com|cloud\.microsoft|office365\.com)\/mail/,
  cal: /^https:\/\/outlook\.(office\.com|cloud\.microsoft|office365\.com)\/calendar/,
  copilot: /^https:\/\/(copilot|m365)\.cloud\.microsoft\/chat/,
  page: /^https:\/\/briancapano-ctrl\.github\.io\/command-center/
};
const LANE_KINDS = ["mail", "cal", "copilot"];
const withFlag = (u, kind) => LANE_KINDS.includes(kind) && !/cc-lane/.test(u) ? u.split("#")[0] + "#cc-lane" : u;

async function laneTabs() {
  const { cc_lane_tabs } = await chrome.storage.local.get("cc_lane_tabs");
  return cc_lane_tabs || {};
}
async function reloadTab(id) {
  try { await chrome.tabs.get(id); await chrome.tabs.reload(id); return true; } catch (e) { return false; }   // tab was closed
}

let registration = Promise.resolve();
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg || !sender.tab || !sender.tab.id) return;
  const kind = msg.cc === "lane" && KEYS[msg.kind] ? msg.kind : msg.cc === "relay" ? "page" : null;
  if (!kind) return;
  // Serialize read/merge/write so tabs registering together cannot overwrite each other.
  registration = registration.catch(() => {}).then(async () => {
    const t = await laneTabs(); t[kind] = sender.tab.id;
    const { cc_lane_urls } = await chrome.storage.local.get("cc_lane_urls");
    const urls = cc_lane_urls || {}; if (sender.tab.url) urls[kind] = withFlag(sender.tab.url, kind);
    await chrome.storage.local.set({ cc_lane_tabs: t, cc_lane_urls: urls });
    try { if (!sender.tab.pinned) await chrome.tabs.update(sender.tab.id, { pinned: true }); } catch (e) { /* tab closed meanwhile */ }
  });
});

async function arm() { await chrome.alarms.create("cc-watch", { periodInMinutes: 2 }); }
chrome.runtime.onStartup.addListener(arm);
chrome.runtime.onInstalled.addListener(async () => {
  await arm();
  // Fresh code: restart only our own tabs (work tabs and the Command Center page), nothing else.
  const t = await laneTabs();
  await chrome.storage.local.set({ cc_reloads: {} });
  for (const k of Object.keys(t)) await reloadTab(t[k]);
});

// If one of our tabs is gone, adopt a matching pinned tab (after a browser restart) or reopen it pinned in the background.
async function heal(tabs, urls, reloads) {
  let changed = false;
  for (const kind of Object.keys(PATTERNS)) {
    if (!urls[kind]) continue;   // never seen this one report, so nothing to restore
    let alive = false;
    if (tabs[kind]) { try { await chrome.tabs.get(tabs[kind]); alive = true; } catch (e) { /* closed or stale id */ } }
    if (alive) continue;
    const pinned = (await chrome.tabs.query({ pinned: true })).find(t => PATTERNS[kind].test(t.url || t.pendingUrl || ""));
    if (pinned) { tabs[kind] = pinned.id; try { await chrome.tabs.reload(pinned.id); } catch (e) { /* ignore */ } }
    else { try { const n = await chrome.tabs.create({ url: urls[kind], pinned: true, active: false }); tabs[kind] = n.id; } catch (e) { continue; } }
    reloads[kind] = Date.now(); changed = true;   // fresh tab: give it a full window before the stuck-tab check
  }
  return changed;
}

chrome.alarms.onAlarm.addListener(async a => {
  if (a.name !== "cc-watch") return;
  const st = await chrome.storage.local.get(["cc_mail", "cc_cal", "cc_copilot", "cc_reloads", "cc_lane_tabs", "cc_lane_urls"]);
  const tabs = st.cc_lane_tabs || {}, reloads = st.cc_reloads || {};
  let changed = await heal(tabs, st.cc_lane_urls || {}, reloads);
  for (const kind of Object.keys(LIMITS)) {
    const age = (Date.now() - ((st[KEYS[kind]] && st[KEYS[kind]].ts) || 0)) / 60000;
    if (age < LIMITS[kind] || !tabs[kind]) continue;
    if (Date.now() - (reloads[kind] || 0) < LIMITS[kind] * 60000) continue;   // one reload per window, then wait
    reloads[kind] = Date.now(); changed = true;
    if (!(await reloadTab(tabs[kind]))) delete tabs[kind];
  }
  if (changed) await chrome.storage.local.set({ cc_reloads: reloads, cc_lane_tabs: tabs });
});
