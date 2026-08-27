from qlink_chatbot.database.collections import git, idac
from qlink_chatbot.processors.abstract_processor import Processor
from qlink_chatbot.utils.logger_config import logger


class UserRegistration(Processor):
    """Processor class for getting or creating user profile."""

    def should_run(self, data: dict) -> bool:
        """Determine whether the processor should run based on the input data."""
        return True

    def check_user_profile(
        self, phone_number: str, whatsapp_username: str = ""
    ) -> dict:
        """Get or create user profile based on the phone number."""
        profile = idac.find_one({"phone_number": phone_number})
        if profile:
            return profile
        else:
            profile = {
                "username": whatsapp_username,
                "phone_number": phone_number,
                "service_selected": "",
                "chat_history": [],
            }
            return profile

    async def process(self, data: dict) -> dict:
        """Process input data for user registration."""
        phone_number = data["phone_number"]

        logger.info(
            "Request received to register user",
            extra={"phone_number": phone_number},
        )

        whatsapp_username = data["whatsapp_username"]
        response = self.check_user_profile(
            phone_number=phone_number, whatsapp_username=whatsapp_username
        )
        data["user_profile"] = response

        return data
    
class GitUserRegistration(Processor):
    """Processor class for getting or creating user profile."""

    def should_run(self, data: dict) -> bool:
        """Determine whether the processor should run based on the input data."""
        return True

    def check_user_profile(
        self, phone_number: str, whatsapp_username: str = ""
    ) -> dict:
        """Get or create user profile based on the phone number."""
        profile = git.find_one({"phone_number": phone_number})
        if profile:
            return profile
        else:
            profile = {
                "username": whatsapp_username,
                "phone_number": phone_number,
                "service_selected": "",
                "chat_history": [],
            }
            return profile

    async def process(self, data: dict) -> dict:
        """Process input data for user registration."""
        phone_number = data["phone_number"]

        logger.info(
            "Request received to register user",
            extra={"phone_number": phone_number},
        )

        whatsapp_username = data["whatsapp_username"]
        response = self.check_user_profile(
            phone_number=phone_number, whatsapp_username=whatsapp_username
        )
        data["user_profile"] = response

        return data
