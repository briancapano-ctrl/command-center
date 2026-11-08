"""Entry point. `python -m cc.build` collects everything, writes docs/index.html (encrypted), and optionally pushes a phone alert."""
import json, os, subprocess, sys, datetime as dt, urllib.request
from . import sports, google_api as G, ms_graph as M, priorities, render
from .util import safe, now, short_date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MS_STATE = os.path.join(ROOT, "state", "ms.json")
MAC_BLOB = os.path.join(ROOT, "inbox", "mac.enc")


def load_cfg():
    raw = os.environ.get("CC_CONFIG")
    if raw:
        return json.loads(raw)
    p = os.path.join(ROOT, "config.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def read_mac(passphrase):
    if not os.path.exists(MAC_BLOB):
        raise RuntimeError("no Mac snapshot yet")
    r = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-pass", "env:CC_PW", "-in", MAC_BLOB],
                       capture_output=True, env={**os.environ, "CC_PW": passphrase})
    if r.returncode != 0:
        raise RuntimeError("could not decrypt Mac snapshot")
    snap = json.loads(r.stdout)
    age = (now() - short_date(snap["as_of_iso"])).total_seconds() / 3600
    if age > 36:
        raise RuntimeError(f"Mac snapshot is {age:.0f} hours old")
    return snap


HIST = os.path.join(ROOT, "state", "history.json")
LAST = os.path.join(ROOT, "state", "last.json")
NOTE = os.path.join(ROOT, "state", "notified.json")


def push(topic, tasks):
    top = tasks[:3]
    body = "\n".join(f"- {t['t']}" for t in top) or "Nothing needs you today."
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode(), headers={"Title": "Command Center", "Tags": "calendar"}, method="POST")
    urllib.request.urlopen(req, timeout=15).read()


def update_history(model, pw, src):
    """Keep a small encrypted time series so the page can draw trends."""
    pts = []
    if os.path.exists(HIST):
        try:
            pts = render.decrypt(json.load(open(HIST)), pw).get("points", [])
        except Exception:
            pts = []
    cur = {k["key"]: k["num"] for k in model["kpis"] if k.get("num") is not None and k.get("key") != "need"}
    yt = src.get("youtube")
    if yt:
        cur["yt_views"] = yt["views_total"]
    t = now()
    if not pts or (t - short_date(pts[-1]["t"])).total_seconds() >= 1500 or any(pts[-1].get(k) != v for k, v in cur.items()):
        pts.append({"t": t.isoformat(), **cur})
    pts = pts[-500:]
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    json.dump(render.encrypt({"points": pts}, pw), open(HIST, "w"))
    keys = {k for p in pts for k in p if k != "t"}
    return {k: [p.get(k) for p in pts[-96:] if p.get(k) is not None] for k in keys}


def health(src, model_time):
    """Per-source freshness for the status strip."""
    err = src.get("errors", {})
    mac = src.get("mac")
    def row(key, label, ok, updated):
        return {"key": key, "label": label, "ok": bool(ok), "updated": updated if ok else None, "err": err.get(key, "") if not ok else ""}
    t = model_time
    return [
        row("mac", "Texts and reminders", mac, (mac or {}).get("as_of_iso")),
        row("gmail", "Gmail", src.get("gmail"), t),
        row("outlook", "Hotmail", src.get("outlook_folders"), t),
        row("gcal", "Calendars", src.get("gcal") is not None or src.get("outlook_cal") is not None, t),
        row("youtube", "YouTube", src.get("youtube"), t),
        row("sports", "Sports", src.get("sports"), t),
    ]


def should_notify(model):
    """One phone alert per day, at the first run after 6 AM Eastern."""
    n = now()
    if n.hour < 6:
        return False
    last = json.load(open(NOTE)).get("date") if os.path.exists(NOTE) else None
    return last != n.strftime("%Y-%m-%d")


