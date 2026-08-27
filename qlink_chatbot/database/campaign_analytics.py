"""Campaign delivery-status persistence for Gupshup webhooks."""

from qlink_chatbot.database.collections import campaigns
from qlink_chatbot.utils.campaign_status import should_apply_status


def update_campaign_recipient_status(
    message_id: str,
    status: str,
    whatsapp_message_id: str | None = None,
    error_reason: str | None = None,
) -> bool:
    """Update a recipient's delivery status by Gupshup and/or WhatsApp id.

    ``message_id`` should be the Gupshup ``gs_id`` / submit ``messageId`` when
    available. ``whatsapp_message_id`` is stored on first match so later
    webhooks that only carry the WhatsApp id can still update.

    Returns True if a matching recipient was found (most status webhooks
    won't match, since they fire for every outbound message, not just
    campaign sends). Skipped downgrades still return True.
    """
    ids = [i for i in (message_id, whatsapp_message_id) if i]
    if not ids or not status:
        return False

    doc = campaigns.find_one(
        {
            "$or": [
                {"recipients.gupshup_message_id": {"$in": ids}},
                {"recipients.whatsapp_message_id": {"$in": ids}},
            ]
        },
        {"recipients": 1},
    )
    if not doc:
        return False

    recipient = None
    idx = None
    for i, rec in enumerate(doc.get("recipients") or []):
        if (
            rec.get("gupshup_message_id") in ids
            or rec.get("whatsapp_message_id") in ids
        ):
            recipient = rec
            idx = i
            break

    if recipient is None or idx is None:
        return False

    if not should_apply_status(recipient.get("status"), status):
        return True

    set_fields: dict = {f"recipients.{idx}.status": status}
    if whatsapp_message_id:
        set_fields[f"recipients.{idx}.whatsapp_message_id"] = (
            whatsapp_message_id
        )
    if error_reason:
        set_fields[f"recipients.{idx}.error"] = error_reason

    campaigns.update_one({"_id": doc["_id"]}, {"$set": set_fields})
    return True
