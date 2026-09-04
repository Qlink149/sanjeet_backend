
import asyncio
import os

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.requests import Request

from qlink_chatbot.constants import (
    MASTERCLASS_NO_ACTIVE_REPLY,
    MASTERCLASS_TRIGGER_PHRASES,
)
from qlink_chatbot.database.campaign_analytics import (
    update_campaign_recipient_status,
)
from qlink_chatbot.database.db_utils import (
    append_chat_entries,
    ensure_user_thread,
    get_user_profile,
    save_to_mongo,
)
from qlink_chatbot.database.leads import register_for_masterclass, upsert_quiz_lead
from qlink_chatbot.database.masterclasses import (
    build_masterclass_reply,
    get_active_masterclass,
)
from qlink_chatbot.processors.response_manager import ResponseManager
from qlink_chatbot.utils.campaign_status import (
    extract_message_event_ids,
    extract_meta_failure_reason,
    extract_status_lookup_ids,
    extract_v3_failure_reason,
)
from qlink_chatbot.utils.format_chathistory import format_user
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.utils.phone import (
    inbound_matches_masterclass_trigger,
    normalize_wa_phone,
)
from qlink_chatbot.whatsapp_functions.send_text_message import send_text_message

QUICK_REPLY_RESPONSES = {
    "send sanjeet contact details": (
        "🔗 Here's how to reach Sanjeet. Contact URL TBD."
    ),
}


def _gupshup_native_to_meta(payload: dict) -> tuple[str, str, dict] | None:
    """Gupshup native ``type=message`` payload → phone, name, Meta-shaped message."""
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    msg_type = (payload.get("type") or "").lower()
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    phone = str(payload.get("source") or sender.get("phone") or "").strip()
    phone = normalize_wa_phone(phone) or phone
    username = str(sender.get("name") or "").strip()
    if not phone:
        return None

    if msg_type == "text":
        text = inner.get("text") if inner else payload.get("text")
        messages = {
            "type": "text",
            "from": phone,
            "text": {"body": str(text or "")},
        }
    elif msg_type in {"button_reply", "quick_reply", "button"}:
        title = inner.get("title") or inner.get("text") or inner.get("postbackText") or ""
        messages = {
            "type": "interactive",
            "from": phone,
            "interactive": {
                "type": "button_reply",
                "button_reply": {
                    "title": str(title),
                    "id": str(inner.get("id") or ""),
                },
            },
        }
    elif msg_type == "list_reply":
        title = inner.get("title") or inner.get("postbackText") or ""
        messages = {
            "type": "interactive",
            "from": phone,
            "interactive": {
                "type": "list_reply",
                "list_reply": {
                    "title": str(title),
                    "id": str(inner.get("id") or ""),
                },
            },
        }
    else:
        messages = {
            "type": "text",
            "from": phone,
            "text": {"body": f"[{msg_type or 'message'}]"},
        }
    return phone, username, messages


