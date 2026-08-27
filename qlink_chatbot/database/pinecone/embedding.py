from openai import OpenAI

from qlink_chatbot.constants import EMBEDDING_MODEL
from qlink_chatbot.utils.env_load import openai_api_key

openai_client = OpenAI(api_key=openai_api_key)


def get_embedding(text: str) -> list:
    """Openai text to embedding function."""
    response = openai_client.embeddings.create(
        input=text, model=EMBEDDING_MODEL
    )

    return response.data[0].embedding
