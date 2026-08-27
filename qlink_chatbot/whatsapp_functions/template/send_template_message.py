import httpx

from qlink_chatbot.constants import GUPSHUP_SOURCE
from qlink_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_app_name,
    gupshup_token,
)
from qlink_chatbot.utils.logger_config import logger


def send_template_message(phone_number: str):
    """Sends a template message tos a phone number."""
    logger.info(
        "Sending text message to phone number with message",
        extra={"phone_number": phone_number},
    )
    destination = f"{phone_number}"
    url = (
        f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/template/msg"
    )

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "content-type": "application/x-www-form-urlencoded",
        "token": gupshup_token,
    }

    # Modify the data to match the cURL request format
    data = {
        "source": GUPSHUP_SOURCE,
        "destination": destination,
        "src.name": gupshup_app_name,
        "template": '{"id": "ed70665a-1d66-47c2-8ae7-122efcbf4d88", "params": []}',  # hirandani
        # "template": '{"id": "b5c80b2e-7780-423f-b5e2-6b8f42ad20f0", "params": []}',  # ticket.ca
        "message": '{ "type": "text", "text": "Here is your ticket information from Tickets.ca" }',
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
            "Error in sending template message",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
