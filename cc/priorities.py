"""Turn raw source data into the dashboard model. Pure rules, no AI, no credits."""
import re, datetime as dt
from collections import Counter
from .util import now, short_date, TZ

ACTION = re.compile(r"(action required|payment|past due|statement|invoice|security alert|password|verify|"
                    r"confirm|installation|schedule|renewal|expires|expiring|credits|appointment|"
                    r"paused|declined|failed|receipt|delivery)", re.I)
NOISE = re.compile(r"(unsubscribe|% off|sale|deal|newsletter|digest|weekly|promo|coupon|free trial)", re.I)


def _fmt_time(iso, all_day):
    d = short_date(iso)
    if not d:
        return ""
    return "All day" if all_day else d.strftime("%-I:%M %p")


def build(src, cfg):
    n = now()
    errors = src.get("errors", {})
    tasks, triage, channels = [], [], []

    # ---- reminders (Mac)
    mac = src.get("mac") or {}
    for r in mac.get("reminders", []):
        d = short_date(r.get("due")) if r.get("due") else None
        if d and d.date() < n.date():
            days = (n.date() - d.date()).days
            tasks.append({"t": r["title"], "w": f"Apple Reminder, {days} day{'s' if days != 1 else ''} overdue.", "p": ["Overdue", "p-high"], "rank": 0})
        elif d and d.date() == n.date():
            tasks.append({"t": r["title"], "w": "Apple Reminder due today.", "p": ["Today", "p-high"], "rank": 1})
        elif d and (d.date() - n.date()).days <= 2:
            tasks.append({"t": r["title"], "w": f"Apple Reminder due {d.strftime('%a %b %-d')}.", "p": [d.strftime('%a'), "p-med"], "rank": 3})

    # ---- texts waiting on you (Mac)
    for c in (mac.get("waiting") or [])[:4]:
        tasks.append({"t": f"Reply to {c['label']}", "w": f"Last message {c['ago']} ago ends with a question or request.", "p": ["Reply", "p-med"], "rank": 2})

    # ---- mail that looks actionable
    mails = []
    for m in (src.get("gmail") or {}).get("recent", []):
        mails.append(("Gmail", m))
    for m in (src.get("outlook_unread") or [])[:60]:
        mails.append(("Hotmail", m))
    seen = 0
    for acct, m in mails:
        d = short_date(m.get("date") or "") if m.get("date") else None
        if m.get("date") and not d:
            try:
                from email.utils import parsedate_to_datetime
                d = parsedate_to_datetime(m["date"]).astimezone(TZ)
            except Exception:
                d = None
        if d and (n - d).days > 5:
            continue
        s = m.get("subject", "")
        if ACTION.search(s) and not NOISE.search(s):
            tasks.append({"t": s[:80], "w": f"{acct}, from {m.get('domain') or m.get('from','')}.", "p": ["Mail", "p-info"], "rank": 4})
            seen += 1
            if seen >= 4:
                break

    # ---- events today / tomorrow and birthdays
    events = []
    for e in (src.get("gcal") or []) + (src.get("outlook_cal") or []):
        d = short_date(e["start"]) if e.get("start") else None
        if d:
            events.append({**e, "d": d})
    events.sort(key=lambda e: e["d"])
    for e in events:
        days = (e["d"].date() - n.date()).days
        if 0 <= days <= 3 and re.search(r"birthday", e["title"], re.I):
            tasks.append({"t": f"Send birthday wishes: {e['title']}", "w": e["d"].strftime("%a %b %-d") + ". On your calendar.", "p": [e["d"].strftime("%a"), "p-med"], "rank": 3})
        elif days == 0 and not e["all_day"]:
            tasks.append({"t": e["title"], "w": f"Today at {e['d'].strftime('%-I:%M %p')}.", "p": ["Today", "p-info"], "rank": 2})
    tasks.sort(key=lambda t: t["rank"])
    # drop near-duplicates (same thing from a reminder, a text and a calendar): keep the highest-ranked one
    import re as _re
    keep, seen = [], []
    for t in tasks:
        toks = {w for w in _re.findall(r"[a-z]{4,}", t["t"].lower())} - {"reply", "text", "send", "wishes", "happy", "call"}
        if any(len(toks & o) >= 2 for o in seen):
            continue
        seen.append(toks); keep.append(t)
    tasks[:] = keep

    # ---- week timeline
    week, seen_keys = [], set()
    for e in events:
        key = (e["d"].date(), e["title"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        week.append({"dow": e["d"].strftime("%a"), "day": e["d"].day, "title": e["title"],
                     "meta": _fmt_time(e["start"], e["all_day"]), "today": e["d"].date() == n.date(), "_d": e["d"]})
    sports = src.get("sports") or []
    for t in sports:
        for g in t["next"][:1]:
            d = short_date(g["when"])
            if d and (d - n).days <= 7:
                week.append({"dow": d.strftime("%a"), "day": d.day, "title": f"{t['team']}: {g['name']}",
                             "meta": d.strftime("%-I:%M %p"), "today": d.date() == n.date(), "_d": d})
    week.sort(key=lambda w: w["_d"])
    week = week[:10]
    for w in week:
        w.pop("_d", None)

    # ---- inbox triage
    g = src.get("gmail")
    if g:
        triage.append({"acct": "Gmail", "finding": f"{g['cleared']:,} promotions and social messages archived and marked read today." if g["cleared"] else "No promotions or social mail to clear today.",
                       "action": "Undo: search the Cleanup label in Gmail."})
        top = Counter(m["domain"] for m in g["recent"]).most_common(3)
        if top:
            triage.append({"acct": "Gmail", "finding": "Top unread senders: " + ", ".join(f"{d} ({c})" for d, c in top) + ".", "action": "Review or filter."})
    fo = src.get("outlook_folders")
    if fo:
        inbox = next((f for f in fo if f["name"].lower() == "inbox"), None)
        if inbox:
            triage.append({"acct": "Hotmail", "finding": f"Inbox: {inbox['unread']:,} unread of {inbox['total']:,}. Swept today: {src.get('outlook_swept', 0)}.", "action": "Approved promo senders are archived each run."})
    if not triage:
        triage.append({"acct": "All", "finding": "No mail sources connected yet.", "action": "Finish the setup steps in the README."})

    # ---- KPIs
    unread_texts = mac.get("unread_total")
    need = len([t for t in tasks if t["rank"] <= 3])
    kpis = [
        {"key": "need", "label": "Needs you", "num": need, "value": str(need), "note": "reminders, replies, dates"},
        {"key": "texts", "label": "Unread texts", "num": unread_texts, "value": f"{unread_texts:,}" if unread_texts is not None else "n/a", "note": f"{mac.get('unread_chats', 0)} chats" if mac else "Mac not reporting"},
        {"key": "gmail", "label": "Gmail unread", "num": g["unread_estimate"] if g else None, "value": f"{g['unread_estimate']:,}" if g else "n/a", "note": f"{g['cleared']:,} cleared today" if g else "not connected"},
    ]
    if fo and inbox:
        kpis.append({"key": "hotmail", "label": "Hotmail unread", "num": inbox["unread"], "value": f"{inbox['unread']:,}", "note": f"{inbox['total']:,} total"})
    nxt = []
    for t in sports:
        for gm in t["next"][:1]:
            d = short_date(gm["when"])
            if d:
                nxt.append((d, t["team"], gm["name"]))
    if nxt:
        nxt.sort()
        d, team, name = nxt[0]
        kpis.append({"label": "Next game", "value": d.strftime("%a %-I:%M %p"), "note": f"{team}: {name}"})

    # ---- channels
    def ch(name, handle, ok, stat, nxt_note):
        channels.append({"name": name, "handle": handle, "state": "live" if ok else "off", "stat": stat, "next": nxt_note})
    ch("iMessage and SMS", "Mac mini", bool(mac), f"{unread_texts} unread" if mac else "No report", mac.get("as_of", "Mac job has not reported") if mac else "Run the Mac installer.")
    ch("Gmail", cfg.get("gmail_address", ""), bool(g), f"{g['unread_estimate']:,} unread" if g else "Not connected", errors.get("gmail", ""))
    ch("Hotmail and Outlook", cfg.get("outlook_address", ""), bool(fo), f"{inbox['unread']:,} unread" if fo and inbox else "Not connected", errors.get("outlook", ""))
    ch("Calendars", "Google, Outlook", bool(events) or bool(src.get("gcal") is not None), f"{len(events)} event{'' if len(events)==1 else 's'} in 7 days", errors.get("gcal", ""))
    yt = src.get("youtube")
    ch("YouTube", cfg.get("youtube_handle", ""), bool(yt), f"{yt['subs']:,} subs, {yt['videos']} videos, {yt['views_30d'] if yt['views_30d'] is not None else 'n/a'} views in 30 days" if yt else "Not connected", errors.get("youtube", ""))
    for m in cfg.get("manual_channels", []):
        channels.append({"name": m["name"], "handle": m.get("handle", ""), "state": "snap", "stat": m.get("stat", ""), "next": f"Manual entry, as of {m.get('as_of','?')}. No official feed."})
    # ---- inbox detail for the Inbox scene and drawers
    inbox_detail = {}
    if g:
        senders = [{"d": d_, "n": c_} for d_, c_ in Counter(m["domain"] for m in g["recent"] if m.get("domain")).most_common(8)]
        inbox_detail["gmail"] = {"unread": g["unread_estimate"], "cleared": g["cleared"], "cats": g.get("cats") or {}, "senders": senders}
    if fo and inbox:
        top = sorted([f for f in fo if f["unread"] > 0], key=lambda f: -f["unread"])[:7]
        inbox_detail["hotmail"] = {"unread": inbox["unread"], "total": inbox["total"], "swept": src.get("outlook_swept", 0),
                                   "folders": [{"name": f["name"], "unread": f["unread"]} for f in top]}
    if mac:
        inbox_detail["texts"] = {"unread": unread_texts, "chats": mac.get("unread_chats", 0), "waiting": (mac.get("waiting") or [])[:6]}
    events_out = [{"title": e["title"], "start": e["start"], "all_day": e["all_day"], "cal": e.get("cal", ""), "end": e.get("end")} for e in events]
    return {"generated": n.isoformat(), "meta": {"name": cfg.get("name", "Brian"), "lat": cfg.get("lat", 36.0217), "lon": cfg.get("lon", -78.4756), "tz": "America/New_York", "dim": cfg.get("night_dim", True)},
            "events": events_out, "kpis": kpis, "tasks": tasks[:9], "week": week, "teams": sports,
            "triage": triage, "channels": channels, "inbox": inbox_detail, "errors": errors}
