#!/usr/bin/env python3
"""Runs on the Mac mini. Reads texts, reminders, Apple Calendar, birthdays, photo memories and home health locally, encrypts the result, pushes it to your GitHub repo.
Python 3.9 standard library plus the macOS `openssl` and `sqlite` already installed. Nothing leaves the Mac unencrypted."""
import base64, datetime as dt, glob, json, os, re, shutil, sqlite3, subprocess, sys, tempfile

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, ".config", "command-center", "env")
APPLE_EPOCH = 978307200
DAYS = 30  # only count unread texts newer than this, so ancient unread spam does not inflate the number
ENV = {}


def skip_lists():
    return {x.strip().lower() for x in ENV.get("CC_SKIP_LISTS", "To do").split(",") if x.strip()}


def work_re():
    words = [re.escape(x.strip()) for x in ENV.get("CC_WORK_WORDS", "Allbridge,bid,DIRECTV,Ruckus,COHO,Koch").split(",") if x.strip()]
    return re.compile(r"\b(" + "|".join(words) + r")", re.I) if words else None
SKIP_CALS = {"scheduled reminders", "found in mail", "found in natural language", "us holidays", "birthdays", "facebook birthdays", "default"}
CAL_DB = os.path.join(HOME, "Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb")
PHOTOS_DB = glob.glob(os.path.join(HOME, "Pictures/*.photoslibrary/database/Photos.sqlite"))
NET_LOG = os.path.join(HOME, "CommandCenter", "net.jsonl")
ASK = re.compile(r"(\?|can you|could you|please|let me know|when are you|are you able|need you|call me)", re.I)


def load_env():
    env = dict(os.environ)
    if os.path.exists(CONF):
        for line in open(CONF):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                env.setdefault(k, v)
    return env


def snapshot(path):
    """Copy a live SQLite DB (and WAL) so we never lock Messages or Reminders."""
    tmp = tempfile.mkdtemp()
    dst = os.path.join(tmp, "db.sqlite")
    shutil.copy(path, dst)
    for ext in ("-wal", "-shm"):
        if os.path.exists(path + ext):
            shutil.copy(path + ext, dst + ext)
    return dst


def last10(s):
    d = re.sub(r"\D", "", s or "")
    return d[-10:] if len(d) >= 10 else ""


def contacts():
    names = {}
    for p in glob.glob(os.path.join(HOME, "Library/Application Support/AddressBook/**/AddressBook-v22.abcddb"), recursive=True):
        try:
            db = sqlite3.connect(snapshot(p))
            people = {}
            for pk, f, l, nick, org in db.execute("select Z_PK, ZFIRSTNAME, ZLASTNAME, ZNICKNAME, ZORGANIZATION from ZABCDRECORD"):
                people[pk] = (nick or f or org or "").strip() + ((" " + l) if l and not nick and f else "")
            for owner, num in db.execute("select ZOWNER, ZFULLNUMBER from ZABCDPHONENUMBER"):
                if owner in people and last10(num):
                    names.setdefault(last10(num), people[owner].strip())
            for owner, addr in db.execute("select ZOWNER, ZADDRESS from ZABCDEMAILADDRESS"):
                if owner in people and addr:
                    names.setdefault(addr.lower(), people[owner].strip())
        except Exception:
            continue
    return names


def decode_body(text, blob):
    if text:
        return text
    if not blob:
        return ""
    try:
        i = blob.index(b"NSString") + len(b"NSString") + 5
        n = blob[i]
        i += 1
        if n == 0x81:
            n = int.from_bytes(blob[i:i + 2], "little")
            i += 2
        return blob[i:i + n].decode("utf-8", "replace")
    except Exception:
        return ""


