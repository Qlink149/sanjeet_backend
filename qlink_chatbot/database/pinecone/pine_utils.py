import random
import string

from pinecone import Pinecone

from qlink_chatbot.utils.env_load import pinecone_api, pinecone_namespace

pine_client = Pinecone(api_key=pinecone_api)
index = pine_client.Index("demo")


def _generate_id(length=8):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


async def upsert_data(vector: list, text: str, company: str) -> None:
    """Pinecone Util Function to append new vector to the db."""
    try:
        vector_id = f"{company}#{_generate_id()}"
        index.upsert(
            namespace=pinecone_namespace,
            vectors=[
                {
                    "id": vector_id,
                    "values": vector,
                    "metadata": {
                        "text": text,
                        "company": company,
                    },
                }
            ],
        )

    except Exception as e:
        raise e


async def fetch_data(vector: list, top_k: int = 3) -> list:
    """Pinecone util function to perform similarity search in the db."""
    try:
        result = index.query(
            namespace=pinecone_namespace,
            vector=vector,
            top_k=top_k,
            include_metadata=True,
        )

        return result.get("matches", [])

    except Exception as e:
        raise e


async def delete_user_data(file_name: str) -> None:
    """Pinecone util function to delete all vector of user."""
    try:
        for ids in index.list(
            prefix=f"{file_name}#", namespace=pinecone_namespace
        ):
            index.delete(ids=ids, namespace=pinecone_namespace)

    except Exception as e:
        raise e
