"""Coachee people: query helpers and JSON import (one doc per phone)."""

from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from qlink_chatbot.database.collections import idac, leads
from qlink_chatbot.utils.logger_config import logger
from qlink_chatbot.utils.phone import (
    normalize_wa_phone,
    pick_sendable_phone,
)

WA_READY_CLASSES = {
    "india_10",
    "india_91",
    "india_leading_zero",
    "uae",
}

PIPELINE_VALUES = {
    "converted",
    "nurture",
    "unknown",
    "not_now",
    "attended",
    "no_show",
    "discontinued",
}


def map_pipeline(status: str | None) -> str:
    if not status:
        return "unknown"
    s = status.lower()
    if "discontinu" in s:
        return "discontinued"
    if "converted" in s:
        return "converted"
    if "no show" in s:
        return "no_show"
    if "attended" in s or "atteneded" in s:
        return "attended"
    if any(
        x in s
        for x in (
            "not interested",
            "not for now",
            "reject",
            "above budget",
            "can't afford",
            "cant afford",
            "doesn't have budget",
            "doesnt have budget",
            "needed a pure",
            "just wanted free",
            "chose to continue therapy",
            "sanjeet not interested",
        )
    ):
        return "not_now"
    return "nurture"


def canonicalize_product(raw: str | None) -> list[str]:
    if not raw:
        return []
    tags = []
    seen = set()
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        pl = p.lower()
        if "fulfil" in pl or "fulfill" in pl:
            key = "The Fulfilment Project"
        elif pl in ("masterclass", "free masterclass"):
            key = "Free Masterclass"
        elif "evolve+" in pl:
            key = "Evolve+"
        elif pl == "evolve":
            key = "Evolve"
        else:
            key = p
        if key not in seen:
            seen.add(key)
            tags.append(key)
    return tags


def is_whatsapp_ready(phone_class: str | None) -> bool:
    return phone_class in WA_READY_CLASSES


def build_lead_query(
    category: str | None = None,
    sub_category: str | None = None,
    pipeline: str | None = None,
    product: str | None = None,
    source: str | None = None,
    masterclass_id: str | None = None,
    whatsapp_ready_only: bool = False,
    no_number_only: bool = False,
    not_whatsapp_ready_only: bool = False,
    expiry_offset_days: int | None = None,
    expiry_date: str | None = None,
) -> dict:
    """Shared filter for Leads UI, campaign preview, and scheduled sends.

    ``category`` is treated as pipeline (all_leads = everyone matching
    the other filters). ``sub_category`` is treated as product tag.
    Expiry args are ignored — FSAI membership dates are gone.
    """
    query: dict = {}
    pipe = pipeline or category
    if pipe and pipe not in ("all_leads", "all", ""):
        query["pipeline"] = pipe
    prod = product or sub_category
    if prod:
        query["products"] = prod
    if source:
        query["source"] = source
    if masterclass_id:
        query["masterclass_registrations.masterclass_id"] = masterclass_id
    if no_number_only:
        query["$or"] = [
            {"contact_number": {"$exists": False}},
            {"contact_number": None},
            {"contact_number": ""},
        ]
    elif not_whatsapp_ready_only:
        query["whatsapp_ready"] = {"$ne": True}
        query["contact_number"] = {"$nin": [None, ""]}
    elif whatsapp_ready_only:
        query["whatsapp_ready"] = True
        query["contact_number"] = {"$nin": [None, ""]}
    return query


def _engagement_event(
    event_type: str,
    at: datetime,
    *,
    masterclass_id: str | None = None,
    title: str | None = None,
    label: str | None = None,
) -> dict:
    event = {"type": event_type, "at": at}
    if label:
        event["label"] = label
    if masterclass_id:
        event["masterclass_id"] = masterclass_id
    if title:
        event["title"] = title
    return event