def imessage():
    db = sqlite3.connect(snapshot(os.path.join(HOME, "Library/Messages/chat.db")))
    names = contacts()
    cutoff = (dt.datetime.now().timestamp() - DAYS * 86400 - APPLE_EPOCH) * 1e9
    rows = db.execute("""
        select c.ROWID, coalesce(c.display_name,''), c.chat_identifier, coalesce(c.room_name,''),
               sum(case when m.is_read=0 and m.is_from_me=0 and m.item_type=0 and m.date>? then 1 else 0 end) as unread
        from chat c join chat_message_join j on j.chat_id=c.ROWID join message m on m.ROWID=j.message_id
        group by c.ROWID having unread>0 order by unread desc""", (cutoff,)).fetchall()
    chats, waiting, total = [], [], 0
    now = dt.datetime.now().timestamp()
    for rid, disp, ident, room, unread in rows:
        total += unread
        label = disp.strip()
        if not label:
            label = names.get(last10(ident)) or names.get((ident or "").lower()) or ("Group chat" if room else "Direct chat")
        last = db.execute("""select m.text, m.attributedBody, m.is_from_me, m.date, m.associated_message_type from message m
            join chat_message_join j on j.message_id=m.ROWID where j.chat_id=? and m.item_type=0
            and coalesce(m.associated_message_type,0)=0 order by m.date desc limit 1""", (rid,)).fetchone()
        chats.append({"label": label, "unread": unread})
        if last and not last[2]:
            when = last[3] / 1e9 + APPLE_EPOCH
            hrs = (now - when) / 3600
            body = decode_body(last[0], last[1])
            if hrs <= 72 and ASK.search(body):
                waiting.append({"label": label, "ago": f"{int(hrs)}h" if hrs < 48 else f"{int(hrs // 24)}d",
                                "snippet": re.sub(r"\s+", " ", body).strip()[:90]})
    return {"unread_total": total, "unread_chats": len(chats),
            "top_unread": [{"label": c["label"], "unread": c["unread"]} for c in chats[:6]], "waiting": waiting[:6]}


def reminders():
    out, seen = [], set()
    skip, wre = skip_lists(), work_re()
    for p in glob.glob(os.path.join(HOME, "Library/Group Containers/group.com.apple.reminders/Container_v1/Stores/*.sqlite")):
        try:
            db = sqlite3.connect(snapshot(p))
            rows = db.execute("""select r.ZTITLE, r.ZDUEDATE, r.ZTIMEZONE, coalesce(l.ZNAME,''), coalesce(r.ZFLAGGED,0)
                from ZREMCDREMINDER r left join ZREMCDBASELIST l on l.Z_PK=r.ZLIST
                where coalesce(r.ZCOMPLETED,0)=0 and coalesce(r.ZMARKEDFORDELETION,0)=0
                and (r.ZDUEDATE is not null or coalesce(r.ZFLAGGED,0)=1)""").fetchall()
            for title, due, tz, lst, flagged in rows:
                if lst.lower() in skip or (wre and wre.search(title or "")):
                    continue
                if due is not None:
                    if tz:  # fixed instant
                        d = dt.datetime.fromtimestamp(due + APPLE_EPOCH).astimezone()
                    else:   # floating: the stored clock time is the local clock time
                        d = dt.datetime.utcfromtimestamp(due + APPLE_EPOCH).replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
                    key = (title, d.strftime("%Y-%m-%d %H:%M"))
                else:
                    d, key = None, (title, "flag")
                if key in seen:
                    continue
                seen.add(key)
                out.append({"title": title, "due": d.isoformat() if d else None, "list": lst, "flagged": bool(flagged)})
        except Exception:
            continue
    out.sort(key=lambda r: (r["due"] or "9999"))
    return out[:40]


def _cal_rows(days_ahead, cal_filter):
    """Occurrences from Apple Calendar's own cache, so recurring events are already expanded."""
    if not os.path.exists(CAL_DB):
        return []
    db = sqlite3.connect(snapshot(CAL_DB))
    t0 = dt.datetime.now().timestamp() - APPLE_EPOCH - 86400
    t1 = t0 + (days_ahead + 1) * 86400
    rows = db.execute("""select o.occurrence_date, o.occurrence_end_date, i.summary, i.all_day, c.title, coalesce(s.name,''), coalesce(l.title,'')
        from OccurrenceCache o join CalendarItem i on i.ROWID=o.event_id join Calendar c on c.ROWID=i.calendar_id
        left join Store s on s.ROWID=c.store_id left join Location l on l.ROWID=i.location_id
        where o.occurrence_date >= ? and o.occurrence_date < ? and coalesce(i.hidden,0)=0 and coalesce(i.status,0)<>3
        order by o.occurrence_date""", (t0, t1)).fetchall()
    out = []
    for st, en, title, all_day, cal, store, loc in rows:
        if not cal_filter(cal or "", store or ""):
            continue
        out.append((st, en, title or "(no title)", bool(all_day), cal or "", store or "", loc or ""))
    return out


