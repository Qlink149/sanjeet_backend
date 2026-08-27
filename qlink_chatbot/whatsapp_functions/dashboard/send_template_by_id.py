import json

import httpx

from qlink_chatbot.constants import GUPSHUP_SOURCE
from qlink_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_app_name,
    gupshup_token,
)
from qlink_chatbot.utils.logger_config import logger


def send_template_message(
    phone_number: str, template_id: str, image_url: str | None = None
) -> dict:
    """Sends a template message to a phone number.

    `image_url` must be a real, publicly-fetchable URL — required for
    templates with an IMAGE header. Without it, WhatsApp accepts the send
    but silently never delivers it (header format mismatch).

    Returns {"success": bool, "message_id": str | None}.
    """
    logger.info(
        "Sending template message",
        extra={"phone_number": phone_number, "image_url": image_url},
    )

    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/template/msg"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "token": gupshup_token,
    }

    data = {
        "source": GUPSHUP_SOURCE,
        "destination": phone_number,
        "src.name": gupshup_app_name,
        "template": json.dumps(
            {
                "id": template_id,
                "params": [],
            }
        ),
    }

    if image_url:
        data["message"] = json.dumps({"type": "image", "image": {"link": image_url}})

    try:
        response = httpx.post(
            url,
            headers=headers,
            data=data,
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
        payload = response.json()

        # ---- SUCCESS ----
        if response.status_code == 200 and payload.get("status") == "submitted":
            message_id = payload.get("messageId")
            logger.info(
                "Template message sent",
                extra={
                    "phone_number": phone_number,
                    "message_id": message_id,
                },
            )
            return {"success": True, "message_id": message_id}
        else:
            error_msg = payload.get("message") or payload.get("status") or "Send failed"
            logger.error(
                "Template message rejected by Gupshup",
                extra={
                    "phone_number": phone_number,
                    "template_id": template_id,
                    "response": payload,
                },
            )
            return {"success": False, "message_id": None, "error": error_msg}

    except Exception as e:
        logger.error(
            "Error sending template message",
            extra={
                "phone_number": phone_number,
                "template_id": template_id,
                "error": str(e),
            },
        )
        raise