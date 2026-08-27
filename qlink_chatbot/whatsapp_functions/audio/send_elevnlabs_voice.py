import httpx
from elevenlabs import ElevenLabs
from imagekitio import ImageKit

from qlink_chatbot.constants import GUPSHUP_SOURCE
from qlink_chatbot.utils.env_load import (
    eleven_api_key,
    gupshup_api_key,
    gupshup_app_name,
    imagekit_private_key,
    imagekit_public_key,
    imagekit_url,
)
from qlink_chatbot.utils.logger_config import logger

# ------------------ CONFIG ------------------
ELEVEN_API_KEY = eleven_api_key

IMAGEKIT_PUBLIC_KEY = imagekit_public_key
IMAGEKIT_PRIVATE_KEY = imagekit_private_key
IMAGEKIT_URL = imagekit_url


# Clients
eleven_client = ElevenLabs(api_key=ELEVEN_API_KEY)
imagekit = ImageKit(
    private_key=IMAGEKIT_PRIVATE_KEY,
    public_key=IMAGEKIT_PUBLIC_KEY,
    url_endpoint=IMAGEKIT_URL,
)


# ------------------ FUNCTIONS ------------------
def generate_audio_bytes(text: str) -> bytes:
    """Generate audio from text (bytes)."""
    try:
        audio = eleven_client.text_to_speech.convert(
            voice_id="aGb0TwKthRLQTPThYRqI",
            output_format="mp3_44100_128",
            text=text,
            model_id="eleven_multilingual_v2",
        )
        return b"".join(audio)
    except Exception as e:
        logger.error("Error generating audio", extra={"error": str(e)})
        raise e


def upload_audio_to_imagekit(
    audio_bytes: bytes, file_name: str = "voice.mp3"
) -> str:
    """Upload audio bytes to ImageKit and return public URL."""
    try:
        upload = imagekit.upload(
            file=audio_bytes,
            file_name=file_name,
            options={"folder": "/voice-messages/"},
        )
        return upload.response_metadata.raw["url"]
    except Exception as e:
        logger.error("Error uploading to ImageKit", extra={"error": str(e)})
        raise e


def send_gupshup_voice_message(phone_number: str, audio_url: str):
    """Send voice message to WhatsApp via Gupshup API."""
    try:
        url = "https://api.gupshup.io/wa/api/v1/msg"
        headers = {
            "apikey": gupshup_api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        payload = {
            "channel": "whatsapp",
            "source": GUPSHUP_SOURCE,
            "destination": phone_number,
            "message": f'{{"type":"audio","url":"{audio_url}"}}',
            "src.name": gupshup_app_name,
        }

        response = httpx.post(url, data=payload, headers=headers, timeout=30.0)
        logger.info(
            "Voice message sent",
            extra={"phone_number": phone_number, "response": response.json()},
        )
        return response.json()
    except Exception as e:
        logger.error(
            "Error sending voice message",
            extra={"phone_number": phone_number, "error": str(e)},
        )
        raise e


def process_and_send_voice(phone_number: str, text: str):
    """Full flow: text → audio → ImageKit → Gupshup."""
    audio_bytes = generate_audio_bytes(text)
    audio_url = upload_audio_to_imagekit(audio_bytes)
    return send_gupshup_voice_message(phone_number, audio_url)


# ------------------ USAGE ------------------
# response = process_and_send_voice("+91xxxxxxxxxx", "Hello bro, testing voice note")
# print(response)
