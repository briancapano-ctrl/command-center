#!/usr/bin/env python3
"""Runs on the Mac mini. Reads texts, reminders, Apple Calendar, birthdays, photo memories, home health and Apple Home accessory status locally, encrypts the result, pushes it to your GitHub repo.
Python 3.9 standard library plus the macOS `openssl` and `sqlite` already installed. Nothing leaves the Mac unencrypted."""
import atexit, urllib.parse, base64, datetime as dt, glob, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, time

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, ".config", "command-center", "env")
APPLE_EPOCH = 978307200
DAYS = 30  # only count unread texts newer than this, so ancient unread spam does not inflate the number
ENV = {}
MAX_COPY_MB = 300  # largest live database the collector will ever copy


def skip_lists():
    return {x.strip().lower() for x in ENV.get("CC_SKIP_LISTS", "To do,Tasks").split(",") if x.strip()}


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


_TMPS = []
atexit.register(lambda: [shutil.rmtree(t, ignore_errors=True) for t in _TMPS])


def snapshot(path):
    """Copy a live SQLite DB (and WAL) so we never lock Messages or Reminders. The copy is removed when the run ends."""
    if os.path.getsize(path) > MAX_COPY_MB * 1048576:   # never write a multi-GB copy every 10 minutes (it wears the SSD and stalls the Mac)
        raise RuntimeError("refusing to copy a large live database: " + os.path.basename(path))
    tmp = tempfile.mkdtemp()
    _TMPS.append(tmp)
    dst = os.path.join(tmp, "db.sqlite")
    shutil.copy(path, dst)
    for ext in ("-wal", "-shm"):
        if os.path.exists(path + ext):
            shutil.copy(path + ext, dst + ext)
    return dst


def connect_ro(path, immutable_ok=False):
    """Open a big live SQLite DB (Messages about 1.7 GB, Photos about 1.7 GB) read-only in place instead of copying it every run.
    WAL databases allow readers next to the writer. immutable_ok adds a lock-free read for data that rarely changes (Photos).
    The old copy is the last resort and is refused for anything large."""
    uri = "file:" + urllib.parse.quote(path)
    for q in ("?mode=ro",) + (("?immutable=1",) if immutable_ok else ()):
        try:
            db = sqlite3.connect(uri + q, uri=True, timeout=5)
            db.execute("select 1 from sqlite_master limit 1").fetchone()
            return db
        except Exception:
            pass
    return sqlite3.connect(snapshot(path))


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
    db = connect_ro(os.path.join(HOME, "Library/Messages/chat.db"))
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
    try:
        ppl = people(db, names)
    except Exception as e:
        ppl = {"err": str(e)[:120]}
    return {"unread_total": total, "unread_chats": len(chats),
            "top_unread": [{"label": c["label"], "unread": c["unread"]} for c in chats[:6]], "waiting": waiting[:6], "people": ppl}


