
from datetime import datetime

from qlink_chatbot.models.service_list import ServiceList
from qlink_chatbot.processors.abstract_processor import Processor
from qlink_chatbot.utils.logger_config import logger


class QuizAgent(Processor):
    """Quiz agent to handle quiz requests."""

    def should_run(self, data: dict) -> bool:
        """Determine whether the processor should run based on the input data."""
        if "bot_response" in data:
            return False
        return True


    async def process(self, data: dict) -> dict:
        """Process the input data and return the processed data."""
        phone_number = data["phone_number"]
        user_profile = data["user_profile"]

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
            service_selected = user_profile.get("service_selected", "")
            quiz_sub_category = user_profile.get("quiz_sub_category", "")
            
            logger.info(
                "Quiz agent processing request",
                extra={
                    "phone_number": phone_number,
                    "service_selected": service_selected,
                    "quiz_sub_category": quiz_sub_category,
                },
            )
            
            # Check if subcategory is present (category + subcategory)
            if quiz_sub_category and service_selected==ServiceList.QUIZ.value:
                # User selected a specific day - send quiz flow
                logger.info(
                    "Sending quiz flow for specific day",
                    extra={
                        "phone_number": phone_number,
                        "quiz_sub_category": quiz_sub_category,
                    },
                )
                data["bot_response"] = [
                    {
                        "type": "flow",
                        "flow": "send_day1_quiz_flow",
                    }
                ]
            else:
                # Only category (no subcategory) - ask which day
                logger.info(
                    "Asking user which day for quiz",
                    extra={"phone_number": phone_number},
                )
                data["bot_response"] = [
                    {
                        "type": "text",
                        "text": "Which day's quiz would you like to participate in? Please specify Day 1, Day 2, or Day 3.",
                    }
                ]
            user_profile["service_selected"] = ""
            user_profile["quiz_sub_category"] = ""
            return data
            
        except Exception as e:
            logger.exception(
                "Exception occurred while running quiz agent",
                extra={"exception": e, "phone_number": phone_number},
            )
            raise e
        
       