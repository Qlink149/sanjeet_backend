from qlink_chatbot.whatsapp_functions.cta.send_cta import send_cta_url
from qlink_chatbot.whatsapp_functions.media.send_audio_message import (
    send_audio_message,
)
from qlink_chatbot.whatsapp_functions.media.send_document_message import (
    send_file_message,
)
from qlink_chatbot.whatsapp_functions.media.send_image_message import (
    send_image_message,
)
from qlink_chatbot.whatsapp_functions.quick_reply.send_quick_reply import (
    send_quickreply,
)
from qlink_chatbot.whatsapp_functions.send_text_message import send_text_message


class ResponseManager:
    """Sends bot responses for remaining WhatsApp types (text, media, CTA)."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers = {}
            cls._instance._register_default_handlers()
        return cls._instance

    def _register_default_handlers(self):
        self.register_handler("text", self._handle_text)
        self.register_handler("media", self._handle_media)
        self.register_handler("quickreply", self._handle_quick_reply)
        self.register_handler("cta_url", self._handle_url)

    def register_handler(self, response_type, handler):
        self._handlers[response_type] = handler

    def handle_responses(self, data):
        bot_responses = data.get("bot_response", [])
        phone_number = data["phone_number"]
        for response in bot_responses:
            response_type = response.get("type")
            handler = self._handlers.get(response_type)
            if handler:
                handler(phone_number=phone_number, bot_response=response)
            else:
                raise ValueError(
                    f"No handler registered for response type: {response_type}"
                )

    def _handle_text(self, phone_number, bot_response):
        send_text_message(phone_number=phone_number, bot_response=bot_response)

    def _handle_quick_reply(self, phone_number, bot_response):
        send_quickreply(phone_number=phone_number, bot_response=bot_response)

    def _handle_url(self, phone_number, bot_response):
        send_cta_url(phone_number=phone_number, bot_response=bot_response)

    def _handle_media(self, phone_number, bot_response):
        media_type = bot_response["media_type"]
        if media_type == "image":
            send_image_message(phone_number=phone_number, bot_response=bot_response)
        elif media_type == "doc":
            send_file_message(phone_number=phone_number, bot_response=bot_response)
        elif media_type == "audio":
            send_audio_message(phone_number=phone_number, bot_response=bot_response)
        else:
            raise ValueError(f"Unknown media type: {media_type}")
