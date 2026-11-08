"""Shared helpers. Standard library only, so it runs anywhere."""
import json, urllib.request, urllib.parse, urllib.error, datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")


def now():
    return dt.datetime.now(TZ)


def http(method, url, headers=None, body=None, form=None, timeout=30):
    """Return parsed JSON (or {} for empty bodies). Raises RuntimeError with a short message."""
    h = dict(headers or {})
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {e.code} {url.split('?')[0]}: {detail}")
    except Exception as e:  # network, timeout, bad JSON
        raise RuntimeError(f"{type(e).__name__} {url.split('?')[0]}: {e}")


def domain_of(addr):
    addr = (addr or "").lower()
    if "<" in addr and ">" in addr:
        addr = addr.split("<")[-1].split(">")[0]
    return addr.split("@")[-1].strip()


def short_date(iso):
    try:
        d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=TZ)
        return d.astimezone(TZ)
    except Exception:
        return None


def safe(label, fn, errors):
    """Run a collector. On failure record the error and return None so the page shows 'stale'."""
    try:
        return fn()
    except Exception as e:
        errors[label] = str(e)[:200]
        return None