async def _save_inbound_chat(
    phone_number: str,
    whatsapp_username: str,
    messages: dict,
    response_manager: ResponseManager,
):
    phone_number = normalize_wa_phone(phone_number) or phone_number
    user_profile = await asyncio.to_thread(get_user_profile, phone_number) or {
        "chat_history": [],
        "service_selected": None,
    }
    pipeline_data = {
        "phone_number": phone_number,
        "messages": messages,
        "whatsapp_username": whatsapp_username,
        "user_profile": user_profile,
    }
    inbound_text = _extract_button_label(messages) or ""
    if inbound_matches_masterclass_trigger(inbound_text, MASTERCLASS_TRIGGER_PHRASES):
        logger.info(
            "Masterclass trigger matched",
            extra={"phone_number": phone_number},
        )
        active = await asyncio.to_thread(get_active_masterclass)
        if active:
            reply_text = build_masterclass_reply(active)
        else:
            reply_text = MASTERCLASS_NO_ACTIVE_REPLY
        user_content = format_user(messages, phone_number)
        entries = [
            {
                "role": "user",
                "content": user_content,
            }
        ]
        try:
            rsp = await asyncio.to_thread(
                send_text_message,
                phone_number,
                {"type": "text", "text": reply_text},
            )
        except Exception as e:
            logger.exception(
                "Masterclass auto-reply send failed",
                extra={"phone_number": phone_number, "error": str(e)},
            )
            rsp = {"success": False, "message_id": None, "error": str(e)}
        assistant = {
            "role": "assistant",
            "content": reply_text,
            "status": "submitted" if rsp.get("success") else "failed",
        }
        if rsp.get("message_id"):
            assistant["gupshup_message_id"] = rsp["message_id"]
        if rsp.get("error"):
            assistant["error"] = rsp["error"]
        entries.append(assistant)
        await asyncio.to_thread(
            append_chat_entries,
            phone_number,
            entries,
            whatsapp_username or None,
        )
        if active:
            await asyncio.to_thread(
                register_for_masterclass,
                phone_number,
                whatsapp_username or None,
                active,
            )
        return
    button_label = inbound_text
    quick_reply_text = (
        QUICK_REPLY_RESPONSES.get(button_label.strip().lower())
        if button_label
        else None
    )
    if quick_reply_text:
        logger.info(
            "Quick-reply button intercepted",
            extra={"button_label": button_label, "phone_number": phone_number},
        )
        pipeline_data["bot_response"] = [
            {"type": "text", "text": quick_reply_text}
        ]
        await asyncio.to_thread(save_to_mongo, pipeline_data)
        await asyncio.to_thread(response_manager.handle_responses, pipeline_data)
        return
    await asyncio.to_thread(save_to_mongo, pipeline_data)


def _extract_button_label(messages: dict) -> str | None:
    """Pulls the tapped button's label out of an inbound message, across
    the few different shapes BSPs use to relay a quick-reply tap."""
    msg_type = messages.get("type")

    if msg_type == "button":
        return (messages.get("button") or {}).get("text")

    if msg_type == "interactive":
        button_reply = (messages.get("interactive") or {}).get("button_reply") or {}
        return button_reply.get("title")

    if msg_type == "text":
        return (messages.get("text") or {}).get("body")

    return None


app = FastAPI(
    title="Qlink Sanjeet backend API",
    version="0.1.0",
    redoc_url=None,
    docs_url=None,
    openapi_url=None
)

from qlink_chatbot.routes.dashboard_routes import dashboard_router

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api/v1")

app.include_router(router=dashboard_router, prefix="/dashboard")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def _start_campaign_scheduler():
    try:
        from qlink_chatbot.database.collections import ensure_indexes

        ensure_indexes()
    except Exception as e:
        logger.warning("Could not ensure Mongo indexes", extra={"error": str(e)})
    if os.environ.get("VERCEL"):
        logger.info("Skipping in-process campaign scheduler on Vercel")
        return
    try:
        from qlink_chatbot.campaign_scheduler import start_scheduler

        start_scheduler()
    except Exception as e:
        logger.warning(
            "Campaign scheduler not started",
            extra={"error": str(e)},
        )


@app.get("/ping")
def ping():
    """Ping endpoint to check if the server is running."""
    return {"message": "Qlink <> Sanjeet backend API is up and running"}


