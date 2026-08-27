import json

import httpx

from qlink_chatbot.utils.logger_config import logger


def post_lead(data: dict) -> dict:
    """Send lead data to Sperto API.

    Args:
        data (dict): Registration data with keys like name, phone_number, email, etc.

    Returns:
        dict: API response (JSON).
    """
    url = "https://net4hc.sperto.co.in/_api/api_post_lead.php"

    webdata = {
        "lead_category": "O",
        "campaign_key": "20250915040245141429683112985077368c7eb4d9a004073117169",
        "customer_name": data.get("name", ""),
        "mobile1_isd": "91",
        "mobile_no1": data.get("phone_number", ""),
        "email_id1": data.get("email", ""),
        "project_name": data.get("project", ""),
        "address": data.get("address", ""),
        "comments": data.get("comment", ""),
        "configurations": data.get("config", ""),
        "site_visit_date": data.get("site_visit", ""),
    }

    payload = {"webdata": json.dumps(webdata)}

    try:
        with httpx.Client() as client:
            response = client.post(
                url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )
            result = response.json()
            logger.info("Lead posted successfully", extra={"response": result})
            return result
    except Exception as e:
        logger.error("Error posting lead", extra={"error": str(e)})
        return {"status": "error", "message": str(e)}
