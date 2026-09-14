"""Auto-retry retriable campaign delivery failures after a delay."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qlink_chatbot.database.collections import campaigns
from qlink_chatbot.database.db_utils import append_chat_entries
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.utils.template_image import resolve_template_image_url
from qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch import (
    _template_chat_content,
)
from qlink_chatbot.whatsapp_functions.dashboard.send_template_by_id import (
    send_template_message,
)

DEFAULT_RETRY_DELAY_HOURS = 3
MAX_RETRIES_PER_CRON = 40
FAILED_STATUSES = frozenset({"failed", "undelivered"})
CLAIM_STALE_MINUTES = 15
RETRY_COUNT_PENDING_QUERY = {
    "$or": [
        {"retry_count": {"$exists": False}},
        {"retry_count": None},
        {"retry_count": 0},
    ]
}

PERMANENT_ERROR_MARKERS = (
    "[1002]",
    "not exist on whatsapp",
    "opt-in",
    "opt in",
    "template match",
    "[4003]",
    "[4005]",
    "paused template",
    "[1005]",
    "[1006]",
    "[1007]",
    "[1004]",
)

RETRIABLE_ERROR_MARKERS = (
    "low balance",
    "[9999]",
    "[1003]",
    "[4001]",
    "rate limit",
    "rate limited",
    "internal server",
    "[500]",
    "timeout",
    "temporarily unavailable",
    "service unavailable",
)


def is_retriable_campaign_error(error: str | None) -> bool:
    if not error:
        return False
    lowered = error.lower()
    for marker in PERMANENT_ERROR_MARKERS:
        if marker.lower() in lowered:
            return False
    for marker in RETRIABLE_ERROR_MARKERS:
        if marker.lower() in lowered:
            return True
    return False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _retry_delay_hours(campaign: dict) -> int:
    policy = campaign.get("retry_policy") or {}
    try:
        hours = int(policy.get("delay_hours", DEFAULT_RETRY_DELAY_HOURS))
    except (TypeError, ValueError):
        hours = DEFAULT_RETRY_DELAY_HOURS
    return max(hours, 1)


def _attempt_entry(
    *,
    kind: str,
    status: str,
    error: str | None = None,
    message_id: str | None = None,
) -> dict:
    return {
        "at": _utc_now().isoformat(),
        "kind": kind,
        "status": status,
        "error": error,
        "message_id": message_id,
    }


def schedule_recipient_retry(
    campaign_id: str,
    phone_number: str,
    error: str | None,
    *,
    failure_status: str = "failed",
) -> bool:
    """Schedule a one-time retry for a retriable failure. Returns True if scheduled."""
    if not is_retriable_campaign_error(error):
        return False

    doc = campaigns.find_one(
        {"campaign_id": campaign_id},
        {"recipients": 1, "retry_policy": 1},
    )
    if not doc:
        return False

    policy = doc.get("retry_policy") or {}
    if policy.get("enabled") is False:
        return False

    recipient = None
    idx = None
    for i, rec in enumerate(doc.get("recipients") or []):
        if rec.get("phone_number") == phone_number:
            recipient = rec
            idx = i
            break

    if recipient is None or idx is None:
        return False

    if recipient.get("status") in ("delivered", "read"):
        return False
    if (recipient.get("retry_count") or 0) >= 1:
        return False
    if recipient.get("retry_at"):
        return False

    now = _utc_now()
    retry_at = now + timedelta(hours=_retry_delay_hours(doc))
    attempt = _attempt_entry(
        kind="initial",
        status=failure_status,
        error=error,
        message_id=recipient.get("gupshup_message_id"),
    )

    campaigns.update_one(
        {"campaign_id": campaign_id},
        {
            "$set": {
                f"recipients.{idx}.failed_at": now,
                f"recipients.{idx}.retry_at": retry_at,
                f"recipients.{idx}.retry_count": recipient.get("retry_count") or 0,
            },
            "$push": {f"recipients.{idx}.attempts": attempt},
        },
    )
    logger.info(
        "Campaign recipient retry scheduled",
        extra={
            "campaign_id": campaign_id,
            "phone_number": phone_number,
            "retry_at": retry_at.isoformat(),
        },
    )
    return True


def _release_stale_claims(now: datetime) -> None:
    """Recover recipients stuck mid-retry after a crashed serverless invocation."""
    stale_before = now - timedelta(minutes=CLAIM_STALE_MINUTES)
    campaigns.update_many(
        {"recipients.retry_in_progress": True},
        {
            "$set": {
                "recipients.$[rec].retry_in_progress": False,
            }
        },
        array_filters=[
            {
                "rec.retry_in_progress": True,
                "rec.last_attempt_at": {"$lte": stale_before},
            }
        ],
    )


def claim_due_recipient() -> dict | None:
    """Atomically claim one recipient due for retry, or return None."""
    now = _utc_now()
    _release_stale_claims(now)
    doc = campaigns.find_one(
        {
            "recipients": {
                "$elemMatch": {
                    "status": {"$in": list(FAILED_STATUSES)},
                    "retry_at": {"$lte": now},
                    **RETRY_COUNT_PENDING_QUERY,
                    "retry_in_progress": {"$ne": True},
                }
            }
        },
        {"campaign_id": 1, "template_id": 1, "template_name": 1, "recipients": 1},
    )
    if not doc:
        return None

    campaign_id = doc["campaign_id"]
    for rec in doc.get("recipients") or []:
        phone = rec.get("phone_number")
        retry_at = _parse_dt(rec.get("retry_at"))
        if not phone:
            continue
        if rec.get("status") not in FAILED_STATUSES:
            continue
        if rec.get("retry_in_progress"):
            continue
        if (rec.get("retry_count") or 0) >= 1:
            continue
        if not retry_at or retry_at > now:
            continue

        result = campaigns.update_one(
            {
                "campaign_id": campaign_id,
                "recipients": {
                    "$elemMatch": {
                        "phone_number": phone,
                        "status": {"$in": list(FAILED_STATUSES)},
                        "retry_at": {"$lte": now},
                        **RETRY_COUNT_PENDING_QUERY,
                        "retry_in_progress": {"$ne": True},
                    }
                },
            },
            {
                "$set": {
                    "recipients.$.retry_in_progress": True,
                    "recipients.$.last_attempt_at": now,
                }
            },
        )
        if result.modified_count:
            return {
                "campaign_id": campaign_id,
                "phone_number": phone,
                "template_id": doc.get("template_id"),
                "template_name": doc.get("template_name"),
            }
    return None


def record_campaign_retry_send(
    campaign_id: str,
    phone_number: str,
    *,
    success: bool,
    message_id: str | None,
    error: str | None = None,
) -> None:
    """Finalize a retry attempt: reset status, bump retry_count, append audit."""
    status = "sent" if success else "failed"
    attempt = _attempt_entry(
        kind="retry",
        status=status,
        error=error,
        message_id=message_id,
    )
    set_fields = {
        "recipients.$.status": status,
        "recipients.$.gupshup_message_id": message_id,
        "recipients.$.retry_count": 1,
        "recipients.$.last_attempt_at": _utc_now(),
        "recipients.$.retry_at": None,
        "recipients.$.retry_in_progress": False,
    }
    if error:
        set_fields["recipients.$.error"] = error
    elif not success:
        set_fields["recipients.$.error"] = "Send failed"

    campaigns.update_one(
        {"campaign_id": campaign_id, "recipients.phone_number": phone_number},
        {
            "$set": set_fields,
            "$push": {"recipients.$.attempts": attempt},
        },
    )


def retry_campaign_recipient(claimed: dict) -> dict:
    """Send one retry for a previously claimed recipient."""
    campaign_id = claimed["campaign_id"]
    phone = claimed["phone_number"]
    template_id = claimed["template_id"]
    template_name = claimed.get("template_name") or template_id
    image_url = resolve_template_image_url(template_id)
    content = _template_chat_content(template_id, template_name)

    try:
        rsp = send_template_message(phone, template_id, image_url=image_url)
        record_campaign_retry_send(
            campaign_id,
            phone,
            success=rsp.get("success", False),
            message_id=rsp.get("message_id"),
            error=rsp.get("error"),
        )
        entry = {
            "role": "assistant",
            "content": content,
            "status": "submitted" if rsp.get("success") else "failed",
        }
        if rsp.get("message_id"):
            entry["gupshup_message_id"] = rsp["message_id"]
        if rsp.get("error"):
            entry["error"] = rsp["error"]
        append_chat_entries(phone, [entry])
        return {
            "campaign_id": campaign_id,
            "phone_number": phone,
            "success": rsp.get("success", False),
            "error": rsp.get("error"),
        }
    except Exception as e:
        logger.exception(
            "Campaign retry send failed",
            extra={"campaign_id": campaign_id, "phone": phone, "error": str(e)},
        )
        record_campaign_retry_send(
            campaign_id,
            phone,
            success=False,
            message_id=None,
            error=str(e),
        )
        append_chat_entries(
            phone,
            [
                {
                    "role": "assistant",
                    "content": content,
                    "status": "failed",
                    "error": str(e),
                }
            ],
        )
        return {
            "campaign_id": campaign_id,
            "phone_number": phone,
            "success": False,
            "error": str(e),
        }


def run_due_campaign_retries(limit: int = MAX_RETRIES_PER_CRON) -> dict:
    """Claim and process up to ``limit`` due campaign retries."""
    claimed_count = 0
    sent_ok = 0
    sent_failed = 0
    results: list[dict] = []

    for _ in range(max(limit, 0)):
        claimed = claim_due_recipient()
        if not claimed:
            break
        claimed_count += 1
        outcome = retry_campaign_recipient(claimed)
        results.append(outcome)
        if outcome.get("success"):
            sent_ok += 1
        else:
            sent_failed += 1

    summary = {
        "claimed": claimed_count,
        "sent_ok": sent_ok,
        "sent_failed": sent_failed,
    }
    if claimed_count:
        logger.info("Campaign retry cron finished", extra=summary)
    return summary


def backfill_recipient_retries(
    campaign_id: str | None = None,
    *,
    delay_hours: int = DEFAULT_RETRY_DELAY_HOURS,
) -> dict:
    """One-time backfill: schedule retries for existing retriable failures."""
    query = {}
    if campaign_id:
        query["campaign_id"] = campaign_id

    scheduled = 0
    skipped = 0
    now = _utc_now()

    for doc in campaigns.find(query, {"campaign_id": 1, "recipients": 1, "retry_policy": 1}):
        cid = doc["campaign_id"]
        for i, rec in enumerate(doc.get("recipients") or []):
            if rec.get("status") not in FAILED_STATUSES:
                skipped += 1
                continue
            if rec.get("retry_at"):
                skipped += 1
                continue
            if (rec.get("retry_count") or 0) >= 1:
                skipped += 1
                continue
            error = rec.get("error")
            if not is_retriable_campaign_error(error):
                skipped += 1
                continue

            failed_at = _parse_dt(rec.get("failed_at")) or now
            retry_at = failed_at + timedelta(hours=delay_hours)
            if retry_at <= now:
                retry_at = now

            attempt = _attempt_entry(
                kind="initial",
                status=rec.get("status") or "failed",
                error=error,
                message_id=rec.get("gupshup_message_id"),
            )
            campaigns.update_one(
                {"campaign_id": cid},
                {
                    "$set": {
                        f"recipients.{i}.failed_at": failed_at,
                        f"recipients.{i}.retry_at": retry_at,
                        f"recipients.{i}.retry_count": rec.get("retry_count") or 0,
                    },
                    "$push": {f"recipients.{i}.attempts": attempt},
                },
            )
            scheduled += 1

    return {"scheduled": scheduled, "skipped": skipped}
