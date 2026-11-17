const { test, expect } = require("playwright/test");
const fs = require("fs");
const vm = require("vm");
const parser = fs.readFileSync(require("path").join(__dirname, "../extension/work_parse.js"), "utf8");

test("Calendar uses appointments, not empty selected time slots", async ({ page }) => {
  await page.setContent(`<main>
    <div role="button" id="selectedInterval_id__1" aria-label="11:15 PM to 11:30 PM, Sunday, November 08, 2026"></div>
    <div role="button" aria-label="Planning, with the team, 9:00 AM to 9:30 AM, Monday, November 09, 2026, Microsoft Teams Meeting, Busy"></div>
    <div role="button" aria-label="Hidden title, 10:00 AM to 10:30 AM, Monday, November 09, 2026, Secret room, Private, Busy"></div>
    <div role="button" aria-label="Holiday, all day event, Wednesday, November 11, 2026, United States, Free"></div>
    </main>`);
  await page.addScriptTag({ content: parser });
  const events = await page.evaluate(() => CCWorkParse.calendar(document));
  expect(events).toHaveLength(3);
  expect(events[0].title).toBe("Planning, with the team");
  expect(events[1].title).toBe("Private appointment");
  expect(events[1].location).toBe("");
  expect(events[2].allDay).toBe(true);
});

test("Briefing selects the latest briefing reply and extracts priorities", async ({ page }) => {
  await page.setContent(`<div data-testid="markdown-reply"><h2>Daily Sales Briefing | Sample date</h2>
    <h1>🔴 1. Example Property: resolve an outage</h1><p>Verified context in the original briefing.</p>
    <h3>Monday action</h3><p>Check the technical resolution before following up.</p>
    <h2>🟠 2. Example Portfolio: prepare a quote</h2><p>Pricing is pending.</p>
    <h3>Next step</h3><p>Confirm the delivery date.</p></div>
    <div data-testid="markdown-reply"><h2>A later unrelated response</h2><p>No briefing here.</p></div>`);
  await page.addScriptTag({ content: parser });
  const b = await page.evaluate(() => CCWorkParse.briefing(document, "https://m365.cloud.microsoft/chat/conversation/example"));
  expect(b.items).toHaveLength(2);
  expect([b.red, b.orange, b.yellow]).toEqual([1, 1, 0]);
  expect(b.items[0].action).toContain("Check the technical resolution");
  expect(b.items[1].summary).toContain("Pricing is pending");
});

test("Briefing reads the P1/P2/P3 digest format", async ({ page }) => {
  await page.setContent(`<div data-testid="markdown-reply"><h1>ALLBRIDGE DAILY DIGEST – November 6, 2026</h1>
    <h2>1. EXECUTIVE PRIORITY</h2><ol><li>P1 | Example Inn: clear the blocker</li></ol>
    <h2>2. ACTIONS</h2>
    <h3>Example Inn | P1 | FOLLOW UP</h3><p>VERIFIED FACTS: A document is outstanding.</p><p>RECOMMENDATION: Verify the document.</p>
    <h3>Example Group | P2 | WAIT</h3><p>VERIFIED FACTS: Pricing is pending.</p>
    <h3>Example Resort | P3 | REVIEW REQUIRED</h3><p>VERIFIED FACTS: Monitor.</p>
    <h2>3. TODAY AND TOMORROW MEETINGS</h2></div>`);
  await page.addScriptTag({ content: parser });
  const b = await page.evaluate(() => CCWorkParse.briefing(document, "https://m365.cloud.microsoft/chat/conversation/example"));
  expect(b.items).toHaveLength(3);
  expect([b.red, b.orange, b.yellow]).toEqual([1, 1, 1]);
  expect(b.items[0].action).toContain("Verify the document");
});

function loadBackground(store, extra = {}, hour = 21) {
  const events = {}, log = { reloads: [], created: [], removed: [], updates: [], closedTabs: [] };
  const chrome = {
    storage: { local: { get: async keys => structuredClone(Object.fromEntries((typeof keys === "string" ? [keys] : keys).map(k => [k, store[k]]))), set: async val => Object.assign(store, structuredClone(val)) } },
    tabs: Object.assign({
      get: async id => ({ id, url: "https://outlook.cloud.microsoft/mail/" }),
      reload: async id => log.reloads.push(id),
      update: async (id, p) => log.updates.push([id, p]),
      remove: async id => log.closedTabs.push(id),
      query: async () => [],
      create: async o => { log.created.push(o); return { id: 900 + log.created.length }; },
      onCreated: { addListener: f => events.created = f }
    }, extra.tabs || {}),
    windows: Object.assign({ get: async id => ({ id, type: "normal" }), remove: async id => log.removed.push(id) }, extra.windows || {}),
    runtime: Object.assign({ onMessage: { addListener: f => events.message = f }, onStartup: { addListener: f => events.start = f }, onInstalled: { addListener: f => events.install = f } }, extra.runtime || {}),
    alarms: { create: async () => {}, onAlarm: { addListener: f => events.alarm = f } }
  };
  class FixedDate extends Date { constructor(...a) { super(...(a.length ? a : [FixedDate.now()])); } static now() { const d = new Date(); d.setHours(hour, 15, 0, 0); return d.getTime(); } }
  const context = { chrome, Date: FixedDate, Promise };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(require("path").join(__dirname, "../extension/background.js"), "utf8"), context);
  return { events, log, context };
}

