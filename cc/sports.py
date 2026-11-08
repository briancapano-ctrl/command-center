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
    return {
        "name": ev.get("shortName") or ev.get("name"),
        "when": ev.get("date"),
        "state": status.get("state"),  # pre / in / post
        "detail": status.get("shortDetail"),
        "score": score,
    }


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
        out.append({"team": label, "path": path, "abbr": team_slug.upper(), "live": live[:1], "next": upcoming[:3], "last": done[-1:]})
    return out
