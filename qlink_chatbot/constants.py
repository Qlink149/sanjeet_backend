# ruff:noqa:E501
from qlink_chatbot.utils.env_load import gupshup_source

OPENAI_MODEL = "gpt-4o-mini"
GUPSHUP_SOURCE = gupshup_source
QLINK_SOURCE = "919549549339"
GUPSHUP_URL = "https://api.gupshup.io/wa/api/v1/msg"
EMBEDDING_MODEL = "text-embedding-3-small"
SKIP_FIELDS_LOGGER = (
    "args",
    "exc_info",
    "exc_text",
    "stack_info",
    "msg",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "name",
    "lineno",
    "funcName",
)

AWAZ_ROUTE = "https://api.awaz.ai/v1"
AWAZ_SOURCE = "+12315005708"
CALLCHIMP_ROUTE = "https://api.callchimp.ai/v1"

MASTERCLASS_TRIGGER_PHRASES = (
    "send me the link",
    "im ready for the masterclass",
    "i'm ready for the masterclass",
)
# Meeting URL lives on the Active masterclass in Mongo (dashboard-owned).
# Keep these phrases in sync with the quiz WhatsApp CTA prefill.
# Exact inbound "Yes" (Utility QR after quiz) is handled separately in
# inbound_matches_masterclass_trigger — do not add "yes" as a substring phrase.
MASTERCLASS_NO_ACTIVE_REPLY = (
    "Thanks for your interest! There isn't a live masterclass link right now. "
    "Sanjeet will share one soon."
)
