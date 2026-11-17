// Work Lane background. Only ever touches the add-on's own work tabs (they report in when they load).
// Work meetings come from the Mac mini (Apple Calendar's synced Allbridge account) through a local bridge, so no Outlook calendar tab is needed.
// Quiet hours: between 7 AM and 7 PM it never reloads a tab. Outside those hours it refreshes a stuck work tab at most once per window.
// It pins its own tabs (no close button) and reopens one in the background if it is closed.
const LIMITS = { mail: 30, copilot: 60 };   // minutes before a tab is considered stuck
const KEYS = { mail: "cc_mail", copilot: "cc_copilot" };
const PATTERNS = {   // which pinned tab is which, used to adopt a tab after a browser restart instead of opening a duplicate
  mail: /^https:\/\/outlook\.(office\.com|cloud\.microsoft|office365\.com)\/mail/,
  copilot: /^https:\/\/(copilot|m365)\.cloud\.microsoft\/chat/,
  page: /^https:\/\/briancapano-ctrl\.github\.io\/command-center/
};
const LANE_KINDS = ["mail", "cal", "copilot"];
const HOST = "com.commandcenter.work";
const withFlag = (u, kind) => LANE_KINDS.includes(kind) && !/cc-lane/.test(u) ? u.split("#")[0] + "#cc-lane" : u;
const quietHours = () => { const h = new Date(Date.now()).getHours(); return h >= 7 && h < 19; };

async function laneTabs() {
  const { cc_lane_tabs } = await chrome.storage.local.get("cc_lane_tabs");
  return cc_lane_tabs || {};
}
async function reloadTab(id) {
  try { await chrome.tabs.get(id); await chrome.tabs.reload(id); return true; } catch (e) { return false; }   // tab was closed
}

// Work meetings from the Mac mini. The bridge only reads a file the Mac collector writes; nothing goes online.
async function syncMac() {
  if (!chrome.runtime.sendNativeMessage) return;
  try {
    const r = await chrome.runtime.sendNativeMessage(HOST, { want: "work" });
    if (!r || !r.ts || !Array.isArray(r.events)) return;
    await chrome.storage.local.set({ cc_cal: { ts: r.ts, events: r.events, account: r.account || "", schema: 2, range: r.range || "", status: "ok", message: "", src: "mac" } });
  } catch (e) { /* bridge not installed yet; the Mac collector installs it on its next run */ }
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
chrome.runtime.onStartup.addListener(async () => { await arm(); await syncMac(); });
chrome.runtime.onInstalled.addListener(async () => {
  await arm();
  // The Outlook calendar tab is retired (it kept opening stray pop-up windows): close it and never reopen it.
  const t = await laneTabs();
  const { cc_lane_urls } = await chrome.storage.local.get("cc_lane_urls");
  const urls = cc_lane_urls || {};
  if (t.cal) { try { await chrome.tabs.remove(t.cal); } catch (e) { /* already closed */ } }
  delete t.cal; delete urls.cal;
  await chrome.storage.local.set({ cc_lane_tabs: t, cc_lane_urls: urls, cc_reloads: {} });
  // Fresh code: restart only our own tabs so the new code runs. This happens only when the add-on itself is updated.
  for (const k of Object.keys(t)) await reloadTab(t[k]);
  await syncMac();
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
    if (pinned) tabs[kind] = pinned.id;   // adopt as is; no reload
    else { try { const n = await chrome.tabs.create({ url: urls[kind], pinned: true, active: false }); tabs[kind] = n.id; } catch (e) { continue; } }
    reloads[kind] = Date.now(); changed = true;   // give it a full window before the stuck-tab check
  }
  return changed;
}

chrome.alarms.onAlarm.addListener(async a => {
  if (a.name !== "cc-watch") return;
  await syncMac();
  const st = await chrome.storage.local.get(["cc_mail", "cc_copilot", "cc_reloads", "cc_lane_tabs", "cc_lane_urls"]);
  const tabs = st.cc_lane_tabs || {}, reloads = st.cc_reloads || {};
  let changed = await heal(tabs, st.cc_lane_urls || {}, reloads);
  if (!quietHours()) {
    for (const kind of Object.keys(LIMITS)) {
      const age = (Date.now() - ((st[KEYS[kind]] && st[KEYS[kind]].ts) || 0)) / 60000;
      if (age < LIMITS[kind] || !tabs[kind]) continue;
      if (Date.now() - (reloads[kind] || 0) < LIMITS[kind] * 60000) continue;   // one reload per window, then wait
      reloads[kind] = Date.now(); changed = true;
      if (!(await reloadTab(tabs[kind]))) delete tabs[kind];
    }
  }
  if (changed) await chrome.storage.local.set({ cc_reloads: reloads, cc_lane_tabs: tabs });
});

// Outlook can open stray about:blank pop-up windows from a work tab. Close a pop-up only when one of this add-on's own work tabs opened it.
if (chrome.tabs.onCreated) chrome.tabs.onCreated.addListener(async t => {
  if (!t.openerTabId || !chrome.windows || !chrome.windows.get) return;
  const tabs = await laneTabs();
  if (!LANE_KINDS.some(k => tabs[k] === t.openerTabId)) return;
  try {
    const w = await chrome.windows.get(t.windowId);
    if (w.type === "popup") await chrome.windows.remove(t.windowId);
  } catch (e) { /* already gone */ }
});
