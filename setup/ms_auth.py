#!/usr/bin/env python3
"""Run once. Prints a code, you enter it at microsoft.com/devicelogin while signed in as your Hotmail, and it prints the refresh token.
Usage: python3 ms_auth.py APPLICATION_CLIENT_ID"""
import json, sys, time, urllib.parse, urllib.request

BASE = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
SCOPE = "offline_access Mail.ReadWrite Calendars.Read"


def post(url, form):
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request(url, data=urllib.parse.urlencode(form).encode())))
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    cid = sys.argv[1]
    d = post(BASE + "/devicecode", {"client_id": cid, "scope": SCOPE})
    if "user_code" not in d:
        sys.exit(f"Microsoft rejected the request: {d}")
    print(f"\nGo to {d['verification_uri']} and enter the code: {d['user_code']}\nSign in as bcapano@hotmail.com and approve.\n")
    end = time.time() + d["expires_in"]
    while time.time() < end:
        time.sleep(d.get("interval", 5))
        t = post(BASE + "/token", {"client_id": cid, "grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": d["device_code"]})
        if "refresh_token" in t:
            print("Save this as the GitHub secret MS_REFRESH_TOKEN:\n")
            print(t["refresh_token"])
            return
        if t.get("error") not in ("authorization_pending", "slow_down"):
            sys.exit(f"Failed: {t}")
    sys.exit("Timed out.")


if __name__ == "__main__":
    main()