def people(db, names):
    """Your regulars: who you texted most this week, and people you text often but have not in three weeks or more.
    Names and counts only. No message text, numbers or addresses leave the Mac. Unknown numbers and businesses are skipped."""
    now_s = dt.datetime.now().timestamp()
    ns = lambda days: (now_s - days * 86400 - APPLE_EPOCH) * 1e9
    rows = db.execute("""select h.id, count(*), max(m.date), sum(case when m.date>? then 1 else 0 end)
        from message m join handle h on h.ROWID=m.handle_id
        where m.date>? and m.item_type=0 and coalesce(m.associated_message_type,0)=0
        group by h.id""", (ns(7), ns(365))).fetchall()
    who = {}
    for ident, n, last, wk in rows:
        name = names.get(last10(ident)) or names.get((ident or "").lower())
        if not name:
            continue
        p = who.setdefault(name, {"n": 0, "last": 0, "wk": 0})
        p["n"] += n; p["wk"] += wk or 0; p["last"] = max(p["last"], last or 0)
    groups = db.execute("""select coalesce(c.display_name,''), count(*) from chat c join chat_message_join j on j.chat_id=c.ROWID
        join message m on m.ROWID=j.message_id where m.date>? and m.item_type=0 and coalesce(m.associated_message_type,0)=0
        and coalesce(c.display_name,'')<>'' group by c.ROWID""", (ns(7),)).fetchall()
    week = [{"name": k, "n": v["wk"]} for k, v in who.items() if v["wk"] >= 5] + [{"name": g.strip(), "n": c, "group": True} for g, c in groups if c >= 5]
    week.sort(key=lambda x: -x["n"])
    days = lambda last: int((now_s - (last / 1e9 + APPLE_EPOCH)) // 86400)
    rec = [{"name": k, "days": days(v["last"]), "n": v["n"]} for k, v in who.items() if v["n"] >= 40 and days(v["last"]) >= 21]
    rec.sort(key=lambda x: -x["n"])
    return {"week": week[:6], "reconnect": rec[:6]}


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
                        d = dt.datetime.fromtimestamp(due + APPLE_EPOCH, dt.timezone.utc).replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
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
    skip_stores = {x.strip().lower() for x in ENV.get("CC_SKIP_STORES", "Exchange").split(",") if x.strip()}  # the work (Exchange) account stays out of the personal feed
    ok = lambda cal, store: cal.lower() not in SKIP_CALS and store.lower() not in ("other", "reminders", "subscribed calendars") and store.lower() not in skip_stores
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
    """'On this day' memories, computed once per day (the answer cannot change within a day) and cached."""
    if not PHOTOS_DB:
        return None
    today = dt.date.today().isoformat()
    cache = os.path.join(HOME, ".config", "command-center", "photos_cache.json")
    c = None
    try:
        c = json.load(open(cache))
        if c.get("day") == today:
            return c["data"]
    except Exception:
        c = None
    try:
        data = _photos_scan()
    except Exception:
        if c and c.get("data"):
            return c["data"]   # yesterday's answer beats an error
        raise
    try:
        json.dump({"day": today, "data": data}, open(cache, "w"))
    except Exception:
        pass
    return data


def _photos_scan():
    """'On this day' memories from the Photos library: a count, the years, and up to three small thumbnails."""
    lib = os.path.dirname(os.path.dirname(PHOTOS_DB[0]))
    db = connect_ro(PHOTOS_DB[0], True)
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
    _TMPS.append(tmp)
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


HK_DIR = os.path.join(HOME, "CommandCenter", "home")
HK_RAW = os.path.join(HK_DIR, "homebot.json")                 # last raw reading, kept on this Mac only
HB_CLI = "/Applications/HomeBot.app/Contents/MacOS/homebot-cli"
HK_TYPES = ("lightbulb", "switch", "outlet", "fan", "thermostat", "heater-cooler", "window-covering", "window", "door",
            "garage-door-opener", "lock-mechanism", "temperature-sensor", "humidity-sensor", "air-quality-sensor",
            "contact-sensor", "motion-sensor", "occupancy-sensor", "leak-sensor", "smoke-sensor", "carbon-monoxide-sensor",
            "light-sensor", "battery", "stateful-programmable-switch", "air-purifier", "valve")


def _hk_cli(args, tok, timeout=120):
    return subprocess.run([HB_CLI] + args, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, "HOMEBOT_AUTOMATION_TOKEN": tok})


def _hk_read(tok, args, log):
    """One get-home-items call. Returns the item list, or None when HomeBot could not export it."""
    for attempt in range(3):   # HomeBot is sometimes killed mid-read (exit -9); a retry usually succeeds
        try:
            r = _hk_cli(["get-home-items", "--json"] + args, tok)
            code, o, err = r.returncode, r.stdout, (r.stderr or "").strip()
        except subprocess.TimeoutExpired:
            code, o, err = -1, "", "timed out"
        if code != -9:
            break
        time.sleep(1.5)
    try:
        data = json.loads(o)
        if isinstance(data, list):
            log.append(f"{' '.join(args)}: ok {len(data)}")
            return data
    except Exception:
        pass
    log.append(f"{' '.join(args)}: exit {code} " + re.sub(r"\s+", " ", (o or err))[:160])
    return None


