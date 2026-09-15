"""Smoke checks for broadcast 24h masterclass_link_reminder wiring."""
from __future__ import annotations

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

APPROVED_REMINDER_ID = "5f8f530a-1668-4da7-8c49-a9e67c3462ae"


def main() -> int:
    from qlink_chatbot.utils.env_load import broadcast_masterclass_reminder_template_id
    from qlink_chatbot.utils.template_buttons import (
        resolve_broadcast_reminder_template_id,
        template_display_body,
    )
    from qlink_chatbot.whatsapp_functions.dashboard.get_all_templates import (
        get_all_templates,
    )

    errors: list[str] = []

    configured = (broadcast_masterclass_reminder_template_id or "").strip()
    if configured != APPROVED_REMINDER_ID:
        errors.append(
            f"env default mismatch: expected {APPROVED_REMINDER_ID}, got {configured!r}"
        )

    resolved = resolve_broadcast_reminder_template_id()
    if resolved != APPROVED_REMINDER_ID:
        errors.append(f"resolve_broadcast_reminder_template_id returned {resolved!r}")

    templates = get_all_templates(force=True) or []
    by_id = {t.get("id"): t for t in templates if t.get("id")}
    tpl = by_id.get(APPROVED_REMINDER_ID)
    if not tpl:
        errors.append(f"template {APPROVED_REMINDER_ID} not found in Gupshup")
    else:
        status = str(tpl.get("status", "")).upper()
        name = tpl.get("elementName")
        print(f"OK Gupshup template: {name} status={status}")
        if status != "APPROVED":
            errors.append(f"template status is {status}, expected APPROVED")
        body = template_display_body(APPROVED_REMINDER_ID)
        if not body:
            errors.append("could not read template body for inbox label")
        else:
            print(f"OK body preview: {body[:80]}...")

    vercel_path = Path(__file__).resolve().parent.parent / "vercel.json"
    if vercel_path.exists():
        text = vercel_path.read_text(encoding="utf-8")
        if "masterclass-utility-reminders" not in text:
            errors.append("vercel.json missing masterclass-utility-reminders cron")
        else:
            print("OK vercel.json cron path present")

    if errors:
        print("\nFAIL:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
