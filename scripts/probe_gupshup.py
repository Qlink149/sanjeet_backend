"""Probe Sanjeet Gupshup credentials: list templates, then optional test send.

Does not print secrets. Destination for send: 919116914178 (user-provided).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

APP_ID = os.environ.get("GUPSHUP_APP_ID") or ""
TOKEN = os.environ.get("GUPSHUP_TOKEN") or ""
API_KEY = os.environ.get("GUPSHUP_API_KEY") or ""
APP_NAME = os.environ.get("GUPSHUP_APP_NAME") or ""
SOURCE = os.environ.get("GUPSHUP_SOURCE") or ""
DEST = "919116914178"


def mask(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 8:
        return f"len={len(value)}"
    return f"{value[:4]}…{value[-3:]} len={len(value)} quoted={value[:1]==chr(34)}"


def dump_resp(label: str, res: httpx.Response) -> dict | None:
    try:
        body = res.json()
    except Exception:
        body = {"raw": res.text[:400]}
    status = body.get("status") if isinstance(body, dict) else None
    msg = None
    if isinstance(body, dict):
        msg = body.get("message") or body.get("error") or body.get("reason")
    n_tpl = None
    templates = []
    if isinstance(body, dict):
        templates = body.get("templates") or body.get("data") or []
        if isinstance(templates, list):
            n_tpl = len(templates)
    print(f"\n=== {label} ===")
    print(f"http={res.status_code} gupshup_status={status} message={msg} templates={n_tpl}")
    if n_tpl:
        for t in templates[:8]:
            if isinstance(t, dict):
                print(
                    f"  - {t.get('elementName') or t.get('name')} "
                    f"id={t.get('id')} status={t.get('status')} cat={t.get('category')}"
                )
    elif isinstance(body, dict) and not n_tpl:
        keys = list(body.keys())
        print(f"  body_keys={keys}")
        snippet = json.dumps(body)[:500]
        if "sk_" not in snippet:
            print(f"  body={snippet}")
    return body if isinstance(body, dict) else None


def main() -> int:
    print("env check")
    print(f"  APP_ID   {mask(APP_ID)}")
    print(f"  TOKEN    {mask(TOKEN)}")
    print(f"  API_KEY  {mask(API_KEY)}")
    print(f"  APP_NAME {APP_NAME!r}")
    print(f"  SOURCE   {SOURCE!r}")

    partner_url = f"https://partner.gupshup.io/partner/app/{APP_ID}/templates"
    direct_url = f"https://api.gupshup.io/wa/app/{APP_ID}/template"

    attempts = [
        ("partner Authorization=TOKEN", partner_url, {"Authorization": TOKEN}),
        ("partner token=TOKEN", partner_url, {"token": TOKEN}),
        ("partner Authorization=API_KEY", partner_url, {"Authorization": API_KEY}),
        ("partner token=API_KEY", partner_url, {"token": API_KEY}),
        ("direct apikey=API_KEY", direct_url, {"apikey": API_KEY}),
        ("direct apikey=TOKEN", direct_url, {"apikey": TOKEN}),
    ]

    winners = []
    templates = []
    with httpx.Client(timeout=25.0) as client:
        for label, url, headers in attempts:
            hdrs = {**headers, "Content-Type": "application/json"}
            try:
                res = client.get(url, headers=hdrs)
            except Exception as e:
                print(f"\n=== {label} ===\n  request failed: {e}")
                continue
            body = dump_resp(label, res)
            tpls = (body or {}).get("templates") or (body or {}).get("data") or []
            ok = res.status_code == 200 and (
                (body or {}).get("status") == "success" or isinstance(tpls, list) and tpls
            )
            if ok and isinstance(tpls, list) and tpls:
                winners.append(label)
                templates = tpls

        print("\n=== session text send (api.gupshup.io, apikey) ===")
        text_url = "https://api.gupshup.io/wa/api/v1/msg"
        text_data = {
            "source": SOURCE,
            "destination": DEST,
            "src.name": APP_NAME,
            "message": json.dumps(
                {
                    "type": "text",
                    "text": "Sanjeet dashboard test from Qlink — if you see this, session messages work.",
                }
            ),
        }
        res = client.post(
            text_url,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "apikey": API_KEY,
            },
            data=text_data,
        )
        dump_resp("session text API_KEY", res)

        if templates:
            approved = [
                t
                for t in templates
                if str(t.get("status", "")).upper() in {"APPROVED", "ACTIVE"}
            ]
            pick = approved[0] if approved else templates[0]
            print(
                f"\n=== template send using {pick.get('elementName')} "
                f"({pick.get('id')}) status={pick.get('status')} ==="
            )
            tpl_url = f"https://partner.gupshup.io/partner/app/{APP_ID}/template/msg"
            res = client.post(
                tpl_url,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "token": TOKEN,
                },
                data={
                    "source": SOURCE,
                    "destination": DEST,
                    "src.name": APP_NAME,
                    "template": json.dumps({"id": pick.get("id"), "params": []}),
                },
            )
            dump_resp("template TOKEN header", res)
            if res.status_code != 200:
                res2 = client.post(
                    tpl_url,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "token": API_KEY,
                    },
                    data={
                        "source": SOURCE,
                        "destination": DEST,
                        "src.name": APP_NAME,
                        "template": json.dumps({"id": pick.get("id"), "params": []}),
                    },
                )
                dump_resp("template API_KEY as token", res2)

    print("\n=== winners (list templates) ===")
    print(winners or "(none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