def _hk_parse_text(out, service):
    """Parse HomeBot's readable listing ("[*] item" headers, "[ ] Key: Value" lines) into the JSON field names."""
    items, cur = [], None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("[*]") and "Home Items:" not in line:
            cur = {"item_service_type": service}
            items.append(cur)
            continue
        m = re.match(r"\[ \] ([^:]+): (.*)$", line)
        if not (m and cur is not None):
            continue
        k, v = m.group(1).strip().lower().replace(" ", "_"), m.group(2).strip()
        if k in ("item_service_type", "item_property_types", "item_action_types"):
            continue
        if v in ("true", "false"):
            val = v == "true"
        else:
            n = re.match(r"^(-?\d+(?:\.\d+)?)\s*(%|°C|K|lx)?$", v)
            val = float(n.group(1)) if n else v
            if isinstance(val, float) and val.is_integer():
                val = int(val)
        cur[k] = val.lower() if k == "item_type" and isinstance(val, str) else val
    return items


def _f(c):
    return None if c is None else round(c * 9 / 5 + 32, 1)


def _hk_slim(items, skipped):
    """Trim the raw HomeBot reading to what the page shows. No identifiers leave the Mac."""
    dev = [x for x in items if x.get("item_type") == "device"]
    def of(t):
        return [x for x in dev if x.get("item_service_type") == t]
    def base(x):
        d = {"n": x.get("item_name"), "r": x.get("room_name")}
        if x.get("item_is_reachable") is False:
            d["off"] = True   # not responding
        return d
    climate_names = {"2nd Floor Hallway": "Upstairs"}
    out = {
        "state": "ok",
        "home": next((x.get("home_name") for x in items if x.get("home_name")), "Home"),
        "lights": [{**base(x), "on": bool(x.get("item_is_active")), "b": x.get("light_brightness")} for x in of("lightbulb")],
        "climate": [{**base(x), "n": climate_names.get(x.get("room_name"), x.get("room_name") or x.get("item_name")),
                     "t": _f(x.get("temperature_sensor_measurement")), "set": _f(x.get("target_temperature")),
                     "heat": _f(x.get("heating_threshold_temperature")), "cool": _f(x.get("cooling_threshold_temperature")),
                     "mode": x.get("thermostat_mode") or x.get("heater_cooler_mode"), "hum": x.get("relative_humidity_sensor_measurement"),
                     "fan": x.get("fan_state")} for x in of("thermostat") + of("heater-cooler")],
        "shades": [{**base(x), "pos": x.get("current_position"), "to": x.get("target_position")} for x in of("window-covering") + of("window")],
        # HomeBot exposes no lock-state field, so an active lock is read as secured (HomeKit lock state 1); a contact sensor
        # that is detecting means open (HomeKit contact state 1).
        "locks": [{**base(x), "locked": bool(x.get("item_is_active"))} for x in of("lock-mechanism")],
        "doors": [{**base(x), "open": bool(x.get("detection_sensor_measurement"))} for x in of("contact-sensor")],
        "garage": [{**base(x), "open": x.get("current_door_state") not in (None, "closed"), "st": x.get("current_door_state")} for x in of("garage-door-opener")],
        "motion": [{**base(x), "on": bool(x.get("detection_sensor_measurement"))} for x in of("motion-sensor") + of("occupancy-sensor")],
        "temps": [{**base(x), "t": _f(x.get("temperature_sensor_measurement"))} for x in of("temperature-sensor")],
        "safety": [{**base(x), "alarm": bool(x.get("detection_sensor_measurement")), "kind": x.get("item_service_type")}
                   for x in of("smoke-sensor") + of("carbon-monoxide-sensor") + of("leak-sensor")],
        "battery": sorted([{**base(x), "lvl": x.get("battery_level")} for x in of("battery") if x.get("battery_level") is not None],
                          key=lambda b: b["lvl"]),
        "scenes": [{"n": x.get("item_name"), "on": bool(x.get("item_is_active"))} for x in items if x.get("item_type") == "scene"],
        "rooms": sorted(x.get("item_name") for x in items if x.get("item_type") == "room" and x.get("item_name") != "Default Room"),
        "skipped": len(skipped),
    }
    for k in [k for k, v in out.items() if v == []]:
        del out[k]
    return out


