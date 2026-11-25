"""Stateless signed dashboard tokens (HMAC-SHA256, compact JSON, base64url).

Format: ``<b64url(payload json)>.<b64url(hmac)>`` with payload {sub, iat, exp}.
Secret: DASHBOARD_TOKEN_SECRET if set, else derived from existing server
secrets (LOGIN_PASS, CRON_SECRET, MONGO_URI). With no secret available we
fail closed: no tokens are issued and none verify.
Tokens cannot be revoked before expiry; rotating the secret invalidates all.
"""

import base64
import hashlib
import hmac
import json
import os
import time

TOKEN_TTL_SECONDS = 12 * 60 * 60
_LABEL = b"sanjeet-dashboard-token-v1"


class TokenError(Exception):
    pass


def _secret() -> bytes | None:
    explicit = os.environ.get("DASHBOARD_TOKEN_SECRET")
    if explicit:
        return explicit.encode("utf-8")
    parts = [
        os.environ.get(k) or ""
        for k in ("LOGIN_PASS", "CRON_SECRET", "MONGO_URI")
    ]
    if not any(parts):
        return None
    h = hashlib.sha256(_LABEL)
    for p in parts:
        h.update(b"\x00" + p.encode("utf-8"))
    return h.digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: bytes, body: str) -> str:
    return _b64(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())


def issue_token(sub: str, now: float | None = None) -> tuple[str, int]:
    """Return (token, expires_at_epoch_seconds). Raises TokenError if no secret."""
    secret = _secret()
    if secret is None:
        raise TokenError("token secret not configured")
    iat = int(now if now is not None else time.time())
    exp = iat + TOKEN_TTL_SECONDS
    payload = json.dumps(
        {"sub": sub, "iat": iat, "exp": exp}, separators=(",", ":")
    ).encode("utf-8")
    body = _b64(payload)
    return f"{body}.{_sign(secret, body)}", exp


def verify_token(token: str | None, now: float | None = None) -> dict:
    """Return the payload or raise TokenError (empty/garbage/tampered/expired)."""
    if not token or not isinstance(token, str):
        raise TokenError("missing token")
    secret = _secret()
    if secret is None:
        raise TokenError("token secret not configured")
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(_sign(secret, body), sig):
            raise TokenError("bad signature")
        payload = json.loads(_unb64(body))
        exp = int(payload["exp"])
        payload["sub"]
    except TokenError:
        raise
    except Exception as exc:
        raise TokenError("malformed token") from exc
    if (now if now is not None else time.time()) >= exp:
        raise TokenError("token expired")
    return payload
