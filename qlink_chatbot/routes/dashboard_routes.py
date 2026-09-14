
import asyncio
import json
import os
import re
from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from starlette.requests import Request

from qlink_chatbot.database.db_utils import (
    append_chat_entries,
    get_all_docs_dashboard,
    get_doc_by_id,
    create_campaign,
    get_all_campaigns,
    get_campaign_by_id,
    get_campaign_recipients_csv,
    get_all_leads,
    get_filtered_leads,
    get_lead_stats,
    save_template_image,
    get_template_image,
    create_schedule,
    get_schedules,
    update_schedule,
    delete_schedule,
)
from qlink_chatbot.database.collections import leads
from qlink_chatbot.database.leads import PIPELINE_VALUES, build_lead_query, get_lead_by_id
from qlink_chatbot.database.masterclasses import (
    create_masterclass,
    delete_masterclass,
    list_masterclass_registrants,
    list_masterclasses,
    set_active,
    update_masterclass,
)
from qlink_chatbot.utils.env_load import password as pwd
from qlink_chatbot.utils.env_load import public_base_url
from qlink_chatbot.utils.env_load import username as us
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.utils.phone import normalize_phone_list, normalize_wa_phone
from qlink_chatbot.whatsapp_functions.dashboard.create_template import (
    create_template,
    upload_template_media,
)
from qlink_chatbot.whatsapp_functions.send_text_message import send_text_message
from qlink_chatbot.whatsapp_functions.dashboard.delete_template import (
    delete_template_by_name,
)
from qlink_chatbot.whatsapp_functions.dashboard.get_all_templates import (
    get_all_templates,
)
from qlink_chatbot.whatsapp_functions.dashboard.send_campaign_batch import (
    send_campaign_messages,
)


class LoginData(BaseModel):
    username: str
    password: str



dashboard_router = APIRouter()

def _verify_cron_secret(request: Request) -> JSONResponse | None:
    secret = os.environ.get("CRON_SECRET")
    if secret:
        auth = request.headers.get("authorization") or ""
        if auth != f"Bearer {secret}":
            return JSONResponse(
                {"success": False, "message": "Unauthorized"},
                status_code=401,
            )
    return None


@dashboard_router.get("/cron/schedules")
def cron_run_schedules(request: Request):
    """Vercel Cron tick for delayed/expiry campaign sends.

    In-process APScheduler does not survive serverless. vercel.json hits
    this path on a schedule. If CRON_SECRET is set, require
    Authorization: Bearer <CRON_SECRET> (Vercel sends this automatically).
    """
    denied = _verify_cron_secret(request)
    if denied:
        return denied
    from qlink_chatbot.campaign_scheduler import run_due_schedules

    run_due_schedules()
    return JSONResponse({"success": True})


@dashboard_router.get("/cron/campaign-retries")
def cron_run_campaign_retries(request: Request):
    """Vercel Cron tick for auto-retrying retriable campaign failures."""
    denied = _verify_cron_secret(request)
    if denied:
        return denied
    from qlink_chatbot.utils.campaign_retry import run_due_campaign_retries

    summary = run_due_campaign_retries()
    return JSONResponse({"success": True, **summary})


@dashboard_router.get("/cron/quiz-access-reminders")
def cron_run_quiz_access_reminders(request: Request):
    """Vercel Cron tick for 24h quiz access_yes reminders."""
    denied = _verify_cron_secret(request)
    if denied:
        return denied
    from qlink_chatbot.utils.quiz_access_reminder import run_due_quiz_access_reminders

    summary = run_due_quiz_access_reminders()
    return JSONResponse({"success": True, **summary})


@dashboard_router.get("/ping")
def ping():
    """General Ping."""
    try:
        logger.info("dashboard Ping Received")
        return JSONResponse({"success":True}, status_code=201)
    except Exception as e:
        logger.info("Error Occured in dashboard ping", extra={"error": e})
        return JSONResponse({
            "success": False, "message": str(e)
        }, status_code=501)
    
@dashboard_router.post("/login")
def login(data: LoginData):
    """Dashboard Login."""  
    username = data.username
    password = data.password
    try:
        if not password or not username:
            return JSONResponse({"success":False, "message": "Invalid Request"}, status_code=401)
        elif (
            username != us or password != pwd
        ):
            return JSONResponse({"success":False, "message": "Invalid Username or Password"}, status_code=402)
        else:
            return JSONResponse({"success":True}, status_code=201)
    except Exception as e:
        logger.info("Error Occured in login", extra={"error": e})
        return JSONResponse({
            "success": False, "message": str(e)
        }, status_code=501)
    
