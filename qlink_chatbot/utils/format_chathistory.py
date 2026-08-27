import json

from qlink_chatbot.utils.logger_config import logger


def format_assistant(assistant_message, phone_number):
    """Format the assistant message to a user assistant way."""
    body = ""
    try:
        for assistant in assistant_message:
            message_type = assistant["type"]

            if message_type == "list":
                body += f"\nSent list - [{assistant['list']}]"
                if "search_results" in assistant:
                    body += "\nSearch results:"
                    for idx, result in enumerate(
                        assistant["search_results"], start=1
                    ):
                        name = result.get("name", "")
                        phone = result.get("phone", "")
                        city = result.get("city", "")
                        state = result.get("state", "")

                        body += f"\n{idx}. Name: {name}, Phone: {phone}, City: {city}, State: {state}"  # noqa

            elif message_type == "flow":
                body += f"\nSent flow - [{assistant['flow']}]"

            elif message_type == "quick_reply":
                body += f"\nSent Quick Reply - [{assistant['msgid']}]: \n{assistant['text']}"

            elif message_type == "text":
                body += f"{assistant['text']}"

            elif message_type == "skip":
                continue

            else:
                body += f"\nSent {message_type} message"

        return body
    except Exception as e:
        logger.exception(
            "formatting assistant message failed",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise e


def format_user(user_message, phone_number):
    """Format the user message to a user assistant way."""
    body = ""
    try:
        msg_type = user_message["type"]
        if msg_type == "text":
            body = f'{user_message["text"]["body"]}'

        elif msg_type == "interactive":
            type = user_message["interactive"]["type"]
            if type == "list_reply":
                title = user_message["interactive"]["list_reply"]["title"]
                body = f"User Selected - [{title}] from list"

            elif type == "nfm_reply":
                response_json = json.loads(
                    user_message["interactive"]["nfm_reply"]["response_json"]
                )
                body = "Flow Reply - "
                for key, value in response_json.items():
                    body += f"\n{key}: {value}"

            elif type == "button_reply":
                title = user_message["interactive"]["button_reply"]["title"]
                body = f"User Selected - [{title}] from quick reply"

        return body
    except Exception as e:
        logger.exception(
            "formatting user message failed",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise e


def format_chat_history(user, assistant, phone_number):
    """Format chat history in user assistant way."""
    try:
        chat_history = [
            {
                "role": "user",
                "content": format_user(
                    user_message=user, phone_number=phone_number
                ),
            },
            {
                "role": "assistant",
                "content": format_assistant(
                    assistant_message=assistant, phone_number=phone_number
                ),
            },
        ]

        return chat_history
    except Exception as e:
        logger.exception(
            "formatting chat histroy failed",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise e
