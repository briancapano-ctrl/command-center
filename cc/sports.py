"""Eagles, Flyers, Phillies from ESPN's public JSON. No key needed."""
from .util import http, short_date, now

TEAMS = [
    ("Eagles", "football/nfl"),
    ("Flyers", "hockey/nhl"),
    ("Phillies", "baseball/mlb"),
]


def _event(ev):
    comp = (ev.get("competitions") or [{}])[0]
    teams = comp.get("competitors") or []
    status = (comp.get("status") or ev.get("status") or {}).get("type", {})
    score = {}
    for t in teams:
        s = t.get("score")
        if isinstance(s, dict):
            s = s.get("displayValue")
        score[(t.get("team") or {}).get("abbreviation", "?")] = s
    tv = [((b.get("media") or {}).get("shortName") or "") for b in comp.get("broadcasts") or []]
    out = {
        "name": ev.get("shortName") or ev.get("name"),
        "when": ev.get("date"),
        "state": status.get("state"),  # pre / in / post
        "detail": status.get("shortDetail"),
        "score": score,
    }
    if any(tv):
        out["tv"] = ", ".join(x for x in tv if x)[:30]
    venue = (comp.get("venue") or {}).get("fullName")
    if venue:
        out["venue"] = venue[:60]
    me = next((t for t in teams if (t.get("team") or {}).get("abbreviation") == "PHI"), None)
    if me and status.get("state") == "post" and me.get("winner") is not None:
        out["won"] = bool(me.get("winner"))
    return out


def _team_info(path, slug):
    """Record, colors and logo. Optional: the card still works without it."""
    try:
        t = http("GET", f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{slug}").get("team") or {}
    except Exception:
        return {}
    rec = ((t.get("record") or {}).get("items") or [{}])[0].get("summary")
    info = {"record": rec, "color": t.get("color"), "alt": t.get("alternateColor"), "standing": t.get("standingSummary")}
    return {k: v for k, v in info.items() if v}


def collect(team_slug="phi"):
    out = []
    n = now()
    for label, path in TEAMS:
        j = http("GET", f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{team_slug}/schedule")
        evs = [_event(e) for e in j.get("events", [])]
        live = [e for e in evs if e["state"] == "in"]
        upcoming = [e for e in evs if e["state"] == "pre" and short_date(e["when"]) and short_date(e["when"]) >= n]
        upcoming.sort(key=lambda e: e["when"])
        done = [e for e in evs if e["state"] == "post"]
        done.sort(key=lambda e: e["when"])
        row = {"team": label, "path": path, "abbr": team_slug.upper(), "live": live[:1], "next": upcoming[:3], "last": done[-1:]}
        row.update(_team_info(path, team_slug))
        out.append(row)
    return out