@dashboard_router.get("/chat/all")
async def fetch_all_docs(page: int = 1, limit: int = 20, search: str = ""):
    """Paginated inbox list — no chat_history payload."""
    try:
        if limit > 100:
            limit = 100
        docs = await asyncio.to_thread(
            get_all_docs_dashboard, page, limit, search
        )
        return JSONResponse(
            content={"success": True, "data": docs},
            status_code=200,
        )
    except Exception as e:
        logger.exception("Error fetching all docs", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error fetching documents"},
            status_code=500,
        )


class ChatSendPayload(BaseModel):
    doc_id: str
    text: str


@dashboard_router.post("/chat/send")
async def send_chat_message(payload: ChatSendPayload):
    """Session text from Inbox composer (24h customer-care window required)."""
    text = (payload.text or "").strip()
    doc_id = (payload.doc_id or "").strip()
    if not doc_id or not text:
        return JSONResponse(
            content={"success": False, "message": "doc_id and text are required"},
            status_code=400,
        )
    try:
        doc = await asyncio.to_thread(get_doc_by_id, doc_id)
        if not doc:
            return JSONResponse(
                content={"success": False, "message": "Chat thread not found"},
                status_code=404,
            )
        phone = normalize_wa_phone(doc.get("phone_number")) or doc.get("phone_number")
        if not phone:
            return JSONResponse(
                content={"success": False, "message": "Thread has no phone number"},
                status_code=400,
            )
        try:
            rsp = await asyncio.to_thread(
                send_text_message,
                phone,
                {"type": "text", "text": text},
            )
        except Exception as e:
            logger.exception(
                "Inbox send failed",
                extra={"phone_number": phone, "error": str(e)},
            )
            rsp = {"success": False, "message_id": None, "error": str(e)}

        assistant = {
            "role": "assistant",
            "content": text,
            "status": "submitted" if rsp.get("success") else "failed",
        }
        if rsp.get("message_id"):
            assistant["gupshup_message_id"] = rsp["message_id"]
        if rsp.get("error"):
            assistant["error"] = rsp["error"]

        await asyncio.to_thread(
            append_chat_entries,
            phone,
            [assistant],
            doc.get("username") or None,
        )
        if not rsp.get("success"):
            return JSONResponse(
                content={
                    "success": False,
                    "message": rsp.get("error")
                    or "Send failed (outside 24h window or provider error)",
                    "data": assistant,
                },
                status_code=400,
            )
        return JSONResponse(
            content={"success": True, "data": assistant},
            status_code=200,
        )
    except Exception as e:
        logger.exception("Error sending chat message", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error sending message"},
            status_code=500,
        )


@dashboard_router.get("/chat/{doc_id}")
async def fetch_doc_by_id(doc_id: str):
    """Fetch a document by its _id."""
    try:
        doc = await asyncio.to_thread(get_doc_by_id, doc_id)
        if not doc:
            return JSONResponse(
                content={"success": False, "message": "Document not found"},
                status_code=404,
            )
        
        return JSONResponse(
            content={"success": True, "data": doc},
            status_code=200,
        )
    except Exception as e:
        logger.exception(
            "Error fetching doc by id", extra={"exception": e, "_id": doc_id}
        )
        return JSONResponse(
            content={"success": False, "message": "Error fetching document"},
            status_code=500,
        )
    
@dashboard_router.get("/chat/template/all")
async def fetch_all_templates():
    """Routes to fetch all templates"""
    try:
        doc = await asyncio.to_thread(get_all_templates)
        if doc is None:
            return JSONResponse(
                content={
                    "success": False,
                    "message": "Gupshup did not return templates in time. Retry.",
                },
                status_code=504,
            )
        
        return JSONResponse(
            content={"success": True, "data": doc},
            status_code=200,
        )
    except Exception as e:
        logger.exception(
            "Error fetching templates", extra={"exception": e}
        )
        return JSONResponse(
            content={"success": False, "message": "Error fetching Templates."},
            status_code=500,
        )
    