test("Never reloads a work tab during the 7 AM to 7 PM quiet hours", async () => {
  const store = { cc_lane_tabs: { mail: 123, copilot: 789 }, cc_mail: { ts: 0 }, cc_copilot: { ts: 0 } };
  const { events, log } = loadBackground(store, {}, 10);
  await events.alarm({ name: "cc-watch" });
  expect(log.reloads).toEqual([]);
});

test("Outside quiet hours reloads a stuck tab once, then waits", async () => {
  const now = new Date(); now.setHours(21, 15, 0, 0);
  const store = { cc_lane_tabs: { mail: 123, copilot: 789 }, cc_mail: { ts: now.getTime() - 40 * 60000 }, cc_copilot: { ts: now.getTime() } };
  const { events, log, context } = loadBackground(store, {}, 21);
  await events.alarm({ name: "cc-watch" });
  await events.alarm({ name: "cc-watch" });
  expect(log.reloads).toEqual([123]);
  events.message({ cc: "lane", kind: "mail" }, { tab: { id: 222 } });
  await vm.runInContext("registration", context);
  expect(store.cc_lane_tabs.mail).toBe(222);
});

test("Pins its tabs, adopts a pinned one without reloading, reopens a closed one, never reopens the calendar", async () => {
  const store = { cc_lane_tabs: { mail: 1, copilot: 2 }, cc_lane_urls: { mail: "https://outlook.cloud.microsoft/mail/#cc-lane", copilot: "https://copilot.cloud.microsoft/chat/conversation/x#cc-lane", cal: "https://outlook.cloud.microsoft/calendar/view/workweek#cc-lane" }, cc_mail: { ts: Date.now() }, cc_copilot: { ts: Date.now() } };
  const { events, log, context } = loadBackground(store, { tabs: {
    get: async id => { if (id === 1 || id === 2) throw new Error("gone"); return { id }; },
    query: async () => [{ id: 50, url: "https://outlook.cloud.microsoft/mail/inbox", pinned: true }]
  } }, 10);
  await events.alarm({ name: "cc-watch" });
  expect(store.cc_lane_tabs.mail).toBe(50);
  expect(log.reloads).toEqual([]);
  expect(log.created).toHaveLength(1);
  expect(log.created[0]).toMatchObject({ pinned: true, active: false });
  expect(log.created[0].url).toContain("copilot");
  events.message({ cc: "lane", kind: "copilot" }, { tab: { id: 9, url: "https://copilot.cloud.microsoft/chat/conversation/x", pinned: false } });
  events.message({ cc: "lane", kind: "cal" }, { tab: { id: 10, url: "https://outlook.cloud.microsoft/calendar/view/day", pinned: false } });
  await vm.runInContext("registration", context);
  expect(log.updates).toContainEqual([9, { pinned: true }]);
  expect(store.cc_lane_tabs.cal).toBeUndefined();
});

test("Update retires the Outlook calendar tab and loads meetings from the Mac", async () => {
  const store = { cc_lane_tabs: { mail: 1, cal: 4, copilot: 2 }, cc_lane_urls: { cal: "x", mail: "y" } };
  const mac = { ts: 1700000000000, account: "bcapano@allbridge.com", range: "Today and the next 7 days", events: [{ s: "2026-11-18T14:00:00.000Z", e: "2026-11-18T14:30:00.000Z", title: "Pipeline review", location: "", private: false, allDay: false }] };
  const { events, log } = loadBackground(store, { runtime: { sendNativeMessage: async (host, msg) => { expect(host).toBe("com.commandcenter.work"); return mac; } } });
  await events.install();
  expect(log.closedTabs).toEqual([4]);
  expect(store.cc_lane_tabs.cal).toBeUndefined();
  expect(store.cc_lane_urls.cal).toBeUndefined();
  expect(store.cc_cal).toMatchObject({ ts: mac.ts, schema: 2, status: "ok", src: "mac" });
  expect(store.cc_cal.events[0].title).toBe("Pipeline review");
});

test("Closes a pop-up window opened by a work tab, and only those", async () => {
  const store = { cc_lane_tabs: { mail: 7 } };
  const { events, log } = loadBackground(store, { windows: { get: async id => ({ id, type: id === 50 ? "popup" : "normal" }) } });
  await events.created({ id: 1, windowId: 50, openerTabId: 7 });
  await events.created({ id: 2, windowId: 51, openerTabId: 7 });
  await events.created({ id: 3, windowId: 50, openerTabId: 99 });
  expect(log.removed).toEqual([50]);
});
