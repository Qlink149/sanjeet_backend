import json

from qlink_chatbot.utils.logger_config import logger


def format_assistant(assistant_message, phone_number):
    """Format the assistant message to a user assistant way."""
    if not assistant_message:
        return ""
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
        if not isinstance(user_message, dict):
            return str(user_message or "").strip() or "[message]"
        msg_type = (user_message.get("type") or "text").lower()
        if msg_type == "text":
            body = (user_message.get("text") or {}).get("body") or ""

        elif msg_type == "button":
            body = (user_message.get("button") or {}).get("text") or ""
            if body:
                body = f"User Selected - [{body}] from quick reply"

        elif msg_type == "interactive":
            interactive = user_message.get("interactive") or {}
            itype = interactive.get("type")
            if itype == "list_reply":
                title = (interactive.get("list_reply") or {}).get("title")
                body = f"User Selected - [{title}] from list"

            elif itype == "nfm_reply":
                response_json = json.loads(
                    (interactive.get("nfm_reply") or {}).get("response_json") or "{}"
                )
                body = "Flow Reply - "
                for key, value in response_json.items():
                    body += f"\n{key}: {value}"

            elif itype == "button_reply":
                title = (interactive.get("button_reply") or {}).get("title")
                body = f"User Selected - [{title}] from quick reply"

        elif msg_type in {"image", "audio", "document", "sticker", "video", "location"}:
            body = f"[{msg_type.capitalize()}]"

        if not str(body).strip():
            body = f"[{msg_type or 'message'}]"
        return body
    except Exception as e:
        logger.exception(
            "formatting user message failed",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise e


def format_chat_history(user, assistant, phone_number):
    """Format standalone user / assistant rows. Skip empty assistant bubbles."""
    try:
        chat_history = [
            {
                "role": "user",
                "content": format_user(
                    user_message=user, phone_number=phone_number
                ),
            },
        ]
        assistant_content = format_assistant(
            assistant_message=assistant, phone_number=phone_number
        )
        if assistant_content and str(assistant_content).strip():
            chat_history.append(
                {
                    "role": "assistant",
                    "content": assistant_content,
                }
            )

        return chat_history
    except Exception as e:
        logger.exception(
            "formatting chat histroy failed",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise e