def homekit():
    """Apple Home status through the HomeBot for HomeKit command-line reader. Read-only: this only ever calls get-home-items,
    never run-home-action. The raw reading stays on this Mac; the page gets a trimmed copy inside the encrypted snapshot."""
    os.makedirs(HK_DIR, exist_ok=True)
    for old in ("home_shortcut.plist", "Command Center Home.shortcut", "last.txt"):   # retired Shortcuts attempt
        try:
            os.remove(os.path.join(HK_DIR, old))
        except FileNotFoundError:
            pass
    try:
        os.chmod(CONF, 0o600)
    except Exception:
        pass
    tok = ENV.get("HOMEBOT_AUTOMATION_TOKEN", "").strip()
    if not os.path.exists(HB_CLI):
        return {"state": "setup", "err": "HomeBot is not installed"}
    if not tok:
        return {"state": "setup", "err": "HomeBot token is missing"}
    helpf = os.path.join(HK_DIR, "help.txt")
    if not os.path.exists(helpf):
        try:
            h = _hk_cli(["get-home-items", "--help"], tok, 30)
            open(helpf, "w").write(h.stdout + h.stderr)
        except Exception as e:
            open(helpf, "w").write("help failed: " + str(e))
    probe = os.path.join(HK_DIR, "probe.txt")   # one-time reference notes kept on this Mac (help text, lock wording)
    if not os.path.exists(probe):
        out = []
        for a in (["run-home-action", "--help"], ["get-home-items", "--item-service-type", "lock-mechanism"],
                  ["get-home-items", "--item-service-type", "contact-sensor"]):
            try:
                r = _hk_cli(a, tok, 60)
                out.append("$ " + " ".join(a) + "\n" + r.stdout + r.stderr)
            except Exception as e:
                out.append("$ " + " ".join(a) + " failed: " + str(e))
        open(probe, "w").write("\n\n".join(out))
    t0 = dt.datetime.now().timestamp()
    log, skipped = [], []
    items = _hk_read(tok, ["--verbose"], log)
    if items is None:
        # One device can make HomeBot's whole JSON export fail, so read each service type on its own, then each room for a
        # type that still fails. Anything that still fails is skipped (and logged on this Mac) instead of blanking the panel.
        items = []
        rooms = _hk_read(tok, ["--verbose", "--item-type", "room"], log) or _hk_read(tok, ["--item-type", "room"], log) or []
        items += rooms + (_hk_read(tok, ["--verbose", "--item-type", "scene"], log) or [])
        for t in HK_TYPES:
            got = _hk_read(tok, ["--verbose", "--item-service-type", t], log)
            if got is None:
                got = _hk_read(tok, ["--item-service-type", t], log)
            if got is None:
                got = []
                for rm in sorted({x.get("item_name") for x in rooms if x.get("item_name")}):
                    part = _hk_read(tok, ["--verbose", "--item-service-type", t, "--room-name", rm], log)
                    if part is None:
                        part = _hk_read(tok, ["--item-service-type", t, "--room-name", rm], log)
                    if part is not None:
                        got += part
                        continue
                    try:   # the plain-text listing still works when one value breaks the JSON export
                        txt = _hk_cli(["get-home-items", "--item-service-type", t, "--room-name", rm], tok, 60)
                        part = _hk_parse_text(txt.stdout + "\n" + txt.stderr, t)
                        log.append(f"  text exit {txt.returncode}, out {len(txt.stdout)}, err {len(txt.stderr)}: " + re.sub(r"\s+", " ", txt.stdout + txt.stderr)[:300])
                    except Exception as e:
                        part = []
                        log.append("  text failed: " + str(e))
                    log.append(f"  text {t} in {rm}: {len(part)}")
                    if part:
                        got += part
                    else:
                        skipped.append(f"{t} in {rm}")
            items += got
    secs = round(dt.datetime.now().timestamp() - t0, 1)
    with open(HK_RAW + ".tmp", "w") as fh:
        json.dump(items, fh)
    os.chmod(HK_RAW + ".tmp", 0o600)
    os.replace(HK_RAW + ".tmp", HK_RAW)
    with open(os.path.join(HK_DIR, "last_err.txt"), "w") as fh:
        fh.write(f"{secs}s, {len(items)} items, skipped: {skipped}\n" + "\n".join(log))
    if not items:
        return {"state": "error", "err": "HomeBot returned no items"}
    return {**_hk_slim(items, skipped), "secs": secs}


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


