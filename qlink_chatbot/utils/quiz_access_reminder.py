"""24h follow-up for quiz leads who have not registered for the Active masterclass."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qlink_chatbot.database.collections import leads
from qlink_chatbot.database.db_utils import append_chat_entries
from qlink_chatbot.database.leads import _engagement_event
from qlink_chatbot.database.masterclasses import get_active_masterclass
from qlink_chatbot.utils.env_load import quiz_submit_template_id
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.whatsapp_functions.dashboard.send_template_by_id import (
    send_template_message,
)

QUIZ_ACCESS_REMINDER_HOURS = 24
MAX_REMINDERS_PER_CRON = 40
CLAIM_STALE_MINUTES = 15

QUIZ_ACCESS_TEMPLATE_BODY = (
    "Thank you for completing the Money Archetype Quiz. "
    "Your Masterclass access has been unlocked. Tap Yes to receive the link."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_registered_for_active_masterclass(lead: dict) -> bool:
    """True when the lead has a registration row for the currently Active masterclass."""
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


def schedule_quiz_access_reminder(lead_id: str, sent_at: datetime) -> None:
    """Schedule a one-time 24h reminder after the first successful access_yes send."""
    if not lead_id:
        return
    due_at = sent_at + timedelta(hours=QUIZ_ACCESS_REMINDER_HOURS)
    leads.update_one(
        {"lead_id": lead_id},
        {
            "$set": {
                "quiz_access_first_sent_at": sent_at,
                "quiz_access_reminder_due_at": due_at,
            }
        },
    )
    logger.info(
        "Quiz access reminder scheduled",
        extra={"lead_id": lead_id, "due_at": due_at.isoformat()},
    )


def send_quiz_access_template(
    phone: str,
    username: str | None,
    *,
    kind: str = "initial",
    lead_id: str | None = None,
) -> dict:
    """Send access_yes Utility template and append inbox bubble."""
    template_id = (quiz_submit_template_id or "").strip()
    if not phone or not template_id:
        return {"success": False, "message_id": None, "error": "missing phone or template"}

    try:
        rsp = send_template_message(phone, template_id)
    except Exception as e:
        logger.exception(
            "Quiz access template send failed",
            extra={"phone_number": phone, "kind": kind, "error": str(e)},
        )
        rsp = {"success": False, "message_id": None, "error": str(e)}

    assistant = {
        "role": "assistant",
        "content": QUIZ_ACCESS_TEMPLATE_BODY,
        "status": "submitted" if rsp.get("success") else "failed",
        "template_id": template_id,
        "template_name": "access_yes",
    }
    if rsp.get("message_id"):
        assistant["gupshup_message_id"] = rsp["message_id"]
    if rsp.get("error"):
        assistant["error"] = rsp["error"]
    try:
        append_chat_entries(phone, [assistant], username)
    except Exception as e:
        logger.exception(
            "Quiz access template inbox append failed",
            extra={"phone_number": phone, "kind": kind, "error": str(e)},
        )

    if kind == "initial" and rsp.get("success") and lead_id:
        schedule_quiz_access_reminder(lead_id, _utc_now())

    return rsp


def _mark_reminder_complete(lead_id: str, *, sent: bool) -> None:
    now = _utc_now()
    update: dict = {"quiz_access_reminder_sent_at": now, "updated_at": now}
    ops: dict = {"$set": update}
    if sent:
        ops["$push"] = {
            "engagement": _engagement_event(
                "quiz_access_reminder_sent",
                now,
                label="Quiz access reminder sent",
            )
        }
    leads.update_one({"lead_id": lead_id}, ops)


def _release_stale_reminder_claims(now: datetime) -> None:
    stale_before = now - timedelta(minutes=CLAIM_STALE_MINUTES)
    leads.update_many(
        {
            "quiz_access_reminder_in_progress": True,
            "quiz_access_reminder_claimed_at": {"$lte": stale_before},
        },
        {"$set": {"quiz_access_reminder_in_progress": False}},
    )


def _due_reminder_query(now: datetime) -> dict:
    return {
        "source": "Money Ceiling Quiz",
        "quiz_access_reminder_due_at": {"$lte": now},
        "$or": [
            {"quiz_access_reminder_sent_at": {"$exists": False}},
            {"quiz_access_reminder_sent_at": None},
        ],
        "contact_number": {"$nin": [None, ""]},
        "whatsapp_ready": True,
        "quiz_access_reminder_in_progress": {"$ne": True},
    }


def claim_due_quiz_reminder() -> dict | None:
    """Atomically claim one lead due for a quiz access reminder."""
    now = _utc_now()
    _release_stale_reminder_claims(now)

    for _ in range(50):
        doc = leads.find_one(_due_reminder_query(now))
        if not doc:
            return None

        lead_id = doc.get("lead_id")
        if not lead_id:
            return None

        if is_registered_for_active_masterclass(doc):
            _mark_reminder_complete(lead_id, sent=False)
            continue

        result = leads.update_one(
            {
                "lead_id": lead_id,
                **_due_reminder_query(now),
            },
            {
                "$set": {
                    "quiz_access_reminder_in_progress": True,
                    "quiz_access_reminder_claimed_at": now,
                }
            },
        )
        if result.modified_count:
            return leads.find_one({"lead_id": lead_id})

    return None


def send_quiz_access_reminder(lead: dict) -> dict:
    """Send the one-time 24h access_yes reminder for a claimed lead."""
    lead_id = lead.get("lead_id")
    phone = lead.get("contact_number")
    name = lead.get("name")

    if is_registered_for_active_masterclass(lead):
        _mark_reminder_complete(lead_id, sent=False)
        leads.update_one(
            {"lead_id": lead_id},
            {"$set": {"quiz_access_reminder_in_progress": False}},
        )
        return {"lead_id": lead_id, "success": False, "skipped": "already_registered"}

    rsp = send_quiz_access_template(phone, name, kind="reminder")
    now = _utc_now()
    if rsp.get("success"):
        _mark_reminder_complete(lead_id, sent=True)
    leads.update_one(
        {"lead_id": lead_id},
        {"$set": {"quiz_access_reminder_in_progress": False}},
    )
    return {
        "lead_id": lead_id,
        "phone_number": phone,
        "success": rsp.get("success", False),
        "error": rsp.get("error"),
    }


def run_due_quiz_access_reminders(limit: int = MAX_REMINDERS_PER_CRON) -> dict:
    """Claim and process up to ``limit`` due quiz access reminders."""
    sent_ok = 0
    sent_failed = 0
    skipped_registered = 0
    claimed_count = 0

    for _ in range(max(limit, 0)):
        lead = claim_due_quiz_reminder()
        if not lead:
            break

        claimed_count += 1
        outcome = send_quiz_access_reminder(lead)
        if outcome.get("skipped") == "already_registered":
            skipped_registered += 1
        elif outcome.get("success"):
            sent_ok += 1
        else:
            sent_failed += 1

    summary = {
        "claimed": claimed_count,
        "sent_ok": sent_ok,
        "sent_failed": sent_failed,
        "skipped_registered": skipped_registered,
    }
    if claimed_count or skipped_registered:
        logger.info("Quiz access reminder cron finished", extra=summary)
    return summary
