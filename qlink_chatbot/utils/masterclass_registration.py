"""Shared helpers for Active masterclass registration and nudge cleanup."""

from __future__ import annotations

from datetime import datetime, timezone

from qlink_chatbot.database.collections import campaigns, leads
from qlink_chatbot.database.masterclasses import get_active_masterclass
from qlink_chatbot.utils.phone import normalize_wa_phone


def is_registered_for_active_masterclass(lead: dict | None) -> bool:
    """True when the lead has a registration row for the currently Active masterclass."""
    if not lead:
        return False
    active = get_active_masterclass()
    if not active:
        return False
    active_id = active.get("masterclass_id")
    if not active_id:
        return False
    for row in lead.get("masterclass_registrations") or []:
        if isinstance(row, dict) and row.get("masterclass_id") == active_id:
            return True
    return False


def find_lead_by_phone(phone: str) -> dict | None:
    stored = normalize_wa_phone(phone) or phone
    if not stored:
        return None
    return leads.find_one(
        {
            "$or": [
                {"contact_number": stored},
                {"contact_numbers": stored},
            ]
        }
    )


def clear_pending_masterclass_nudges(phone: str) -> None:
    """Clear quiz and broadcast 24h reminder timers for a phone."""
    stored = normalize_wa_phone(phone) or phone
    if not stored:
        return
    now = datetime.now(timezone.utc)
    leads.update_many(
        {
            "$or": [
                {"contact_number": stored},
                {"contact_numbers": stored},
            ],
            "quiz_access_reminder_due_at": {"$exists": True, "$ne": None},
        },
        {
            "$set": {
                "quiz_access_reminder_sent_at": now,
                "updated_at": now,
                "masterclass_nudge_in_progress": False,
            },
            "$unset": {"quiz_access_reminder_due_at": ""},
        },
    )
    campaigns.update_many(
        {
            "recipients": {
                "$elemMatch": {
                    "phone_number": stored,
                    "mc_nudge_due_at": {"$exists": True, "$ne": None},
                    "$or": [
                        {"mc_nudge_sent_at": {"$exists": False}},
                        {"mc_nudge_sent_at": None},
                    ],
                }
            }
        },
        {
            "$set": {
                "recipients.$[r].mc_nudge_sent_at": now,
                "recipients.$[r].mc_nudge_in_progress": False,
            },
            "$unset": {"recipients.$[r].mc_nudge_due_at": ""},
        },
        array_filters=[
            {
                "r.phone_number": stored,
                "$or": [
                    {"r.mc_nudge_sent_at": {"$exists": False}},
                    {"r.mc_nudge_sent_at": None},
                ],
            }
        ],
    )
