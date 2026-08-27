import json

import httpx

from qlink_chatbot.constants import GUPSHUP_SOURCE, QLINK_SOURCE
from qlink_chatbot.utils.env_load import (
    gupshup_api_key,
    gupshup_app_name,
    qlink_app_name,
)
from qlink_chatbot.utils.logger_config import logger


def send_text_message(phone_number: str, bot_response: str):
    """Sends a text message to a phone number."""
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

    # Modify the data to match the cURL request format
    data = {
        "source": source,
        "destination": destination,
        "message": json.dumps(bot_response),
        "src.name": app_name,
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        logger.info(
            "Response",
            extra={
                "phone_number": phone_number,
                "response": response.json(),
            },
        )
    except Exception as e:
        logger.error(
            "Error in sending text message",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
