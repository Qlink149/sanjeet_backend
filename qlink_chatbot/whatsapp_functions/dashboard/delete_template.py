import httpx

from qlink_chatbot.utils.env_load import gupshup_app_id, gupshup_token
from qlink_chatbot.utils.logger_config import logger


def delete_template_by_name(template_name: str):
    """Delete template by name."""
    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/template/{template_name}"
    headers = {
        "Authorization": f"{gupshup_token}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.delete(url, headers=headers, timeout=httpx.Timeout(15.0, connect=5.0))
        data = response.json()

        if data.get("status") == "success":
            return True
        else:
            logger.info("Response error for deleting template", extra={"response": data})
            return False

    except Exception as e:
        logger.error("Error deleteting template", extra={"error": e})
        raise e
    