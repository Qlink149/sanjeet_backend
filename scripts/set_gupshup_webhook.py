"""Point the Sanjeet Gupshup app webhook at this bot's inbound route."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

PARTNER_BASE_URL = "https://partner.gupshup.io"
DEFAULT_WEBHOOK_URL = "https://sanjeet-bot.vercel.app/gupshup/sanjeet/message"
DEFAULT_TAG = "sanjeet-bot"
DEFAULT_MODES = (
    "MESSAGE,FLOWS_MESSAGE,SENT,DELIVERED,READ,DELETED,FAILED,"
    "OTHERS,ENQUEUED,TEMPLATE,ACCOUNT,BILLING,PAYMENTS"
)


def require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip().strip('"')
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def partner_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    form: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Call the Partner API via curl.exe (Python TLS to partner.gupshup.io stalls on Windows)."""
    with tempfile.NamedTemporaryFile(delete=False) as body_file:
        body_path = body_file.name
    cmd = [
        "curl.exe",
        "-sS",
        "-X",
        method,
        "--max-time",
        "30",
        "-o",
        body_path,
        "-w",
        "%{http_code}",
    ]
    for key, value in (headers or {}).items():
        cmd.extend(["-H", f"{key}: {value}"])
    if form is not None:
        cmd.extend(["-H", "Content-Type: application/x-www-form-urlencoded"])
        cmd.extend(["--data", urlencode(form)])
    cmd.append(url)
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SystemExit("curl.exe is required to call the Gupshup Partner API.") from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"Timed out calling {method} {url}") from exc

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()[:500]
        raise SystemExit(f"curl failed for {method} {url}: {err or completed.returncode}")

    try:
        status_code = int((completed.stdout or "0").strip() or "0")
    except ValueError as exc:
        raise SystemExit(f"Could not parse HTTP status from curl: {completed.stdout!r}") from exc

    raw = Path(body_path).read_text(encoding="utf-8", errors="replace")
    Path(body_path).unlink(missing_ok=True)
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Unexpected non-JSON response from {method} {url}: HTTP {status_code} {raw[:500]}"
        ) from exc
    if not isinstance(data, dict):
        data = {"data": data}
    return status_code, data


def ensure_ok(status_code: int, data: dict[str, Any], context: str) -> dict[str, Any]:
    if status_code >= 400:
        message = data.get("message") or data.get("status") or str(data)[:500]
        raise SystemExit(f"{context} failed: HTTP {status_code} - {message}")
    return data


def get_partner_token() -> str:
    explicit_token = (os.environ.get("GUPSHUP_PARTNER_TOKEN") or "").strip()
    if explicit_token:
        return explicit_token

    email = (os.environ.get("GUPSHUP_PARTNER_EMAIL") or "").strip()
    password = (
        os.environ.get("GUPSHUP_PARTNER_CLIENT_SECRET")
        or os.environ.get("GUPSHUP_PARTNER_PASSWORD")
        or ""
    ).strip()
    if not email or not password:
        raise SystemExit(
            "Missing partner authentication. Set GUPSHUP_PARTNER_TOKEN, or both "
            "GUPSHUP_PARTNER_EMAIL and GUPSHUP_PARTNER_CLIENT_SECRET "
            "(or GUPSHUP_PARTNER_PASSWORD for older partner accounts)."
        )

    status_code, data = partner_request(
        "POST",
        f"{PARTNER_BASE_URL}/partner/account/login",
        form={"email": email, "password": password},
    )
    ensure_ok(status_code, data, "Partner login")
    token = (data.get("token") or "").strip()
    if not token:
        raise SystemExit("Partner login succeeded but no partner token was returned.")
    return token


