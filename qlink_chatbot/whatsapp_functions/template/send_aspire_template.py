import httpx

from qlink_chatbot.utils.logger_config import logger


def send_aspire_template(phone_number: str):
    """Sends a template message tos a phone number."""
    logger.info(
        "Sending text message to phone number with message",
        extra={"phone_number": phone_number},
    )
    destination = f"{phone_number}"
    url = "https://partner.gupshup.io/partner/app/daf79045-73c8-42ed-ac21-e9754cdaa3cd/template/msg"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "content-type": "application/x-www-form-urlencoded",
        "token": "sk_be9423d9909348fc83857ab77b476ae4",
    }

    # Modify the data to match the cURL request format
    data = {
        "source": "919549549339",
        "destination": destination,
        "src.name": "Qliink",
        "template": '{"id": "aea565a5-b77a-46ea-93a2-94103b3f1aaa", "params": []}',  # aspire finance # noqa
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
