
from datetime import datetime

import pytz

from qlink_chatbot.processors.abstract_processor import Processor
from qlink_chatbot.prompt.agenda_prompt import agenda_prompt
from qlink_chatbot.utils.get_openai_responses import get_openai_responses
from qlink_chatbot.utils.logger_config import logger


class AgendaAgent(Processor):
    """Search a query."""

    def should_run(self, data: dict) -> bool:
        """Determine whether the processor should run based on the input data."""
        if "bot_response" in data:
            return False
        return True


    async def process(self, data: dict) -> dict:
        """Process the input data and return the processed data."""
        phone_number = data["phone_number"]
        user_profile = data["user_profile"]
        username = user_profile["username"]

        CONTEXT = agenda_prompt


        if not self.should_run(data):
            logger.info(
                "Skipping processor",
                extra={
                    "processor": self.__class__.__name__,
                    "phone_number": phone_number,
                },
            )
            return data

        try:
            if "text" in data["messages"]:
                user_message = data["messages"]["text"]["body"]
            else:
                user_message = "please tell me the agenda of the event in short."

            logger.info(
                "Request received to agenda query", extra={"query": user_message}
            )


            # Get the most recent 7 chats from chat_history
            chat_history = data["user_profile"].get("chat_history", [])
            recent_chats = chat_history[-10:]

            # Convert chat history list of dicts to a single string
            chat_history_str = ""
            for chat in recent_chats:
                role = chat.get("role", "")
                content = chat.get("content", "")
                chat_history_str += f"{role.capitalize()}: {content}\n"


            message = [
                {"role": "system", "content": f"Current Time in IST {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')}"},
                {"role": "system", "content": f"Username is {username}"},
                {
                    "role": "system",
                    "content": f"Recent chat history:\n{chat_history_str.strip()}",
                },
                {
                    "role": "user",
                    "content": f"user message: {user_message}",
                },
            ]

            response = await get_openai_responses(
                agent_name="Genrator Agent",
                model="gpt-4.1-mini",
                messages=message,
                instruction=CONTEXT,
            )

            response_data = response
            if response_data == "auto_reply":
                data["bot_response"] = [
                    {
                        "type": "skip"  # noqa
                    }
                ]
            else:
                response_data = response_data.replace("**", "*")
                response_data = response_data.replace("####", "*")
                response_data = response_data.replace("###", "*")
                response_data = response_data.replace("##", "*")

                data["bot_response"] = [
                    {
                        "type": "text",
                        "text": response_data,  # noqa
                    }
                ]

            user_profile["service_selected"] = ""
            return data
        except Exception as e:
            logger.exception(
                "Exception occured while running agenda agent.",
                extra={"exception": e, "phone_number": phone_number},
            )
            raise e
