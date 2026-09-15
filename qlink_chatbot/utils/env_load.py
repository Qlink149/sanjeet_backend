import os

from dotenv import load_dotenv

load_dotenv()

openai_api_key = os.environ.get("OPENAI_API_KEY")
mongo_uri = os.environ.get("MONGO_URI")
gupshup_app_id = os.environ.get("GUPSHUP_APP_ID")
gupshup_token = os.environ.get("GUPSHUP_TOKEN")
gupshup_app_name = os.environ.get("GUPSHUP_APP_NAME")
gupshup_api_key = os.environ.get("GUPSHUP_API_KEY")
gupshup_source = os.environ.get("GUPSHUP_SOURCE")
# Public URL of THIS bot (FastAPI), not the Vercel dashboard. Gupshup
# fetches template header images from {PUBLIC_BASE_URL}/dashboard/template-image/<id>.
# Leave empty until sanjeet_bot is deployed — do not point at FSAI's host.
public_base_url = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
pinecone_api = os.environ.get("PINECONE_API")
pinecone_namespace = os.environ.get("PINECONE_NAMESPACE")
webhook_api = os.environ.get("WEBHOOK_API")

google_private_key_id = os.environ.get("GOOGLE_PRIVATE_KEY_ID")

qlink_app_id = os.environ.get("QLINK_APP_ID")
qlink_app_name = os.environ.get("QLINK_APP_NAME")
qlink_token = os.environ.get("QLINK_TOKEN")

username = os.environ.get("LOGIN_USERNAME")
password = os.environ.get("LOGIN_PASS")

futwork_webhook = os.environ.get("FUTWORKS_API")
futwork_pacific_agent = os.environ.get("FUTWORK_PACIFIC_AGENT")

fist_awards_template_id = os.environ.get("FIST_AWARDS_TEMPLATE_ID")
fist_awards_template_id_v2 = os.environ.get("FIST_AWARDS_TEMPLATE_ID_V2")
fist_awards_template_id_v3 = os.environ.get("FIST_AWARDS_TEMPLATE_ID_V3")
fist_awards_template_id_v4 = os.environ.get("FIST_AWARDS_TEMPLATE_ID_V4")

# Utility template sent after Money Ceiling Quiz details submit (`access_yes`).
quiz_submit_template_id = (
    os.environ.get("QUIZ_SUBMIT_TEMPLATE_ID")
    or "bb2a2c86-87f0-4201-a108-d55e38dc3da6"
)

# 24h broadcast masterclass reminder — approved masterclass_link_reminder Utility.
broadcast_masterclass_reminder_template_id = os.environ.get(
    "BROADCAST_MASTERCLASS_REMINDER_TEMPLATE_ID",
    "5f8f530a-1668-4da7-8c49-a9e67c3462ae",
)
broadcast_masterclass_reminder_template_ids = os.environ.get(
    "BROADCAST_MASTERCLASS_REMINDER_TEMPLATE_IDS", ""
)