"""Web Push notification helper for critical alerts.

Manages VAPID keys and push subscription storage,
and sends push notifications via the Web Push API.
"""

import json, base64
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
VAPID_KEYS_PATH = BASE_DIR / "data" / "vapid_keys.json"
SUBS_PATH = BASE_DIR / "data" / "push_subs.json"

_vapid_private_key = None
_vapid_public_key_b64 = None
_vapid_claims = None
_push_subs = []


def init_vapid():
    global _vapid_private_key, _vapid_public_key_b64, _vapid_claims, _push_subs
    from py_vapid import Vapid
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    import base64
    if VAPID_KEYS_PATH.exists():
        with open(VAPID_KEYS_PATH, "rb") as f:
            pem = f.read()
        v = Vapid.from_pem(pem)
    else:
        v = Vapid()
        v.generate_keys()
        VAPID_KEYS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(VAPID_KEYS_PATH, "wb") as f:
            f.write(v.private_pem())
    _vapid_private_key = v.private_pem().decode()
    pub_bytes = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    _vapid_public_key_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()
    _vapid_claims = {"sub": "mailto:admin@condominium-expert.local"}
    if SUBS_PATH.exists():
        with open(SUBS_PATH) as f:
            _push_subs = json.load(f)
    else:
        _push_subs = []


def _save_subs():
    SUBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SUBS_PATH, "w") as f:
        json.dump(_push_subs, f, indent=2)


def add_subscription(sub: dict):
    global _push_subs
    endpoint = sub.get("endpoint")
    _push_subs = [s for s in _push_subs if s.get("endpoint") != endpoint]
    _push_subs.append(sub)
    _save_subs()


def remove_subscription(endpoint: str):
    global _push_subs
    _push_subs = [s for s in _push_subs if s.get("endpoint") != endpoint]
    _save_subs()


def get_public_key() -> str:
    return _vapid_public_key_b64


def send_push(title: str, body: str, tag: str = "default", url: str = "/"):
    """Send a push notification to all stored subscriptions."""
    if not _push_subs:
        return
    from pywebpush import webpush, WebPushException
    payload = json.dumps({"title": title, "body": body, "tag": tag, "url": url})
    dead = []
    for sub in _push_subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=_vapid_private_key,
                vapid_claims=_vapid_claims,
            )
        except WebPushException as e:
            if e.response and e.response.status_code in (410, 404):
                dead.append(sub)
        except Exception:
            dead.append(sub)
    for d in dead:
        if d in _push_subs:
            _push_subs.remove(d)
    if dead:
        _save_subs()