WORK_LOCAL = os.path.join(HOME, "CommandCenter", "work_local.json")
EXT_ID = "plhacmcjdmghcfilnjknledephfgilce"
HOST_NAME = "com.commandcenter.work"
HOST_PY = os.path.join(HOME, "CommandCenter", "work_host.py")
HOST_SRC = "#!" + os.path.realpath(sys.executable) + "\n" + """\
# Chrome native-messaging host for the Command Center Work Lane add-on.
# Hands the add-on the work meetings the Mac collector saved locally. Read-only; no network; nothing else.
import json, os, struct, sys
raw = sys.stdin.buffer.read(4)
if len(raw) == 4:
    sys.stdin.buffer.read(struct.unpack("<I", raw)[0])
try:
    data = open(os.path.expanduser("~/CommandCenter/work_local.json"), "rb").read()
    json.loads(data)
except Exception:
    data = b'{"error": "no work data yet"}'
if len(data) > 900000:
    data = b'{"error": "work data too large"}'
sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
sys.stdout.buffer.flush()
"""


def install_native_host():
    """Keeps the add-on's local bridge installed (idempotent). The add-on reads work meetings from here, so no Outlook calendar tab is needed."""
    if not os.path.exists(HOST_PY) or open(HOST_PY).read() != HOST_SRC:
        open(HOST_PY, "w").write(HOST_SRC)
    os.chmod(HOST_PY, 0o755)
    d = os.path.join(HOME, "Library", "Application Support", "Google", "Chrome", "NativeMessagingHosts")
    os.makedirs(d, exist_ok=True)
    man = json.dumps({"name": HOST_NAME, "description": "Command Center work meetings (local only)", "path": HOST_PY,
                      "type": "stdio", "allowed_origins": ["chrome-extension://%s/" % EXT_ID]}, indent=1)
    f = os.path.join(d, HOST_NAME + ".json")
    if not os.path.exists(f) or open(f).read() != man:
        open(f, "w").write(man)


def work_local():
    """Work (Exchange) meetings from Apple Calendar for today and the next 7 days. Written to a file on this Mac only (never pushed);
    the Chrome add-on picks it up through the local bridge above."""
    rows = _cal_rows(8, lambda cal, store: "exchange" in store.lower())
    start_today = dt.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    utc = lambda d: d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    out, seen = [], set()
    for st, en, title, all_day, cal, store, loc in rows:
        s = dt.datetime.fromtimestamp(st + APPLE_EPOCH).astimezone()
        e = dt.datetime.fromtimestamp((en or st) + APPLE_EPOCH).astimezone()
        if all_day and e <= s:
            e = s + dt.timedelta(days=1)
        if e <= start_today:
            continue
        key = (utc(s), title)
        if key in seen:
            continue
        seen.add(key)
        out.append({"s": utc(s), "e": utc(e), "title": (title or "")[:200], "location": (loc or "")[:120], "private": False, "allDay": bool(all_day)})
    out.sort(key=lambda x: x["s"])
    data = {"ts": int(dt.datetime.now().timestamp() * 1000), "account": "bcapano@allbridge.com", "range": "Today and the next 7 days", "events": out[:120]}
    tmp = WORK_LOCAL + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.chmod(tmp, 0o600)
    os.replace(tmp, WORK_LOCAL)
    return len(out)


def main():
    env = load_env()
    ENV.update(env)
    for fn in (install_native_host, work_local):   # work meetings stay on this Mac; failures never block the personal feed
        try:
            fn()
        except Exception as e:
            print("work lane:", fn.__name__, type(e).__name__, str(e)[:120])
    now = dt.datetime.now().astimezone()
    snap = {"as_of": "Updated " + now.strftime("%-I:%M %p"), "as_of_iso": now.isoformat()}
    for key, fn in (("imessage", imessage), ("reminders", reminders), ("calendar", calendar), ("birthdays", birthdays), ("photos", photos), ("home", home), ("homekit", homekit)):
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
    if isinstance(core.get("homekit"), dict):   # motion flips constantly and timing varies; neither alone forces a push
        core["homekit"] = {k: v for k, v in core["homekit"].items() if k not in ("motion", "secs")}
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
