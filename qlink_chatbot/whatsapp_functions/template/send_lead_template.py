import json

import httpx

from qlink_chatbot.constants import GUPSHUP_SOURCE
from qlink_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_app_name,
    gupshup_token,
)
from qlink_chatbot.utils.logger_config import logger


def send_lead_template_message(phone_numbers: list):
    """Sends a template message to a list of phone numbers."""
    for phone_number in phone_numbers:
        try:
            logger.info(
                "Sending text message to phone number with message",
                extra={"phone_number": phone_number},
            )
            destination = f"{phone_number}"
            url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/template/msg"

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "content-type": "application/x-www-form-urlencoded",
                "token": gupshup_token,
            }

            data = {
                "source": GUPSHUP_SOURCE,
                "destination": destination,
                "src.name": gupshup_app_name,
                "template": json.dumps(
                    {
                        "id": "b9560820-21d5-4d51-80f6-8da59a725322",
                    }
                ),
                "message": '{ "type": "text", "text": "Here is your ticket information from Tickets.ca" }',  # noqa
            }

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
            continue



def git_send_lead_template_message(phone_numbers: list):
    """Sends a template message to a list of phone numbers."""
    for phone_number in phone_numbers:
        try:
            logger.info(
                "Sending text message to phone number with message",
                extra={"phone_number": phone_number},
            )
            destination = f"{phone_number}"
            url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/template/msg"

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "content-type": "application/x-www-form-urlencoded",
                "token": gupshup_token,
            }

            data = {
                "source": GUPSHUP_SOURCE,
                "destination": destination,
                "src.name": gupshup_app_name,
                "template": json.dumps(
                    {
                        "id": "b9560820-21d5-4d51-80f6-8da59a725322",
                    }
                ),
                "message": '{ "type": "text", "text": "Here is your ticket information from Tickets.ca" }',  # noqa
            }

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
            continue














# {
#   "status": "success",
#   "template": {
#     "appId": "daf79045-73c8-42ed-ac21-e9754cdaa3cd",
#     "buttonSupported": "URL",
#     "category": "UTILITY",
#     "containerMeta": "{\"appId\":\"daf79045-73c8-42ed-ac21-e9754cdaa3cd\",\"data\":\"A new appointment booking has been received. Please check the Google Sheet for details.\",\"buttons\":[{\"type\":\"URL\",\"text\":\"Check Sheet\",\"url\":\"https://docs.google.com/spreadsheets/d/1fM3hiia27nH_3jLgScJ4yceAd_5k79tfIMTytzgqwis/edit?gid=0#gid=0\",\"example\":[\"https://docs.google.com/spreadsheets/d/1fM3hiia27nH_3jLgScJ4yceAd_5k79tfIMTytzgqwis/edit?gid=0#gid=0\"]}],\"header\":\"Dear Team,\",\"footer\":\"to unsubscribe, reply STOP\",\"sampleText\":\"A new appointment booking has been received. Please check the Google Sheet for details.\",\"sampleHeader\":\"Dear Team,\",\"enableSample\":true,\"editTemplate\":false,\"allowTemplateCategoryChange\":false,\"addSecurityRecommendation\":false,\"isCPR\":false,\"cpr\":false}",
#     "createdOn": 1762789054285,
#     "data": "Dear Team,\nA new appointment booking has been received. Please check the Google Sheet for details.\nto unsubscribe, reply STOP | [Check Sheet,https://docs.google.com/spreadsheets/d/1fM3hiia27nH_3jLgScJ4yceAd_5k79tfIMTytzgqwis/edit?gid=0#gid=0]",
#     "elementName": "pims_registation2",
#     "id": "a4b2afbb-7f09-42a0-861f-f6885899262e",
#     "languageCode": "en_US",
#     "languagePolicy": "deterministic",
#     "meta": "{\"example\":\"A new appointment booking has been received. Please check the Google Sheet for details.\"}",
#     "modifiedOn": 1762789054285,
#     "namespace": "9140c149_a16b_4896_aaf7_dc863801b5bb",
#     "priority": 2,
#     "quality": "UNKNOWN",
#     "retry": 0,
#     "stage": "NONE",
#     "status": "PENDING",
#     "templateType": "TEXT",
#     "vertical": "Internal_vertical",
#     "wabaId": "421729091033235"
#   }
# }