TEMPLATE_CATEGORIES = {"UTILITY", "MARKETING", "AUTHENTICATION"}
LEAD_PIPELINES = {"all_leads", *PIPELINE_VALUES}
ELEMENT_NAME_RE = re.compile(r"^[a-z0-9_]+$")
PUBLIC_BASE_URL = public_base_url




@dashboard_router.post("/chat/template")
async def create_template_route(
    element_name: str = Form(...),
    category: str = Form(...),
    content: str = Form(...),
    example: str = Form(...),
    language_code: str = Form("en"),
    header: str | None = Form(None),
    footer: str | None = Form(None),
    buttons: str | None = Form(None),
    image: UploadFile | None = File(None),
):
    """Create a new WhatsApp template and submit it to Gupshup for approval.

    `buttons`, if provided, is a JSON string: [{"text": "...", "url": "..."}, ...]
    """
    try:
        if not ELEMENT_NAME_RE.match(element_name):
            return JSONResponse(
                content={
                    "success": False,
                    "message": "element_name must be lowercase_snake_case (letters, numbers, underscores only)",
                },
                status_code=400,
            )

        if category not in TEMPLATE_CATEGORIES:
            return JSONResponse(
                content={
                    "success": False,
                    "message": f"category must be one of {sorted(TEMPLATE_CATEGORIES)}",
                },
                status_code=400,
            )

        gupshup_payload = {
            "elementName": element_name,
            "languageCode": language_code,
            "category": category,
            "content": content,
            "example": example,
            "vertical": element_name,
        }

        if header:
            gupshup_payload["header"] = header
        if footer:
            gupshup_payload["footer"] = footer

        if buttons:
            try:
                button_list = json.loads(buttons)
            except json.JSONDecodeError:
                return JSONResponse(
                    content={"success": False, "message": "buttons must be valid JSON"},
                    status_code=400,
                )

            gupshup_buttons = []
            for b in button_list:
                if not b.get("text"):
                    continue
                if b.get("type") == "QUICK_REPLY" or not b.get("url"):
                    gupshup_buttons.append(
                        {"type": "QUICK_REPLY", "text": b["text"]}
                    )
                else:
                    gupshup_buttons.append(
                        {
                            "type": "URL",
                            "text": b["text"],
                            "url": b["url"],
                            "example": [b["url"]],
                        }
                    )
            if gupshup_buttons:
                gupshup_payload["buttons"] = json.dumps(gupshup_buttons)

        file_bytes = None
        if image is not None:
            file_bytes = await image.read()
            handle = await asyncio.to_thread(
                upload_template_media,
                file_bytes,
                image.filename,
                image.content_type,
            )
            gupshup_payload["templateType"] = "IMAGE"
            gupshup_payload["exampleMedia"] = handle
        else:
            gupshup_payload["templateType"] = "TEXT"

        result = await asyncio.to_thread(create_template, gupshup_payload)

        if result.get("status") != "success":
            return JSONResponse(
                content={
                    "success": False,
                    "message": result.get("message", "Template creation failed"),
                },
                status_code=400,
            )

        template_data = result.get("template") or {}

        # Persist the header image in MongoDB so it has a stable, public URL
        # we can reference when actually sending this template later — the
        # media handle from upload_template_media above is only valid for
        # Gupshup's approval-time preview, not for real sends. MongoDB (not
        # local disk) so this survives on stateless/serverless deployments.
        if file_bytes is not None and template_data.get("id"):
            await asyncio.to_thread(
                save_template_image,
                template_data["id"],
                image.filename or "image.jpg",
                image.content_type or "image/jpeg",
                file_bytes,
            )

        return JSONResponse(
            content={"success": True, "data": template_data},
            status_code=201,
        )

    except Exception as e:
        logger.exception("Error creating template", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error creating template"},
            status_code=500,
        )


@dashboard_router.get("/template-image/{template_id}")
async def fetch_template_image(template_id: str):
    """Serves a template's header image from MongoDB.

    Public and unauthenticated on purpose — Gupshup/Meta's servers need to
    fetch this URL directly to attach it as the template's header image.
    """
    image = await asyncio.to_thread(get_template_image, template_id)
    if not image:
        return JSONResponse(
            content={"success": False, "message": "Image not found"},
            status_code=404,
        )
    return Response(content=image["data"], media_type=image["content_type"])