@app.post("/gupshup/sanjeet/message")
async def messages(request: Request):
    """Inbound WhatsApp: campaign delivery status + save chat. No PACC menu."""
    request_data = await request.json()
    logger.info(
        "Webhook received",
        extra={
            "type": request_data.get("type"),
            "has_entry": "entry" in request_data,
            "has_payload": "payload" in request_data,
        },
    )
    phone_number = None
    response_manager = ResponseManager()

    try:
        if request_data.get("type") == "message-event":
            event_payload = request_data.get("payload") or {}
            primary_id, wa_id = extract_message_event_ids(event_payload)
            status = event_payload.get("type") or event_payload.get("status")

            logger.info(
                "V3 message-event webhook received",
                extra={
                    "gs_id": primary_id,
                    "wa_id": wa_id,
                    "status": status,
                },
            )

            if primary_id and status:
                error_reason = (
                    extract_v3_failure_reason(event_payload)
                    if status in ("failed", "undelivered")
                    else None
                )
                matched = await asyncio.to_thread(
                    update_campaign_recipient_status,
                    primary_id,
                    status,
                    wa_id,
                    error_reason,
                )
                logger.info(
                    "Campaign recipient status update result",
                    extra={
                        "gs_id": primary_id,
                        "wa_id": wa_id,
                        "status": status,
                        "error_reason": error_reason,
                        "matched": matched,
                    },
                )
            return {"status": "success"}

        # Gupshup native inbound: {type: "message", payload: {source, type, payload, sender}}
        if request_data.get("type") == "message" and isinstance(
            request_data.get("payload"), dict
        ):
            native_payload = request_data["payload"]
            if "entry" in native_payload:
                request_data = native_payload
            else:
                converted = _gupshup_native_to_meta(native_payload)
                if converted is None:
                    logger.info("Native inbound ignored; no phone on payload")
                    return {"status": "ignored", "reason": "no phone_number"}
                phone_number, whatsapp_username, messages = converted
                await _save_inbound_chat(
                    phone_number,
                    whatsapp_username,
                    messages,
                    response_manager,
                )
                return {"status": "success"}

        if "entry" not in request_data:
            logger.info(
                "Webhook ignored; unrecognized shape",
                extra={"keys": list(request_data.keys())[:12]},
            )
            return {"status": "ignored"}

        whatsapp_event = request_data["entry"][0]["changes"][0]["value"]

        if "statuses" in whatsapp_event:
            status_obj = whatsapp_event["statuses"][0]
            if "type" in status_obj:
                status = status_obj["type"]
            else:
                status = status_obj["status"]

            primary_id, wa_id = extract_status_lookup_ids(status_obj)
            if primary_id and status:
                error_reason = (
                    extract_meta_failure_reason(status_obj)
                    if status in ("failed", "undelivered")
                    else None
                )
                matched = await asyncio.to_thread(
                    update_campaign_recipient_status,
                    primary_id,
                    status,
                    wa_id,
                    error_reason,
                )
                logger.info(
                    "Campaign recipient status update result",
                    extra={
                        "gs_id": primary_id,
                        "wa_id": wa_id,
                        "status": status,
                        "error_reason": error_reason,
                        "matched": matched,
                    },
                )

            logger.info(
                "Ignoring message with status", extra={"status": status}
            )
            return {"status": "success"}

        messages = whatsapp_event["messages"][0]
        phone_number = normalize_wa_phone(messages["from"]) or messages["from"]
        whatsapp_username = (
            request_data["entry"][0]["changes"][0]["value"]["contacts"][0][
                "profile"
            ]["name"]
            if "contacts" in request_data["entry"][0]["changes"][0]["value"]
            else ""
        )
        await _save_inbound_chat(
            phone_number,
            whatsapp_username,
            messages,
            response_manager,
        )
        return {"status": "success"}

    except Exception as e:
        logger.exception(
            "Exception occured while running message endpoint",
            extra={"exception": e, "phone_number": phone_number},
        )
        if not phone_number:
            return {"status": "ignored", "reason": "no phone_number"}
        return {"status": "error"}


class QuizSubmit(BaseModel):
    name: str
    phone: str
    email: str | None = None
    archetype: str | None = None
    answers: dict | None = Field(default=None)


@app.post("/quiz/submit")
async def quiz_submit(payload: QuizSubmit):
    """Public: persist Money Ceiling Quiz capture, then show archetype in-page."""
    name = (payload.name or "").strip()
    phone = (payload.phone or "").strip()
    if not name or not phone:
        return {"success": False, "message": "Name and WhatsApp number are required"}
    email = (payload.email or "").strip() or None
    try:
        lead = await asyncio.to_thread(
            upsert_quiz_lead,
            name,
            phone,
            email,
            payload.archetype,
            payload.answers,
        )
        stored = (lead or {}).get("contact_number") or normalize_wa_phone(phone) or phone
        await asyncio.to_thread(ensure_user_thread, stored, name)
        return {
            "success": True,
            "data": {
                "lead_id": (lead or {}).get("lead_id"),
                "phone": stored,
            },
        }
    except Exception as e:
        logger.exception("Quiz submit failed", extra={"error": str(e)})
        return {"success": False, "message": "Could not save quiz details"}