def _serialize_lead(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("_id", None)
    for field in ("created_at", "updated_at", "masterclass_registered_at"):
        value = doc.get(field)
        if isinstance(value, datetime):
            doc[field] = value.isoformat()
    regs = doc.get("masterclass_registrations")
    if isinstance(regs, list):
        cleaned = []
        for row in regs:
            if not isinstance(row, dict):
                cleaned.append(row)
                continue
            item = dict(row)
            at = item.get("registered_at")
            if isinstance(at, datetime):
                item["registered_at"] = at.isoformat()
            cleaned.append(item)
        doc["masterclass_registrations"] = cleaned
    engagement = doc.get("engagement")
    if isinstance(engagement, list):
        cleaned_eng = []
        for row in engagement:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            at = item.get("at")
            if isinstance(at, datetime):
                item["at"] = at.isoformat()
            cleaned_eng.append(item)
        cleaned_eng.sort(key=lambda e: e.get("at") or "", reverse=True)
        doc["engagement"] = cleaned_eng
    return doc


def get_all_leads():
    docs = list(leads.find({}, {"_id": 0, "history": 0}))
    docs.sort(key=lambda d: (d.get("name") or "zzz").lower())
    return [_serialize_lead(doc) for doc in docs]


def get_lead_by_id(lead_id: str):
    if not lead_id:
        return None
    doc = leads.find_one({"lead_id": lead_id}, {"_id": 0})
    return _serialize_lead(doc) if doc else None


def get_filtered_leads(query: dict, search: str = "", page: int = 1, limit: int = 25):
    parts = [query] if query else []
    if search:
        pattern = {"$regex": search, "$options": "i"}
        parts.append(
            {
                "$or": [
                    {"name": pattern},
                    {"email": pattern},
                    {"contact_number": pattern},
                    {"contact_numbers": pattern},
                    {"aka": pattern},
                ]
            }
        )
    if len(parts) > 1:
        full_query = {"$and": parts}
    else:
        full_query = parts[0] if parts else {}

    total = leads.count_documents(full_query)
    skip = max(page - 1, 0) * limit
    docs = list(
        leads.find(full_query, {"_id": 0, "history": 0})
        .sort([("name", 1)])
        .skip(skip)
        .limit(limit)
    )
    return {
        "leads": [_serialize_lead(doc) for doc in docs],
        "total": total,
        "page": page,
        "limit": limit,
    }


def _facet_count(bucket: list) -> int:
    return bucket[0]["n"] if bucket else 0


def get_lead_stats():
    pipeline = [
        {
            "$facet": {
                "total": [{"$count": "n"}],
                "pipelines": [
                    {
                        "$group": {
                            "_id": {"$ifNull": ["$pipeline", "unknown"]},
                            "n": {"$sum": 1},
                        }
                    }
                ],
                "whatsapp_ready": [
                    {"$match": {"whatsapp_ready": True}},
                    {"$count": "n"},
                ],
                "no_number": [
                    {
                        "$match": {
                            "$or": [
                                {"contact_number": {"$exists": False}},
                                {"contact_number": None},
                                {"contact_number": ""},
                            ]
                        }
                    },
                    {"$count": "n"},
                ],
                "not_whatsapp_ready": [
                    {
                        "$match": {
                            "whatsapp_ready": {"$ne": True},
                            "contact_number": {"$nin": [None, ""]},
                        }
                    },
                    {"$count": "n"},
                ],
                "products": [
                    {
                        "$unwind": {
                            "path": "$products",
                            "preserveNullAndEmptyArrays": False,
                        }
                    },
                    {"$group": {"_id": "$products", "n": {"$sum": 1}}},
                ],
                "sources": [
                    {
                        "$group": {
                            "_id": {
                                "$cond": [
                                    {
                                        "$or": [
                                            {"$eq": ["$source", None]},
                                            {"$eq": ["$source", ""]},
                                        ]
                                    },
                                    "(blank)",
                                    "$source",
                                ]
                            },
                            "n": {"$sum": 1},
                        }
                    }
                ],
            }
        }
    ]
    rows = list(leads.aggregate(pipeline))
    facet = rows[0] if rows else {}
    pipelines = {d["_id"] or "unknown": d["n"] for d in facet.get("pipelines") or []}
    products = {d["_id"]: d["n"] for d in facet.get("products") or [] if d.get("_id")}
    sources = {d["_id"] or "(blank)": d["n"] for d in facet.get("sources") or []}
    return {
        "total": _facet_count(facet.get("total") or []),
        "whatsapp_ready": _facet_count(facet.get("whatsapp_ready") or []),
        "converted": pipelines.get("converted", 0),
        "nurture": pipelines.get("nurture", 0),
        "no_number": _facet_count(facet.get("no_number") or []),
        "not_whatsapp_ready": _facet_count(facet.get("not_whatsapp_ready") or []),
        "pipelines": pipelines,
        "products": dict(sorted(products.items(), key=lambda kv: -kv[1])),
        "sources": dict(sorted(sources.items(), key=lambda kv: -kv[1])),
    }


def _row_sort_key(row: dict):
    return (row.get("date") or "", row.get("excel_row") or 0)


def _person_from_rows(rows: list[dict], now: datetime) -> dict:
    rows_sorted = sorted(rows, key=_row_sort_key)
    latest = rows_sorted[-1]
    names = []
    seen_names = set()
    for row in rows_sorted:
        name = (row.get("name") or "").strip()
        if name and name.lower() not in seen_names:
            seen_names.add(name.lower())
            names.append(name)
    primary_name = names[-1] if names else latest.get("name")
    aka = [n for n in names if n != primary_name]

    emails = [r.get("email") for r in rows_sorted if r.get("email")]
    email = emails[-1] if emails else None

    contact_numbers = []
    seen_nums = set()
    for row in rows_sorted:
        for num in row.get("contact_numbers") or []:
            if num and num not in seen_nums:
                seen_nums.add(num)
                contact_numbers.append(num)
        primary = row.get("contact_number")
        if primary and primary not in seen_nums:
            seen_nums.add(primary)
            contact_numbers.append(primary)

    products = []
    seen_prod = set()
    for row in rows_sorted:
        for tag in canonicalize_product(row.get("product")):
            if tag not in seen_prod:
                seen_prod.add(tag)
                products.append(tag)

    history = []
    for row in rows_sorted[:-1]:
        history.append(
            {
                "excel_row": row.get("excel_row"),
                "date": row.get("date"),
                "source": row.get("source"),
                "product": row.get("product"),
                "status": row.get("status"),
                "remarks": row.get("remarks"),
            }
        )

    sendable, phone_class, ready = pick_sendable_phone(
        contact_numbers, latest.get("contact_number")
    )
    stored_numbers = []
    seen_stored = set()
    for num in contact_numbers:
        n = normalize_wa_phone(num) or num
        if n and n not in seen_stored:
            seen_stored.add(n)
            stored_numbers.append(n)
    if sendable and sendable not in seen_stored:
        stored_numbers.insert(0, sendable)
    contact_number = sendable or latest.get("contact_number")
    return {
        "lead_id": str(uuid4()),
        "name": primary_name,
        "aka": aka,
        "email": email,
        "contact_number": contact_number,
        "contact_numbers": stored_numbers,
        "phone_class": phone_class,
        "whatsapp_ready": bool(contact_number) and ready,
        "source": latest.get("source"),
        "products": products,
        "product_raw": latest.get("product"),
        "pipeline": map_pipeline(latest.get("status")),
        "status_raw": latest.get("status"),
        "referred_by": latest.get("referred_by"),
        "discovery_call_status": latest.get("discovery_call_status"),
        "discovery_call_date": latest.get("discovery_call_date"),
        "remarks": latest.get("remarks"),
        "instagram_handle": latest.get("instagram_handle"),
        "first_touch_date": rows_sorted[0].get("date"),
        "last_touch_date": latest.get("date"),
        "history": history,
        "imported_from": "coachee_leads.json",
        "created_at": now,
        "updated_at": now,
    }


def import_coachee_json(payload: dict, replace: bool = True) -> dict:
    """Collapse 657 Excel rows into one person per phone (+ no-number docs)."""
    now = datetime.now(timezone.utc)
    rows = payload.get("leads") or []
    by_phone = defaultdict(list)
    no_phone = []
    for row in rows:
        phone = row.get("contact_number")
        key = normalize_wa_phone(phone) if phone else ""
        if key:
            by_phone[key].append(row)
        elif phone:
            by_phone[phone].append(row)
        else:
            no_phone.append(row)

    people = [_person_from_rows(group, now) for group in by_phone.values()]
    for row in no_phone:
        people.append(_person_from_rows([row], now))

    if replace:
        leads.delete_many({})

    if people:
        leads.insert_many(people)

    try:
        leads.create_index(
            "contact_number",
            unique=True,
            partialFilterExpression={"contact_number": {"$type": "string"}},
            name="contact_number_unique_string",
        )
    except Exception as e:
        logger.warning("Could not ensure contact_number index", extra={"error": str(e)})

    stats = get_lead_stats()
    logger.info(
        "Imported coachee people",
        extra={"people": stats["total"], "from_rows": len(rows)},
    )
    return {
        "people": stats["total"],
        "from_rows": len(rows),
        "unique_phones": len(by_phone),
        "no_number": len(no_phone),
        "stats": stats,
    }


def _lead_sort_key(doc: dict):
    return doc.get("updated_at") or doc.get("created_at") or datetime.min.replace(
        tzinfo=timezone.utc
    )


def recompute_lead_phones() -> dict:
    """Normalize numbers, promote a sendable India/UAE number, merge duplicates."""
    now = datetime.now(timezone.utc)
    docs = list(leads.find({}))
    groups = defaultdict(list)
    no_key = []
    for doc in docs:
        sendable, cls, ready = pick_sendable_phone(
            doc.get("contact_number"), doc.get("contact_numbers")
        )
        if sendable:
            groups[sendable].append((doc, cls, ready, sendable))
        else:
            no_key.append((doc, cls, ready))

    rewritten = 0
    merged = 0
    for key, items in groups.items():
        items.sort(key=lambda pair: _lead_sort_key(pair[0]))
        keeper_doc, cls, ready, sendable = items[-1]
        numbers = []
        seen = set()
        names = []
        aka = []
        products = []
        seen_prod = set()
        history = list(keeper_doc.get("history") or [])
        for doc, _, _, _ in items:
            for num in [doc.get("contact_number"), *(doc.get("contact_numbers") or [])]:
                n = normalize_wa_phone(num) or num
                if n and n not in seen:
                    seen.add(n)
                    numbers.append(n)
            name = (doc.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
            for extra in doc.get("aka") or []:
                if extra and extra not in aka and extra not in names:
                    aka.append(extra)
            for tag in doc.get("products") or []:
                if tag and tag not in seen_prod:
                    seen_prod.add(tag)
                    products.append(tag)
            if doc is not keeper_doc:
                history.extend(doc.get("history") or [])
        if sendable and sendable not in seen:
            numbers.insert(0, sendable)
        primary_name = names[-1] if names else keeper_doc.get("name")
        extra_aka = [n for n in names if n != primary_name] + aka
        set_fields = {
            "contact_number": sendable,
            "contact_numbers": numbers,
            "phone_class": cls,
            "whatsapp_ready": ready,
            "updated_at": now,
        }
        if primary_name:
            set_fields["name"] = primary_name
        if extra_aka:
            set_fields["aka"] = extra_aka
        if products:
            set_fields["products"] = products
        if history:
            set_fields["history"] = history
        extra_ids = [pair[0]["_id"] for pair in items[:-1]]
        unchanged = (
            not extra_ids
            and keeper_doc.get("contact_number") == sendable
            and keeper_doc.get("whatsapp_ready") == ready
            and keeper_doc.get("phone_class") == cls
        )
        if unchanged:
            continue
        # Delete extras first so the unique contact_number index is free.
        if extra_ids:
            leads.delete_many({"_id": {"$in": extra_ids}})
            merged += 1
        leads.update_one({"_id": keeper_doc["_id"]}, {"$set": set_fields})
        rewritten += 1

    for doc, cls, ready in no_key:
        if doc.get("whatsapp_ready") is False and doc.get("phone_class") == cls:
            continue
        leads.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "phone_class": cls,
                    "whatsapp_ready": False,
                    "updated_at": now,
                }
            },
        )
        rewritten += 1

    logger.info(
        "Recomputed lead phones",
        extra={"rewritten": rewritten, "merged_groups": merged},
    )
    return {"rewritten": rewritten, "merged_groups": merged}


