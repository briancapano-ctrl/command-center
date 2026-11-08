#!/usr/bin/env python3
"""Runs on the Mac mini. Reads texts and reminders locally, encrypts the result, pushes it to your GitHub repo.
Python 3.9 standard library plus the macOS `openssl` and `sqlite` already installed. Nothing leaves the Mac unencrypted."""
import base64, datetime as dt, glob, json, os, re, shutil, sqlite3, subprocess, sys, tempfile

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, ".config", "command-center", "env")
APPLE_EPOCH = 978307200
DAYS = 30  # only count unread texts newer than this, so ancient unread spam does not inflate the number
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
                waiting.append({"label": label, "ago": f"{int(hrs)}h" if hrs < 48 else f"{int(hrs // 24)}d"})
    return {"unread_total": total, "unread_chats": len(chats),
            "top_unread": [{"label": c["label"], "unread": c["unread"]} for c in chats[:6]], "waiting": waiting[:6]}


def reminders():
    out, seen = [], set()
    for p in glob.glob(os.path.join(HOME, "Library/Group Containers/group.com.apple.reminders/Container_v1/Stores/*.sqlite")):
        try:
            db = sqlite3.connect(snapshot(p))
            for title, due, tz in db.execute("""select ZTITLE, ZDUEDATE, ZTIMEZONE from ZREMCDREMINDER
                where coalesce(ZCOMPLETED,0)=0 and coalesce(ZMARKEDFORDELETION,0)=0 and ZDUEDATE is not null"""):
                if tz:  # fixed instant
                    d = dt.datetime.fromtimestamp(due + APPLE_EPOCH).astimezone()
                else:   # floating: the stored clock time is the local clock time
                    d = dt.datetime.utcfromtimestamp(due + APPLE_EPOCH).replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
                key = (title, d.strftime("%Y-%m-%d %H:%M"))
                if key in seen:
                    continue
                seen.add(key)
                out.append({"title": title, "due": d.isoformat()})
        except Exception:
            continue
    out.sort(key=lambda r: r["due"])
    return out[:40]


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
    now = dt.datetime.now().astimezone()
    snap = {"as_of": "Updated " + now.strftime("%-I:%M %p"), "as_of_iso": now.isoformat()}
    for key, fn in (("imessage", imessage), ("reminders", reminders)):
        try:
            snap[key] = fn()
        except Exception as e:
            snap[key] = None
            snap.setdefault("errors", {})[key] = str(e)[:160]
    im = snap.get("imessage") or {}
    flat = {**snap, **{k: v for k, v in im.items()}, "reminders": snap.get("reminders") or []}
    if "--dry-run" in sys.argv:
        print(json.dumps(flat, indent=2, default=str)[:4000])
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
