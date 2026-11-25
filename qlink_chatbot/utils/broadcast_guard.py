"""Never send the same template to the same person twice.

Two layers:

1. ``filter_already_received`` looks at past campaigns, so a repeat broadcast or an
   overlapping list drops people who already got this template, and the preview
   can say how many were skipped.
2. ``try_claim`` is an atomic per-(phone, template) claim taken right before each
   send. It stops a double click, two overlapping campaigns, or the scheduler and
   a manual send, from both reaching the same person. A send that fails (at submit
   or later at delivery) gives its claim back so the retry job, or a new
   broadcast, can still deliver it.

"Same message" means the same template: matched by template id or template name.
Passing ``skip_already_sent=False`` to a send is the deliberate "send again" escape.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from qlink_chatbot.database.collections import campaigns
from qlink_chatbot.database.database import db
from qlink_chatbot.utils.logger_config import logger

# A recipient in one of these states has the message (or it is on its way).
RECEIVED_STATUSES = ("sent", "delivered", "read")
# A claim whose owner ended in one of these states did not actually deliver.
NOT_DELIVERED_STATUSES = ("failed", "undelivered")
SKIPPED_STATUS = "skipped_duplicate"

claims = db["broadcast_claims"]
_index_ready = False


def _ensure_index() -> None:
    global _index_ready
    if _index_ready:
        return
    claims.create_index(
        [("phone", 1), ("template_key", 1)], unique=True, name="phone_template_unique"
    )
    _index_ready = True


def template_key(template_id: str | None, template_name: str | None) -> str:
    return (template_name or template_id or "").strip()


def already_received_phones(
    template_id: str | None,
    template_name: str | None,
    phones: list[str],
    exclude_campaign_id: str | None = None,
) -> set[str]:
    """Phones in ``phones`` that already received this template in a past campaign."""
    if not phones or not (template_id or template_name):
        return set()
    same_template = []
    if template_id:
        same_template.append({"template_id": template_id})
    if template_name:
        same_template.append({"template_name": template_name})
    match: dict = {"$or": same_template}
    if exclude_campaign_id:
        match["campaign_id"] = {"$ne": exclude_campaign_id}
    pipeline = [
        {"$match": match},
        {"$unwind": "$recipients"},
        {
            "$match": {
                "recipients.phone_number": {"$in": phones},
                "recipients.status": {"$in": list(RECEIVED_STATUSES)},
            }
        },
        {"$group": {"_id": "$recipients.phone_number"}},
    ]
    return {row["_id"] for row in campaigns.aggregate(pipeline)}


def filter_already_received(
    template_id: str | None,
    template_name: str | None,
    phones: list[str],
    exclude_campaign_id: str | None = None,
) -> tuple[list[str], list[str]]:
    """(to_send, skipped) with order preserved."""
    received = already_received_phones(
        template_id, template_name, phones, exclude_campaign_id
    )
    return (
        [p for p in phones if p not in received],
        [p for p in phones if p in received],
    )


def _recipient_status(campaign_id: str, phone: str) -> str | None:
    doc = campaigns.find_one(
        {"campaign_id": campaign_id, "recipients.phone_number": phone},
        {"recipients.$": 1},
    )
    recipients = (doc or {}).get("recipients") or []
    return recipients[0].get("status") if recipients else None


def try_claim(
    phone: str, template_id: str | None, template_name: str | None, campaign_id: str
) -> bool:
    """True if this call won the right to send; False if someone already has."""
    _ensure_index()
    key = template_key(template_id, template_name)
    now = datetime.now(timezone.utc)
    try:
        claims.insert_one(
            {
                "phone": phone,
                "template_key": key,
                "campaign_id": campaign_id,
                "claimed_at": now,
            }
        )
        return True
    except DuplicateKeyError:
        pass

    existing = claims.find_one({"phone": phone, "template_key": key})
    if not existing:  # released between our insert and this read: try once more
        return try_claim_once(phone, key, campaign_id, now)
    owner = existing.get("campaign_id")
    if owner == campaign_id:
        return True  # our own claim (e.g. a retry of the same campaign)
    if _recipient_status(owner, phone) in NOT_DELIVERED_STATUSES:
        # the earlier send never reached them: take the claim over
        taken = claims.update_one(
            {"_id": existing["_id"], "campaign_id": owner},
            {"$set": {"campaign_id": campaign_id, "claimed_at": now}},
        )
        return taken.modified_count == 1
    return False


def try_claim_once(phone: str, key: str, campaign_id: str, now: datetime) -> bool:
    try:
        claims.insert_one(
            {
                "phone": phone,
                "template_key": key,
                "campaign_id": campaign_id,
                "claimed_at": now,
            }
        )
        return True
    except DuplicateKeyError:
        return False


def release_claim(
    phone: str, template_id: str | None, template_name: str | None, campaign_id: str
) -> None:
    """Give the claim back after a failed send so a retry can deliver it."""
    claims.delete_one(
        {
            "phone": phone,
            "template_key": template_key(template_id, template_name),
            "campaign_id": campaign_id,
        }
    )


def mark_skipped(campaign_id: str, phone: str) -> None:
    """Record that this recipient was skipped because they already got the template."""
    try:
        campaigns.update_one(
            {"campaign_id": campaign_id, "recipients.phone_number": phone},
            {"$set": {"recipients.$.status": SKIPPED_STATUS}},
        )
    except Exception as exc:
        logger.warning("could not mark recipient skipped", extra={"error": str(exc)})
