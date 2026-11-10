"""Hotmail/Outlook.com through Microsoft Graph (personal account)."""
import datetime as dt, urllib.parse, json
from .util import http, now, domain_of

TOK = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
G = "https://graph.microsoft.com/v1.0"
SCOPE = "offline_access Mail.ReadWrite Calendars.Read"


def refresh(client_id, refresh_token):
    """Returns (access_token, new_refresh_token). Microsoft rotates refresh tokens, so callers must save the new one."""
    j = http("POST", TOK, form={"client_id": client_id, "grant_type": "refresh_token",
                                "refresh_token": refresh_token, "scope": SCOPE})
    return j["access_token"], j.get("refresh_token", refresh_token)


def _g(tok, path):
    return http("GET", G + urllib.parse.quote(path, safe="/?$&=,:()"), headers={"Authorization": f"Bearer {tok}"})


def folders(tok):
    j = _g(tok, "/me/mailFolders?$top=100&$select=id,displayName,unreadItemCount,totalItemCount,childFolderCount"
                "&$expand=singleValueExtendedProperties($filter=id eq 'Long 0xe08')")
    out = []
    for f in j.get("value", []):
        sz = next((int(p["value"]) for p in f.get("singleValueExtendedProperties", []) if p.get("value", "").isdigit()), None)
        out.append({"name": f["displayName"], "unread": f.get("unreadItemCount", 0), "total": f.get("totalItemCount", 0), "bytes": sz})
        if f.get("childFolderCount"):
            try:
                c = _g(tok, f"/me/mailFolders/{f['id']}/childFolders?$top=50&$select=displayName,unreadItemCount,totalItemCount")
                out += [{"name": f["displayName"] + "/" + x["displayName"], "unread": x.get("unreadItemCount", 0), "total": x.get("totalItemCount", 0)}
                        for x in c.get("value", [])]
            except Exception:
                pass
    return out


def inbox_unread(tok, n=100):
    j = _g(tok, "/me/mailFolders/inbox/messages?$top=%d&$orderby=receivedDateTime desc"
                "&$select=id,from,subject,receivedDateTime,isRead" % n)
    out = []
    for m in j.get("value", []):
        if m.get("isRead"):
            continue
        addr = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "")
        out.append({"id": m["id"], "from": addr, "domain": domain_of(addr),
                    "subject": m.get("subject", ""), "date": m.get("receivedDateTime", "")})
    return out


def sweep(tok, promo_domains, msgs):
    """Approved standing action: mark read and archive unread inbox mail from promo sender domains."""
    wanted = [m for m in msgs if any(m["domain"] == d or m["domain"].endswith("." + d) for d in promo_domains)]
    for i in range(0, len(wanted), 10):
        reqs = []
        for k, m in enumerate(wanted[i:i + 10]):
            reqs.append({"id": f"r{k}", "method": "PATCH", "url": f"/me/messages/{m['id']}",
                         "headers": {"Content-Type": "application/json"}, "body": {"isRead": True}})
        http("POST", G + "/$batch", headers={"Authorization": f"Bearer {tok}"}, body={"requests": reqs})
        reqs = []
        for k, m in enumerate(wanted[i:i + 10]):
            reqs.append({"id": f"m{k}", "method": "POST", "url": f"/me/messages/{m['id']}/move",
                         "headers": {"Content-Type": "application/json"}, "body": {"destinationId": "archive"}})
        http("POST", G + "/$batch", headers={"Authorization": f"Bearer {tok}"}, body={"requests": reqs})
    return len(wanted)


PROTECTED = ("robinhood", "citi", "pennmutual", "starlink", "apple.com", "perplexity", "stubhub", "school")


def sweep_backlog(tok, promo_domains, cursor, pages=20):
    """Rolling pass back through the inbox, newest to oldest, for approved promo senders only (mark read and archive).
    Pages by received date, which is cheap on a large mailbox. Returns (swept, next_cursor); cursor None means start over."""
    swept = 0
    for _ in range(pages):
        q = "/me/mailFolders/inbox/messages?$top=100&$orderby=receivedDateTime desc&$select=id,from,isRead,receivedDateTime"
        if cursor:
            q += "&$filter=receivedDateTime lt " + cursor
        j = _g(tok, q)
        vals = j.get("value", [])
        if not vals:
            return swept, None
        hit = []
        for m in vals:
            if m.get("isRead"):
                continue
            dom = domain_of(((m.get("from") or {}).get("emailAddress") or {}).get("address", ""))
            if any(x in dom for x in PROTECTED):
                continue
            if any(dom == d or dom.endswith("." + d) for d in promo_domains):
                hit.append(m["id"])
        for i in range(0, len(hit), 10):
            chunk = hit[i:i + 10]
            for op, mk in (("r", lambda mid: {"method": "PATCH", "url": f"/me/messages/{mid}", "headers": {"Content-Type": "application/json"}, "body": {"isRead": True}}),
                           ("m", lambda mid: {"method": "POST", "url": f"/me/messages/{mid}/move", "headers": {"Content-Type": "application/json"}, "body": {"destinationId": "archive"}})):
                http("POST", G + "/$batch", headers={"Authorization": f"Bearer {tok}"},
                     body={"requests": [dict(mk(mid), id=f"{op}{k}") for k, mid in enumerate(chunk)]})
        swept += len(hit)
        cursor = vals[-1].get("receivedDateTime")
        if len(vals) < 100:
            return swept, None
    return swept, cursor


