"""Submit both broadcast 24h reminder Utility variants (Yes QR). Use whichever Meta approves."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qlink_chatbot.utils.env_load import gupshup_app_id, gupshup_token
from qlink_chatbot.whatsapp_functions.dashboard.create_template import create_template

if not gupshup_app_id or not gupshup_token:
    print("FAIL: GUPSHUP_APP_ID or GUPSHUP_TOKEN missing")
    sys.exit(1)

VARIANTS = [
    {
        "elementName": "masterclass_link_reminder",
        "body": (
            "We shared your masterclass invite earlier. "
            "Tap Yes and we'll send your joining link here on WhatsApp."
        ),
    },
    {
        "elementName": "masterclass_missing_out_reminder",
        "body": (
            "You are missing out on the Masterclass. "
            "Please click on 'Yes' below to register."
        ),
    },
]

results = []
for variant in VARIANTS:
    name = variant["elementName"]
    body = variant["body"]
    payload = {
        "elementName": name,
        "languageCode": "en",
        "category": "UTILITY",
        "templateType": "TEXT",
        "vertical": name,
        "content": body,
        "example": body,
        "buttons": json.dumps([{"type": "QUICK_REPLY", "text": "Yes"}]),
    }
    print(f"\n--- Submitting {name} as UTILITY + Yes QR ---")
    result = create_template(payload)
    tpl = result.get("template") or {}
    row = {
        "elementName": name,
        "status": result.get("status"),
        "template_id": tpl.get("id"),
        "template_status": tpl.get("status"),
        "category": tpl.get("category"),
        "message": result.get("message"),
    }
    results.append(row)
    print(json.dumps(row, indent=2))
    if result.get("status") != "success":
        safe = {k: v for k, v in result.items() if k not in ("token", "apiKey")}
        print(json.dumps(safe, indent=2, default=str)[:1500])

print("\n=== Summary ===")
for row in results:
    print(
        f"{row['elementName']}: id={row['template_id']} meta_status={row['template_status']}"
    )

approved_ids = [r["template_id"] for r in results if r.get("template_id")]
if approved_ids:
    print("\nSet on Vercel (comma-separated; bot uses first APPROVED):")
    print("BROADCAST_MASTERCLASS_REMINDER_TEMPLATE_IDS=" + ",".join(approved_ids))

if not any(r.get("template_id") for r in results):
    sys.exit(2)