def get_app_token(app_id: str) -> str:
    explicit_app_token = (os.environ.get("GUPSHUP_PARTNER_APP_TOKEN") or "").strip()
    if explicit_app_token:
        return explicit_app_token

    legacy_app_token = (os.environ.get("GUPSHUP_TOKEN") or "").strip().strip('"')
    if legacy_app_token:
        return legacy_app_token

    partner_token = get_partner_token()
    status_code, data = partner_request(
        "GET",
        f"{PARTNER_BASE_URL}/partner/app/{app_id}/token",
        headers={"token": partner_token},
    )
    ensure_ok(status_code, data, "Fetch app token")
    token_data = data.get("token") or {}
    app_token = token_data.get("token") if isinstance(token_data, dict) else str(token_data)
    app_token = (app_token or "").strip()
    if not app_token:
        raise SystemExit("App token request succeeded but no PARTNER_APP_TOKEN was returned.")
    return app_token


def get_existing_subscriptions(app_id: str, app_token: str) -> list[dict[str, Any]]:
    status_code, data = partner_request(
        "GET",
        f"{PARTNER_BASE_URL}/partner/app/{app_id}/subscription",
        headers={"Authorization": app_token},
    )
    ensure_ok(status_code, data, "Fetch subscriptions")
    subscriptions = data.get("subscriptions") or []
    if not isinstance(subscriptions, list):
        raise SystemExit("Unexpected subscriptions payload returned by Gupshup.")
    return subscriptions


def upsert_subscription(app_id: str, app_token: str, webhook_url: str) -> dict[str, Any]:
    tag = (os.environ.get("GUPSHUP_WEBHOOK_TAG") or DEFAULT_TAG).strip()
    version = (os.environ.get("GUPSHUP_WEBHOOK_VERSION") or "3").strip()
    modes = (os.environ.get("GUPSHUP_WEBHOOK_MODES") or DEFAULT_MODES).strip()
    show_on_ui = (os.environ.get("GUPSHUP_WEBHOOK_SHOW_ON_UI") or "true").strip().lower()

    payload = {
        "url": webhook_url,
        "tag": tag,
        "version": version,
        "modes": modes,
        "showOnUI": "true" if show_on_ui in {"1", "true", "yes"} else "false",
        "active": "true",
        "doCheck": "false",
    }

    subscriptions = get_existing_subscriptions(app_id, app_token)
    existing = next(
        (
            subscription
            for subscription in subscriptions
            if subscription.get("tag") == tag or subscription.get("url") == webhook_url
        ),
        None,
    )
    headers = {"Authorization": app_token}

    if existing:
        subscription_id = str(existing.get("id") or "").strip()
        if not subscription_id:
            raise SystemExit("Found matching subscription but it has no subscription id.")
        status_code, data = partner_request(
            "PUT",
            f"{PARTNER_BASE_URL}/partner/app/{app_id}/subscription/{subscription_id}",
            headers=headers,
            form=payload,
        )
        ensure_ok(status_code, data, "Update subscription")
        return {"action": "updated", "subscription": data.get("subscription") or {}}

    status_code, data = partner_request(
        "POST",
        f"{PARTNER_BASE_URL}/partner/app/{app_id}/subscription",
        headers=headers,
        form=payload,
    )
    ensure_ok(status_code, data, "Create subscription")
    return {"action": "created", "subscription": data.get("subscription") or {}}


def main() -> int:
    app_id = require_env("GUPSHUP_APP_ID")
    webhook_url = (os.environ.get("WEBHOOK_URL") or DEFAULT_WEBHOOK_URL).strip()
    if not webhook_url:
        raise SystemExit("Missing WEBHOOK_URL (or default inbound URL).")
    app_token = get_app_token(app_id)
    result = upsert_subscription(app_id, app_token, webhook_url)
    subscription = result["subscription"]
    print(
        json.dumps(
            {
                "status": "success",
                "action": result["action"],
                "appId": app_id,
                "subscriptionId": subscription.get("id"),
                "url": subscription.get("url"),
                "tag": subscription.get("tag"),
                "version": subscription.get("version"),
                "modes": subscription.get("modes"),
                "active": subscription.get("active"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
