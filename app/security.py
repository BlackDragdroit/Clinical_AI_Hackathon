"""HMAC signing for session cookies and mock eID assertions (stdlib only). Owner: SWE 2."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.config import settings


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict, purpose: str, ttl_s: int) -> str:
    body = dict(payload, _p=purpose, _exp=int(time.time()) + ttl_s)
    raw = _b64(json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode())
    mac = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).digest()
    return f"{raw}.{_b64(mac)}"


def unsign(token: str, purpose: str) -> dict | None:
    """Returns the payload, or None if the signature, purpose or expiry is wrong."""
    try:
        raw, mac = token.split(".", 1)
        good = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(good, _unb64(mac)):
            return None
        body = json.loads(_unb64(raw))
    except (ValueError, json.JSONDecodeError):
        return None
    if body.get("_p") != purpose or body.get("_exp", 0) < time.time():
        return None
    return {k: v for k, v in body.items() if not k.startswith("_")}
