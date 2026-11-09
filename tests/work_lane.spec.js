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

test("Background reloads a stale registered tab only and rate limits retries", async () => {
  const store = { cc_lane_tabs: { mail: 123, cal: 456, copilot: 789 }, cc_mail: { ts: Date.now() - 8*60000 }, cc_cal: { ts: Date.now() }, cc_copilot: { ts: Date.now() } };
  const events = {}, reloads = [];
  const chrome = {
    storage: { local: { get: async keys => structuredClone(Object.fromEntries((typeof keys === "string" ? [keys] : keys).map(k => [k, store[k]]))), set: async val => Object.assign(store, structuredClone(val)) } },
    tabs: { get: async id => ({ id }), reload: async id => reloads.push(id) },
    runtime: { onMessage: { addListener: f => events.message=f }, onStartup: { addListener: f => events.start=f }, onInstalled: { addListener: f => events.install=f } },
    alarms: { create: async () => {}, onAlarm: { addListener: f => events.alarm=f } }
  };
  const context = { chrome, Date, Promise };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(require("path").join(__dirname, "../extension/background.js"), "utf8"), context);
  await events.alarm({ name: "cc-watch" });
  expect(reloads).toEqual([123]);
  await events.alarm({ name: "cc-watch" });
  expect(reloads).toEqual([123]);
  events.message({ cc: "lane", kind: "mail" }, { tab: { id: 222 } });
  events.message({ cc: "lane", kind: "cal" }, { tab: { id: 333 } });
  await vm.runInContext("registration", context);
  expect(store.cc_lane_tabs.mail).toBe(222);
  expect(store.cc_lane_tabs.cal).toBe(333);
});
