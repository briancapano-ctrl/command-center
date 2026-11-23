"""Command Center scene buttons: runs an Apple Home scene when the dashboard asks.

Runs on the Mac mini as a launchd agent (com.commandcenter.homectl, installed by mac_collect.py). It listens on a private
ntfy topic that only the encrypted dashboard knows, and acts only on messages that
  - are signed with a key derived from the dashboard passphrase (HMAC-SHA256),
  - are less than 2 minutes old and have not been seen before,
  - name a scene on the allow-list below.
It never runs anything else: the only HomeBot command it can send is trigger-scene for those scenes.
"""
import hashlib, hmac, json, os, subprocess, sys, time

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, ".config", "command-center", "env")
HK_DIR = os.path.join(HOME, "CommandCenter", "home")
BEAT = os.path.join(HK_DIR, "listener.json")
LOG = os.path.join(HK_DIR, "listener_log.txt")
HB_CLI = "/Applications/HomeBot.app/Contents/MacOS/homebot-cli"
HOME_NAME = "Capano Home"
ALLOWED = ("Good Morning", "Good Night")      # scene buttons Brian approved on Nov 22, 2026
MAX_AGE_MS = 120_000


def load_env():
    env = {}
    if os.path.exists(CONF):
        for line in open(CONF):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    return env


def key_for(passphrase):
    return hashlib.sha256(("cc-home-v1:" + passphrase).encode()).digest()


def sign(key, text):
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()


def log(line):
    try:
        old = open(LOG).read().splitlines()[-200:] if os.path.exists(LOG) else []
        open(LOG, "w").write("\n".join(old + [time.strftime("%Y-%m-%d %H:%M:%S ") + line]) + "\n")
    except Exception:
        pass


def beat(state):
    try:
        tmp = BEAT + ".tmp"
        json.dump({"at": time.time(), "state": state}, open(tmp, "w"))
        os.replace(tmp, BEAT)
    except Exception:
        pass


def publish(topic, payload):
    subprocess.run(["/usr/bin/curl", "-s", "-m", "20", "-d", json.dumps(payload), "https://ntfy.sh/" + topic],
                   capture_output=True, timeout=30)


def run_scene(tok, scene, dry):
    args = [HB_CLI, "run-home-action", "--action-type", "trigger-scene", "--item-type", "scene",
            "--home-name", HOME_NAME, "--item-name", scene, "--json"] + (["--dry-run"] if dry else [])
    r = subprocess.run(args, capture_output=True, text=True, timeout=60, env={**os.environ, "HOMEBOT_AUTOMATION_TOKEN": tok})
    out = (r.stdout or r.stderr or "").strip()
    ok = r.returncode == 0
    try:
        data = json.loads(r.stdout)
        if isinstance(data, dict) and data.get("error"):
            ok, out = False, str(data["error"].get("message") if isinstance(data["error"], dict) else data["error"])
        elif isinstance(data, list):
            ok = ok and len(data) == 1
            out = f"{len(data)} scene matched"
    except Exception:
        pass
    return ok, out[:200]


def handle(env, key, raw, seen):
    try:
        m = json.loads(raw)
    except Exception:
        return
    if not isinstance(m, dict) or m.get("v") != 1 or "re" in m:   # replies (ours) and junk are ignored
        return
    scene, ts, n, dry = m.get("scene"), m.get("ts"), str(m.get("n", "")), bool(m.get("dry"))
    text = f"v1|{scene}|{ts}|{n}|{int(dry)}"
    if not hmac.compare_digest(sign(key, text), str(m.get("sig", ""))):
        log("rejected: bad signature")
        return
    if scene not in ALLOWED or not isinstance(ts, (int, float)) or abs(time.time() * 1000 - ts) > MAX_AGE_MS or len(n) < 12 or n in seen:
        log(f"rejected: {scene!r} stale/replayed/not allowed")
        return
    seen[n] = time.time()
    for k in [k for k, t in seen.items() if time.time() - t > 600]:
        del seen[k]
    ok, msg = run_scene(env.get("HOMEBOT_AUTOMATION_TOKEN", ""), scene, dry)
    log(f"{'dry run ' if dry else ''}{scene}: {'ok' if ok else 'failed'} {msg}")
    reply = {"v": 1, "re": n, "ok": ok, "msg": msg if not ok else ("Checked, not run" if dry else "Done")}
    reply["sig"] = sign(key, f"r1|{n}|{int(ok)}")
    publish(env["CC_HOME_TOPIC"], reply)
    if ok and not dry:   # refresh the dashboard soon so lights and locks show the scene's result
        time.sleep(20)
        subprocess.run(["launchctl", "kickstart", f"gui/{os.getuid()}/com.commandcenter.mac"], capture_output=True)


def main():
    env = load_env()
    topic, pw = env.get("CC_HOME_TOPIC", ""), env.get("CC_PASSPHRASE", "")
    if len(topic) < 24 or not pw or not os.path.exists(HB_CLI):
        beat("setup")
        log("not configured; sleeping")
        time.sleep(300)
        return
    key, seen, since = key_for(pw), {}, None
    while True:
        url = f"https://ntfy.sh/{topic}/json" + (f"?since={since}" if since else "")
        p = subprocess.Popen(["/usr/bin/curl", "-sN", "--max-time", "3600", url], stdout=subprocess.PIPE, text=True)
        beat("listening")
        try:
            for line in p.stdout:
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                beat("listening")
                if ev.get("event") == "message":
                    since = ev.get("id") or since
                    handle(env, key, ev.get("message", ""), seen)
        finally:
            try:
                p.kill()
            except Exception:
                pass
        beat("reconnecting")
        time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("crashed: " + repr(e)[:200])
        time.sleep(30)
        sys.exit(1)
