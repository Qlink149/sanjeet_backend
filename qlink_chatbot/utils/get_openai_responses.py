from openai import OpenAI

from qlink_chatbot.utils.env_load import openai_api_key
from qlink_chatbot.utils.logger_config import logger


async def get_openai_responses(
    agent_name: str,
    model: str,
    instruction: str,
    messages,
    output_format=None,
    temperature: float = 0.0,
):
    """Asynchronously sends a request to OpenAI's API and returns the response."""
    logger.info(
        "Request recieved from agent with model and messages",
        extra={
            "agent_name": agent_name,
            "model": model,
            "messages": messages,
        },
    )
    async_client = OpenAI(api_key=openai_api_key)
    try:
        if output_format:
            response = async_client.responses.create(
                model=model,
                input=messages,
                instructions=instruction,
                temperature=temperature,
                text=output_format,
            )
        else:
            response = async_client.responses.create(
                model=model,
                input=messages,
                instructions=instruction,
                temperature=temperature,
            )
        logger.info(
            "Response from OpenAI for agent",
            extra={"response": response, "agent_name": agent_name},
        )
        return response.output[0].content[0].text
    except Exception as e:
        logger.error(
            "Error in getting response from OpenAI", extra={"exception": e}
        )
        raise e
