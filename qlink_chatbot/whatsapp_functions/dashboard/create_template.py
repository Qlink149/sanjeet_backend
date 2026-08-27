import httpx

from qlink_chatbot.utils.env_load import gupshup_app_id, gupshup_token
from qlink_chatbot.utils.logger_config import logger


def upload_template_media(file_bytes: bytes, filename: str, content_type: str) -> str:
    """Uploads sample media for a template and returns Gupshup's media handle."""
    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/upload/media"
    headers = {"Authorization": gupshup_token}
    files = {"file": (filename, file_bytes, content_type)}
    data = {"file_type": content_type}

    try:
        response = httpx.post(
            url, headers=headers, files=files, data=data, timeout=60
        )
        payload = response.json()
        handle = payload.get("handleId", {}).get("message")

        if not handle:
            logger.error("Media upload failed", extra={"response": payload})
            raise ValueError(f"Media upload failed: {payload}")

        return handle
    except Exception as e:
        logger.error("Error uploading template media", extra={"error": str(e)})
        raise


def create_template(payload: dict) -> dict:
    """Creates a new WhatsApp template via the Gupshup Partner API."""
    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/templates"
    headers = {
        "Authorization": gupshup_token,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    logger.info(
        "Creating template", extra={"element_name": payload.get("elementName")}
    )

    try:
        response = httpx.post(url, headers=headers, data=payload, timeout=60)
        data = response.json()
        logger.info("Create template response", extra={"response": data})
        return data
    except Exception as e:
        logger.error("Error creating template", extra={"error": str(e)})
        raise
