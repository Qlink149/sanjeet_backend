import httpx

from qlink_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_token
)
from qlink_chatbot.utils.logger_config import logger

def send_session_feedback_flow(phone_number: str, bot_response):
    """Sends a session feedback flow to a phone number."""
    logger.info(
        "Sending session feedback flow to phone number",
        extra={"phone_number": phone_number},
    )
    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/v3/message"
    headers = {
        "Authorization": f"{gupshup_token}",
        "Content-Type": "application/json",
    }
    data = {
        "recipient_type": "individual",
        "messaging_product": "whatsapp",
        "to": f"{phone_number}",
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "header": {
                "type": "text", 
                "text": f"Thank You for attending."
                },
            "body": {
                "text": f"Please share your valuable feedback on *{bot_response.get("session_name")}* for improvements."
            },
            "footer": {"text": "Managed by PACC Sanjeet."},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_token": bot_response.get("flow_id"),
                    "flow_id":bot_response.get("flow_id"),
                    "flow_message_version": "3",
                    "flow_action": "navigate",
                    "flow_cta": "Feedback",
                    "flow_action_payload": {
                        "screen": "RECOMMEND",
                        "data": {
                            "Full name": "Vaibhav Verma",
                            "Brand name": "Qlink",
                            "Email": "vaibhav@gmail.com",
                            "Whatsapp Number": "+919999999999",
                        },
                    },
                },
            },
        },
    }

    try:
        response = httpx.post(url, headers=headers, json=data)
        logger.info("Response", extra={"response": response.json()})
    except Exception as e:
        logger.error("Error in sending session feedback flow", extra={"error": e})
        raise e