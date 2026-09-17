import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from qlink_chatbot.database.collections import (
    idac,
    campaigns,
    leads,
    template_images,
    campaign_schedules,
)
from qlink_chatbot.database.leads import (
    get_all_leads,
    get_filtered_leads,
    get_lead_stats,
    build_lead_query,
    import_coachee_json,
)
from qlink_chatbot.utils.format_chathistory import format_assistant, format_user
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.utils.phone import normalize_wa_phone

from uuid import uuid4


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def mongo_search(query, collection):
    """Executes a MongoDB search based on a given query."""
    try:
        logger.debug("Executing MongoDB search", extra={"query": query})
        results = list(collection.find(query))
        logger.info("Found results of length", extra={"length": len(results)})
        return results

    except Exception as e:
        logger.exception("MongoDB search failed:", extra={"exception": e})
        raise e


def append_chat_entries(
    phone_number: str,
    entries: list,
    username: str | None = None,
):
    """Append standalone chat rows (user and/or assistant) without rewriting history."""
    phone_number = normalize_wa_phone(phone_number) or phone_number
    if not phone_number or not entries:
        return
    now = datetime.now(timezone.utc)
    rows = []
    for entry in entries:
        row = dict(entry)
        row.setdefault("at", now)
        rows.append(row)
    update: dict = {
        "$push": {"chat_history": {"$each": rows}},
        "$set": {
            "updated_at": now,
            "phone_number": phone_number,
        },
        "$setOnInsert": {
            "created_at": now,
            "service_selected": None,
        },
    }
    if username:
        update["$set"]["username"] = username
    idac.update_one({"phone_number": phone_number}, update, upsert=True)


def ensure_user_thread(phone_number: str, username: str | None = None):
    """Create an empty inbox thread so quiz leads show up before they message."""
    phone_number = normalize_wa_phone(phone_number) or phone_number
    if not phone_number:
        return
    now = datetime.now(timezone.utc)
    update = {
        "$set": {"updated_at": now, "phone_number": phone_number},
        "$setOnInsert": {
            "created_at": now,
            "chat_history": [],
            "service_selected": None,
        },
    }
    if username:
        update["$set"]["username"] = username
    idac.update_one({"phone_number": phone_number}, update, upsert=True)


def _history_sort_key(msg: dict):
    at = msg.get("at") if isinstance(msg, dict) else None
    if isinstance(at, datetime):
        return at
    return datetime.min.replace(tzinfo=timezone.utc)


def merge_split_user_threads() -> dict:
    """Collapse 9820… / 919820… (and UAE short vs 971…) into one users doc."""
    groups = defaultdict(list)
    for doc in idac.find({}):
        raw = doc.get("phone_number") or ""
        key = normalize_wa_phone(raw) or raw
        if not key:
            continue
        groups[key].append(doc)

    rewritten = 0
    merged = 0
    for key, docs in groups.items():
        docs.sort(
            key=lambda d: d.get("created_at")
            or d.get("updated_at")
            or datetime.min.replace(tzinfo=timezone.utc)
        )
        keeper = docs[0]
        if len(docs) == 1:
            if keeper.get("phone_number") != key:
                idac.update_one(
                    {"_id": keeper["_id"]},
                    {"$set": {"phone_number": key}},
                )
                rewritten += 1
            continue
        history = []
        username = keeper.get("username")
        for doc in docs:
            history.extend(doc.get("chat_history") or [])
            if not username:
                username = doc.get("username")
        history.sort(key=_history_sort_key)
        now = datetime.now(timezone.utc)
        set_fields = {
            "phone_number": key,
            "chat_history": history,
            "updated_at": now,
        }
        if username:
            set_fields["username"] = username
        idac.update_one({"_id": keeper["_id"]}, {"$set": set_fields})
        extra_ids = [d["_id"] for d in docs[1:]]
        if extra_ids:
            idac.delete_many({"_id": {"$in": extra_ids}})
        merged += 1
    if rewritten or merged:
        logger.info(
            "Merged split inbox threads",
            extra={"rewritten": rewritten, "merged_groups": merged},
        )
    return {"rewritten": rewritten, "merged_groups": merged}


