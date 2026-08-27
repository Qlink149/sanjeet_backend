import httpx

from qlink_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_token,
    qlink_app_id,
    qlink_token,
)
from qlink_chatbot.utils.logger_config import logger


def send_site_visit_flow(phone_number: str):
    """Sends a site visit flow to a phone number."""
    logger.info(
        "Sending site visit flow to phone number",
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
                "text": "Please fill in your query."
            },
            "footer": {"text": "Managed by Sanjeet."},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_token": "869740435673660",
                    "flow_id": "869740435673660",
                    "flow_message_version": "3",
                    "flow_action": "navigate",
                    "flow_cta": "Ask Question",
                    "flow_action_payload": {
                        "screen": "WELCOME_SCREEN",
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
        logger.error("Error in sending spot booking flow", extra={"error": e})
        raise e
    
def send_git_site_visit_flow(phone_number: str):
    """Sends a site visit flow to a phone number."""
    logger.info(
        "Sending site visit flow to phone number",
        extra={"phone_number": phone_number},
    )
    url = f"https://partner.gupshup.io/partner/app/{qlink_app_id}/v3/message"
    headers = {
        "Authorization": f"{qlink_token}",
        "Content-Type": "application/json",
    }
    data = {
        "recipient_type": "individual",
        "messaging_product": "whatsapp",
        "to": f"{phone_number}",
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "header": {"type": "text", "text": "Book Appointment"},
            "body": {
                "text": "Please fill in your info to book an appointment."
            },
            "footer": {"text": "Managed by Geetanjali Hospital."},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_token": "685081584337677",
                    "flow_id": "685081584337677",
                    "flow_message_version": "3",
                    "flow_action": "navigate",
                    "flow_cta": "Enquire Now",
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
        logger.error("Error in sending spot booking flow", extra={"error": e})
        raise e
