from datetime import datetime, timezone

from qlink_chatbot.database.collections import campaigns
from qlink_chatbot.database.db_utils import (
    append_chat_entries,
    schedule_campaign_mc_nudge,
    set_campaign_recipient_sent,
)
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.utils.phone import normalize_phone_list
from qlink_chatbot.whatsapp_functions.dashboard.get_all_templates import (
    get_all_templates,
)
from qlink_chatbot.whatsapp_functions.dashboard.send_template_by_id import (
    send_template_message,
)


def _template_chat_content(template_id: str, template_name: str) -> str:
    """Label an outbound bubble: template name, short body, quiz hint."""
    name = template_name or template_id or "template"
    body = ""
    try:
        templates = get_all_templates() or []
        match = next(
            (
                t
                for t in templates
                if t.get("id") == template_id or t.get("elementName") == name
            ),
            None,
        )
        if match:
            name = match.get("elementName") or name
            body = (match.get("data") or match.get("content") or "").strip()
    except Exception as e:
        logger.warning(
            "Could not load template body for chat history",
            extra={"template_id": template_id, "error": str(e)},
        )
    parts = [name]
    if body:
        parts.append(body if len(body) <= 240 else f"{body[:237]}...")
    if "quiz" in name.lower() and "take the quiz" not in "\n".join(parts).lower():
        parts.append("Take the quiz")
    return "\n".join(parts)


def send_campaign_messages(
    campaign_id: str,
    phones: list,
    template_id: str,
    image_url: str | None,
):
    """Sends every recipient's message and records the outcome.

    Shared by both the manual "Send Campaign" trigger (as a FastAPI
    BackgroundTask, so a large audience doesn't block the HTTP request)
    and the automatic scheduler — same send path, same recorded outcome
    either way.
    """
    phones = normalize_phone_list(phones)
    campaign = campaigns.find_one(
        {"campaign_id": campaign_id},
        {"template_name": 1, "template_id": 1, "masterclass_nudge_enabled": 1},
    ) or {}
    masterclass_nudge_enabled = bool(campaign.get("masterclass_nudge_enabled"))
    template_name = campaign.get("template_name") or template_id
    content = _template_chat_content(template_id, template_name)

    for phone in phones:
        try:
            rsp = send_template_message(phone, template_id, image_url=image_url)
            set_campaign_recipient_sent(
                campaign_id,
                phone,
                rsp["message_id"],
                rsp["success"],
                error=rsp.get("error"),
            )
            if rsp.get("success") and masterclass_nudge_enabled:
                schedule_campaign_mc_nudge(
                    campaign_id,
                    phone,
                    datetime.now(timezone.utc),
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
        except Exception as e:
            logger.error(
                "Error sending campaign message",
                extra={"campaign_id": campaign_id, "phone": phone, "error": str(e)},
            )
            set_campaign_recipient_sent(campaign_id, phone, None, False, error=str(e))
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
