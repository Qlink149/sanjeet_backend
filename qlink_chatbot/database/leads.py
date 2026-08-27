"""Coachee people: query helpers and JSON import (one doc per phone)."""

from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from qlink_chatbot.database.collections import leads
from qlink_chatbot.utils.logger_config import logger

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
    whatsapp_ready_only: bool = False,
    no_number_only: bool = False,
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
    if no_number_only:
        query["$or"] = [
            {"contact_number": {"$exists": False}},
            {"contact_number": None},
            {"contact_number": ""},
        ]
    elif whatsapp_ready_only:
        query["whatsapp_ready"] = True
        query["contact_number"] = {"$nin": [None, ""]}
    return query


def _serialize_lead(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("_id", None)
    for field in ("created_at", "updated_at"):
        value = doc.get(field)
        if isinstance(value, datetime):
            doc[field] = value.isoformat()
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

    phone_class = latest.get("phone_class")
    contact_number = latest.get("contact_number")
    return {
        "lead_id": str(uuid4()),
        "name": primary_name,
        "aka": aka,
        "email": email,
        "contact_number": contact_number,
        "contact_numbers": contact_numbers,
        "phone_class": phone_class,
        "whatsapp_ready": bool(contact_number) and is_whatsapp_ready(phone_class),
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
        if phone:
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