def upsert_quiz_lead(
    name: str,
    phone: str,
    email: str | None,
    archetype: str | None,
    answers: dict | None,
) -> dict:
    sendable, cls, ready = pick_sendable_phone(phone)
    stored = sendable or normalize_wa_phone(phone)
    now = datetime.now(timezone.utc)
    existing = None
    if stored:
        existing = leads.find_one(
            {
                "$or": [
                    {"contact_number": stored},
                    {"contact_numbers": stored},
                    {"contact_number": phone},
                ]
            }
        )
    payload = {
        "name": name,
        "email": email or None,
        "contact_number": stored or None,
        "phone_class": cls,
        "whatsapp_ready": ready,
        "source": "Money Ceiling Quiz",
        "quiz_archetype": archetype,
        "quiz_answers": answers or {},
        "updated_at": now,
    }
    quiz_event = _engagement_event(
        "quiz_submitted",
        now,
        label=f"Quiz submitted{f' · {archetype}' if archetype else ''}",
    )
    if existing:
        update: dict = {
            "$set": payload,
            "$push": {"engagement": quiz_event},
        }
        if stored:
            update["$addToSet"] = {"contact_numbers": stored}
        leads.update_one({"lead_id": existing["lead_id"]}, update)
        return get_lead_by_id(existing["lead_id"])
    lead = {
        **payload,
        "lead_id": str(uuid4()),
        "contact_numbers": [stored] if stored else [],
        "aka": [],
        "products": [],
        "pipeline": "nurture",
        "engagement": [quiz_event],
        "created_at": now,
    }
    leads.insert_one(lead)
    return get_lead_by_id(lead["lead_id"])


