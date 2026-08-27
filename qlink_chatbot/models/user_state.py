from enum import Enum


class UserState(Enum):
    """All user states."""

    SEND_REGISTRATION_FLOW = "send_registration_flow"
    REGISTRATION_DONE = "registration_done"
    SENT_SERVICE_LIST = "sent_service_list"
    SENT_BOOK_SPOT_FLOW = "sent_book_spot_flow"
    SENT_SPEAKER_REGISTRATION = "sent_speaker_registration"
    SEND_NOTIFY_FLOW = "send_notify_flow"
    SEND_CALLCHIMP_CALL = "send_callchimp_call"
    SEND_PRODUCT_DETAILS_FLOW = "send_product_details_flow"
    SEND_PRODUCT_LIST = "send_product_list"
    SEND_PROFESSIONAL_DETAILS_FLOW = "send_professional_details_flow"
    SEND_PROFESSIONAL_LIST = "send_professional_list"
    SEND_PAYMENT_LINK = "send_payment_link"
    SEND_RESERVATION_FLOW = "sent_reservation_flow"
    SEND_RESERVATION_DETAILS_FLOW = "sent_reservation_details_flow"
    SEND_RESERVATION_LIST = "sent_reservation_list"
    SEND_CANCEL_RESERVATION_FLOW = "sent_cancel_reservation_flow"
    SEND_CUSTOM_FLOW = "send_custom_flow"
    SEND_CUSTOM_LIST = "send_custom_list"
    SEND_FEEDBACK_FORM = "sent_feedback_form"
