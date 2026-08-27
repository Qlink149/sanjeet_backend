
from datetime import datetime
import json

from qlink_chatbot.processors.abstract_processor import Processor
from qlink_chatbot.utils.calculate_score import calculate_day_total_score
from qlink_chatbot.utils.logger_config import logger

from qlink_chatbot.database.db_utils import (
    mark_attendance, 
    set_venue_entry_flag, 
    get_attendee_by_id,
    mark_session_attendance,
    mark_venue_entry,
    is_flow_id_exist,
    save_session_feedback,
    save_quiz_score
)


class ScanAgent(Processor):
    """Search a query."""

    def should_run(self, data: dict) -> bool:
        """Determine whether the processor should run based on the input data."""
        if "bot_response" in data:
            return False
        return True


    async def process(self, data: dict) -> dict:
        """Process the input data and return the processed data."""
        phone_number = data["phone_number"]
        scan_id = data.get("scanid")
        scan_type = data.get("scan_type")
        user_profile = data["user_profile"]
        messages = data["messages"]


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
            if "interactive" in messages and "nfm_reply" in messages["interactive"]:
                nfm_reply = messages["interactive"]["nfm_reply"]
                if nfm_reply["name"] == "flow":
                    flow_data = json.loads(nfm_reply["response_json"])
                    flow_id = flow_data.get("flow_token")
                    if is_flow_id_exist(flow_id):
                        feedback_respone = {
                            "q1": flow_data.get(
                                "screen_0_Was_this_worth_your_time_0", ""
                            ),
                            "q2": flow_data.get(
                                "screen_0_Practical_actionable_insights_1", ""
                            ),
                            "q3": flow_data.get(
                                "screen_0_Go_deeper_next_PACC_2", ""
                            ),
                        }

                        save_session_feedback(
                            phone_number=phone_number,
                            flow_id=flow_id,
                            flow_data=feedback_respone
                        )

                        logger.info(
                            "Session feedback saved",
                            extra={
                                "phone_number": phone_number,
                                "flow_id": flow_id,
                            },
                        )

                        data["bot_response"] = [
                            {
                                "type": "text",
                                "text": "Thanks for your feedback.",  # noqa
                            }
                        ]

                        user_profile["service_selected"] = ""
                        return data
                    
                    if flow_id in (
                        "2338473189912684",
                        "1545494639860594",
                        "1300595032122020"
                    ):

                        quiz_response = {
                            "screen_0_Select_Correct_Option_0": flow_data.get("screen_0_Select_Correct_Option_0", ""),
                            "screen_1_Select_Correct_Option_0": flow_data.get("screen_1_Select_Correct_Option_0", ""),
                            "screen_2_Select_Correct_Option_0": flow_data.get("screen_2_Select_Correct_Option_0", ""),
                            "screen_3_Select_Correct_Option_0": flow_data.get("screen_3_Select_Correct_Option_0", ""),
                        }

                        logger.info(
                            "Quiz response received",
                            extra={"phone_number": phone_number,
                                "flow_id": flow_id,
                                "quiz_response": quiz_response
                            },
                        )

                        flow_day_map = {
                            "2338473189912684": "day1",
                            "1545494639860594": "day2", 
                            "1300595032122020": "day3"
                        }
                        day = flow_day_map.get(flow_id)
                        score = calculate_day_total_score(phone_number, day, quiz_response)

                        logger.info(    
                            "Quiz response received",
                                    extra={
                                    "phone_number": phone_number,
                                    "flow_id": flow_id,
                                    "day": day,
                                    "quiz_response": quiz_response,
                                    "score": score
                                    },
                          )

                        save_quiz_score(
                            phone_number=phone_number,
                            day=day,
                            score=score
                        )

                        logger.info(
                                "Quiz score saved",
                                extra={
                                    "phone_number": phone_number,
                                    "flow_id": flow_id,
                                    "day": day,
                                    "score": score
                                }
                        )

                        data["bot_response"] = [
                            {
                                "type": "text",
                                "text":"Thanks for participating in the quiz! Your responses have been recorded.",  # noqa
                            }
                        ]

                        user_profile["service_selected"] = ""
                        return data


            if scan_type == "scanstall":
                logger.info(
                    "Request received to mark the stall attendace", extra={"phone_number": phone_number}
                )

                result = mark_attendance(phone_number=phone_number, stall_id=scan_id)

                if result.get("success"):
                    stall = result.get("stall")
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": (
                                f"Thank you for visiting *{stall.get('company_name')}* 🙌\n\n"
                                f"This stall is at *{stall.get('stall_number')}*.\n"
                                f"I can also help you with details about other stalls around this area."
                            )
                        }
                    ]

                else:
                    if result.get("error") == "invalid_stall":
                        message = (
                            "❌ Invalid stall QR code.\n\n"
                            "Please scan a valid stall QR or contact the helpdesk."
                        )
                    else:
                        message = (
                            "Sorry, your entry couldn’t be verified ❌\n\n"
                            "Your number is not registered in the attendee list. "
                            "Please contact the event helpdesk for assistance."
                        )

                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": message
                        }
                    ]

            elif scan_type == "scansession":
                logger.info(
                    "Request received to mark the scan session", extra={"phone_number": phone_number}
                )

                result = mark_session_attendance(phone_number=phone_number, session_id=int(scan_id))
                logger.info("result", extra={"result": result})

                if result.get("success"):
                    session = result.get("session")
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": "Your attendance has been marked for this session."
                        },
                        {
                            "type": "flow",
                            "flow": "session_feedback",
                            "session_name": session.get("session_name"),
                            "flow_id": session.get("flow_id")
                        }
                    ]


                    # TODO:
                    if not user_profile.get("send_day_1_quiz", ""):
                        data["bot_response"].append(
                            {
                                "type": "flow",
                                "flow": "send_day1_quiz_flow"
                            }
                        )
                        user_profile["send_day_1_quiz"] = True


                else:
                    if result.get("error") == "invalid_session":
                        message = (
                            "❌ Invalid session QR code.\n\n"
                            "Please scan a valid session QR or contact the helpdesk."
                        )
                    else:
                        message = (
                            "Sorry, your entry couldn’t be verified ❌\n\n"
                            "Your number is not registered in the attendee list. "
                            "Please contact the event helpdesk for assistance."
                        )

                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": message
                        }
                    ]

            elif scan_type == "scanatd":
                logger.info(
                    "Request received to get attendee details.", extra={"phone_number": phone_number}
                )

                if phone_number in {
                    "918432563408",
                    "94705296174",
                    "94710356133",
                    "94710327157",
                    "94702318890",
                    "94702318759",
                    "919167244847"
                }:
                    # Authorized person — mark venue entry
                    entry_result = mark_venue_entry(user_id=scan_id)

                    if entry_result.get("success"):
                        attendee_name = entry_result.get("name", "Attendee")
                        data["bot_response"] = [
                            {
                                "type": "text",
                                "text": (
                                    f"✅ Venue entry marked for *{attendee_name}*\n\n"
                                    "Attendance marked successfully."
                                )
                            }
                        ]
                    else:
                        data["bot_response"] = [
                            {
                                "type": "text",
                                "text": (
                                    "❌ Attendee does not exist.\n\n"
                                    "The scanned QR does not match any registered attendee. "
                                    "Please verify and try again."
                                )
                            }
                        ]

                    user_profile["service_selected"] = ""
                    return data

                result = get_attendee_by_id(user_id=scan_id)

                if result:
                    attendee = result

                    name = attendee.get("name", "N/A")
                    designation = attendee.get("designation")
                    company = attendee.get("company")
                    category = attendee.get("category", "").lower()
                    sponsor_type = attendee.get("sponsor_type")

                    title_map = {
                        "vip": "🌟 VIP Delegate",
                        "office_bearers": "🏛️ Office Bearer",
                        "sponsor": "🤝 Sponsor",
                        "spouse": "💐 Spouse Delegate"
                    }

                    intro_map = {
                        "vip": "Here’s one of our distinguished guests today ✨",
                        "office_bearers": "Meet one of the key people behind the association 👋",
                        "sponsor": "Here’s a valued partner supporting this event 🤝",
                        "spouse": "A lovely presence accompanying one of our delegates 💐"
                    }

                    lines = [
                        f"{intro_map.get(category, 'Here’s an attendee at the event 👋')}",
                        f"*{name}*"
                    ]

                    if category == "spouse":
                        if company:
                            lines.append(f"They are accompanying *{company}* today.")
                    else:
                        if designation and company:
                            lines.append(f"They serve as *{designation}* at *{company}*.")
                        elif designation:
                            lines.append(f"They currently hold the role of *{designation}*.")
                        elif company:
                            lines.append(f"They are associated with *{company}*.")

                    if category == "sponsor" and sponsor_type:
                        lines.append(f"They’re supporting us as part of the *{sponsor_type}* sponsor group.")

                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": "\n\n".join(lines)
                        }
                    ]

                else:
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": (
                                "❌ Invalid attendee QR code.\n\n"
                                "Please scan a valid attendee QR or contact the event helpdesk."
                            )
                        }
                    ]


            elif scan_type == "scanentry":
                logger.info(
                    "Request received to mark the entry", extra={"phone_number": phone_number}
                )

                success = set_venue_entry_flag(phone_number=phone_number, flag=True)
                if success:
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": (
                                "Welcome to the venue! 🎉\n\n"
                                "Your entry has been successfully recorded.\n"
                                "You can scan stalls to get details, discover nearby stalls, "
                                "or ask me for any help during the event."
                            )
                        }
                    ]
                else:
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": (
                                "Sorry, your entry couldn’t be verified ❌\n\n"
                                "Your number is not registered in the attendee list. "
                                "Please contact the event helpdesk for assistance."
                            )
                        }
                    ]

            else:
                data["bot_response"] = [
                        {
                            "type": "text",
                            "text": (
                                "Invalid QR Code Scanned. ⚠️\n\n"
                                "Please contact the event helpdesk for assistance."
                            )
                        }
                    ]

            

            user_profile["service_selected"] = ""
            return data
        except Exception as e:
            logger.exception(
                "Exception occured while running stall and sponser agent.",
                extra={"exception": e, "phone_number": phone_number},
            )
            raise e