def update_outbound_chat_status(
    message_ids: list[str],
    status: str,
    error_reason: str | None = None,
    whatsapp_message_id: str | None = None,
):
    """Set status on outbound bubbles keyed by Gupshup / WhatsApp message id."""
    ids = [i for i in message_ids if i]
    if not ids or not status:
        return
    now = datetime.now(timezone.utc)
    set_fields = {
        "chat_history.$[elem].status": status,
        "updated_at": now,
    }
    if error_reason:
        set_fields["chat_history.$[elem].error"] = error_reason
    if whatsapp_message_id:
        set_fields["chat_history.$[elem].whatsapp_message_id"] = whatsapp_message_id
    for field in ("gupshup_message_id", "whatsapp_message_id"):
        idac.update_many(
            {f"chat_history.{field}": {"$in": ids}},
            {"$set": set_fields},
            array_filters=[{f"elem.{field}": {"$in": ids}}],
        )


def save_to_mongo(data):
    """Append inbound user text and any bot auto-reply as separate chat rows."""
    phone_number = data.get("phone_number")
    try:
        logger.info(
            "Request received to save user profile with data",
            extra={"phone_number": phone_number},
        )
        query = data["messages"]
        assistant = data["bot_response"] if "bot_response" in data else None
        now = datetime.now(timezone.utc)
        entries = []
        user_content = format_user(user_message=query, phone_number=phone_number)
        if user_content and str(user_content).strip():
            entries.append(
                {
                    "role": "user",
                    "content": user_content,
                    "at": now,
                }
            )
        if assistant:
            assistant_content = format_assistant(assistant, phone_number)
            if assistant_content and str(assistant_content).strip():
                entries.append(
                    {
                        "role": "assistant",
                        "content": assistant_content,
                        "at": now,
                        "status": "submitted",
                    }
                )
        append_chat_entries(
            phone_number,
            entries,
            username=data.get("whatsapp_username") or None,
        )
        logger.info(
            "User profile saved successfully",
            extra={"phone_number": phone_number},
        )
        return get_user_profile(phone_number)
    except Exception as e:
        logger.exception(
            "MongoDB save failed:",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise e
    


def save_user_profile(phone_number: str, profile_data: dict):
    """Saves data to user profile collection."""
    try:
        logger.info(
            "Request received to save user profile with data",
            extra={"profile_data": profile_data, "phone_number": phone_number},
        )
        profile_data["created_at"] = datetime.now(timezone.utc)
        profile_data["updated_at"] = datetime.now(timezone.utc)

        response = idac.find_one_and_update(
            {"phone_number": phone_number},
            {"$set": profile_data},
            upsert=True,  # Insert if document doesn't exist
            return_document=True,
        )

        logger.info(
            "User profile saved successfully",
            extra={
                "response_id": response.get("_id"),
                "phone_number": phone_number,
            },
        )
        response.pop("_id")
        return response
    except Exception as e:
        logger.exception(
            "MongoDB save failed:",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise e


def get_user_profile(phone_number: str):
    """Get User Profile data."""
    try:
        phone_number = normalize_wa_phone(phone_number) or phone_number
        profile = idac.find_one({"phone_number": phone_number})

        if not profile:
            logger.exception(
                "No profile exists for phone number.",
                extra={"phone_number": phone_number},
            )
            return None

        return profile
    except Exception as e:
        logger.exception(
            "Exception occured while fetching user profile.",
            extra={"phone_number": phone_number},
        )
        raise e


def get_doc_by_id(doc_id: str):
    """Fetch a document by its _id and return a clean structured dict."""
    try:
        doc = idac.find_one({"_id": ObjectId(doc_id)})
        if not doc:
            logger.warning(
                "No document found for given ID", extra={"_id": doc_id}
            )
            return None

        new_doc = {
            "_id": str(doc["_id"]),
            "phone_number": doc.get("phone_number", ""),
            "username": doc.get("username", ""),
            "chat_history": _json_safe(doc.get("chat_history", [])),
            "service_selected": doc.get("service_selected", ""),
            "updated_at": (
                doc["updated_at"].isoformat()
                if isinstance(doc.get("updated_at"), datetime)
                else doc.get("updated_at")
            ),
            "find_doctor": doc.get("Find a Doctor", 0),
            "direction": doc.get("Direction", 0),
            "contact_us": doc.get("Contact Us", 0),
            "book_an_appointment": doc.get("Book an Appointment", 0),
            "other": doc.get("Other", 0),
        }

        return new_doc

    except Exception as e:
        logger.exception(
            "Error fetching document by ID",
            extra={"exception": e, "_id": doc_id},
        )
        raise e


def get_all_docs():
    """Return all docs."""
    try:
        docs = list(
            idac.find(
                {},
                {
                    "_id": 1,
                    "phone_number": 1,
                    "updated_at": 1,
                    "username": 1,
                    "chat_history": 1,
                },
            ).sort("updated_at", -1)
        )
        for doc in docs:
            doc["_id"] = str(doc["_id"])
            doc["updated_at"] = (
                doc["updated_at"].isoformat()
                if isinstance(doc.get("updated_at"), datetime)
                else doc.get("updated_at")
            )
            doc["total_interaction"] = len(doc.get("chat_history", [])) // 2
            doc.pop("chat_history", None)
        return docs
    except Exception as e:
        logger.exception(
            "Error fetching all document summaries", extra={"exception": e}
        )
        raise e
    
# get all docs
def get_all_docs_dashboard(page: int = 1, limit: int = 20, search: str = ""):
    """Return paginated inbox rows without pulling chat_history arrays."""
    try:
        page = max(int(page or 1), 1)
        limit = min(max(int(limit or 20), 1), 100)
        skip = (page - 1) * limit

        query = {}
        if search and search.strip():
            pattern = {"$regex": search.strip(), "$options": "i"}
            query = {
                "$or": [
                    {"username": pattern},
                    {"phone_number": pattern},
                ]
            }

        total_docs = idac.count_documents(query)
        total_pages = (total_docs + limit - 1) // limit if limit else 0

        pipeline = [
            {"$match": query} if query else {"$match": {}},
            {"$sort": {"updated_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 1,
                    "phone_number": 1,
                    "updated_at": 1,
                    "username": 1,
                    "total_interaction": {
                        "$toInt": {
                            "$divide": [
                                {
                                    "$cond": [
                                        {"$isArray": "$chat_history"},
                                        {"$size": "$chat_history"},
                                        0,
                                    ]
                                },
                                2,
                            ]
                        }
                    },
                }
            },
        ]
        docs = list(idac.aggregate(pipeline))

        for doc in docs:
            doc["_id"] = str(doc["_id"])
            doc["updated_at"] = (
                doc["updated_at"].isoformat()
                if isinstance(doc.get("updated_at"), datetime)
                else doc.get("updated_at")
            )

        return {
            "page": page,
            "limit": limit,
            "total_docs": total_docs,
            "total_pages": total_pages,
            "docs": docs,
        }

    except Exception as e:
        logger.exception(
            "Error fetching all document summaries",
            extra={"exception": e}
        )
        raise e

# get recent docs  
def get_recent_docs(limit: int = 5):
    """Return the most recent docs."""
    try:
        docs = list(
            idac.find(
                {},
                {
                    "_id": 1,
                    "phone_number": 1,
                    "updated_at": 1,
                    "username": 1,
                    "chat_history": 1,
                },
            )
            .sort("updated_at", -1)
            .limit(limit)
        )

        for doc in docs:
            doc["_id"] = str(doc["_id"])
            doc["updated_at"] = (
                doc["updated_at"].isoformat()
                if isinstance(doc.get("updated_at"), datetime)
                else doc.get("updated_at")
            )
            doc["total_interaction"] = len(doc.get("chat_history", [])) // 2
            doc.pop("chat_history", None)

        return docs

    except Exception as e:
        logger.exception(
            "Error fetching recent docs", extra={"exception": e}
        )
        raise e




    




    
    








    



    
    



 
    





    
    




    








# ──────────────────────────────────────────────
# Session Utilities
# ──────────────────────────────────────────────











# question metadata from the WhatsApp flow
FEEDBACK_QUESTIONS = {
    "q1": {
        "label": "Was this worth your time?",
        "options": ["0_Absolutely", "1_Somewhat", "2_Not_enough_valueion"],
    },
    "q2": {
        "label": "Practical, actionable insights",
        "options": ["0_Yes", "1_Partly", "2_No"],
    },
    "q3": {
        "label": "Go deeper next PACC?",
        "options": [
            "0_Yes_–_Full_Session_Needed",
            "1_Maybe_–_Breakout_Format",
            "2_Prefer_New_Topic",
        ],
    },
}










# ──────────────────────────────────────────────
# Campaign Analytics
# ──────────────────────────────────────────────

def _default_recipient(phone: str) -> dict:
    return {
        "phone_number": phone,
        "status": "pending",
        "gupshup_message_id": None,
        "whatsapp_message_id": None,
        "error": None,
        "failed_at": None,
        "retry_at": None,
        "retry_count": 0,
        "last_attempt_at": None,
        "retry_in_progress": False,
        "attempts": [],
        "mc_nudge_due_at": None,
        "mc_nudge_sent_at": None,
        "mc_nudge_in_progress": False,
    }


def create_campaign(
    template_id: str,
    template_name: str,
    recipients: list,
    *,
    masterclass_nudge_enabled: bool = False,
) -> str:
    """Creates a campaign record with one pending entry per recipient phone number."""
    campaign_id = str(uuid4())
    campaigns.insert_one({
        "campaign_id": campaign_id,
        "template_id": template_id,
        "template_name": template_name,
        "masterclass_nudge_enabled": masterclass_nudge_enabled,
        "retry_policy": {"enabled": True, "delay_hours": 3},
        "recipients": [_default_recipient(phone) for phone in recipients],
        "created_at": datetime.now(timezone.utc),
    })
    return campaign_id


def _clear_stale_broadcast_mc_nudges(phone_number: str, except_campaign_id: str) -> None:
    """Drop pending 24h nudges from older campaigns so only the latest broadcast schedules."""
    campaigns.update_many(
        {
            "campaign_id": {"$ne": except_campaign_id},
            "recipients": {
                "$elemMatch": {
                    "phone_number": phone_number,
                    "mc_nudge_due_at": {"$exists": True, "$ne": None},
                    "$or": [
                        {"mc_nudge_sent_at": {"$exists": False}},
                        {"mc_nudge_sent_at": None},
                    ],
                }
            },
        },
        {
            "$unset": {"recipients.$[r].mc_nudge_due_at": ""},
            "$set": {"recipients.$[r].mc_nudge_in_progress": False},
        },
        array_filters=[
            {
                "r.phone_number": phone_number,
                "$or": [
                    {"r.mc_nudge_sent_at": {"$exists": False}},
                    {"r.mc_nudge_sent_at": None},
                ],
            }
        ],
    )


def schedule_campaign_mc_nudge(
    campaign_id: str,
    phone_number: str,
    sent_at: datetime,
) -> None:
    """Schedule a one-time 24h broadcast masterclass reminder for a recipient."""
    _clear_stale_broadcast_mc_nudges(phone_number, campaign_id)
    due_at = sent_at + timedelta(hours=24)
    campaigns.update_one(
        {"campaign_id": campaign_id, "recipients.phone_number": phone_number},
        {
            "$set": {
                "recipients.$.mc_nudge_due_at": due_at,
                "recipients.$.mc_nudge_sent_at": None,
                "recipients.$.mc_nudge_in_progress": False,
            }
        },
    )


def set_campaign_recipient_sent(
    campaign_id: str,
    phone_number: str,
    message_id: str,
    success: bool,
    error: str | None = None,
):
    """Records the outcome of sending a single campaign message.

    ``error`` is Gupshup's rejection reason at submit time (e.g. invalid
    template id, malformed destination) — kept alongside the later
    delivery-webhook failure reason so a "failed" status is never a dead
    end when diagnosing why a send didn't go through.
    """
    set_fields = {
        "recipients.$.status": "sent" if success else "failed",
        "recipients.$.gupshup_message_id": message_id,
    }
    if error:
        set_fields["recipients.$.error"] = error

    campaigns.update_one(
        {"campaign_id": campaign_id, "recipients.phone_number": phone_number},
        {"$set": set_fields},
    )
    if not success:
        from qlink_chatbot.utils.campaign_retry import schedule_recipient_retry

        schedule_recipient_retry(
            campaign_id,
            phone_number,
            error,
            failure_status="failed",
        )


def update_campaign_recipient_status(
    message_id: str,
    status: str,
    whatsapp_message_id: str | None = None,
    error_reason: str | None = None,
) -> bool:
    """Updates a recipient's delivery status by Gupshup/WhatsApp message id."""
    from qlink_chatbot.database.campaign_analytics import (
        update_campaign_recipient_status as _update,
    )

    return _update(
        message_id,
        status,
        whatsapp_message_id=whatsapp_message_id,
        error_reason=error_reason,
    )


def _serialize_campaign_recipient(rec: dict) -> dict:
    """JSON-safe campaign recipient row (mc_nudge_*, retry_*, etc.)."""
    row = dict(rec)
    for key, val in list(row.items()):
        if isinstance(val, datetime):
            row[key] = val.isoformat()
    return row


def _parse_recipient_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _campaign_stats(recipients: list) -> dict:
    total = len(recipients)
    delivered = sum(1 for r in recipients if r["status"] in ("delivered", "read"))
    read = sum(1 for r in recipients if r["status"] == "read")
    failed = sum(1 for r in recipients if r["status"] in ("failed", "undelivered"))
    now = datetime.now(timezone.utc)
    retry_pending = 0
    for r in recipients:
        if r.get("status") not in ("failed", "undelivered"):
            continue
        retry_at = _parse_recipient_dt(r.get("retry_at"))
        if retry_at and retry_at > now:
            retry_pending += 1

    return {
        "total": total,
        "delivered": delivered,
        "read": read,
        "failed": failed,
        "retry_pending": retry_pending,
        "delivery_rate": round(delivered / total * 100, 1) if total else 0,
        "read_rate": round(read / total * 100, 1) if total else 0,
    }


def get_all_campaigns(limit: int | None = None):
    """Returns campaigns with summary stats, latest first. Optional ``limit``."""
    cursor = campaigns.find({}).sort("created_at", -1)
    if limit is not None:
        cursor = cursor.limit(max(int(limit), 1))
    docs = list(cursor)
    result = []
    for doc in docs:
        stats = _campaign_stats(doc.get("recipients", []))
        created_at = doc.get("created_at")
        result.append({
            "campaign_id": doc["campaign_id"],
            "template_name": doc.get("template_name"),
            "created_at": created_at.isoformat()
            if isinstance(created_at, datetime)
            else created_at,
            **stats,
        })
    return result


def _filter_campaign_recipients(recipients: list, status: str | None) -> list:
    if not status or status == "all":
        return recipients
    return [r for r in recipients if r.get("status") == status]


def get_campaign_by_id(
    campaign_id: str,
    page: int = 1,
    limit: int = 50,
    status: str = "all",
):
    """Campaign detail with stats over all recipients and a paginated table page."""
    doc = campaigns.find_one({"campaign_id": campaign_id}, {"_id": 0})
    if not doc:
        return None

    recipients = doc.get("recipients") or []
    doc["stats"] = _campaign_stats(recipients)
    if isinstance(doc.get("created_at"), datetime):
        doc["created_at"] = doc["created_at"].isoformat()

    filtered = _filter_campaign_recipients(recipients, status)
    page = max(int(page or 1), 1)
    limit = min(max(int(limit or 50), 1), 100)
    skip = (page - 1) * limit
    serialized = [
        _serialize_campaign_recipient(rec)
        for rec in filtered[skip : skip + limit]
    ]
    doc["recipients"] = serialized
    doc["recipients_total"] = len(filtered)
    doc["page"] = page
    doc["limit"] = limit
    doc["status_filter"] = status or "all"
    return doc


def get_campaign_recipients_csv(campaign_id: str, status: str = "all"):
    """All matching recipients for CSV download — not paginated."""
    doc = campaigns.find_one(
        {"campaign_id": campaign_id},
        {"_id": 0, "recipients": 1, "template_name": 1, "campaign_id": 1},
    )
    if not doc:
        return None
    rows = _filter_campaign_recipients(doc.get("recipients") or [], status)
    return {
        "campaign_id": doc.get("campaign_id"),
        "template_name": doc.get("template_name") or "campaign",
        "recipients": rows,
    }


def _run_after_from_ist(send_date: str, send_time: str) -> datetime:
    """Build a UTC datetime from an IST calendar date + HH:MM."""
    from zoneinfo import ZoneInfo

    ist = ZoneInfo("Asia/Kolkata")
    year, month, day = (int(part) for part in send_date.split("-"))
    hour, minute = (int(part) for part in send_time.split(":"))
    return datetime(year, month, day, hour, minute, tzinfo=ist).astimezone(
        timezone.utc
    )


def create_schedule(
    template_id: str,
    template_name: str,
    offset_days: int,
    send_time: str,
    category: str | None = None,
    sub_category: str | None = None,
    expiry_offset_days: int | None = None,
    expiry_date: str | None = None,
    enabled: bool = True,
    schedule_type: str = "delay",
    send_date: str | None = None,
) -> str:
    """Creates a campaign schedule.

    ``delay``: fires once after 5/7 days (or 0 = test in ~1 minute).
    ``expiry``: fires every day at send_time to whoever matches the
    expiry window — until the user stops it.
    """
    schedule_id = str(uuid4())
    is_expiry = schedule_type == "expiry"
    if is_expiry:
        run_after = None
        is_test = False
        stored_time = send_time
    elif send_date:
        run_after = _run_after_from_ist(send_date, send_time)
        is_test = False
        stored_time = send_time
    else:
        delay = (
            timedelta(minutes=1)
            if int(offset_days) == 0
            else timedelta(days=int(offset_days))
        )
        run_after = datetime.now(timezone.utc) + delay
        is_test = int(offset_days) == 0
        stored_time = "00:00" if is_test else send_time
    campaign_schedules.insert_one({
        "schedule_id": schedule_id,
        "template_id": template_id,
        "template_name": template_name,
        "schedule_type": "expiry" if is_expiry else "delay",
        "offset_days": offset_days,
        "send_time": stored_time,
        "send_date": send_date,
        "category": category,
        "sub_category": sub_category,
        "expiry_offset_days": expiry_offset_days,
        "expiry_date": expiry_date,
        "enabled": enabled,
        "is_test": is_test,
        "created_at": datetime.now(timezone.utc),
        "run_after": run_after,
        "last_run_date": None,
        "last_campaign_id": None,
    })
    return schedule_id


def ensure_expiry_schedule(
    template_id: str,
    template_name: str,
    category: str | None,
    sub_category: str | None,
    expiry_offset_days: int | None,
    expiry_date: str | None,
    send_time: str = "10:00",
) -> str | None:
    """Starts (or reuses) a daily expiry auto-send for this template/audience."""
    if expiry_offset_days is None and not expiry_date:
        return None
    query = {
        "template_id": template_id,
        "schedule_type": "expiry",
        "enabled": True,
        "category": category,
        "sub_category": sub_category,
        "expiry_offset_days": expiry_offset_days,
        "expiry_date": expiry_date,
    }
    existing = campaign_schedules.find_one(query, {"schedule_id": 1})
    if existing:
        return existing["schedule_id"]
    return create_schedule(
        template_id=template_id,
        template_name=template_name,
        offset_days=0,
        send_time=send_time,
        category=category,
        sub_category=sub_category,
        expiry_offset_days=expiry_offset_days,
        expiry_date=expiry_date,
        schedule_type="expiry",
    )


def expiry_offset_from_template_name(name: str) -> int | None:
    """Map names like ``3_days_before_expiry`` to a daily expiry offset."""
    raw = (name or "").lower().replace(" ", "_").replace("-", "_")
    if "expir" not in raw:
        return None
    if "today" in raw:
        return 0
    match = re.search(r"(\d+)_*days?_*(before|after)", raw)
    if not match:
        match = re.search(r"(\d+).*?(before|after).*expir", raw)
    if not match:
        return None
    days = int(match.group(1))
    # before expiry → valid_till is in the future; after → in the past
    return days if match.group(2) == "before" else -days


def sync_expiry_jobs_from_templates() -> int:
    """No-op: Sanjeet has no membership expiry auto-sends."""
    return 0


def get_schedules(template_id: str | None = None):
    """Lists schedules, optionally filtered to one template."""
    query = {"template_id": template_id} if template_id else {}
    docs = list(campaign_schedules.find(query, {"_id": 0}).sort("created_at", -1))
    for doc in docs:
        created_at = doc.get("created_at")
        if isinstance(created_at, datetime):
            doc["created_at"] = created_at.isoformat()
        run_after = doc.get("run_after")
        if isinstance(run_after, datetime):
            doc["run_after"] = run_after.isoformat()
    return docs


def update_schedule(schedule_id: str, **fields) -> bool:
    """Updates whichever schedule fields are provided (partial update)."""
    allowed = {"offset_days", "send_time", "category", "sub_category", "enabled"}
    set_fields = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not set_fields:
        return False
    result = campaign_schedules.update_one(
        {"schedule_id": schedule_id}, {"$set": set_fields}
    )
    return result.matched_count > 0


def delete_schedule(schedule_id: str) -> bool:
    result = campaign_schedules.delete_one({"schedule_id": schedule_id})
    return result.deleted_count > 0


def get_due_schedules(now_ist: datetime):
    """Delay jobs fire once after run_after. Expiry jobs fire daily at send_time."""
    current_hm = now_ist.strftime("%H:%M")
    today_str = now_ist.strftime("%Y-%m-%d")
    now_utc = now_ist.astimezone(timezone.utc)
    delay_due = list(
        campaign_schedules.find({
            "enabled": True,
            "last_run_date": None,
            "schedule_type": {"$ne": "expiry"},
            "$and": [
                {
                    "$or": [
                        {"run_after": {"$lte": now_utc}},
                        {"run_after": {"$exists": False}},
                    ]
                },
                {
                    "$or": [
                        {"is_test": True},
                        {"send_time": {"$lte": current_hm}},
                    ]
                },
            ],
        })
    )
    expiry_due = list(
        campaign_schedules.find({
            "enabled": True,
            "schedule_type": "expiry",
            "send_time": {"$lte": current_hm},
            "last_run_date": {"$ne": today_str},
        })
    )
    return delay_due + expiry_due


def mark_schedule_run(schedule_id: str, campaign_id: str | None, run_date: str):
    campaign_schedules.update_one(
        {"schedule_id": schedule_id},
        {"$set": {"last_run_date": run_date, "last_campaign_id": campaign_id}},
    )










# ──────────────────────────────────────────────
# Template Header Images
# ──────────────────────────────────────────────

def save_template_image(
    template_id: str, filename: str, content_type: str, data: bytes
):
    """Stores a template's header image in MongoDB.

    Vercel's filesystem is ephemeral/read-only at runtime, so images can't
    be saved to local disk like on a persistent server — they need to live
    somewhere external that survives between requests.
    """
    template_images.update_one(
        {"template_id": template_id},
        {
            "$set": {
                "filename": filename,
                "content_type": content_type,
                "data": data,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


def get_template_image(template_id: str):
    """Returns {"content_type": str, "data": bytes} or None if not stored."""
    doc = template_images.find_one({"template_id": template_id})
    if not doc:
        return None
    return {
        "content_type": doc.get("content_type", "image/jpeg"),
        "data": doc["data"],
    }