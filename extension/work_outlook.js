// Runs on your Outlook web pages. Reads only: unread counts for the folders you list, and meeting start/end times.
// It never reads sender names, subjects, meeting titles or message text.
(() => {
  const DEFAULTS = { folders: [{ match: "Inbox", label: "Inbox unread" }] };
  const norm = t => t.replace(/\s+/g, " ").trim();
  const bare = t => norm(t).replace(/^[^A-Za-z0-9]+/, "").toLowerCase();

  async function cfg() {
    const { cc_cfg } = await chrome.storage.local.get("cc_cfg");
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
    if (out.length) chrome.storage.local.set({ cc_mail: { ts: Date.now(), folders: out } });
  }

  function scanCalendar() {
    const events = [];
    document.querySelectorAll("[aria-label]").forEach(el => {
      const l = el.getAttribute("aria-label") || "";
      const m = l.match(/^(\d{1,2}:\d{2}\s?[AP]M)\s+to\s+(\d{1,2}:\d{2}\s?[AP]M)\b/i);
      if (!m) return;
      const parts = l.split(",");
      const dm = (parts[parts.length - 2] || "").trim() + ", " + (parts[parts.length - 1] || "").trim();   // "November 08, 2026"
      const s = new Date(`${dm} ${m[1]}`), e = new Date(`${dm} ${m[2]}`);
      if (!isNaN(s) && !isNaN(e)) events.push({ s: s.toISOString(), e: e.toISOString() });
    });
    if (events.length || document.querySelector('[role="grid"],[role="application"]')) {
      chrome.storage.local.set({ cc_cal: { ts: Date.now(), events } });
    }
  }

  function tick() {
    try {
      if (location.pathname.startsWith("/mail")) scanMail();
      if (location.pathname.startsWith("/calendar")) scanCalendar();
    } catch (e) { /* page changed under us; try again next tick */ }
  }
  setTimeout(tick, 6000);
  setInterval(tick, 30000);

  // Calendar tab: go back to today's view once an hour and after midnight so "next meeting" stays right.
  if (location.pathname.startsWith("/calendar") && sessionStorage.getItem("cc_lane") === "1") {
    const day = () => new Date().toDateString();
    const stamp = sessionStorage.getItem("cc_cal_day");
    if (stamp !== day()) {
      sessionStorage.setItem("cc_cal_day", day());
      if (!location.pathname.startsWith("/calendar/view/day")) location.replace(location.origin + "/calendar/view/day");
    }
    setInterval(() => location.replace(location.origin + "/calendar/view/day"), 60 * 60 * 1000);
  }
})();