def _iso(apple_ts, all_day):
    d = dt.datetime.fromtimestamp(apple_ts + APPLE_EPOCH)
    if all_day:  # the cache stores all-day occurrences at local midnight
        return d.strftime("%Y-%m-%d")
    return d.astimezone().isoformat()


def calendar():
    """iCloud / local calendars from Calendar.app. Skips the holiday feed, mail-detected items and anything already covered."""
    ok = lambda cal, store: cal.lower() not in SKIP_CALS and store.lower() not in ("other", "reminders", "subscribed calendars")
    out, seen = [], set()
    for st, en, title, all_day, cal, store, loc in _cal_rows(14, ok):
        key = (title, round(st))
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "start": _iso(st, all_day), "end": None if all_day else _iso(en, False), "all_day": all_day,
                    "cal": cal if cal and not re.match(r"^[0-9A-F-]{36}$", cal) else "iCloud", "location": loc})
    return out[:60]


def birthdays():
    """Contacts and Facebook birthdays that Calendar.app already knows about, next 45 days."""
    ok = lambda cal, store: cal.lower() in ("birthdays", "facebook birthdays")
    out, seen = [], set()
    for st, en, title, all_day, cal, store, loc in _cal_rows(45, ok):
        name = re.sub(r"[\u2019']s birthday$", "", title, flags=re.I).strip()
        day = _iso(st, True)
        if (name.lower(), day) in seen or dt.date.fromisoformat(day) < dt.date.today():
            continue
        seen.add((name.lower(), day))
        out.append({"name": name, "date": day, "src": "Facebook" if "facebook" in cal.lower() else "Contacts"})
    out.sort(key=lambda b: b["date"])
    return out[:12]


def photos():
    """'On this day' memories from the Photos library: a count, the years, and up to three small thumbnails."""
    if not PHOTOS_DB:
        return None
    lib = os.path.dirname(os.path.dirname(PHOTOS_DB[0]))
    db = sqlite3.connect(snapshot(PHOTOS_DB[0]))
    md = dt.date.today().strftime("%m-%d")
    fav_only = "and coalesce(ZFAVORITE,0)=1" if ENV.get("CC_PHOTOS_FAVORITES", "0") == "1" else ""
    rows = db.execute(f"""select ZUUID, strftime('%Y', ZDATECREATED+978307200,'unixepoch','localtime'), coalesce(ZFAVORITE,0)
        from ZASSET where coalesce(ZTRASHEDSTATE,0)=0 and coalesce(ZHIDDEN,0)=0 and ZKIND=0 {fav_only}
        and strftime('%m-%d', ZDATECREATED+978307200,'unixepoch','localtime')=?
        and strftime('%Y', ZDATECREATED+978307200,'unixepoch','localtime')<strftime('%Y','now','localtime')
        order by ZFAVORITE desc, ZUUID""", (md,)).fetchall()
    if not rows:
        return {"count": 0, "years": [], "thumbs": []}
    years = sorted({int(y) for _, y, _ in rows if y})
    thumbs, tmp = [], tempfile.mkdtemp()
    for uuid, y, fav in rows:
        if len(thumbs) >= 3:
            break
        cands = glob.glob(os.path.join(lib, "resources", "derivatives", uuid[0], uuid + "_1_105_c.jpeg"))
        if not cands:
            continue
        out = os.path.join(tmp, uuid + ".jpg")
        r = subprocess.run(["sips", "-Z", "420", "-s", "format", "jpeg", "-s", "formatOptions", "70", cands[0], "--out", out],
                           capture_output=True, timeout=30)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) < 90000:
            thumbs.append({"year": int(y), "b64": base64.b64encode(open(out, "rb").read()).decode()})
    shutil.rmtree(tmp, ignore_errors=True)
    return {"count": len(rows), "years": years, "thumbs": thumbs}


