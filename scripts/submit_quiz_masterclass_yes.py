"""Submit quiz_masterclass_yes Utility template (Yes QR, no meet link in body)."""
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

BODY = (
    "Your money archetype Quiz is submitted successfully. "
    "You are now eligible for the Free money masterclass. "
    "Tap Yes to receive the link"
)

payload = {
    "elementName": "quiz_masterclass_yes",
    "languageCode": "en",
    "category": "UTILITY",
    "templateType": "TEXT",
    "vertical": "quiz_masterclass_yes",
    "content": BODY,
    "example": BODY,
    "buttons": json.dumps([{"type": "QUICK_REPLY", "text": "Yes"}]),
}

print("Submitting quiz_masterclass_yes as UTILITY + Yes QR...")
result = create_template(payload)
print("status_field=", result.get("status"))
print("message=", result.get("message"))
tpl = result.get("template") or {}
print("template_id=", tpl.get("id"))
print("template_status=", tpl.get("status"))
print("category=", tpl.get("category"))
print("elementName=", tpl.get("elementName"))
if result.get("status") != "success":
    safe = {k: v for k, v in result.items() if k not in ("token", "apiKey")}
    print(json.dumps(safe, indent=2, default=str)[:2000])
    sys.exit(2)
print("OK submitted")
