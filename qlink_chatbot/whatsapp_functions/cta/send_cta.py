import json

import httpx

from qlink_chatbot.constants import GUPSHUP_SOURCE, GUPSHUP_URL, QLINK_SOURCE
from qlink_chatbot.utils.env_load import (
    gupshup_api_key,
    gupshup_app_name,
    qlink_app_name,
)
from qlink_chatbot.utils.logger_config import logger


def send_cta_url(phone_number, bot_response):
    """Send CTA to the user."""
    logger.info(
        "Sending url cta to phone number",
        extra={"phone_number": phone_number},
    )

    if bot_response.get("source", "pims") == "git":
        source = QLINK_SOURCE
        app_name = qlink_app_name
        footer = "Managed by Geetanjali Hospital."
    else:
        source = GUPSHUP_SOURCE
        app_name = gupshup_app_name
        footer = "Managed by PIMS City Hospital."

    destination = f"{phone_number}"
    url = GUPSHUP_URL

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "apikey": gupshup_api_key,
    }

    data = {
        "message": json.dumps(
            {
                "body": bot_response["text"],
                "type": "cta_url",
                "display_text": bot_response["display_text"],
                "url": bot_response["url"],
                "footer": footer,
            }
        ),
        "source": source,
        "destination": destination,
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
            "Error while sending url cta",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
