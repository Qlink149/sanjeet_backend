import json

import httpx

from qlink_chatbot.constants import GUPSHUP_SOURCE
from qlink_chatbot.models.enums import ListIds
from qlink_chatbot.utils.env_load import (
    gupshup_api_key,
    gupshup_app_name,
)
from qlink_chatbot.utils.logger_config import logger


def send_service_list(phone_number):
    """Send a list message to a phone number."""
    url = "https://api.gupshup.io/wa/api/v1/msg"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "apikey": gupshup_api_key,
    }

    messages = (
        "Hello 😊\n"
        "Welcome to the PACC AI Experience! 🤖\n\n"
        "Welcome to PACC! We are thrilled to introduce your personal AI Event Assistant for the conference. Think of this bot as your 24/7 friend and guide for everything related to the event.\n\n" # noqa
        "To continue, please select one of the following options:\n"
    )

    message_json = json.dumps(
        {
            "type": "list",
            "title": "",
            "body": messages,
            "footer": "Managed by Sanjeet",
            "msgid": f"{ListIds.SERVICE_LIST_ID.value}",
            "globalButtons": [{"type": "text", "title": "Options"}],
            "items": [
                {
                    "title": "Options",
                    "subtitle": "option Subtitle",
                    "options": [
                        {
                            "type": "text",
                            "title": "Agenda",
                            "description": "Full session details & timings.",
                            "postbackText": "register postback payload",
                        },
                        {
                            "type": "text",
                            "title": "Exhibitors",
                            "description": "List of Fire & Security brands and booth locations.",
                            "postbackText": "register postback payload",
                        },
                        {
                            "type": "text",
                            "title": "Navigation",
                            "description": "Floor plans and directions.",
                            "postbackText": "register postback payload",
                        },
                        {
                            "type": "text",
                            "title": "Other",
                            "description": "Ask any query.",
                            "postbackText": "register postback payload",
                        },
                    ],
                }
            ],
        }
    )

    data = {
        "source": GUPSHUP_SOURCE,
        "destination": f"{phone_number}",
        "src.name": gupshup_app_name,
        "message": message_json,
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        logger.info(
            "Response from Gupshup API for sending service list",
            extra={"response": response.json()},
        )
    except Exception as e:
        logger.error("Error in sending list", extra={"error": e})
