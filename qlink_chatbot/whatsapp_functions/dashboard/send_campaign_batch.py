from qlink_chatbot.database.db_utils import set_campaign_recipient_sent
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.whatsapp_functions.dashboard.send_template_by_id import (
    send_template_message,
)


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
        except Exception as e:
            logger.error(
                "Error sending campaign message",
                extra={"campaign_id": campaign_id, "phone": phone, "error": str(e)},
            )
            set_campaign_recipient_sent(campaign_id, phone, None, False, error=str(e))
