"""Unified 24h Utility reminders for quiz access_yes and broadcast masterclass nudges."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from qlink_chatbot.database.collections import campaigns, leads
from qlink_chatbot.database.db_utils import append_chat_entries
from qlink_chatbot.database.leads import _engagement_event
from qlink_chatbot.utils.env_load import quiz_submit_template_id
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.utils.masterclass_registration import (
    clear_pending_masterclass_nudges,
    find_lead_by_phone,
    is_registered_for_active_masterclass,
)
from qlink_chatbot.utils.quiz_access_reminder import send_quiz_access_template
from qlink_chatbot.utils.template_buttons import (
    resolve_broadcast_reminder_template_id,
    template_display_body,
)
from qlink_chatbot.utils.template_image import resolve_template_image_url
from qlink_chatbot.whatsapp_functions.dashboard.send_template_by_id import (
    send_template_message,
)

NudgeKind = Literal["quiz_access", "broadcast"]

MAX_REMINDERS_PER_CRON = 40
CLAIM_STALE_MINUTES = 15
NUDGE_DEFER_HOURS = 24

BROADCAST_REMINDER_BODY_FALLBACK = (
    "You are missing out on the Masterclass. "
    "Please click on 'Yes' below to register."
)

SUCCESSFUL_CAMPAIGN_STATUSES = frozenset({"sent", "delivered", "read"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def _quiz_due_query(now: datetime) -> dict:
    return {
        "source": "Money Ceiling Quiz",
        "quiz_access_reminder_due_at": {"$lte": now},
        "$or": [
            {"quiz_access_reminder_sent_at": {"$exists": False}},
            {"quiz_access_reminder_sent_at": None},
        ],
        "contact_number": {"$nin": [None, ""]},
        "whatsapp_ready": True,
        "masterclass_nudge_in_progress": {"$ne": True},
    }


def _broadcast_recipient_due(rec: dict, now: datetime) -> bool:
    if rec.get("mc_nudge_in_progress"):
        return False
    if rec.get("mc_nudge_sent_at"):
        return False
    due_at = _parse_dt(rec.get("mc_nudge_due_at"))
    if not due_at or due_at > now:
        return False
    if rec.get("status") not in SUCCESSFUL_CAMPAIGN_STATUSES:
        return False
    return bool(rec.get("phone_number"))


def _collect_due_items(now: datetime, exclude_phones: set[str]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)

    quiz_template_id = (quiz_submit_template_id or "").strip()
    for doc in leads.find(_quiz_due_query(now), limit=200):
        phone = doc.get("contact_number")
        if not phone or phone in exclude_phones:
            continue
        due_at = _parse_dt(doc.get("quiz_access_reminder_due_at"))
        if not due_at:
            continue
        grouped[phone].append(
            {
                "kind": "quiz_access",
                "phone": phone,
                "due_at": due_at,
                "template_id": quiz_template_id,
                "lead_id": doc.get("lead_id"),
                "lead": doc,
            }
        )

    reminder_template_id = resolve_broadcast_reminder_template_id()
    if reminder_template_id:
        cursor = campaigns.find(
            {"masterclass_nudge_enabled": True},
            {"campaign_id": 1, "recipients": 1},
            limit=100,
        )
        for doc in cursor:
            campaign_id = doc.get("campaign_id")
            for rec in doc.get("recipients") or []:
                if not _broadcast_recipient_due(rec, now):
                    continue
                phone = rec.get("phone_number")
                if not phone or phone in exclude_phones:
                    continue
                due_at = _parse_dt(rec.get("mc_nudge_due_at"))
                if not due_at:
                    continue
                grouped[phone].append(
                    {
                        "kind": "broadcast",
                        "phone": phone,
                        "due_at": due_at,
                        "template_id": reminder_template_id,
                        "campaign_id": campaign_id,
                    }
                )

    return grouped


def _priority(kind: NudgeKind) -> int:
    return 0 if kind == "quiz_access" else 1


def _resolve_collision(items: list[dict], now: datetime) -> tuple[dict | None, list[dict]]:
    due_items = [item for item in items if item["due_at"] <= now]
    if not due_items:
        return None, []
    due_items.sort(key=lambda item: (_priority(item["kind"]), item["due_at"]))
    to_send = due_items[0]
    to_defer = [item for item in due_items[1:] if item["kind"] == "broadcast"]
    return to_send, to_defer


def _defer_broadcast_nudges(items: list[dict], now: datetime) -> None:
    new_due = now + timedelta(hours=NUDGE_DEFER_HOURS)
    for item in items:
        campaign_id = item.get("campaign_id")
        phone = item.get("phone")
        if not campaign_id or not phone:
            continue
        campaigns.update_one(
            {
                "campaign_id": campaign_id,
                "recipients": {
                    "$elemMatch": {
                        "phone_number": phone,
                        "mc_nudge_due_at": {"$lte": now},
                        "$or": [
                            {"mc_nudge_sent_at": {"$exists": False}},
                            {"mc_nudge_sent_at": None},
                        ],
                    }
                },
            },
            {
                "$set": {
                    "recipients.$.mc_nudge_due_at": new_due,
                    "recipients.$.mc_nudge_in_progress": False,
                }
            },
        )
        logger.info(
            "Broadcast masterclass nudge deferred",
            extra={
                "campaign_id": campaign_id,
                "phone_number": phone,
                "new_due_at": new_due.isoformat(),
            },
        )


def _release_stale_claims(now: datetime) -> None:
    stale_before = now - timedelta(minutes=CLAIM_STALE_MINUTES)
    leads.update_many(
        {
            "masterclass_nudge_in_progress": True,
            "masterclass_nudge_claimed_at": {"$lte": stale_before},
        },
        {"$set": {"masterclass_nudge_in_progress": False}},
    )
    campaigns.update_many(
        {"recipients.mc_nudge_in_progress": True},
        {
            "$set": {
                "recipients.$[rec].mc_nudge_in_progress": False,
            }
        },
        array_filters=[
            {
                "rec.mc_nudge_in_progress": True,
                "rec.mc_nudge_claimed_at": {"$lte": stale_before},
            }
        ],
    )


def _claim_quiz_nudge(lead_id: str, now: datetime) -> bool:
    result = leads.update_one(
        {
            "lead_id": lead_id,
            **_quiz_due_query(now),
        },
        {
            "$set": {
                "masterclass_nudge_in_progress": True,
                "masterclass_nudge_claimed_at": now,
            }
        },
    )
    return bool(result.modified_count)


def _claim_broadcast_nudge(campaign_id: str, phone: str, now: datetime) -> bool:
    result = campaigns.update_one(
        {
            "campaign_id": campaign_id,
            "recipients": {
                "$elemMatch": {
                    "phone_number": phone,
                    "mc_nudge_due_at": {"$lte": now},
                    "$or": [
                        {"mc_nudge_sent_at": {"$exists": False}},
                        {"mc_nudge_sent_at": None},
                    ],
                    "mc_nudge_in_progress": {"$ne": True},
                    "status": {"$in": list(SUCCESSFUL_CAMPAIGN_STATUSES)},
                }
            },
        },
        {
            "$set": {
                "recipients.$.mc_nudge_in_progress": True,
                "recipients.$.mc_nudge_claimed_at": now,
            }
        },
    )
    return bool(result.modified_count)


def _claim_item(item: dict, now: datetime) -> bool:
    kind = item["kind"]
    if kind == "quiz_access":
        lead_id = item.get("lead_id")
        return bool(lead_id) and _claim_quiz_nudge(lead_id, now)
    return _claim_broadcast_nudge(item.get("campaign_id"), item.get("phone"), now)


def _release_claim(item: dict) -> None:
    if item["kind"] == "quiz_access":
        lead_id = item.get("lead_id")
        if lead_id:
            leads.update_one(
                {"lead_id": lead_id},
                {"$set": {"masterclass_nudge_in_progress": False}},
            )
        return
    campaign_id = item.get("campaign_id")
    phone = item.get("phone")
    if campaign_id and phone:
        campaigns.update_one(
            {"campaign_id": campaign_id, "recipients.phone_number": phone},
            {"$set": {"recipients.$.mc_nudge_in_progress": False}},
        )


def _mark_quiz_reminder_complete(lead_id: str, *, sent: bool) -> None:
    now = _utc_now()
    update: dict = {
        "quiz_access_reminder_sent_at": now,
        "updated_at": now,
        "masterclass_nudge_in_progress": False,
    }
    ops: dict = {"$set": update, "$unset": {"quiz_access_reminder_due_at": ""}}
    if sent:
        ops["$push"] = {
            "engagement": _engagement_event(
                "quiz_access_reminder_sent",
                now,
                label="Quiz access reminder sent",
            )
        }
    leads.update_one({"lead_id": lead_id}, ops)


def _mark_broadcast_nudge_complete(campaign_id: str, phone: str, *, sent: bool) -> None:
    now = _utc_now()
    set_fields = {
        "recipients.$.mc_nudge_sent_at": now,
        "recipients.$.mc_nudge_in_progress": False,
    }
    ops: dict = {"$set": set_fields, "$unset": {"recipients.$.mc_nudge_due_at": ""}}
    campaigns.update_one(
        {"campaign_id": campaign_id, "recipients.phone_number": phone},
        ops,
    )


def _send_broadcast_reminder(phone: str, template_id: str) -> dict:
    image_url = resolve_template_image_url(template_id)
    try:
        rsp = send_template_message(phone, template_id, image_url=image_url)
    except Exception as e:
        logger.exception(
            "Broadcast masterclass reminder send failed",
            extra={"phone_number": phone, "error": str(e)},
        )
        rsp = {"success": False, "message_id": None, "error": str(e)}

    body = template_display_body(template_id) or BROADCAST_REMINDER_BODY_FALLBACK
    assistant = {
        "role": "assistant",
        "content": body,
        "status": "submitted" if rsp.get("success") else "failed",
        "template_id": template_id,
        "template_name": "broadcast_masterclass_reminder",
    }
    if rsp.get("message_id"):
        assistant["gupshup_message_id"] = rsp["message_id"]
    if rsp.get("error"):
        assistant["error"] = rsp["error"]
    try:
        append_chat_entries(phone, [assistant])
    except Exception as e:
        logger.exception(
            "Broadcast reminder inbox append failed",
            extra={"phone_number": phone, "error": str(e)},
        )
    return rsp


def _send_nudge(item: dict) -> dict:
    phone = item["phone"]
    kind = item["kind"]
    if kind == "quiz_access":
        lead = item.get("lead") or find_lead_by_phone(phone) or {}
        lead_id = item.get("lead_id") or lead.get("lead_id")
        name = lead.get("name")
        rsp = send_quiz_access_template(phone, name, kind="reminder", lead_id=lead_id)
        if rsp.get("success") and lead_id:
            _mark_quiz_reminder_complete(lead_id, sent=True)
        elif lead_id:
            leads.update_one(
                {"lead_id": lead_id},
                {"$set": {"masterclass_nudge_in_progress": False}},
            )
        return {
            "kind": kind,
            "phone_number": phone,
            "lead_id": lead_id,
            "success": rsp.get("success", False),
            "error": rsp.get("error"),
        }

    campaign_id = item.get("campaign_id")
    template_id = item.get("template_id")
    rsp = _send_broadcast_reminder(phone, template_id)
    if rsp.get("success") and campaign_id:
        _mark_broadcast_nudge_complete(campaign_id, phone, sent=True)
    elif campaign_id:
        campaigns.update_one(
            {"campaign_id": campaign_id, "recipients.phone_number": phone},
            {"$set": {"recipients.$.mc_nudge_in_progress": False}},
        )
    return {
        "kind": kind,
        "phone_number": phone,
        "campaign_id": campaign_id,
        "success": rsp.get("success", False),
        "error": rsp.get("error"),
    }


def run_due_masterclass_utility_reminders(
    limit: int = MAX_REMINDERS_PER_CRON,
) -> dict:
    """Claim and process up to ``limit`` due masterclass Utility reminders."""
    now = _utc_now()
    _release_stale_claims(now)

    sent_ok = 0
    sent_failed = 0
    skipped_registered = 0
    deferred = 0
    claimed_count = 0
    processed_phones: set[str] = set()

    while claimed_count < max(limit, 0):
        grouped = _collect_due_items(now, processed_phones)
        if not grouped:
            break

        phone = min(
            grouped.keys(),
            key=lambda p: min(item["due_at"] for item in grouped[p]),
        )
        items = grouped[phone]
        processed_phones.add(phone)

        lead = find_lead_by_phone(phone)
        if is_registered_for_active_masterclass(lead):
            clear_pending_masterclass_nudges(phone)
            skipped_registered += 1
            continue

        to_send, to_defer = _resolve_collision(items, now)
        if to_defer:
            _defer_broadcast_nudges(to_defer, now)
            deferred += len(to_defer)

        if not to_send:
            continue

        if not _claim_item(to_send, now):
            continue

        claimed_count += 1
        try:
            outcome = _send_nudge(to_send)
        except Exception:
            _release_claim(to_send)
            raise

        if not outcome.get("success"):
            _release_claim(to_send)
            sent_failed += 1
        else:
            sent_ok += 1

    summary = {
        "claimed": claimed_count,
        "sent_ok": sent_ok,
        "sent_failed": sent_failed,
        "skipped_registered": skipped_registered,
        "deferred": deferred,
    }
    if any(summary.values()):
        logger.info("Masterclass utility reminder cron finished", extra=summary)
    return summary
