// Source reader. Run `node extension/build.js` after changing this file.
// Reads folder counts and, from the dedicated work-calendar tab only, actual appointment titles/times/locations.
// No email bodies or attendees. Private appointments are redacted. Nothing is uploaded.
(() => {
  // After the add-on is reloaded or updated, copies already running in open tabs lose their connection.
  // Stop quietly instead of logging "Extension context invalidated" every 30 seconds.
  const alive = () => { try { return !!(chrome.runtime && chrome.runtime.id); } catch (e) { return false; } };
  const timers = [];
  const every = (fn, ms) => timers.push(setInterval(() => { if (!alive()) { timers.forEach(clearInterval); return; } fn(); }, ms));
  const put = obj => { try { if (alive()) Promise.resolve(chrome.storage.local.set(obj)).catch(() => {}); } catch (e) { /* context lost during reload */ } };
  const DEFAULTS = { folders: [{ match: "Inbox", label: "Inbox unread" }] };
  const norm = t => t.replace(/\s+/g, " ").trim();
  const bare = t => norm(t).replace(/^[^A-Za-z0-9]+/, "").toLowerCase();

  async function cfg() {
    if (!alive()) return { ...DEFAULTS };
    const { cc_cfg } = await chrome.storage.local.get("cc_cfg").catch(() => ({}));
    return { ...DEFAULTS, ...(cc_cfg || {}) };
  }

  async function scanMail() {
    const rows = [...document.querySelectorAll('[role="treeitem"]')];
    if (!rows.length) return;                       // folder pane not rendered yet
    const { folders } = await cfg();
    const out = folders.map(f => {
      const want = f.match.toLowerCase();
      const named = rows.map(r => {
        const num = [...r.querySelectorAll("span,div")].filter(k => !k.children.length && /^\d{1,6}$/.test(k.textContent.trim()));
        const raw = norm(r.innerText);
        const name = bare(raw.replace(/\b(selected|unread|items?)\b/gi, "").replace(/\[\d+\]/g, "").replace(/\s\d{1,6}\s*$/, ""));
        return { name, n: num.length ? parseInt(num[num.length - 1].textContent.trim(), 10) : 0 };
      });
      const hit = named.find(x => x.name === want) || named.find(x => x.name.includes(want));
      return hit ? { label: f.label, n: hit.n } : { label: f.label, n: null };
    }).filter(x => x.n !== null);
    if (out.length) put({ cc_mail: { ts: Date.now(), folders: out } });
  }

  function scanCalendar() {
    if (sessionStorage.getItem("cc_lane") !== "1" || !globalThis.CCWorkParse) return;
    const account = "bcapano@allbridge.com";
    const groups = [...document.querySelectorAll('button[title^="Hide account"]')];
    const selected = groups.filter(h => h.parentElement?.parentElement?.querySelector('button[role="option"][aria-selected="true"]'));
    const scoped = selected.length === 1 && selected[0].title.includes(account);
    const status = [...document.querySelectorAll('[aria-live]')].map(e => e.textContent).find(x => /Loaded \d+ events in/i.test(x || ""));
    if (!status || !document.querySelector('main,[role="main"]')) return;
    if (!scoped) {
      put({ cc_cal: { ts: Date.now(), events: [], status: "scope", message: "Select only the Allbridge calendar in the work tab.", account, schema: 2 } });
      return;
    }
    const events = CCWorkParse.calendar(document);
    const expected = Number((status.match(/Loaded (\d+) events/i) || [])[1] || 0);
    put({ cc_cal: {
      ts: Date.now(), events, account, schema: 2,
      range: status.replace(/^Loaded \d+ events in \d+ selected calendars?\s*/i, "").replace(/\.$/, ""),
      status: expected > events.length ? "partial" : "ok",
      message: expected > events.length ? "Some entries could not be read. Check Outlook for the complete calendar." : ""
    } });
  }

  function ensureWorkWeek() {
    if (sessionStorage.getItem("cc_lane") !== "1") return;
    if (!location.pathname.startsWith("/calendar/view/workweek")) {
      location.replace(location.origin + "/calendar/view/workweek#cc-lane"); return;
    }
    const d = new Date();
    if (d.getDay() === 0) d.setDate(d.getDate() + 1);
    if (d.getDay() === 6) d.setDate(d.getDate() + 2);
    const key = [d.getFullYear(), String(d.getMonth()+1).padStart(2,"0"), String(d.getDate()).padStart(2,"0")].join("-");
    if (document.querySelector(`[data-tabid$="${key}"]`)) return;
    const want = `${d.getDate()}, ${d.toLocaleString("en-US", {month:"long"})}, ${d.getFullYear()}`;
    const day = [...document.querySelectorAll('button[aria-label]')].find(e => e.getAttribute("aria-label") === want);
    if (day) day.click(); // view selection only; never creates or edits an appointment
  }
  function tick() {
    try {
      if (location.pathname.startsWith("/mail")) scanMail().catch(() => {});
      if (location.pathname.startsWith("/calendar")) { ensureWorkWeek(); scanCalendar(); }
    } catch (e) { /* page changed under us; try again next tick */ }
  }
  setTimeout(tick, 6000);
  document.addEventListener("resume", () => { if (alive()) tick(); });   // tab woke up from sleep: count right away
  every(tick, 30000);

  // Refresh only our own calendar tab. The next scan selects the current/next work week.
  if (location.pathname.startsWith("/calendar") && sessionStorage.getItem("cc_lane") === "1") {
    const day = () => new Date().toDateString();
    const stamp = sessionStorage.getItem("cc_cal_day");
    if (stamp !== day()) {
      sessionStorage.setItem("cc_cal_day", day());
      ensureWorkWeek();
    }
    every(() => location.replace(location.origin + "/calendar/view/workweek#cc-lane"), 60 * 60 * 1000);
  }
})();
