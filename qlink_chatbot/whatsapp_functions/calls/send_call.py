
import httpx

from qlink_chatbot.utils.env_load import futwork_pacific_agent, futwork_webhook
from qlink_chatbot.utils.logger_config import logger


def send_call(phone_number: str):
    """Sends a template call to a phone number."""
    logger.info(
        "Sending template call.",
        extra={"phone_number": phone_number},
    )

    url = f"https://platform.futwork.ai/api/agents/{futwork_pacific_agent}/call"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "x-api-key": futwork_webhook,
    }

    data = {
        "mobile": f"+{phone_number}",
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        payload = response.json()

        # ---- SUCCESS ----
        if payload.get("success") == True:
            logger.info(
                "Template message sent",
                extra={
                    "phone_number": phone_number,
                    "payload": payload,
                },
            )
            return True
        else:
            return False

    except Exception as e:
        logger.error(
            "Error sending template call.",
            extra={
                "phone_number": phone_number,
                "error": str(e),
            },
        )
        raise