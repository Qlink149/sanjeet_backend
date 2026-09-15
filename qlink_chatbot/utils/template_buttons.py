"""Helpers for inspecting Gupshup template button metadata."""

from __future__ import annotations

import json

from qlink_chatbot.utils.env_load import (
    broadcast_masterclass_reminder_template_id,
    broadcast_masterclass_reminder_template_ids,
)
from qlink_chatbot.utils.phone import normalize_trigger_text
from qlink_chatbot.whatsapp_functions.dashboard.get_all_templates import (
    get_all_templates,
)

# Submitted Utility variants — bot uses first APPROVED (in this order).
_BROADCAST_REMINDER_FALLBACK_IDS = (
    "5f8f530a-1668-4da7-8c49-a9e67c3462ae",  # masterclass_link_reminder
    "6528f8e7-0ec5-43ee-9fb5-fbba70315611",  # masterclass_missing_out_reminder
)


def _template_by_id(template_id: str) -> dict | None:
    if not template_id:
        return None
    templates = get_all_templates() or []
    return next((t for t in templates if t.get("id") == template_id), None)


def _buttons_from_template(template: dict) -> list[dict]:
    raw = template.get("containerMeta")
    if not raw:
        return []
    try:
        meta = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    buttons = meta.get("buttons") if isinstance(meta, dict) else None
    return buttons if isinstance(buttons, list) else []


def template_has_yes_quick_reply(template_id: str) -> bool:
    """True when the template has a QUICK_REPLY button labeled Yes (case-insensitive)."""
    template = _template_by_id(template_id)
    if not template:
        return False
    for btn in _buttons_from_template(template):
        if btn.get("type") != "QUICK_REPLY":
            continue
        if normalize_trigger_text(btn.get("text")) == "yes":
            return True
    return False


def broadcast_reminder_template_candidates() -> list[str]:
    """Ordered list of broadcast reminder template ids to try (env + fallbacks)."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in (
        broadcast_masterclass_reminder_template_ids or "",
        broadcast_masterclass_reminder_template_id or "",
    ):
        for part in raw.split(","):
            tid = part.strip()
            if tid and tid not in seen:
                seen.add(tid)
                out.append(tid)
    for tid in _BROADCAST_REMINDER_FALLBACK_IDS:
        tid = (tid or "").strip()
        if tid and tid not in seen:
            seen.add(tid)
            out.append(tid)
    return out


def resolve_broadcast_reminder_template_id() -> str:
    """Pick the first Meta-APPROVED reminder template, else first configured candidate."""
    candidates = broadcast_reminder_template_candidates()
    if not candidates:
        return ""
    templates = get_all_templates(force=True) or []
    by_id = {t.get("id"): t for t in templates if t.get("id")}
    for tid in candidates:
        tpl = by_id.get(tid)
        if tpl and str(tpl.get("status", "")).upper() == "APPROVED":
            return tid
    return candidates[0]


def template_display_body(template_id: str) -> str:
    """Human-readable template body for inbox bubbles."""
    tpl = _template_by_id(template_id)
    if tpl:
        raw = (tpl.get("data") or tpl.get("content") or "").strip()
        if raw:
            return raw.split("|")[0].strip()
    return ""


def resolve_masterclass_nudge_enabled(template_id: str) -> bool:
    """Broadcast campaigns schedule 24h nudges when Yes QR + reminder template configured."""
    return bool(broadcast_reminder_template_candidates()) and template_has_yes_quick_reply(
        template_id
    )
