import httpx

from qlink_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_token,
)
from qlink_chatbot.utils.logger_config import logger


def send_day1_quiz_flow(phone_number: str):
    """Sends a quiz flow to a phone number."""
    logger.info(
        "Sending quiz flow to phone number",
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
            "header": {"type": "text", "text": "Question"},
            "body": {
                "text": "Please answer the quiz."
            },
            "footer": {"text": "Managed by Sanjeet."},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_token": "2338473189912684",
                    "flow_id": "2338473189912684",
                    "flow_message_version": "3",
                    "flow_action": "navigate",
                    "flow_cta": "Ask Question",
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
        logger.error("Error in sending quiz flow", extra={"error": e})
        raise e
    

def send_day2_quiz_flow(phone_number: str):
    """Sends a quiz flow to a phone number."""
    logger.info(
        "Sending quiz flow to phone number",
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
            "header": {"type": "text", "text": "Question"},
            "body": {
                "text": "Please answer the quiz."
            },
            "footer": {"text": "Managed by Sanjeet."},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_token": "1545494639860594",
                    "flow_id": "1545494639860594",
                    "flow_message_version": "3",
                    "flow_action": "navigate",
                    "flow_cta": "Ask Question",
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
        logger.error("Error in sending quiz flow", extra={"error": e})
        raise e
    


def send_day3_quiz_flow(phone_number: str):
    """Sends a quiz flow to a phone number."""
    logger.info(
        "Sending quiz flow to phone number",
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
            "header": {"type": "text", "text": "Question"},
            "body": {
                "text": "Please answer the quiz."
            },
            "footer": {"text": "Managed by Sanjeet."},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_token": "1300595032122020",
                    "flow_id": "1300595032122020",
                    "flow_message_version": "3",
                    "flow_action": "navigate",
                    "flow_cta": "Ask Question",
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
        logger.error("Error in sending quiz flow", extra={"error": e})
        raise e
