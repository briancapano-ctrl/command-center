"""Headlines for the News scene and the ticker. Free public RSS feeds and ESPN JSON, no keys, standard library only.
Fetched at most every 45 minutes (cached encrypted in state/news.json) so the repo does not grow faster."""
import re, html, json, os, datetime as dt, email.utils, urllib.request, xml.etree.ElementTree as ET
from .util import now, TZ

UA = {"User-Agent": "Mozilla/5.0 (CommandCenter personal dashboard)"}
ATOM = "{http://www.w3.org/2005/Atom}"
GN = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="

# key, label, max age in days, feeds (source name or None to read it from the item, url, optional filter)
SECTIONS = [
    ("philly", "Philly sports", 4, []),  # filled by _philly()
    ("hotel", "Hotel world", 7, [
        ("Hotel Dive", "https://www.hoteldive.com/feeds/news/"),
        ("Skift", "https://skift.com/feed/", r"(?i)\b(hotels?|hospitality|lodging|resorts?|Marriott|Hilton|Hyatt|IHG|Accor|Wyndham|Choice|Best Western|Ennismore|Airbnb|guest)\b"),
        (None, GN + "%22hotel+technology%22+OR+%22hospitality+technology%22+OR+%22hotel+wifi%22+when:7d"),
    ]),
    ("local", "Close to home", 3, [
        ("WRAL", "https://www.wral.com/news/rss/48/"),
        ("ABC11", "https://abc11.com/feed/", r"\b(NC|North Carolina|Raleigh|Durham|Wake|Triangle|Franklin|Youngsville|Cary|Chapel Hill|Johnston|Granville|Wilson|Fayetteville|Hurricanes|NC State|UNC|Duke)\b"),
    ]),
    ("world", "Nation and world", 2, [
        ("NPR", "https://feeds.npr.org/1001/rss.xml"),
        (None, "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"),
    ]),
    ("tech", "AI and tech", 4, [
        ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ]),
]
TEAM_WORDS = {"Eagles": ("eagles",), "Flyers": ("flyers",), "Phillies": ("phillies",)}
ESPN = {"Eagles": "football/nfl", "Flyers": "hockey/nhl", "Phillies": "baseball/mlb"}
PER_SECTION = 10


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _when(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = email.utils.parsedate_to_datetime(s)
    except Exception:
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(TZ)


def parse_feed(raw, source=None):
    """RSS 2.0 or Atom -> [{t, src, u, ts}]"""
    root = ET.fromstring(raw)
    out = []
    for it in root.findall(".//item"):
        t = _clean(it.findtext("title"))
        src = source or _clean(it.findtext("source")) or ""
        if not source and " - " in t:  # Google News: "Headline - Publisher"
            head, _, pub = t.rpartition(" - ")
            if head and len(pub) < 60:
                t, src = head.strip(), src or pub.strip()
        cats = " ".join(_clean(c.text) for c in it.findall("category"))
        out.append({"t": t, "src": src, "u": (it.findtext("link") or "").strip(), "cats": cats,
                    "d": _when(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date"))})
    for it in root.findall(f".//{ATOM}entry"):
        link = ""
        for l in it.findall(f"{ATOM}link"):
            if l.get("rel") in (None, "alternate"):
                link = l.get("href") or ""
                break
        out.append({"t": _clean(it.findtext(f"{ATOM}title")), "src": source or "", "u": link,
                    "d": _when(it.findtext(f"{ATOM}published") or it.findtext(f"{ATOM}updated"))})
    return [x for x in out if x["t"]]


def _norm(t):
    return re.sub(r"[^a-z0-9 ]", "", t.lower())[:70]


def _finish(items, max_age_days, n):
    cutoff = n - dt.timedelta(days=max_age_days)
    seen, keep = set(), []
    for x in sorted([x for x in items if x.get("d") and cutoff <= x["d"] <= n + dt.timedelta(hours=2)], key=lambda x: x["d"], reverse=True):
        k = _norm(x["t"])
        if k in seen:
            continue
        seen.add(k)
        keep.append({"t": x["t"][:160], "src": x["src"][:40], "u": x["u"][:400], "ts": x["d"].isoformat(), **({"tag": x["tag"]} if x.get("tag") else {})})
        if len(keep) >= PER_SECTION:
            break
    return keep


def _philly(errors):
    """Team stories from ESPN plus the Inquirer, kept only when they are really about the Eagles, Flyers or Phillies."""
    items = []
    for team, path in ESPN.items():
        try:
            j = json.loads(_get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/news?team=phi&limit=12"))
            for a in j.get("articles", []):
                if not any(w in (a.get("headline") or "").lower() for w in TEAM_WORDS[team]):
                    continue
                items.append({"t": _clean(a.get("headline")), "src": "ESPN", "u": ((a.get("links") or {}).get("web") or {}).get("href", ""),
                              "d": _when(a.get("published")), "tag": team})
        except Exception as e:
            errors[f"news_espn_{team.lower()}"] = str(e)[:120]
    try:
        for x in parse_feed(_get("https://www.inquirer.com/arc/outboundfeeds/rss/category/sports/?outputType=xml", 25), "Inquirer"):
            hay = (x["t"] + " " + x["u"]).lower()
            for team, words in TEAM_WORDS.items():
                if any(w in hay for w in words):
                    items.append({**x, "tag": team})
                    break
    except Exception as e:
        errors["news_inquirer"] = str(e)[:120]
    return items


def _allbridge(errors, n):
    """Company mentions in the last 120 days, shown first in Hotel world with an Allbridge tag."""
    try:
        got = parse_feed(_get(GN + "Allbridge+hotel+OR+hospitality+OR+%22property+technology%22"))
    except Exception as e:
        errors["news_allbridge"] = str(e)[:120]
        return []
    hits = [{**x, "tag": "Allbridge"} for x in got if "allbridge" in x["t"].lower()]
    return _finish(hits, 120, n)[:3]


def alerts(lat, lon):
    """Active National Weather Service alerts for home. Empty list when the sky is quiet."""
    req = urllib.request.Request(f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}",
                                 headers={"User-Agent": "CommandCenter personal dashboard", "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read())
    out = []
    for f in j.get("features", [])[:4]:
        p = f.get("properties") or {}
        out.append({"event": p.get("event", ""), "sev": p.get("severity", ""), "head": _clean(p.get("headline"))[:180], "ends": p.get("ends") or p.get("expires")})
    return out


def collect(errors=None, cfg=None):
    errors = {} if errors is None else errors
    n = now()
    out = []
    for key, label, age, feeds in SECTIONS:
        items = _philly(errors) if key == "philly" else []
        for src, url, *flt in feeds:
            try:
                got = parse_feed(_get(url), src)
                if flt:
                    rx = re.compile(flt[0])
                    got = [x for x in got if rx.search(x["t"] + " " + x.get("cats", ""))]
                items += got
            except Exception as e:
                errors[f"news_{key}"] = f"{(src or 'Google News')}: {str(e)[:100]}"
        keep = _finish(items, age, n)
        if key == "hotel":
            ab = _allbridge(errors, n)
            have = {_norm(x["t"]) for x in ab}
            keep = (ab + [x for x in keep if _norm(x["t"]) not in have])[:PER_SECTION]
        out.append({"key": key, "label": label, "items": keep})
    if not any(s["items"] for s in out):
        raise RuntimeError("no headlines from any feed")
    return {"as_of": n.isoformat(), "sections": out}


def cached(path, pw, encrypt, decrypt, errors, max_age_min=45):
    """Reuse the last fetch for up to 45 minutes. Falls back to the cache (up to a day old) if every feed fails."""
    old = None
    if os.path.exists(path):
        try:
            old = decrypt(json.load(open(path)), pw)
        except Exception:
            old = None
    age = (now() - dt.datetime.fromisoformat(old["as_of"])).total_seconds() / 60 if old and old.get("as_of") else 1e9
    if old and age < max_age_min:
        return old
    try:
        fresh = collect({})  # one dead feed is normal; only a total failure is reported
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(encrypt(fresh, pw), open(path, "w"))
        return fresh
    except Exception as e:
        errors["news"] = str(e)[:160]
        return old if old and age < 1440 else None
