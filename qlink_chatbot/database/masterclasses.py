"""Dashboard-managed masterclasses (exactly one Active for WhatsApp)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from qlink_chatbot.database.collections import leads, masterclasses
from qlink_chatbot.utils.logger_config import logger


def _serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("_id", None)
    for field in ("created_at", "updated_at"):
        value = doc.get(field)
        if isinstance(value, datetime):
            doc[field] = value.isoformat()
    return doc


def _normalize_message_body(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _registrant_counts() -> dict[str, int]:
    pipeline = [
        {"$match": {"masterclass_registrations.0": {"$exists": True}}},
        {"$unwind": "$masterclass_registrations"},
        {
            "$group": {
                "_id": "$masterclass_registrations.masterclass_id",
                "count": {"$sum": 1},
            }
        },
    ]
    return {
        row["_id"]: int(row["count"])
        for row in leads.aggregate(pipeline)
        if row.get("_id")
    }


def list_masterclasses() -> list[dict]:
    docs = list(masterclasses.find({}).sort([("is_active", -1), ("updated_at", -1)]))
    counts = _registrant_counts()
    out = []
    for doc in docs:
        item = _serialize(doc)
        item["registrant_count"] = counts.get(item.get("masterclass_id"), 0)
        out.append(item)
    return out


def get_masterclass(masterclass_id: str) -> dict | None:
    if not masterclass_id:
        return None
    doc = masterclasses.find_one({"masterclass_id": masterclass_id})
    if not doc:
        return None
    item = _serialize(doc)
    counts = _registrant_counts()
    item["registrant_count"] = counts.get(masterclass_id, 0)
    return item


def get_active_masterclass() -> dict | None:
    doc = masterclasses.find_one({"is_active": True})
    return _serialize(doc) if doc else None


def list_masterclass_registrants(masterclass_id: str) -> list[dict]:
    """People who have a registration row for this masterclass_id (one seat each)."""
    if not masterclass_id:
        return []
    cursor = leads.find(
        {"masterclass_registrations.masterclass_id": masterclass_id},
        {
            "_id": 0,
            "lead_id": 1,
            "name": 1,
            "contact_number": 1,
            "source": 1,
            "masterclass_registrations": 1,
        },
    )
    rows = []
    for doc in cursor:
        registered_at = None
        title = None
        for reg in doc.get("masterclass_registrations") or []:
            if not isinstance(reg, dict):
                continue
            if reg.get("masterclass_id") != masterclass_id:
                continue
            registered_at = reg.get("registered_at")
            title = reg.get("title")
            break
        if isinstance(registered_at, datetime):
            registered_at = registered_at.isoformat()
        rows.append(
            {
                "lead_id": doc.get("lead_id"),
                "name": doc.get("name"),
                "contact_number": doc.get("contact_number"),
                "source": doc.get("source"),
                "registered_at": registered_at,
                "title": title,
            }
        )
    rows.sort(
        key=lambda r: r.get("registered_at") or "",
        reverse=True,
    )
    return rows


def create_masterclass(
    title: str,
    meeting_link: str,
    notes: str | None = None,
    activate: bool = False,
) -> dict:
    now = datetime.now(timezone.utc)
    masterclass_id = str(uuid4())
    doc = {
        "masterclass_id": masterclass_id,
        "title": title.strip(),
        "meeting_link": _normalize_message_body(meeting_link),
        "notes": (notes or "").strip() or None,
        "is_active": False,
        "created_at": now,
        "updated_at": now,
    }
    masterclasses.insert_one(doc)
    if activate:
        set_active(masterclass_id)
        return get_masterclass(masterclass_id)
    logger.info("Masterclass created", extra={"masterclass_id": masterclass_id})
    item = _serialize(doc)
    item["registrant_count"] = 0
    return item


def update_masterclass(
    masterclass_id: str,
    *,
    title: str | None = None,
    meeting_link: str | None = None,
    notes: str | None = None,
) -> dict | None:
    existing = masterclasses.find_one({"masterclass_id": masterclass_id})
    if not existing:
        return None
    fields: dict = {"updated_at": datetime.now(timezone.utc)}
    if title is not None:
        fields["title"] = title.strip()
    if meeting_link is not None:
        fields["meeting_link"] = _normalize_message_body(meeting_link)
    if notes is not None:
        fields["notes"] = notes.strip() or None
    masterclasses.update_one({"masterclass_id": masterclass_id}, {"$set": fields})
    return get_masterclass(masterclass_id)


def set_active(masterclass_id: str) -> dict | None:
    existing = masterclasses.find_one({"masterclass_id": masterclass_id})
    if not existing:
        return None
    now = datetime.now(timezone.utc)
    masterclasses.update_many({}, {"$set": {"is_active": False, "updated_at": now}})
    masterclasses.update_one(
        {"masterclass_id": masterclass_id},
        {"$set": {"is_active": True, "updated_at": now}},
    )
    logger.info("Masterclass activated", extra={"masterclass_id": masterclass_id})
    return get_masterclass(masterclass_id)


def deactivate_all() -> int:
    now = datetime.now(timezone.utc)
    result = masterclasses.update_many(
        {"is_active": True},
        {"$set": {"is_active": False, "updated_at": now}},
    )
    return result.modified_count


def delete_masterclass(masterclass_id: str) -> tuple[bool, str]:
    existing = masterclasses.find_one({"masterclass_id": masterclass_id})
    if not existing:
        return False, "Masterclass not found"
    if existing.get("is_active"):
        return False, "Deactivate this masterclass before deleting it"
    masterclasses.delete_one({"masterclass_id": masterclass_id})
    return True, "Deleted"


def build_masterclass_reply(mc: dict) -> str:
    return _normalize_message_body(mc.get("meeting_link") or "")
