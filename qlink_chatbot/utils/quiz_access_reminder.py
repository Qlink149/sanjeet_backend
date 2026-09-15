"""24h follow-up for quiz leads who have not registered for the Active masterclass."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qlink_chatbot.database.collections import leads
from qlink_chatbot.database.db_utils import append_chat_entries
from qlink_chatbot.utils.env_load import quiz_submit_template_id
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.whatsapp_functions.dashboard.send_template_by_id import (
    send_template_message,
)

QUIZ_ACCESS_REMINDER_HOURS = 24

QUIZ_ACCESS_TEMPLATE_BODY = (
    "Thank you for completing the Money Archetype Quiz. "
    "Your Masterclass access has been unlocked. Tap Yes to receive the link."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
