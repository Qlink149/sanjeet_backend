from enum import Enum


class ListIds(Enum):
    """All list ids."""

    SERVICE_LIST_ID = "service_list"


class QuickReplyId(Enum):
    """All quick reply ids."""

    EVENT_TYPE = "event_type"


class FLowId(Enum):
    """All flow ids."""

    BOOK_SPOT_FLOW_ID = "1244838263732533"
    INTELLIGENT_EVENT_REGISTRATION_FLOW_ID = "1262293402565331"
    MAIN_EVENT_REGISTRATION_FLOW_ID = "1364918277991593"
    SPEAKER_REGISTRATION = "4119093268366665"
    QUIZ_FLOW_ID = "2001925777346025"

    SITE_VISIT = "869740435673660"
    GIT_SITE_VISIT = "685081584337677"
