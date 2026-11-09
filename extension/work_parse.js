// Pure, tested parsers shared by the work readers. No network calls or browser storage here.
(() => {
  const clean = x => String(x || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  const clip = (x, n) => clean(x).replace(/\s*\+\d+\s*$/g, "").slice(0, n);
  function calendarLabel(label) {
    const l = clean(label);
    // Real appointment labels begin with a title. Empty selectedInterval time slots do not.
    const m = l.match(/^(.+?), (\d{1,2}:\d{2}\s?[AP]M) to (\d{1,2}:\d{2}\s?[AP]M), (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), ([A-Za-z]+ \d{1,2}, \d{4})(?:, (.*))?$/i);
    const ad = !m && l.match(/^(.+?), All day(?: event)?, (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), ([A-Za-z]+ \d{1,2}, \d{4})(?:, (.*))?$/i);
    if (!m && !ad) return null;
    let s, e, title, tail;
    if (m) {
      title = m[1]; tail = m[5] || "";
      s = new Date(`${m[4]} ${m[2]}`); e = new Date(`${m[4]} ${m[3]}`);
      if (+e < +s) e.setDate(e.getDate() + 1);
    } else {
      title = ad[1]; tail = ad[3] || "";
      s = new Date(`${ad[2]} 00:00`); e = new Date(s); e.setDate(e.getDate() + 1);
    }
    if (isNaN(s) || isNaN(e) || !clean(title)) return null;
    const privateItem = /\bprivate\b/i.test(l);
    const loc = clean(tail.split(",")[0]);
    return {
      s: s.toISOString(), e: e.toISOString(), title: privateItem ? "Private appointment" : clip(title, 200),
      location: privateItem || /^(By |Busy|Free|Tentative|Out of office|Recurring|Exception|Working elsewhere|Private)/i.test(loc) ? "" : clip(loc, 120),
      private: privateItem, allDay: !!ad
    };
  }
  function calendar(root) {
    const main = root.querySelector('main,[role="main"]');
    if (!main) return [];
    const seen = new Set(), events = [];
    main.querySelectorAll('[role="button"][aria-label]').forEach(el => {
      if (/^selectedInterval/i.test(el.id || "")) return;
      const x = calendarLabel(el.getAttribute("aria-label"));
      if (!x) return;
      const key = x.s + x.e + x.title;
      if (!seen.has(key)) { seen.add(key); events.push(x); }
    });
    return events.sort((a, b) => Date.parse(a.s) - Date.parse(b.s));
  }
  function briefing(root, href) {
    const outputs = [...root.querySelectorAll('[data-testid="chatOutput"],[data-testid="markdown-reply"]')];
    let last = null, start = null;
    for (let i = outputs.length - 1; i >= 0 && !start; i--) {
      const h = [...outputs[i].querySelectorAll("h1,h2,h3")].find(e => /briefing|digest/i.test(e.textContent));
      if (h) { last = outputs[i]; start = h; }
    }
    if (!start) return null;
    const heads = [...last.querySelectorAll("h1,h2,h3")];
    const priorities = heads.slice(heads.indexOf(start) + 1).filter(h => /^[🔴🟠🟡]/u.test(clean(h.textContent)));
    const items = priorities.map((h, i) => {
      const raw = clean(h.textContent), level = raw.startsWith("🔴") ? "urgent" : raw.startsWith("🟠") ? "watch" : "low";
      const nodes = [...last.querySelectorAll("h1,h2,h3,p,li")];
      const begin = nodes.indexOf(h), end = priorities[i + 1] ? nodes.indexOf(priorities[i + 1]) : nodes.length;
      const body = nodes.slice(begin + 1, end);
      const actionAt = body.findIndex(e => /(?:Monday|next|today|tomorrow)\s+action|next step|recommended action/i.test(e.textContent));
      const actionNodes = actionAt < 0 ? [] : body.slice(actionAt, actionAt + 5).filter(e => e.tagName === "P" || e.tagName === "LI");
      const context = body.filter(e => e.tagName === "P" && !/^\s*(?:Monday|next|today|tomorrow)\s+action/i.test(e.textContent)).slice(0, 2);
      return {
        level, title: clip(raw.replace(/^[^A-Za-z0-9]+/, "").replace(/^\d+[.)]\s*/, ""), 220),
        summary: clip(context.map(e => e.textContent).join(" "), 460),
        action: clip(actionNodes.map(e => e.textContent).join(" "), 440)
      };
    });
    return {
      title: clip(start.textContent, 180), items: items.slice(0, 20),
      red: items.filter(x => x.level === "urgent").length,
      orange: items.filter(x => x.level === "watch").length,
      yellow: items.filter(x => x.level === "low").length,
      href: /^https:\/\/m365\.cloud\.microsoft\/chat\/conversation\//.test(href || "") ? href.split("#")[0] : ""
    };
  }
  globalThis.CCWorkParse = { calendarLabel, calendar, briefing };
})();
