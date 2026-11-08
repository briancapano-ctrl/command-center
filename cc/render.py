"""Encrypts the dashboard model and writes one static page. Data never appears in plain text in the repo."""
import json, os, base64, secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ITER = 200_000
TEMPLATE = os.path.join(os.path.dirname(__file__), "template.html")


def encrypt(obj, passphrase):
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = PBKDF2HMAC(hashes.SHA256(), 32, salt, ITER).derive(passphrase.encode())
    ct = AESGCM(key).encrypt(iv, json.dumps(obj, default=str).encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "iter": ITER, "salt": b(salt), "iv": b(iv), "ct": b(ct)}


MANIFEST = {"name": "Command Center", "short_name": "Command", "start_url": "./#wall", "display": "standalone",
            "background_color": "#05070a", "theme_color": "#05070a",
            "icons": [{"src": "icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}]}
ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" fill="#05070a"/>'
        '<circle cx="256" cy="256" r="150" fill="none" stroke="#4de3c2" stroke-width="22"/>'
        '<circle cx="256" cy="256" r="70" fill="none" stroke="#4de3c2" stroke-width="22" opacity=".55"/>'
        '<circle cx="256" cy="256" r="16" fill="#4de3c2"/></svg>')


def write_site(model, passphrase, out_dir, plain=False):
    os.makedirs(out_dir, exist_ok=True)
    html = open(TEMPLATE, encoding="utf-8").read()
    if plain:  # for hosts that are already private; no lock screen
        html = html.replace("/*__PLAIN__*/null", json.dumps(model, default=str))
    else:
        blob = encrypt(model, passphrase)
        html = html.replace("/*__BLOB__*/null", json.dumps(blob))
        json.dump(blob, open(os.path.join(out_dir, "data.enc.json"), "w"))
    open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(html)
    json.dump(MANIFEST, open(os.path.join(out_dir, "manifest.webmanifest"), "w"))
    open(os.path.join(out_dir, "icon.svg"), "w").write(ICON)
    open(os.path.join(out_dir, ".nojekyll"), "w").write("")


def decrypt(blob, passphrase):
    b = base64.b64decode
    key = PBKDF2HMAC(hashes.SHA256(), 32, b(blob["salt"]), blob["iter"]).derive(passphrase.encode())
    return json.loads(AESGCM(key).decrypt(b(blob["iv"]), b(blob["ct"]), None))
