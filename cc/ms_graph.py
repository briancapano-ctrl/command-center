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
    j = _g(tok, "/me/mailFolders?$top=100&$select=id,displayName,unreadItemCount,totalItemCount,childFolderCount")
    out = []
    for f in j.get("value", []):
        out.append({"name": f["displayName"], "unread": f.get("unreadItemCount", 0), "total": f.get("totalItemCount", 0)})
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


def calendar(tok, days=7):
    t0 = now()
    t1 = t0 + dt.timedelta(days=days)
    q = urllib.parse.urlencode({"startDateTime": t0.isoformat(), "endDateTime": t1.isoformat(),
                                "$orderby": "start/dateTime", "$top": 50, "$select": "subject,start,isAllDay"})
    j = http("GET", f"{G}/me/calendarView?{q}", headers={"Authorization": f"Bearer {tok}", "Prefer": 'outlook.timezone="America/New_York"'})
    return [{"title": e.get("subject", "(no title)"), "start": (e.get("start") or {}).get("dateTime"),
             "all_day": bool(e.get("isAllDay")), "cal": "Outlook"} for e in j.get("value", [])]
