import json
import os
from datetime import datetime

import gspread
import pytz
from google.oauth2.service_account import Credentials

from qlink_chatbot.utils.logger_config import logger

IST = pytz.timezone("Asia/Kolkata")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
SHEET_NAME = os.environ.get("GOOGLE_SHEET_NAME", "Sheet1")


def _sheet():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw or not SHEET_ID:
        return None
    info = json.loads(raw)
    credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    client = gspread.authorize(credentials)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)


def add_data_to_sheet(data: dict):
    """Append a new lead entry to Google Sheet."""
    try:
        sheet = _sheet()
        if sheet is None:
            logger.warning(
                "Skipping sheet append; set GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID"
            )
            return
        row = [
            datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            data.get("username", ""),
            data.get("question", ""),
            data.get("wa_phone", ""),
        ]
        sheet.append_row(row)
        logger.info("Lead added to Google Sheet", extra={"lead": row})
    except Exception as e:
        logger.error("Failed to add lead to Google Sheet", extra={"error": str(e)})
        raise e