def _ping(host):
    try:
        r = subprocess.run(["ping", "-c", "3", "-i", "0.3", "-W", "1500", host], capture_output=True, text=True, timeout=12)
        m = re.search(r"= [\d.]+/([\d.]+)/", r.stdout)
        loss = re.search(r"([\d.]+)% packet loss", r.stdout)
        return (float(m.group(1)) if m else None), (float(loss.group(1)) if loss else 100.0)
    except Exception:
        return None, 100.0


def home():
    """Mac and home-network health. Keeps a 24-hour ping log so the page can show uptime."""
    out = {}
    try:
        st = os.statvfs("/")
        free, total = st.f_bavail * st.f_frsize, st.f_blocks * st.f_frsize
        out["disk"] = {"free_gb": round(free / 1e9), "total_gb": round(total / 1e9), "pct_used": round(100 - free / total * 100)}
    except Exception:
        pass
    try:
        boot = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"sec = (\d+)", boot)
        if m:
            out["uptime_days"] = round((dt.datetime.now().timestamp() - int(m.group(1))) / 86400, 1)
    except Exception:
        pass
    try:
        di = subprocess.run(["tmutil", "destinationinfo"], capture_output=True, text=True, timeout=20)
        if "No destinations configured" in (di.stdout + di.stderr):
            out["backup"] = {"last": None, "ok": None, "off": True, "err": "No backup drive set up"}
            raise StopIteration
        r = subprocess.run(["tmutil", "latestbackup"], capture_output=True, text=True, timeout=20)
        m = re.search(r"(\d{4}-\d{2}-\d{2})-(\d{6})", r.stdout)
        if m:
            when = dt.datetime.strptime(m.group(1) + m.group(2), "%Y-%m-%d%H%M%S")
            out["backup"] = {"last": when.isoformat(), "age_h": round((dt.datetime.now() - when).total_seconds() / 3600, 1), "ok": True}
        else:
            msg = (r.stderr or r.stdout).strip()
            out["backup"] = {"last": None, "ok": False, "err": re.sub(r"UserInfo=.*", "", msg)[:120] or "No backup found"}
    except StopIteration:
        pass
    except Exception as e:
        out["backup"] = {"last": None, "ok": False, "err": str(e)[:120]}
    gw = None
    try:
        rt = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"gateway: (\S+)", rt)
        gw = m.group(1) if m else None
    except Exception:
        pass
    inet_ms, inet_loss = _ping("1.1.1.1")
    gw_ms, gw_loss = _ping(gw) if gw else (None, None)
    up = inet_loss < 100
    ts = dt.datetime.now().timestamp()
    hist = []
    try:
        for line in open(NET_LOG):
            try:
                rec = json.loads(line)
                if ts - rec["t"] < 86400:
                    hist.append(rec)
            except Exception:
                continue
    except FileNotFoundError:
        pass
    hist.append({"t": ts, "up": up, "ms": inet_ms})
    try:
        os.makedirs(os.path.dirname(NET_LOG), exist_ok=True)
        open(NET_LOG, "w").write("".join(json.dumps(h) + "\n" for h in hist))
    except Exception:
        pass
    avail = round(100 * sum(1 for h in hist if h["up"]) / len(hist))
    outages = sum(1 for a, b in zip(hist, hist[1:]) if a["up"] and not b["up"])
    # bucket latency to 5 ms so the snapshot does not change (and push) on every run
    out["net"] = {"up": up, "ms": None if inet_ms is None else int(round(inet_ms / 5) * 5), "loss": inet_loss,
                  "gw_ms": None if gw_ms is None else int(round(gw_ms / 5) * 5), "avail_24h": avail, "outages_24h": outages,
                  "checks_24h": len(hist), "worst_ms": int(round(max((h["ms"] or 0) for h in hist) / 5) * 5)}
    return out


