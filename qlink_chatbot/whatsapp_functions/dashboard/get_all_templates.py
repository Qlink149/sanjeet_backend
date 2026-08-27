import time

import httpx

from qlink_chatbot.utils.env_load import gupshup_app_id, gupshup_token
from qlink_chatbot.utils.logger_config import logger

_CACHE: dict = {"ts": 0.0, "templates": None}
_CACHE_TTL_SEC = 60
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def get_all_templates(force: bool = False):
    """Get all templates. Empty list is valid. Never block forever."""
    now = time.monotonic()
    if (
        not force
        and _CACHE["templates"] is not None
        and now - _CACHE["ts"] < _CACHE_TTL_SEC
    ):
        return _CACHE["templates"]

    logger.info("Get All Templates")
    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/templates"
    headers = {
        "Authorization": f"{gupshup_token}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.get(url, headers=headers, timeout=_TIMEOUT)
        data = response.json()

        if data.get("status") == "success":
            templates = data.get("templates") or []
            _CACHE["templates"] = templates
            _CACHE["ts"] = time.monotonic()
            return templates
        logger.info("Response error for all templates", extra={"response": data})
        return None

    except httpx.TimeoutException as e:
        logger.warning("Gupshup templates timed out", extra={"error": str(e)})
        return None
    except Exception as e:
        logger.error("Error fetching templates from Gupshup", extra={"error": e})
        raise e