@dashboard_router.delete("/chat/template/{template_name}")
async def delete_templates(template_name: str):
    """Routes to fetch all templates"""
    try:
        doc = await asyncio.to_thread(delete_template_by_name, template_name)
        if not doc:
            return JSONResponse(
                content={"success": False, "message": "Error deleting Templates."},
                status_code=401,
            )
        
        return JSONResponse(
            content={"success": True},
            status_code=200,
        )
    except Exception as e:
        logger.exception(
            "Error deleting templates", extra={"exception": e}
        )
        return JSONResponse(
            content={"success": False, "message": "Error deleting Templates."},
        )


class PhoneItem(BaseModel):
    phone_code: str
    phone_number: str



@dashboard_router.post("/template/trigger/{template_id}")
async def trigger_campaign_v2(
    request: Request,
    background_tasks: BackgroundTasks,
    template_id: str,
    file: UploadFile = File(None),
    phone_numbers: str | None = Form(None),
    phone_codes: str | None = Form(None),
    category: str | None = Form(None),
    sub_category: str | None = Form(None),
    source: str | None = Form(None),
    exclude_phone_numbers: str | None = Form(None),
    dry_run: bool = Form(False),
):
    try:
        records = []

        # If category selected
        if category:
            query = build_lead_query(
                category=category,
                sub_category=sub_category,
                source=source,
                whatsapp_ready_only=True,
            )
            if exclude_phone_numbers:
                excluded = [
                    p.strip() for p in exclude_phone_numbers.split(",") if p.strip()
                ]
                if excluded:
                    already = query.get("contact_number", {}).get("$nin", [])
                    query["contact_number"] = {"$nin": list({*already, *excluded})}

            lead_docs = await asyncio.to_thread(
                lambda q=query: list(
                    leads.find(q, {"contact_number": 1, "_id": 0})
                )
            )
            records = [
                {"phone_code": "", "phone_number": lead["contact_number"]}
                for lead in lead_docs
                if lead.get("contact_number")
            ]

        # If file uploaded
        elif file:
            try:
                import pandas as pd
            except ImportError:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "message": "Excel support is not installed"},
                )
            if file.filename.endswith(".xlsx"):
                df = pd.read_excel(file.file, engine="openpyxl")
            elif file.filename.endswith(".xls"):
                df = pd.read_excel(file.file, engine="xlrd")
            else:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "message": "Invalid file format"},
                )

            records = df[["phone_code", "phone_number"]].to_dict(orient="records")

        # Manual numbers
        elif phone_numbers and phone_codes:
            numbers = phone_numbers.split(",")
            codes = phone_codes.split(",")

            if len(numbers) != len(codes):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "message": "Length mismatch"},
                )

            records = [
                {"phone_code": c, "phone_number": n}
                for c, n in zip(codes, numbers)
            ]

        else:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Provide file, phone list or category"},
            )

        phones = normalize_phone_list(
            [
                r["phone_number"] if category else f"{r['phone_code']}{r['phone_number']}"
                for r in records
            ]
        )

        # Preview mode — resolves and counts the audience exactly like a
        # real send would, but never creates a campaign or queues any
        # messages. Lets the dropdown filters be tested against real data
        # without touching a single lead's phone.
        if dry_run:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "status": "dry_run",
                    "total": len(phones),
                    "sample_phones": phones[:5],
                    "message": f"Dry run — {len(phones)} recipient(s) would be messaged. Nothing was sent.",
                },
            )

        all_templates = await asyncio.to_thread(get_all_templates) or []
        template_name = next(
            (t["elementName"] for t in all_templates if t.get("id") == template_id),
            template_id,
        )

        campaign_id = await asyncio.to_thread(
            create_campaign, template_id, template_name, phones
        )

        # If this template was created with a header image, it was saved in
        # MongoDB at creation time — build its public URL so the send
        # actually attaches the header image instead of silently failing.
        # Uses a hardcoded public domain rather than request.base_url, since
        # that can resolve to an internal address depending on how TLS
        # termination/proxying in front of the server is configured.
        from qlink_chatbot.utils.template_image import resolve_template_image_url

        image_url = await asyncio.to_thread(resolve_template_image_url, template_id)
        if image_url:
            logger.info(
                "Resolved header image for campaign trigger",
                extra={"template_id": template_id, "image_url": image_url},
            )

        # Send in the background instead of blocking this request — for a
        # large audience (e.g. "all leads"), sending one-by-one in-request
        # can take long enough to hit browser/proxy timeouts. The caller
        # polls GET /dashboard/campaigns/{campaign_id} for live progress.
        background_tasks.add_task(
            send_campaign_messages, campaign_id, phones, template_id, image_url
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "campaign_id": campaign_id,
                "total": len(records),
                "status": "queued",
                "message": "Campaign queued — check GET /dashboard/campaigns/{campaign_id} for live progress.",
            },
        )

    except Exception as e:
        logger.error("error occured while sending campaign", extra={"error": e})
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Error triggering campaign"},
        )