def unchanged(model):
    """Skip rewriting the site when nothing changed in the last hour, so the repo history stays small."""
    sig = json.dumps({**{k: model[k] for k in ("kpis", "tasks", "week", "teams", "triage", "channels", "errors")},
                      "sources": [(x["key"], x["ok"]) for x in model["sources"]]}, sort_keys=True, default=str)
    import hashlib
    h = hashlib.sha256(sig.encode()).hexdigest()
    prev = json.load(open(LAST)) if os.path.exists(LAST) else {}
    fresh = prev.get("h") == h and prev.get("t") and (now() - short_date(prev["t"])).total_seconds() < 3300
    if not fresh:
        os.makedirs(os.path.dirname(LAST), exist_ok=True)
        json.dump({"h": h, "t": now().isoformat()}, open(LAST, "w"))
    return fresh


def collect(cfg, pw):
    err = {}
    src = {"errors": err}
    src["sports"] = safe("sports", sports.collect, err)
    env = os.environ
    if env.get("GOOGLE_REFRESH_TOKEN"):
        tok = safe("google", lambda: G.access_token(env["GOOGLE_CLIENT_ID"], env["GOOGLE_CLIENT_SECRET"], env["GOOGLE_REFRESH_TOKEN"]), err)
        if tok:
            src["gmail"] = safe("gmail", lambda: G.gmail(tok, sweep=cfg.get("sweep_gmail_promos", True)), err)
            src["gcal"] = safe("gcal", lambda: G.calendar(tok), err)
            src["youtube"] = safe("youtube", lambda: G.youtube(tok), err)
    refresh = None
    if os.path.exists(MS_STATE):
        refresh = safe("ms_state", lambda: render.decrypt(json.load(open(MS_STATE)), pw)["refresh"], err)
    refresh = refresh or env.get("MS_REFRESH_TOKEN")
    if refresh and env.get("MS_CLIENT_ID"):
        pair = safe("outlook", lambda: M.refresh(env["MS_CLIENT_ID"], refresh), err)
        if pair:
            tok, new_refresh = pair
            os.makedirs(os.path.dirname(MS_STATE), exist_ok=True)
            json.dump(render.encrypt({"refresh": new_refresh}, pw), open(MS_STATE, "w"))
            src["outlook_folders"] = safe("outlook", lambda: M.folders(tok), err)
            msgs = safe("outlook", lambda: M.inbox_unread(tok), err) or []
            src["outlook_swept"] = 0
            if cfg.get("outlook_promo_domains") and msgs:
                src["outlook_swept"] = safe("outlook", lambda: M.sweep(tok, cfg["outlook_promo_domains"], msgs), err) or 0
                msgs = M.inbox_unread(tok) if src["outlook_swept"] else msgs
            src["outlook_unread"] = msgs
            src["outlook_cal"] = safe("outlook_cal", lambda: M.calendar(tok), err)
    src["mac"] = safe("mac", lambda: read_mac(pw), err)
    return src


def main():
    pw = os.environ.get("CC_PASSPHRASE")
    if not pw:
        sys.exit("CC_PASSPHRASE is required")
    cfg = load_cfg()
    demo, plain = "--demo" in sys.argv, "--plain" in sys.argv
    snap = sys.argv[sys.argv.index("--snapshot") + 1] if "--snapshot" in sys.argv else None
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(ROOT, "docs")
    if snap:
        src = json.load(open(snap)); demo = True
    elif demo:
        from .demo import sample
        src = sample()
    else:
        src = collect(cfg, pw)
    model = priorities.build(src, cfg)
    model["sources"] = health(src, model["generated"])
    model["history"] = src.get("_history", {}) if demo else update_history(model, pw, src)
    if not demo and not plain and unchanged(model):
        print("no change; site left as is")
        return
    render.write_site(model, pw, out, plain=plain)
    print(f"built: {len(model['tasks'])} tasks, {len(model['errors'])} source errors")
    if os.environ.get("NTFY_TOPIC") and not demo and should_notify(model):
        if safe("notify", lambda: push(os.environ["NTFY_TOPIC"], model["tasks"]), model["errors"]) is None and "notify" not in model["errors"]:
            json.dump({"date": now().strftime("%Y-%m-%d")}, open(NOTE, "w"))


if __name__ == "__main__":
    main()
