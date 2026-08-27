import json

from qlink_chatbot.models.enums import FLowId, ListIds
from qlink_chatbot.models.service_list import ServiceList as sl
from qlink_chatbot.processors.abstract_processor import Processor
from qlink_chatbot.utils.add_to_sheet import add_data_to_sheet
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.database.db_utils import is_flow_id_exist


class ServiceList(Processor):
    """Processor for sending and saving service list options."""

    def should_run(self, data: dict) -> bool:
        """Determine whether the processor should run based on the input data."""
        if "bot_response" in data:
            return False
        else:
            return True

    async def process(self, data: dict) -> dict:
        """Process input data for user service list."""
        user_profile = data["user_profile"]
        messages = data["messages"]
        phone_number = data["phone_number"]
        username = user_profile["username"] 

        if not self.should_run(data):
            logger.info(
                "Skipping processor",
                extra={
                    "processor": self.__class__.__name__,
                    "phone_number": phone_number,
                },
            )
            return data
        
        if (
            "interactive" in messages
            and "list_reply" in messages["interactive"]
        ):
            logger.info(
                "Message of type list received",
                extra={"phone_number": phone_number},
            )
            list_id_json = json.loads(
                messages["interactive"]["list_reply"]["id"]
            )
            list_id = list_id_json["msgid"]
            if list_id == ListIds.SERVICE_LIST_ID.value:
                service_selected = messages["interactive"]["list_reply"][
                    "title"
                ]
                logger.info(
                    "Service selected storing in user profile",
                    extra={
                        "service_selected": service_selected,
                        "phone_number": phone_number,
                    },
                )

                user_profile[service_selected] = (
                    user_profile.get(service_selected, 0) + 1
                )  # noqa

                if service_selected == sl.SL_AGENDA.value:
                    data["bot_response"] = [
                        {
                            "type": "media",
                            "media_type": "doc",
                            "caption": "",
                            "filename": "PACC Sanjeet Agenda 26",  # noqa
                            "url": "https://ik.imagekit.io/0rf6agnve/fsai/PACC2026%20Agenda%20FINAL.pdf",  # noqa
                        }
                    ]
                    return data

                elif service_selected == sl.SL_EXHIBITOR.value:
                    data["messages"]["text"] = {
                        "body": "Tell me more about the exhibitors in short."
                    }
                    user_profile["service_selected"] = sl.STALL.value
                    
                elif service_selected == sl.SL_NAVIGATION.value:
                    data["bot_response"] = [
                        {
                            "type": "media",
                            "media_type": "image",
                            "caption": "Venue Map",
                            "originalUrl": "https://ik.imagekit.io/0rf6agnve/fsai/PACC_stall_layout.jpg",  # noqa
                        },
                        {
                            "type": "text",
                            "text": (
                                "This is the venue map. You can directly ask queries like: \n"
                                "- Where is a specific stall or sponsor located?\n"
                                "- How can I reach a particular booth or area?\n"
                                "- Guide me to a section of the venue.\n\n"
                                "I'll help you navigate the venue easily."
                            )
                        }
                    ]
                    return data


                elif service_selected == sl.SL_OTHER.value:
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": (
                                "Please type your query, and I will assist you.\n\nFor example:\n\n"
                                "1. What is Sanjeet and what does it do?\n"
                                "2. What is the vision and mission of Sanjeet?\n"
                                "3. What is the agenda for today’s event?\n"
                                "4. Can you share the day-wise event schedule?\n"
                                "5. Where are the sponsor and exhibitor stalls located?"
                            ),
                        },
                    ]
                    return data


        if "interactive" in messages and "nfm_reply" in messages["interactive"]:
            nfm_reply = messages["interactive"]["nfm_reply"]
            if nfm_reply["name"] == "flow":
                flow_data = json.loads(nfm_reply["response_json"])
                if( 
                    is_flow_id_exist(flow_data.get("flow_token")) or 
                    flow_data.get('flow_token') in {'2338473189912684','1545494639860594','1300595032122020'}
                ):
                    user_profile["service_selected"] = sl.SCAN.value

                elif flow_data.get("flow_token") in {FLowId.SITE_VISIT.value}:
                    logger.info(
                        "site visit registration data received",
                        extra={"phone_number": phone_number},
                    )

                    registration_data = {
                        "username": username,
                        "question": flow_data.get(
                            "screen_0_question_or_message_0", ""
                        ),
                        "wa_phone": phone_number,
                    }

                    add_data_to_sheet(data=registration_data)
                    

                    logger.info(
                        "New appointment booked",
                        extra={
                            "payload": registration_data,
                            "phone_number": phone_number,
                        },
                    )

                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": "Thanks! Our team will get back to you soon.",  # noqa
                        }
                    ]

            return data

        if user_profile["service_selected"] == "":
            logger.info(
                "Sending service list", extra={"phone_number": phone_number}
            )
            data["bot_response"] = [
                {
                    "type": "list",
                    "list": "service_list",
                    "text": "Sending service list",
                }
            ]

        return data
    