def encrypt(payload, passphrase):
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-salt", "-pass", "env:CC_PW"],
                       input=payload, capture_output=True, env={**os.environ, "CC_PW": passphrase})
    if r.returncode != 0:
        raise RuntimeError("openssl failed: " + r.stderr.decode()[:200])
    return r.stdout


def _git(env, args, cwd=None, timeout=90):
    key = os.path.join(HOME, ".config", "command-center", "deploy_key")
    kh = os.path.join(HOME, ".config", "command-center", "known_hosts")
    ssh = (f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "
           f"-o UserKnownHostsFile={kh} -o ConnectTimeout=20")
    r = subprocess.run(["git", "-c", "user.name=command-center-mac", "-c", "user.email=mac@command-center.local"] + args,
                       cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "GIT_SSH_COMMAND": ssh, "GIT_TERMINAL_PROMPT": "0"})
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {r.stderr.strip()[:200]}")
    return r.stdout


def push(env, blob):
    """Commits inbox/mac.enc to the repo over SSH with a deploy key limited to this one repository."""
    repo = env["GH_REPO"]
    url = f"ssh://git@ssh.github.com:443/{repo}.git"
    work = os.path.join(HOME, "CommandCenter", "repo")
    for attempt in (1, 2):
        if not os.path.isdir(os.path.join(work, ".git")):
            shutil.rmtree(work, ignore_errors=True)
            os.makedirs(os.path.dirname(work), exist_ok=True)
            _git(env, ["clone", "--depth", "1", url, work])
        else:
            _git(env, ["fetch", "--depth", "1", "origin", "main"], cwd=work)
            _git(env, ["reset", "--hard", "origin/main"], cwd=work)
        os.makedirs(os.path.join(work, "inbox"), exist_ok=True)
        open(os.path.join(work, "inbox", "mac.enc"), "wb").write(blob)
        _git(env, ["add", "inbox/mac.enc"], cwd=work)
        if not _git(env, ["status", "--porcelain"], cwd=work).strip():
            return
        _git(env, ["commit", "-m", "mac snapshot"], cwd=work)
        try:
            _git(env, ["push", "origin", "HEAD:main"], cwd=work)
            return
        except RuntimeError:
            if attempt == 2:
                raise


def main():
    env = load_env()
    ENV.update(env)
    now = dt.datetime.now().astimezone()
    snap = {"as_of": "Updated " + now.strftime("%-I:%M %p"), "as_of_iso": now.isoformat()}
    for key, fn in (("imessage", imessage), ("reminders", reminders), ("calendar", calendar), ("birthdays", birthdays), ("photos", photos), ("home", home)):
        try:
            snap[key] = fn()
        except Exception as e:
            snap[key] = None
            snap.setdefault("errors", {})[key] = str(e)[:160]
    im = snap.get("imessage") or {}
    flat = {**snap, **{k: v for k, v in im.items()}, "reminders": snap.get("reminders") or []}
    if "--dry-run" in sys.argv:
        ph = dict(flat.get("photos") or {})
        if ph.get("thumbs"):
            ph["thumbs"] = [{"year": t["year"], "bytes": len(t["b64"])} for t in ph["thumbs"]]
        print(json.dumps({**flat, "photos": ph}, indent=2, default=str)[:6000])
        return
    # Push only when something changed, or at least once an hour so the page can tell the Mac is alive.
    import hashlib, time
    core = {k: v for k, v in flat.items() if k not in ("as_of", "as_of_iso")}
    digest = hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()
    mark = os.path.expanduser("~/CommandCenter/.last")
    try:
        old_digest, old_ts = open(mark).read().split(",")
    except Exception:
        old_digest, old_ts = "", "0"
    if digest == old_digest and time.time() - float(old_ts) < 3300 and "--force" not in sys.argv:
        print("unchanged, skipped")
        return
    blob = encrypt(json.dumps(flat, default=str).encode(), env["CC_PASSPHRASE"])
    push(env, blob)
    open(mark, "w").write(f"{digest},{time.time()}")
    print("pushed", len(blob), "bytes")


if __name__ == "__main__":
    main()
