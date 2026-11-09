"""Gmail, Google Calendar and YouTube using one OAuth refresh token."""
import datetime as dt, urllib.parse
from .util import http, now, domain_of

TOK = "https://oauth2.googleapis.com/token"
CLEANUP_LABEL = "Cleanup"


def access_token(cid, secret, refresh):
    j = http("POST", TOK, form={"client_id": cid, "client_secret": secret,
                                "refresh_token": refresh, "grant_type": "refresh_token"})
    return j["access_token"]


def _g(tok, url, **kw):
    return http("GET", url, headers={"Authorization": f"Bearer {tok}"}, **kw)


def _p(tok, url, body):
    return http("POST", url, headers={"Authorization": f"Bearer {tok}"}, body=body)


def _label_id(tok, name):
    labels = _g(tok, "https://gmail.googleapis.com/gmail/v1/users/me/labels").get("labels", [])
    for l in labels:
        if l["name"] == name:
            return l["id"]
    return _p(tok, "https://gmail.googleapis.com/gmail/v1/users/me/labels", {"name": name})["id"]


def _list_ids(tok, q, cap=3000):
    ids, page = [], None
    while len(ids) < cap:
        params = {"q": q, "maxResults": 500}
        if page:
            params["pageToken"] = page
        j = _g(tok, "https://gmail.googleapis.com/gmail/v1/users/me/messages?" + urllib.parse.urlencode(params))
        ids += [m["id"] for m in j.get("messages", [])]
        page = j.get("nextPageToken")
        if not page:
            break
    return ids


def sweep_promos(tok):
    """Approved standing action: archive + mark read promotions/social/older updates, labeled for undo."""
    label = _label_id(tok, f"{CLEANUP_LABEL} {now():%Y-%m-%d}")
    total = 0
    # Updates (approved Nov 8): only mail older than 2 days that Gmail did not flag important or you did not star,
    # so fresh codes, receipts and bank alerts still show up first.
    for cat, extra in (("promotions", ""), ("social", ""), ("updates", " older_than:2d -is:important -is:starred")):
        ids = _list_ids(tok, f"is:unread in:inbox category:{cat}{extra}")
        for i in range(0, len(ids), 1000):
            _p(tok, "https://gmail.googleapis.com/gmail/v1/users/me/messages/batchModify",
               {"ids": ids[i:i + 1000], "addLabelIds": [label], "removeLabelIds": ["INBOX", "UNREAD"]})
        total += len(ids)
    return total


def gmail(tok, sweep=True, recent_n=50):
    cleared = sweep_promos(tok) if sweep else 0
    cats = {}
    for key, lid in (("inbox", "INBOX"), ("primary", "CATEGORY_PERSONAL"), ("updates", "CATEGORY_UPDATES"),
                     ("promotions", "CATEGORY_PROMOTIONS"), ("social", "CATEGORY_SOCIAL"), ("forums", "CATEGORY_FORUMS")):
        try:
            cats[key] = _g(tok, f"https://gmail.googleapis.com/gmail/v1/users/me/labels/{lid}").get("messagesUnread", 0)
        except RuntimeError:
            cats[key] = None
    q = "is:unread in:inbox"
    j = _g(tok, "https://gmail.googleapis.com/gmail/v1/users/me/messages?" +
           urllib.parse.urlencode({"q": q, "maxResults": recent_n}))
    est = cats.get("inbox")
    if est is None:
        est = j.get("resultSizeEstimate", 0)
    recent = []
    for m in j.get("messages", []):
        d = _g(tok, f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}?format=metadata"
                    "&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date")
        h = {x["name"]: x["value"] for x in d.get("payload", {}).get("headers", [])}
        recent.append({"from": h.get("From", ""), "domain": domain_of(h.get("From", "")),
                       "subject": h.get("Subject", ""), "date": h.get("Date", "")})
    return {"unread_estimate": est, "recent": recent, "cleared": cleared, "cats": cats}


CAL_NAMES = []


def calendar(tok, days=7):
    global CAL_NAMES
    t0 = now()
    t1 = t0 + dt.timedelta(days=days)
    cals = _g(tok, "https://www.googleapis.com/calendar/v3/users/me/calendarList").get("items", [])
    CAL_NAMES = [c.get("summary", "") for c in cals]
    out = []
    for c in cals:
        params = {"timeMin": t0.isoformat(), "timeMax": t1.isoformat(), "singleEvents": "true",
                  "orderBy": "startTime", "maxResults": 50}
        cid = urllib.parse.quote(c["id"])
        try:
            ev = _g(tok, f"https://www.googleapis.com/calendar/v3/calendars/{cid}/events?" + urllib.parse.urlencode(params))
        except RuntimeError:
            continue
        for e in ev.get("items", []):
            s = e.get("start", {})
            out.append({"title": e.get("summary", "(no title)"), "start": s.get("dateTime") or s.get("date"),
                        "all_day": "date" in s, "cal": c.get("summary", ""),
                        "end": (e.get("end") or {}).get("dateTime")})
    out.sort(key=lambda e: e["start"] or "")
    return out


def youtube(tok):
    ch = _g(tok, "https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&mine=true")
    item = (ch.get("items") or [{}])[0]
    st = item.get("statistics", {})
    start = (now() - dt.timedelta(days=30)).strftime("%Y-%m-%d")
    end = now().strftime("%Y-%m-%d")
    views30 = None
    try:
        r = _g(tok, "https://youtubeanalytics.googleapis.com/v2/reports?" + urllib.parse.urlencode(
            {"ids": "channel==MINE", "startDate": start, "endDate": end, "metrics": "views"}))
        views30 = (r.get("rows") or [[0]])[0][0]
    except RuntimeError:
        pass
    return {"handle": (item.get("snippet") or {}).get("customUrl", ""),
            "subs": int(st.get("subscriberCount", 0)), "videos": int(st.get("videoCount", 0)),
            "views_total": int(st.get("viewCount", 0)), "views_30d": views30}