@dashboard_router.get("/campaigns")
async def fetch_all_campaigns(limit: int | None = None):
    """List campaigns with summary delivery stats. Optional ``limit`` for Home."""
    try:
        data = await asyncio.to_thread(get_all_campaigns, limit)
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error fetching campaigns", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error fetching campaigns"},
            status_code=500,
        )


@dashboard_router.get("/campaigns/{campaign_id}/export")
async def export_campaign_recipients(campaign_id: str, status: str = "all"):
    """CSV of all matching recipients — used only on Export click."""
    try:
        data = await asyncio.to_thread(
            get_campaign_recipients_csv, campaign_id, status
        )
        if not data:
            return JSONResponse(
                content={"success": False, "message": "Campaign not found"},
                status_code=404,
            )

        def cell(value):
            text = "" if value is None else str(value)
            if any(ch in text for ch in (",", '"', "\n")):
                return '"' + text.replace('"', '""') + '"'
            return text

        lines = ["Phone Number,Status,Reason"]
        for row in data["recipients"]:
            lines.append(
                ",".join(
                    [
                        cell(row.get("phone_number")),
                        cell(row.get("status")),
                        cell(row.get("error")),
                    ]
                )
            )
        filename = f"{data['template_name']}_{status}_{data['campaign_id']}.csv"
        return Response(
            content="\n".join(lines),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except Exception as e:
        logger.exception("Error exporting campaign", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error exporting campaign"},
            status_code=500,
        )


@dashboard_router.get("/campaigns/{campaign_id}")
async def fetch_campaign_by_id(
    campaign_id: str,
    page: int = 1,
    limit: int = 50,
    status: str = "all",
):
    """Campaign summary plus one page of recipients."""
    try:
        if limit > 100:
            limit = 100
        data = await asyncio.to_thread(
            get_campaign_by_id, campaign_id, page, limit, status
        )
        if not data:
            return JSONResponse(
                content={"success": False, "message": "Campaign not found"},
                status_code=404,
            )
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error fetching campaign", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error fetching campaign"},
            status_code=500,
        )


# 0 = test (next scheduler check). Positive = delay from when the user saves it.
SCHEDULE_OFFSET_DAYS = {0, 3, 5, 7, 10, 15, 30}
SCHEDULE_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleCreate(BaseModel):
    template_id: str
    template_name: str
    offset_days: int = 0
    send_time: str  # "HH:MM", IST
    category: str | None = None
    sub_category: str | None = None
    expiry_offset_days: int | None = None
    expiry_date: str | None = None
    schedule_type: str = "delay"
    send_date: str | None = None  # YYYY-MM-DD in IST, calendar pick
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    offset_days: int | None = None
    send_time: str | None = None
    category: str | None = None
    sub_category: str | None = None
    enabled: bool | None = None


def _validate_schedule_fields(offset_days: int, send_time: str) -> str | None:
    if offset_days not in SCHEDULE_OFFSET_DAYS:
        return f"offset_days must be one of {sorted(SCHEDULE_OFFSET_DAYS)}"
    if not SCHEDULE_TIME_RE.match(send_time):
        return "send_time must be in HH:MM 24-hour format"
    return None


