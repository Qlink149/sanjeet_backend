import json

import httpx

from qlink_chatbot.constants import GUPSHUP_SOURCE, QLINK_SOURCE
from qlink_chatbot.utils.env_load import (
    gupshup_api_key,
    gupshup_app_name,
    qlink_app_name,
)
from qlink_chatbot.utils.logger_config import logger


def send_text_message(phone_number: str, bot_response: dict) -> dict:
    """Sends a text message to a phone number.

    Returns ``{"success": bool, "message_id": str | None, "error": str | None}``.
    """
    logger.info(
        "Sending text message to phone number with message",
        extra={"phone_number": phone_number, "bot_response": bot_response},
    )

    if bot_response.get("source", "pims") == "git":
        source = QLINK_SOURCE
        app_name = qlink_app_name
    else:
        source = GUPSHUP_SOURCE
        app_name = gupshup_app_name

    destination = f"{phone_number}"
    url = "https://api.gupshup.io/wa/api/v1/msg"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "apikey": gupshup_api_key,
    }

    payload = {
        "type": "text",
        "text": bot_response.get("text") or "",
    }

    data = {
        "source": source,
        "destination": destination,
        "message": json.dumps(payload),
        "src.name": app_name,
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        body = {}
        try:
            body = response.json()
        except Exception:
            body = {}
        logger.info(
            "Response",
            extra={
                "phone_number": phone_number,
                "response": body,
            },
        )
        message_id = body.get("messageId") or body.get("message_id")
        status = (body.get("status") or "").lower()
        success = response.status_code == 200 and (
            status in {"submitted", "success"} or bool(message_id)
        )
        error_msg = None if success else (
            body.get("message") or body.get("status") or f"HTTP {response.status_code}"
        )
        return {
            "success": success,
            "message_id": message_id,
            "error": error_msg,
        }
    except Exception as e:
        logger.error(
            "Error in sending text message",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