def register_for_masterclass(
    phone: str,
    username: str | None,
    masterclass: dict,
) -> dict | None:
    """Create or update a People row for the Active masterclass registration."""
    stored = normalize_wa_phone(phone) or phone
    if not stored or not masterclass:
        return None
    mc_id = masterclass.get("masterclass_id")
    title = (masterclass.get("title") or "Masterclass").strip()
    link = (masterclass.get("meeting_link") or "").strip()
    if not mc_id or not link:
        return None

    now = datetime.now(timezone.utc)
    product_tag = f"MC · {title}"
    registration = {
        "masterclass_id": mc_id,
        "title": title,
        "registered_at": now,
        "meeting_link": link,
    }

    existing = leads.find_one(
        {
            "$or": [
                {"contact_number": stored},
                {"contact_numbers": stored},
            ]
        }
    )
    already = False
    if existing:
        for row in existing.get("masterclass_registrations") or []:
            if isinstance(row, dict) and row.get("masterclass_id") == mc_id:
                already = True
                break

    if existing:
        if already:
            eng = _engagement_event(
                "masterclass_reengaged",
                now,
                masterclass_id=mc_id,
                title=title,
                label=f"Re-engaged · {title}",
            )
            update = {
                "$set": {
                    "updated_at": now,
                    "masterclass_registered_at": now,
                },
                "$addToSet": {
                    "products": {"$each": ["Registered", product_tag]},
                    "contact_numbers": stored,
                },
                "$push": {"engagement": eng},
            }
        else:
            eng = _engagement_event(
                "masterclass_registered",
                now,
                masterclass_id=mc_id,
                title=title,
                label=f"Registered · {title}",
            )
            update = {
                "$set": {
                    "updated_at": now,
                    "masterclass_registered_at": now,
                },
                "$addToSet": {
                    "products": {"$each": ["Registered", product_tag]},
                    "contact_numbers": stored,
                },
                "$push": {
                    "masterclass_registrations": registration,
                    "engagement": eng,
                },
            }
        leads.update_one({"lead_id": existing["lead_id"]}, update)
        lead_id = existing["lead_id"]
    else:
        sendable, cls, ready = pick_sendable_phone(stored)
        contact = sendable or stored
        name = (username or "").strip() or f"WhatsApp {contact[-4:]}"
        eng = _engagement_event(
            "masterclass_registered",
            now,
            masterclass_id=mc_id,
            title=title,
            label=f"Registered · {title}",
        )
        lead = {
            "lead_id": str(uuid4()),
            "name": name,
            "aka": [],
            "email": None,
            "contact_number": contact,
            "contact_numbers": [contact],
            "phone_class": cls,
            "whatsapp_ready": ready,
            "source": "WhatsApp Masterclass",
            "products": ["Registered", product_tag],
            "pipeline": "nurture",
            "masterclass_registrations": [registration],
            "masterclass_registered_at": now,
            "engagement": [eng],
            "created_at": now,
            "updated_at": now,
        }
        leads.insert_one(lead)
        lead_id = lead["lead_id"]

    user_set = {
        "masterclass_registered_at": now,
        "masterclass_id": mc_id,
        "updated_at": now,
        "phone_number": stored,
    }
    if username:
        user_set["username"] = username
    idac.update_one(
        {"phone_number": stored},
        {
            "$set": user_set,
            "$setOnInsert": {
                "created_at": now,
                "chat_history": [],
                "service_selected": None,
            },
        },
        upsert=True,
    )
    return get_lead_by_id(lead_id)


def mark_masterclass_registered(phone: str) -> None:
    """Deprecated: use register_for_masterclass with the Active masterclass."""
    logger.warning(
        "mark_masterclass_registered called without masterclass context",
        extra={"phone": phone},
    )