@dashboard_router.post("/schedules")
async def create_schedule_route(payload: ScheduleCreate):
    """Creates a one-shot delayed send: this template fires once after
    offset_days (5 or 7) at send_time IST, to the chosen audience."""
    try:
        if payload.schedule_type == "expiry":
            if payload.expiry_offset_days is None and not payload.expiry_date:
                return JSONResponse(
                    content={"success": False, "message": "expiry schedule needs an expiry window or date"},
                    status_code=400,
                )
            if not SCHEDULE_TIME_RE.match(payload.send_time):
                return JSONResponse(
                    content={"success": False, "message": "send_time must be in HH:MM 24-hour format"},
                    status_code=400,
                )
        else:
            if payload.send_date:
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", payload.send_date):
                    return JSONResponse(
                        content={"success": False, "message": "send_date must be YYYY-MM-DD"},
                        status_code=400,
                    )
                if not SCHEDULE_TIME_RE.match(payload.send_time):
                    return JSONResponse(
                        content={"success": False, "message": "send_time must be in HH:MM 24-hour format"},
                        status_code=400,
                    )
            else:
                error = _validate_schedule_fields(payload.offset_days, payload.send_time)
                if error:
                    return JSONResponse(content={"success": False, "message": error}, status_code=400)

        schedule_id = await asyncio.to_thread(
            create_schedule,
            payload.template_id,
            payload.template_name,
            payload.offset_days,
            payload.send_time,
            payload.category,
            payload.sub_category,
            payload.expiry_offset_days,
            payload.expiry_date,
            payload.enabled,
            payload.schedule_type,
            payload.send_date,
        )
        return JSONResponse(
            content={"success": True, "data": {"schedule_id": schedule_id}},
            status_code=201,
        )
    except Exception as e:
        logger.exception("Error creating schedule", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error creating schedule"},
            status_code=500,
        )


@dashboard_router.get("/schedules")
async def fetch_schedules(template_id: str | None = None):
    try:
        data = await asyncio.to_thread(get_schedules, template_id)
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error fetching schedules", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error fetching schedules"},
            status_code=500,
        )


@dashboard_router.patch("/schedules/{schedule_id}")
async def update_schedule_route(schedule_id: str, payload: ScheduleUpdate):
    try:
        fields = payload.model_dump(exclude_unset=True)
        if "offset_days" in fields and fields["offset_days"] not in SCHEDULE_OFFSET_DAYS:
            return JSONResponse(
                content={"success": False, "message": f"offset_days must be one of {sorted(SCHEDULE_OFFSET_DAYS)}"},
                status_code=400,
            )
        if "send_time" in fields and not SCHEDULE_TIME_RE.match(fields["send_time"]):
            return JSONResponse(
                content={"success": False, "message": "send_time must be in HH:MM 24-hour format"},
                status_code=400,
            )

        updated = await asyncio.to_thread(
            lambda: update_schedule(schedule_id, **fields)
        )
        if not updated:
            return JSONResponse(
                content={"success": False, "message": "Schedule not found or no changes provided"},
                status_code=404,
            )
        return JSONResponse(content={"success": True}, status_code=200)
    except Exception as e:
        logger.exception("Error updating schedule", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error updating schedule"},
            status_code=500,
        )


@dashboard_router.delete("/schedules/{schedule_id}")
async def delete_schedule_route(schedule_id: str):
    try:
        deleted = await asyncio.to_thread(delete_schedule, schedule_id)
        if not deleted:
            return JSONResponse(
                content={"success": False, "message": "Schedule not found"},
                status_code=404,
            )
        return JSONResponse(content={"success": True}, status_code=200)
    except Exception as e:
        logger.exception("Error deleting schedule", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error deleting schedule"},
            status_code=500,
        )


@dashboard_router.get("/leads")
async def fetch_all_leads():
    try:
        data = await asyncio.to_thread(get_all_leads)
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error fetching leads", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error fetching leads"},
            status_code=500,
        )


@dashboard_router.get("/leads/stats")
@dashboard_router.get("/leads/categories")
async def fetch_lead_stats():
    try:
        data = await asyncio.to_thread(get_lead_stats)
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error fetching lead stats", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error fetching lead stats"},
            status_code=500,
        )