def audit(tok, budget_s=540, full=False):
    """Read-only size audit of messages with attachments (the bulk of mailbox size). Returns an aggregate report."""
    import time
    t0 = time.time()
    rep = {"folders": {}, "note": "messages with attachments only; time-capped"}
    for fid in (("inbox",) if full else ("inbox", "archive", "sentitems", "deleteditems", "junkemail")):
        agg, big, years, n, total, pages, done = {}, [], {}, 0, 0, 0, False
        q = (f"/me/mailFolders/{fid}/messages?{'' if full else '$filter=hasAttachments eq true&'}$top=100&$select=id,from,subject,receivedDateTime,isRead"
             "&$expand=singleValueExtendedProperties($filter=id eq 'Integer 0xe08')")
        url = G + urllib.parse.quote(q, safe="/?$&=,:()'")
        while url and time.time() - t0 < budget_s:
            j = None
            for _ in range(3):
                try:
                    j = http("GET", url, headers={"Authorization": f"Bearer {tok}"})
                    break
                except Exception:
                    time.sleep(2)
            if j is None:
                break
            pages += 1
            for m in j.get("value", []):
                sz = next((int(p["value"]) for p in m.get("singleValueExtendedProperties", []) if str(p.get("value", "")).isdigit()), 0)
                addr = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "")
                d = domain_of(addr) or addr
                a = agg.setdefault(d, [0, 0, 0]); a[0] += sz; a[1] += 1; a[2] += 0 if m.get("isRead") else 1
                y = (m.get("receivedDateTime") or "")[:4]; years[y] = years.get(y, 0) + sz
                n += 1; total += sz
                big.append((sz, m.get("receivedDateTime", "")[:10], addr, (m.get("subject") or "")[:70], m["id"]))
            big = sorted(big, reverse=True)[:40]
            url = j.get("@odata.nextLink")
            done = not url
        rep["folders"][fid] = {"complete": done, "pages": pages, "messages_with_attachments": n, "bytes": total,
                               "top_senders": sorted(([d, v[0], v[1], v[2]] for d, v in agg.items()), key=lambda x: -x[1])[:70],
                               "by_year": dict(sorted(years.items())), "largest": [list(b) for b in big]}
    return rep

DELETE_DOMAINS = (
    "em1.mint.intuit.com", "mint.com", "d.email.draftkings.com", "auth.draftkings.com", "creativemarket.com",
    "email.dailywire.com", "mailer.dailywire.com", "news.washingtonexaminer.com", "theepochtimes.com", "smwsa.com",
    "pixelfilmstudios.com", "email.consumerreports.org", "ee.mgmresorts.com", "brandedbills.com", "email-marriott.com",
    "email.chipotle.com", "shrunkenhead.com", "mixtiles.com", "e.dji.com", "em.homegoods.com", "e-mail.gopro.com",
    "mail.petsmart.com", "47brand.com", "e.wine.com", "info.hollywoodfeed.com", "email.sel.sony.com",
    "info.chamberlain.com", "uber.com", "email.informeddelivery.usps.com", "usps.com", "mail.coinbase.com",
    "hotelsmag.net", "hotelsmag.com")


def delete_approved(tok, cursor, budget_s=1500):
    """User-approved permanent deletion (Nov 10, 2026): UNREAD inbox mail from the listed sender domains only.
    Scans newest to oldest by received date. Returns (deleted_by_domain, next_cursor); cursor None means finished."""
    import time
    t0 = time.time()
    done = {}
    while time.time() - t0 < budget_s:
        q = "/me/mailFolders/inbox/messages?$top=100&$orderby=receivedDateTime desc&$select=id,from,isRead,receivedDateTime"
        if cursor:
            q += "&$filter=receivedDateTime lt " + cursor
        j = None
        for _ in range(3):
            try:
                j = _g(tok, q); break
            except Exception:
                time.sleep(2)
        if j is None:
            return done, cursor
        vals = j.get("value", [])
        if not vals:
            return done, None
        hit = []
        for m in vals:
            if m.get("isRead"):
                continue
            dom = domain_of(((m.get("from") or {}).get("emailAddress") or {}).get("address", ""))
            if not dom or any(x in dom for x in PROTECTED):
                continue
            if any(dom == d or dom.endswith("." + d) for d in DELETE_DOMAINS):
                hit.append((m["id"], dom))
        for i in range(0, len(hit), 20):
            chunk = hit[i:i + 20]
            http("POST", G + "/$batch", headers={"Authorization": f"Bearer {tok}"},
                 body={"requests": [{"id": str(k), "method": "POST", "url": f"/me/messages/{mid}/permanentDelete"} for k, (mid, _) in enumerate(chunk)]})
            for _, dom in chunk:
                done[dom] = done.get(dom, 0) + 1
        cursor = vals[-1].get("receivedDateTime")
        if len(vals) < 100:
            return done, None
    return done, cursor


def calendar(tok, days=7):
    t0 = now()
    t1 = t0 + dt.timedelta(days=days)
    q = urllib.parse.urlencode({"startDateTime": t0.isoformat(), "endDateTime": t1.isoformat(),
                                "$orderby": "start/dateTime", "$top": 50, "$select": "subject,start,isAllDay"})
    j = http("GET", f"{G}/me/calendarView?{q}", headers={"Authorization": f"Bearer {tok}", "Prefer": 'outlook.timezone="America/New_York"'})
    return [{"title": e.get("subject", "(no title)"), "start": (e.get("start") or {}).get("dateTime"),
             "all_day": bool(e.get("isAllDay")), "cal": "Outlook"} for e in j.get("value", [])]