@dashboard_router.get("/leads/filtered")
async def fetch_filtered_leads(
    category: str | None = None,
    sub_category: str | None = None,
    source: str | None = None,
    pipeline: str | None = None,
    product: str | None = None,
    masterclass_id: str | None = None,
    whatsapp_ready: bool = True,
    no_number: bool = False,
    not_whatsapp_ready: bool = False,
    search: str = "",
    page: int = 1,
    limit: int = 25,
):
    """Paginated audience preview — same filter as campaign send.

    People page should pass ``whatsapp_ready=false`` to list everyone.
    """
    try:
        if limit > 100:
            limit = 100
        query = build_lead_query(
            category=category,
            sub_category=sub_category,
            pipeline=pipeline,
            product=product,
            source=source,
            masterclass_id=masterclass_id,
            whatsapp_ready_only=whatsapp_ready and not no_number and not not_whatsapp_ready,
            no_number_only=no_number,
            not_whatsapp_ready_only=not_whatsapp_ready and not no_number,
        )
        data = await asyncio.to_thread(
            get_filtered_leads, query, search, page, limit
        )
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error fetching filtered leads", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error fetching filtered leads"},
            status_code=500,
        )


@dashboard_router.get("/leads/{lead_id}")
async def fetch_lead_by_id(lead_id: str):
    """Full person profile including history — used by the People drawer."""
    try:
        data = await asyncio.to_thread(get_lead_by_id, lead_id)
        if not data:
            return JSONResponse(
                content={"success": False, "message": "Person not found"},
                status_code=404,
            )
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error fetching lead", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error fetching person"},
            status_code=500,
        )


class MasterclassCreate(BaseModel):
    title: str
    meeting_link: str
    notes: str | None = None
    activate: bool = False


class MasterclassUpdate(BaseModel):
    title: str | None = None
    meeting_link: str | None = None
    notes: str | None = None


@dashboard_router.get("/masterclasses")
async def fetch_masterclasses():
    try:
        data = await asyncio.to_thread(list_masterclasses)
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error listing masterclasses", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error listing masterclasses"},
            status_code=500,
        )


@dashboard_router.get("/masterclasses/{masterclass_id}/registrants")
async def fetch_masterclass_registrants(masterclass_id: str):
    try:
        data = await asyncio.to_thread(list_masterclass_registrants, masterclass_id)
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error listing masterclass registrants", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error listing registrants"},
            status_code=500,
        )


@dashboard_router.post("/masterclasses")
async def create_masterclass_route(payload: MasterclassCreate):
    title = (payload.title or "").strip()
    link = (payload.meeting_link or "").strip()
    if not title or not link:
        return JSONResponse(
            content={"success": False, "message": "Title and WhatsApp message are required"},
            status_code=400,
        )
    try:
        data = await asyncio.to_thread(
            create_masterclass,
            title,
            link,
            payload.notes,
            payload.activate,
        )
        return JSONResponse(content={"success": True, "data": data}, status_code=201)
    except Exception as e:
        logger.exception("Error creating masterclass", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error creating masterclass"},
            status_code=500,
        )


@dashboard_router.patch("/masterclasses/{masterclass_id}")
async def update_masterclass_route(masterclass_id: str, payload: MasterclassUpdate):
    try:
        data = await asyncio.to_thread(
            update_masterclass,
            masterclass_id,
            title=payload.title,
            meeting_link=payload.meeting_link,
            notes=payload.notes,
        )
        if not data:
            return JSONResponse(
                content={"success": False, "message": "Masterclass not found"},
                status_code=404,
            )
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error updating masterclass", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error updating masterclass"},
            status_code=500,
        )


@dashboard_router.post("/masterclasses/{masterclass_id}/activate")
async def activate_masterclass_route(masterclass_id: str):
    try:
        data = await asyncio.to_thread(set_active, masterclass_id)
        if not data:
            return JSONResponse(
                content={"success": False, "message": "Masterclass not found"},
                status_code=404,
            )
        return JSONResponse(content={"success": True, "data": data}, status_code=200)
    except Exception as e:
        logger.exception("Error activating masterclass", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error activating masterclass"},
            status_code=500,
        )


@dashboard_router.delete("/masterclasses/{masterclass_id}")
async def delete_masterclass_route(masterclass_id: str):
    try:
        ok, message = await asyncio.to_thread(delete_masterclass, masterclass_id)
        if not ok:
            status = 404 if "not found" in message.lower() else 400
            return JSONResponse(
                content={"success": False, "message": message},
                status_code=status,
            )
        return JSONResponse(content={"success": True, "message": message}, status_code=200)
    except Exception as e:
        logger.exception("Error deleting masterclass", extra={"exception": e})
        return JSONResponse(
            content={"success": False, "message": "Error deleting masterclass"},
            status_code=500,
        )

